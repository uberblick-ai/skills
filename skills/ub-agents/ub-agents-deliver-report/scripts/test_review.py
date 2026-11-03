"""Checks for review.py that need no network: evidence, the digest, records and the document's cards."""

import datetime as dt
import os
import re
import sys
import time
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review  # noqa: E402


def run(agent, started, minutes, cls):
    return {"agent": agent, "started": started, "minutes": minutes, "result": "done", "summary": "Did it.",
            "denied": [], "url": "", "class": cls}


def data(issues=(), lessons=(), actions=()):
    summary = dict.fromkeys(["deliveries", "autonomous", "runs", "wasted_runs", "human_stops", "human_wait_h",
                             "runs_with_denials", "claude_runs", "prs_merged", "prs_merged_by_loop",
                             "issues_closed", "issues_opened", "retrospectives"], 0)
    return {"repo": "o/n", "day": "2026-10-14", "timezone": "CEST +0200",
            "summary": summary | {"autonomous_pct": 50.0, "wasted_pct": None, "denial_pct": None},
            "issues": list(issues), "lessons": list(lessons), "actions": list(actions), "changes": [],
            "findings": [], "retrospectives": {"errors": [], "in_window": []}}


# What GitHub would answer for an issue or pull request, by owner/name#number.
KNOWN = {"o/r#5": "https://github.com/o/r/pull/5", "o/r#3": "https://github.com/o/r/issues/3",
         "o/x#9": "https://github.com/o/x/pull/9", "o/r#1": "https://github.com/o/r/pull/1"}


