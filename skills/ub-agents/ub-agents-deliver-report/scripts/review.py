#!/usr/bin/env python3
"""Facts, the page and the dataset records for the ub-agents-deliver-report skill. Reads GitHub only;
standard library and `gh`.

    review.py missing days.json                                 # the days to report: the gap since the newest stored day
    review.py collect --repo OWNER/NAME [--day YYYY-MM-DD] > data.json
    review.py digest data.json                                  # the day in a few lines per item, to read first
    review.py render data.json notes.json OUT_DIR [--no-open]   # writes report.html and report.json
    review.py records report.json [--schemas] > operations.json # update_data operations for the day
    review.py document dataset.json report.json [--doc UUID] [--since DAY] [--no-button] > sections.json  # Actions, Changelog
    review.py create report.json [--no-button] > create.json    # create_doc arguments for a new dataset document
    review.py queue --repo OWNER/NAME [--day YYYY-MM-DD]         # only the open-queue figures for a day

The day runs from midnight to midnight UTC; the default is yesterday. Only runs that started
before the day ended count, so a day reads the same whenever it is collected.
Works on any repository that runs ub-agents (https://agents.uberblick.ai): roles, triggers and outcomes
come from the repository's ub-agents.yaml, and ROLES maps the common role names to a letter.
"""

import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import re
import statistics
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

SCHEMA = "ub-agents-deliver-report/1"
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
# Every record version (ub-agent:v1, ub-agent:v2, ub-agents:v2, ub-agents:v3) carries the same JSON record.
RECORD = re.compile(r"<!-- ub-agents?:v\d+ -->.*?```json\n(.*?)\n```", re.S)
NOTICE = re.compile(r"<!-- ub-agents?:action-needed")
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)
LOCAL = re.compile(r"(?<![\w.~])/(?:Users|home|srv|mnt|tmp|private|var|opt|root)/\S*")
ROLES = {"issue-preparer": "P", "issue-reviewer": "Q", "implementer": "I", "pr-reviewer": "R", "reviewer": "R",
         "integrator": "G"}
ORDER = "PQIRG"
REVIEWERS = {"Q", "R"}
MARK = {"forward": "", "back": "<", "stop": "!", "waste": "x", "pending": "?"}
# Used only when ub-agents.yaml declares no outcomes for a role.
FALLBACK = {"needs-human": "stop", "maintainer-merge": "stop", "changes": "back", "changes-requested": "back",
            "returned": "back"}
CLASSES = ["launcher", "environment", "context", "sandbox", "scheduling", "routing", "integration", "ci", "contract",
           "decision"]
STATES = ["open", "fixed", "accepted"]
LEVERS = {"authority": "Clearer authority", "wording": "Better wording",
          "fewer-instructions": "Fewer instructions", "autonomy": "More autonomy"}
LESSON_STATES = ["proposed", "tracked", "applied", "rejected"]
ADDRESSED_AS = {"implemented": "Implemented", "planned": "Planned"}  # a pull request that does it, an issue that plans it


def public(text, limit):
    """Pages may be shared and boards are public: drop local paths."""
    return LOCAL.sub("<path>", " ".join((text or "").split()))[:limit]


def gh(*args):
    done = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    if done.returncode:
        raise RuntimeError((done.stderr or done.stdout).strip().splitlines()[-1])
    return json.loads(done.stdout)


def pages(path, **params):
    query = [f"-f{k}={v}" for k, v in params.items()]
    for page in range(1, 100):
        rows = gh("-XGET", path, "-fper_page=100", f"-fpage={page}", *query)
        yield from rows
        if len(rows) < 100:
            return


def when(text):
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00")) if text else None


def stamp(moment):
    return moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def minutes(start, end):
    return round((when(end) - when(start)).total_seconds() / 60, 1) if start and end else None


def hours(value):
    return None if value is None else round(value / 60, 2)


def median(values):
    values = [v for v in values if v is not None]
    return round(statistics.median(values), 2) if values else None


def share(part, whole):
    return round(part / whole, 2) if whole else None


def percent(part, whole):
    return round(100 * part / whole, 1) if whole else None


def cycle(runs, done):
    """Cycle time, first run start to delivery: the last run's end, or the merge or close when that came later."""
    started = [r["started"] for r in runs if r["started"]]
    if not started or not done:
        return None
    ends = [stamp(when(r["started"]) + dt.timedelta(minutes=r["minutes"])) for r in runs if r["started"] and r["minutes"]]
    return minutes(min(started), max(ends + [done]))


def waited(stops, runs, end):
    """Minutes from each stop to the next run on the item, or to the end, counting each wait once."""
    starts = sorted(when(r["started"]) for r in runs)
    waits = {}
    for stop in sorted(map(when, stops)):
        waits.setdefault(next((s for s in starts if s > stop), end), stop)
    return round(sum(max(0, (resume - stop).total_seconds()) for resume, stop in waits.items()) / 60, 1)


def day_window(text):
    """Midnight to midnight UTC for the given day, whatever the local zone; yesterday when none is given."""
    zone = dt.timezone.utc
    day = dt.date.fromisoformat(text) if text else dt.datetime.now(zone).date() - dt.timedelta(days=1)
    since = dt.datetime.combine(day, dt.time.min, zone)
    return day, zone, since, since + dt.timedelta(days=1)


def missing(stored, yesterday):
    """The days to report, oldest first: every day after the newest stored one up to yesterday, so a run fills the
    days nobody reported. With no day stored, or none missing, yesterday alone."""
    days = []
    for key, value in values(stored).items():
        try:
            days.append(dt.date.fromisoformat((value or {}).get("day") or key))
        except (TypeError, ValueError):
            continue
    first = max(days) + dt.timedelta(days=1) if days else yesterday
    return [(first + dt.timedelta(days=n)).isoformat() for n in range((yesterday - first).days + 1)] or \
        [yesterday.isoformat()]


def labels(text):
    return [part.strip(" '\"") for part in text.strip().strip("[]").split(",") if part.strip(" '\"")]


def config_of(text):
    """Per agent its retrospective board, trigger labels and the labels each outcome adds; and the stop labels."""
    agents, agent, section, stop = {}, None, None, ["needs-human"]
    for line in text.splitlines():
        line = line.split(" #")[0].rstrip()
        if found := re.match(r"^([\w-]+):(.*)", line):
            section = found.group(1)
            stop = labels(found.group(2)) if section == "stop-labels" else stop
        elif section != "agents":
            continue
        elif found := re.match(r"^  ([\w-]+):\s*$", line):
            agent = agents.setdefault(found.group(1), {"board": None, "triggers": [], "outcomes": {}})
        elif agent is None:
            continue
        elif found := re.match(r"^    retrospectives:\s*(\d+)", line):
            agent["board"] = int(found.group(1))
        elif found := re.match(r"^    trigger:\s*(.+)", line):
            agent["triggers"] = labels(found.group(1))
        elif found := re.match(r"^      ([\w-]+):\s*\{(.*)\}", line):
            add = re.search(r"add:\s*\[([^\]]*)\]", found.group(2))
            agent["outcomes"][found.group(1)] = labels(add.group(1)) if add else []
    return agents, set(stop)


def classifier(agents, stop):
    """A run moved the item forward, sent it back to an earlier role, stopped for a person, or was wasted:
    it ended without an accepted outcome the role declares."""
    rank = lambda name: ORDER.find(ROLES.get(name, "?"))
    triggered = {}
    for name, agent in agents.items():
        for label in agent["triggers"]:
            triggered.setdefault(label, []).append(rank(name))

    def kind(run):
        if run.get("pending"):
            return "pending"
        declared = agents.get(run["agent"], {}).get("outcomes")
        if not declared:
            return "waste" if not run["accepted"] else FALLBACK.get(run["result"], "forward")
        added = declared.get(run["result"])
        if added is None or not run["accepted"]:
            return "waste"
        if set(added) & stop:
            return "stop"
        next_roles = [r for label in added for r in triggered.get(label, [])]
        return "back" if next_roles and max(next_roles) < rank(run["agent"]) else "forward"
    return kind


def anonymous(*parts):
    """A short stable id for a host or a loop checkout: counts without hostnames or paths."""
    return hashlib.sha256("\0".join(parts).encode()).hexdigest()[:8] if all(parts) else None


def peak(runs):
    """The most runs that overlapped at any moment."""
    edges = sorted(e for r in runs if r["started"] and r["minutes"] for e in (
        (when(r["started"]), 1), (when(r["started"]) + dt.timedelta(minutes=r["minutes"]), -1)))
    most = current = 0
    for _, step in edges:
        current += step
        most = max(most, current)
    return most


