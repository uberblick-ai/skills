#!/usr/bin/env python3
"""Build the loop flow documents from flow.json and its ablauf flows: an overview and one document per phase,
as Uberblick Markdown and a page; reads only."""
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
# Past these a document stops reading at a glance.
BUDGET = {"summary": 60, "phase": 30, "point": 30, "does": 20, "rule": 30}


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


def gate_list(gates, where):
    """A phase's gates, numbered G1, G2, ... in the order an item meets them."""
    if not isinstance(gates, list) or not gates:
        raise ValueError(f"{where}: gates must list at least one gate")
    for n, gate in enumerate(gates, 1):
        gid = text(gate, "id", f"{where} gate")
        if gid != f"G{n}":
            raise ValueError(f"{where}: gate {gid!r} must be G{n}; number each phase's gates from G1 in order")
        for key in ("name", "at"):
            text(gate, key, f"{where} {gid}")
        if gate.get("decides") not in DECIDERS:
            raise ValueError(f"{where} {gid}: decides must be one of {', '.join(sorted(DECIDERS))}")
        sources = gate.get("sources")
        if not isinstance(sources, list) or not sources:
            raise ValueError(f"{where} {gid}: sources must name the files (path:line) the gate comes from")
        for source in sources:
            if not isinstance(source, str) or not SOURCE.match(source):
                raise ValueError(f"{where} {gid}: source {source!r} must be path or path:line or path:start-end")
    return [g["id"] for g in gates]


def note_list(obj, where):
    notes = obj.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(n, str) and n.strip() for n in notes):
        raise ValueError(f"{where}: notes must be nonempty sentences")
    return notes


def section_list(obj, where):
    """A phase's extra sections, such as work that enters it without an issue."""
    sections = obj.get("sections", [])
    if not isinstance(sections, list):
        raise ValueError(f"{where}: sections must be a list")
    for section in sections:
        heading = text(section, "heading", f"{where} section")
        items = section.get("items", [])
        if not isinstance(items, list) or not all(isinstance(i, str) and i.strip() for i in items):
            raise ValueError(f"{where}: {heading}: items must be nonempty sentences")
        if not section.get("text") and not items:
            raise ValueError(f"{where}: {heading} needs text, items or both")
        if "text" in section:
            text(section, "text", f"{where}: {heading}")
    return sections


def flow_name(obj, where):
    name = text(obj, "flow", where)
    if not name.endswith(".flow") or "/" in name:
        raise ValueError(f"{where}: flow must name an ablauf .flow file next to flow.json")
    return name


