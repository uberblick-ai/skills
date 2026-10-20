#!/usr/bin/env python3
"""Build the one or two page loop flow report from flow.json and the ablauf SVG; reads only."""
import argparse
import html
import json
import re
import sys
import webbrowser
from pathlib import Path

DECIDERS = {"launcher", "agent", "person"}
GATE_ID = re.compile(r"^G\d+$")
SOURCE = re.compile(r"^([^\s:]+)(?::(\d+)(?:-(\d+))?)?$")
# ablauf 0.2.0's light palette, forced when printing so a dark screen still prints on white.
LIGHT = {"bg": "#ffffff", "ink": "#17202c", "muted": "#5a6575", "line": "#d3d9e2", "band": "#e9eef5",
         "surface": "#ffffff", "neutral": "#59616c", "neutral-bg": "#e1e3e6", "agent": "#3e6563",
         "agent-bg": "#e7eeed", "system": "#4f5d76", "system-bg": "#ebedf3", "rework": "#826954",
         "rework-bg": "#f3f0eb", "stop": "#815f5a", "stop-bg": "#ede6e5", "done": "#536e5a", "done-bg": "#e8ede9"}
# Past these the report no longer fits two pages.
BUDGET = {"summary": 60, "does": 20, "passes": 35, "holds": 35, "gates": 8}


def esc(value):
    return html.escape(str(value), quote=True)


def text(obj, key, where):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{where}: {key} must be nonempty text")
    return value.strip()


def labels(value, where):
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise ValueError(f"{where} must be a list of label names")
    return value


def words(value):
    return len(value.split())


def validate(data, flow=None):
    """Raise on a malformed report; return warnings about consistency and length."""
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    repo = text(data, "repository", "report")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("repository must be OWNER/NAME")
    text(data, "ref", "report")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text(data, "date", "report")):
        raise ValueError("date must be YYYY-MM-DD")
    warnings = []
    if words(text(data, "summary", "report")) > BUDGET["summary"]:
        warnings.append(f"summary is over {BUDGET['summary']} words")
    roles = data.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError("roles must list every agent in ub-agents.yaml")
    stops = labels(data.get("stop_labels", ["needs-human"]), "stop_labels")
    seen = set()
    for role in roles:
        name = text(role, "agent", "role")
        if name in seen:
            raise ValueError(f"role {name} appears twice")
        seen.add(name)
        labels(role.get("triggers"), f"{name}: triggers")
        if words(text(role, "does", name)) > BUDGET["does"]:
            warnings.append(f"{name}: does is over {BUDGET['does']} words")
        outcomes = role.get("outcomes")
        if not isinstance(outcomes, dict) or not outcomes:
            raise ValueError(f"{name}: outcomes must map each outcome to the labels it adds")
        for outcome, added in outcomes.items():
            labels(added, f"{name}: outcome {outcome}")
    triggered = {label for role in roles for label in role["triggers"]}
    for role in roles:
        for outcome, added in role["outcomes"].items():
            for label in added:
                if label not in triggered and label not in stops:
                    warnings.append(f"{role['agent']}: outcome {outcome} adds {label}, which starts no agent")
    gates = data.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ValueError("gates must list at least one gate")
    if len(gates) > BUDGET["gates"]:
        warnings.append(f"{len(gates)} gates; merge related ones to stay within {BUDGET['gates']}")
    ids = []
    for gate in gates:
        gid = text(gate, "id", "gate")
        if not GATE_ID.match(gid) or gid in ids:
            raise ValueError(f"gate id {gid!r} must be G1, G2, ... and unique")
        ids.append(gid)
        for key in ("name", "at"):
            text(gate, key, gid)
        if gate.get("decides") not in DECIDERS:
            raise ValueError(f"{gid}: decides must be one of {', '.join(sorted(DECIDERS))}")
        for key in ("passes", "holds"):
            if words(text(gate, key, gid)) > BUDGET[key]:
                warnings.append(f"{gid}: {key} is over {BUDGET[key]} words")
        sources = gate.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{gid}: sources must name the files (path:line) the gate comes from")
        for source in sources:
            if not isinstance(source, str) or not SOURCE.match(source):
                raise ValueError(f"{gid}: source {source!r} must be path or path:line or path:start-end")
    for setting in data.get("settings", []):
        for key in ("name", "value", "meaning"):
            text(setting, key, "setting")
    for note in data.get("notes", []):
        if not isinstance(note, str) or not note.strip():
            raise ValueError("notes must be nonempty sentences")
    if flow is not None:
        drawn = set(re.findall(r"\bG\d+\b", flow))
        warnings += [f"{gid} is not in the flow" for gid in ids if gid not in drawn]
        warnings += [f"the flow shows {gid}, which is not a gate" for gid in sorted(drawn - set(ids))]
    return warnings