def events_since(repo, moment):
    """Issue and PR events newer than moment, newest first."""
    for page in range(1, 300):
        rows = gh("-XGET", f"repos/{repo}/issues/events", "-fper_page=100", f"-fpage={page}")
        for event in rows:
            if when(event["created_at"]) < moment:
                return
            yield event
        if len(rows) < 100:
            return


def parents(repo):
    """Open issues with sub-issues: containers whose work is counted in their children."""
    owner, name = repo.split("/")
    found, cursor = set(), None
    while True:
        after = f', after: "{cursor}"' if cursor else ""
        page = gh("graphql", "-f", f'query=query {{ repository(owner: "{owner}", name: "{name}") {{ issues(states: OPEN, '
                  f'first: 100{after}) {{ pageInfo {{ hasNextPage endCursor }} nodes {{ number subIssues {{ totalCount }} }} }} }} }}'
                  )["data"]["repository"]["issues"]
        found |= {n["number"] for n in page["nodes"] if n["subIssues"]["totalCount"]}
        if not page["pageInfo"]["hasNextPage"]:
            return found
        cursor = page["pageInfo"]["endCursor"]


def queue(repo, until, rows, agents):
    """Open issues at the end of the day: those waiting for preparation, those already prepared, all of them, and
    those no role can take until a person starts them (no workflow label or parked; parents excluded). Today's
    labels and state with every later change undone; parent links are today's."""
    rank = lambda name: ORDER.find(ROLES.get(name, "?"))
    waiting = {l for name, a in agents.items() if rank(name) == 0 for l in a["triggers"]}
    prepared = {l for name, a in agents.items() if rank(name) in (1, 2) for l in a["triggers"]} - waiting
    state = {}
    for r in list(rows) + list(pages(f"repos/{repo}/issues", state="open")):
        if "pull_request" not in r:
            state.setdefault(r["number"], {"open": r["state"] == "open", "created": r["created_at"],
                                           "labels": {l["name"] for l in r["labels"]}})
    for event in events_since(repo, until):
        item = state.get(event["issue"]["number"]) if not event["issue"].get("pull_request") else None
        if item is None:
            continue
        label = (event.get("label") or {}).get("name")
        if event["event"] == "labeled":
            item["labels"].discard(label)
        elif event["event"] == "unlabeled":
            item["labels"].add(label)
        elif event["event"] in ("closed", "reopened"):
            item["open"] = event["event"] == "closed"
    containers = parents(repo)
    live = {n: i for n, i in state.items() if i["open"] and when(i["created"]) < until}
    unprepared = sum(bool(i["labels"] & waiting) for i in live.values())
    ready = sum(bool(i["labels"] & prepared) and not i["labels"] & waiting for i in live.values())
    return {"backlog": unprepared + ready, "backlog_unprepared": unprepared, "backlog_prepared": ready,
            "open_issues": len(live),
            "waiting_to_start": sum(not i["labels"] & (waiting | prepared) and n not in containers for n, i in live.items())}


def runs_of(records):
    leases = {r["run"]: r for r in records if r.get("kind") == "lease"}
    outcomes = {r["run"]: r for r in records if r.get("kind") == "outcome"}
    runs = []
    for run in leases.keys() | outcomes.keys():
        lease, out = leases.get(run, {}), outcomes.get(run, {})
        if lease.get("result") == "withdrawn" or (out.get("status") == "success" and not out.get("outcome")) or \
                (not out and lease.get("state") in ("withdrawn", "claiming")):
            continue  # withdrawn, a claim that never started, or a recovery lease re-posting another run's report
        result = out.get("outcome") if out.get("status") == "success" else out.get("status")
        runs.append({"agent": lease.get("agent") or out.get("agent"),
                     "runtime": lease.get("runtime") or out.get("runtime"),
                     "started": lease.get("created") or out.get("created"),
                     "minutes": minutes(lease.get("created"), out.get("created")),
                     "result": result or lease.get("result") or "no report",
                     "accepted": bool(out.get("accepted")),
                     "denied": [public(f'{d.get("tool")}: {d.get("command")}', 160) for d in out.get("denials") or []],
                     "denials_recorded": "denials" in out,
                     "summary": public(out.get("summary") or lease.get("summary"), 400),
                     "url": out.get("url") or lease.get("url"),
                     "machine": anonymous(lease.get("host") or out.get("host")),
                     "loop": anonymous(lease.get("host") or out.get("host"),
                                       re.split(r"/\.ub-agents?/", lease.get("log_dir") or "")[0] or None),
                     "pending": not out and lease.get("state") == "running" and bool(lease.get("expires"))
                     and when(lease["expires"]) > dt.datetime.now(dt.timezone.utc)})
    return sorted(runs, key=lambda r: r["started"] or "")


def board_posts(repo, agents):
    posts, errors, names = [], [], {}
    for agent, number in ((a, c["board"]) for a, c in agents.items() if c["board"]):
        names[number] = f'{names[number]}, {agent}' if number in names else agent
    for number, agent in names.items():
        try:
            comments = list(pages(f"repos/{repo}/discussions/{number}/comments"))
        except RuntimeError as exc:
            errors.append(f"{agent} board #{number}: {str(exc)[:160]}")
            continue
        posts += [{"agent": agent, "url": c["html_url"], "created": c["created_at"], "body": public(c["body"], 1200),
                   "items": {int(n) for n in re.findall(r"(?:#|/(?:issues|pull)/)(\d+)", c["body"])}}
                  for c in comments if c["author_association"] in TRUSTED and not c.get("parent_id")]
    return posts, errors


# What a day is read against: guidance, not a gate. A day with few deliveries swings widely; read a week.
TARGETS = {"autonomous_pct": (75, "75% or more"), "wasted_pct": (-10, "under 10%"), "denial_pct": (-10, "under 10%")}


def on_target(field, value):
    """True or False against the field's target; None without a target or a value. A negative limit is a ceiling."""
    if field not in TARGETS or value is None:
        return None
    limit = TARGETS[field][0]
    return value >= limit if limit >= 0 else value < -limit


NEEDS_CAUSE = {"back", "stop", "waste"}
EVENTS = {"labeled", "unlabeled", "merged", "closed", "reopened", "head_ref_force_pushed", "ready_for_review",
          "convert_to_draft"}
SLACK = dt.timedelta(minutes=5)  # the launcher swaps labels just before a run starts and just after it reports


def needs_cause(d):
    """An item whose runs the notes must explain: a send-back, a stop or a wasted run, or a loop delivery that was
    not autonomous."""
    return any(r["class"] in NEEDS_CAUSE for r in d["runs"]) or (d["loop"] and not d["autonomous"])


def evidence(repo, d, until, loop_accounts=frozenset()):
    """What the run summaries leave out, for an item that needs a cause: label and state changes by anyone but the
    accounts that post run records, commits pushed while none of its runs was going (a person, an attended session,
    another tool), and the CI runs on its PRs. Without known loop accounts, events also go by run times."""
    windows = [(when(r["started"]) - SLACK, when(r["started"]) + dt.timedelta(minutes=r["minutes"]) + SLACK
                if r["minutes"] is not None else until) for r in d["runs"] if r["started"]]
    outside = lambda text: bool(text) and when(text) < until and not any(a <= when(text) <= b for a, b in windows)
    found = {"commits": [], "events": [], "ci": [], "errors": []}
    for n in [d["number"]] + [p["number"] for p in d["prs"] if p["number"] != d["number"]]:
        try:
            for e in pages(f"repos/{repo}/issues/{n}/timeline"):
                if e.get("event") == "committed" and outside((e.get("committer") or {}).get("date")):
                    found["commits"].append({"pr": n, "sha": e["sha"][:7], "at": e["committer"]["date"],
                                             "author": (e.get("author") or {}).get("name"),
                                             "message": public((e.get("message") or "").splitlines()[0], 120)})
                elif e.get("event") in EVENTS and when(e.get("created_at")) < until and (
                        (e.get("actor") or {}).get("login") not in loop_accounts if loop_accounts
                        else outside(e.get("created_at"))):
                    label = (e.get("label") or {}).get("name")
                    found["events"].append({"item": n, "at": e["created_at"], "by": (e.get("actor") or {}).get("login"),
                                            "event": ("+" if e["event"] == "labeled" else "-") + label if label
                                            else e["event"]})
        except RuntimeError as exc:
            found["errors"].append(f"#{n} timeline: {str(exc)[:160]}")
    for p in d["prs"]:
        try:
            branch = gh(f"repos/{repo}/pulls/{p['number']}")["head"]["ref"]
            ci = gh("-XGET", f"repos/{repo}/actions/runs", f"-fbranch={branch}", "-fper_page=100")["workflow_runs"]
        except (RuntimeError, KeyError) as exc:
            found["errors"].append(f"#{p['number']} CI: {str(exc)[:160]}")
            continue
        found["ci"] += [{"pr": p["number"], "run": w["id"], "workflow": w.get("name"), "sha": w["head_sha"][:7],
                         "attempt": w.get("run_attempt", 1), "result": w.get("conclusion") or w.get("status"),
                         "started": w.get("run_started_at") or w["created_at"],
                         "minutes": minutes(w.get("run_started_at") or w["created_at"], w.get("updated_at"))}
                        for w in ci if when(w["created_at"]) < until]
    found["ci"].sort(key=lambda w: w["started"])
    return {k: v for k, v in found.items() if v}


