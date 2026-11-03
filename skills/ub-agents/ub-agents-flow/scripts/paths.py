#!/usr/bin/env python3
"""The paths items took through the ub-agents loop, counted per phase, so a drawing's play scenarios follow the
most common ones. Reads GitHub only; standard library and `gh`.

    paths.py --repo OWNER/NAME [--days 30] [--top 5] [--json]

An item is an issue with the pull requests that close it or that its runs handed off to, or a pull request with no
issue, such as a bot's. Its path is the outcomes its agents reported, in order, read from the coordination records
the launcher posts as comments. Only accepted outcomes count, and a blocked report counts as `blocked`; a run that
reported nothing or failed changes no route and is left out, as is a repeat of the step before it. Items count when
they finished (merged or closed) within the window; items still open are counted, not tallied.

Phases split by the config's `kind`: agents with `kind: issue` make the issue phase, every other agent the PR phase.
Each phase's paths are tallied separately, with the item's end (`merged`, `closed`) on the last phase it reached.
"""
import argparse
import base64
import datetime as dt
import json
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
# Every record version (ub-agent:v1 to ub-agents:v4) carries the same JSON record.
RECORD = re.compile(r"<!-- ub-agents?:v\d+ -->.*?```json\n(.*?)\n```", re.S)
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)


