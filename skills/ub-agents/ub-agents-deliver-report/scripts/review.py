#!/usr/bin/env python3
"""Facts, the page and the dataset records for the ub-agents-deliver-report skill. Reads GitHub only;
standard library and `gh`.

    review.py collect --repo OWNER/NAME [--day YYYY-MM-DD] > data.json
    review.py render data.json notes.json OUT_DIR [--no-open]   # writes report.html and report.json
    review.py records report.json > operations.json             # update_data operations for the day
    review.py document dataset.json report.json > sections.json # the dataset document's generated sections

The day runs from local midnight to local midnight; the default is yesterday. Only runs that started
before the day ended count, so a day reads the same whenever it is collected.
Works on any repository that runs ub-agents (https://agents.uberblick.ai): roles, triggers and outcomes
come from the repository's ub-agents.yaml, and ROLES maps the common role names to a letter.
"""

import argparse
import base64
import datetime as dt
import html
import json
import re
import statistics
import subprocess
import sys
import webbrowser
from pathlib import Path

SCHEMA = "ub-agents-deliver-report/1"
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
RECORD = re.compile(r"<!-- ub-agents:v3 -->.*?```json\n(.*?)\n```", re.S)
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
    """Local midnight to local midnight for the given day; yesterday when none is given."""
    zone = dt.datetime.now().astimezone().tzinfo
    day = dt.date.fromisoformat(text) if text else dt.datetime.now(zone).date() - dt.timedelta(days=1)
    since = dt.datetime.combine(day, dt.time.min, zone)
    return day, zone, since, since + dt.timedelta(days=1)


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
                     "summary": public(out.get("summary") or lease.get("summary"), 400),
                     "url": out.get("url") or lease.get("url"),
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


def collect(repo, day, zone, since, until):
    inside = lambda text: bool(text) and since <= when(text) < until
    before = lambda text: bool(text) and when(text) < until
    agents, stop = config_of(base64.b64decode(gh(f"repos/{repo}/contents/ub-agents.yaml")["content"]).decode())
    kind = classifier(agents, stop)

    items = {}
    for row in pages(f"repos/{repo}/issues", state="all", since=stamp(since)):
        records, notices = [], []
        for c in pages(f"repos/{repo}/issues/{row['number']}/comments"):
            if c["author_association"] not in TRUSTED:
                continue
            if found := RECORD.search(c["body"] or ""):
                records.append(json.loads(found.group(1)) | {"url": c["html_url"]})
            if (c["body"] or "").startswith("<!-- ub-agents:action-needed"):
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
                pr = gh(f"repos/{repo}/pulls/{n}")
                pulls.append({"number": n, "url": pr["html_url"], "merged": pr["merged_at"],
                              "additions": pr["additions"], "deletions": pr["deletions"], "files": pr["changed_files"],
                              "by_loop": inside(pr["merged_at"]) and any(
                                  l == "G" and r["result"] == "merged" for l, r in zip(letters, runs))})
        merged = [p["merged"] for p in pulls if inside(p["merged"])]
        closed = "pull_request" not in head and inside(head.get("closed_at"))
        delivered = bool(merged) or closed
        if not delivered and not any(inside(r["started"]) for r in runs):
            continue
        done = max(merged) if merged else head.get("closed_at") if closed else None
        stops = sorted(t for n in members for t in items[n]["notices"] if before(t))
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

    window = [r for d in issues for r in d["runs"] if inside(r["started"])]
    claude = [r for r in window if (r["runtime"] or "").startswith("claude")] or window
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
            "retrospectives": len(retrospectives)},
        "retrospectives": {"errors": errors, "in_window": retrospectives},
        "issues": issues}


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
.grid .num { font-size: 26px; } section { display: grid; gap: 12px; min-width: 0; }
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
    return [(f'{t["autonomous"]}/{t["deliveries"]}', "autonomous", f'{pct(t["autonomous_pct"])} of loop deliveries'),
            (t["wasted_runs"], "wasted runs", f'{pct(t["wasted_pct"])} of {t["runs"]} runs'),
            (t["human_stops"], "human stops", f'{spanh(t["human_wait_h"])} waited'),
            (spanh(t["loop_cycle_h_median"]), "cycle", f'median without human wait · {spanh(t["cycle_h_median"])} with'),
            (spanh(t["run_h_median"]), "run time", f'median per delivery · {spanh(t["run_h"])} all runs'),
            (pct(t["denial_pct"]), "runs with denials", f'{t["runs_with_denials"]} of {t["claude_runs"]} Claude runs'),
            (t["prs_merged"], "PRs merged", f'+{t["additions"]:,} −{t["deletions"]:,} · {t["files"]} files'),
            (t["issues_closed"], "issues closed", f'{t["issues_opened"]} opened')]


