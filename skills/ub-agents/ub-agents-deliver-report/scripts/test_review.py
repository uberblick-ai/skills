"""Checks for review.py that need no network: evidence, the digest, targets, records and the document sections."""

import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review  # noqa: E402

UNTIL = dt.datetime(2026, 10, 14, 22, tzinfo=dt.timezone.utc)


def run(agent, started, minutes, cls, result="done", summary="Did the work.", denied=()):
    return {"agent": agent, "runtime": "claude:x", "started": started, "minutes": minutes, "result": result,
            "summary": summary, "denied": list(denied), "url": f"https://example.test/{agent}/{started}",
            "class": cls}


def item(number, runs, *, delivered=True, loop=True, autonomous=False, prs=()):
    return {"number": number, "title": f"Item {number}", "delivered": delivered, "loop": loop,
            "autonomous": autonomous, "runs": runs, "prs": list(prs),
            "sequence": " ".join(review.ROLES[r["agent"]] + review.MARK[r["class"]] for r in runs),
            "human_stops": sum(r["class"] == "stop" for r in runs), "human_wait_h": 1.5, "loop_cycle_h": 0.5,
            "run_h": 0.4, "retrospectives": []}


def data(issues, lessons=(), changes=(), actions=()):
    summary = {"deliveries": 2, "autonomous": 1, "autonomous_pct": 50.0, "runs": 6, "wasted_runs": 1,
               "wasted_pct": 16.7, "human_stops": 1, "human_wait_h": 1.5, "runs_with_denials": 1, "claude_runs": 6,
               "denial_pct": 16.7, "prs_merged": 2, "prs_merged_by_loop": 1, "issues_closed": 2, "issues_opened": 1,
               "retrospectives": 0}
    return {"repo": "owner/name", "day": "2026-10-14", "timezone": "CEST +0200", "summary": summary,
            "issues": issues, "lessons": list(lessons), "changes": list(changes), "actions": list(actions),
            "findings": [], "retrospectives": {"errors": [], "in_window": []}}


def lesson(key, title, day=None):
    value = {"lever": "wording", "title": title, "change": f"Change for {key}.", "where": "AGENTS.md",
             "cost": "1 run", "causes": ["some-cause"], "evidence": [7], "state": "proposed"}
    return value | ({"day": day} if day else {"id": key})


