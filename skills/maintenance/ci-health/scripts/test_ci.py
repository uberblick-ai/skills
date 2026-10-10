"""Checks for ci.py that need no network: test counting, step detection, records and the document."""

import json
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
    def test_vitest_summaries_add_up_across_packages(self):
        text = log("packages/cli test:       Tests  120 passed | 2 skipped (122)",
                   "packages/web test:       Tests  1 failed | 300 passed (301)",
                   "\x1b[2m      Tests \x1b[22m \x1b[1m\x1b[32m5 passed\x1b[39m\x1b[22m\x1b[90m (5)\x1b[39m")
        self.assertEqual(ci.tests_in(text), 426)

    def test_playwright(self):
        self.assertEqual(ci.tests_in(log("Running 80 tests using 2 workers", "  2 skipped", "  1 flaky",
                                         "  77 passed (3.4m)")), 78)

    def test_unittest_drops_skipped_and_its_own_marks(self):
        text = log("........s....", "-" * 70, "Ran 13 tests in 2.000s (4 workers)", "", "OK (skipped=1)")
        self.assertEqual(ci.tests_in(text), 12)

    def test_node_runner(self):
        self.assertEqual(ci.tests_in(log("ℹ tests 40", "ℹ suites 3", "ℹ skipped 2")), 38)
        self.assertEqual(ci.tests_in(log("Run node --test --test-reporter=dot", "..........X.....")), 16)

    def test_pytest(self):
        self.assertEqual(ci.tests_in(log("======= 3 failed, 97 passed, 4 skipped in 12.30s =======")), 100)

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
            self.assertEqual(ci.tests_in(ci.job_log("o/r", 1)), 3)
        finally:
            ci.gh = real
        self.assertEqual(calls, [(), ("--allow-escape-sequences",)])

    def test_no_summary(self):
        self.assertIsNone(ci.tests_in(log("Lint passed", "done")))

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

    def test_records_and_document(self):
        data = {"repo": "o/r", "branch": "main", "jobs": {"ci_tests_min": "CI / tests"},
                "days": [{"day": "2026-10-01", "repo": "o/r", "commits": 3, "failed": 0, "wall_min": 5.0,
                          "wall_min_7d": 5.0, "ci_tests_min": 5.0, "tests": 10}]}
        incidents = [{"day": "2026-10-01", "repo": "o/r", "direction": "faster", "before_min": 9, "after_min": 5,
                      "title": "Split the tests", "ref": "o/r#7", "why": "Two jobs instead of one."}]
        batch = ci.records(data, incidents)
        self.assertEqual([b["collection"] for b in batch], ["r", "incidents"])
        self.assertIn("ci_tests_min", batch[0]["schema"]["schema"]["properties"])
        self.assertEqual(batch[1]["upsert"][0]["id"], "r/2026-10-01")
        self.assertEqual(batch[1]["upsert"][0]["value"]["url"], "https://github.com/o/r/pull/7")
        doc = ci.create_document([data], incidents)
        charts = [json.loads(b["text"]) for b in doc["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["collection"] for c in charts], ["r", "r"])
        self.assertEqual(charts[0]["y"][0]["field"], "wall_min_7d")
        self.assertTrue(all(len(c["y"]) <= 8 for c in charts))
        items = [b for b in doc["blocks"] if b["type"] == "list-item"]
        self.assertIn("Split the tests", items[0]["inline"][1]["text"])
        with self.assertRaises(SystemExit):
            ci.incident_rows([{"day": "2026-10-01", "repo": "o/r", "direction": "up", "title": "t", "why": "w"}])


if __name__ == "__main__":
    unittest.main()
