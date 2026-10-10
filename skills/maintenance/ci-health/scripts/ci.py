#!/usr/bin/env python3
"""Facts and the dataset records for the ci-health skill. Reads GitHub Actions only; standard library and `gh`.

    ci.py collect --repo OWNER/NAME [--day D | --since D [--until D]] [--workflow W] [--start D] > data.json
    ci.py shifts data.json [--limit 5]                 # candidate incidents: steps in wall time, and hangs
    ci.py logs data.json --out DIR [--day DAY]         # a day's job logs, cleaned, to find the test summary line
    ci.py tests data.json --pattern REGEX...           # each day's test count from that line, added in place
    ci.py measure data.json --checkout PATH            # optional: coverage and code/test lines, added in place
    ci.py summary data.json                            # the days as a Markdown table, for a reply
    ci.py records data.json [incidents.json] [--doc UUID] > update.json  # update_data batch for the document
    ci.py create data.json [--incidents incidents.json] [--tag ID]... > create.json  # create_doc arguments
    ci.py charts data.json > charts.json               # the chart blocks, to replace when the jobs change
    ci.py changelog incidents.json > changelog.json    # the document's Incidents list, latest five
    ci.py ub TOOL [arguments.json] [--checkout PATH]   # an Uberblick MCP tool through `ub mcp serve`

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
import statistics
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

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
    capture, on every line it matches, summed. None when no pattern matched."""
    total, found = 0, False
    for line in clean(text).splitlines():
        for pattern in patterns:
            if m := pattern.search(line):
                total += sum(int(g) for g in m.groups() if g and g.isdigit())
                found = True
    return total if found else None


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
                  "wait_min": median(c["wait_min"] for c in green)}
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


# Source files for the built-in line count, by extension; everything else (docs, data, lockfiles) is left out.
SOURCE = {"c", "cc", "cpp", "cs", "cxx", "dart", "ex", "exs", "fs", "go", "h", "hpp", "java", "js", "jsx", "kt",
          "kts", "lua", "m", "mjs", "cjs", "mm", "php", "pl", "py", "rb", "rs", "scala", "sh", "swift", "ts", "tsx",
          "vb", "vue", "svelte", "zig"}
# Test files by path, across ecosystems: test directories, and test_*, *_test, *.test, *.spec, *Test(s), *Spec.
TEST_PATH = re.compile(r"(^|/)(tests?|__tests__|spec|specs|e2e|testing)/|(^|/)test_[^/]*$|[^/]*(_test|_tests|_spec|"
                       r"\.test|\.spec|Tests?|Spec)\.[^/.]+$")


def mise_tasks(root):
    """Task names the checkout's mise config defines; empty when mise is missing or has none."""
    done = subprocess.run(["mise", "tasks", "ls", "--json"], cwd=root, capture_output=True, text=True,
                          env=mise_env(root))
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


def count_lines(root):
    """Code and test lines over the source files git tracks, by extension and test path. A rough, language-agnostic
    split; a repository that wants its own defines `mise run loc`."""
    files = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout.split(b"\0")
    code = test = 0
    for name in filter(None, (f.decode(errors="replace") for f in files)):
        if name.rsplit(".", 1)[-1].lower() not in SOURCE or "." not in name:
            continue
        try:
            with open(Path(root) / name, "rb") as f:
                n = sum(1 for line in f if line.strip())
        except OSError:
            continue
        if TEST_PATH.search(name):
            test += n
        else:
            code += n
    return {"code_lines": code, "test_lines": test}


def measure(data, checkout, timeout=1800):
    """Coverage and code against test lines at the last day's last green commit, from a detached worktree of
    `checkout`. `mise run codecov` and `mise run loc` are used when the checkout defines them; lines fall back to
    count_lines. Adds the figures to the last day."""
    day = data["days"][-1]
    commit = last_green(data, day["day"])
    if not commit:
        print(f"measure: no green commit on {day['day']}", file=sys.stderr)
        return data
    sha = commit["sha"]
    git = lambda *a, **k: subprocess.run(["git", "-C", checkout, *a], capture_output=True, text=True, **k)
    if git("cat-file", "-e", f"{sha}^{{commit}}").returncode:
        git("fetch", "-q", "origin", sha)
    root = Path(tempfile.mkdtemp(prefix="ci-health-")) / "tree"
    added = git("worktree", "add", "-q", "--detach", str(root), sha)
    if added.returncode:
        sys.exit(f"measure: cannot check out {sha[:12]} in {checkout}: {added.stderr.strip()}")
    try:
        tasks = mise_tasks(root)
        found = {}
        if "codecov" in tasks:
            found |= {k: v for k, v in mise_json(root, "codecov", timeout).items() if k == "coverage_pct"}
        if "loc" in tasks:
            found |= {k: v for k, v in mise_json(root, "loc", timeout).items() if k in ("code_lines", "test_lines")}
        if "code_lines" not in found or "test_lines" not in found:
            found |= count_lines(root)
    finally:
        git("worktree", "remove", "--force", str(root))
    if found.get("code_lines"):
        found["test_ratio"] = round(found["test_lines"] / found["code_lines"], 2)
    day |= {k: v for k, v in found.items() if isinstance(v, (int, float))}
    day["measured_sha"] = sha[:12]
    return data