class Evidence(unittest.TestCase):
    def setUp(self):
        self.d = item(5, [run("integrator", "2026-10-14T04:37:00Z", 13.0, "waste", "blocked")],
                      prs=[{"number": 6, "merged": "2026-10-14T04:50:38Z", "by_loop": False}])
        timeline = {
            "repos/o/n/issues/5/timeline": [
                {"event": "labeled", "created_at": "2026-10-14T04:30:00Z", "actor": {"login": "maintainer"},
                 "label": {"name": "needs-preparation"}}],
            "repos/o/n/issues/6/timeline": [
                {"event": "committed", "sha": "c34bdb0" + "0" * 33, "committer": {"date": "2026-10-14T03:23:42Z"},
                 "author": {"name": "Claude"}, "message": "Merge main into #6\n\nbody"},
                {"event": "committed", "sha": "aaaaaaa" + "0" * 33, "committer": {"date": "2026-10-14T04:40:00Z"},
                 "author": {"name": "agent"}, "message": "Inside the run"},
                {"event": "labeled", "created_at": "2026-10-14T04:50:00Z", "actor": {"login": "loop-bot"},
                 "label": {"name": "needs-human"}},
                {"event": "merged", "created_at": "2026-10-14T04:50:38Z", "actor": {"login": "maintainer"}},
                {"event": "merged", "created_at": "2026-10-15T01:00:00Z", "actor": {"login": "maintainer"}}]}
        self.pages = mock.patch.object(review, "pages", lambda path, **_: iter(timeline[path]))
        self.gh = mock.patch.object(review, "gh", side_effect=self.fake_gh)
        self.pages.start(), self.gh.start()
        self.addCleanup(self.pages.stop), self.addCleanup(self.gh.stop)

    @staticmethod
    def fake_gh(*args):
        if args[0] == "repos/o/n/pulls/6":
            return {"head": {"ref": "agent/6"}}
        assert "-fbranch=agent/6" in args
        return {"workflow_runs": [
            {"id": 1, "name": "Test", "head_sha": "c34bdb0" + "0" * 33, "run_attempt": 1, "conclusion": "cancelled",
             "created_at": "2026-10-14T03:23:49Z", "run_started_at": "2026-10-14T03:23:49Z",
             "updated_at": "2026-10-14T04:10:34Z"},
            {"id": 2, "name": "Test", "head_sha": "b" * 40, "run_attempt": 1, "conclusion": "success",
             "created_at": "2026-10-15T03:00:00Z", "run_started_at": "2026-10-15T03:00:00Z",
             "updated_at": "2026-10-15T03:05:00Z"}]}

    def test_outside_commits_people_and_ci(self):
        found = review.evidence("o/n", self.d, UNTIL, frozenset({"loop-bot"}))
        self.assertEqual([c["sha"] for c in found["commits"]], ["c34bdb0"])
        self.assertEqual(found["commits"][0]["message"], "Merge main into #6")
        # People's changes count wherever they fall, the loop's never; nothing after the day.
        self.assertEqual([(e["item"], e["event"]) for e in found["events"]], [(5, "+needs-preparation"), (6, "merged")])
        self.assertEqual([(w["run"], w["result"], w["minutes"]) for w in found["ci"]], [(1, "cancelled", 46.8)])
        self.assertNotIn("errors", found)

    def test_without_loop_accounts_events_go_by_run_times(self):
        found = review.evidence("o/n", self.d, UNTIL)
        # The merge falls within the run's slack, the loop's label too; only the earlier change is outside.
        self.assertEqual([e["event"] for e in found["events"]], ["+needs-preparation"])

    def test_needs_cause(self):
        clean = [run("implementer", "2026-10-14T01:00:00Z", 5, "forward")]
        self.assertFalse(review.needs_cause(item(1, clean, autonomous=True)))
        self.assertTrue(review.needs_cause(item(2, clean + [run("reviewer", "2026-10-14T02:00:00Z", 3, "back")],
                                                autonomous=True)))
        self.assertTrue(review.needs_cause(item(3, clean, autonomous=False)))
        self.assertFalse(review.needs_cause(item(4, clean, delivered=False, loop=False)))


class Digest(unittest.TestCase):
    def test_sections_runs_and_targets(self):
        long = "Blocked because " + "x" * 300
        explain = item(5, [run("implementer", "2026-10-13T20:00:00Z", 10, "forward", summary="Handed off " + "y" * 300),
                           run("integrator", "2026-10-14T04:37:00Z", 13.3, "waste", "blocked", long, ["Bash: sed -n 1p f"])],
                       prs=[{"number": 6, "merged": "2026-10-14T04:50:38Z", "by_loop": False}])
        explain["evidence"] = {"commits": [{"pr": 6, "sha": "c34bdb0", "at": "2026-10-14T03:23:42Z",
                                            "author": "Claude", "message": "Merge main"}],
                               "ci": [{"pr": 6, "run": 1, "workflow": "Test", "sha": "c34bdb0", "attempt": 2,
                                       "result": "cancelled", "started": "2026-10-14T03:23:49Z", "minutes": 46.8}]}
        clean = item(7, [run("implementer", "2026-10-14T06:00:00Z", 8, "forward")], autonomous=True,
                     prs=[{"number": 8, "merged": "2026-10-14T07:00:00Z", "by_loop": True}])
        outside = item(9, [], loop=False)
        text = review.digest(data([explain, clean, outside]))
        self.assertIn("autonomous 1 (50%, target 75% or more)", text)
        self.assertIn("wasted 1 (16.7%, target under 10%)", text)
        self.assertIn("## Needs a cause (1)", text)
        self.assertIn("  G 06:37 13.3 min waste blocked", text)  # local time on the day
        self.assertIn("  I 13 Oct 22:00 10 min forward", text)  # other days carry their date
        self.assertIn(long, text)  # a run that needs explaining keeps its whole summary
        self.assertNotIn("y" * 200, text)  # a forward run keeps its gist
        self.assertIn("denied: Bash: sed -n 1p f", text)
        self.assertIn("commit outside runs: 05:23 c34bdb0 by Claude on #6: Merge main", text)
        self.assertIn("CI #6: 05:23 Test c34bdb0 cancelled 46.8 min attempt 2", text)
        self.assertIn("PR #6 merged 06:50 outside the loop", text)
        self.assertIn("## Went through cleanly (1)\n\n#7 Item 7: loop delivery, autonomous; I;", text)
        self.assertIn("## Outside the loop (1)\n\n#9 Item 9: delivered; no runs", text)


