"""Checks for ci.py that need no network: test counting, line counts, step detection, records and the document."""

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci  # noqa: E402

STAMP = "2026-10-10T12:50:01.1234567Z "


def log(*lines):
    return "\n".join(STAMP + line for line in lines)


def commit(n, wall, day="2026-10-01", ok=True, title=None):
    start = f"{day}T{n % 24:02d}:00:00Z"
    return {"sha": f"{n:040d}", "day": day, "created": f"{day}T{n % 24:02d}:00:00Z", "ok": ok, "wall_min": wall,
            "title": title or f"Change {n} (#{n})", "workflows": {"CI": "success"},
            "jobs": [{"workflow": "CI", "name": "tests", "min": wall, "started": start, "completed": start}]}


class Tests(unittest.TestCase):
    def test_patterns_sum_every_count_they_capture(self):
        text = log("packages/cli test:       Tests  120 passed | 2 skipped (122)",
                   "packages/web test:       Tests  1 failed | 300 passed (301)",
                   "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m5 passed\x1b[39m\x1b[22m\x1b[90m (5)\x1b[39m",
                   "Lint passed")
        self.assertEqual(ci.tests_in(text, [re.compile(r"\bTests\s.*?(\d+) passed")]), 425)

    def test_several_patterns_and_groups(self):
        text = log("test result: ok. 12 passed; 1 failed; 1 ignored; 0 measured",
                   "Passed!  - Failed:     0, Passed:    42, Skipped:     1, Total:    43")
        patterns = [re.compile(r"test result: \w+\. (\d+) passed; (\d+) failed"), re.compile(r"Passed:\s+(\d+),")]
        self.assertEqual(ci.tests_in(text, patterns), 55)

    def test_no_summary(self):
        self.assertIsNone(ci.tests_in(log("Lint passed", "done"), [re.compile(r"Ran (\d+) tests")]))

    def test_log_read_retries_when_gh_refuses_escapes(self):
        calls = []

        def fake(path, raw=False, *flags):
            calls.append(flags)
            if not flags:
                raise RuntimeError(f"gh api {path}: the response contains terminal escape sequences; pass "
                                   "--allow-escape-sequences to output it anyway")
            return b"Ran 3 tests in 0.1s"
        real, ci.gh = ci.gh, fake
        try:
            self.assertEqual(ci.tests_in(ci.job_log("o/r", 1), [re.compile(r"Ran (\d+) tests")]), 3)
        finally:
            ci.gh = real
        self.assertEqual(calls, [(), ("--allow-escape-sequences",)])

    def test_tests_per_day_count_a_matrix_once(self):
        c = commit(1, 5.0)
        c["jobs"] = [{"id": i, "workflow": "CI", "name": f"test (py{v})", "min": 5.0} for i, v in ((1, "3.11"), (2, "3.14"))]
        c["jobs"].append({"id": 3, "workflow": "CI", "name": "lint", "min": 1.0})
        data = {"repo": "o/r", "days": [{"day": "2026-10-01"}, {"day": "2026-10-02"}], "commits": [c]}
        logs = {1: "Ran 10 tests in 1s", 2: "Ran 12 tests in 1s", 3: "All checks passed"}
        real, ci.job_log = ci.job_log, lambda repo, job: logs[job]
        try:
            ci.add_tests(data, [r"Ran (\d+) tests"])
        finally:
            ci.job_log = real
        self.assertEqual(data["days"][0]["tests"], 12)
        self.assertEqual(data["days"][0]["tests_pattern"], r"Ran (\d+) tests")
        self.assertNotIn("tests", data["days"][1], "a day without a green commit has no count")
        with self.assertRaises(SystemExit):
            ci.add_tests(data, [r"Ran \d+ tests"])

    def test_test_paths_across_languages(self):
        tests = ["tests/test_app.py", "src/app_test.go", "web/button.test.tsx", "App.Tests/LoginTests.cs",
                 "spec/models/user_spec.rb", "crates/core/tests/parse.rs", "src/FooTest.java"]
        code = ["src/app.py", "src/main.rs", "App/Login.cs", "web/button.tsx", "src/latest.py"]
        self.assertEqual([t for t in tests if not ci.TEST_PATH.search(t)], [])
        self.assertEqual([c for c in code if ci.TEST_PATH.search(c)], [])

    def test_count_lines_splits_code_and_tests(self):
        with tempfile.TemporaryDirectory() as root:
            for name, text in {"src/app.py": "a = 1\n\nb = 2\n", "tests/test_app.py": "assert 1\n",
                               "README.md": "words\n" * 50}.items():
                (Path(root) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(root) / name).write_text(text)
            subprocess.run(["git", "init", "-q", root], check=True)
            subprocess.run(["git", "-C", root, "add", "."], check=True)
            self.assertEqual(ci.count_lines(root), {"code_lines": 2, "test_lines": 1})

    def test_tail_and_spread(self):
        walls = [10.0, 11.0, 12.0, 13.0, 30.0]
        self.assertEqual((ci.median(walls), ci.p95(walls), ci.spread(walls)), (12.0, 30.0, 1.0))
        self.assertEqual(ci.p95(range(1, 41)), 38)
        self.assertIsNone(ci.spread([5.0]))

    def test_shift_found_with_its_suspects(self):
        commits = [commit(n, 5.0) for n in range(10)] + [commit(n, 9.0, "2026-10-02") for n in range(10, 20)]
        found = ci.shifts({"repo": "o/r", "commits": commits})
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["day"], found[0]["direction"], found[0]["change_min"]), ("2026-10-02", "slower", 4.0))
        self.assertIn(10, [s["pr"] for s in found[0]["suspects"]])

    def test_noise_is_not_a_shift(self):
        commits = [commit(n, 5.0 + (n % 3) * 0.2) for n in range(30)]
        self.assertEqual(ci.shifts({"repo": "o/r", "commits": commits}), [])

    def test_hang_stretch_names_its_ends(self):
        commits = [commit(n, 2.0) for n in range(5)] + [commit(n, 360.0, ok=False) for n in range(5, 8)] + \
                  [commit(8, 2.5, ok=False), commit(9, 2.0)]
        found = ci.hangs({"repo": "o/r", "commits": commits})
        self.assertEqual([(h["commits"], h["first"]["pr"], h["last"]["pr"], h["after"]["pr"]) for h in found],
                         [(3, 5, 7, 8)])

    def test_ub_bridge_uses_one_server_and_waits_for_sync(self):
        server = """#!/usr/bin/env python3
import json, os, sys
assert sys.argv[1:] == ["mcp", "serve"]
with open(os.path.join(os.path.dirname(sys.argv[0]), "starts"), "a") as f:
    f.write("x")
pending = 1
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        continue
    print(json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {}}), flush=True)
    if m["method"] == "initialize":
        result = {"capabilities": {}, "client": m["params"]["clientInfo"]["title"]}
    elif m["params"]["name"] == "sync_status":
        result = {"content": [{"type": "text", "text": json.dumps({"unsyncedChanges": pending})}]}
        pending = 0
    else:
        result = {"content": [{"type": "text", "text": json.dumps(m["params"].get("arguments"))}]}
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": result}), flush=True)
"""
        with tempfile.TemporaryDirectory() as bin_:
            (Path(bin_) / "ub").write_text(server)
            (Path(bin_) / "ub").chmod(0o755)
            path, poll = os.environ["PATH"], ci.SETTLE_POLL
            os.environ["PATH"], ci.SETTLE_POLL = f"{bin_}:{path}", 0
            try:
                out = ci.ub_calls([{"tool": "search", "arguments": {"query": "CI health"}},
                                   {"tool": "update_data", "arguments": {"uuid": "u", "operations": []}}], bin_)
            finally:
                os.environ["PATH"], ci.SETTLE_POLL = path, poll
            self.assertEqual([json.loads(o["result"]) for o in out],
                             [{"query": "CI health"}, {"uuid": "u", "operations": []}])
            self.assertEqual((Path(bin_) / "starts").read_text(), "x", "one server for every call")

    def test_records_and_document(self):
        data = {"repo": "o/r", "branch": "main", "jobs": {"ci_tests_min": "CI / tests"},
                "days": [{"day": "2026-10-01", "repo": "o/r", "commits": 3, "failed": 0, "wall_min": 5.0,
                          "wall_min_7d": 5.0, "ci_tests_min": 5.0, "tests": 10}]}
        incidents = [{"day": "2026-10-01", "repo": "o/r", "direction": "faster", "before_min": 9, "after_min": 5,
                      "title": "Split the tests", "ref": "o/r#7", "why": "Two jobs instead of one."}]
        batch = ci.records(data, incidents)
        self.assertEqual([b["collection"] for b in batch], ["days", "incidents"])
        self.assertIn("ci_tests_min", batch[0]["schema"]["schema"]["properties"])
        self.assertEqual(batch[1]["upsert"][0]["id"], "2026-10-01/o-r-7")
        same_day = incidents + [dict(incidents[0], ref="abc123", title="Drop macOS")]
        self.assertEqual([r["id"] for r in ci.incident_rows(same_day)], ["2026-10-01/o-r-7", "2026-10-01/abc123"])
        self.assertEqual(batch[1]["upsert"][0]["value"]["url"], "https://github.com/o/r/pull/7")
        with self.assertRaises(SystemExit):
            ci.records(data, [dict(incidents[0], repo="o/other")])
        doc = ci.create_document(data, incidents)
        types = [b["type"] for b in doc["blocks"]]
        self.assertLess(types.index("chart"), types.index("heading"), "incidents sit below the charts")
        charts = [json.loads(b["text"]) for b in doc["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["collection"] for c in charts], ["days", "days"])
        data["days"][0] |= {"code_lines": 900, "test_lines": 300, "test_ratio": 0.33, "coverage_pct": 81.5}
        self.assertEqual([json.loads(b["text"])["title"] for b in ci.charts(data) if b["type"] == "chart"],
                         ["Wall time on main", "Tests", "Test to code ratio", "Test coverage"])
        self.assertIn("coverage_pct", ci.schema(data)["schema"]["properties"])
        self.assertEqual([y["field"] for y in charts[0]["y"][:2]], ["wall_min_7d", "wall_p95_7d"])
        self.assertTrue(all(len(c["y"]) <= 8 for c in charts))
        self.assertTrue(len(doc["description"]) <= 300 and len(doc["tldr"]) <= 300)
        items = [b for b in doc["blocks"] if b["type"] == "list-item"]
        self.assertIn("Split the tests", items[0]["inline"][1]["text"])
        with self.assertRaises(SystemExit):
            ci.incident_rows([{"day": "2026-10-01", "repo": "o/r", "direction": "up", "title": "t", "why": "w"}])


if __name__ == "__main__":
    unittest.main()
