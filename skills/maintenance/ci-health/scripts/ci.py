#!/usr/bin/env python3
"""Facts and the dataset records for the ci-health skill. Reads GitHub Actions only; standard library and `gh`.

    ci.py collect --repo OWNER/NAME [--day D | --since D [--until D]] [--workflow W] [--start D] > data.json
    ci.py shifts data.json [--limit 5]                 # candidate incidents: steps in wall time, and hangs
    ci.py logs data.json --out DIR [--day DAY]         # a day's job logs, cleaned, to find the test summary line
    ci.py tests data.json --pattern REGEX...           # each day's test count from that line, added in place
    ci.py measure data.json --checkout PATH [--path SPEC]... [--every-day]  # optional: test ratio and coverage, added in place
    ci.py summary data.json                            # the days as a Markdown table, for a reply
    ci.py signals data.json [--days 7] > signals.json  # what the last days show, to choose the top actions
    ci.py records data.json [incidents.json] [--actions actions.json] [--doc UUID] > update.json  # update_data batch
    ci.py create data.json [--incidents F] [--actions F] [--tag ID]... > create.json  # create_doc arguments
    ci.py charts data.json > charts.json               # the chart blocks, to compare with an existing document's
    ci.py changelog incidents.json > changelog.json    # the document's Incidents list, latest five
    ci.py cards data.json actions.json [--doc UUID]  # the Actions section's cards
    ci.py ub TOOL [ARGS] | --calls calls.json [--checkout PATH]  # Uberblick tools through one `ub mcp serve`

Days are UTC calendar days; the default is yesterday. A commit counts on the day its first push run was
created. Wall time is the time from the first job starting to the last job finishing, over every workflow the
push to the default branch triggered: what someone waits for once runners pick the work up. See
references/data.md.
"""

import argparse
import datetime as dt
import io
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from urllib.parse import quote