def validate(data, flows=None):
    """Raise on a malformed report; return warnings about consistency and length."""
    if data.get("schema_version") != 2:
        raise ValueError("schema_version must be 2")
    repo = text(data, "repository", "report")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
        raise ValueError("repository must be OWNER/NAME")
    text(data, "ref", "report")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text(data, "date", "report")):
        raise ValueError("date must be YYYY-MM-DD")
    for gone, why in (("settings", "a limit that holds work is a gate, and a queue rule is a note linking its "
                                   "agents.uberblick.ai page"),
                      ("gates", "each phase lists its own gates, numbered from G1"),
                      ("summary", "the summary belongs to the overview"),
                      ("notes", "notes belong to a phase")):
        if gone in data:
            raise ValueError(f"{gone} is not a top-level field: {why}")
    warnings = []
    overview = data.get("overview")
    if not isinstance(overview, dict):
        raise ValueError("overview must hold the summary, the overview flow and its points")
    if words(text(overview, "summary", "overview")) > BUDGET["summary"]:
        warnings.append(f"overview: summary is over {BUDGET['summary']} words")
    flow_name(overview, "overview")
    if "notes" in overview:
        raise ValueError("overview: notes belong to a phase; the overview keeps to the abstract flow")
    points = overview.get("points")
    if not isinstance(points, list) or not points or not all(isinstance(p, str) and p.strip() for p in points):
        raise ValueError("overview: points must list each input and each phase in a sentence")
    warnings += [f"overview: point {n} is over {BUDGET['point']} words"
                 for n, point in enumerate(points, 1) if words(point) > BUDGET["point"]]
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
    phases = data.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ValueError("phases must list the issue phase and the implementation and PR phase")
    placed, files = [], {overview["flow"]}
    for phase in phases:
        name = text(phase, "name", "phase")
        if words(text(phase, "summary", name)) > BUDGET["phase"]:
            warnings.append(f"{name}: summary is over {BUDGET['phase']} words")
        flow = flow_name(phase, name)
        if Path(flow).stem in ("overview", "flow"):
            raise ValueError(f"{name}: {flow} would overwrite the overview's or the combined document's Markdown")
        if flow in files:
            raise ValueError(f"{name}: {flow} is already another document's flow")
        files.add(flow)
        listed = labels(phase.get("roles", []), f"{name}: roles")
        if not listed:
            raise ValueError(f"{name}: roles must name the agents of this phase")
        unknown = [v for v in listed if v not in seen]
        if unknown:
            raise ValueError(f"{name}: unknown roles {', '.join(unknown)}")
        placed += listed
        gate_list(phase.get("gates"), name)
        for gate in phase["gates"]:
            if words(text(gate, "rule", f"{name} {gate['id']}")) > BUDGET["rule"]:
                warnings.append(f"{name} {gate['id']}: rule is over {BUDGET['rule']} words")
        section_list(phase, name)
        note_list(phase, name)
    missing = [r["agent"] for r in roles if r["agent"] not in placed]
    twice = sorted({v for v in placed if placed.count(v) > 1})
    if missing or twice:
        raise ValueError("every role belongs to exactly one phase: "
                         + "; ".join(filter(None, [missing and f"missing {', '.join(missing)}",
                                                   twice and f"twice {', '.join(twice)}"])))
    if flows is not None:
        for phase in phases:
            # A gate is drawn as a node; a number in an edge label alone is easy to miss.
            source = flows.get(phase["flow"], "")
            shown = {gid for line in source.splitlines() if not EDGE.search(line)
                     for gid in re.findall(r"\bG\d+\b", line)}
            ids = [g["id"] for g in phase["gates"]]
            warnings += [f"{phase['name']}: {gid} is not in {phase['flow']}" for gid in ids if gid not in shown]
            warnings += [f"{phase['name']}: {phase['flow']} shows {gid}, which is not one of its gates"
                         for gid in sorted(shown - set(ids))]
    return warnings


def cell(value):
    """Inline Markdown for a GFM table cell."""
    return str(value).replace("|", "\\|").replace("\n", " ")


def titles(data):
    """Each document's title: the overview's, then each phase's."""
    repo = data["repository"]
    phase = {p["flow"]: p.get("title") or f"The loop in {repo}: {p['name'][0].lower()}{p['name'][1:]}"
             for p in data["phases"]}
    return data["overview"].get("title") or f"How the loop runs in {repo}", phase


def documents(data):
    """The overview, then one document per phase, each as (name, title, Uberblick blocks in order)."""
    roles = {r["agent"]: r for r in data["roles"]}
    overview, phase_titles = titles(data)
    docs = [("overview", overview, [("p", data["overview"]["summary"]), ("ablauf", data["overview"]["flow"])]
             + [("li", point) for point in data["overview"]["points"]])]
    for phase in data["phases"]:
        table = [["Agent", "Starts on", "Does"]]
        table += [[f"**{name}** {roles[name].get('kind', 'any')}", ", ".join(f"`{t}`" for t in roles[name]["triggers"]),
                   roles[name]["does"]] for name in phase["roles"]]
        out = [("p", phase["summary"]), ("ablauf", phase["flow"]), ("table", table)]
        out += [("card", {"label": f"{g['id']} · {g['at']} · {g['decides']} decides", "title": g["name"],
                          "body": g["rule"]}) for g in phase["gates"]]
        for section in phase.get("sections", []):
            out += [("h2", section["heading"])] + ([("p", section["text"])] if section.get("text") else [])
            out += [("li", item) for item in section.get("items", [])]
        docs.append((Path(phase["flow"]).stem, phase_titles[phase["flow"]], out + notes(phase)))
    return docs


def notes(obj):
    return [("h2", "Notes")] + [("li", n) for n in obj["notes"]] if obj.get("notes") else []


