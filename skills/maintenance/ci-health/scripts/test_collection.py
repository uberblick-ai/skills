"""Regression checks for failed measurements and repeated GitHub reads, without network access."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ci  # noqa: E402


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.cache_patch = mock.patch.object(ci, "CACHE", ci.ReadCache())
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def test_transient_read_retries_and_checkpoints_success(self):
        failed = subprocess.CompletedProcess([], 1, b"", b"dial tcp: i/o timeout")
        success = subprocess.CompletedProcess([], 0, b'{"jobs": []}', b"")
        with tempfile.TemporaryDirectory() as root, mock.patch.object(ci.time, "sleep") as sleep:
            ci.CACHE = ci.ReadCache(root)
            with mock.patch.object(ci.subprocess, "run", side_effect=[failed, success]) as run:
                self.assertEqual(ci.gh("repos/o/r/jobs"), {"jobs": []})
                self.assertEqual(run.call_count, 2)
            sleep.assert_called_once()
            ci.CACHE = ci.ReadCache(root)
            with mock.patch.object(ci.subprocess, "run") as run:
                self.assertEqual(ci.gh("repos/o/r/jobs"), {"jobs": []})
                run.assert_not_called()

    def test_subprocess_timeout_is_retried(self):
        results = [subprocess.TimeoutExpired(["gh", "api"], ci.GH_TIMEOUT),
                   subprocess.CompletedProcess([], 0, b"{}", b"")]
        with mock.patch.object(ci.subprocess, "run", side_effect=results) as run, \
                mock.patch.object(ci.time, "sleep"):
            self.assertEqual(ci.gh("repos/o/r/jobs"), {})
            self.assertEqual(run.call_count, 2)

    def test_transient_retry_is_bounded_and_failures_are_not_cached(self):
        failed = subprocess.CompletedProcess([], 1, b"", b"HTTP 503: Service Unavailable")
        with mock.patch.object(ci.time, "sleep"), mock.patch.object(ci.subprocess, "run", return_value=failed) as run:
            with self.assertRaisesRegex(RuntimeError, "503"):
                ci.gh("repos/o/r/jobs")
            self.assertEqual(run.call_count, ci.GH_ATTEMPTS)
        with mock.patch.object(ci.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, b"{}", b"")) as run:
            self.assertEqual(ci.gh("repos/o/r/jobs"), {})
            run.assert_called_once()

    def test_permanent_errors_are_not_retried(self):
        for status in (401, 403, 404):
            with self.subTest(status=status), mock.patch.object(ci.time, "sleep") as sleep:
                failed = subprocess.CompletedProcess([], 1, b"", f"HTTP {status}".encode())
                with mock.patch.object(ci.subprocess, "run", return_value=failed) as run:
                    with self.assertRaises(RuntimeError):
                        ci.gh(f"repos/o/r/{status}")
                    run.assert_called_once()
                    sleep.assert_not_called()

    def test_invalid_json_is_not_cached(self):
        results = [subprocess.CompletedProcess([], 0, b"not JSON", b""),
                   subprocess.CompletedProcess([], 0, b"{}", b"")]
        with mock.patch.object(ci.subprocess, "run", side_effect=results) as run:
            with self.assertRaisesRegex(RuntimeError, "JSON"):
                ci.gh("repos/o/r/jobs")
            self.assertEqual(ci.gh("repos/o/r/jobs"), {})
            self.assertEqual(run.call_count, 2)

    def test_skipped_workflow_keeps_commit_context_without_reading_jobs(self):
        skipped = {"id": 1, "head_sha": "abc", "head_branch": "main", "path": ".github/workflows/deploy.yml",
                   "name": "Deploy", "status": "completed", "conclusion": "skipped",
                   "created_at": "2026-10-14T08:59:00Z", "head_commit": {"message": "Change"}}
        green = skipped | {"id": 2, "name": "CI", "path": ".github/workflows/ci.yml", "conclusion": "success",
                           "created_at": "2026-10-14T09:00:00Z"}
        job = {"id": 3, "name": "tests", "started_at": "2026-10-14T09:00:00Z",
               "completed_at": "2026-10-14T09:05:00Z", "conclusion": "success"}

        def read(path, raw=False, *flags):
            if path == "repos/o/r":
                return {"default_branch": "main"}
            if "/runs/1/jobs" in path:
                self.fail("a skipped workflow must not fetch jobs")
            if "/jobs" in path:
                return {"jobs": [job]}
            return {"workflow_runs": [skipped, green]}

        with mock.patch.object(ci, "gh", side_effect=read):
            day = ci.dt.date(2026, 10, 14)
            data = ci.collect("o/r", day, day, required=["CI"])
        commit = data["commits"][0]
        self.assertEqual(commit["created"], skipped["created_at"])
        self.assertEqual(commit["workflows"], {"Deploy": "skipped", "CI": "success"})
        self.assertEqual((commit["wall_min"], commit["wait_min"], commit["runs"]), (5.0, 1.0, ["success"]))
        self.assertEqual((data["days"][0]["commits"], data["days"][0]["failure_pct"]), (1, 0.0))

    def test_logs_and_test_count_share_completed_job_logs_on_disk(self):
        day = "2026-10-14"
        jobs = [{"id": 1, "workflow": "CI", "name": "Batch 1"},
                {"id": 2, "workflow": "CI", "name": "Batch 2"}]
        data = {"repo": "o/r", "days": [{"day": day}],
                "commits": [{"day": day, "ok": True, "sha": "abc123", "jobs": jobs}]}
        with tempfile.TemporaryDirectory() as root, mock.patch.object(ci, "gh", return_value=b"Ran 3 tests in 1s") as gh:
            ci.CACHE = ci.ReadCache(Path(root) / "cache")
            ci.save_logs(data, Path(root) / "logs")
            self.assertEqual(gh.call_count, 2)
            ci.CACHE = ci.ReadCache(Path(root) / "cache")
            ci.add_tests(data, [r"Ran (\d+) tests"])
            self.assertEqual(data["days"][0]["tests"], 6)
            self.assertEqual(gh.call_count, 2, "test counting must reuse both downloaded logs")
            ci.job_log("o/r", 3)
            ci.job_log("other/repo", 1)
            self.assertEqual(gh.call_count, 4, "cache entries belong to a repository and job id")

    def test_cli_logs_and_tests_reuse_the_same_cache(self):
        day = "2026-10-14"
        data = {"repo": "o/r", "days": [{"day": day}], "commits": [{"day": day, "ok": True,
                "sha": "abc123", "jobs": [{"id": 1, "workflow": "CI", "name": "Tests"}]}]}
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            path = root / "data.json"
            path.write_text(json.dumps(data))
            fake_gh = root / "gh"
            fake_gh.write_text(f"#!{sys.executable}\nfrom pathlib import Path\n"
                               "p = Path(__file__).with_name('requests')\n"
                               "with p.open('a') as f: f.write('request\\n')\n"
                               "print('Ran 3 tests in 1s')\n")
            fake_gh.chmod(0o755)
            env = os.environ | {"PATH": str(root) + os.pathsep + os.environ["PATH"]}
            base = [sys.executable, ci.__file__]
            for args in (["logs", str(path), "--out", str(root / "logs")],
                         ["tests", str(path), "--pattern", r"Ran (\d+) tests"],
                         ["logs", str(path), "--out", str(root / "logs")]):
                subprocess.run([*base, *args, "--cache", str(root / "cache")], env=env,
                               capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(path.read_text())["days"][0]["tests"], 3)
            self.assertEqual((root / "requests").read_text(), "request\n")


class CounterTests(unittest.TestCase):
    def test_failed_probe_is_not_a_working_counter(self):
        failed = subprocess.CompletedProcess([], 1, "", "untrusted configuration")
        with mock.patch.object(ci.shutil, "which", return_value="/tool/scc"), \
                mock.patch.object(ci.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, "untrusted configuration"):
                ci.line_counter()

    def test_failed_or_invalid_counter_output_cannot_become_zero_lines(self):
        for tool in ("scc", "cloc"):
            counter = ci.LineCounter(tool, f"/tool/{tool}", f"{tool} 1.0")
            for result in (subprocess.CompletedProcess([], 1, "", "counter failed"),
                           subprocess.CompletedProcess([], 0, "", ""),
                           subprocess.CompletedProcess([], 0, "not JSON", ""),
                           subprocess.CompletedProcess([], 0, '[{"Files": [{}]}]', "")):
                with self.subTest(tool=tool, result=result), mock.patch.object(ci.subprocess, "run", return_value=result):
                    with self.assertRaises(RuntimeError):
                        ci.file_lines(counter, "/unused", ["src/app.py"])

    def test_selected_executable_survives_a_path_change(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            good, bad = root / "good", root / "bad"
            good.mkdir()
            bad.mkdir()
            (good / "scc").write_text(
                "#!/usr/bin/env python3\nimport sys\n"
                "print('scc 1.0' if '--version' in sys.argv else "
                "'[{' + '\"Name\":\"Python\",\"Files\":[{\"Location\":\"src/app.py\",\"Code\":1}]' + '}]')\n")
            (bad / "scc").write_text("#!/bin/sh\nexit 1\n")
            (good / "scc").chmod(0o755)
            (bad / "scc").chmod(0o755)
            original_path = os.environ["PATH"]
            with mock.patch.dict(os.environ, PATH=str(good) + os.pathsep + original_path):
                counter = ci.line_counter()
            with mock.patch.dict(os.environ, PATH=str(bad) + os.pathsep + original_path):
                self.assertEqual(ci.file_lines(counter, root, ["src/app.py"]), [("src/app.py", "Python", 1)])

    def test_measurement_error_leaves_the_input_file_unchanged(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / "app.py").write_text("print('hello')\n")
            subprocess.run(["git", "-C", str(root), "add", "app.py"], check=True)
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                            "-c", "commit.gpgsign=false",
                            "commit", "-qm", "Initial"], check=True)
            sha = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            day = "2026-10-14"
            data = {"days": [{"day": day}], "commits": [{"day": day, "ok": True, "sha": sha}]}
            path = root / "data.json"
            original = json.dumps(data)
            path.write_text(original)
            fake = root / "scc"
            fake.write_text("#!/bin/sh\necho 'counter failed' >&2\nexit 1\n")
            fake.chmod(0o755)
            with mock.patch.object(sys, "argv", ["ci.py", "measure", str(path), "--checkout", str(root)]), \
                    mock.patch.object(ci, "line_counter", return_value=ci.LineCounter("scc", str(fake), "scc 1.0")), \
                    mock.patch.object(ci, "mise_tasks", return_value=set()):
                with self.assertRaisesRegex(SystemExit, "counter failed"):
                    ci.main()
            self.assertEqual(path.read_text(), original)
            worktrees = subprocess.check_output(["git", "-C", str(root), "worktree", "list", "--porcelain"], text=True)
            self.assertEqual(worktrees.count("worktree "), 1, "the failed measurement removes its temporary worktree")


if __name__ == "__main__":
    unittest.main()