SCHEMA = "ci-health/1"
WINDOW = 7  # rolling median over this many days, the headline
LOOKBACK = 21  # days of commits read before the first day: the rolling median and step detection need them
LOG = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def gh(path, raw=False, *flags):
    done = subprocess.run(["gh", "api", *flags, path], capture_output=True)
    if done.returncode:
        raise RuntimeError(f"gh api {path}: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout if raw else json.loads(done.stdout)


def pages(path, key, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    page = 1
    while True:
        batch = gh(f"{path}?{query}&per_page=100&page={page}")[key]
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def when(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


def minutes(start, end):
    return round((when(end) - when(start)).total_seconds() / 60, 2)


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 2) if values else None


def p95(values):
    """The 95th percentile by nearest rank: a value that was measured. With under 20 values it is the slowest."""
    values = sorted(v for v in values if v is not None)
    return values[math.ceil(0.95 * len(values)) - 1] if values else None


def spread(values):
    """Half the interquartile range: the ± around the median that holds the middle half of the values."""
    values = [v for v in values if v is not None]
    if len(values) < 2:
        return None
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return round((q3 - q1) / 2, 2)


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def field(workflow, job):
    """Stable record field for one job's minutes: workflow and job name, so two workflows never collide."""
    return f"{slug(f'{workflow} {job}')}_min"


def clean(text):
    """A job log without GitHub's timestamps and terminal colors."""
    return "\n".join(ANSI.sub("", LOG.sub("", line)).rstrip() for line in text.splitlines())


def tests_in(text, patterns):
    """Tests a job reports, by the agent's patterns for this repository's runners: every integer a pattern's groups
    capture, on every line it matches, summed; a group named `skipped` is subtracted instead, for runners whose total
    includes skipped tests. None when no pattern matched."""
    total, found = 0, False
    for line in clean(text).splitlines():
        for pattern in patterns:
            if m := pattern.search(line):
                skipped = m.groupdict().get("skipped")
                total += sum(int(g) for g in m.groups() if g and g.isdigit()) - 2 * int(skipped or 0)
                found = True
    return max(total, 0) if found else None


def job_log(repo, job_id):
    path = f"repos/{repo}/actions/jobs/{job_id}/logs"
    try:
        data = gh(path, True)
    except RuntimeError as e:
        # Newer gh refuses output with terminal escapes, which test runners print; older gh lacks the flag.
        if "--allow-escape-sequences" not in str(e):
            raise
        data = gh(path, True, "--allow-escape-sequences")
    if data[:2] == b"PK":  # some hosts hand back the zipped log
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            return "\n".join(z.read(n).decode(errors="replace") for n in z.namelist())
    return data.decode(errors="replace")


def window(args):
    yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    if args.day:
        first = last = dt.date.fromisoformat(args.day)
    else:
        first = dt.date.fromisoformat(args.since) if args.since else yesterday
        last = dt.date.fromisoformat(args.until) if args.until else yesterday
    if first > last:
        sys.exit(f"--since {first} is after --until {last}")
    return first, last


def collect(repo, first, last, required=(), floor=None):
    """Every push run on the default branch from LOOKBACK days before `first` to the end of `last`, grouped by
    commit, and one record per day from `first` to `last`. With `required` workflows, a commit counts only when it
    ran one of them; the other workflows on that commit still count toward its wall time. Runs before `floor` are
    ignored, so a reworked or re-enabled CI does not mix with what came before."""
    info = gh(f"repos/{repo}")
    branch = info["default_branch"]
    start = max(first - dt.timedelta(days=LOOKBACK), floor or dt.date.min)
    runs = [r for r in pages(f"repos/{repo}/actions/runs", "workflow_runs", branch=branch, event="push",
                             created=f"{start.isoformat()}..{last.isoformat()}")
            if r["head_branch"] == branch and not r["path"].startswith("dynamic/")]
    commits, pending = {}, set()
    for run in sorted(runs, key=lambda r: r["created_at"]):
        if run["status"] != "completed":
            pending.add(run["head_sha"])
            continue
        jobs = [j for j in pages(f"repos/{repo}/actions/runs/{run['id']}/jobs", "jobs", filter="latest")
                if j.get("started_at") and j.get("completed_at") and j["conclusion"] not in ("skipped", None)]
        c = commits.setdefault(run["head_sha"], {
            "sha": run["head_sha"], "created": run["created_at"],
            "title": (run.get("head_commit") or {}).get("message", "").split("\n")[0][:200],
            "workflows": {}, "jobs": []})
        c["workflows"][run["name"]] = run["conclusion"]
        c["jobs"] += [{"id": j["id"], "workflow": run["name"], "name": j["name"], "started": j["started_at"],
                       "completed": j["completed_at"], "conclusion": j["conclusion"],
                       "min": minutes(j["started_at"], j["completed_at"])} for j in jobs]
    rows = []
    for sha, c in commits.items():
        if sha in pending or not c["jobs"] or (required and not set(required) & set(c["workflows"])):
            continue  # a commit counts once all its runs finished, and only when it ran CI
        c["day"] = c["created"][:10]
        c["ok"] = all(v in ("success", "skipped", "neutral") for v in c["workflows"].values())
        c["wall_min"] = minutes(min(j["started"] for j in c["jobs"]), max(j["completed"] for j in c["jobs"]))
        c["wait_min"] = max(0, minutes(c["created"], min(j["started"] for j in c["jobs"])))
        c["late_start_min"] = late_start(c["jobs"])
        c["execution_min"] = round(sum(j["min"] for j in c["jobs"]), 2)
        rows.append(c)
    rows.sort(key=lambda c: c["created"])
    names = {}
    days = []
    d = first
    while d <= last:
        key = d.isoformat()
        since = (d - dt.timedelta(days=WINDOW - 1)).isoformat()
        today = [c for c in rows if c["day"] == key]
        green = [c for c in today if c["ok"]]
        recent = [c for c in rows if since <= c["day"] <= key and c["ok"]]
        record = {"day": key, "repo": repo, "workflows": ", ".join(required) or None,
                  "start": floor.isoformat() if floor else None, "commits": len(today), "failed": len(today) - len(green),
                  "wall_min": median(c["wall_min"] for c in green),
                  "wall_min_7d": median(c["wall_min"] for c in recent),
                  "wall_spread_7d": spread(c["wall_min"] for c in recent),
                  "wall_p95_7d": p95(c["wall_min"] for c in recent),
                  "execution_min": median(c["execution_min"] for c in green),
                  "wait_min": median(c["wait_min"] for c in green),
                  "late_start_min": median(c.get("late_start_min") for c in green)}
        per_job = {}
        for c in green:
            for j in c["jobs"]:
                key_ = field(j["workflow"], j["name"])
                names[key_] = f"{j['workflow']} / {j['name']}"
                per_job.setdefault(key_, []).append(j["min"])
        record |= {k: median(v) for k, v in sorted(per_job.items())}
        days.append({k: v for k, v in record.items() if v is not None})
        d += dt.timedelta(days=1)
    for c in rows:
        for j in c["jobs"]:
            names.setdefault(field(j["workflow"], j["name"]), f"{j['workflow']} / {j['name']}")
    return {"schema": SCHEMA, "repo": repo, "branch": branch, "first": first.isoformat(), "last": last.isoformat(),
            "collected": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workflows": list(required), "jobs": dict(sorted(names.items())), "days": days, "commits": rows}


def late_start(jobs, short=0.5):
    """How long after the first job of a push the last real job started: waiting for a runner (macOS, a busy or
    capped pool) or for jobs it `needs`. Jobs under `short` minutes, such as a summary job, are left out. The jobs
    API cannot tell the two waits apart, and its `created_at` is stamped too late to show either."""
    first = min(j["started"] for j in jobs)
    return round(max((minutes(first, j["started"]) for j in jobs if j["min"] >= short), default=0), 2)


def count_tests(repo, commit, patterns):
    """Tests on a green commit, summed over its jobs; a matrix runs one suite several times, so jobs that differ
    only in their parenthesised matrix values count once, at their largest."""
    groups = {}
    for j in commit["jobs"]:
        try:
            n = tests_in(job_log(repo, j["id"]), patterns)
        except RuntimeError as e:
            print(f"tests: no log for {j['workflow']} / {j['name']}: {e}", file=sys.stderr)
            continue
        if n is not None:
            base = (j["workflow"], re.sub(r"\s*\(.*\)$", "", j["name"]))
            groups[base] = max(groups.get(base, 0), n)
    return sum(groups.values()) if groups else None


def last_green(data, day):
    green = [c for c in data["commits"] if c["day"] == day and c["ok"]]
    return green[-1] if green else None


def save_logs(data, out, day=None):
    """The job logs of a day's last green commit, cleaned, one file per job, for the agent to read."""
    day = day or data["days"][-1]["day"]
    commit = last_green(data, day)
    if not commit:
        sys.exit(f"logs: no green commit on {day}")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for j in commit["jobs"]:
        path = out / f"{slug(j['workflow'] + ' ' + j['name'])}.log"
        path.write_text(clean(job_log(data["repo"], j["id"])))
        files.append({"job": f"{j['workflow']} / {j['name']}", "file": str(path), "lines": len(path.read_text().splitlines())})
    return {"day": day, "sha": commit["sha"][:12], "logs": files}


def add_tests(data, patterns):
    """Set `tests` on every day with a green commit, from that commit's logs, and record the patterns used."""
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p))
        except re.error as e:
            sys.exit(f"tests: pattern {p!r}: {e}")
        if not compiled[-1].groups:
            sys.exit(f"tests: pattern {p!r} captures nothing; put the count in a group, like (\\d+) passed")
    for d in data["days"]:
        commit = last_green(data, d["day"])
        if commit and (n := count_tests(data["repo"], commit, compiled)) is not None:
            d["tests"] = n
            d["tests_pattern"] = " || ".join(patterns)
    return data


# Line counters that tell comments from code in every language they know, in the order tried.
COUNTERS = ("scc", "cloc")
# Commands that install a counter, by the first package manager on the PATH, as the scc and cloc READMEs give them:
# scc where the manager packages it, cloc from the Linux distributions, which package cloc and not scc.
INSTALL = (("brew", "brew install scc"), ("port", "sudo port install scc"), ("scoop", "scoop install scc"),
           ("winget", "winget install --id benboyter.scc --source winget"), ("choco", "choco install scc"),
           ("pkg", "pkg install scc"), ("apt-get", "sudo apt install cloc"), ("dnf", "sudo dnf install cloc"),
           ("pacman", "sudo pacman -S cloc"), ("apk", "sudo apk add cloc"),
           ("go", "go install github.com/boyter/scc/v4@latest"))
# Prose and data, which the counters report as languages too, by the names scc and cloc give them, lowercased: the
# ratio compares the code people write and test, style and markup included.
NOT_CODE = {"asciidoc", "csv", "diff", "gitignore", "ini", "json", "json5", "jsonl", "license", "markdown",
            "plain text", "properties", "restructuredtext", "svg", "tex", "text", "toml", "xml", "yaml"}
# Test files by path, across ecosystems: test directories, and test_*, *_test, *.test, *.spec, *Test(s), *Spec.
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs|e2e|testing)/|(^|/)test_[^/]*$|[^/]*(_test|_tests|_spec|"
                       r"\.test|\.spec|Tests?|Spec)\.[^/.]+$")


