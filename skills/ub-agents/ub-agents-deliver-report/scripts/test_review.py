"""Checks for review.py that need no network: evidence, the digest, records and the document's cards."""

import datetime as dt
import re
import sys
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


class Tests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