def number(title):
    m = re.search(r"\(#(\d+)\)\s*$", title) or re.search(r"Merge pull request #(\d+)", title)
    return int(m.group(1)) if m else None


def shifts(data, limit=5, span=8):
    """Steps in wall time over green commits: at each commit, the median of the `span` green commits before against
    the `span` from it on. A step must move at least a minute and 15 percent; nearby steps keep only the largest.
    Each carries the commits around it, so the agent can name the change, and the jobs that moved."""
    green = [c for c in data["commits"] if c["ok"]]
    found = []
    for i in range(span, len(green) - span + 1):
        before, after = green[i - span:i], green[i:i + span]
        b, a = median(c["wall_min"] for c in before), median(c["wall_min"] for c in after)
        delta = a - b
        if abs(delta) >= max(1.0, 0.15 * b):
            found.append((abs(delta), i, b, a))
    chosen = []
    for size, i, b, a in sorted(found, reverse=True):
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
        out.append({"repo": data["repo"], "day": green[i]["day"], "direction": "slower" if a > b else "faster",
                    "before_min": b, "after_min": a, "change_min": round(a - b, 2),
                    "change_pct": round(100 * (a - b) / b) if b else None, "jobs": moved,
                    "suspects": [{"sha": c["sha"][:12], "day": c["day"], "title": c["title"], "pr": number(c["title"]),
                                  "wall_min": c["wall_min"]}
                                 for c in data["commits"][max(0, data["commits"].index(green[i]) - 3):
                                                          data["commits"].index(green[i]) + 2]]})
    return out


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
            pick = lambda x: {"sha": x["sha"][:12], "day": x["day"], "title": x["title"], "pr": number(x["title"]),
                              "wall_min": x["wall_min"]} if x else None
            out.append({"repo": data["repo"], "kind": "hang", "day": stretch[0]["day"], "commits": len(stretch),
                        "hung_min": median(x["wall_min"] for x in stretch), "green_min": typical,
                        "first": pick(stretch[0]), "last": pick(stretch[-1]), "after": pick(c)})
            stretch = []
    return out


def summary(data):
    jobs = [k for k in data["jobs"] if any(k in d for d in data["days"])]
    extra = [k for k in ("tests", "coverage_pct", "code_lines", "test_lines") if any(k in d for d in data["days"])]
    titles = {"tests": "Tests", "coverage_pct": "Coverage %", "code_lines": "Code lines", "test_lines": "Test lines"}
    head = ["Day", "Commits", "Failed", "Wall (7d)", "P95 (7d)", "Wall", *[data["jobs"][k] for k in jobs], *[titles[k] for k in extra]]
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    fmt = lambda v: "" if v is None else f"{v:.1f}" if isinstance(v, float) else str(v)
    wall = lambda d: fmt(d.get("wall_min_7d")) + (f" ± {fmt(float(d['wall_spread_7d']))}" if "wall_spread_7d" in d else "")
    for d in data["days"]:
        lines.append("| " + " | ".join([d["day"], fmt(d["commits"]), fmt(d["failed"]), wall(d), fmt(d.get("wall_p95_7d")),
                                        fmt(d.get("wall_min")), *[fmt(d.get(k)) for k in jobs],
                                        *[fmt(d.get(k)) for k in extra]]) + " |")
    return f"{data['repo']} ({data['branch']}), minutes, medians of green commits:\n\n" + "\n".join(lines)


NUM = {"type": ["number", "null"], "minimum": 0}
COUNT = {"type": "integer", "minimum": 0}
TEXT = {"type": "string"}
DAY = {"type": "string", "minLength": 10, "maxLength": 10}
INCIDENTS = {"version": 1, "schema": {"type": "object", "required": ["day", "repo", "direction", "title", "why"],
             "properties": {"day": DAY, "repo": TEXT, "direction": {"type": "string", "enum": ["slower", "faster"]},
                            "before_min": NUM, "after_min": NUM, "change_min": {"type": ["number", "null"]},
                            "change_pct": {"type": ["number", "null"]}, "title": TEXT, "why": TEXT, "ref": TEXT,
                            "url": TEXT, "jobs": TEXT}}}