class Tests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(review, "item_url", lambda repo, number: KNOWN.get(f"{repo}#{number}"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_evidence_keeps_what_happened_outside_the_loop(self):
        d = {"number": 5, "runs": [run("integrator", "2026-10-14T04:37:00Z", 13, "waste")], "prs": [{"number": 6}]}
        timeline = {"repos/o/n/issues/5/timeline": [], "repos/o/n/issues/6/timeline": [
            {"event": "committed", "sha": "c34bdb0" + "0" * 33, "committer": {"date": "2026-10-14T03:23:42Z"},
             "author": {"name": "Claude"}, "message": "Merge main"},
            {"event": "committed", "sha": "a" * 40, "committer": {"date": "2026-10-14T04:40:00Z"},
             "author": {"name": "agent"}, "message": "Inside the run"},
            {"event": "labeled", "created_at": "2026-10-14T04:50:00Z", "actor": {"login": "loop-bot"},
             "label": {"name": "needs-human"}},
            {"event": "merged", "created_at": "2026-10-14T04:50:38Z", "actor": {"login": "maintainer"}}]}
        ci = {"workflow_runs": [{"id": 1, "name": "Test", "head_sha": "c" * 40, "conclusion": "cancelled",
                                 "created_at": "2026-10-14T03:23:49Z", "updated_at": "2026-10-14T04:10:34Z"}]}
        with mock.patch.object(review, "pages", lambda path, **_: iter(timeline[path])), \
                mock.patch.object(review, "gh", lambda *a: {"head": {"ref": "b"}} if "pulls" in a[0] else ci):
            found = review.evidence("o/n", d, dt.datetime(2026, 10, 14, 22, tzinfo=dt.timezone.utc),
                                    frozenset({"loop-bot"}))
        self.assertEqual([c["sha"] for c in found["commits"]], ["c34bdb0"])
        self.assertEqual([e["event"] for e in found["events"]], ["merged"])
        self.assertEqual([(w["result"], w["minutes"]) for w in found["ci"]], [("cancelled", 46.8)])

    def test_digest_lists_runs_in_local_time_with_targets(self):
        item = {"number": 5, "title": "Item", "delivered": True, "loop": True, "autonomous": False, "prs": [],
                "sequence": "Gx", "human_stops": 0, "human_wait_h": 0, "loop_cycle_h": None, "run_h": 0.2,
                "runs": [run("integrator", "2026-10-14T04:37:00Z", 13.3, "waste")], "retrospectives": []}
        text = review.digest(data([item]))
        self.assertIn("(50%, target 75% or more)", text)
        self.assertIn("## Needs a cause (1)", text)
        self.assertIn("  G 06:37 13.3 min waste done", text)

    def test_new_document_has_no_kpi_table(self):
        blocks = review.create_document(data())["blocks"]
        self.assertNotIn("table", [b["type"] for b in blocks])
        self.assertEqual([b["text"] for b in blocks if b["type"] == "heading"],
                         ["Data", "Recommended Actions", "Changelog"])

    def test_records_send_schemas_only_when_asked(self):
        report = data() | {"summary": data()["summary"] | {"day": "2026-10-14"}}
        self.assertFalse(any("schema" in op for op in review.records(report)))
        self.assertTrue(all("schema" in op for op in review.records(report, schemas=True)))

    def test_cards_mark_what_the_day_changed(self):
        new = {"id": "new", "lever": "wording", "title": "New", "change": "C.", "state": "proposed"}
        registry = {"lessons": [{"id": "old", "value": new | {"title": "Old", "day": "2026-10-07"}}]}
        sections = review.document(registry, data(lessons=[new], actions=["old", "new"]))
        self.assertEqual([(c["lesson"], c["changed"]) for c in sections["cards"]], [("old", False), ("new", True)])
        self.assertEqual(sections["changelog_new"], 0)
        with self.assertRaises(SystemExit):
            review.document({}, data(actions=["old"]))

    def test_a_lesson_being_applied_is_struck_through(self):
        new = {"id": "new", "lever": "wording", "title": "New", "change": "C.", "state": "proposed"}
        tracked = {"lever": "authority", "title": "Old", "change": "Do it.", "state": "tracked", "day": "2026-10-07",
                   "addressed_by": "o/r#12", "addressed_as": "implemented"}
        registry = {"lessons": [{"id": "old", "value": tracked}]}
        sections = review.document(registry, data(lessons=[new], actions=["new"]), doc="d0c")
        self.assertEqual([(c["lesson"], c["title"]) for c in sections["cards"]], [("new", "New"), ("old", "~~Old~~")])
        self.assertEqual(sections["actions"][-1]["text"], "label: Clearer authority\ntitle: ~~Old~~\n"
                         "footer: Implemented in [o/r#12](https://github.com/o/r/issues/12).\n\n~~Do it.~~",
                         "struck through, no button, the pull request as a pill below")
        prompt = unquote(re.search(r"q=(\S+)\)", sections["actions"][1]["text"]).group(1))
        for part in ('In Uberblick document d0c, replace the card titled "New"', "title: ~~New~~",
                     "footer: STATUS in [REF](URL).", "~~C.~~", 'read the record "new" of the collection "lessons"',
                     'set "state" to "tracked"'):
            self.assertIn(part, prompt)

    def test_page_declares_its_encoding_before_any_text(self):
        day = data(lessons=[{"id": "x", "lever": "wording", "title": "Prüfung — schneller…", "change": "C.",
                             "state": "proposed"}], actions=["x"])
        day["summary"] |= dict.fromkeys(["loop_cycle_h_median", "cycle_h_median", "run_h_median", "run_h",
                                         "additions", "deletions", "files"], 0) | {"headline": "Ein Tag."}
        page = review.report(day | {"retrospective_groups": []})
        self.assertTrue(page.startswith('<!doctype html><html lang="en"><meta charset="utf-8">'))
        self.assertLess(page.index('name="viewport"'), page.index("<title>"))
        self.assertIn("Prüfung — schneller…", page)

    def test_page_cards_link_a_proposed_lesson_to_claude_code(self):
        lessons = [{"id": "x", "lever": "wording", "title": "Shorter brief", "change": "Drop step 3.",
                    "where": "AGENTS.md", "cost": "5 runs on 11 October", "evidence": [7], "state": "proposed"},
                   {"id": "y", "lever": "autonomy", "title": "Merge green PRs", "change": "Let the loop merge.",
                    "state": "tracked", "addressed_by": "o/n#9"}]
        day = data(lessons=lessons, actions=["x"])
        day["summary"] |= dict.fromkeys(["loop_cycle_h_median", "cycle_h_median", "run_h_median", "run_h",
                                         "additions", "deletions", "files"], 0) | {"headline": "A day."}
        page = review.report(day | {"retrospective_groups": []})
        links = re.findall(r'<a class="discuss" href="([^"]+)">Discuss in Claude Code</a>', page)
        self.assertEqual(len(links), 1, "only the proposed lesson, not one already being handled")
        prompt = unquote(links[0].replace("&amp;", "&").split("q=", 1)[1])
        for part in ("From the delivery report for o/n, evidence as of 2026-10-14", "Recommendation: Shorter brief.",
                     "Where: AGENTS.md", "5 runs on 11 October", "items: #7", "wait for my go-ahead",
                     "\n\nFirst check that nobody is on it already: search the issues and pull requests of o/n",
                     "open ones (drafts included) and ones merged or closed in the last 30 days",
                     "as soon as a pull request implements it (a draft counts)"):
            self.assertIn(part, prompt)

    def test_a_day_is_a_utc_day_in_any_local_zone(self):
        with mock.patch.dict(os.environ, {"TZ": "Asia/Bangkok"}):
            time.tzset()
            window = review.day_window("2026-10-14")
        time.tzset()
        self.assertEqual(window[2:], (dt.datetime(2026, 10, 14, tzinfo=dt.timezone.utc),
                                      dt.datetime(2026, 10, 15, tzinfo=dt.timezone.utc)))

    def test_missing_days_since_the_newest_stored_one(self):
        yesterday = dt.date(2026, 10, 18)
        stored = {"records": [{"id": "2026-10-15", "value": {"day": "2026-10-15"}},
                              {"id": "2026-10-11", "value": {"day": "2026-10-11"}}]}
        self.assertEqual(review.missing(stored, yesterday), ["2026-10-16", "2026-10-17", "2026-10-18"])
        self.assertEqual(review.missing([], yesterday), ["2026-10-18"], "no corpus: the last day alone")
        self.assertEqual(review.missing([{"id": "2026-10-18", "value": {"day": "2026-10-18"}}], yesterday),
                         ["2026-10-18"], "nothing missing: the last day again")

    def test_document_after_a_backfill_counts_every_filled_day_as_new(self):
        lesson = {"lever": "wording", "title": "Earlier", "change": "C.", "state": "proposed", "day": "2026-10-13"}
        registry = {"lessons": [{"id": "early", "value": lesson}],
                    "changes": [{"id": "o/r#1", "value": {"day": "2026-10-13", "title": "A", "why": "W."}},
                                {"id": "o/r#2", "value": {"day": "2026-10-10", "title": "B", "why": "W."}}]}
        day = data(actions=["early"])
        self.assertEqual((review.document(registry, day)["changelog_new"],
                          review.document(registry, day)["cards"][0]["changed"]), (0, False))
        backfilled = review.document(registry, day, first="2026-10-12")
        self.assertEqual((backfilled["changelog_new"], backfilled["cards"][0]["changed"]), (1, True))

    def test_changelog_writes_each_reference_as_a_pill(self):
        changes = {"o/r#5": {"day": "2026-10-20", "title": "Fix it", "url": "https://github.com/o/r/issues/5",
                             "why": "It broke; #3 tracks the rest, x#9 and o/x#9 the docs, #404 and PR#5 stay text."},
                   "abc1234": {"day": "2026-10-19", "title": "Commit", "why": "See #3.",
                               "url": "https://github.com/o/r/commit/abc1234"}}
        pr, commit = review.changelog(changes)
        self.assertEqual(pr["inline"], [
            {"text": "20 Oct: Fix it (", "marks": {}},
            {"text": "r#5", "marks": {"link": "https://github.com/o/r/pull/5"}},
            {"text": "). It broke; ", "marks": {}},
            {"text": "#3", "marks": {"link": "https://github.com/o/r/issues/3"}},
            {"text": " tracks the rest, ", "marks": {}},
            {"text": "x#9", "marks": {"link": "https://github.com/o/x/pull/9"}},
            {"text": " and ", "marks": {}},
            {"text": "o/x#9", "marks": {"link": "https://github.com/o/x/pull/9"}},
            {"text": " the docs, #404 and PR#5 stay text.", "marks": {}}],
            "the title stays text and the reference is the link, so the web shows a pull request pill")
        self.assertEqual(commit["inline"], [
            {"text": "19 Oct: ", "marks": {}},
            {"text": "Commit", "marks": {"link": "https://github.com/o/r/commit/abc1234"}},
            {"text": " (abc1234). See ", "marks": {}},
            {"text": "#3", "marks": {"link": "https://github.com/o/r/issues/3"}},
            {"text": ".", "marks": {}}])

    def test_changelog_keeps_the_stored_link_when_github_cannot_say(self):
        changes = {"o/r#7": {"day": "2026-10-20", "title": "T", "why": "W.", "url": "https://github.com/o/r/issues/7"}}
        self.assertEqual(review.changelog(changes)[0]["inline"][1],
                         {"text": "r#7", "marks": {"link": "https://github.com/o/r/issues/7"}})

    def test_runs_keep_only_a_complete_context(self):
        context = {"window": 1000000, "first": 35000, "call_10": 70000, "peak": 160000, "compactions": 0}
        lease = {"kind": "lease", "run": "a", "agent": "reviewer", "runtime": "claude:m:high",
                 "created": "2026-10-14T04:00:00Z"}
        outcome = {"kind": "outcome", "run": "a", "status": "success", "outcome": "approved",
                   "created": "2026-10-14T04:10:00Z", "context": context}
        self.assertEqual(review.runs_of([lease, outcome])[0]["context"], context)
        for broken in ({k: v for k, v in context.items() if k != "peak"}, context | {"window": 0},
                       context | {"peak": 1}, context | {"first": "35000"}):
            self.assertIsNone(review.runs_of([lease, outcome | {"context": broken}])[0]["context"])

    def test_capacity_leaves_out_what_no_run_names(self):
        self.assertEqual(review.capacity([{"machine": "m1", "loop": "l1"}, {"machine": "m2", "loop": "l1"}]),
                         {"machines": 2, "loops": 1})
        self.assertEqual(review.capacity([{"machine": "m1", "loop": None}]), {"machines": 1})

    def test_outcomes_find_their_lease_by_comment_id(self):
        lease = {"kind": "lease", "id": 11, "run": "a", "agent": "reviewer", "runtime": "claude:m:high",
                 "created": "2026-11-01T04:00:00Z"}
        outcome = {"kind": "outcome", "lease_id": 11, "agent": "reviewer", "status": "success",
                   "outcome": "approved", "accepted": True, "created": "2026-11-01T04:10:00Z"}
        orphan = outcome | {"lease_id": 12, "created": "2026-11-01T05:00:00Z"}
        runs = review.runs_of([lease, outcome, orphan])
        self.assertEqual([(r["runtime"], r["minutes"], r["result"]) for r in runs],
                         [("claude:m:high", 10.0, "approved"), (None, None, "approved")])

    def test_context_report_groups_by_agent_and_runtime(self):
        def measured(agent, runtime, window, call_10, peak, compactions=0, cls="forward"):
            return run(agent, "2026-10-14T04:00:00Z", 10, cls) | {"runtime": runtime, "url": "u", "context": {
                "window": window, "first": 1000, "call_10": call_10, "peak": peak, "compactions": compactions}}
        issues = [{"number": 5, "runs": [measured("implementer", "codex:g:x", 400000, 100000, 320000, 1),
                                         measured("reviewer", "claude:m:h", 1000000, 50000, 60000),
                                         measured("reviewer", "claude:m:h", 1000000, 70000, 100000),
                                         run("integrator", "2026-10-14T05:00:00Z", 5, "forward") | {"runtime": "claude:m:h"},
                                         run("reviewer", "2026-10-14T06:00:00Z", 5, "pending")]}]
        summary, context = review.context_report(issues, lambda text: True)
        self.assertEqual({k: summary[k] for k in ("context_runs", "context_peak_pct_max", "context_compacted")},
                         {"context_runs": 3, "context_peak_pct_max": 80.0, "context_compacted": 1})
        self.assertEqual(summary["context_by_runtime"]["claude"], {"runs": 2, "start_pct": 6.0, "peak_pct": 8.0,
                                                                    "peak_pct_max": 10.0, "compacted": 0})
        self.assertEqual(context["unmeasured"], 1, "the pending run is not counted; the integrator run has no context")
        self.assertEqual([(a["agent"], a["runtime"], a["runs"]) for a in context["agents"]],
                         [("implementer", "codex", 1), ("reviewer", "claude", 2)])
        self.assertEqual([(t["item"], t["peak_pct"]) for t in context["top"]], [(5, 80.0), (5, 10.0), (5, 6.0)])
        self.assertEqual(review.context_report([{"number": 1, "runs": [run("reviewer", "x", 1, "forward")]}],
                                               lambda text: True), ({}, {"unmeasured": 1, "agents": [], "top": []}))

    def test_page_charts_context_over_the_stored_days(self):
        day = data()
        day["summary"] |= dict.fromkeys(["loop_cycle_h_median", "cycle_h_median", "run_h_median", "run_h",
                                         "additions", "deletions", "files"], 0) | {"headline": "A day."}
        page = review.report(day | {"retrospective_groups": []})
        self.assertIn("No run on this day recorded its context", page)
        claude = {"runs": 2, "start_pct": 6.0, "peak_pct": 8.0, "peak_pct_max": 10.0, "compacted": 0}
        codex = {"runs": 1, "start_pct": 25.0, "peak_pct": 80.0, "peak_pct_max": 80.0, "compacted": 1}
        day["summary"] |= {"context_runs": 3, "context_start_pct": 7.0, "context_peak_pct": 10.0,
                           "context_peak_pct_max": 80.0, "context_compacted": 1,
                           "context_by_runtime": {"claude": claude, "codex": codex}}
        day["context"] = {"unmeasured": 1, "agents": [
            {"agent": "implementer", "runtime": "codex", "call_10_median": 100000} | codex],
            "top": [{"item": 5, "agent": "implementer", "runtime": "codex", "url": "u", "peak_pct": 80.0,
                     "window": 400000, "compactions": 1}]}
        stored = {"2026-10-13": {"day": "2026-10-13", "context_runs": 4, "context_start_pct": 5.0,
                                 "context_peak_pct": 9.0, "context_peak_pct_max": 30.0, "context_compacted": 0},
                  "2026-10-12": {"day": "2026-10-12", "runs": 3}}
        page = review.report(day | {"retrospective_groups": []}, stored)
        self.assertEqual(re.findall(r'data-runtime="(\w+)"', page), ["all", "claude", "codex"])
        self.assertEqual(page.count("<title>2026-10-1"), 4, "two days for all runtimes, this day alone for each runtime")
        self.assertIn("↻1</text>", page)
        self.assertIn('stroke-dasharray="5 4"', page)
        self.assertIn("#5 implementer</a> 80% of 400k ↻1 · 1 runs without context", page)

    def test_stored_days_read_get_data_and_earlier_reports(self):
        folder = Path(self.enterContext(__import__("tempfile").TemporaryDirectory()))
        (folder / "days.json").write_text('{"records": [{"id": "2026-10-12", "value": {"day": "2026-10-12"}}]}')
        (folder / "report.json").write_text('{"day": "2026-10-13", "summary": {"day": "2026-10-13", "runs": 2}}')
        self.assertEqual(sorted(review.stored_days([folder / "days.json", folder / "report.json", folder / "none"])),
                         ["2026-10-12", "2026-10-13"])

    def test_documents_chart_context_with_a_heavy_start_line(self):
        chart = next(b for b in review.create_document(data())["blocks"]
                     if b["type"] == "chart" and review.CONTEXT_CHART_TITLE in b["text"])
        mapping = review.json.loads(chart["text"])
        self.assertEqual([(y["field"], y.get("type", "line"), y.get("reference")) for y in mapping["y"]],
                         [("context_start_pct", "bar", 20), ("context_peak_pct", "line", None),
                          ("context_peak_pct_max", "line", None)])
        self.assertEqual(review.document({}, data())["context_chart"]["block"], chart,
                         "the same block, for documents created before the chart existed")
        fields = review.SCHEMAS["days"]["schema"]["properties"]
        self.assertTrue({"context_runs", "context_start_pct", "context_peak_pct", "context_peak_pct_max",
                         "context_compacted", "context_by_runtime"} <= fields.keys())

    def test_document_charts_bridge_days_whose_shares_are_null(self):
        charts = {m["title"]: m for m in (review.json.loads(b["text"]) for b in review.create_document(data())["blocks"]
                                          if b["type"] == "chart") if m["type"] == "line"}
        self.assertEqual({t for t, m in charts.items() if m.get("missing") == "connect"},
                         {"Autonomy and waste", "Cycle and run time per delivery", review.CONTEXT_CHART_TITLE},
                         "a day without loop runs stores null shares and medians, so their lines connect across it")

    def test_digest_says_how_much_context_the_day_used(self):
        day = data()
        day["summary"] |= {"context_runs": 3, "context_start_pct": 7.0, "context_peak_pct": 10.0,
                           "context_peak_pct_max": 80.0, "context_compacted": 1}
        day["context"] = {"unmeasured": 1, "agents": [], "top": [{"item": 5, "agent": "implementer", "runtime": "codex"}]}
        self.assertIn("Context: 3 runs measured, 1 not; median start 7% of the window at call 10, median peak 10%, "
                      "largest 80% (#5 implementer, codex); 1 compacted.", review.digest(day))


if __name__ == "__main__":
    unittest.main()