def mise_tasks(root):
    """Task names the checkout's mise config defines; empty when mise is missing or has none."""
    try:
        done = subprocess.run(["mise", "tasks", "ls", "--json"], cwd=root, capture_output=True, text=True,
                              env=mise_env(root))
    except OSError:  # no mise on this host: the built-in line count still works
        return set()
    if done.returncode:
        return set()
    try:
        return {t["name"] for t in json.loads(done.stdout)}
    except (ValueError, KeyError, TypeError):
        return set()


def mise_env(root):
    # A throwaway worktree is a new path to mise; trust its config for this run only.
    return os.environ | {"MISE_TRUSTED_CONFIG_PATHS": str(root), "MISE_YES": "1"}


def mise_json(root, task, timeout):
    """Run `mise run TASK` and read the last line of its output that is a JSON object."""
    try:
        done = subprocess.run(["mise", "run", task], cwd=root, capture_output=True, text=True, timeout=timeout,
                              env=mise_env(root))
    except subprocess.TimeoutExpired:
        print(f"measure: mise run {task} took longer than {timeout}s", file=sys.stderr)
        return {}
    for line in reversed(done.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                break
    print(f"measure: mise run {task} printed no JSON object (exit {done.returncode})", file=sys.stderr)
    return {}


def line_counter():
    """The first line counter on the PATH, as `name version`, or None."""
    for tool in COUNTERS:
        if shutil.which(tool):
            version = re.search(r"\d+(?:\.\d+)+", subprocess.run([tool, "--version"], capture_output=True,
                                                                  text=True).stdout)
            return f"{tool} {version.group(0)}" if version else tool
    return None


def install_hint():
    """How to install a line counter on this host, by the first package manager it has."""
    return next((f"run `{command}`" for manager, command in INSTALL if shutil.which(manager)),
                "download scc from https://github.com/boyter/scc/releases")


def file_lines(counter, root, files):
    """(path, language, lines of code) for each of `files` the counter knows; blank and comment lines are not code."""
    if counter.startswith("scc"):
        rows = []
        for i in range(0, len(files), 1000):  # in batches, under the argument length limit
            out = subprocess.run(["scc", "--by-file", "--format", "json", *files[i:i + 1000]], cwd=root,
                                 capture_output=True, text=True).stdout
            rows += [(f["Location"], lang["Name"], f["Code"]) for lang in json.loads(out or "[]") for f in lang["Files"]]
        return rows
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as listing:
        listing.write("\n".join(files))
        listing.flush()
        out = subprocess.run(["cloc", "--by-file", "--json", "--quiet", f"--list-file={listing.name}"], cwd=root,
                             capture_output=True, text=True).stdout
    return [(name, f["language"], f["code"]) for name, f in json.loads(out or "{}").items()
            if name not in ("header", "SUM")]


def count_lines(root, counter, paths=()):
    """Code and test lines over the files git tracks under `paths`, git pathspecs (everything by default), so
    untracked trees such as dependencies, build output or nested worktrees never count. Prose and data are left out,
    and a file is a test when its path matches TEST_PATH."""
    listed = subprocess.run(["git", "ls-files", "-z", "--", *paths], cwd=root, capture_output=True, text=True,
                            check=True).stdout
    code = test = 0
    for name, language, n in file_lines(counter, root, [f for f in listed.split("\0") if f]):
        if language.lower() in NOT_CODE:
            continue
        if TEST_PATH.search(name.removeprefix("./")):
            test += n
        else:
            code += n
    return {"code_lines": code, "test_lines": test}


def measure(data, checkout, timeout=1800, every_day=False, paths=()):
    """Coverage and code against test lines at a day's last green commit, from a detached worktree of `checkout`.
    `mise run codecov` and `mise run loc` are used when the checkout defines them; lines fall back to count_lines
    over `paths`, with the first line counter installed. Adds the figures to the last day, or with `every_day` the
    lines to every day and coverage to the last, since coverage runs the suite."""
    days = data["days"] if every_day else data["days"][-1:]
    counter, told = line_counter(), False
    git = lambda *a, **k: subprocess.run(["git", "-C", checkout, *a], capture_output=True, text=True, **k)
    for day in days:
        commit = last_green(data, day["day"])
        if not commit:
            print(f"measure: no green commit on {day['day']}", file=sys.stderr)
            continue
        sha = commit["sha"]
        if git("cat-file", "-e", f"{sha}^{{commit}}").returncode:
            git("fetch", "-q", "origin", sha)
        root = Path(tempfile.mkdtemp(prefix="ci-health-")) / "tree"
        added = git("worktree", "add", "-q", "--detach", str(root), sha)
        if added.returncode:
            sys.exit(f"measure: cannot check out {sha[:12]} in {checkout}: {added.stderr.strip()}")
        try:
            tasks = mise_tasks(root)
            found = {}
            if "codecov" in tasks and day is data["days"][-1]:
                found |= {k: v for k, v in mise_json(root, "codecov", timeout).items() if k == "coverage_pct"}
            if "loc" in tasks:
                found |= {k: v for k, v in mise_json(root, "loc", timeout).items() if k in ("code_lines", "test_lines")}
            if "code_lines" in found and "test_lines" in found:
                found["loc_tool"] = "mise run loc"
            elif counter:
                found |= count_lines(root, counter, paths) | {"loc_tool": counter, "loc_paths": " || ".join(paths)}
            elif not told:
                told = True
                print(f"measure: no line counter: neither scc nor cloc is installed and the checkout defines no loc "
                      f"task, so lines and the test ratio are left out; to count them, {install_hint()}",
                      file=sys.stderr)
        finally:
            git("worktree", "remove", "--force", str(root))
        if found.get("code_lines"):
            found["test_ratio"] = round(found["test_lines"] / found["code_lines"], 2)
        day |= {k: v for k, v in found.items()
                if isinstance(v, (int, float)) or (k in ("loc_tool", "loc_paths") and v)}
        day["measured_sha"] = sha[:12]
    return data


def number(title):
    m = re.search(r"\(#(\d+)\)\s*$", title) or re.search(r"Merge pull request #(\d+)", title)
    return int(m.group(1)) if m else None


def shifts(data, limit=5, span=8):
    """Steps in wall time over green commits: at each commit, the median of the `span` green commits before against
    the `span` from it on. A step must move at least a minute and 15 percent; nearby steps keep only the largest.
    Each carries the commits that can explain it, so the agent can name the change, and the jobs that moved. The
    lookback before the first collected day informs the medians; only steps on collected days are returned."""
    green = [c for c in data["commits"] if c["ok"]]
    found = []
    for i in range(span, len(green) - span + 1):
        before, after = green[i - span:i], green[i:i + span]
        b, a = median(c["wall_min"] for c in before), median(c["wall_min"] for c in after)
        delta = a - b
        if abs(delta) >= max(1.0, 0.15 * b):
            # Medians tie over the commits around a clean step; the means peak where it landed.
            sharp = abs(statistics.fmean(c["wall_min"] for c in after) - statistics.fmean(c["wall_min"] for c in before))
            found.append((abs(delta), sharp, i, b, a))
    chosen = []
    for size, _, i, b, a in sorted(found, key=lambda x: (-x[0], -x[1])):
        if all(abs(i - j) >= span for _, j, _, _ in chosen):
            chosen.append((size, i, b, a))
    out = []
    for size, i, b, a in sorted(chosen, key=lambda x: green[x[1]]["created"], reverse=True)[:limit]:
        jobs = {}
        for side, cs in (("before", green[i - span:i]), ("after", green[i:i + span])):
            for c in cs:
                for j in c["jobs"]:
                    jobs.setdefault(f"{j['workflow']} / {j['name']}", {}).setdefault(side, []).append(j["min"])
        moved = {k: {"before": median(v.get("before", [])), "after": median(v.get("after", []))} for k, v in jobs.items()}
        out.append({"repo": data["repo"], "day": green[i]["day"], "time": green[i]["created"],
                    "direction": "slower" if a > b else "faster",
                    "before_min": b, "after_min": a, "change_min": round(a - b, 2),
                    "change_pct": round(100 * (a - b) / b) if b else None, "jobs": moved,
                    "suspects": suspects(data["commits"], green[i - 2], green[i])})
    first, last = data.get("first", ""), data.get("last", "9999")
    return [s for s in out if first <= s["day"] <= last]


def suspects(commits, previous, step, cap=40):
    """The commits that can explain a step at `step`: every one since `previous`, two green commits back, since the
    detector places a step within a commit or two (failed ones included: a change can land on a red run), the step
    itself and the one after."""
    lo, hi = commits.index(previous) + 1, commits.index(step) + 2
    pick = commits[max(lo, hi - cap):hi]
    return [{"sha": c["sha"][:12], "day": c["day"], "title": c["title"], "pr": number(c["title"]), "ok": c["ok"],
             "wall_min": c["wall_min"]} for c in pick]


def hangs(data, floor=60):
    """Stretches of commits whose CI failed after running `floor` minutes or more and over three times the green
    median, such as tests hanging until the job timeout. A failed commit is left out of wall time, so this is the
    only place a hang shows. Each stretch names its first and last commit and the first one after it."""
    commits = data["commits"]
    typical = median(c["wall_min"] for c in commits if c["ok"]) or 0
    out, stretch = [], []
    for c in commits + [None]:
        hung = c is not None and not c["ok"] and c["wall_min"] >= max(floor, 3 * typical)
        if hung:
            stretch.append(c)
        elif stretch:
            pick = lambda x: {"sha": x["sha"][:12], "day": x["day"], "time": x["created"], "title": x["title"],
                              "pr": number(x["title"]),
                              "wall_min": x["wall_min"]} if x else None
            out.append({"repo": data["repo"], "kind": "hang", "day": stretch[0]["day"], "commits": len(stretch),
                        "hung_min": median(x["wall_min"] for x in stretch), "green_min": typical,
                        "first": pick(stretch[0]), "last": pick(stretch[-1]), "after": pick(c)})
            stretch = []
    first, last = data.get("first", ""), data.get("last", "9999")
    return [h for h in out if h["day"] <= last and ((h["after"] or h["last"])["day"] >= first)]


def signals(data, days=WINDOW):
    """What the pushes of the last `days` days show, for choosing actions: how often main is pushed, the job that
    finishes last and how far ahead of the next one, which jobs fail, runner waits and hangs. Each comes with a rough
    count of the minutes of waiting a day it accounts for, one scale to rank actions on."""
    last = data["last"]
    first = (dt.date.fromisoformat(last) - dt.timedelta(days=days - 1)).isoformat()
    recent = [c for c in data["commits"] if first <= c["day"] <= last]
    out = {"repo": data["repo"], "from": first, "to": last, "pushes": len(recent)}
    if not recent:
        return out
    span = (dt.date.fromisoformat(last) - dt.date.fromisoformat(min(c["day"] for c in recent))).days + 1
    green, failed = [c for c in recent if c["ok"]], [c for c in recent if not c["ok"]]
    name = lambda j: f"{j['workflow']} / {j['name']}"
    jobs = {}
    for c in recent:
        for j in c["jobs"]:
            job = jobs.setdefault(name(j), {"min": [], "ahead": [], "failed": 0})
            if c["ok"]:
                job["min"].append(j["min"])
            elif j.get("conclusion") in ("failure", "timed_out"):
                job["failed"] += 1
        # A summary job under half a minute often ends last; the job before it is what the push waits for.
        ends = sorted(((when(j["completed"]), name(j)) for j in c["jobs"] if j.get("completed") and j["min"] >= 0.5),
                      reverse=True)
        if c["ok"] and ends:
            jobs[ends[0][1]]["ahead"].append(
                (ends[0][0] - ends[1][0]).total_seconds() / 60 if len(ends) > 1 else c["wall_min"])
    rows = [{"job": job, "median_min": median(j["min"]),
             "ends_last": round(len(j["ahead"]) / len(green), 2) if green else 0,
             "ahead_min": median(j["ahead"]), "failed": j["failed"]} for job, j in jobs.items()]
    rows.sort(key=lambda r: (-r["ends_last"], -(r["median_min"] or 0)))
    wall = median(c["wall_min"] for c in green) or 0
    wait = (median(c["wait_min"] for c in green) or 0) + (median(c["late_start_min"] for c in green) or 0)
    stuck = [h for h in hangs(data) if h["day"] >= first]
    lead = rows[0] if rows and rows[0]["ahead_min"] else None
    per_day = lambda minutes: round(minutes / span, 1)
    return out | {
        "days": span, "pushes_per_day": round(len(recent) / span, 1), "failed": len(failed), "wall_min": wall,
        "wall_p95_min": p95(c["wall_min"] for c in green), "wait_min": round(wait, 2), "jobs": rows, "hangs": stuck,
        # Rough minutes of waiting a day: the last job's lead on every push it ends, a full run more for each failed
        # push, the runner waits of every push, and the time hung runs held before failing.
        "waiting_min_per_day": {
            "slowest_job": per_day(lead["ahead_min"] * len(jobs[lead["job"]]["ahead"])) if lead else 0,
            "failed_pushes": per_day(len(failed) * wall),
            "runner_waits": per_day(wait * len(recent)),
            "hangs": per_day(sum(h["hung_min"] * h["commits"] for h in stuck))}}


def summary(data):
    cols = [("commits", "Commits"), ("failed", "Failed"), ("wall_min_7d", "Wall (7d)"), ("wall_p95_7d", "P95 (7d)"),
            ("wall_min", "Wall"), ("late_start_min", "Late start"), ("tests", "Tests"), ("test_ratio", "Test ratio"),
            ("coverage_pct", "Coverage %")]
    cols = [(k, t) for k, t in cols if any(k in d for d in data["days"])]
    fmt = lambda v: "" if v is None else f"{v:.1f}" if isinstance(v, float) else str(v)
    cell = lambda d, k: fmt(d.get(k)) + (f" ± {fmt(float(d['wall_spread_7d']))}"
                                         if k == "wall_min_7d" and "wall_spread_7d" in d else "")
    lines = ["| Day | " + " | ".join(t for _, t in cols) + " |", "|" + " --- |" * (len(cols) + 1)]
    lines += ["| " + " | ".join([d["day"], *[cell(d, k) for k, _ in cols]]) + " |" for d in data["days"]]
    return (f"{data['repo']} ({data['branch']}), minutes, medians of green commits; per-job medians are in "
            "data.json:\n\n" + "\n".join(lines))


NUM = {"type": ["number", "null"], "minimum": 0}
COUNT = {"type": "integer", "minimum": 0}
TEXT = {"type": "string"}
DAY = {"type": "string", "minLength": 10, "maxLength": 10}
INCIDENTS = {"version": 1, "schema": {"type": "object", "required": ["day", "repo", "direction", "title", "why"],
             "properties": {"day": DAY, "repo": TEXT, "direction": {"type": "string", "enum": ["slower", "faster"]},
                            "before_min": NUM, "after_min": NUM, "change_min": {"type": ["number", "null"]},
                            "change_pct": {"type": ["number", "null"]}, "title": TEXT, "why": TEXT, "ref": TEXT,
                            "url": TEXT, "jobs": TEXT, "time": TEXT}}}

ACTIONS = {"version": 1, "schema": {"type": "object", "required": ["repo", "rank", "area", "title", "why", "since",
                                                                  "updated"],
           "properties": {"repo": TEXT, "rank": {"type": "integer", "minimum": 1, "maximum": 3}, "area": TEXT,
                          "title": TEXT, "why": TEXT, "check": TEXT, "impact_min_per_day": NUM, "since": DAY,
                          "updated": DAY}}}
TOP = 3  # actions on the document at a time


def schema(data):
    fields = {"day": DAY, "repo": TEXT, "workflows": TEXT, "start": DAY, "measured_sha": TEXT, "tests_pattern": TEXT,
              "loc_tool": TEXT, "loc_paths": TEXT,
              **dict.fromkeys(["commits", "failed", "tests", "code_lines", "test_lines"], COUNT),
              "coverage_pct": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
              **dict.fromkeys(["wall_min", "wall_min_7d", "wall_spread_7d", "wall_p95_7d", "execution_min", "late_start_min", "wait_min", "test_ratio", *data["jobs"]], NUM)}
    return {"version": 1, "schema": {"type": "object", "required": ["day", "repo", "commits"], "properties": fields}}


def link(ref):
    m = re.fullmatch(r"([\w.-]+/[\w.-]+)#(\d+)", ref or "")
    return f"https://github.com/{m.group(1)}/pull/{m.group(2)}" if m else None


def incident_rows(incidents):
    rows = []
    for i in incidents:
        missing = [k for k in ("day", "repo", "direction", "title", "why") if not i.get(k)]
        if missing:
            sys.exit(f"incident {i.get('day')} {i.get('repo')}: missing {', '.join(missing)}")
        if i["direction"] not in ("slower", "faster"):
            sys.exit(f"incident {i['day']}: direction must be slower or faster")
        value = {k: i[k] for k in ("day", "repo", "direction", "before_min", "after_min", "change_min", "change_pct",
                                   "title", "why", "ref", "url", "time") if i.get(k) is not None}
        if isinstance(i.get("jobs"), str):
            value["jobs"] = i["jobs"]
        if "url" not in value and link(i.get("ref")):
            value["url"] = link(i["ref"])
        # Several changes can land on one day: the change itself keeps their ids apart.
        change = slug(i.get("ref") or i["title"]).replace("_", "-")
        rows.append({"id": f"{i['day']}/{change}", "value": value})
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        sys.exit(f"incidents: the same change twice on one day: {sorted({x for x in ids if ids.count(x) > 1})}")
    return rows


def action_rows(data, actions):
    """The current top actions, ranked in the order given. A kept action keeps its id and `since`, so its age shows;
    a new one starts on the last collected day."""
    if len(actions) > TOP:
        sys.exit(f"actions: at most {TOP}, the ones that would save the most waiting")
    rows = []
    for rank, a in enumerate(actions, 1):
        missing = [k for k in ("area", "title", "why") if not a.get(k)]
        if missing:
            sys.exit(f"action {rank}: missing {', '.join(missing)}")
        if a.get("repo") not in (None, data["repo"]):
            sys.exit(f"actions: every action must be for {data['repo']}, the repository of this document")
        value = {"repo": data["repo"], "rank": rank, "since": a.get("since") or data["last"], "updated": data["last"],
                 **{k: a[k] for k in ("area", "title", "why", "check", "impact_min_per_day") if a.get(k) is not None}}
        rows.append({"id": a.get("id") or slug(a["title"]).replace("_", "-"), "value": value})
    ids = [r["id"] for r in rows]
    if len(ids) != len(set(ids)):
        sys.exit(f"actions: the same id twice: {sorted({x for x in ids if ids.count(x) > 1})}")
    return rows


def records(data, incidents=(), actions=None):
    """One update_data batch: the repository's days, keyed by day so a refresh replaces them, any incidents, and
    with `actions` the current top actions, which replace the ones before."""
    if any(i.get("repo") not in (None, data["repo"]) for i in incidents):
        sys.exit(f"incidents: every incident must be for {data['repo']}, the repository of this document")
    batch = [{"collection": "days", "schema": schema(data),
              "upsert": [{"id": d["day"], "value": d} for d in data["days"]]}]
    if incidents:
        batch.append({"collection": "incidents", "schema": INCIDENTS, "upsert": incident_rows(incidents)})
    if actions is not None:
        batch.append({"collection": "actions", "schema": ACTIONS, "replaceRecords": action_rows(data, actions)})
    return batch


def chart(mapping):
    return {"type": "chart", "text": json.dumps(mapping, indent=1)}


def charts(data):
    """The charts, bound to the document's days: total wall time (the 7-day median and P95), tests, and, once
    measured, the test-to-code ratio and coverage. Per-job times stay in the data, to explain steps, not drawn."""
    x = {"field": "day", "type": "date", "label": "Day"}
    line = lambda title, y: chart({"version": 1, "type": "line", "collection": "days", "title": title, "x": x,
                                   "missing": "connect", "y": y})
    blocks = [line(f"Wall time on {data['branch']}",
                   [{"field": "wall_min_7d", "label": "7-day median", "unit": "min"},
                    {"field": "wall_p95_7d", "label": "7-day P95", "unit": "min"}]),
              line("Tests", [{"field": "tests", "label": "Tests"}])]
    if any("test_ratio" in d for d in data["days"]):
        blocks.append(line("Test to code ratio", [{"field": "test_ratio", "label": "Test lines per code line"}]))
    if any("coverage_pct" in d for d in data["days"]):
        blocks.append(line("Test coverage", [{"field": "coverage_pct", "label": "Coverage", "unit": "%"}]))
    return blocks


def changelog(incidents, limit=5):
    """The latest incidents as list items, newest first: the day, the change linked, its effect and why."""
    rows = incidents.get("records", incidents) if isinstance(incidents, dict) else incidents
    rows = [r.get("value", r) for r in rows]
    blocks = []
    # `time`, when the change's first run started, keeps several incidents on one day in order.
    for i in sorted(rows, key=lambda i: (i["day"], i.get("time", "")), reverse=True)[:limit]:
        arrow = "▲ slower" if i["direction"] == "slower" else "▼ faster"
        short = lambda v: f"{v:.1f}" if v < 10 else f"{v:.0f}"
        effect = arrow + (f", {short(i['before_min'])} → {short(i['after_min'])} min"
                               if i.get("before_min") is not None and i.get("after_min") is not None else "")
        day = dt.date.fromisoformat(i["day"]).strftime("%-d %b %Y")
        url = i.get("url") or link(i.get("ref"))
        blocks.append({"type": "list-item", "inline": [
            {"text": f"{day}: ", "marks": {"bold": True}},
            {"text": i["title"], "marks": {"link": url} if url else {}},
            {"text": f" ({effect}). {i['why']}", "marks": {}}]})
    return blocks or [{"type": "paragraph", "text": "No incident recorded yet."}]


SKILL_URL = "https://skills.uberblick.ai/skills/ci-health"
# A card's link opens a new Claude Code session in the desktop app with the prompt filled in; the prompt names the
# repository, since the link can only select a local folder.
CLAUDE_CODE = "claude://code/new?q="
CHECK = "Check it against the repository: is it sound, what would it change, what are the risks, and is there a simpler way?"


def discuss_link(data, action, doc=None):
    """A link that opens Claude Code with a prompt to discuss the action before changing anything: the repository,
    the recommendation, its evidence, what to check, then a plan. The prompt is filled in, not sent."""
    source = f"the CI Health Report for {data['repo']}" + (f" (Uberblick document {doc})" if doc else "")
    prompt = (f"From {source}, data as of {action.get('updated') or data['last']}:\n\n"
              f"Recommendation: {action['title'].rstrip('.')}.\nEvidence: {action['why']}\n\n"
              f"Let's discuss this before changing anything. {action.get('check') or CHECK} "
              "Then propose a plan and wait for my go-ahead.")
    return CLAUDE_CODE + quote(prompt, safe="")


def cards(data, actions, doc=None):
    """The actions as cards in rank order: the area and since when, the action, why with its numbers, and a link to
    discuss it in Claude Code. Takes the agent's actions or the stored records."""
    rows = actions.get("records", actions) if isinstance(actions, dict) else actions
    stored = [r["value"] for r in rows if "value" in r]
    values = sorted(stored, key=lambda a: a["rank"]) if stored else [r["value"] for r in action_rows(data, rows)]
    one_line = lambda text: " ".join(text.split())
    blocks = []
    for a in values:
        since = dt.date.fromisoformat(a["since"]).strftime("%-d %b %Y")
        blocks.append({"type": "card", "text": f"label: {one_line(a['area'])} · since {since}\n"
                                               f"title: {one_line(a['title'])}\n"
                                               f"footer: [Discuss in Claude Code]({discuss_link(data, a, doc)})\n\n"
                                               f"{a['why']}"})
    return blocks or [{"type": "paragraph", "text": "No action proposed yet."}]


def create_document(data, incidents=(), actions=()):
    """create_doc arguments for a repository's CI health document: intent, how to read it, the charts, the top
    actions, then the incidents."""
    repo = data["repo"]
    blocks = [
        {"type": "paragraph", "text": f"How long a push to {data['branch']} in {repo} waits for CI, and how many tests "
         "it runs. The goal is short wall time: the time from the first job starting to the last one finishing, not "
         "the minutes the jobs add up to, so running checks in parallel is one way to bring it down."},
        {"type": "paragraph", "inline": [
            {"text": "Reading the charts: ", "marks": {"bold": True}},
            {"text": "one point per day, over green commits, in minutes. Wall time is the total over the last 7 days: the "
             "median, and the P95 that shows the slow tail. Lower is better. "
             "Runner queueing before the first job is left out. Data from GitHub Actions, refreshed by the ",
             "marks": {}},
            {"text": "ci-health skill", "marks": {"link": SKILL_URL}},
            {"text": ".", "marks": {}}]},
        *charts(data),
        {"type": "heading", "level": 2, "text": "Actions"},
        {"type": "paragraph", "text": f"The {TOP} changes that would most cut the time pushes wait for a green "
         f"{data['branch']}, from the last days of CI, kept until done or outranked."},
        *cards(data, list(actions)),
        {"type": "heading", "level": 2, "text": "Incidents"},
        {"type": "paragraph", "text": "The latest steps in total wall time, up or down, and the change behind each."},
        *changelog(list(incidents)),
    ]
    return {"title": "CI Health Report",
            "description": f"How long CI takes on {data['branch']} in {repo}: daily GitHub Actions wall time, its "
                           "slow tail, test counts, the incidents that made CI slower or faster, and the top "
                           "actions to cut the wait. Data in days, incidents and actions, refreshed by ci-health.",
            "blocks": blocks}


SETTLE_POLL = 2  # seconds between sync_status checks before the server exits


def ub_calls(calls, checkout, timeout=300, settle=60):
    """Call Uberblick MCP tools through one `ub mcp serve` in `checkout`, for a host that has the `ub` command but not
    the uberblick MCP tools. The server serves the workspace that checkout is bound to. One server for the whole
    list keeps the run to one agent in the workspace's activity. Before it exits it waits up to `settle` seconds
    for the hub to acknowledge any write, so the changes leave this machine. Stops at the first error."""
    try:
        server = subprocess.Popen(["ub", "mcp", "serve"], cwd=checkout, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True)
    except OSError as e:
        sys.exit(f"ub: {e}")
    ids = iter(range(1, 1_000_000))

    def ask(method, params):
        n = next(ids)
        server.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params}) + "\n")
        server.stdin.flush()
        for line in server.stdout:  # one JSON-RPC message per line; skip the server's notifications
            message = json.loads(line) if line.strip().startswith("{") else {}
            if message.get("id") == n:
                if "error" in message:
                    sys.exit(f"ub {params.get('name', method)}: {message['error'].get('message')}")
                return message["result"]
        sys.exit(f"ub mcp serve stopped before answering {method}; run `ub doctor` in {checkout}")

    def call(tool, arguments):
        result = ask("tools/call", {"name": tool, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            sys.exit(f"ub {tool}: {text}")
        return text

    out = []
    try:
        ask("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "ci-health", "title": "CI health", "version": "1.0"}})
        server.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        for c in calls:
            out.append({"tool": c["tool"], "result": call(c["tool"], c.get("arguments", {}))})
        deadline = time.monotonic() + settle
        while calls:
            try:
                status = json.loads(call("sync_status", {}))
            except ValueError:
                break
            if not status.get("unsyncedChanges") and not status.get("inFlightUpdates"):
                break
            if time.monotonic() > deadline:
                print(f"ub: the hub has not acknowledged {status.get('unsyncedChanges')} change(s) after "
                      f"{settle}s; they are saved locally and sync when a server next runs in {checkout}",
                      file=sys.stderr)
                break
            time.sleep(SETTLE_POLL)
    finally:
        server.stdin.close()
        try:
            server.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            server.kill()
    return out


def load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"{path}: {e}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("collect")
    c.add_argument("--repo", required=True)
    c.add_argument("--day", help="one UTC day, YYYY-MM-DD (default yesterday)")
    c.add_argument("--since", help="first UTC day of a backfill")
    c.add_argument("--until", help="last UTC day of a backfill (default yesterday)")
    c.add_argument("--workflow", action="append", default=[],
                   help="count only commits that ran this workflow (repeatable); default every push workflow")
    c.add_argument("--start", type=dt.date.fromisoformat,
                   help="ignore runs before this UTC day, when they cannot be compared, such as CI re-enabled after a gap")
    s = commands.add_parser("shifts")
    s.add_argument("data")
    s.add_argument("--limit", type=int, default=5)
    commands.add_parser("summary").add_argument("data")
    g = commands.add_parser("signals", help="what the last days of pushes show, for choosing actions")
    g.add_argument("data")
    g.add_argument("--days", type=int, default=WINDOW)
    lg = commands.add_parser("logs", help="save a day's job logs for reading")
    lg.add_argument("data")
    lg.add_argument("--out", required=True)
    lg.add_argument("--day", help="default the last day")
    t = commands.add_parser("tests", help="set each day's test count from the job logs, in place")
    t.add_argument("data")
    t.add_argument("--pattern", action="append", required=True,
                   help="regex for a line reporting tests, the count in a group (repeatable)")
    m = commands.add_parser("measure", help="add the test ratio and coverage to the last day, in place")
    m.add_argument("data")
    m.add_argument("--checkout", required=True, help="a local clone of the repository")
    m.add_argument("--timeout", type=int, default=1800, help="seconds each mise task may take")
    m.add_argument("--every-day", action="store_true", help="lines on every day, for a backfill; coverage stays last-day")
    m.add_argument("--path", action="append", default=[],
                   help="a git pathspec of main source to count, ':!dir' to leave one out (repeatable; default all)")
    r = commands.add_parser("records")
    r.add_argument("data")
    r.add_argument("incidents", nargs="?")
    r.add_argument("--actions", help="the current top actions, which replace the stored ones")
    r.add_argument("--doc", help="the document's uuid: print update_data arguments instead of the operations alone")
    n = commands.add_parser("create")
    n.add_argument("data")
    n.add_argument("--incidents")
    n.add_argument("--actions")
    n.add_argument("--tag", action="append", default=[], help="a catalog tag id from list_tags")
    commands.add_parser("charts").add_argument("data")
    commands.add_parser("changelog").add_argument("incidents")
    k = commands.add_parser("cards", help="the actions as card blocks, for the Actions section")
    k.add_argument("data")
    k.add_argument("actions", help="the agent's actions, or the stored ones from get_data")
    k.add_argument("--doc", help="the document's uuid, named in each card's prompt")
    u = commands.add_parser("ub", help="call Uberblick MCP tools through one `ub mcp serve`")
    u.add_argument("tool", nargs="?", help="one tool; or pass --calls")
    u.add_argument("arguments", nargs="?", help="the tool's arguments: inline JSON or a JSON file (default none)")
    u.add_argument("--calls", help='a JSON file listing calls, [{"tool": ..., "arguments": {...}}], run in order')
    u.add_argument("--checkout", default=".", help="a checkout bound to the workspace (default here)")
    args = parser.parse_args()
    if args.command == "collect":
        if args.day and (args.since or args.until):
            sys.exit("--day and --since/--until do not combine")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
            sys.exit(f"--repo {args.repo}: expected OWNER/NAME")
        try:
            out = collect(args.repo, *window(args), required=args.workflow,
                          floor=args.start)
        except RuntimeError as e:
            sys.exit(str(e))
    elif args.command == "shifts":
        data = load(args.data)
        out = shifts(data, args.limit) + hangs(data)
    elif args.command == "logs":
        try:
            out = save_logs(load(args.data), args.out, args.day)
        except RuntimeError as e:
            sys.exit(str(e))
    elif args.command == "tests":
        Path(args.data).write_text(json.dumps(add_tests(load(args.data), args.pattern), indent=1))
        return
    elif args.command == "measure":
        Path(args.data).write_text(json.dumps(measure(load(args.data), args.checkout, args.timeout, args.every_day, args.path), indent=1))
        return
    elif args.command == "signals":
        out = signals(load(args.data), args.days)
    elif args.command == "summary":
        print(summary(load(args.data)))
        return
    elif args.command == "records":
        out = records(load(args.data), load(args.incidents) if args.incidents else (),
                      load(args.actions) if args.actions else None)
        if args.doc:
            out = {"uuid": args.doc, "operations": out}
    elif args.command == "create":
        out = create_document(load(args.data), load(args.incidents) if args.incidents else (),
                              load(args.actions) if args.actions else ())
        if args.tag:
            out["tags"] = args.tag
    elif args.command == "charts":
        out = charts(load(args.data))
    elif args.command == "cards":
        out = cards(load(args.data), load(args.actions), args.doc)
    elif args.command == "ub":
        if bool(args.calls) == bool(args.tool):
            sys.exit("ub: pass one TOOL or --calls FILE")
        if args.calls:
            calls = load(args.calls)
        else:
            given = args.arguments or "{}"
            try:
                calls = [{"tool": args.tool,
                          "arguments": json.loads(given) if given.lstrip().startswith("{") else load(given)}]
            except ValueError as e:
                sys.exit(f"ub {args.tool}: {e}")
        results = ub_calls(calls, args.checkout)
        print(results[0]["result"] if args.tool else json.dumps(results, indent=1, ensure_ascii=False))
        return
    else:
        out = changelog(load(args.incidents))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