def gh(*args):
    try:
        done = subprocess.run(["gh", "api", *args], capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("gh is not installed; install the GitHub CLI and run gh auth login") from None
    if done.returncode:
        raise RuntimeError(((done.stderr or done.stdout).strip().splitlines() or ["gh api failed"])[-1])
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


def kinds_of(config):
    """Each agent's kind from ub-agents.yaml, `any` when unset; a line parser, enough for the launcher's layout."""
    kinds, agent, section = {}, None, None
    for line in config.splitlines():
        line = line.split(" #")[0].rstrip()
        if found := re.match(r"^([\w-]+):", line):
            section = found.group(1)
        elif section != "agents":
            continue
        elif found := re.match(r"^  ([\w-]+):\s*$", line):
            agent = found.group(1)
            kinds[agent] = "any"
        elif agent and (found := re.match(r"^    kind:\s*['\"]?(\w+)", line)):
            kinds[agent] = found.group(1)
    return kinds


def records_of(comments):
    """The coordination records in an item's comments, from trusted accounts only."""
    out = []
    for comment in comments:
        if comment.get("author_association") not in TRUSTED:
            continue
        if found := RECORD.search(comment.get("body") or ""):
            try:
                out.append(json.loads(found.group(1)))
            except json.JSONDecodeError:
                continue
    return out


def step_of(record):
    """One step of a path, `agent outcome`, or None for a record that changes no route."""
    if record.get("kind") != "outcome" or not record.get("agent"):
        return None
    if record.get("status") == "success" and record.get("accepted") and record.get("outcome"):
        return f"{record['agent']} {record['outcome']}"
    if record.get("status") == "blocked":
        return f"{record['agent']} blocked"
    return None


def groups_of(items):
    """Issue number -> the numbers of the item's issue and pull requests; a pull request with no issue is its own."""
    groups, claimed = {}, set()
    for number, item in items.items():
        if item["row"].get("pull_request"):
            continue
        linked = {int(r["handoff"]) for r in item["records"] if str(r.get("handoff") or "").isdigit()}
        groups[number] = {number} | linked
        claimed |= linked
    for number, item in items.items():
        row = item["row"]
        if not row.get("pull_request") or number in claimed:
            continue
        targets = [int(n) for n in CLOSES.findall(row.get("body") or "")
                   if int(n) in groups]
        targets += [int(r["assignment"]) for r in item["records"]
                    if str(r.get("assignment") or "").isdigit() and int(r["assignment"]) in groups]
        if targets:
            groups[targets[0]].add(number)
        else:
            groups[number] = {number}
    return groups


def path_of(members, items, kinds):
    """An item's steps per phase, in order, with consecutive repeats dropped, and how it ended."""
    records = sorted((r for n in members if n in items for r in items[n]["records"]), key=lambda r: r.get("created") or "")
    steps = []
    for record in records:
        step = step_of(record)
        if step and (not steps or steps[-1] != step):
            steps.append(step)
    rows = [items[n]["row"] for n in members if n in items]
    merged = [r for r in rows if (r.get("pull_request") or {}).get("merged_at")]
    end = "merged" if merged else "closed" if all(r.get("state") == "closed" for r in rows) else "open"
    finished = max((r["pull_request"]["merged_at"] for r in merged), default=None) or \
        max((r.get("closed_at") or "" for r in rows), default="") or None
    issue = [s for s in steps if kinds.get(s.split()[0]) == "issue"]
    pr = [s for s in steps if kinds.get(s.split()[0]) != "issue"]
    return {"issue": issue, "pr": pr, "end": end, "finished": finished if end != "open" else None}


def entry_of(members, items):
    """How the item entered: an issue, or a pull request with no issue, named by its author when a bot opened it."""
    head = items[min(members)]["row"]
    if not head.get("pull_request"):
        return "issue"
    user = head.get("user") or {}
    return f"pull request by {user.get('login')}" if user.get("type") == "Bot" else "pull request"


def tally(items, kinds, since, top):
    """Count the finished items' entries and each phase's paths, most common first."""
    groups = groups_of(items)
    finished, still_open = [], 0
    for key, members in sorted(groups.items()):
        path = path_of(members, items, kinds)
        if not path["issue"] and not path["pr"]:
            continue  # no loop run on it
        if path["end"] == "open":
            still_open += 1
        elif when(path["finished"]) >= since:
            finished.append((key, entry_of(members, items), path))
    total = len(finished)
    entries = Counter(entry for _, entry, _ in finished)
    out = {"items": total, "open": still_open,
           "entries": [{"entry": e, "count": c, "share": share(c, total)} for e, c in entries.most_common()],
           "phases": {}}
    for phase in ("issue", "pr"):
        counts, examples = Counter(), {}
        for key, _, path in finished:
            steps = path[phase]
            if not steps:
                continue
            last = phase == "pr" or not path["pr"]
            route = tuple(steps) + ((path["end"],) if last else ())
            counts[route] += 1
            examples.setdefault(route, []).append(key)
        reached = sum(counts.values())
        out["phases"][phase] = [{"path": list(route), "count": c, "share": share(c, reached),
                                 "examples": sorted(examples[route], reverse=True)[:3]}
                                for route, c in counts.most_common(top)]
        out["phases"][phase + "_items"] = reached
    return out


def share(part, whole):
    return round(100 * part / whole, 1) if whole else None


def collect(repo, days, top):
    until = dt.datetime.now(dt.timezone.utc)
    since = until - dt.timedelta(days=days)
    config = base64.b64decode(gh(f"repos/{repo}/contents/ub-agents.yaml")["content"]).decode()
    kinds = kinds_of(config)
    if not kinds:
        raise RuntimeError(f"{repo}/ub-agents.yaml names no agents")
    # An item that finished in the window was updated in it; older updates cannot finish inside it.
    rows = list(pages(f"repos/{repo}/issues", state="all", since=since.strftime("%Y-%m-%dT%H:%M:%SZ")))

    def read(row):
        comments = pages(f"repos/{repo}/issues/{row['number']}/comments") if row.get("comments") else []
        return row["number"], {"row": row, "records": records_of(comments)}
    with ThreadPoolExecutor(max_workers=8) as pool:
        items = dict(pool.map(read, rows))
    return {"repository": repo, "since": since.date().isoformat(), "until": until.date().isoformat(), "days": days,
            "kinds": kinds, **tally(items, kinds, since, top)}


def text(data):
    lines = [f"{data['repository']}: {data['items']} items finished from {data['since']} to {data['until']}, "
             f"{data['open']} still open.",
             "Entries: " + (", ".join(f"{e['entry']} {e['count']} ({e['share']}%)" for e in data["entries"]) or "none")]
    for phase, name in (("issue", "Issue phase"), ("pr", "PR phase")):
        lines += ["", f"{name} ({data['phases'][phase + '_items']} items):"]
        for n, path in enumerate(data["phases"][phase], 1):
            refs = " ".join(f"#{e}" for e in path["examples"])
            lines.append(f"{n}. {path['count']}x ({path['share']}%) " + " > ".join(path["path"]) + f"  {refs}")
        if not data["phases"][phase]:
            lines.append("none")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo", required=True, help="OWNER/NAME of the repository the loop runs on")
    p.add_argument("--days", type=int, default=30, help="the window, in days back from now (default 30)")
    p.add_argument("--top", type=int, default=5, help="paths to keep per phase (default 5)")
    p.add_argument("--json", action="store_true", help="print JSON instead of the summary")
    args = p.parse_args(argv)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", args.repo) or args.days < 1 or args.top < 1:
        print("error: --repo must be OWNER/NAME, --days and --top at least 1", file=sys.stderr)
        return 2
    try:
        data = collect(args.repo, args.days, args.top)
    except (RuntimeError, KeyError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2) if args.json else text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
