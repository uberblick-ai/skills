#!/usr/bin/env python3
"""Facts and the dataset records for the ci-health skill. Reads GitHub Actions only; standard library and `gh`.

    ci.py collect --repo OWNER/NAME [--day YYYY-MM-DD | --since YYYY-MM-DD [--until YYYY-MM-DD]] > data.json
    ci.py shifts data.json [--limit 5]                 # candidate incidents: steps in wall time, and hangs
    ci.py summary data.json                            # the days as a Markdown table, for a reply
    ci.py records data.json [incidents.json] > operations.json  # update_data batch for the CI health document
    ci.py create data.json... [--incidents incidents.json] > create.json  # create_doc arguments for a new document
    ci.py section data.json > section.json             # insert_block arguments for one more repository
    ci.py changelog incidents.json > changelog.json    # the document's Incidents list, latest five

Days are UTC calendar days; the default is yesterday. A commit counts on the day its first push run was
created. Wall time is the time from the first job starting to the last job finishing, over every workflow the
push to the default branch triggered: what someone waits for once runners pick the work up. See
references/data.md.
"""

import argparse
import datetime as dt
import io
import json
import re
import statistics
import subprocess
import sys
import zipfile
from pathlib import Path

SCHEMA = "ci-health/1"
WINDOW = 7  # rolling median over this many days, the headline
LOOKBACK = 21  # days of commits read before the first day: the rolling median and step detection need them
LOG = re.compile(r"^﻿?\d{4}-\d\d-\d\dT[\d:.]+Z ?")
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
VITEST = re.compile(r"\bTests\s+((?:\d+ (?:passed|failed|skipped|todo|flaky)\s*\|?\s*)+)\(\d+\)")
JEST = re.compile(r"^Tests:\s+(.*\d+ total)")
COUNTS = re.compile(r"(\d+) (passed|failed|flaky|errors?|skipped|todo)\b")
PLAYWRIGHT = re.compile(r"^\s*(\d+) (passed|failed|flaky)(?: \([\d.]+m?s?\)| \(\d+(?:\.\d+)?[smh]\))?\s*$")
UNITTEST = re.compile(r"^Ran (\d+) tests? in ")
UNITTEST_SKIPPED = re.compile(r"^(?:OK|FAILED) \(.*?skipped=(\d+)")
PYTEST = re.compile(r"^=+ (.*?\d+ (?:passed|failed).*?) in [\d.]+s")
NODE = re.compile(r"^ℹ (tests|skipped|todo) (\d+)$")
DOTS = re.compile(r"^[.X]+$")
RAN = {"passed", "failed", "flaky", "error", "errors"}


def gh(path, raw=False):
    done = subprocess.run(["gh", "api", path], capture_output=True)
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


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]


def field(workflow, job):
    """Stable record field for one job's minutes: workflow and job name, so two workflows never collide."""
    return f"{slug(f'{workflow} {job}')}_min"


def tests_in(text):
    """Tests a job ran, from the summaries test runners print: vitest, jest, playwright, unittest, pytest and the
    node test runner (its spec summary, or one mark per test from the dot reporter). None when nothing matched."""
    total, found, dots = 0, False, []
    lines = [ANSI.sub("", LOG.sub("", line)).rstrip() for line in text.splitlines()]
    for n, line in enumerate(lines):
        body = line.split(": ", 1)[1] if re.match(r"^\S+ (?:test|e2e)\S*: ", line) else line
        if m := VITEST.search(body) or JEST.search(body) or PYTEST.search(body):
            total += sum(int(c) for c, kind in COUNTS.findall(m.group(1)) if kind in RAN)
            found = True
        elif m := PLAYWRIGHT.match(body):
            total += int(m.group(1))
            found = True
        elif m := UNITTEST.match(body):
            skipped = next((int(s.group(1)) for later in lines[n + 1:n + 6] if (s := UNITTEST_SKIPPED.match(later))), 0)
            total += int(m.group(1)) - skipped
            found = True
            # The unittest runner's own progress marks are not a second suite.
            dots = [d for d in dots if d[0] < n - 6]
        elif m := NODE.match(body):
            total += int(m.group(2)) * (1 if m.group(1) == "tests" else -1)
            found = True
        elif DOTS.match(body):
            dots.append((n, body.count(".") + body.count("X")))
    total += sum(count for _, count in dots)
    return total if found or dots else None


