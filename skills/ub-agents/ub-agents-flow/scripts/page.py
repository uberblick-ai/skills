#!/usr/bin/env python3
"""Build the loop flow report from flow.json and one ablauf flow per phase: Uberblick Markdown and a page; reads only."""
import argparse
import html
import json
import re
import sys
import webbrowser
from pathlib import Path

DECIDERS = {"launcher", "agent", "person"}
GATE_ID = re.compile(r"^G\d+$")
EDGE = re.compile(r"\s-\.?->\s")
SOURCE = re.compile(r"^([^\s:]+)(?::(\d+)(?:-(\d+))?)?$")
# ablauf 0.2.0's light palette, forced when printing so a dark screen still prints on white.
LIGHT = {"bg": "#ffffff", "ink": "#17202c", "muted": "#5a6575", "line": "#d3d9e2", "band": "#e9eef5",
         "surface": "#ffffff", "neutral": "#59616c", "neutral-bg": "#e1e3e6", "agent": "#3e6563",
         "agent-bg": "#e7eeed", "system": "#4f5d76", "system-bg": "#ebedf3", "rework": "#826954",
         "rework-bg": "#f3f0eb", "stop": "#815f5a", "stop-bg": "#ede6e5", "done": "#536e5a", "done-bg": "#e8ede9"}
# Past these the report no longer fits two pages.
BUDGET = {"summary": 60, "phase": 30, "does": 20, "rule": 30, "gates": 8}


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


def validate(data, flows=None):
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
        if words(text(gate, "rule", gid)) > BUDGET["rule"]:
            warnings.append(f"{gid}: rule is over {BUDGET['rule']} words")
        sources = gate.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{gid}: sources must name the files (path:line) the gate comes from")
        for source in sources:
            if not isinstance(source, str) or not SOURCE.match(source):
                raise ValueError(f"{gid}: source {source!r} must be path or path:line or path:start-end")
    if "settings" in data:
        raise ValueError("settings are gone: a limit that holds work is a gate, and a queue rule is a note "
                         "linking its agents.uberblick.ai page")
    for note in data.get("notes", []):
        if not isinstance(note, str) or not note.strip():
            raise ValueError("notes must be nonempty sentences")
    phases = data.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("phases must list the issue phase and the implementation and PR phase")
    placed = {"roles": [], "gates": []}
    for phase in phases:
        name = text(phase, "name", "phase")
        if words(text(phase, "summary", name)) > BUDGET["phase"]:
            warnings.append(f"{name}: summary is over {BUDGET['phase']} words")
        if not text(phase, "flow", name).endswith(".flow"):
            raise ValueError(f"{name}: flow must name an ablauf .flow file next to flow.json")
        for key, known in (("roles", seen), ("gates", set(ids))):
            listed = labels(phase.get(key, []), f"{name}: {key}")
            if key == "roles" and not listed:
                raise ValueError(f"{name}: roles must name the agents of this phase")
            unknown = [v for v in listed if v not in known]
            if unknown:
                raise ValueError(f"{name}: unknown {key} {', '.join(unknown)}")
            placed[key] += listed
    for key, every in (("roles", [r["agent"] for r in roles]), ("gates", ids)):
        missing = [v for v in every if v not in placed[key]]
        twice = sorted({v for v in placed[key] if placed[key].count(v) > 1})
        if missing or twice:
            raise ValueError(f"every {key[:-1]} belongs to exactly one phase: "
                             + "; ".join(filter(None, [missing and f"missing {', '.join(missing)}",
                                                       twice and f"twice {', '.join(twice)}"])))
    if flows is not None:
        # A gate is drawn as a node; a number in an edge label alone is easy to miss.
        drawn = {name: {gid for line in source.splitlines() if not EDGE.search(line)
                        for gid in re.findall(r"\bG\d+\b", line)}
                 for name, source in flows.items()}
        every = set().union(*drawn.values())
        warnings += [f"{gid} is in no flow" for gid in ids if gid not in every]
        warnings += [f"the {name} flow shows {gid}, which is not a gate"
                     for name, shown in drawn.items() for gid in sorted(shown - set(ids))]
        for phase in phases:
            shown = drawn.get(phase["name"], set())
            warnings += [f"{gid} is not in the {phase['name']} flow" for gid in phase.get("gates", [])
                         if gid in every and gid not in shown]
    return warnings