def collect(repo, day, zone, since, until):
    inside = lambda text: bool(text) and since <= when(text) < until
    before = lambda text: bool(text) and when(text) < until
    agents, stop = config_of(base64.b64decode(gh(f"repos/{repo}/contents/ub-agents.yaml")["content"]).decode())
    kind = classifier(agents, stop)

    items, loop_accounts = {}, set()
    for row in pages(f"repos/{repo}/issues", state="all", since=stamp(since)):
        records, notices = [], []
        # An item opened after the day holds none of its runs, and one without comments holds no records.
        thread = row["comments"] and before(row["created_at"])
        for c in pages(f"repos/{repo}/issues/{row['number']}/comments") if thread else []:
            if c["author_association"] not in TRUSTED:
                continue
            if found := RECORD.search(c["body"] or ""):
                records.append(json.loads(found.group(1)) | {"url": c["html_url"]})
                loop_accounts.add((c.get("user") or {}).get("login"))
            if NOTICE.match(c["body"] or ""):
                notices.append(c["created_at"])
        items[row["number"]] = {"row": row, "records": records, "notices": notices}

    groups = {}
    for number, item in items.items():
        row = item["row"]
        if "pull_request" in row:
            targets = [int(n) for n in CLOSES.findall(row.get("body") or "")
                       if int(n) in items and "pull_request" not in items[int(n)]["row"]]
            for key in targets or [number]:
                groups.setdefault(key, set()).add(number)
        else:
            groups.setdefault(number, set()).update(int(r["handoff"]) for r in item["records"] if r.get("handoff"))

    posts, errors = board_posts(repo, agents)
    open_queue = queue(repo, until, [i["row"] for i in items.values()], agents)
    issues = []
    for key, prs in sorted(groups.items()):
        members = [key] + sorted(p for p in prs - {key} if p in items)
        head = items[key]["row"]
        runs = [r | {"class": kind(r)} for r in runs_of([r for n in members for r in items[n]["records"]])
                if before(r["started"])]
        letters = [ROLES.get(r["agent"], "?") for r in runs]
        pulls = []
        for n in members:
            if "pull_request" in items[n]["row"]:
                row = items[n]["row"]
                landed = row["pull_request"].get("merged_at")
                # The issue row carries the merge time; size counts only for PRs merged inside the day.
                pr = gh(f"repos/{repo}/pulls/{n}") if inside(landed) else {}
                pulls.append({"number": n, "url": row["html_url"], "merged": landed, "additions": pr.get("additions", 0),
                              "deletions": pr.get("deletions", 0), "files": pr.get("changed_files", 0),
                              "by_loop": inside(landed) and any(
                                  l == "G" and r["result"] == "merged" for l, r in zip(letters, runs))})
        merged = [p["merged"] for p in pulls if inside(p["merged"])]
        closed = "pull_request" not in head and inside(head.get("closed_at"))
        delivered = bool(merged) or closed
        if not delivered and not any(inside(r["started"]) for r in runs):
            continue
        done = max(merged) if merged else head.get("closed_at") if closed else None
        stops = sorted(t for n in members for t in items[n]["notices"] if before(t))
        # Early loop versions stopped for a person without posting an action-needed notice.
        stopped = [stamp(when(r["started"]) + dt.timedelta(minutes=r["minutes"] or 0)) for r in runs if r["class"] == "stop"]
        stops = stops if len(stops) >= len(stopped) else stopped
        loop = delivered and "I" in letters
        wait = waited(stops, runs, when(done) if done else until)
        took = cycle(runs, done)
        issues.append({
            "repo": repo, "day": day.isoformat(), "number": key, "title": head["title"], "url": head["html_url"],
            "delivered": delivered, "loop": loop,
            "autonomous": bool(loop and any(p["by_loop"] for p in pulls) and not stops and all(
                r["class"] == "forward" or (r["class"] == "back" and l in REVIEWERS) for l, r in zip(letters, runs))),
            "prs": pulls, "runs": runs,
            "sequence": " ".join(l + MARK[r["class"]] for l, r in zip(letters, runs)),
            "attempts": len(runs),
            "wasted_runs": sum(r["class"] == "waste" for r in runs),
            "review_rounds": sum(r["class"] == "back" and l in REVIEWERS for l, r in zip(letters, runs)),
            "human_stops": len(stops), "human_wait_h": hours(wait) if stops else 0,
            "lead_h": hours(minutes(head["created_at"], done)), "cycle_h": hours(took),
            "loop_cycle_h": hours(max(0, took - wait)) if took is not None else None,
            "run_h": hours(sum(r["minutes"] or 0 for r in runs)),
            "denials": sum(len(r["denied"]) for r in runs), "runs_with_denials": sum(bool(r["denied"]) for r in runs),
            "lines": sum(p["additions"] + p["deletions"] for p in pulls if inside(p["merged"])),
            "retrospectives": [p | {"items": sorted(p["items"])} for p in posts if p["items"] & set(members)]})
        if needs_cause(issues[-1]):
            issues[-1]["evidence"] = evidence(repo, issues[-1], until, frozenset(loop_accounts - {None}))

    window = [r for d in issues for r in d["runs"] if inside(r["started"])]
    # Older records carry no denials at all: count only runs that recorded them, so a gap is not a zero.
    claude = [r for r in window if (r["runtime"] or "").startswith("claude") and r.get("denials_recorded")]
    loop = [d for d in issues if d["loop"]]
    merged = {p["number"]: p for d in issues for p in d["prs"] if inside(p["merged"])}.values()
    rows = [i["row"] for i in items.values()]
    wasted = sum(r["class"] == "waste" for r in window)
    autonomous = sum(d["autonomous"] for d in loop)
    retrospectives = [p | {"items": sorted(p["items"])} for p in posts if inside(p["created"])]
    return {
        "schema": SCHEMA, "repo": repo, "day": day.isoformat(), "timezone": since.strftime("%Z %z"),
        "since": stamp(since), "until": stamp(until),
        "summary": {
            "repo": repo, "day": day.isoformat(),
            "deliveries": len(loop), "autonomous": autonomous, "autonomous_pct": percent(autonomous, len(loop)),
            "runs": len(window), "wasted_runs": wasted, "wasted_pct": percent(wasted, len(window)),
            "run_h": hours(sum(r["minutes"] or 0 for r in window)),
            "human_stops": sum(d["human_stops"] for d in loop),
            "human_stops_per_delivery": share(sum(d["human_stops"] for d in loop), len(loop)),
            "human_wait_h": round(sum(d["human_wait_h"] or 0 for d in loop), 2),
            "review_rounds_per_delivery": share(sum(d["review_rounds"] for d in loop), len(loop)),
            "lead_h_median": median(d["lead_h"] for d in loop), "cycle_h_median": median(d["cycle_h"] for d in loop),
            "loop_cycle_h_median": median(d["loop_cycle_h"] for d in loop),
            "run_h_median": median(d["run_h"] for d in loop),
            "claude_runs": len(claude), "runs_with_denials": sum(bool(r["denied"]) for r in claude),
            "denial_pct": percent(sum(bool(r["denied"]) for r in claude), len(claude)),
            "denials": sum(len(r["denied"]) for r in window),
            "prs_merged": len(merged), "prs_merged_by_loop": sum(p["by_loop"] for p in merged),
            "additions": sum(p["additions"] for p in merged), "deletions": sum(p["deletions"] for p in merged),
            "files": sum(p["files"] for p in merged),
            "issues_closed": sum(1 for r in rows if "pull_request" not in r and inside(r.get("closed_at"))),
            "issues_opened": sum(1 for r in rows if "pull_request" not in r and inside(r["created_at"])),
            "retrospectives": len(retrospectives),
            **open_queue, "peak_runs": peak(window),
            # Records from before host tracking say nothing about machines: leave the gap rather than report zero.
            **({"machines": len({r["machine"] for r in window if r["machine"]}),
                "loops": len({r["loop"] for r in window if r["loop"]})} if any(r["machine"] for r in window) else {})},
        "retrospectives": {"errors": errors, "in_window": retrospectives},
        "issues": issues}