def job_log(repo, job_id):
    data = gh(f"repos/{repo}/actions/jobs/{job_id}/logs", raw=True)
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


def collect(repo, first, last, tests=True, required=(), floor=None):
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
    if tests:
        # One log read per day: the day's last green commit.
        for day in {c["day"] for c in rows if first.isoformat() <= c["day"]}:
            green = [c for c in rows if c["day"] == day and c["ok"]]
            if green:
                count_tests(repo, green[-1])
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
                  "execution_min": median(c["execution_min"] for c in green),
                  "wait_min": median(c["wait_min"] for c in green)}
        per_job = {}
        for c in green:
            for j in c["jobs"]:
                key_ = field(j["workflow"], j["name"])
                names[key_] = f"{j['workflow']} / {j['name']}"
                per_job.setdefault(key_, []).append(j["min"])
        record |= {k: median(v) for k, v in sorted(per_job.items())}
        counted = [c for c in green if c.get("tests") is not None]
        if counted:
            record["tests"] = counted[-1]["tests"]
        days.append({k: v for k, v in record.items() if v is not None})
        d += dt.timedelta(days=1)
    for c in rows:
        for j in c["jobs"]:
            names.setdefault(field(j["workflow"], j["name"]), f"{j['workflow']} / {j['name']}")
    return {"schema": SCHEMA, "repo": repo, "branch": branch, "first": first.isoformat(), "last": last.isoformat(),
            "collected": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workflows": list(required), "jobs": dict(sorted(names.items())), "days": days, "commits": rows}


def count_tests(repo, commit):
    """Tests on a green commit, summed over its jobs; a matrix runs one suite several times, so jobs that differ
    only in their parenthesised matrix values count once, at their largest."""
    groups = {}
    for j in commit["jobs"]:
        try:
            j["tests"] = tests_in(job_log(repo, j["id"]))
        except RuntimeError as e:
            print(f"tests: no log for {j['workflow']} / {j['name']}: {e}", file=sys.stderr)
            j["tests"] = None
        if j["tests"] is not None:
            base = (j["workflow"], re.sub(r"\s*\(.*\)$", "", j["name"]))
            groups[base] = max(groups.get(base, 0), j["tests"])
    commit["tests"] = sum(groups.values()) if groups else None


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
    head = ["Day", "Commits", "Failed", "Wall (7d)", "Wall", *[data["jobs"][k] for k in jobs], "Tests"]
    lines = ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
    fmt = lambda v: "" if v is None else f"{v:.1f}" if isinstance(v, float) else str(v)
    for d in data["days"]:
        lines.append("| " + " | ".join([d["day"], fmt(d["commits"]), fmt(d["failed"]), fmt(d.get("wall_min_7d")),
                                        fmt(d.get("wall_min")), *[fmt(d.get(k)) for k in jobs],
                                        fmt(d.get("tests"))]) + " |")
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


def collection_name(repo):
    """One collection per repository, named like it: a chart reads one collection, so each repository has its own."""
    return repo.split("/", 1)[1]


def schema(data):
    fields = {"day": DAY, "repo": TEXT, "workflows": TEXT, "start": DAY, "commits": COUNT, "failed": COUNT, "tests": COUNT,
              **dict.fromkeys(["wall_min", "wall_min_7d", "execution_min", "wait_min", *data["jobs"]], NUM)}
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
        rows.append({"id": f"{collection_name(i['repo'])}/{i['day']}", "value": value})
    return rows


def records(data, incidents=()):
    """One update_data batch: the repository's days, keyed by day so a refresh replaces them, and any incidents."""
    batch = [{"collection": collection_name(data["repo"]), "schema": schema(data),
              "upsert": [{"id": d["day"], "value": d} for d in data["days"]]}]
    if incidents:
        batch.append({"collection": "incidents", "schema": INCIDENTS, "upsert": incident_rows(incidents)})
    return batch


def chart(mapping):
    return {"type": "chart", "text": json.dumps(mapping, indent=1)}


def section(data):
    """A repository's heading and charts, bound to its collection."""
    repo, name = data["repo"], collection_name(data["repo"])
    # Job names change as CI is reworked: draw the jobs of the last three days with green commits; older ones
    # stay in the data.
    recent = [d for d in data["days"] if d.get("wall_min") is not None][-3:]
    jobs = [k for k in data["jobs"] if any(k in d for d in recent)] or list(data["jobs"])
    x = {"field": "day", "type": "date", "label": "Day"}
    blocks = [{"type": "heading", "level": 2, "text": repo},
              chart({"version": 1, "type": "line", "collection": name, "title": f"{name}: wall time on {data['branch']}",
                     "x": x, "missing": "connect",
                     "y": [{"field": "wall_min_7d", "label": "Total wall time, 7-day median", "unit": "min"},
                           *[{"field": k, "label": data["jobs"][k], "unit": "min"} for k in jobs[:7]]]}),
              chart({"version": 1, "type": "line", "collection": name, "title": f"{name}: tests", "x": x,
                     "missing": "connect", "y": [{"field": "tests", "label": "Tests"}]})]
    if len(jobs) > 7:
        blocks.insert(2, {"type": "paragraph", "text": f"{len(jobs) - 7} more jobs are in the data but not drawn."})
    return blocks


def changelog(incidents, limit=5):
    """The latest incidents as list items, newest first: day, repository, the change linked, its effect and why."""
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
            {"text": f"{day}, {collection_name(i['repo'])}: ", "marks": {"bold": True}},
            {"text": i["title"], "marks": {"link": url} if url else {}},
            {"text": f" ({effect}). {i['why']}", "marks": {}}]})
    return blocks or [{"type": "paragraph", "text": "No incident recorded yet."}]