def combined(data):
    """All documents as one: the overview, then each phase under its own heading."""
    (_, title, out), *phases = documents(data)
    for (_, _, blocks), phase in zip(phases, data["phases"]):
        out = out + [("phase", phase["name"])] + [("h3", v) if k == "h2" else (k, v) for k, v in blocks]
    return [("flow", title, out)]


def markdown(title, blocks, flows):
    """Uberblick Markdown: headings, paragraphs, ablauf fences, GFM tables, cards and list items."""
    parts = [f"# {title}"]
    for kind, value in blocks:
        if kind in ("h2", "phase"):
            parts.append(f"## {value}")
        elif kind == "h3":
            parts.append(f"### {value}")
        elif kind == "p":
            parts.append(value)
        elif kind == "li":
            parts.append(f"- {value}")
        elif kind == "ablauf":
            parts.append("```ablauf\n" + flows[value].strip() + "\n```")
        elif kind == "table":
            head, *rows = value
            parts.append("\n".join(["| " + " | ".join(cell(c) for c in head) + " |",
                                    "|" + "---|" * len(head)]
                                   + ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]))
        elif kind == "card":
            parts.append(f":::card\nlabel: {value['label']}\ntitle: {value['title']}\n\n{value['body']}\n:::")
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


def render(docs, svgs, repository):
    """The page: each document's blocks styled like an Uberblick document, each ablauf fence drawn."""
    articles = []
    for _, title, blocks in docs:
        html_blocks, items = [f"<h1>{inline(title)}</h1>"], []
        for kind, value in blocks:
            if kind != "li" and items:
                html_blocks.append("<ul>" + "".join(items) + "</ul>")
                items = []
            if kind in ("h2", "h3"):
                html_blocks.append(f"<{kind}>{inline(value)}</{kind}>")
            elif kind == "phase":
                html_blocks.append(f'<h2 class="phase">{inline(value)}</h2>')
            elif kind == "p":
                html_blocks.append(f"<p>{inline(value)}</p>")
            elif kind == "li":
                items.append(f"<li>{inline(value)}</li>")
            elif kind == "ablauf":
                html_blocks.append(f'<figure class="ablauf">{svgs.get(value, "")}</figure>')
            elif kind == "table":
                head, *rows = value
                html_blocks.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head)
                                   + "</tr></thead><tbody>"
                                   + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>"
                                             for row in rows)
                                   + "</tbody></table>")
            elif kind == "card":
                html_blocks.append(f'<div class="card"><div class="card-label">{inline(value["label"])}</div>'
                                   f'<div class="card-title">{inline(value["title"])}</div>'
                                   f'<div class="card-body">{inline(value["body"])}</div></div>')
        if items:
            html_blocks.append("<ul>" + "".join(items) + "</ul>")
        articles.append("<article>\n" + "\n".join(html_blocks) + "\n</article>")
    body = "\n".join(articles)
    light = "".join(f"--ab-{k}:{v};" for k, v in LIGHT.items())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Loop flow · {esc(repository)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
/* Uberblick's document tokens and block styles, so the page reads like the documents the Markdown imports as. */
:root{{--background:oklch(0.96 0.008 75);--foreground:oklch(0.145 0 0);--card:oklch(0.97 0.005 75);--muted:oklch(0.97 0 0);
--muted-foreground:oklch(0.511 0 0);--border:oklch(0.922 0 0);--prose-text:oklch(0.3 0 0);--radius:0.625rem;color-scheme:light dark}}
@media (prefers-color-scheme:dark){{:root{{--background:oklch(0.145 0 0);--foreground:oklch(0.985 0 0);--card:oklch(0.205 0 0);
--muted:oklch(0.22 0.01 65);--muted-foreground:oklch(0.708 0 0);--border:oklch(1 0 0 / 10%);--prose-text:oklch(0.92 0 0)}}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--background);color:var(--prose-text);font:16px/27px Geist,system-ui,sans-serif}}
main{{max-width:72ch;margin:0 auto;padding:40px 16px 64px}}
h1,h2,h3{{color:var(--foreground);font-weight:600}}
h1{{font-size:36px;line-height:42px;letter-spacing:-0.021em;margin:0 0 .35em}}
h2{{font-size:22px;line-height:28px;letter-spacing:-0.012em;margin:1.9em 0 .45em}}h3{{font-size:18px;line-height:24px;margin:1.5em 0 .4em}}
article+article{{margin-top:64px;padding-top:40px;border-top:1px solid var(--border)}}
p{{margin:.5em 0}}a{{color:inherit}}strong{{color:var(--foreground);font-weight:600}}
code{{white-space:nowrap;font:.875em "Geist Mono",ui-monospace,monospace;background:var(--muted);border:1px solid var(--border);border-radius:4px;padding:0 4px}}
.ablauf{{margin:12px 0;text-align:center;overflow-x:auto}}.ablauf svg{{max-width:100%;height:auto}}
table{{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px;line-height:20px}}
th,td{{text-align:left;vertical-align:top;padding:6px 8px;border:1px solid var(--border)}}th{{color:var(--foreground);font-weight:600;background:var(--muted)}}
.card{{margin:12px 0;padding:20px 24px;border:1px solid var(--border);border-radius:var(--radius);background:var(--card);break-inside:avoid}}
.card-label{{color:var(--muted-foreground);font-size:12px;line-height:16px;font-weight:500;text-transform:uppercase;letter-spacing:.08em}}
.card-title{{margin-top:6px;color:var(--foreground);font-size:18px;line-height:24px;font-weight:600}}
.card-body{{margin-top:12px}}
ul{{margin:.5em 0;padding-left:1.4em}}
@page{{size:A4;margin:12mm}}
@media print{{:root{{--background:#fff;--foreground:oklch(0.145 0 0);--card:oklch(0.97 0.005 75);--muted:oklch(0.97 0 0);
--muted-foreground:oklch(0.511 0 0);--border:oklch(0.922 0 0);--prose-text:oklch(0.3 0 0)}}
main{{max-width:none;padding:0}}body{{font-size:11px;line-height:16px}}h1{{font-size:22px;line-height:26px}}
h2{{font-size:15px;line-height:20px;margin:1.2em 0 .3em}}h3{{font-size:13px;line-height:18px;margin:1em 0 .3em}}
article+article{{break-before:page;margin-top:0;padding-top:0;border:0}}.phase{{break-before:page;margin-top:0}}
.ablauf svg{{max-height:120mm;width:auto}}.ablauf{{{light}}}table{{font-size:10px;line-height:14px}}th,td{{padding:3px 6px}}
.card{{padding:8px 12px;margin:6px 0}}.card-label{{font-size:8.5px;line-height:12px}}.card-title{{font-size:12px;line-height:16px;margin-top:2px}}.card-body{{margin-top:4px}}}}
</style></head><body><main>
{body}
</main></body></html>
"""


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("report", type=Path, help="flow.json; each .flow and its .svg sit next to it")
    p.add_argument("--out", type=Path, required=True,
                   help="the page; the Uberblick Markdown goes next to it, one file per document")
    p.add_argument("--combine", action="store_true",
                   help="write one document, the overview followed by every phase, as flow.md")
    p.add_argument("--open", action="store_true", help="open the page in the default browser")
    args = p.parse_args(argv)
    try:
        data = json.loads(args.report.read_text(encoding="utf-8"))
        validate(data)
        flows, svgs = {}, {}
        for name in [data["overview"]["flow"]] + [phase["flow"] for phase in data["phases"]]:
            flow = args.report.parent / name
            flows[name] = flow.read_text(encoding="utf-8")
            svg = flow.with_suffix(".svg")
            if not svg.exists():
                raise ValueError(f"no {svg.name}: render {name} with render.mjs first")
            svgs[name] = svg.read_text(encoding="utf-8")
            if not svgs[name].lstrip().startswith("<svg"):
                raise ValueError(f"{svg} is not an SVG; render {name} first")
        warnings = validate(data, flows)
    except (OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    docs = combined(data) if args.combine else documents(data)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(docs, svgs, data["repository"]), encoding="utf-8")
    print(args.out)
    for name, title, blocks in docs:
        md = args.out.parent / f"{name}.md"
        md.write_text(markdown(title, blocks, flows), encoding="utf-8")
        print(md)
    if args.open:
        webbrowser.open(args.out.resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