def offset(data):
    """The day's UTC offset, from the collected time zone such as 'CEST +0200'."""
    found = re.search(r"([+-])(\d\d)(\d\d)$", data.get("timezone") or "")
    if not found:
        return dt.timezone.utc
    span_ = dt.timedelta(hours=int(found.group(2)), minutes=int(found.group(3)))
    return dt.timezone(span_ if found.group(1) == "+" else -span_)


def digest(data):
    """The day for the agent to read before data.json: every run of an item that needs a cause, with its summary,
    denials and evidence; one line for each item that went through cleanly or came from outside the loop."""
    zone, day, s = offset(data), data["day"], data["summary"]

    def at(text):
        if not text:
            return "?"
        moment = when(text).astimezone(zone)
        return moment.strftime("%H:%M") if moment.date().isoformat() == day else moment.strftime("%-d %b %H:%M")

    def num(value, unit=""):
        return "n/a" if value is None else f"{value:g}{unit}"

    def prs(d):
        return ", ".join(f'PR #{p["number"]} ' + (f'merged {at(p["merged"])}' + ("" if p["by_loop"] else " outside the loop")
                                                  if p["merged"] else "open") for p in d["prs"] if p["number"] != d["number"])

    def head(d):
        state = ("loop delivery" if d["loop"] else "delivered") if d["delivered"] else "not delivered"
        parts = [state + (", autonomous" if d["autonomous"] else ""), d["sequence"] or "no runs",
                 f'stops {d["human_stops"]} ({num(d["human_wait_h"], " h")} waited)' if d["human_stops"] else "",
                 f'cycle {num(d["loop_cycle_h"], " h")}' if d["loop_cycle_h"] is not None else "",
                 f'run {num(d["run_h"], " h")}' if d["runs"] else "", prs(d)]
        return f'#{d["number"]} {d["title"]}: ' + "; ".join(p for p in parts if p)

    out = [f'{data["repo"]}, {day} ({data["timezone"]}). Times are in that zone; times on other days carry their date.',
           f'Loop deliveries {s["deliveries"]}, autonomous {s["autonomous"]} ({num(s["autonomous_pct"], "%")}, target '
           f'{TARGETS["autonomous_pct"][1]}). Runs {s["runs"]}, wasted {s["wasted_runs"]} ({num(s["wasted_pct"], "%")}, '
           f'target {TARGETS["wasted_pct"][1]}). Human stops {s["human_stops"]}, {num(s["human_wait_h"], " h")} waited. '
           f'Claude runs with denials {s["runs_with_denials"]} of {s["claude_runs"]} ({num(s["denial_pct"], "%")}, '
           f'target {TARGETS["denial_pct"][1]}). '
           f'PRs merged {s["prs_merged"]} ({s["prs_merged_by_loop"]} by the loop). '
           f'Issues closed {s["issues_closed"]}, opened {s["issues_opened"]}. Retrospectives {s["retrospectives"]}.']
    explain = [d for d in data["issues"] if d["runs"] and needs_cause(d)]
    clean = [d for d in data["issues"] if d["runs"] and not needs_cause(d)]
    outside = [d for d in data["issues"] if not d["runs"]]
    out += ["", f"## Needs a cause ({len(explain)})"]
    for d in explain:
        out += ["", head(d)]
        for r in d["runs"]:
            # Runs that moved the item forward need only their gist; the others are what the notes explain.
            full = r["class"] != "forward"
            out.append(f'  {ROLES.get(r["agent"], "?")} {at(r["started"])} {num(r["minutes"], " min")} '
                       f'{r["class"]} {r["result"]} {r["url"] or ""}')
            out.append(f'    {r["summary"] if full else r["summary"][:160]}')
            out += [f'    denied: {"; ".join(r["denied"])}'] if r["denied"] else []
        ev = d.get("evidence", {})
        out += [f'  commit outside runs: {at(c["at"])} {c["sha"]} by {c["author"]} on #{c["pr"]}: {c["message"]}'
                for c in ev.get("commits", [])]
        out += [f'  by a person: {at(e["at"])} {e["by"]} {e["event"]} on #{e["item"]}' for e in ev.get("events", [])]
        out += [f'  CI #{w["pr"]}: {at(w["started"])} {w["workflow"]} {w["sha"]} {w["result"]} '
                f'{num(w["minutes"], " min")}' + (f' attempt {w["attempt"]}' if w["attempt"] > 1 else "")
                for w in ev.get("ci", [])]
        out += [f'  evidence error: {e}' for e in ev.get("errors", [])]
        out += [f'  retrospective: {p["agent"]} {at(p["created"])} {p["url"]}' for p in d["retrospectives"]]
    out += ["", f"## Went through cleanly ({len(clean)})", ""]
    for d in clean:
        denied = [x for r in d["runs"] for x in r["denied"]]
        out.append(head(d) + (f'; denied: {"; ".join(denied)}' if denied else ""))
    out += ["", f"## Outside the loop ({len(outside)})", ""] + [head(d) for d in outside]
    retro = data["retrospectives"]
    out += ["", f'## Retrospectives on the day ({len(retro["in_window"])})']
    for p in retro["in_window"]:
        out += ["", f'{p["agent"]} {at(p["created"])} on {", ".join(f"#{n}" for n in p["items"]) or "no item"} {p["url"]}',
                f'  {p["body"]}']
    out += [f"Board not read: {e}" for e in retro["errors"]]
    return "\n".join(out) + "\n"


CSS = """<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@600&family=IBM+Plex+Sans:wght@400;600&family=IBM+Plex+Mono&display=swap">
<style>
:root { --bg: #f6f7f8; --panel: #fff; --fg: #1d2329; --muted: #5d6874; --line: #dde2e7; --accent: #2f6f8f;
  --ok: #3f8a5a; --back: #b7791f; --fail: #c4473f; --head: "Bricolage Grotesque", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { --bg: #12161a; --panel: #1a2026; --fg: #e4e8ec;
  --muted: #9aa5b1; --line: #2c343c; --accent: #6fb3d2; --ok: #8fc29f; --back: #e0b462; --fail: #e8776f; color-scheme: dark } }
:root[data-theme="dark"] { --bg: #12161a; --panel: #1a2026; --fg: #e4e8ec; --muted: #9aa5b1; --line: #2c343c;
  --accent: #6fb3d2; --ok: #8fc29f; --back: #e0b462; --fail: #e8776f; color-scheme: dark }
body { background: var(--bg); color: var(--fg); font: 15px/1.55 "IBM Plex Sans", system-ui, sans-serif; }
a { color: var(--accent); } h1, h2, h3 { font-family: var(--head); margin: 0; text-wrap: balance; }
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; }
.label { text-transform: uppercase; letter-spacing: .07em; font-size: 12px; color: var(--muted); }
.box { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 14px 16px; }
.box p { margin: 6px 0; } .muted { color: var(--muted); }
.run { display: inline-block; font: 11px/1 var(--mono); padding: 4px 5px; margin: 1px; border-radius: 4px; color: var(--bg); text-decoration: none; }
.ok { background: var(--ok); } .back { background: var(--back); } .fail { background: var(--fail); } .wait { background: var(--muted); }
.wrap { max-width: 1080px; margin: 0 auto; padding-inline: 20px; padding-block: 32px 56px; display: grid; gap: 36px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.grid .num { font-size: 26px; } .num.hit { color: var(--ok); } .num.miss { color: var(--fail); }
section { display: grid; gap: 12px; min-width: 0; }
.scroll { overflow-x: auto; } table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
td.r { text-align: right; white-space: nowrap; }
"""
TONE = {"forward": "ok", "back": "back", "stop": "fail", "waste": "fail", "pending": "wait"}


def esc(value):
    return html.escape(str(value))


def span(m):
    return "–" if m is None else f"{m:.0f}m" if m < 90 else f"{m / 60:.1f}h" if m < 2880 else f"{m / 1440:.1f}d"


def spanh(h):
    return span(None if h is None else h * 60)


def pct(value):
    return "–" if value is None else f"{value:.0f}%"


def chips(runs):
    return "".join(f'<a class="run {TONE[r["class"]]}" href="{esc(r["url"])}" title="{esc(r["agent"])} · {esc(r["result"])} · '
                   f'{span(r["minutes"])}">{ROLES.get(r["agent"], "?")}</a>' for r in runs) or '<span class="label">outside the loop</span>'


def refs(repo, numbers):
    return " ".join(f'<a href="https://github.com/{repo}/issues/{n}">#{n}</a>' for n in numbers)