def report(data):
    """The page follows references/report.md: header, figures, what to change, where extra runs went,
    each delivery, retrospectives."""
    repo, summary = data["repo"], data["summary"]
    out = [f'<title>Delivery report {data["day"]}</title>', CSS, "</style><main class=\"wrap\">",
           f'<header><div class="label">{esc(repo)} · {esc(data["day"])} · {esc(data["timezone"])}</div>'
           f'<h1>Delivery report</h1><p>{esc(summary["headline"])}</p></header><section class="grid">']
    out += [f'<div class="box"><div class="label">{l}</div><div class="num">{esc(v)}</div><div class="label">{esc(s)}</div></div>'
            for v, l, s in figures(summary)]
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
                         "deletions", "files", "issues_closed", "issues_opened", "retrospectives"], COUNT),
        **dict.fromkeys(["autonomous_pct", "wasted_pct", "denial_pct"], PERCENT),
        **dict.fromkeys(["run_h", "human_wait_h", "human_stops_per_delivery", "review_rounds_per_delivery",
                         "lead_h_median", "cycle_h_median", "loop_cycle_h_median", "run_h_median"], HOURS)),
    "items": collection(
        ["day", "number", "title", "loop", "autonomous", "sequence"], day=DAY, number=COUNT, title=TEXT, url=TEXT,
        loop={"type": "boolean"}, autonomous={"type": "boolean"}, sequence=TEXT, prs=NUMBERS, note=TEXT,
        **dict.fromkeys(["attempts", "wasted_runs", "review_rounds", "human_stops", "denials", "runs_with_denials",
                         "lines"], COUNT),
        **dict.fromkeys(["human_wait_h", "lead_h", "cycle_h", "loop_cycle_h", "run_h"], HOURS)),
    "findings": collection(
        ["day", "cause", "class", "example"], day=DAY, cause=TEXT, cost=TEXT, runs=COUNT, items=NUMBERS,
        example=TEXT, **{"class": {"type": "string", "enum": CLASSES}}),
    "causes": collection(
        ["class", "mechanism", "state"], mechanism=TEXT, fixed_by=TEXT,
        state={"type": "string", "enum": STATES}, **{"class": {"type": "string", "enum": CLASSES}}),
    "lessons": collection(
        ["day", "lever", "title", "change", "state"], day=DAY, title=TEXT, change=TEXT, where=TEXT, cost=TEXT,
        causes=IDS, evidence=NUMBERS, addressed_by=TEXT, lever={"type": "string", "enum": list(LEVERS)},
        state={"type": "string", "enum": LESSON_STATES}),
    "changes": collection(
        ["day", "title", "why"], day=DAY, title=TEXT, why=TEXT, url=TEXT, causes=IDS, lessons=IDS),
}
ITEM_FIELDS = ["day", "number", "title", "url", "loop", "autonomous", "sequence", "attempts", "wasted_runs",
               "review_rounds", "human_stops", "human_wait_h", "lead_h", "cycle_h", "loop_cycle_h", "run_h",
               "denials", "runs_with_denials", "lines", "note"]


def records(data):
    """One update_data batch for the day: upserts keyed so that storing a day again replaces it."""
    day = data["day"]
    rows = {
        "days": [{"id": day, "value": data["summary"]}],
        "items": [{"id": str(d["number"]), "value": {k: d[k] for k in ITEM_FIELDS} | {
            "prs": [p["number"] for p in d["prs"] if p["number"] != d["number"]]}}
            for d in data["issues"] if d["delivered"] and d["runs"]],
        "findings": [{"id": f'{day}/{f["cause"]}', "value": {"day": day} | {
            k: f[k] for k in ("cause", "class", "cost", "runs", "items", "example") if k in f}} for f in data["findings"]],
        "causes": [{"id": f["cause"], "value": {k: f[k] for k in ("class", "mechanism", "state", "fixed_by") if f.get(k)}}
                   for f in data["findings"]],
        "lessons": [{"id": l["id"], "value": {"day": day} | {
            k: l[k] for k in ("lever", "title", "change", "where", "cost", "causes", "evidence", "state", "addressed_by")
            if k in l}} for l in data["lessons"]],
        "changes": [{"id": c["ref"], "value": {k: c[k] for k in ("day", "title", "why", "url", "causes", "lessons") if k in c}}
                    for c in data.get("changes", [])]}
    return [{"collection": name, "schema": SCHEMAS[name], "upsert": rows[name]} for name in SCHEMAS if rows[name]]


def link(ref):
    """GitHub link for an owner/name#number reference; None for a bare commit."""
    found = re.fullmatch(r"([\w.-]+/[\w.-]+)#(\d+)", ref)
    return f"https://github.com/{found.group(1)}/issues/{found.group(2)}" if found else None


