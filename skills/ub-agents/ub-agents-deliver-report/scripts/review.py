#!/usr/bin/env python3
"""Facts and the page for the ub-agents-deliver-report skill. Read-only; standard library and `gh` only.

    review.py collect --repo OWNER/NAME [--day YYYY-MM-DD] > data.json
    review.py render data.json notes.json OUT_DIR [--no-open]   # writes report.html and report.json

The day runs from local midnight to local midnight; the default is yesterday.
Works on any repository that runs ub-agents (https://agents.uberblick.ai): the role
names come from the repository's ub-agents.yaml, and ROLES maps the common ones to a letter.
"""

import argparse
import base64
import datetime as dt
import html
import json
import re
import subprocess
import webbrowser
from pathlib import Path

SCHEMA = "ub-agents-deliver-report/1"
TRUSTED = {"OWNER", "MEMBER", "COLLABORATOR"}
RECORD = re.compile(r"<!-- ub-agents:v3 -->.*?```json\n(.*?)\n```", re.S)
CLOSES = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I)
LOCAL = re.compile(r"(?<![\w.~])/(?:Users|home|srv|mnt|tmp|private|var|opt|root)/\S*")
FORWARD = {"prepared", "handed-off", "approved", "merged"}


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


def day_window(text):
    """Local midnight to local midnight for the given day; yesterday when none is given."""
    zone = dt.datetime.now().astimezone().tzinfo
    day = dt.date.fromisoformat(text) if text else dt.datetime.now(zone).date() - dt.timedelta(days=1)
    since = dt.datetime.combine(day, dt.time.min, zone)
    return day, zone, since, since + dt.timedelta(days=1)


def runs_of(records):
    leases = {r["run"]: r for r in records if r.get("kind") == "lease"}
    outcomes = {r["run"]: r for r in records if r.get("kind") == "outcome"}
    runs = []
    for run in leases.keys() | outcomes.keys():
        lease, out = leases.get(run, {}), outcomes.get(run, {})
        if lease.get("result") == "withdrawn":
            continue
        result = out.get("outcome") if out.get("status") == "success" else out.get("status")
        runs.append({"agent": lease.get("agent") or out.get("agent"),
                     "started": lease.get("created") or out.get("created"),
                     "minutes": minutes(lease.get("created"), out.get("created")),
                     "result": result or lease.get("result") or "no report",
                     "accepted": bool(out.get("accepted")),
                     "denied": [public(f'{d.get("tool")}: {d.get("command")}', 160) for d in out.get("denials") or []],
                     "summary": public(out.get("summary") or lease.get("summary"), 400),
                     "url": out.get("url") or lease.get("url")})
    return sorted(runs, key=lambda r: r["started"] or "")