def figures(t):
    """The tiles as (value, label, detail, the field read against a target or None)."""
    goal = lambda field: f' · target {TARGETS[field][1]}'
    return [(f'{t["autonomous"]}/{t["deliveries"]}', "autonomous",
             f'{pct(t["autonomous_pct"])} of loop deliveries' + goal("autonomous_pct"), "autonomous_pct"),
            (t["wasted_runs"], "wasted runs", f'{pct(t["wasted_pct"])} of {t["runs"]} runs' + goal("wasted_pct"),
             "wasted_pct"),
            (t["human_stops"], "human stops", f'{spanh(t["human_wait_h"])} waited', None),
            (spanh(t["loop_cycle_h_median"]), "cycle", f'median without human wait · {spanh(t["cycle_h_median"])} with', None),
            (spanh(t["run_h_median"]), "run time", f'median per delivery · {spanh(t["run_h"])} all runs', None),
            (pct(t["denial_pct"]), "runs with denials",
             f'{t["runs_with_denials"]} of {t["claude_runs"]} Claude runs' + goal("denial_pct"), "denial_pct"),
            (t["prs_merged"], "PRs merged", f'+{t["additions"]:,} −{t["deletions"]:,} · {t["files"]} files', None),
            (t["issues_closed"], "issues closed", f'{t["issues_opened"]} opened', None),
            (t.get("backlog", "–"), "open queue", f'{t.get("backlog_unprepared", "–")} to prepare · '
             f'{t.get("backlog_prepared", "–")} prepared · {t.get("waiting_to_start", "–")} not started', None),
            (t.get("machines", "–"), "machines", f'{t.get("loops", "–")} loops · peak {t.get("peak_runs", "–")} parallel runs',
             None)]


def report(data):
    """The page follows references/report.md: header, figures, what to change, where extra runs went,
    each delivery, retrospectives."""
    repo, summary = data["repo"], data["summary"]
    out = ['<!doctype html><html lang="en"><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f'<title>Delivery report {data["day"]}</title>', CSS, "</style><main class=\"wrap\">",
           f'<header><div class="label">{esc(repo)} · {esc(data["day"])} · {esc(data["timezone"])}</div>'
           f'<h1>Delivery report</h1><p>{esc(summary["headline"])}</p></header><section class="grid">']
    tone = {True: " hit", False: " miss", None: ""}
    out += [f'<div class="box"><div class="label">{l}</div><div class="num{tone[on_target(f, summary.get(f))]}">{esc(v)}</div>'
            f'<div class="label">{esc(s)}</div></div>' for v, l, s, f in figures(summary)]
    out.append("</section><section><h2>What to change</h2>")
    out += [f'<div class="box"><div class="label">{esc(LEVERS[l["lever"]])}</div><h3>{esc(l["title"])}</h3>'
            f'<p>{esc(l["change"])}</p><div class="label">{esc(l.get("where", ""))} · {esc(l.get("cost", ""))} · '
            f'{esc(", ".join(l.get("causes", [])))} · {refs(repo, l.get("evidence", []))}</div></div>' for l in data["lessons"]]
    out.append('</section><section><h2>Where extra runs went</h2>')
    out += [f'<div class="box"><div class="label">{esc(f["cost"])} · {esc(f["class"])}</div><p>{esc(f["example"])}</p>'
            f'<p class="muted">{esc(f["cause"])}: {esc(f["mechanism"])} {esc(f["state"].capitalize())}'
            f'{esc(" by " + f["fixed_by"]) if f.get("fixed_by") else ""}.</p>'
            f'<div class="label">{refs(repo, f["items"])}</div></div>' for f in data["findings"]]
    out.append('</section><section><h2>Each delivery</h2><div class="label">P preparer · Q issue reviewer · I implementer · '
               'R reviewer · G integrator; green moved forward, amber sent back, red stopped for a person or wasted, grey still running. '
               'Autonomous: through the loop with no wasted run or human stop; reviewer send-backs allowed · '
               'Wasted: runs without an accepted outcome · Lead: filed to merged · Cycle: first run to delivery '
               'without human wait · Run time: run minutes summed</div>'
               '<div class="scroll box"><table><tr><th>Item</th><th>Runs</th><th>Autonomous</th><th>Wasted</th>'
               '<th>Reviews</th><th>Human stops</th><th>Lines</th><th>Lead</th><th>Cycle</th><th>Run time</th><th>Note</th></tr>')
    for d in sorted(data["issues"], key=lambda d: (not d["delivered"], d["autonomous"], -d["wasted_runs"], -d["attempts"])):
        extra = [f'<a href="{esc(p["url"])}">PR #{p["number"]}</a>' for p in d["prs"] if p["number"] != d["number"]]
        extra += [f'<a href="{esc(r["url"])}">retro</a>' for r in d["retrospectives"]]
        extra += ["in flight"] * (not d["delivered"]) + ["outside the loop"] * (d["delivered"] and not d["loop"])
        out.append(f'<tr><td><a href="{esc(d["url"])}">#{d["number"]}</a> {esc(d["title"])}<div class="label">{" · ".join(extra)}</div></td>'
                   f'<td>{chips(d["runs"])}</td><td class="r">{"✓" if d["autonomous"] else "–"}</td>'
                   f'<td class="r">{d["wasted_runs"] or "–"}</td><td class="r">{d["review_rounds"] or "–"}</td>'
                   f'<td class="r">{d["human_stops"] or "–"}</td><td class="r">{d["lines"]:,}</td>'
                   f'<td class="r">{spanh(d["lead_h"])}</td><td class="r" title="with human wait: {spanh(d["cycle_h"])}">'
                   f'{spanh(d["loop_cycle_h"])}</td><td class="r">{spanh(d["run_h"])}</td><td>{esc(d.get("note", ""))}</td></tr>')
    out.append("</table></div></section><section><h2>Retrospectives</h2>")
    retro, posts = data["retrospectives"], {r["url"]: r for r in data["retrospectives"]["in_window"]}
    groups = list(data["retrospective_groups"])
    rest = [u for u in posts if not any(u in g["posts"] for g in groups)]
    groups += [{"summary": "Not grouped.", "posts": rest}] * bool(rest)
    links = lambda urls: " · ".join(f'<a href="{esc(u)}">{esc(posts[u]["agent"])}</a>' for u in urls)
    out += [f'<div class="box"><div class="label">{len(g["posts"])} posts{esc(" · " + g["cause"]) if g.get("cause") else ""}</div>'
            f'<p>{esc(g["summary"])}</p><div class="label">{links(g["posts"])}</div></div>' for g in groups]
    out.append(f'<p>Boards not read: {esc(retro["errors"][0])}</p>' if retro["errors"] else "" if posts else "<p>None posted on this day.</p>")
    return "\n".join(out + ["</section></main>"])


FINDING = {"cause", "class", "mechanism", "state", "example", "items"}
LESSON = {"id", "lever", "title", "change"}
CHANGE = {"ref", "day", "title", "why"}