def cell(value):
    """Inline Markdown for a GFM table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def blocks(data, svgs):
    """The report as Uberblick document blocks, in order; Markdown and HTML both come from these."""
    repo, ref = data["repository"], data["ref"]
    roles = {r["agent"]: r for r in data["roles"]}
    gates = {g["id"]: g for g in data["gates"]}

    def link(source):
        path, start, end = SOURCE.match(source).groups()
        anchor = f"#L{start}" + (f"-L{end}" if end else "") if start else ""
        return f"[{source}](https://github.com/{repo}/blob/{ref}/{path}{anchor})"

    out = [("h1", f"How the loop runs in {repo}"),
           ("p", f"`ub-agents.yaml` at `{ref}` · {data['date']} · {len(data['roles'])} agents · {len(data['gates'])} gates"),
           ("p", data["summary"])]
    for phase in data["phases"]:
        rows = [["Agent", "Starts on", "Does", "Outcome → label"]]
        for name in phase["roles"]:
            r = roles[name]
            does = r["does"] + (f" {link(r['instructions'])}" if r.get("instructions") else "")
            outcomes = "; ".join(f"{o} → " + (" ".join(f"`{a}`" for a in added) or "*no label*")
                                 for o, added in r["outcomes"].items())
            rows.append([f"**{name}** {r.get('kind', 'any')}", " ".join(f"`{t}`" for t in r["triggers"]), does, outcomes])
        out += [("phase", phase["name"]), ("p", phase["summary"]),
                ("ablauf", svgs.get(phase["name"], "")), ("table", rows)]
        for gid in phase.get("gates", []):
            g = gates[gid]
            out.append(("card", {"label": f"{gid} · {g['at']} · {g['decides']} decides", "title": g["name"],
                                 "body": g["rule"],
                                 "footer": " · ".join(link(s) for s in g["sources"])}))
    if data.get("notes"):
        out += [("h2", "Notes")] + [("li", n) for n in data["notes"]]
    out.append(("p", "*Generated by the ub-agents-flow skill. Read-only: nothing on GitHub changed.*"))
    return out


def markdown(data, flows):
    """Uberblick Markdown: headings, paragraphs, ablauf fences, GFM tables, cards and list items."""
    parts, phase = [], 0
    for kind, value in blocks(data, {}):
        if kind == "h1":
            parts.append(f"# {value}")
        elif kind in ("h2", "phase"):
            parts.append(f"## {value}")
        elif kind == "p":
            parts.append(value)
        elif kind == "li":
            parts.append(f"- {value}")
        elif kind == "ablauf":
            parts.append("```ablauf\n" + flows[data["phases"][phase]["name"]].strip() + "\n```")
            phase += 1
        elif kind == "table":
            head, *rows = value
            parts.append("\n".join(["| " + " | ".join(cell(c) for c in head) + " |",
                                    "|" + "---|" * len(head)]
                                   + ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]))
        elif kind == "card":
            parts.append(":::card\n" + "".join(f"{k}: {value[k]}\n" for k in ("label", "title", "footer"))
                         + "\n" + value["body"] + "\n:::")
    text = "\n\n".join(parts)
    return re.sub(r"\n(- [^\n]*)\n\n(?=- )", r"\n\1\n", text) + "\n"


def inline(value):
    """The inline Markdown the report writes: code, links, bold and italic."""
    codes = []

    def keep(match):
        codes.append(f"<code>{esc(match.group(1))}</code>")
        return f"\x00{len(codes) - 1}\x00"
    value = esc(re.sub(r"`([^`]+)`", keep, value))
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" rel="noreferrer">\1</a>', value)
    value = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"(?<![\w*])\*([^*]+)\*(?!\w)", r"<em>\1</em>", value)
    return re.sub("\x00(\\d+)\x00", lambda m: codes[int(m.group(1))], value).replace("\n", "<br>")


def render(data, svgs):
    """The page: the same blocks styled like an Uberblick document, each ablauf fence drawn."""
    html_blocks, items = [], []
    for kind, value in blocks(data, svgs):
        if kind != "li" and items:
            html_blocks.append("<ul>" + "".join(items) + "</ul>")
            items = []
        if kind == "h1":
            html_blocks.append(f'<h1>{inline(value)}</h1>')
        elif kind == "h2":
            html_blocks.append(f'<h2>{inline(value)}</h2>')
        elif kind == "phase":
            html_blocks.append(f'<h2 class="phase">{inline(value)}</h2>')
        elif kind == "p":
            html_blocks.append(f"<p>{inline(value)}</p>")
        elif kind == "li":
            items.append(f"<li>{inline(value)}</li>")
        elif kind == "ablauf":
            html_blocks.append(f'<figure class="ablauf">{value}</figure>')
        elif kind == "table":
            head, *rows = value
            html_blocks.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                               + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in rows)
                               + "</tbody></table>")
        elif kind == "card":
            html_blocks.append(f'<div class="card"><div class="card-label">{inline(value["label"])}</div>'
                               f'<div class="card-title">{inline(value["title"])}</div>'
                               f'<div class="card-body">{inline(value["body"])}</div>'
                               f'<div class="card-footer">{inline(value["footer"])}</div></div>')
    if items:
        html_blocks.append("<ul>" + "".join(items) + "</ul>")
    body = "\n".join(html_blocks)
    light = "".join(f"--ab-{k}:{v};" for k, v in LIGHT.items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Loop flow · {esc(data["repository"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
/* Uberblick's document tokens and block styles, so the page reads like the document flow.md imports as. */
:root{{--background:oklch(0.96 0.008 75);--foreground:oklch(0.145 0 0);--card:oklch(0.97 0.005 75);--muted:oklch(0.97 0 0);
--muted-foreground:oklch(0.511 0 0);--border:oklch(0.922 0 0);--prose-text:oklch(0.3 0 0);--radius:0.625rem;color-scheme:light dark}}
@media (prefers-color-scheme:dark){{:root{{--background:oklch(0.145 0 0);--foreground:oklch(0.985 0 0);--card:oklch(0.205 0 0);
--muted:oklch(0.22 0.01 65);--muted-foreground:oklch(0.708 0 0);--border:oklch(1 0 0 / 10%);--prose-text:oklch(0.92 0 0)}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--background);color:var(--prose-text);font:16px/27px Geist,system-ui,sans-serif}}
main{{max-width:72ch;margin:0 auto;padding:40px 16px 64px}}
h1,h2{{color:var(--foreground);font-weight:600}}
h1{{font-size:36px;line-height:42px;letter-spacing:-0.021em;margin:0 0 .35em}}
h2{{font-size:22px;line-height:28px;letter-spacing:-0.012em;margin:1.9em 0 .45em}}
p{{margin:.5em 0}}a{{color:inherit}}strong{{color:var(--foreground);font-weight:600}}
code{{white-space:nowrap;font:.875em "Geist Mono",ui-monospace,monospace;background:var(--muted);border:1px solid var(--border);border-radius:4px;padding:0 4px}}
.ablauf{{margin:12px 0;text-align:center;overflow-x:auto}}.ablauf svg{{max-width:100%;height:auto}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;line-height:20px}}
th,td{{text-align:left;vertical-align:top;padding:6px 8px;border:1px solid var(--border)}}th{{color:var(--foreground);font-weight:600;background:var(--muted)}}
.card{{margin:12px 0;padding:20px 24px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);break-inside:avoid}}
.card-label,.card-footer{{color:var(--muted-foreground);font-size:12px;line-height:16px;font-weight:500;text-transform:uppercase;letter-spacing:.08em}}
.card-title{{margin-top:6px;color:var(--foreground);font-size:18px;line-height:24px;font-weight:600}}
.card-body{{margin-top:12px}}.card-footer{{margin-top:12px;letter-spacing:.06em}}.card-footer a{{text-transform:none}}
ul{{margin:.5em 0;padding-left:1.4em}}
@page{{size:A4;margin:12mm}}
@media print{{:root{{--background:#fff;--foreground:oklch(0.145 0 0);--card:oklch(0.97 0.005 75);--muted:oklch(0.97 0 0);
--muted-foreground:oklch(0.511 0 0);--border:oklch(0.922 0 0);--prose-text:oklch(0.3 0 0)}}
main{{max-width:none;padding:0}}body{{font-size:11px;line-height:16px}}h1{{font-size:22px;line-height:26px}}
h2{{font-size:15px;line-height:20px;margin:1.2em 0 .3em}}.phase~.phase{{break-before:page;margin-top:0}}
.ablauf svg{{max-height:120mm;width:auto}}.ablauf{{{light}}}table{{font-size:10px;line-height:14px}}th,td{{padding:3px 6px}}
.card{{padding:8px 12px;margin:6px 0}}.card-label,.card-footer{{font-size:8.5px;line-height:12px}}.card-title{{font-size:12px;line-height:16px;margin-top:2px}}.card-body{{margin-top:4px}}.card-footer{{margin-top:4px}}}}
</style></head><body><main>
{body}
</main></body></html>
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path, help="flow.json; each phase's .flow and its .svg sit next to it")
    p.add_argument("--out", type=Path, required=True, help="the page; the Uberblick Markdown goes next to it as .md")
    p.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = p.parse_args(argv)
    try:
        data = json.loads(args.report.read_text(encoding="utf-8"))
        warnings = validate(data)
        flows, svgs = {}, {}
        for phase in data["phases"]:
            flow = args.report.parent / phase["flow"]
            flows[phase["name"]] = flow.read_text(encoding="utf-8")
            svg = flow.with_suffix(".svg")
            if not svg.exists():
                raise ValueError(f"no {svg.name}: render {flow.name} with render.mjs first")
            svgs[phase["name"]] = svg.read_text(encoding="utf-8")
            if not svgs[phase["name"]].lstrip().startswith("<svg"):
                raise ValueError(f"{flow.with_suffix('.svg')} is not an SVG; render {flow.name} first")
        warnings = validate(data, flows)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    args.out.write_text(render(data, svgs), encoding="utf-8")
    args.out.with_suffix(".md").write_text(markdown(data, flows), encoding="utf-8")
    print(args.out)
    print(args.out.with_suffix(".md"))
    if args.open:
        webbrowser.open(args.out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