def board_posts(repo, boards):
    posts, errors, names = [], [], {}
    for agent, number in boards.items():
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
    config = base64.b64decode(gh(f"repos/{repo}/contents/ub-agents.yaml")["content"]).decode()
    boards, agent = {}, None
    for line in config.splitlines():
        agent = (re.match(r"^  ([\w-]+):\s*$", line) or [None, agent])[1]
        if found := re.match(r"^\s+retrospectives:\s*(\d+)", line):
            boards[agent] = int(found.group(1))

    items = {}
    for row in pages(f"repos/{repo}/issues", state="all", since=stamp(since)):
        records, notices = [], 0
        for c in pages(f"repos/{repo}/issues/{row['number']}/comments"):
            if c["author_association"] in TRUSTED and (found := RECORD.search(c["body"] or "")):
                records.append(json.loads(found.group(1)) | {"url": c["html_url"]})
            notices += (c["body"] or "").startswith("<!-- ub-agents:action-needed")
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

    posts, errors = board_posts(repo, boards)
    issues = []
    for key, prs in sorted(groups.items()):
        members = [key] + sorted(p for p in prs - {key} if p in items)
        head = items[key]["row"]
        runs = runs_of([r for n in members for r in items[n]["records"]])
        pulls = []
        for n in members:
            if "pull_request" in items[n]["row"]:
                pr = gh(f"repos/{repo}/pulls/{n}")
                pulls.append({"number": n, "url": pr["html_url"], "merged": pr["merged_at"],
                              "additions": pr["additions"], "deletions": pr["deletions"], "files": pr["changed_files"],
                              "by_loop": any(r["agent"] == "integrator" and r["result"] == "merged" for r in runs)})
        done = max([p["merged"] for p in pulls if p["merged"]] or [head.get("closed_at") or ""]) or None
        delivered = any(inside(p["merged"]) for p in pulls) or ("pull_request" not in head and inside(head.get("closed_at")))
        if not delivered and not any(inside(r["started"]) for r in runs):
            continue
        issues.append({
            "repo": repo, "day": day.isoformat(), "number": key, "title": head["title"], "url": head["html_url"],
            "delivered": delivered, "prs": pulls,
            "runs": runs, "extra_runs": max(0, len(runs) - len({r["agent"] for r in runs})),
            "resets": sum(1 for r in items[key]["records"] if r.get("kind") == "reset"),
            "notices": sum(items[n]["notices"] for n in members),
            "lead": minutes(head["created_at"], done), "agent_minutes": round(sum(r["minutes"] or 0 for r in runs), 1),
            "retrospectives": [p | {"items": sorted(p["items"])} for p in posts if p["items"] & set(members)]})

    window = [r for d in issues for r in d["runs"] if inside(r["started"])]
    merged = {p["number"]: p for d in issues for p in d["prs"] if inside(p["merged"])}.values()
    rows = [i["row"] for i in items.values()]
    return {
        "schema": SCHEMA, "repo": repo, "day": day.isoformat(), "timezone": since.strftime("%Z %z"),
        "since": stamp(since), "until": stamp(until),
        "summary": {
            "repo": repo, "day": day.isoformat(),
            "prs_merged": len(merged), "prs_merged_by_loop": sum(p["by_loop"] for p in merged),
            "additions": sum(p["additions"] for p in merged), "deletions": sum(p["deletions"] for p in merged),
            "files": sum(p["files"] for p in merged),
            "issues_closed": sum(1 for r in rows if "pull_request" not in r and inside(r.get("closed_at"))),
            "issues_opened": sum(1 for r in rows if "pull_request" not in r and inside(r["created_at"])),
            "runs": len(window), "runs_accepted": sum(r["accepted"] for r in window),
            "agent_hours": round(sum(r["minutes"] or 0 for r in window) / 60, 1),
            "deliveries": sum(1 for d in issues if d["delivered"] and d["runs"]),
            "first_pass": sum(1 for d in issues if d["delivered"] and d["runs"] and not d["extra_runs"]),
            "denials": sum(len(r["denied"]) for r in window)},
        "retrospectives": {"errors": errors, "in_window": [p | {"items": sorted(p["items"])} for p in posts if inside(p["created"])]},
        "issues": issues}


ROLES = {"issue-preparer": "P", "issue-reviewer": "Q", "implementer": "I", "pr-reviewer": "R", "reviewer": "R",
         "integrator": "G"}