class Targets(unittest.TestCase):
    def test_floor_and_ceiling(self):
        self.assertTrue(review.on_target("autonomous_pct", 75))
        self.assertFalse(review.on_target("autonomous_pct", 66.7))
        self.assertTrue(review.on_target("wasted_pct", 4.3))
        self.assertFalse(review.on_target("wasted_pct", 10))
        self.assertFalse(review.on_target("denial_pct", 29.4))
        self.assertIsNone(review.on_target("denial_pct", None))
        self.assertIsNone(review.on_target("human_stops", 3))

    def test_page_and_new_document_show_targets(self):
        tiles = {label: (detail, field) for _, label, detail, field in review.figures(data([])["summary"] | {
            "loop_cycle_h_median": 1, "cycle_h_median": 1, "run_h_median": 1, "run_h": 1, "additions": 1,
            "deletions": 1, "files": 1})}
        self.assertEqual(tiles["autonomous"], ("50% of loop deliveries · target 75% or more", "autonomous_pct"))
        self.assertIsNone(tiles["human stops"][1])
        table = review.create_document(data([]) | {"lessons": [], "actions": []})["blocks"][3]["text"]
        self.assertIn("| KPI | Goal | Target | Definition |", table)
        self.assertIn("| Runs with denials | down | under 10% |", table)
        recent = next(b for b in review.create_document(data([]) | {"lessons": [], "actions": []})["blocks"]
                      if b["type"] == "chart" and '"Recent days"' in b["text"])
        self.assertIn('"limit": 7', recent["text"])


class Records(unittest.TestCase):
    def report(self):
        d = data([item(5, [run("implementer", "2026-10-14T01:00:00Z", 5, "forward")])])
        return d | {"findings": [{"cause": "c", "class": "ci", "mechanism": "m", "state": "open", "example": "e",
                                  "items": [5]}]}

    def test_schemas_only_when_asked(self):
        plain = review.records(self.report())
        self.assertTrue(all("schema" not in op for op in plain))
        self.assertIn("2026-09-30", next(op for op in plain if op["collection"] == "items")["deleteRecords"])
        full = review.records(self.report(), schemas=True)
        self.assertTrue(all(op["schema"] == review.SCHEMAS[op["collection"]] for op in full))
        self.assertEqual([op["upsert"] for op in plain], [op["upsert"] for op in full])


class Document(unittest.TestCase):
    def test_cards_mark_what_the_day_changed(self):
        today = lesson("new-lesson", "New lesson")
        registry = {"lessons": [{"id": "old-lesson", "value": lesson("old-lesson", "Old lesson", "2026-10-07")},
                                {"id": "new-lesson", "value": lesson("new-lesson", "Stale title", "2026-10-01")}]}
        day = data([], [today], [{"ref": "o/n#9", "day": "2026-10-14", "title": "Fix", "why": "Because."}],
                   ["old-lesson", "new-lesson"])
        sections = review.document(registry, day, "doc-uuid")
        self.assertEqual(sections["cards"], [{"lesson": "old-lesson", "title": "Old lesson", "changed": False},
                                             {"lesson": "new-lesson", "title": "New lesson", "changed": True}])
        self.assertEqual(sections["changelog_new"], 1)
        old, new = (unquote(b["text"]) for b in sections["actions"][1:])
        # A card carries its lesson's day, so it reads the same until a day proposes the lesson again.
        self.assertIn("evidence as of 2026-10-07", old)
        self.assertIn("evidence as of 2026-10-14", new)
        self.assertIn("title: New lesson", new)

    def test_missing_registry_lesson_stops(self):
        with self.assertRaises(SystemExit) as stop:
            review.document({"lessons": []}, data([], actions=["old-lesson"]))
        self.assertIn("old-lesson", str(stop.exception))

    def test_no_new_changes(self):
        sections = review.document({}, data([], [lesson("a", "A")], actions=["a"]))
        self.assertEqual(sections["changelog_new"], 0)


if __name__ == "__main__":
    unittest.main()