def create_document(datas, incidents=()):
    """create_doc arguments for a new CI health document: intent, how to read it, the incidents, then one section
    per repository."""
    repos = ", ".join(d["repo"] for d in datas)
    blocks = [
        {"type": "paragraph", "text": "How long a push to main waits for CI, and how many tests it runs. The goal is "
         "short wall time: the time from the first job starting to the last one finishing, not the minutes the "
         "jobs add up to, so running checks in parallel is one way to bring it down."},
        {"type": "paragraph", "inline": [
            {"text": "Reading the charts: ", "marks": {"bold": True}},
            {"text": "one point per day, medians over green commits in minutes. The first line is the total wall time, "
             "the median over the last 7 days; the others are each parallel job on its own, per day. Lower is better. "
             "Runner queueing before the first job is left out. Data from GitHub Actions, refreshed daily by the "
             "ci-health skill (npx skills@latest add uberblick-ai/skills).", "marks": {}}]},
        {"type": "heading", "level": 2, "text": "Incidents"},
        {"type": "paragraph", "text": "The latest steps in total wall time, up or down, and the change behind each."},
        *changelog(list(incidents)),
    ]
    for data in datas:
        blocks += section(data)
    return {"title": "CI health", "description": f"Daily CI wall time and test count on main for {repos}, stored "
            "by the ci-health skill.", "blocks": blocks}


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
    c.add_argument("--no-tests", action="store_true", help="skip reading job logs for the test count")
    s = commands.add_parser("shifts")
    s.add_argument("data")
    s.add_argument("--limit", type=int, default=5)
    commands.add_parser("summary").add_argument("data")
    r = commands.add_parser("records")
    r.add_argument("data")
    r.add_argument("incidents", nargs="?")
    n = commands.add_parser("create")
    n.add_argument("data", nargs="+")
    n.add_argument("--incidents")
    commands.add_parser("section").add_argument("data")
    commands.add_parser("changelog").add_argument("incidents")
    args = parser.parse_args()
    if args.command == "collect":
        if args.day and (args.since or args.until):
            sys.exit("--day and --since/--until do not combine")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo):
            sys.exit(f"--repo {args.repo}: expected OWNER/NAME")
        try:
            out = collect(args.repo, *window(args), tests=not args.no_tests, required=args.workflow,
                          floor=args.start)
        except RuntimeError as e:
            sys.exit(str(e))
    elif args.command == "shifts":
        data = load(args.data)
        out = shifts(data, args.limit) + hangs(data)
    elif args.command == "summary":
        print(summary(load(args.data)))
        return
    elif args.command == "records":
        out = records(load(args.data), load(args.incidents) if args.incidents else ())
    elif args.command == "create":
        out = create_document([load(p) for p in args.data], load(args.incidents) if args.incidents else ())
    elif args.command == "section":
        out = section(load(args.data))
    else:
        out = changelog(load(args.incidents))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