def values(collection):
    """Records as get_data returns them, or a plain list of {id, value}."""
    rows = collection.get("records", []) if isinstance(collection, dict) else collection or []
    return {r["id"]: r["value"] for r in rows}


def document(dataset, data):
    """The dataset document's generated sections as insert_block arguments: recent days, the top actions
    and the changelog. See references/report.md."""
    repo, days = data["repo"], values(dataset.get("days"))
    lessons = {l["id"]: l for l in data["lessons"]} | values(dataset.get("lessons"))
    changes = values(dataset.get("changes")) | {c["ref"]: c for c in data.get("changes", [])}
    pc = lambda v: "–" if v is None else f"{v:.0f}%"
    hr = lambda v: "–" if v is None else f"{v:.1f} h"
    rows = ["| Day | Deliveries | Autonomous | Wasted runs | Human stops | Cycle | Run time | Runs with denials |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    rows += [f'| {d} | {v["deliveries"]} | {v["autonomous"]} ({pc(v.get("autonomous_pct"))}) | '
             f'{v["wasted_runs"]} ({pc(v.get("wasted_pct"))}) | {v.get("human_stops", 0)}, {hr(v.get("human_wait_h"))} waited | '
             f'{hr(v.get("loop_cycle_h_median"))} | {hr(v.get("run_h_median"))} | {pc(v.get("denial_pct"))} |'
             for d, v in sorted(days.items())[-7:]]
    ranked = data.get("actions") or sorted((i for i, l in lessons.items() if l.get("state") == "proposed"),
                                           key=lambda i: lessons[i].get("day", ""), reverse=True)
    actions = [{"type": "paragraph", "text": "The most valuable changes not yet taken up, most runs saved first. An action "
                "leaves this list once an issue or PR addresses it."}]
    for n, key in enumerate([k for k in ranked if lessons.get(k, {}).get("state", "proposed") == "proposed"][:5], 1):
        l = lessons[key]
        meta = " · ".join(filter(None, [LEVERS[l["lever"]], l.get("where"), l.get("cost"),
                                        "causes: " + ", ".join(l.get("causes", [])) if l.get("causes") else None]))
        evidence = [{"text": f" · evidence: ", "marks": {}}] * bool(l.get("evidence"))
        for i, number in enumerate(l.get("evidence", [])):
            evidence += [{"text": ", " * bool(i), "marks": {}}] * bool(i)
            evidence.append({"text": f"#{number}", "marks": {"link": f"https://github.com/{repo}/issues/{number}"}})
        actions += [{"type": "heading", "level": 3, "text": f'{n}. {l["title"]}'},
                    {"type": "paragraph", "text": l["change"]},
                    {"type": "paragraph", "inline": [{"text": meta, "marks": {"italic": True}}] + evidence}]
    log = ["| Day | Change | Why |", "| --- | --- | --- |"]
    for ref, c in sorted(changes.items(), key=lambda kv: kv[1]["day"], reverse=True)[:5]:
        url = c.get("url") or link(ref)
        title, why = (c[k].replace("|", "\\|") for k in ("title", "why"))
        log.append(f'| {c["day"]} | {f"[{title}]({url})" if url else title} ({ref}) | {why} |')
    return {"recent": [{"type": "table", "text": "\n".join(rows)}], "actions": actions,
            "changelog": [{"type": "table", "text": "\n".join(log)}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("collect")
    c.add_argument("--repo", required=True)
    c.add_argument("--day", help="calendar day, YYYY-MM-DD, local time (default yesterday)")
    r = commands.add_parser("render")
    r.add_argument("data"), r.add_argument("notes"), r.add_argument("out")
    r.add_argument("--no-open", action="store_true", help="do not open the report in the default browser")
    s = commands.add_parser("records")
    s.add_argument("report", help="report.json written by render")
    d = commands.add_parser("document")
    d.add_argument("dataset", help="days, lessons and changes as read with get_data")
    d.add_argument("report", help="report.json written by render")
    args = parser.parse_args()
    if args.command == "collect":
        print(json.dumps(collect(args.repo, *day_window(args.day)), indent=1))
    elif args.command == "records":
        print(json.dumps(records(json.loads(Path(args.report).read_text())), indent=1))
    elif args.command == "document":
        print(json.dumps(document(json.loads(Path(args.dataset).read_text()), json.loads(Path(args.report).read_text())),
                         indent=1, ensure_ascii=False))
    else:
        data = merge(json.loads(Path(args.data).read_text()), json.loads(Path(args.notes).read_text()))
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        page = out / "report.html"
        page.write_text(report(data))
        (out / "report.json").write_text(json.dumps(data, indent=1))
        print(page.resolve())
        if not args.no_open:
            webbrowser.open(page.resolve().as_uri())


if __name__ == "__main__":
    main()
