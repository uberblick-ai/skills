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
                     "Where: AGENTS.md", "5 runs on 11 October", "items: #7", "wait for my go-ahead"):
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


if __name__ == "__main__":
    unittest.main()