def schema(data):
    fields = {"day": DAY, "repo": TEXT, "workflows": TEXT, "start": DAY, "measured_sha": TEXT, "tests_pattern": TEXT,
              **dict.fromkeys(["commits", "failed", "tests", "code_lines", "test_lines"], COUNT),
              "coverage_pct": {"type": ["number", "null"], "minimum": 0, "maximum": 100},
              **dict.fromkeys(["wall_min", "wall_min_7d", "wall_spread_7d", "wall_p95_7d", "execution_min", "wait_min", "test_ratio", *data["jobs"]], NUM)}
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
                                   "title", "why", "ref", "url") if i.get(k) is not None}
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


def records(data, incidents=()):
    """One update_data batch: the repository's days, keyed by day so a refresh replaces them, and any incidents."""
    if any(i.get("repo") not in (None, data["repo"]) for i in incidents):
        sys.exit(f"incidents: every incident must be for {data['repo']}, the repository of this document")
    batch = [{"collection": "days", "schema": schema(data),
              "upsert": [{"id": d["day"], "value": d} for d in data["days"]]}]
    if incidents:
        batch.append({"collection": "incidents", "schema": INCIDENTS, "upsert": incident_rows(incidents)})
    return batch


def chart(mapping):
    return {"type": "chart", "text": json.dumps(mapping, indent=1)}


def charts(data):
    """The wall-time and test charts, bound to the document's days."""
    # Job names change as CI is reworked: draw the jobs of the last three days with green commits; older ones
    # stay in the data.
    recent = [d for d in data["days"] if d.get("wall_min") is not None][-3:]
    jobs = [k for k in data["jobs"] if any(k in d for d in recent)] or list(data["jobs"])
    x = {"field": "day", "type": "date", "label": "Day"}
    blocks = [chart({"version": 1, "type": "line", "collection": "days", "title": f"Wall time on {data['branch']}",
                     "x": x, "missing": "connect",
                     "y": [{"field": "wall_min_7d", "label": "Total wall time, 7-day median", "unit": "min"},
                           {"field": "wall_p95_7d", "label": "Total wall time, 7-day P95", "unit": "min"},
                           *[{"field": k, "label": data["jobs"][k], "unit": "min"} for k in jobs[:6]]]}),
              chart({"version": 1, "type": "line", "collection": "days", "title": "Tests", "x": x,
                     "missing": "connect", "y": [{"field": "tests", "label": "Tests"}]})]
    if any("code_lines" in d for d in data["days"]):
        blocks.append(chart({"version": 1, "type": "line", "collection": "days", "title": "Code and test lines",
                             "x": x, "missing": "connect", "y": [{"field": "code_lines", "label": "Code lines"},
                                                                 {"field": "test_lines", "label": "Test lines"}]}))
    if any("coverage_pct" in d for d in data["days"]):
        blocks.append(chart({"version": 1, "type": "line", "collection": "days", "title": "Test coverage", "x": x,
                             "missing": "connect", "y": [{"field": "coverage_pct", "label": "Coverage", "unit": "%"}]}))
    if len(jobs) > 6:
        blocks.insert(1, {"type": "paragraph", "text": f"{len(jobs) - 6} more jobs are in the data but not drawn."})
    return blocks


def changelog(incidents, limit=5):
    """The latest incidents as list items, newest first: the day, the change linked, its effect and why."""
    rows = incidents.get("records", incidents) if isinstance(incidents, dict) else incidents
    rows = [r.get("value", r) for r in rows]
    blocks = []
    for i in sorted(rows, key=lambda i: i["day"], reverse=True)[:limit]:
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


def create_document(data, incidents=()):
    """create_doc arguments for a repository's CI health document: intent, how to read it, the charts, then the
    incidents."""
    repo, name = data["repo"], data["repo"].split("/", 1)[1]
    blocks = [
        {"type": "paragraph", "text": f"How long a push to {data['branch']} in {repo} waits for CI, and how many tests "
         "it runs. The goal is short wall time: the time from the first job starting to the last one finishing, not "
         "the minutes the jobs add up to, so running checks in parallel is one way to bring it down."},
        {"type": "paragraph", "inline": [
            {"text": "Reading the charts: ", "marks": {"bold": True}},
            {"text": "one point per day, over green commits, in minutes. The first two lines are the total wall time over "
             "the last 7 days: the median, and the P95 that shows the slow tail. The others are each parallel job "
             "on its own, the median per day. Lower is better. "
             "Runner queueing before the first job is left out. Data from GitHub Actions, refreshed daily by the "
             "ci-health skill (npx skills@latest add uberblick-ai/skills).", "marks": {}}]},
        *charts(data),
        {"type": "heading", "level": 2, "text": "Incidents"},
        {"type": "paragraph", "text": "The latest steps in total wall time, up or down, and the change behind each."},
        *changelog(list(incidents)),
    ]
    return {"title": "CI health",
            "description": f"How long CI takes on {data['branch']} in {repo}: daily GitHub Actions wall time per "
                           "parallel job and in total, test counts, and the incidents that made CI slower or faster. "
                           "Data in the document's days and incidents, refreshed by the ci-health skill.",
            "tldr": f"Tracks how long a push to {data['branch']} in {name} waits for CI, how many tests run, and which "
                    "changes moved it.",
            "blocks": blocks}