def check(notes):
    """Refuse notes the dataset would refuse, before anything is written."""
    findings, lessons = notes.get("findings", []), notes.get("lessons", [])
    problems = [f'{what} {entry.get(key)!r} lacks {", ".join(sorted(need - entry.keys()))}'
                for what, key, entries, need in (("finding", "cause", findings, FINDING), ("lesson", "id", lessons, LESSON))
                for entry in entries if need - entry.keys()]
    causes = [f.get("cause") for f in findings]
    problems += [f'cause {c!r} appears in more than one finding' for c in sorted(set(causes)) if causes.count(c) > 1]
    problems += [f'finding {f.get("cause")}: class {f.get("class")!r} is not one of {CLASSES}'
                for f in notes.get("findings", []) if f.get("class") not in CLASSES]
    problems += [f'finding {f.get("cause")}: state {f.get("state")!r} is not one of {STATES}'
                 for f in notes.get("findings", []) if f.get("state") not in STATES]
    problems += [f'finding {f.get("cause")!r}: cause must be a lowercase-hyphenated id'
                 for f in notes.get("findings", []) if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", f.get("cause") or "")]
    problems += [f'lesson {l.get("id")}: lever {l.get("lever")!r} is not one of {list(LEVERS)}'
                 for l in notes.get("lessons", []) if l.get("lever") not in LEVERS]
    problems += [f'lesson {l.get("id")!r}: id must be a lowercase-hyphenated id'
                 for l in notes.get("lessons", []) if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", l.get("id") or "")]
    problems += [f'lesson {l.get("id")}: state {l.get("state")!r} is not one of {LESSON_STATES}'
                 for l in lessons if l.get("state", "proposed") not in LESSON_STATES]
    problems += [f'lesson {l.get("id")}: state tracked or applied needs addressed_by'
                 for l in lessons if l.get("state") in ("tracked", "applied") and not l.get("addressed_by")]
    problems += [f'change {c.get("ref")!r} lacks {", ".join(sorted(CHANGE - c.keys()))}'
                 for c in notes.get("changes", []) if CHANGE - c.keys()]
    grouped = [u for g in notes.get("retrospectives", []) for u in g.get("posts", [])]
    problems += [f'retrospective {u} is in more than one group' for u in sorted(set(grouped)) if grouped.count(u) > 1]
    problems += [f'action {a!r}: a lesson in these notes that is not proposed' for a in notes.get("actions", [])
                 if any(l.get("id") == a and l.get("state", "proposed") != "proposed" for l in lessons)]
    if len(notes.get("actions", [])) > 5:
        problems.append("at most five actions")
    if problems:
        sys.exit("notes.json: " + "; ".join(problems))


def merge(data, notes):
    """The day's record: the summary carries the headline, each issue its note. See references/report.md."""
    check(notes)
    data["summary"]["headline"] = notes["headline"]
    data["findings"] = notes.get("findings", [])
    data["lessons"] = [l | {"state": l.get("state", "proposed")} for l in notes.get("lessons", [])]
    data["changes"], data["actions"] = notes.get("changes", []), notes.get("actions", [])
    known = {r["url"] for r in data["retrospectives"]["in_window"]}
    unknown = [u for g in notes.get("retrospectives", []) for u in g["posts"] if u not in known]
    if unknown:
        sys.exit("notes.json: retrospectives not posted on this day: " + ", ".join(unknown))
    data["retrospective_groups"] = notes.get("retrospectives", [])
    for issue in data["issues"]:
        issue["note"] = notes.get("items", {}).get(str(issue["number"]), "")
    return data


ITEM_REQUIRED = ["number", "title", "autonomous", "sequence"]
ITEM_DAYS = 14  # item detail is a recent snapshot; days, findings and causes stay for trends
RECENT_DAYS = 7  # the Recent days table shows the newest week; the charts plot every stored day


def collection(required, **fields):
    return {"version": 1, "schema": {"type": "object", "required": required, "properties": fields}}


TEXT, DAY = {"type": "string"}, {"type": "string", "minLength": 10, "maxLength": 10}
COUNT, HOURS, PERCENT = {"type": "integer", "minimum": 0}, {"type": ["number", "null"], "minimum": 0}, \
    {"type": ["number", "null"], "minimum": 0, "maximum": 100}
NUMBERS, IDS = {"type": "array", "items": {"type": "integer"}}, {"type": "array", "items": {"type": "string"}}
SCHEMAS = {
    "days": collection(
        ["day", "deliveries", "autonomous", "runs", "wasted_runs"], day=DAY, repo=TEXT, headline=TEXT,
        **dict.fromkeys(["deliveries", "autonomous", "runs", "wasted_runs", "human_stops", "claude_runs",
                         "runs_with_denials", "denials", "prs_merged", "prs_merged_by_loop", "additions",
                         "deletions", "files", "issues_closed", "issues_opened", "retrospectives", "backlog",
                         "backlog_unprepared", "backlog_prepared", "open_issues", "waiting_to_start", "machines",
                         "loops", "peak_runs"], COUNT),
        **dict.fromkeys(["autonomous_pct", "wasted_pct", "denial_pct"], PERCENT),
        **dict.fromkeys(["run_h", "human_wait_h", "human_stops_per_delivery", "review_rounds_per_delivery",
                         "lead_h_median", "cycle_h_median", "loop_cycle_h_median", "run_h_median"], HOURS)),
    "items": collection(["day", "items"], day=DAY, items={"type": "array", "items": {
        "type": "object", "required": ITEM_REQUIRED, "properties": {
            "number": COUNT, "title": TEXT, "autonomous": {"type": "boolean"}, "sequence": TEXT, "prs": NUMBERS,
            "note": TEXT,
            **dict.fromkeys(["attempts", "wasted_runs", "review_rounds", "human_stops", "denials", "runs_with_denials",
                             "lines"], COUNT),
            **dict.fromkeys(["human_wait_h", "lead_h", "cycle_h", "loop_cycle_h", "run_h"], HOURS)}}}),
    "findings": collection(
        ["day", "cause", "class", "example"], day=DAY, cause=TEXT, cost=TEXT, runs=COUNT, items=NUMBERS,
        example=TEXT, **{"class": {"type": "string", "enum": CLASSES}}),
    "causes": collection(
        ["class", "mechanism", "state"], mechanism=TEXT, fixed_by=TEXT,
        state={"type": "string", "enum": STATES}, **{"class": {"type": "string", "enum": CLASSES}}),
    "lessons": collection(
        ["day", "lever", "title", "change", "state"], day=DAY, title=TEXT, change=TEXT, where=TEXT, cost=TEXT,
        causes=IDS, evidence=NUMBERS, addressed_by=TEXT, addressed_as={"type": "string", "enum": list(ADDRESSED_AS)},
        lever={"type": "string", "enum": list(LEVERS)},
        state={"type": "string", "enum": LESSON_STATES}),
    "changes": collection(
        ["day", "title", "why"], day=DAY, title=TEXT, why=TEXT, url=TEXT, causes=IDS, lessons=IDS),
}
ITEM_FIELDS = ["number", "title", "autonomous", "sequence", "attempts", "wasted_runs", "review_rounds", "human_stops",
               "human_wait_h", "lead_h", "cycle_h", "loop_cycle_h", "run_h", "denials", "runs_with_denials", "lines",
               "note"]


def item(d):
    """A loop delivery, compact: zero, empty and derivable fields are left out."""
    value = {k: d[k] for k in ITEM_FIELDS if k in ITEM_REQUIRED or d.get(k) not in (0, "", None, False)}
    prs = [p["number"] for p in d["prs"] if p["number"] != d["number"]]
    return value | ({"prs": prs} if prs else {})


def records(data, schemas=False):
    """One update_data batch for the day: upserts keyed so that storing a day again replaces it. Items are one
    record per day and only the last ITEM_DAYS days are kept; the batch deletes older ones. A document keeps each
    collection's schema and checks every upsert against it, so schemas go out only when asked: for a new document,
    a missing collection, or a record the stored schema refuses."""
    day = data["day"]
    first = dt.date.fromisoformat(day)
    rows = {
        "days": [{"id": day, "value": data["summary"]}],
        "items": [{"id": day, "value": {"day": day, "items": [
            item(d) for d in data["issues"] if d["delivered"] and d["loop"]]}}],
        "findings": [{"id": f'{day}/{f["cause"]}', "value": {"day": day} | {
            k: f[k] for k in ("cause", "class", "cost", "runs", "items", "example") if k in f}} for f in data["findings"]],
        "causes": [{"id": f["cause"], "value": {k: f[k] for k in ("class", "mechanism", "state", "fixed_by") if f.get(k)}}
                   for f in data["findings"]],
        "lessons": [{"id": l["id"], "value": {"day": day} | {
            k: l[k] for k in ("lever", "title", "change", "where", "cost", "causes", "evidence", "state", "addressed_by",
                              "addressed_as")
            if k in l}} for l in data["lessons"]],
        "changes": [{"id": c["ref"], "value": {k: c[k] for k in ("day", "title", "why", "causes", "lessons") if k in c} | (
            {"url": c.get("url") or link(c["ref"])} if c.get("url") or link(c["ref"]) else {})}
                    for c in data.get("changes", [])]}
    expired = [(first - dt.timedelta(days=n)).isoformat() for n in range(ITEM_DAYS, ITEM_DAYS + 60)]
    return [{"collection": name} | ({"schema": SCHEMAS[name]} if schemas else {}) | {"upsert": rows[name]} |
            ({"deleteRecords": expired} if name == "items" else {}) for name in SCHEMAS if rows[name]]


def link(ref):
    """GitHub link for an owner/name#number reference; None for a bare commit."""
    found = re.fullmatch(r"([\w.-]+/[\w.-]+)#(\d+)", ref)
    return f"https://github.com/{found.group(1)}/issues/{found.group(2)}" if found else None


def values(collection):
    """Records as get_data returns them, or a plain list of {id, value}."""
    rows = collection.get("records", []) if isinstance(collection, dict) else collection or []
    return {r["id"]: r["value"] for r in rows}


def changelog(changes, limit=5):
    """The latest changes as list items: the day, the change linked, and why it was made."""
    blocks = []
    for ref, c in sorted(changes.items(), key=lambda kv: (kv[1]["day"], kv[0]), reverse=True)[:limit]:
        url = c.get("url") or link(ref)
        name = ref.split("/", 1)[1] if "/" in ref else ref
        day = dt.date.fromisoformat(c["day"]).strftime("%-d %b")
        title = {"text": c["title"], "marks": {"link": url} if url else {}}
        blocks.append({"type": "list-item", "inline": [{"text": f"{day}: ", "marks": {}}, title,
                                                       {"text": f" ({name}). {c['why']}", "marks": {}}]})
    return blocks


# A card's button opens a new Claude Code session in the desktop app with the prompt filled in, not sent; the prompt
# names the repository, since the link can only select a local folder. Prose parts take only http(s) links, so the
# link is a `button:` line, which Uberblick reads from the release after 0.4.3.
CLAUDE_CODE = "claude://code/new?q="
CHECK = "Check it against the repository: is it sound, what would it change, what are the risks, and is there a simpler way?"


def inline(text):
    """Text for a card's inline Markdown: one line, Markdown characters escaped outside `code` spans."""
    parts = re.split(r"(`[^`]*`)", " ".join(text.split()))
    return "".join(p if p.startswith("`") else re.sub(r"([\\*_\[\]])", r"\\\1", p) for p in parts)


def applied_card(lesson, status, ref, url):
    """A lesson being applied: the title and change struck through, the button gone, and a footer, not struck,
    naming the pull request or issue. A link whose text is the reference and whose target its GitHub URL shows as a
    pill."""
    return (f"label: {LEVERS[lesson['lever']]}\ntitle: ~~{inline(lesson['title'])}~~\n"
            f"footer: {status} in [{ref}]({url}).\n\n~~{inline(lesson['change'])}~~")


def tracked_card(lesson):
    ref = lesson["addressed_by"]
    return {"type": "card", "text": applied_card(lesson, ADDRESSED_AS[lesson.get("addressed_as", "planned")], ref,
                                                 link(ref) or f"https://github.com/{ref}")}


def discuss_link(data, lesson, doc=None):
    """A link that opens Claude Code with a prompt to discuss the lesson before changing anything: the repository,
    the change, its evidence, what to check, then a plan. If the outcome is to apply it, the prompt says how to mark
    the card and the lesson."""
    source = f"the delivery report for {data['repo']}" + (f" (Uberblick document {doc})" if doc else "")
    evidence = "; ".join(filter(None, [lesson.get("cost"),
                                       "causes: " + ", ".join(lesson["causes"]) if lesson.get("causes") else None,
                                       "items: " + ", ".join(f"#{n}" for n in lesson["evidence"])
                                       if lesson.get("evidence") else None]))
    # The lesson's own day, so a card stays the same until a day proposes the lesson again.
    prompt = (f"From {source}, evidence as of {lesson.get('day') or data['day']}:\n\n"
              f"Recommendation: {lesson['title'].rstrip('.')}.\nChange: {lesson['change']}\n"
              + (f"Where: {lesson['where']}\n" if lesson.get("where") else "")
              + (f"Evidence: {evidence}\n" if evidence else "")
              + f"\nLet's discuss this before changing anything. {CHECK} Then propose a plan and wait for my go-ahead.")
    where = f"Uberblick document {doc}" if doc else f"the delivery report document for {data['repo']} in Uberblick"
    prompt += ("\n\nIf we decide to apply it, mark the card once a pull request implements it or an issue plans it, so "
               f"the report shows it is being handled. In {where}, replace the card titled \"{inline(lesson['title'])}\" "
               "under Recommended Actions with this one (delete_block, then insert_block in the same place, since "
               "edit_block cannot change formatting). STATUS is Implemented or Planned, REF is owner/repo#number and "
               "URL its GitHub address; keeping the reference as the link text makes it show as a GitHub pill:\n\n"
               f"{applied_card(lesson, 'STATUS', 'REF', 'URL')}\n\n"
               "Then record it, so later reports keep the card struck through: read the record "
               f"\"{lesson['id']}\" of the collection \"lessons\" with get_data, set \"state\" to \"tracked\", "
               "\"addressed_by\" to REF and \"addressed_as\" to \"implemented\" or \"planned\", and upsert the whole "
               "value back with update_data.")
    return CLAUDE_CODE + quote(prompt, safe="")


def action_card(data, lesson, doc=None, button=True):
    """One proposed lesson as a card: the lever as its label, the title, where it lives, its cost, causes and
    evidence as the footer, the change as the body, and a button to discuss it in Claude Code."""
    repo = data["repo"]
    evidence = " ".join(f"[#{n}](https://github.com/{repo}/issues/{n})" for n in lesson.get("evidence", []))
    footer = " · ".join(filter(None, [inline(lesson.get("where") or ""), inline(lesson.get("cost") or ""),
                                      inline(", ".join(lesson.get("causes", []))), evidence]))
    return {"type": "card", "text": f"label: {LEVERS[lesson['lever']]}\ntitle: {inline(lesson['title'])}\n"
                                    + (f"footer: {footer}\n" if footer else "")
                                    + (f"button: [Discuss in Claude Code]({discuss_link(data, lesson, doc)})\n"
                                       if button else "")
                                    + f"\n{inline(lesson['change'])}"}


def document(dataset, data, doc=None, button=True, first=None):
    """The dataset document's generated sections as insert_block arguments: the Recommended Actions (up to five
    proposed lessons, as cards) and the Changelog (the latest changes). `cards` names each card's lesson and whether
    this day changed it, and `changelog_new` counts the changelog items this day added, so the document changes
    block by block. After a backfill, `first` is its first day: what the days from then on changed counts as new.
    Recent days is a table block bound to the data. See references/report.md."""
    today = {l["id"] for l in data["lessons"]} | {
        k for k, l in values(dataset.get("lessons")).items() if first and l.get("day", "") >= first}
    # The day's notes are newer than any registry read, before or after the day was stored.
    lessons = values(dataset.get("lessons")) | {l["id"]: l | {"day": data["day"]} for l in data["lessons"]}
    ranked = data.get("actions") or sorted((i for i, l in lessons.items() if l.get("state") == "proposed"),
                                           key=lambda i: lessons[i].get("day", ""), reverse=True)
    missing = [k for k in ranked if k not in lessons]
    if missing:
        sys.exit("dataset.json lacks the registry lessons the actions name: " + ", ".join(missing))
    actions = [{"type": "paragraph", "text": "Up to five changes not yet taken up, most runs saved first, then the "
                "ones being applied, struck through, until their pull request or issue is done."}]
    # Actions look back ITEM_DAYS: a lesson nobody proposed again in that window drops off.
    since = (dt.date.fromisoformat(data["day"]) - dt.timedelta(days=ITEM_DAYS - 1)).isoformat()
    current = [k for k in ranked if k in lessons and lessons[k].get("state", "proposed") == "proposed"
               and lessons[k].get("day", data["day"]) >= since][:5]
    # An open issue or PR addresses these: struck through, newest first, until it merges or closes.
    tracked = sorted((k for k, l in lessons.items() if l.get("state") == "tracked" and l.get("addressed_by")
                      and l.get("day", data["day"]) >= since), key=lambda k: (lessons[k].get("day", ""), k),
                     reverse=True)
    actions += [action_card(data, lessons[key] | {"id": key}, doc, button) for key in current]
    actions += [tracked_card(lessons[key]) for key in tracked]
    changes = values(dataset.get("changes")) | {c["ref"]: c for c in data.get("changes", [])}
    latest = sorted(changes, key=lambda ref: (changes[ref]["day"], ref), reverse=True)[:5]
    return {"actions": actions, "changelog": changelog(changes),
            "cards": [{"lesson": key, "title": inline(lessons[key]["title"]), "changed": key in today}
                      for key in current]
                     + [{"lesson": key, "title": f"~~{inline(lessons[key]['title'])}~~", "changed": key in today,
                         "struck": True} for key in tracked],
            "changelog_new": sum(ref in {c["ref"] for c in data.get("changes", [])}
                                 or bool(first and changes[ref]["day"] >= first) for ref in latest)}


KPIS = [("Autonomous deliveries", "up", "autonomous_pct", "Loop deliveries the integrator merged with no wasted run, "
         "no stop and no action-needed notice; a reviewer send-back still counts."),
        ("Wasted runs", "down", "wasted_pct", "Runs started on the day that ended without an accepted outcome."),
        ("Human stops", "down", None, "Action-needed notices on loop deliveries, and the hours from each to the next run on "
         "the item."),
        ("Cycle", "down", None, "First run to delivery, without the human wait."),
        ("Run time", "down", None, "Run minutes summed per delivery, the touch time."),
        ("Runs with denials", "down", "denial_pct", "Claude runs on the day with a permission denial.")]


def chart(mapping):
    """A chart block: a version-1 line or table mapping bound to a collection of the document's data."""
    return {"type": "chart", "text": json.dumps(mapping, indent=1)}


def column(field, label, fmt="number", **extra):
    return {"field": field, "label": label, "format": fmt} | extra


def create_document(data, button=True):
    """create_doc arguments for a new dataset document, laid out as references/report.md describes: intro, KPIs,
    charts and a Recent days table bound to `days`, this day's Recommended Actions, and the Changelog."""
    repo, sections = data["repo"], document({}, data, button=button)
    percent = {"unit": "%", "decimals": 0}
    hours = {"unit": "h", "decimals": 1}
    blocks = [
        {"type": "paragraph", "text": f"The ub-agents loop prepares, implements, reviews and integrates issues in "
         f"{repo} on its own and asks a person only for a real decision. The delivery report measures how close each "
         "day came: how many deliveries needed no wasted run and no person, where the extra runs went, and the few "
         "changes that would have saved them."},
        {"type": "paragraph", "text": "The ub-agents-deliver-report skill (npx skills@latest add uberblick-ai/skills) "
         "stores one record per day in this document's data. The charts and tables below follow that data; the "
         "Recommended Actions are rewritten after each stored day."},
        {"type": "heading", "level": 2, "text": "KPIs"},
        {"type": "table", "text": "| KPI | Goal | Target | Definition |\n| --- | --- | --- | --- |\n" + "\n".join(
            f"| {kpi} | {goal} | {TARGETS[field][1] if field else ''} | {definition} |"
            for kpi, goal, field, definition in KPIS)},
        {"type": "heading", "level": 2, "text": "Data"},
        chart({"version": 1, "type": "line", "collection": "days", "title": "Autonomy and waste",
               "x": {"field": "day", "type": "date", "label": "Day"},
               "y": [{"field": "autonomous_pct", "label": "Autonomous deliveries", "unit": "%"},
                     {"field": "wasted_pct", "label": "Wasted runs", "unit": "%"},
                     {"field": "denial_pct", "label": "Runs with denials", "unit": "%"}]}),
        chart({"version": 1, "type": "line", "collection": "days", "title": "Human stops and the wait for them",
               "x": {"field": "day", "type": "date", "label": "Day"},
               "y": [{"field": "human_stops", "label": "Human stops"},
                     {"field": "human_wait_h", "label": "Hours waited", "unit": "h"}]}),
        chart({"version": 1, "type": "line", "collection": "days", "title": "Cycle and run time per delivery",
               "x": {"field": "day", "type": "date", "label": "Day"},
               "y": [{"field": "loop_cycle_h_median", "label": "Cycle, median", "unit": "h"},
                     {"field": "run_h_median", "label": "Run time, median", "unit": "h"}]}),
        chart({"version": 1, "type": "line", "collection": "days", "title": "Issues in, deliveries out and the open queue",
               "x": {"field": "day", "type": "date", "label": "Day"},
               "y": [{"field": "issues_opened", "label": "Issues opened"},
                     {"field": "deliveries", "label": "Loop deliveries"},
                     {"field": "backlog", "label": "Actionable queue at day end"},
                     {"field": "waiting_to_start", "label": "Waiting to start at day end"}]}),
        {"type": "paragraph", "text": "When issues opened stay above loop deliveries, open work piles up: in the actionable "
         "queue the loop works through, or among issues waiting for a person to start them (no workflow label, or "
         "parked). Parents are left out; their work counts in their sub-issues."},
        chart({"version": 1, "type": "line", "collection": "days", "title": "Capacity",
               "x": {"field": "day", "type": "date", "label": "Day"},
               "y": [{"field": "machines", "label": "Machines"}, {"field": "loops", "label": "Loops"},
                     {"field": "peak_runs", "label": "Peak parallel runs"}]}),
        chart({"version": 1, "type": "table", "collection": "days", "title": "Recent days",
               "columns": [column("day", "Day", "date"), column("deliveries", "Deliveries"),
                           column("autonomous", "Autonomous"), column("wasted_pct", "Wasted runs", **percent),
                           column("human_stops", "Human stops"), column("loop_cycle_h_median", "Cycle", **hours),
                           column("run_h_median", "Run time", **hours), column("denial_pct", "Denials", **percent),
                           column("backlog", "Actionable queue"), column("waiting_to_start", "Waiting to start"),
                           column("open_issues", "Open issues"), column("machines", "Machines")],
               "sort": {"field": "day", "direction": "desc"}, "limit": RECENT_DAYS}),
        {"type": "heading", "level": 2, "text": "Recommended Actions"},
        *sections["actions"],
        {"type": "heading", "level": 2, "text": "Changelog"},
        *sections["changelog"],
    ]
    return {"title": f"Delivery report: {repo}",
            "description": f"Daily KPIs, causes and actions of the ub-agents loop in {repo}, stored by the "
                           "ub-agents-deliver-report skill.",
            "blocks": blocks}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    m = commands.add_parser("missing", help="the days to report, one a line: every day after the newest stored one")
    m.add_argument("days", help="the document's days collection as get_data returned it; a missing file means none")
    c = commands.add_parser("collect")
    c.add_argument("--repo", required=True)
    c.add_argument("--day", help="calendar day, YYYY-MM-DD, UTC (default yesterday)")
    r = commands.add_parser("render")
    r.add_argument("data"), r.add_argument("notes"), r.add_argument("out")
    r.add_argument("--no-open", action="store_true", help="do not open the report in the default browser")
    q = commands.add_parser("queue", help="only the open-queue figures for a day: issue lists and events, no run records")
    q.add_argument("--repo", required=True)
    q.add_argument("--day", help="calendar day, YYYY-MM-DD, UTC (default yesterday)")
    g = commands.add_parser("digest", help="the day in a few lines per item, to read before data.json")
    g.add_argument("data", help="data.json written by collect, or report.json")
    s = commands.add_parser("records")
    s.add_argument("report", help="report.json written by render")
    s.add_argument("--schemas", action="store_true",
                   help="send each collection's schema: for a new document, a missing collection or a refused record")
    d = commands.add_parser("document")
    d.add_argument("dataset", help="the registry lessons the actions name that the notes leave out, as read with get_data")
    d.add_argument("report", help="report.json written by render")
    d.add_argument("--doc", help="the dataset document's uuid, named in each action card's prompt")
    d.add_argument("--since", help="the first day of a backfill: changes and lessons from then on count as new")
    d.add_argument("--no-button", action="store_true", help="cards without the Claude Code button, for Uberblick 0.4.3")
    n = commands.add_parser("create")
    n.add_argument("report", help="report.json written by render")
    n.add_argument("--no-button", action="store_true", help="cards without the Claude Code button, for Uberblick 0.4.3")
    args = parser.parse_args()
    if args.command == "missing":
        path = Path(args.days)
        try:
            stored = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        except ValueError as e:
            sys.exit(f"{path}: {e}")
        print("\n".join(missing(stored, day_window(None)[0])))
    elif args.command == "collect":
        print(json.dumps(collect(args.repo, *day_window(args.day)), indent=1))
    elif args.command == "queue":
        day, _, since, until = day_window(args.day)
        agents, _ = config_of(base64.b64decode(gh(f"repos/{args.repo}/contents/ub-agents.yaml")["content"]).decode())
        rows = list(pages(f"repos/{args.repo}/issues", state="all", since=stamp(since)))
        print(json.dumps({"day": day.isoformat()} | queue(args.repo, until, rows, agents)))
    elif args.command == "digest":
        sys.stdout.write(digest(json.loads(Path(args.data).read_text(encoding="utf-8"))))
    elif args.command == "records":
        # Compact: the agent passes this batch on verbatim, so every byte is read and written again.
        print(json.dumps(records(json.loads(Path(args.report).read_text(encoding="utf-8")), args.schemas), separators=(",", ":"),
                         ensure_ascii=False))
    elif args.command == "create":
        print(json.dumps(create_document(json.loads(Path(args.report).read_text(encoding="utf-8")), not args.no_button), indent=1,
                         ensure_ascii=False))
    elif args.command == "document":
        print(json.dumps(document(json.loads(Path(args.dataset).read_text(encoding="utf-8")), json.loads(Path(args.report).read_text(encoding="utf-8")),
                                  args.doc, not args.no_button, args.since), separators=(",", ":"), ensure_ascii=False))
    else:
        data = merge(json.loads(Path(args.data).read_text(encoding="utf-8")), json.loads(Path(args.notes).read_text(encoding="utf-8")))
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        page = out / "report.html"
        page.write_text(report(data), encoding="utf-8")
        (out / "report.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
        print(page.resolve())
        if not args.no_open:
            webbrowser.open(page.resolve().as_uri())


if __name__ == "__main__":
    main()