def source_link(repo, ref, source):
    path, start, end = SOURCE.match(source).groups()
    anchor = f"#L{start}" + (f"-L{end}" if end else "") if start else ""
    return (f'<a href="https://github.com/{esc(repo)}/blob/{esc(ref)}/{esc(path)}{anchor}" '
            f'rel="noreferrer">{esc(source)}</a>')


def pill(label):
    return f'<code class="pill">{esc(label)}</code>'


def render(data, svg, flow=None):
    repo, ref = data["repository"], data["ref"]
    gates = "".join(
        f'<article class="gate {esc(g["decides"])}"><header><b>{esc(g["id"])}</b> {esc(g["name"])}'
        f'<span>{esc(g["at"])} · {esc(g["decides"])} decides</span></header>'
        f'<p><em>Passes</em> {esc(g["passes"])}</p><p><em>Holds</em> {esc(g["holds"])}</p>'
        f'<p class="src">{" ".join(source_link(repo, ref, s) for s in g["sources"])}</p></article>'
        for g in data["gates"])
    roles = "".join(
        f'<li><b>{esc(r["agent"])}</b> <small>{esc(r.get("kind", "any"))}</small><br>'
        f'<small>starts on</small> {" ".join(pill(t) for t in r["triggers"])}<br>{esc(r["does"])}'
        + (f' <small>{source_link(repo, ref, r["instructions"])}</small>' if r.get("instructions") else "")
        + '<br>' + "; ".join(f'{esc(o)} → {" ".join(pill(a) for a in added) or "<small>no label</small>"}'
                             for o, added in r["outcomes"].items())
        + (f'<br><small>{esc(r["runtime"])}</small>' if r.get("runtime") else "") + "</li>"
        for r in data["roles"])
    settings = "".join(f'<dt><code>{esc(s["name"])}</code> {esc(s["value"])}</dt><dd>{esc(s["meaning"])}</dd>'
                       for s in data.get("settings", []))
    notes = "".join(f"<li>{esc(n)}</li>" for n in data.get("notes", []))
    light = "".join(f"--ab-{k}:{v};" for k, v in LIGHT.items())
    source = (f'<details class="screen"><summary>ablauf source</summary><pre>{esc(flow)}</pre></details>'
              if flow else "")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Loop flow · {esc(repo)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#f6f7f9;--paper:#fff;--ink:#17202c;--muted:#5a6575;--line:#d3d9e2;--system:#4f5d76;--system-bg:#ebedf3;
--stop:#815f5a;--stop-bg:#ede6e5;--agent:#3e6563;--agent-bg:#e7eeed;color-scheme:light dark}}
@media (prefers-color-scheme:dark){{:root{{--bg:#11151b;--paper:#171c24;--ink:#e5e9ef;--muted:#98a2b0;--line:#2c3440;
--system:#98a5bf;--system-bg:#262a31;--stop:#ac8c88;--stop-bg:#2b2221;--agent:#85aaa5;--agent-bg:#232d2b}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 "IBM Plex Sans",system-ui,sans-serif}}
.sheet{{background:var(--paper);max-width:210mm;margin:16px auto;padding:14mm 12mm;border:1px solid var(--line);border-radius:6px}}
h1{{font-size:22px;margin:0 0 2px}}h2{{font-size:15px;margin:18px 0 8px}}h2:first-child{{margin-top:0}}
.eyebrow,.meta,small,.gate span,.src{{color:var(--muted)}}.eyebrow{{font:600 11px "IBM Plex Mono",monospace;letter-spacing:.08em;text-transform:uppercase}}
.meta{{font-size:12px;margin-bottom:10px}}.summary{{margin:0 0 12px}}
.flow{{margin:0;text-align:center}}.flow svg{{max-width:100%;height:auto}}
.gates{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.gate{{border:1px solid var(--line);border-left:4px solid var(--system);border-radius:4px;padding:6px 9px;break-inside:avoid;font-size:12.5px}}
.gate.person{{border-left-color:var(--stop)}}.gate.agent{{border-left-color:var(--agent)}}
.gate header b{{font-family:"IBM Plex Mono",monospace;margin-right:4px}}.gate header span{{display:block;font-size:11.5px}}
.gate p{{margin:3px 0}}.gate em{{font-style:normal;font-weight:600}}.src{{font-size:11px}}.src a{{margin-right:6px}}a{{color:inherit}}
.split{{display:grid;grid-template-columns:minmax(0,1fr) 66mm;gap:6mm;align-items:start}}
aside{{font-size:12px}}.roles{{list-style:none;padding:0;margin:0}}.roles li{{padding:5px 0;border-top:1px solid var(--line)}}
.settings{{display:grid;grid-template-columns:auto 1fr;margin:0;font-size:12.5px}}.settings>*{{border-top:1px solid var(--line);padding:4px 8px 4px 0;margin:0}}
dt{{font-weight:600}}dt code{{font-weight:400}}dd{{color:var(--muted)}}
.pill{{font:.92em "IBM Plex Mono",monospace;border:1px solid var(--line);border-radius:9px;padding:0 6px;white-space:nowrap}}
ul{{margin:4px 0;padding-left:18px}}pre{{font-size:11px;overflow:auto}}footer{{font-size:11px;color:var(--muted);margin-top:12px}}
@media (max-width:640px){{.sheet{{margin:0;border:0;border-radius:0;padding:16px}}.gates,.split{{grid-template-columns:1fr}}}}
@page{{size:A4;margin:11mm}}
@media print{{:root{{--bg:#fff;--paper:#fff;--ink:#17202c;--muted:#5a6575;--line:#d3d9e2;--system:#4f5d76;--stop:#815f5a;--agent:#3e6563}}
body{{background:#fff}}.sheet{{margin:0;padding:0;border:0;max-width:none}}.two{{break-before:page}}.screen{{display:none}}
.flow svg{{max-height:228mm;width:auto}}body{{font-size:12px}}h2{{margin:12px 0 6px}}.gate,aside,.settings{{font-size:11px}}.flow{{{light}}}}}
</style></head><body>
<section class="sheet one">
<div class="eyebrow">ub-agents flow</div>
<h1>How the loop runs in {esc(repo)}</h1>
<div class="meta">ub-agents.yaml at <code>{esc(ref)}</code> · {esc(data["date"])} · {len(data["roles"])} agents · {len(data["gates"])} gates</div>
<p class="summary">{esc(data["summary"])}</p>
<div class="split"><figure class="flow">{svg}</figure>
<aside><h2>Roles</h2><ul class="roles">{roles}</ul></aside></div>
</section>
<section class="sheet two">
<h2>Gates</h2><div class="gates">{gates}</div>
{f'<h2>Limits and policy</h2><dl class="settings">{settings}</dl>' if settings else ""}
{f'<h2>Notes</h2><ul>{notes}</ul>' if notes else ""}
{source}
<footer>Generated by the ub-agents-flow skill from {esc(repo)} at {esc(ref)}. Read-only: nothing on GitHub changed.</footer>
</section>
</body></html>
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path, help="flow.json")
    p.add_argument("--svg", type=Path, required=True, help="the flow drawn by render.mjs")
    p.add_argument("--flow", type=Path, help="the ablauf source, to check gate numbers and show it")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = p.parse_args(argv)
    try:
        data = json.loads(args.report.read_text(encoding="utf-8"))
        svg = args.svg.read_text(encoding="utf-8")
        if not svg.lstrip().startswith("<svg"):
            raise ValueError(f"{args.svg} is not an SVG")
        flow = args.flow.read_text(encoding="utf-8") if args.flow else None
        warnings = validate(data, flow)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    args.out.write_text(render(data, svg, flow), encoding="utf-8")
    print(args.out)
    if args.open:
        webbrowser.open(args.out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
