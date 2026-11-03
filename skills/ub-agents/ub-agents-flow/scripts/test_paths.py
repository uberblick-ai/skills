"""Checks for the path tally: config kinds, records, grouping, paths per phase and the counts."""
import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("flow_paths", HERE / "paths.py")
paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paths)

CONFIG = """\
version: 1
stop-labels: [needs-human]
agents:
  issue-preparer:
    kind: issue  # issues only
    trigger: [needs-preparation]
  implementer:
    trigger: [ready, needs-changes]
  reviewer:
    kind: pr
    trigger: [needs-review]
queue:
  dependencies: wait
"""
SINCE = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)


def comment(record, association="MEMBER"):
    body = "<!-- ub-agents:v4 -->\n✅ summary\n\n<details>\n\n```json\n" + json.dumps(record) + "\n```\n</details>"
    return {"author_association": association, "body": body}


def outcome(agent, name, created, accepted=True, status="success", **extra):
    return {"kind": "outcome", "agent": agent, "outcome": name, "status": status, "accepted": accepted,
            "created": created, **extra}


def issue(number, closed="2026-10-10T00:00:00Z", **extra):
    return {"number": number, "state": "closed" if closed else "open", "closed_at": closed, **extra}


def pull(number, merged="2026-10-10T00:00:00Z", body="", login="someone", kind="User"):
    return {"number": number, "state": "closed" if merged else "open", "closed_at": merged, "body": body,
            "pull_request": {"merged_at": merged}, "user": {"login": login, "type": kind}}


class PathTests(unittest.TestCase):
    kinds = paths.kinds_of(CONFIG)

    def test_kinds_come_from_the_config(self):
        self.assertEqual(self.kinds, {"issue-preparer": "issue", "implementer": "any", "reviewer": "pr"})

    def test_records_from_trusted_accounts_only(self):
        record = outcome("reviewer", "approved", "2026-10-02T00:00:00Z")
        self.assertEqual(paths.records_of([comment(record), comment(record, "NONE"),
                                           {"author_association": "OWNER", "body": "no record"}]), [record])

    def test_steps_leave_out_runs_that_change_no_route(self):
        self.assertEqual(paths.step_of(outcome("reviewer", "approved", "x")), "reviewer approved")
        self.assertEqual(paths.step_of(outcome("implementer", None, "x", status="blocked")), "implementer blocked")
        self.assertIsNone(paths.step_of(outcome("reviewer", "approved", "x", accepted=False)))
        self.assertIsNone(paths.step_of(outcome("reviewer", None, "x", status="failed")))
        self.assertIsNone(paths.step_of({"kind": "lease", "agent": "reviewer", "result": "success"}))

    def items(self):
        return {
            # An issue prepared, handed off to PR 11, reviewed once, merged.
            10: {"row": issue(10), "records": [outcome("issue-preparer", "prepared", "2026-10-02T00:00:00Z"),
                                               outcome("implementer", "handed-off", "2026-10-03T00:00:00Z",
                                                       handoff=11)]},
            11: {"row": pull(11, body="Closes #10"), "records": [
                outcome("reviewer", "changes-requested", "2026-10-04T00:00:00Z"),
                outcome("implementer", "handed-off", "2026-10-05T00:00:00Z", assignment=10),
                outcome("implementer", "handed-off", "2026-10-05T00:00:01Z", assignment=10),
                outcome("reviewer", "approved", "2026-10-06T00:00:00Z"),
                outcome("reviewer", "approved", "2026-10-06T01:00:00Z", accepted=False)]},
            # The same clean path twice, linked only by "Fixes".
            20: {"row": issue(20), "records": [outcome("issue-preparer", "prepared", "2026-10-02T00:00:00Z")]},
            21: {"row": pull(21, body="Fixes #20"), "records": [outcome("implementer", "handed-off", "2026-10-03T00:00:00Z"),
                                                                outcome("reviewer", "approved", "2026-10-04T00:00:00Z")]},
            30: {"row": issue(30), "records": [outcome("issue-preparer", "prepared", "2026-10-02T00:00:00Z")]},
            31: {"row": pull(31, body="closes #30"), "records": [outcome("implementer", "handed-off", "2026-10-03T00:00:00Z"),
                                                                 outcome("reviewer", "approved", "2026-10-04T00:00:00Z")]},
            # A bot's pull request with no issue.
            40: {"row": pull(40, login="dependabot[bot]", kind="Bot"),
                 "records": [outcome("reviewer", "approved", "2026-10-04T00:00:00Z")]},
            # Closed in the issue phase.
            50: {"row": issue(50), "records": [outcome("issue-preparer", "duplicate", "2026-10-02T00:00:00Z")]},
            # Still open, and one that finished before the window.
            60: {"row": issue(60, closed=None), "records": [outcome("issue-preparer", "needs-human", "2026-10-02T00:00:00Z")]},
            70: {"row": issue(70, closed="2026-09-20T00:00:00Z"),
                 "records": [outcome("issue-preparer", "prepared", "2026-09-19T00:00:00Z")]},
            # No loop run at all.
            80: {"row": issue(80), "records": []},
        }

    def test_pull_requests_join_their_issue(self):
        groups = paths.groups_of(self.items())
        self.assertEqual(groups[10], {10, 11})
        self.assertEqual(groups[20], {20, 21})
        self.assertEqual(groups[40], {40})
        self.assertNotIn(11, groups)

    def test_a_path_per_phase_without_repeats(self):
        path = paths.path_of({10, 11}, self.items(), self.kinds)
        self.assertEqual(path["issue"], ["issue-preparer prepared"])
        self.assertEqual(path["pr"], ["implementer handed-off", "reviewer changes-requested", "implementer handed-off",
                                      "reviewer approved"])
        self.assertEqual(path["end"], "merged")

    def test_tally_counts_finished_items_most_common_first(self):
        out = paths.tally(self.items(), self.kinds, SINCE, top=5)
        self.assertEqual((out["items"], out["open"]), (5, 1))
        self.assertEqual(out["entries"][0], {"entry": "issue", "count": 4, "share": 80.0})
        self.assertEqual(out["entries"][1]["entry"], "pull request by dependabot[bot]")
        issue_paths = out["phases"]["issue"]
        self.assertEqual(issue_paths[0], {"path": ["issue-preparer prepared"], "count": 3, "share": 75.0,
                                          "examples": [30, 20, 10]})
        self.assertEqual(issue_paths[1]["path"], ["issue-preparer duplicate", "closed"])
        pr_paths = out["phases"]["pr"]
        self.assertEqual(pr_paths[0]["path"], ["implementer handed-off", "reviewer approved", "merged"])
        self.assertEqual(pr_paths[0]["count"], 2)
        self.assertEqual(out["phases"]["pr_items"], 4)
        self.assertEqual(len(paths.tally(self.items(), self.kinds, SINCE, top=1)["phases"]["pr"]), 1)

    def test_summary_numbers_each_path(self):
        out = {"repository": "o/r", "since": "2026-10-01", "until": "2026-10-31", "days": 30, "kinds": self.kinds,
               **paths.tally(self.items(), self.kinds, SINCE, top=5)}
        text = paths.text(out)
        self.assertIn("o/r: 5 items finished from 2026-10-01 to 2026-10-31, 1 still open.", text)
        self.assertIn("1. 3x (75.0%) issue-preparer prepared  #30 #20 #10", text)

    def test_bad_arguments_fail(self):
        self.assertEqual(paths.main(["--repo", "not a repo"]), 2)


if __name__ == "__main__":
    unittest.main()