LEVERS = {"authority": "Clearer authority", "wording": "Better wording",
          "fewer-instructions": "Fewer instructions", "autonomy": "More autonomy"}
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
.run { display: inline-block; font: 11px/1 var(--mono); padding: 4px 5px; margin: 1px; border-radius: 4px; color: var(--bg); text-decoration: none; }
.ok { background: var(--ok); } .back { background: var(--back); } .fail { background: var(--fail); }
.wrap { max-width: 1080px; margin: 0 auto; padding-inline: 20px; padding-block: 32px 56px; display: grid; gap: 36px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
.grid .num { font-size: 26px; } section { display: grid; gap: 12px; min-width: 0; }
.scroll { overflow-x: auto; } table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
td.r { text-align: right; white-space: nowrap; }
"""


def esc(value):
    return html.escape(str(value))


def span(m):
    return "–" if m is None else f"{m:.0f}m" if m < 90 else f"{m / 60:.1f}h" if m < 2880 else f"{m / 1440:.1f}d"


def tone(run):
    return "ok" if run["accepted"] and run["result"] in FORWARD | {"maintainer-merge"} else \
        "back" if run["result"] == "changes-requested" else "fail"


def chips(runs):
    return "".join(f'<a class="run {tone(r)}" href="{esc(r["url"])}" title="{esc(r["agent"])} · {esc(r["result"])} · '
                   f'{span(r["minutes"])}">{ROLES.get(r["agent"], "?")}</a>' for r in runs) or '<span class="label">outside the loop</span>'


def refs(repo, numbers):
    return " ".join(f'<a href="https://github.com/{repo}/issues/{n}">#{n}</a>' for n in numbers)


def figures(t):
    return [(t["prs_merged"], "PRs merged", f'{t["prs_merged_by_loop"]} by the integrator'),
            (f'+{t["additions"]:,}', "lines", f'−{t["deletions"]:,} · {t["files"]} files'),
            (t["issues_closed"], "issues closed", f'{t["issues_opened"]} opened'),
            (t["runs"], "agent runs", f'{t["runs_accepted"]} accepted · {t["agent_hours"]}h'),
            (f'{t["first_pass"]}/{t["deliveries"]}', "first pass", "each role ran once"),
            (t["denials"], "denied commands", "in this day's runs")]


def report(data, notes):
    """The page follows references/report.md: header, figures, what to change, where extra runs went,
    each delivery, retrospectives."""
    repo = data["repo"]
    out = [f'<title>Delivery report {data["day"]}</title>', CSS, "</style><main class=\"wrap\">",
           f'<header><div class="label">{esc(repo)} · {esc(data["day"])} · {esc(data["timezone"])}</div>'
           f'<h1>Delivery report</h1><p>{esc(notes["headline"])}</p></header><section class="grid">']
    out += [f'<div class="box"><div class="label">{l}</div><div class="num">{esc(v)}</div><div class="label">{esc(s)}</div></div>'
            for v, l, s in figures(data["summary"])]
    out.append("</section><section><h2>What to change</h2>")
    out += [f'<div class="box"><div class="label">{esc(LEVERS.get(l["lever"], l["lever"]))}</div><h3>{esc(l["title"])}</h3>'
            f'<p>{esc(l["change"])}</p><div class="label">{esc(l.get("where", ""))} · {esc(l.get("cost", ""))} · '
            f'{refs(repo, l.get("evidence", []))}</div></div>' for l in notes.get("lessons", [])]
    out.append('</section><section><h2>Where extra runs went</h2><div class="scroll box"><table><tr><th>Cause</th><th>Cost</th><th>Items</th><th>State</th></tr>')
    out += [f'<tr><td>{esc(c["cause"])}</td><td class="r">{esc(c["cost"])}</td><td>{refs(repo, c["items"])}</td>'
            f'<td>{esc(c.get("state", ""))}</td></tr>' for c in notes.get("causes", [])]
    out.append('</table></div></section><section><h2>Each delivery</h2><div class="label">P preparer · Q issue reviewer · I implementer · '
               'R reviewer · G integrator; green moved forward, amber sent back, red blocked, retried or no report</div>'
               '<div class="scroll box"><table><tr><th>Item</th><th>Runs</th><th>Lines</th><th>Lead</th><th>Note</th></tr>')
    for d in sorted(data["issues"], key=lambda d: (not d["delivered"], -d["extra_runs"])):
        extra = [f'<a href="{esc(p["url"])}">PR #{p["number"]}</a>' for p in d["prs"] if p["number"] != d["number"]]
        extra += [f'<a href="{esc(r["url"])}">retro</a>' for r in d["retrospectives"]] + ["in flight"] * (not d["delivered"])
        out.append(f'<tr><td><a href="{esc(d["url"])}">#{d["number"]}</a> {esc(d["title"])}<div class="label">{" · ".join(extra)}</div></td>'
                   f'<td>{chips(d["runs"])}</td><td class="r">{sum(p["additions"] + p["deletions"] for p in d["prs"]):,}</td>'
                   f'<td class="r">{span(d["lead"])}</td><td>{esc(d.get("note", ""))}</td></tr>')
    out.append("</table></div></section><section><h2>Retrospectives</h2>")
    retro = data["retrospectives"]
    out += [f'<div class="box"><a class="label" href="{esc(r["url"])}">{esc(r["agent"])}</a><p>{esc(r["body"])}</p></div>' for r in retro["in_window"]]
    out.append(f'<p>Boards not read: {esc(retro["errors"][0])}</p>' if retro["errors"] else "" if retro["in_window"] else "<p>None posted on this day.</p>")
    return "\n".join(out + ["</section></main>"])


def merge(data, notes):
    """The day's record: the summary carries the reading, each issue its note. See references/report.md."""
    data["summary"] |= {"headline": notes["headline"], "causes": notes.get("causes", []), "lessons": notes.get("lessons", [])}
    for issue in data["issues"]:
        issue["note"] = notes.get("items", {}).get(str(issue["number"]), "")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    c = commands.add_parser("collect")
    c.add_argument("--repo", required=True)
    c.add_argument("--day", help="calendar day, YYYY-MM-DD, local time (default yesterday)")
    r = commands.add_parser("render")
    r.add_argument("data"), r.add_argument("notes"), r.add_argument("out")
    r.add_argument("--no-open", action="store_true", help="do not open the report in the default browser")
    args = parser.parse_args()
    if args.command == "collect":
        print(json.dumps(collect(args.repo, *day_window(args.day)), indent=1))
    else:
        data = merge(json.loads(Path(args.data).read_text()), json.loads(Path(args.notes).read_text()))
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        page = out / "report.html"
        page.write_text(report(data, data["summary"]))
        (out / "report.json").write_text(json.dumps(data, indent=1))
        print(page.resolve())
        if not args.no_open:
            webbrowser.open(page.resolve().as_uri())


if __name__ == "__main__":
    main()