def ub_call(tool, arguments, checkout, timeout=300):
    """Call one Uberblick MCP tool through `ub mcp serve` in `checkout`, for a host that has the `ub` command but not
    the uberblick MCP tools. The server serves the workspace that checkout is bound to."""
    try:
        server = subprocess.Popen(["ub", "mcp", "serve"], cwd=checkout, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  text=True)
    except OSError as e:
        sys.exit(f"ub: {e}")

    def ask(n, method, params):
        server.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params}) + "\n")
        server.stdin.flush()
        for line in server.stdout:  # one JSON-RPC message per line; skip the server's notifications
            message = json.loads(line) if line.strip().startswith("{") else {}
            if message.get("id") == n:
                if "error" in message:
                    sys.exit(f"ub {method}: {message['error'].get('message')}")
                return message["result"]
        sys.exit(f"ub mcp serve stopped before answering {method}; run `ub doctor` in {checkout}")

    try:
        ask(1, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                              "clientInfo": {"name": "ci-health", "version": "1.0"}})
        server.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        result = ask(2, "tools/call", {"name": tool, "arguments": arguments})
    finally:
        server.stdin.close()
        try:
            server.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            server.kill()
    text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
    if result.get("isError"):
        sys.exit(f"ub {tool}: {text}")
    return text


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
                   help="ignore runs before this UTC day, such as the day CI was reworked or re-enabled")
    s = commands.add_parser("shifts")
    s.add_argument("data")
    s.add_argument("--limit", type=int, default=5)
    commands.add_parser("summary").add_argument("data")
    lg = commands.add_parser("logs", help="save a day's job logs for reading")
    lg.add_argument("data")
    lg.add_argument("--out", required=True)
    lg.add_argument("--day", help="default the last day")
    t = commands.add_parser("tests", help="set each day's test count from the job logs, in place")
    t.add_argument("data")
    t.add_argument("--pattern", action="append", required=True,
                   help="regex for a line reporting tests, the count in a group (repeatable)")
    m = commands.add_parser("measure", help="add coverage and code/test lines to the last day, in place")
    m.add_argument("data")
    m.add_argument("--checkout", required=True, help="a local clone of the repository")
    m.add_argument("--timeout", type=int, default=1800, help="seconds each mise task may take")
    r = commands.add_parser("records")
    r.add_argument("data")
    r.add_argument("incidents", nargs="?")
    r.add_argument("--doc", help="the document's uuid: print update_data arguments instead of the operations alone")
    n = commands.add_parser("create")
    n.add_argument("data")
    n.add_argument("--incidents")
    n.add_argument("--tag", action="append", default=[], help="a catalog tag id from list_tags")
    commands.add_parser("charts").add_argument("data")
    commands.add_parser("changelog").add_argument("incidents")
    u = commands.add_parser("ub", help="call an Uberblick MCP tool through `ub mcp serve`")
    u.add_argument("tool")
    u.add_argument("arguments", nargs="?", help="the tool's arguments: inline JSON or a JSON file (default none)")
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
        Path(args.data).write_text(json.dumps(measure(load(args.data), args.checkout, args.timeout), indent=1))
        return
    elif args.command == "summary":
        print(summary(load(args.data)))
        return
    elif args.command == "records":
        out = records(load(args.data), load(args.incidents) if args.incidents else ())
        if args.doc:
            out = {"uuid": args.doc, "operations": out}
    elif args.command == "create":
        out = create_document(load(args.data), load(args.incidents) if args.incidents else ())
        if args.tag:
            out["tags"] = args.tag
    elif args.command == "charts":
        out = charts(load(args.data))
    elif args.command == "ub":
        given = args.arguments or "{}"
        try:
            arguments = json.loads(given) if given.lstrip().startswith("{") else load(given)
        except ValueError as e:
            sys.exit(f"ub {args.tool}: {e}")
        print(ub_call(args.tool, arguments, args.checkout))
        return
    else:
        out = changelog(load(args.incidents))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
