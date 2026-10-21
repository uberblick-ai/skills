"""Checks for ci.py that need no network: test counting, line counts, step detection, records and the document."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import unquote
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

    def test_skipped_group_subtracts(self):
        text = log("Ran 1727 tests in 80.1s", "", "OK (skipped=2)")
        patterns = [re.compile(r"^Ran (\d+) tests? in "), re.compile(r"^OK \(skipped=(?P<skipped>\d+)\)")]
        self.assertEqual(ci.tests_in(text, patterns), 1725)

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

    def test_failure_rate_counts_every_attempt(self):
        def run(i, sha, conclusion, attempt=1, name="CI", hour=9):
            return {"id": i, "head_sha": sha, "head_branch": "main", "path": f".github/workflows/{name}.yml",
                    "name": name, "status": "completed", "conclusion": conclusion, "run_attempt": attempt,
                    "created_at": f"2026-10-14T{hour:02d}:00:00Z", "head_commit": {"message": sha}}
        runs = [run(1, "a", "success", attempt=2), run(2, "b", "failure", hour=10), run(3, "c", "cancelled", hour=11),
                run(4, "c", "success", name="Release", hour=11)]
        job = {"id": 9, "name": "tests", "started_at": "2026-10-14T09:00:00Z", "completed_at": "2026-10-14T09:05:00Z",
               "conclusion": "success"}

        def fake(path, raw=False, *flags):
            if path == "repos/o/r":
                return {"default_branch": "main"}
            if "/attempts/1" in path:
                return {"conclusion": "failure"}
            if "/jobs" in path:
                return {"jobs": [job]}
            return {"workflow_runs": runs}
        real, ci.gh = ci.gh, fake
        try:
            day = ci.dt.date(2026, 10, 14)
            data = ci.collect("o/r", day, day, required=["CI"])
        finally:
            ci.gh = real
        self.assertEqual([c["runs"] for c in data["commits"]], [["failure", "success"], ["failure"], ["cancelled"]],
                         "a re-run's earlier attempt counts; only the named workflows do")
        d = data["days"][0]
        self.assertEqual((d["runs"], d["failure_pct"], d["failure_pct_7d"]), (4, 66.7, 66.7),
                         "2 red of 3 attempts that ended green or red; cancelled ones are neither")
        titles = [json.loads(b["text"])["title"] for b in ci.charts(data)]
        self.assertEqual(titles[:2], ["Wall time on main", "Failed runs on main"])

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
        counters = [c for c in ci.COUNTERS if shutil.which(c)]
        if not counters:
            self.skipTest("no line counter installed")
        with tempfile.TemporaryDirectory() as root:
            for name, text in {"src/app.py": "# note\na = 1\n\nb = 2\n", "tests/test_app.py": "assert 1\n",
                               "README.md": "words\n" * 50, "config.json": '{"a": 1}\n',
                               "scripts/tool.py": "x = 1\n", "untracked/app.py": "y = 1\n"}.items():
                (Path(root) / name).parent.mkdir(parents=True, exist_ok=True)
                (Path(root) / name).write_text(text)
            subprocess.run(["git", "init", "-q", root], check=True)
            subprocess.run(["git", "-C", root, "add", ".", ":!untracked"], check=True)
            for counter in counters:
                self.assertEqual(ci.count_lines(root, counter), {"code_lines": 3, "test_lines": 1},
                                 f"{counter}: tracked code only, no blanks, comments, prose or data")
                self.assertEqual(ci.count_lines(root, counter, ["src", "tests"]), {"code_lines": 2, "test_lines": 1},
                                 f"{counter}: only the paths given")
                self.assertEqual(ci.count_lines(root, counter, [".", ":!scripts"]), {"code_lines": 2, "test_lines": 1},
                                 f"{counter}: a pathspec leaves a directory out")

    def test_no_counter_or_mise(self):
        with tempfile.TemporaryDirectory() as root:
            subprocess.run(["git", "init", "-q", root], check=True)
            path = os.environ["PATH"]
            os.environ["PATH"] = "/nonexistent"
            try:
                self.assertEqual(ci.mise_tasks(root), set(), "no mise is no tasks, not a crash")
                self.assertIsNone(ci.line_counter())
                self.assertIn("github.com/boyter/scc/releases", ci.install_hint(), "no package manager: a release")
                bin_dir = Path(root) / "bin"
                bin_dir.mkdir()
                for manager in ("apt-get", "go"):
                    (bin_dir / manager).write_text("#!/bin/sh\n")
                    (bin_dir / manager).chmod(0o755)
                os.environ["PATH"] = str(bin_dir)
                self.assertEqual(ci.install_hint(), "run `sudo apt install cloc`", "the distribution's package first")
            finally:
                os.environ["PATH"] = path

    def test_tail_and_spread(self):
        walls = [10.0, 11.0, 12.0, 13.0, 30.0]
        self.assertEqual((ci.median(walls), ci.p95(walls), ci.spread(walls)), (12.0, 30.0, 1.0))
        self.assertEqual(ci.p95(range(1, 41)), 38)
        self.assertIsNone(ci.spread([5.0]))

    def test_late_start_inside_a_push(self):
        job = lambda start, end, n: {"started": f"2026-10-10T23:{start}Z", "completed": f"2026-10-10T23:{end}Z", "min": n}
        jobs = [job("00:00", "03:00", 3.0), job("05:00", "09:00", 4.0), job("09:10", "09:13", 0.05)]
        self.assertEqual(ci.late_start(jobs), 5.0, "a summary job is left out")

    def test_shift_found_with_its_suspects(self):
        commits = [commit(n, 5.0) for n in range(10)] + [commit(n, 9.0, "2026-10-02") for n in range(10, 20)]
        found = ci.shifts({"repo": "o/r", "commits": commits})
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["day"], found[0]["direction"], found[0]["change_min"]), ("2026-10-02", "slower", 4.0))
        self.assertIn(10, [s["pr"] for s in found[0]["suspects"]])

    def test_only_collected_days_and_failed_suspects(self):
        commits = [commit(n, 5.0) for n in range(10)] + [commit(10, 6.0, "2026-10-02", ok=False)] + \
                  [commit(n, 9.0, "2026-10-02") for n in range(11, 20)]
        found = ci.shifts({"repo": "o/r", "commits": commits, "first": "2026-10-02", "last": "2026-10-02"})
        self.assertIn(10, [s["pr"] for s in found[0]["suspects"]], "a change can land on a red run")
        self.assertEqual(ci.shifts({"repo": "o/r", "commits": commits, "first": "2026-10-03", "last": "2026-10-03"}),
                         [], "steps in the lookback are context, not candidates")

    def test_noise_is_not_a_shift(self):
        commits = [commit(n, 5.0 + (n % 3) * 0.2) for n in range(30)]
        self.assertEqual(ci.shifts({"repo": "o/r", "commits": commits}), [])

    def test_hang_stretch_names_its_ends(self):
        commits = [commit(n, 2.0) for n in range(5)] + [commit(n, 360.0, ok=False) for n in range(5, 8)] + \
                  [commit(8, 2.5, ok=False), commit(9, 2.0)]
        found = ci.hangs({"repo": "o/r", "commits": commits})
        self.assertEqual([(h["commits"], h["first"]["pr"], h["last"]["pr"], h["after"]["pr"]) for h in found],
                         [(3, 5, 7, 8)])
        self.assertEqual(ci.hangs({"repo": "o/r", "commits": commits, "first": "2026-10-02", "last": "2026-10-03"}), [])

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
        self.assertEqual(doc["title"], "CI Health Report")
        runs = [r for b in doc["blocks"] for r in b.get("inline", [])]
        self.assertIn({"text": "ci-health skill", "marks": {"link": ci.SKILL_URL}}, runs)
        self.assertNotIn("npx", json.dumps(doc))
        types = [b["type"] for b in doc["blocks"]]
        self.assertLess(types.index("chart"), types.index("heading"), "incidents sit below the charts")
        charts = [json.loads(b["text"]) for b in doc["blocks"] if b["type"] == "chart"]
        self.assertEqual([c["collection"] for c in charts], ["days", "days"])
        data["days"][0] |= {"code_lines": 900, "test_lines": 300, "test_ratio": 0.33, "coverage_pct": 81.5}
        self.assertEqual([json.loads(b["text"])["title"] for b in ci.charts(data) if b["type"] == "chart"],
                         ["Wall time on main", "Tests", "Test to code ratio", "Test coverage"])
        self.assertIn("coverage_pct", ci.schema(data)["schema"]["properties"])
        self.assertTrue(all(len(c["y"]) <= 8 for c in charts))
        self.assertLessEqual(len(doc["description"]), 300)
        self.assertNotIn("tldr", doc)
        same_day = [dict(incidents[0], title="Cause", time="2026-10-01T09:00:00Z"),
                    dict(incidents[0], title="Fix", ref="o/r#8", time="2026-10-01T10:00:00Z")]
        self.assertEqual([b["inline"][1]["text"] for b in ci.changelog(same_day)], ["Fix", "Cause"],
                         "newest first within a day, whatever order they come in")
        items = [b for b in doc["blocks"] if b["type"] == "list-item"]
        self.assertIn("Split the tests", items[0]["inline"][1]["text"])
        with self.assertRaises(SystemExit):
            ci.incident_rows([{"day": "2026-10-01", "repo": "o/r", "direction": "up", "title": "t", "why": "w"}])

    def test_signals_rank_the_waiting(self):
        def push(n, day, ok=True, e2e_end="00:12", failing=()):
            job = lambda name, end, mins: {"workflow": "CI", "name": name, "started": f"{day}T00:00:00Z",
                                           "completed": f"{day}T{end}:00Z", "min": mins,
                                           "conclusion": "failure" if name in failing else "success"}
            return {"sha": f"{n:040d}", "day": day, "created": f"{day}T00:00:00Z", "ok": ok, "title": f"C (#{n})",
                    "wall_min": 12.0, "wait_min": 0.5, "late_start_min": 0.5, "workflows": {"CI": "success"},
                    "jobs": [job("e2e", e2e_end, 12.0), job("unit", "00:04", 4.0), job("summary", "00:12", 0.1)]}
        commits = [push(1, "2026-09-20")] + [push(n, "2026-10-01") for n in range(2, 6)] + \
                  [push(6, "2026-10-02", ok=False, failing=("e2e",))]
        found = ci.signals({"repo": "o/r", "last": "2026-10-02", "commits": commits})
        self.assertEqual((found["pushes"], found["days"], found["failed"]), (5, 2, 1), "the week only")
        e2e = found["jobs"][0]
        self.assertEqual((e2e["job"], e2e["ends_last"], e2e["ahead_min"], e2e["failed"]), ("CI / e2e", 1.0, 8.0, 1),
                         "a summary job ending last is not what the push waits for")
        self.assertEqual(found["waiting_min_per_day"],
                         {"slowest_job": 16.0, "failed_pushes": 6.0, "runner_waits": 2.5, "hangs": 0})

    def test_actions_records_and_cards(self):
        data = {"repo": "o/r", "branch": "main", "last": "2026-10-03", "jobs": {},
                "days": [{"day": "2026-10-03", "repo": "o/r", "commits": 9}]}
        actions = [{"id": "shard-e2e", "area": "Wall time", "title": "Shard e2e", "since": "2026-09-20",
                    "why": "It ends 8 min after the rest.", "check": "Look at ci.yml.", "impact_min_per_day": 90,
                    "where": "CI / e2e", "evidence": [7, "#8", "o/tools#3"]},
                   {"area": "Reliability", "title": "Fix flaky login spec", "why": "Failed 4 of 30 pushes."}]
        batch = ci.records(data, (), actions)
        stored = batch[-1]
        self.assertEqual((stored["collection"], [r["id"] for r in stored["replaceRecords"]]),
                         ("actions", ["shard-e2e", "fix-flaky-login-spec"]), "the set replaces the stored one")
        kept, new = (r["value"] for r in stored["replaceRecords"])
        self.assertEqual((kept["rank"], kept["since"], kept["updated"]), (1, "2026-09-20", "2026-10-03"))
        self.assertEqual((kept["where"], kept["evidence"]), ("CI / e2e", ["#7", "#8", "o/tools#3"]),
                         "numbers become references")
        self.assertNotIn("evidence", new, "no evidence, none stored")
        self.assertEqual((new["rank"], new["since"]), (2, "2026-10-03"), "a new action starts on the last day")
        self.assertNotIn("actions", [b["collection"] for b in ci.records(data)], "no actions given, none touched")
        for bad in ([actions[1]] * 2, actions * 2, [dict(actions[1], repo="o/x")], [{"area": "a", "title": "t"}],
                    [dict(actions[1], evidence=["https://example.com"])], [dict(actions[1], evidence=["o/r#x"])]):
            with self.assertRaises(SystemExit):
                ci.action_rows(data, bad)

        blocks = ci.cards(data, actions, doc="d0c")
        self.assertEqual([b["type"] for b in blocks], ["card", "card"])
        head, _, body = blocks[0]["text"].partition("\n\n")
        footer = ("footer: CI / e2e · about 90 min of waiting a day · [#7](https://github.com/o/r/issues/7) "
                  "[#8](https://github.com/o/r/issues/8) [o/tools#3](https://github.com/o/tools/issues/3)")
        self.assertIn(f"label: Wall time · since 20 Sep 2026\ntitle: Shard e2e\n{footer}\n"
                      "button: [Discuss in Claude Code]", head, "the evidence as pills, then the button")
        self.assertEqual(body, "It ends 8 min after the rest.")
        self.assertTrue(blocks[1]["text"].startswith("label: Reliability · since 3 Oct 2026\n"
                                                     "title: Fix flaky login spec\nbutton: "), "no evidence, no footer")
        self.assertEqual(ci.cost({"cost": "one more runner", "impact_min_per_day": 90}), "one more runner")
        url = re.search(r"button: \[[^]]+\]\((\S+)\)", head).group(1)
        self.assertTrue(url.startswith("claude://code/new?q="), "a new session in the desktop app")
        prompt = unquote(url.split("q=", 1)[1])
        for part in ("CI Health Report for o/r (Uberblick document d0c)", "Recommendation: Shard e2e.",
                     "Evidence: It ends 8 min after the rest.\nWhere: CI / e2e\nCost: about 90 min of waiting a day\n"
                     "Issues and PRs: o/r#7, o/r#8, o/tools#3\n\nLet's discuss", "Look at ci.yml.", "wait for my go-ahead"):
            self.assertIn(part, prompt)
        records = {"records": [{"id": r["id"], "value": r["value"]} for r in reversed(stored["replaceRecords"])]}
        self.assertEqual([b["text"] for b in ci.cards(data, records, doc="d0c")], [b["text"] for b in blocks],
                         "stored records render the same, in rank order")
        self.assertEqual(ci.cards(data, []), [{"type": "paragraph", "text": "No action proposed yet."}])
        plain = ci.cards(data, actions, doc="d0c", button=False)[0]["text"]
        self.assertEqual(plain, f"label: Wall time · since 20 Sep 2026\ntitle: Shard e2e\n{footer}\n\n"
                                "It ends 8 min after the rest.",
                         "without buttons, for Uberblick 0.4.3")

        for part in ('In Uberblick document d0c, replace the card titled "Shard e2e"', "title: ~~Shard e2e~~",
                     "footer: STATUS in [REF](URL).", "~~It ends 8 min after the rest.~~", 'collection "applied"',
                     '"id": "shard-e2e"'):
            self.assertIn(part, prompt, "applying it strikes the card through and records it")

        applied = {"records": [{"id": "shard-e2e", "value": {"status": "planned", "ref": "o/r#12",
                                                             "url": "https://github.com/o/r/issues/12"}}]}
        marked = ci.cards(data, records, doc="d0c", applied=applied)
        self.assertEqual(marked[0]["text"], "label: Wall time · since 20 Sep 2026\ntitle: ~~Shard e2e~~\n"
                         "footer: Planned in [o/r#12](https://github.com/o/r/issues/12).\n\n"
                         "~~It ends 8 min after the rest.~~", "struck through, no button, the issue as a pill below")
        self.assertEqual(marked[1]["text"], blocks[1]["text"], "the others stay as they are")
        kept = ci.records(data, (), actions[:1], applied)
        self.assertNotIn("applied", [b["collection"] for b in kept], "a kept action keeps its mark")
        dropped = ci.records(data, (), actions[1:], applied)[-1]
        self.assertEqual((dropped["collection"], dropped["deleteRecords"]), ("applied", ["shard-e2e"]),
                         "a dropped action's mark goes with it")

        doc = ci.create_document(data | {"days": [dict(data["days"][0], wall_min_7d=5.0)]}, (), actions)
        headings = [b["text"] for b in doc["blocks"] if b["type"] == "heading"]
        self.assertEqual(headings, ["Recommended Actions", "Incidents"], "actions above the incidents")
        intro = doc["blocks"][[b.get("text") for b in doc["blocks"]].index("Recommended Actions") + 1]["text"]
        self.assertTrue(intro.startswith("Up to three changes"), "no count the cards may not reach")
        self.assertEqual(len([b for b in doc["blocks"] if b["type"] == "card"]), 2)

    def test_after_fills_every_day_since_the_newest_stored_one(self):
        yesterday = ci.dt.date(2026, 10, 18)
        stored = {"records": [{"id": "2026-10-14", "value": {"day": "2026-10-14"}},
                              {"id": "2026-10-12", "value": {"day": "2026-10-12"}}, {"id": "notes", "value": {}}]}
        self.assertEqual(ci.after(ci.stored_days(stored), yesterday), ci.dt.date(2026, 10, 15), "three days missing")
        self.assertEqual(ci.after([], yesterday), yesterday, "no corpus: the last day alone")
        self.assertEqual(ci.after([yesterday], yesterday), yesterday, "nothing missing: the last day again")
        with mock.patch("sys.stderr"):
            self.assertEqual(ci.after([ci.dt.date(2026, 1, 1)], yesterday), ci.dt.date(2026, 7, 21),
                             "no further back than GitHub keeps job logs")


if __name__ == "__main__":
    unittest.main()
