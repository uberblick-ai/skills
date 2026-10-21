#!/usr/bin/env python3
"""Score an MCP server from probe.json (+ findings.json) and render the report.

  python3 render.py DIR [--findings FILE] [--baseline OLD/report.json] [--open]

Reads DIR/probe.json (from probe.py) and, when present, DIR/findings.json
(the agent's judged audits and recommendations). Writes DIR/report.json and
DIR/report.html. Standard library only.
"""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import webbrowser
from pathlib import Path

RENDER_VERSION = "0.1"
CATALOG_VERSION = "0.1"
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "report.html"

CATEGORIES = [
    ("protocol", "Protocol", "Does it speak MCP correctly?"),
    ("guidance", "Agent guidance", "Can an agent use it from the text alone?"),
    ("errors", "Error recovery", "When a call goes wrong, does the agent learn how to fix it?"),
    ("context", "Context cost", "How much of the agent's context does it spend?"),
    ("safety", "Safety and trust", "Does it tell the agent what is risky, and resist misuse?"),
]

SPEC = "https://modelcontextprotocol.io/specification/2025-11-25"

# id, category, weight, kind (auto|metric|judged), title, why, fix, surfaces, spec link, critical
CATALOG = [
    # Protocol
    ("P01", "protocol", 10, "auto", "Completes the initialize handshake",
     "Without a valid initialize result no client can use the server at all.",
     "Return protocolVersion, capabilities and serverInfo from initialize.", ["transport"], "/basic/lifecycle", True),
    ("P02", "protocol", 3, "auto", "Speaks a current protocol revision",
     "Older revisions miss structured output, tool annotations and elicitation that clients now rely on.",
     "Upgrade the SDK and negotiate 2025-11-25 (or 2026-07-28 for stateless servers).", ["transport"], "/basic/lifecycle#version-negotiation", False),
    ("P03", "protocol", 4, "auto", "Answers an unknown protocol version with one it supports",
     "The spec requires a counter-offer, so newer clients can fall back instead of failing.",
     "On an unsupported protocolVersion, reply with the newest version the server supports.", ["transport"], "/basic/lifecycle#version-negotiation", False),
    ("P04", "protocol", 8, "auto", "Writes only JSON-RPC to stdout",
     "Any other line on stdout corrupts the stdio stream; clients drop the connection or misparse frames.",
     "Send logs and warnings to stderr; keep stdout for MCP frames only.", ["transport"], "/basic/transports#stdio", True),
    ("P05", "protocol", 5, "auto", "Rejects unknown methods with -32601",
     "Clients probe optional methods and rely on Method not found to tell absent from broken.",
     "Return JSON-RPC error -32601 for methods the server does not implement.", ["transport"], "/basic", False),
    ("P06", "protocol", 2, "auto", "Survives malformed JSON",
     "One bad frame must not take the session down; JSON-RPC asks for a -32700 Parse error.",
     "Answer unparsable input with -32700 (id null) and keep serving.", ["transport"], "/basic", False),
    ("P07", "protocol", 6, "auto", "Declared capabilities match what is served",
     "Clients decide what to call from the capabilities; a mismatch hides features or causes failed calls.",
     "Declare exactly the capabilities whose list methods work.", ["tools", "resources", "prompts"], "/basic/lifecycle#capability-negotiation", False),
    ("P08", "protocol", 2, "auto", "Answers ping",
     "Clients use ping for health checks and keep-alive.",
     "Answer ping with an empty result.", ["transport"], "/basic/utilities/ping", False),
    ("P09", "protocol", 2, "auto", "Lists tools in a stable order",
     "A stable order keeps prompt caches warm and diffs readable.",
     "Return tools in a fixed order on every tools/list.", ["tools"], "/server/tools#listing-tools", False),
    ("P10", "protocol", 2, "auto", "Identifies itself in serverInfo",
     "Name, version and title tell users and logs which build answered.",
     "Fill serverInfo.name, version and title.", ["transport"], "/basic/lifecycle#initialization", False),
    ("P11", "protocol", 4, "auto", "Tool names follow the spec's name format",
     "Names outside [A-Za-z0-9_.-], longer than 128 characters or duplicated break some clients.",
     "Rename tools to 1 to 128 characters of letters, digits, '_', '-' and '.', all unique.", ["tools"], "/server/tools#tool-names", False),
    ("P12", "protocol", 5, "auto", "Input schemas are valid objects",
     "Clients validate arguments and models read the schema; a broken schema means unusable tools.",
     "Give every tool an inputSchema of type object whose required fields exist in properties.", ["tools"], "/server/tools#tool", False),
    ("P13", "protocol", 4, "auto", "Structured results match the output schema",
     "Clients validate structuredContent against outputSchema and drop results that do not match.",
     "Return structuredContent that validates against the declared outputSchema.", ["tools"], "/server/tools#output-schema", False),
    ("P14", "protocol", 3, "auto", "Unknown tools get a clear error",
     "An agent that guessed a tool name needs to learn the name is wrong, not wait for a timeout.",
     "Reject unknown tool names with an error that names the tool.", ["tools", "errors"], "/server/tools#error-handling", False),
    # Agent guidance
    ("G01", "guidance", 4, "auto", "Ships startup instructions",
     "Instructions are the one text a client shows the model before any tool: the cross-tool workflow belongs there.",
     "Add short instructions: the workflow that spans tools, and where help lives.", ["transport"], "/basic/lifecycle#initialization", False),
    ("G02", "guidance", 6, "auto", "Every tool has a real description",
     "The description is how a model picks a tool; a missing or one-line one leads to wrong calls.",
     "Describe each tool in at least two plain sentences: what it does and what it returns.", ["tools"], "/server/tools#tool", False),
    ("G03", "guidance", 6, "auto", "Input fields are described",
     "An undescribed field leaves the model to guess formats, units and meaning.",
     "Add a description to every input field, with format and an example where it can be read several ways.", ["tools"], "/server/tools#tool", False),
    ("G04", "guidance", 2, "auto", "Tools have human-readable titles",
     "Clients show the title to users who approve calls.",
     "Set title on every tool.", ["tools"], "/server/tools#tool", False),
    ("G05", "guidance", 4, "auto", "Tools carry behaviour annotations",
     "readOnlyHint and destructiveHint let clients auto-approve reads and ask before writes.",
     "Set readOnlyHint, destructiveHint, idempotentHint and openWorldHint on every tool.", ["tools"], "/server/tools#tool-annotations", False),
    ("G06", "guidance", 1, "auto", "Tools declare output schemas",
     "An output schema tells the agent what comes back before it calls.",
     "Declare outputSchema for tools with structured results.", ["tools"], "/server/tools#output-schema", False),
    ("G10", "guidance", 10, "judged", "Tool descriptions say what, returns, when not, and the main failure",
     "These four facts let a model choose the right tool and recover from the common mistake without help topics.",
     "Rewrite each description as plain sentences covering the four facts; move syntax to one help topic.", ["tools"], "/server/tools#tool", False),
    ("G11", "guidance", 5, "judged", "Startup instructions orient the agent",
     "A good orientation names the workflow across tools and where to read more, and nothing else.",
     "Rewrite the instructions around the one workflow that spans tools.", ["transport"], "/basic/lifecycle#initialization", False),
    ("G12", "guidance", 4, "judged", "Each format or syntax has one home",
     "Copies of the same rules drift; agents then follow a stale copy.",
     "Keep each syntax in one topic and point to it from tool descriptions.", ["tools", "resources", "prompts"], "", False),
    ("G13", "guidance", 4, "judged", "Examples are true",
     "Agents copy examples literally, including their mistakes.",
     "Check every example against the input schema and the real parser in a test.", ["tools", "resources", "prompts"], "", False),
    ("G14", "guidance", 4, "judged", "No internals or history in model-facing text",
     "Internal function names, version history and future plans cost context and give the agent nothing to act on.",
     "Remove internals, old-client notes and plans from descriptions and help.", ["tools", "resources", "prompts"], "", False),
    ("G15", "guidance", 3, "judged", "Help topics teach editing and errors",
     "Agents fail most on edits and on reading errors; help that only shows creation leaves them guessing.",
     "Give each help topic the same shape: example, syntax, reading, editing, errors.", ["resources", "prompts"], "", False),
    ("G16", "guidance", 5, "judged", "Guidance does not contradict itself or the server",
     "A rule the server does not follow is worse than no rule.",
     "Remove or fix advice that the server's behaviour contradicts.", ["tools", "resources", "prompts"], "", False),
    # Error recovery
    ("E01", "errors", 6, "auto", "Invalid arguments are rejected",
     "A call that breaks the schema must fail, or the server acts on input it does not understand.",
     "Validate arguments against the input schema before running the tool.", ["tools", "errors"], "/server/tools#error-handling", False),
    ("E02", "errors", 6, "auto", "Rejections name the offending field",
     "The agent fixes the call in one retry when the error names the field.",
     "Name the field and what was expected in every validation error.", ["tools", "errors"], "/server/tools#error-handling", False),
    ("E03", "errors", 4, "auto", "Validation errors come back as tool errors",
     "Since 2025-11-25 input validation errors are tool execution errors (isError), so the model sees them and can self-correct.",
     "Return validation failures as a result with isError: true instead of a JSON-RPC error.", ["tools", "errors"], "/server/tools#error-handling", False),
    ("E04", "errors", 2, "auto", "Errors do not leak stack traces",
     "Stack traces cost context and tell the agent nothing it can act on.",
     "Catch exceptions and return a short message with the fix.", ["errors"], "", False),
    ("E10", "errors", 8, "judged", "Errors say how to recover",
     "An error that names the fix or the help topic turns a failed call into a corrected one.",
     "Add the recovery step to each error: the valid values, the field, or the tool or topic that helps.", ["errors"], "/server/tools#error-handling", False),
    ("E11", "errors", 4, "judged", "Errors state the real cause",
     "A wrong cause sends the agent to fix the wrong thing.",
     "Report each failure by what actually went wrong.", ["errors"], "", False),
    ("E12", "errors", 8, "judged", "Writes refuse input they cannot store",
     "A write that silently drops or mangles input is the worst failure: every call reports success.",
     "Refuse writes whose content would be stored differently, and say which part.", ["tools", "errors"], "", True),
    # Context cost
    ("C01", "context", 10, "metric", "Tool list fits the budget",
     "Every tool's name, description and input schema is sent to the model on every turn.",
     "Move syntax and examples into help topics and keep descriptions to plain sentences.", ["tools"], "", False),
    ("C02", "context", 4, "metric", "Startup instructions fit the budget",
     "Instructions are always in context; long ones crowd out the task.",
     "Keep instructions to the cross-tool workflow and a pointer to help.", ["transport"], "", False),
    ("C03", "context", 5, "metric", "Largest tool description fits the budget",
     "A long description usually carries syntax that belongs in a help topic.",
     "Cut the description to what, returns, when not, main failure, and a pointer.", ["tools"], "", False),
    ("C04", "context", 4, "metric", "Largest field description fits the budget",
     "Field descriptions are read on every turn too; long ones are usually tutorials.",
     "Keep field descriptions to meaning, format and one example.", ["tools"], "", False),
    ("C05", "context", 4, "metric", "Largest help topic fits the budget",
     "A topic is read in full when the agent asks; oversized topics push the task out of context.",
     "Split large topics by job and drop pasted schemas.", ["resources", "prompts"], "", False),
    ("C06", "context", 2, "metric", "All help together fits the budget",
     "Total help size is a proxy for duplication and drift.",
     "Remove duplicated syntax and history from help.", ["resources", "prompts"], "", False),
    ("C07", "context", 5, "metric", "Largest read response fits the budget",
     "Responses land in context too; a huge read costs more than the whole tool list.",
     "Page or trim large responses and offer a summary view.", ["tools"], "", False),
    ("C08", "context", 3, "metric", "Starts quickly",
     "Slow starts delay every session and time out some clients.",
     "Defer heavy work until the first call that needs it.", ["transport"], "", False),
    ("C09", "context", 3, "metric", "Little text is repeated across tools",
     "The same sentence in many descriptions is paid for many times.",
     "Say shared rules once, in instructions or a help topic.", ["tools"], "", False),
    # Safety and trust
    ("S01", "safety", 6, "auto", "Risk annotations match what tools do",
     "A write tool marked read-only can be auto-approved; a read tool without the hint asks for needless approval. (Heuristic on tool names.)",
     "Mark read tools readOnlyHint: true, never mark writes read-only, and keep destructiveHint on deleting tools.", ["tools"], "/server/tools#tool-annotations", False),
    ("S02", "safety", 6, "auto", "No instructions aimed at hijacking the model",
     "Text like 'ignore previous instructions' or 'do not tell the user' is how tool poisoning works, and clients flag it.",
     "Remove instructions that reach beyond the tool's own use.", ["tools", "resources", "prompts"], "/server/tools#security-considerations", False),
    ("S03", "safety", 5, "auto", "No secrets in model-facing text",
     "Anything in descriptions or help is sent to the model and its logs.",
     "Remove tokens and keys from descriptions, help and examples.", ["tools", "resources", "prompts"], "", False),
    ("S04", "safety", 5, "auto", "Refuses requests from foreign origins",
     "Local HTTP servers must check Origin, or any web page can drive them (DNS rebinding).",
     "Validate the Origin header and refuse unknown origins with 403.", ["transport"], "/basic/transports#security-warning", False),
    ("S10", "safety", 4, "judged", "Destructive tools need an explicit target",
     "A delete driven by a free-text query can hit more than intended.",
     "Require an id for destructive tools; offer search as a separate read.", ["tools"], "", False),
    ("S11", "safety", 3, "judged", "Risky tools say what is lost and whether it can be undone",
     "An agent asks before acting only when it knows the step is irreversible.",
     "State in the description what the tool removes and how to undo it.", ["tools"], "", False),
]

CRITICAL = {row[0] for row in CATALOG if row[9]}

# Metric thresholds: (good, poor, unit). Good scores 0.9, poor 0.5 (Lighthouse-style log-normal).
BUDGETS = {
    "C01": (50 * 1024, 100 * 1024, "B"),
    "C02": (1500, 3000, "B"),
    "C03": (1000, 2000, "ch"),
    "C04": (400, 800, "ch"),
    "C05": (8 * 1024, 16 * 1024, "B"),
    "C06": (150 * 1024, 300 * 1024, "B"),
    "C07": (25 * 1024, 100 * 1024, "B"),
    "C08": (1500, 6000, "ms"),
    "C09": (0.05, 0.20, "%"),
}

READ_VERBS = r"^(get|list|search|read|find|fetch|query|describe|show|export|lookup|view|count|status|sync_status|backlinks)"
WRITE_VERBS = r"(create|update|delete|remove|set|edit|insert|write|archive|restore|pin|unpin|move|send|post|add|annotate|link|upload|merge|close|toggle|trigger|run|execute)"
DESTRUCTIVE_VERBS = r"(delete|remove|drop|purge|destroy|reset|wipe|archive)"
INJECTION = [
    r"ignore (all |any )?(previous|prior|above) (instructions|messages)",
    r"do not (tell|inform|mention|show) (this )?(to )?the user",
    r"hide (this|it) from the user",
    r"<\s*important\s*>",
    r"\bsystem prompt\b",
    r"exfiltrat",
]
SECRETS = [
    r"ghp_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"\bsk-[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}",
    r"xox[abp]-[A-Za-z0-9-]{10,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"Bearer [A-Za-z0-9._-]{24,}",
]
NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def lognormal_score(value: float, good: float, poor: float) -> float:
    if value <= 0:
        return 1.0
    sigma = (math.log(poor) - math.log(good)) / 1.2815515655446004
    z = (math.log(value) - math.log(poor)) / sigma
    return max(0.0, min(1.0, 0.5 * math.erfc(z / math.sqrt(2))))


def walk_fields(schema, prefix=""):
    """Yield (path, property schema) for every property in an input schema."""
    if not isinstance(schema, dict):
        return
    for name, prop in (schema.get("properties") or {}).items():
        path = f"{prefix}{name}"
        yield path, prop if isinstance(prop, dict) else {}
        if isinstance(prop, dict):
            yield from walk_fields(prop, path + ".")
            if isinstance(prop.get("items"), dict):
                yield from walk_fields(prop["items"], path + "[].")
            for key in ("anyOf", "oneOf", "allOf"):
                for alt in prop.get(key) or []:
                    yield from walk_fields(alt, path + ".")
    for key in ("$defs", "definitions"):
        for dname, d in (schema.get(key) or {}).items():
            yield from walk_fields(d, f"{prefix}${dname}.")


def model_facing(tool: dict) -> dict:
    keep = {k: tool[k] for k in ("name", "title", "description", "inputSchema") if k in tool}
    return keep


def fmt_bytes(n) -> str:
    if n is None:
        return "n/a"
    if n < 1024:
        return f"{n:,} B"
    return f"{n / 1024:,.1f} KB"


def fmt_value(value, unit) -> str:
    if value is None:
        return "not measured"
    if unit == "B":
        return fmt_bytes(value)
    if unit == "ch":
        return f"{value:,} chars"
    if unit == "ms":
        return f"{value / 1000:.1f} s" if value >= 1000 else f"{value} ms"
    if unit == "%":
        return f"{value * 100:.0f}%"
    return str(value)


def fmt_budget(code) -> str:
    good, poor, unit = BUDGETS[code]
    return f"good ≤ {fmt_value(good, unit)}, poor ≥ {fmt_value(poor, unit)}"


def sentences(text: str):
    for s in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        s = s.strip()
        if len(s) >= 60:
            yield s


def compute(probe: dict) -> tuple[dict, dict]:
    """Return (metrics, auto audit results) from probe.json."""
    init = probe.get("initialize") or {}
    tools = probe.get("tools") or []
    probes = probe.get("probes") or {}
    stdio = (probe.get("target") or {}).get("transport") == "stdio"
    m: dict = {}
    r: dict = {}

    def res(code, score, display="", items=None, note="", na=False):
        r[code] = {"score": None if na else round(max(0.0, min(1.0, score)), 2), "display": display,
                   "items": items or [], "note": note, "na": na}

    # --- metrics
    per_tool = []
    for t in tools:
        mf = model_facing(t)
        fields = list(walk_fields(t.get("inputSchema") or {}))
        per_tool.append({
            "name": t.get("name"),
            "title": t.get("title") or (t.get("annotations") or {}).get("title"),
            "description_chars": len(t.get("description") or ""),
            "description_bytes": len((t.get("description") or "").encode("utf-8")),
            "input_schema_bytes": size(t.get("inputSchema") or {}),
            "output_schema_bytes": size(t["outputSchema"]) if t.get("outputSchema") else 0,
            "model_bytes": size(mf),
            "fields": len(fields),
            "fields_described": sum(1 for _, p in fields if (p.get("description") or "").strip()),
            "max_field_desc": max([len(p.get("description") or "") for _, p in fields] or [0]),
            "annotations": t.get("annotations") or {},
        })
    m["tools"] = per_tool
    m["tool_count"] = len(tools)
    m["tool_list_model_bytes"] = sum(p["model_bytes"] for p in per_tool) if tools else 0
    m["tool_list_wire_bytes"] = size(tools)
    instr = init.get("instructions") or ""
    m["instructions_bytes"] = len(instr.encode("utf-8")) if instr else None
    if per_tool:
        top_desc = max(per_tool, key=lambda p: p["description_chars"])
        m["max_tool_desc"] = {"value": top_desc["description_chars"], "where": top_desc["name"]}
        best_field = (0, "")
        for t in tools:
            for path, p in walk_fields(t.get("inputSchema") or {}):
                n = len(p.get("description") or "")
                if n > best_field[0]:
                    best_field = (n, f"{t.get('name')}.{path}")
        m["max_field_desc"] = {"value": best_field[0], "where": best_field[1]}
    topics = [x for x in probe.get("resource_reads") or [] if x.get("text_bytes")]
    topics += [{"uri": f"prompt:{x['name']}", "text_bytes": len((x.get("text") or "").encode("utf-8"))}
               for x in probe.get("prompt_gets") or [] if x.get("text")]
    m["topics"] = [{"uri": x["uri"], "bytes": x["text_bytes"]} for x in topics]
    if topics:
        big = max(topics, key=lambda x: x["text_bytes"])
        m["max_topic"] = {"value": big["text_bytes"], "where": big["uri"]}
        m["total_topics"] = sum(x["text_bytes"] for x in topics)
    calls = [c for c in probe.get("calls") or [] if "bytes" in c]
    if calls:
        big = max(calls, key=lambda c: c["bytes"])
        m["max_response"] = {"value": big["bytes"], "where": big["tool"]}
    m["cold_start_ms"] = probe.get("cold_start_ms")
    seen: dict = {}
    total_text = 0
    for t in tools:
        texts = [t.get("description") or ""] + [p.get("description") or "" for _, p in walk_fields(t.get("inputSchema") or {})]
        for text in texts:
            total_text += len(text.encode("utf-8"))
            for s in sentences(text):
                seen.setdefault(s, []).append(t.get("name"))
    repeated = {s: names for s, names in seen.items() if len(names) > 1}
    dup_bytes = sum(len(s.encode("utf-8")) * (len(names) - 1) for s, names in repeated.items())
    m["duplication"] = {"value": (dup_bytes / total_text) if total_text else 0.0,
                        "examples": sorted(repeated.items(), key=lambda kv: -len(kv[0]) * len(kv[1]))[:5]}

    # --- protocol
    ok = bool(init.get("ok"))
    res("P01", 1 if ok else 0, init.get("protocolVersion") or "failed",
        note="" if ok else f"initialize failed: {json.dumps(init.get('error'))}")
    if not ok:
        return m, r
    pv = init.get("protocolVersion")
    res("P02", 1 if pv in ("2026-07-28", "2025-11-25") else 0.5 if pv == "2025-06-18" else 0, str(pv))
    uv = (probes.get("unknown_version") or {}).get("response") or {}
    if uv.get("kind") == "success" and uv.get("protocolVersion") and uv.get("protocolVersion") != "1999-01-01":
        res("P03", 1, f"offers {uv.get('protocolVersion')}")
    elif uv.get("kind") == "success":
        res("P03", 0, "echoed the unknown version", note="The server accepted 1999-01-01 instead of offering a version it supports.")
    else:
        res("P03", 0, uv.get("kind", "no answer"), note=json.dumps(uv)[:300])
    if stdio:
        noise = probe.get("stdout_noise") or []
        res("P04", 0 if noise else 1, f"{len(noise)} stray lines" if noise else "clean",
            items=[{"item": "stdout", "score": 0, "evidence": n} for n in noise[:5]])
    else:
        res("P04", 0, na=True, note="HTTP transport")
    um = (probes.get("unknown_method") or {}).get("response") or {}
    res("P05", 1 if um.get("code") == -32601 else 0.5 if um.get("kind") == "protocol" else 0,
        f"code {um.get('code')}" if um.get("kind") == "protocol" else um.get("kind", "?"))
    pe = probes.get("parse_error")
    if pe:
        resp = pe.get("response") or {}
        if resp.get("code") == -32700 and pe.get("alive_after"):
            res("P06", 1, "-32700, still serving")
        elif pe.get("alive_after"):
            res("P06", 0.5, "no reply, still serving", note="The server ignored the malformed frame instead of answering -32700.")
        else:
            res("P06", 0, "stopped serving")
    else:
        res("P06", 0, na=True, note="only probed on stdio")
    caps = init.get("capabilities") or {}
    checks = []
    for method, cap in (("tools/list", "tools"), ("resources/list", "resources"), ("prompts/list", "prompts")):
        pr = probes.get(method if method != "tools/list" else "tools_list") or {}
        declared = cap in caps
        err = pr.get("error")
        if declared:
            good = not err
            checks.append({"item": method, "score": 1 if good else 0,
                           "evidence": "declared and works" if good else f"declared but failed: {json.dumps(err)[:200]}"})
        else:
            served = not err and (pr.get("count") or (method == "tools/list" and tools))
            checks.append({"item": method, "score": 0 if served else 1,
                           "evidence": "not declared but served" if served else "not declared, not served"})
    res("P07", sum(c["score"] for c in checks) / len(checks), f"{sum(c['score'] for c in checks)} of {len(checks)}", items=checks)
    ping = probes.get("ping") or {}
    res("P08", 1 if ping.get("ok") else 0, f"{ping.get('ms')} ms" if ping.get("ok") else "no answer")
    tl = probes.get("tools_list") or {}
    if tools:
        res("P09", 1 if tl.get("stable_order") else 0, "stable" if tl.get("stable_order") else "order changes")
    else:
        res("P09", 0, na=True)
    info = init.get("serverInfo") or {}
    res("P10", 0.4 * bool(info.get("name")) + 0.4 * bool(info.get("version")) + 0.2 * bool(info.get("title")),
        " · ".join(str(info.get(k)) for k in ("name", "version", "title") if info.get(k)),
        note="" if info.get("title") else "serverInfo has no title.")
    if tools:
        names = [t.get("name") or "" for t in tools]
        bad = [n for n in names if not NAME_RE.match(n) or names.count(n) > 1]
        res("P11", 1 - len(bad) / len(names), f"{len(names) - len(bad)} of {len(names)}",
            items=[{"item": n, "score": 0, "evidence": "invalid or duplicate name"} for n in bad])
        bad_schema = []
        for t in tools:
            s = t.get("inputSchema")
            problem = None
            if not isinstance(s, dict) or s.get("type") != "object":
                problem = "inputSchema is not type object"
            else:
                props = s.get("properties") or {}
                missing = [x for x in s.get("required") or [] if x not in props]
                if missing:
                    problem = f"required but not in properties: {', '.join(missing)}"
            if problem:
                bad_schema.append({"item": t.get("name"), "score": 0, "evidence": problem})
        res("P12", 1 - len(bad_schema) / len(tools), f"{len(tools) - len(bad_schema)} of {len(tools)}", items=bad_schema)
    else:
        res("P11", 0, na=True)
        res("P12", 0, na=True)
    out_calls = []
    tool_by_name = {t.get("name"): t for t in tools}
    for c in probe.get("calls") or []:
        t = tool_by_name.get(c.get("tool")) or {}
        if t.get("outputSchema") and "bytes" in c and not c.get("isError"):
            if not c.get("has_structured"):
                out_calls.append({"item": c["tool"], "score": 0, "evidence": "outputSchema declared but no structuredContent"})
            elif c.get("schema_problems"):
                out_calls.append({"item": c["tool"], "score": 0, "evidence": "; ".join(c["schema_problems"][:3])})
            else:
                out_calls.append({"item": c["tool"], "score": 1, "evidence": "matches"})
    if out_calls:
        res("P13", sum(x["score"] for x in out_calls) / len(out_calls),
            f"{sum(x['score'] for x in out_calls):.0f} of {len(out_calls)} calls", items=out_calls)
    else:
        res("P13", 0, na=True, note="no calls to tools with an output schema")
    ut = (probes.get("unknown_tool") or {}).get("response") or {}
    if ut.get("kind") in ("tool", "protocol"):
        named = "mcp_insights_no_such_tool" in (ut.get("message") or "")
        res("P14", 1 if named else 0.5, "names the tool" if named else "generic error",
            items=[{"item": "tools/call", "score": 1 if named else 0.5, "evidence": ut.get("message", "")}])
    else:
        res("P14", 0, ut.get("kind", "no answer"))

    # --- guidance
    res("G01", 1 if instr.strip() else 0, fmt_bytes(m["instructions_bytes"]) if instr else "none")
    if tools:
        weak = [p for p in per_tool if p["description_chars"] < 40]
        res("G02", 1 - len(weak) / len(tools), f"{len(tools) - len(weak)} of {len(tools)}",
            items=[{"item": p["name"], "score": 0, "evidence": f"{p['description_chars']} characters"} for p in weak])
        nf = sum(p["fields"] for p in per_tool)
        nd = sum(p["fields_described"] for p in per_tool)
        if nf:
            res("G03", nd / nf, f"{nd} of {nf} fields",
                items=[{"item": p["name"], "score": round(p["fields_described"] / p["fields"], 2),
                        "evidence": f"{p['fields'] - p['fields_described']} of {p['fields']} fields undescribed"}
                       for p in per_tool if p["fields"] and p["fields_described"] < p["fields"]])
        else:
            res("G03", 0, na=True, note="no input fields")
        titled = sum(1 for p in per_tool if p["title"])
        res("G04", titled / len(tools), f"{titled} of {len(tools)}")
        annotated = [p for p in per_tool if "readOnlyHint" in p["annotations"]]
        res("G05", len(annotated) / len(tools), f"{len(annotated)} of {len(tools)}",
            items=[{"item": p["name"], "score": 0, "evidence": "no readOnlyHint"} for p in per_tool if p not in annotated])
        with_out = sum(1 for t in tools if t.get("outputSchema"))
        res("G06", with_out / len(tools), f"{with_out} of {len(tools)}")
    else:
        for code in ("G02", "G03", "G04", "G05", "G06"):
            res(code, 0, na=True)

    # --- errors
    inv = probes.get("invalid_arguments") or []
    if inv:
        rejected = [x for x in inv if (x.get("response") or {}).get("kind") in ("tool", "protocol")]
        res("E01", len(rejected) / len(inv), f"{len(rejected)} of {len(inv)}",
            items=[{"item": x["tool"], "score": 1 if x in rejected else 0,
                    "evidence": f"{x['why']}: " + ((x.get("response") or {}).get("message") or (x.get("response") or {}).get("kind", ""))[:300]}
                   for x in inv])
        named = []
        for x in rejected:
            msg = (x["response"].get("message") or "")
            fields = list((x.get("arguments") or {}).keys()) or ((x.get("why") or "").replace("missing required ", "").split(", "))
            named.append({"item": x["tool"], "score": 1 if any(f and f in msg for f in fields) else 0, "evidence": msg[:300]})
        if named:
            res("E02", sum(n["score"] for n in named) / len(named), f"{sum(n['score'] for n in named)} of {len(named)}", items=named)
        else:
            res("E02", 0, na=True)
        as_tool = [x for x in rejected if x["response"].get("kind") == "tool"]
        if rejected:
            res("E03", len(as_tool) / len(rejected), f"{len(as_tool)} of {len(rejected)} as isError")
        else:
            res("E03", 0, na=True)
    else:
        for code in ("E01", "E02", "E03"):
            res(code, 0, na=True, note="no read-only tool to probe with invalid arguments")
    messages = [((x.get("response") or {}).get("message") or "") for x in inv]
    messages += [ut.get("message") or "", um.get("message") or ""]
    traces = [msg for msg in messages if re.search(r"\n\s+at .+:\d+:\d+|Traceback \(most recent call last\)", msg)]
    res("E04", 0 if traces else 1, f"{len(traces)} with traces" if traces else "clean",
        items=[{"item": "error", "score": 0, "evidence": t[:300]} for t in traces[:3]])

    # --- context
    def metric(code, value, where=""):
        good, poor, unit = BUDGETS[code]
        if value is None:
            res(code, 0, na=True, note="not measured")
            return
        res(code, lognormal_score(value, good, poor), fmt_value(value, unit) + (f" · {where}" if where else ""),
            note=fmt_budget(code))
        r[code]["value"] = value
        r[code]["unit"] = unit
    metric("C01", m["tool_list_model_bytes"] if tools else None)
    metric("C02", m["instructions_bytes"])
    metric("C03", (m.get("max_tool_desc") or {}).get("value"), (m.get("max_tool_desc") or {}).get("where", ""))
    metric("C04", (m.get("max_field_desc") or {}).get("value"), (m.get("max_field_desc") or {}).get("where", ""))
    metric("C05", (m.get("max_topic") or {}).get("value"), (m.get("max_topic") or {}).get("where", ""))
    metric("C06", m.get("total_topics"))
    metric("C07", (m.get("max_response") or {}).get("value"), (m.get("max_response") or {}).get("where", ""))
    metric("C08", m.get("cold_start_ms"))
    if tools:
        metric("C09", m["duplication"]["value"])
        r["C09"]["items"] = [{"item": ", ".join(names[:4]) + (" …" if len(names) > 4 else ""), "score": 0,
                              "evidence": f"{len(names)}× {s[:220]}"} for s, names in m["duplication"]["examples"]]
    else:
        res("C09", 0, na=True)
    if tools:
        r["C01"]["items"] = [{"item": p["name"], "score": None, "evidence": fmt_bytes(p["model_bytes"])}
                             for p in sorted(per_tool, key=lambda p: -p["model_bytes"])[:8]]
    if topics:
        r["C05"]["items"] = [{"item": x["uri"], "score": round(lognormal_score(x["text_bytes"], *BUDGETS["C05"][:2]), 2),
                              "evidence": fmt_bytes(x["text_bytes"])}
                             for x in sorted(topics, key=lambda x: -x["text_bytes"])[:10]]

    # --- safety
    if tools:
        checks = []
        for t in tools:
            name = (t.get("name") or "").lower()
            ann = t.get("annotations") or {}
            ro = ann.get("readOnlyHint")
            if re.search(DESTRUCTIVE_VERBS, name):
                good = ro is not True and ann.get("destructiveHint") is not False
                checks.append({"item": t.get("name"), "score": 1 if good else 0,
                               "evidence": "deleting tool" + ("" if good else f": readOnlyHint={ro}, destructiveHint={ann.get('destructiveHint')}")})
            elif re.search(READ_VERBS, name) and not re.search(WRITE_VERBS, name):
                checks.append({"item": t.get("name"), "score": 1 if ro is True else 0.5,
                               "evidence": "read tool" + ("" if ro is True else ": not marked readOnlyHint")})
            elif re.search(WRITE_VERBS, name):
                checks.append({"item": t.get("name"), "score": 0 if ro is True else 1,
                               "evidence": "write tool" + (": marked readOnlyHint" if ro is True else "")})
        if checks:
            res("S01", sum(c["score"] for c in checks) / len(checks),
                f"{sum(1 for c in checks if c['score'] == 1)} of {len(checks)} consistent",
                items=[c for c in checks if c["score"] < 1])
        else:
            res("S01", 0, na=True, note="no tool name matched the heuristics")
    else:
        res("S01", 0, na=True)
    corpus = [("instructions", instr)] + [(f"tool {t.get('name')}", json.dumps(model_facing(t), ensure_ascii=False)) for t in tools]
    corpus += [(x["uri"], x.get("text") or "") for x in probe.get("resource_reads") or []]
    corpus += [(f"prompt {x['name']}", x.get("text") or "") for x in probe.get("prompt_gets") or []]
    hits = []
    for where, text in corpus:
        for pat in INJECTION:
            mt = re.search(pat, text or "", re.I)
            if mt:
                a = max(0, mt.start() - 60)
                hits.append({"item": where, "score": 0, "evidence": (text[a:mt.end() + 60]).replace("\n", " ")})
    res("S02", 0 if hits else 1, f"{len(hits)} matches" if hits else "none found", items=hits[:8])
    leaks = []
    for where, text in corpus:
        for pat in SECRETS:
            mt = re.search(pat, text or "")
            if mt:
                leaks.append({"item": where, "score": 0, "evidence": mt.group(0)[:8] + "… (redacted)"})
    res("S03", 0 if leaks else 1, f"{len(leaks)} found" if leaks else "none found", items=leaks[:8])
    origin = probes.get("origin")
    if origin:
        st = origin.get("status")
        res("S04", 1 if st in (400, 401, 403) else 0, f"HTTP {st}")
    else:
        res("S04", 0, na=True, note="stdio transport" if stdio else "not probed")
    return m, r


def merge_judged(results: dict, findings: dict) -> list[str]:
    warnings = []
    judged = (findings or {}).get("judged") or {}
    for row in CATALOG:
        code, kind = row[0], row[3]
        if kind != "judged":
            continue
        j = judged.get(code)
        if not j:
            results[code] = {"score": None, "display": "not judged", "items": [], "note": "No finding recorded for this audit.",
                             "na": True, "judged": True, "unjudged": True}
            continue
        if j.get("na"):
            results[code] = {"score": None, "display": "not applicable", "items": [], "note": j.get("reason", ""),
                             "na": True, "judged": True}
            continue
        items = []
        for it in j.get("items") or []:
            s = it.get("score")
            if s is None:
                continue
            if s < 1 and not (it.get("evidence") or "").strip():
                warnings.append(f"{code} {it.get('item')}: score {s} without evidence, not scored")
                continue
            items.append({"item": it.get("item"), "score": float(s), "evidence": it.get("evidence", ""), "fix": it.get("fix", "")})
        if items:
            score = sum(i["score"] for i in items) / len(items)
            display = f"{sum(1 for i in items if i['score'] >= 1)} of {len(items)} pass"
        elif j.get("score") is not None and (j.get("score") >= 1 or (j.get("evidence") or "").strip()):
            score = float(j["score"])
            display = j.get("display") or ""
        else:
            warnings.append(f"{code}: no scored items with evidence")
            results[code] = {"score": None, "display": "not judged", "items": [], "note": "", "na": True, "judged": True, "unjudged": True}
            continue
        results[code] = {"score": round(score, 2), "display": j.get("display") or display, "items": items,
                         "note": j.get("summary", ""), "evidence": j.get("evidence", ""), "na": False, "judged": True}
    return warnings


def score_categories(results: dict) -> dict:
    cats = {}
    for key, name, question in CATEGORIES:
        rows = [row for row in CATALOG if row[1] == key]
        applicable = [(row, results.get(row[0])) for row in rows if results.get(row[0]) and not results[row[0]]["na"]]
        total_w = sum(row[2] for row, _ in applicable)
        if not total_w:
            cats[key] = {"score": None, "name": name, "question": question}
            continue
        raw = sum(row[2] * res["score"] for row, res in applicable) / total_w
        score = round(raw * 100)
        capped = [row[0] for row, res in applicable if row[0] in CRITICAL and res["score"] == 0]
        if capped:
            score = min(score, 49)
        cats[key] = {"score": score, "name": name, "question": question, "capped_by": capped, "weight": total_w}
        for row, res in applicable:
            res["gain"] = round(row[2] * (1 - res["score"]) / total_w * 100, 1)
    return cats


EFFORT = {"S": 1, "M": 2, "L": 3}


def recommendations(results: dict, findings: dict, cats: dict) -> list[dict]:
    recs = []
    covered = set()
    by_code = {row[0]: row for row in CATALOG}
    for rec in (findings or {}).get("recommendations") or []:
        audits = [a for a in rec.get("audits") or [] if a in by_code]
        gain = sum((results.get(a) or {}).get("gain", 0) or 0 for a in audits)
        covered.update(audits)
        cat = rec.get("category") or (by_code[audits[0]][1] if audits else "guidance")
        recs.append({**rec, "audits": audits, "category": cat, "gain": round(gain, 1),
                     "effort": rec.get("effort", "M"), "source": "agent"})
    for row in CATALOG:
        code = row[0]
        res = results.get(code)
        if not res or res["na"] or code in covered or res["score"] is None or res["score"] >= 0.9:
            continue
        action = re.split(r"(?<=[.;])\s", row[6])[0].rstrip(".;")
        recs.append({"title": action, "category": row[1], "audits": [code],
                     "why": row[5], "fix": row[6], "effort": "M" if row[3] == "metric" else "S",
                     "gain": res.get("gain", 0), "source": "catalog"})
    for rec in recs:
        rec["rank_value"] = (rec["gain"] or 0) / EFFORT.get(rec["effort"], 2)
        cname = dict((k, n) for k, n, _ in CATEGORIES).get(rec["category"], rec["category"])
        body = [f"**Category:** {cname}", f"**Estimated gain:** +{rec['gain']} points", "", rec.get("why", ""), "",
                "**Fix**", "", rec.get("fix", "")]
        if rec.get("evidence"):
            body += ["", "**Evidence**", "", rec["evidence"]]
        body += ["", f"Found by mcp-insights ({', '.join(rec['audits'])})."]
        rec["issue"] = {"title": rec.get("issue_title") or rec["title"], "body": "\n".join(body)}
    recs.sort(key=lambda r: -r["rank_value"])
    return recs


def squarify(items, x, y, w, h):
    """items: list of (key, value) sorted desc. Returns list of (key, x, y, w, h)."""
    out = []
    items = [(k, v) for k, v in items if v > 0]
    total = sum(v for _, v in items)
    if not items or total <= 0:
        return out
    scale = w * h / total
    vals = [(k, v * scale) for k, v in items]

    def worst(row, side):
        s = sum(v for _, v in row)
        return max(max(side * side * v / (s * s), (s * s) / (side * side * v)) for _, v in row)

    while vals:
        side = min(w, h)
        row = [vals[0]]
        i = 1
        while i < len(vals) and worst(row + [vals[i]], side) <= worst(row, side):
            row.append(vals[i])
            i += 1
        s = sum(v for _, v in row)
        if w >= h:
            cw = s / h
            cy = y
            for k, v in row:
                rh = v / cw
                out.append((k, x, cy, cw, rh))
                cy += rh
            x += cw
            w -= cw
        else:
            rh = s / w
            cx = x
            for k, v in row:
                cw = v / rh
                out.append((k, cx, y, cw, rh))
                cx += cw
            y += rh
            h -= rh
        vals = vals[i:]
    return out


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def band(score) -> str:
    if score is None:
        return "na"
    s = score * 100 if score <= 1 else score
    return "good" if s >= 90 else "avg" if s >= 50 else "poor"


def gauge_svg(score, size_px=120, stroke=8) -> str:
    r = (size_px - stroke) / 2
    c = 2 * math.pi * r
    frac = (score or 0) / 100
    b = band(score)
    label = "–" if score is None else str(score)
    return (f'<svg class="gauge {b}" viewBox="0 0 {size_px} {size_px}" width="{size_px}" height="{size_px}" aria-hidden="true">'
            f'<circle class="track" cx="{size_px / 2}" cy="{size_px / 2}" r="{r}" stroke-width="{stroke}" fill="none"/>'
            f'<circle class="arc" cx="{size_px / 2}" cy="{size_px / 2}" r="{r}" stroke-width="{stroke}" fill="none" '
            f'stroke-dasharray="{c * frac:.1f} {c:.1f}" transform="rotate(-90 {size_px / 2} {size_px / 2})" stroke-linecap="round"/>'
            f'<text x="50%" y="50%" dy="0.35em" text-anchor="middle">{label}</text></svg>')


def shape(b) -> str:
    return f'<span class="shape {b}" aria-hidden="true"></span>'


def treemap_svg(per_tool) -> str:
    W, H = 960, 360
    items = sorted(((p["name"], p["model_bytes"]) for p in per_tool), key=lambda kv: -kv[1])
    rects = squarify(items, 0, 0, W, H)
    by = {p["name"]: p for p in per_tool}
    parts = [f'<svg class="treemap" viewBox="0 0 {W} {H}" role="img" aria-label="Model-facing tool list bytes by tool">']
    for name, x, y, w, h in rects:
        p = by[name]
        desc_share = p["description_bytes"] / p["model_bytes"] if p["model_bytes"] else 0
        dh = h * desc_share
        tip = f"{name}: {fmt_bytes(p['model_bytes'])} (description {fmt_bytes(p['description_bytes'])}, input schema {fmt_bytes(p['input_schema_bytes'])})"
        parts.append(f'<g><title>{esc(tip)}</title>'
                     f'<rect class="tm-desc" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{dh:.1f}"/>'
                     f'<rect class="tm-schema" x="{x:.1f}" y="{y + dh:.1f}" width="{w:.1f}" height="{h - dh:.1f}"/>'
                     f'<rect class="tm-border" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>')
        if w > 70 and h > 34:
            fit = max(3, int((w - 14) / 7.9))
            label = name if len(name) <= fit else name[:fit - 1] + "\u2026"
            parts.append(f'<text x="{x + 8:.1f}" y="{y + 18:.1f}" class="tm-name">{esc(label)}</text>'
                         f'<text x="{x + 8:.1f}" y="{y + 34:.1f}" class="tm-size">{esc(fmt_bytes(p["model_bytes"]))}</text>')
        elif w > 44 and h > 20:
            parts.append(f'<text x="{x + 5:.1f}" y="{y + 15:.1f}" class="tm-size">{esc(fmt_bytes(p["model_bytes"]))}</text>')
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def render_html(report: dict) -> str:
    cats = report["categories"]
    results = report["audits"]
    m = report["metrics"]
    meta = report["meta"]
    by_code = {row[0]: row for row in CATALOG}
    base = report.get("baseline") or {}

    gauges = []
    for key, name, _ in CATEGORIES:
        c = cats[key]
        delta = ""
        if base.get(key) is not None and c["score"] is not None:
            d = c["score"] - base[key]
            delta = f'<span class="delta {"up" if d > 0 else "down" if d < 0 else ""}">{"+" if d > 0 else ""}{d}</span>'
        gauges.append(f'<a class="gauge-link" href="#{key}">{gauge_svg(c["score"])}<span class="gauge-name">{esc(name)}</span>{delta}</a>')

    vitals_spec = [
        ("C01", "Tool list", "model-facing"),
        ("C02", "Startup instructions", ""),
        ("C03", "Largest tool description", "C03"),
        ("C04", "Largest field description", "C04"),
        ("C07", "Largest read response", "C07"),
        ("C08", "Cold start", "to first answer"),
    ]
    vitals = []
    for code, label, _ in vitals_spec:
        res = results.get(code) or {}
        good, poor, unit = BUDGETS[code]
        value = res.get("value")
        b = band(res.get("score")) if not res.get("na") else "na"
        where = ""
        if code == "C03":
            where = (m.get("max_tool_desc") or {}).get("where", "")
        elif code == "C04":
            where = (m.get("max_field_desc") or {}).get("where", "")
        elif code == "C07":
            where = (m.get("max_response") or {}).get("where", "")
        elif code == "C01":
            where = f"{m.get('tool_count', 0)} tools"
        pos = 0
        if value is not None:
            # position on a log scale from good/4 to poor*2
            lo, hi = math.log(good / 4), math.log(poor * 2)
            pos = max(0, min(100, (math.log(max(value, 1e-9)) - lo) / (hi - lo) * 100))
        g_at = (math.log(good) - math.log(good / 4)) / (math.log(poor * 2) - math.log(good / 4)) * 100
        p_at = (math.log(poor) - math.log(good / 4)) / (math.log(poor * 2) - math.log(good / 4)) * 100
        bar = (f'<div class="scale" aria-hidden="true"><span class="seg good" style="width:{g_at:.1f}%"></span>'
               f'<span class="seg avg" style="width:{p_at - g_at:.1f}%"></span><span class="seg poor" style="width:{100 - p_at:.1f}%"></span>'
               + (f'<span class="pin" style="left:{pos:.1f}%"></span>' if value is not None else "") + "</div>")
        vitals.append(f'<div class="vital {b}"><div class="vital-label">{shape(b)}{esc(label)}</div>'
                      f'<div class="vital-value">{esc(fmt_value(value, unit))}</div>'
                      f'<div class="vital-where">{esc(where)}</div>{bar}'
                      f'<div class="vital-budget">{esc(fmt_budget(code))}</div></div>')

    cat_names = {k: n for k, n, _ in CATEGORIES}
    fixes = []
    for i, rec in enumerate(report["recommendations"][:5], 1):
        gain = f'+{rec["gain"]:g} {esc(cat_names.get(rec["category"], ""))}' if rec.get("gain") else esc(cat_names.get(rec["category"], ""))
        saves = f'<span class="pill">{esc(rec["saves"])}</span>' if rec.get("saves") else ""
        fixes.append(
            f'<article class="fix"><div class="fix-rank">{i}</div><div class="fix-body">'
            f'<div class="fix-meta"><span class="pill cat-{esc(rec["category"])}">{gain}</span>{saves}'
            f'<span class="pill effort">Effort {esc(rec.get("effort", "M"))}</span></div>'
            f'<h3>{esc(rec["title"])}</h3><p>{esc(rec.get("why", ""))}</p>'
            f'<details class="fix-detail"><summary>The fix</summary><pre>{esc(rec.get("fix", ""))}</pre></details>'
            f'<div class="fix-actions"><button type="button" data-copy="{esc(rec.get("fix", ""))}">Copy fix</button>'
            f'<button type="button" data-copy="{esc("# " + rec["issue"]["title"] + chr(10) + chr(10) + rec["issue"]["body"])}">Copy as issue</button></div>'
            f'</div></article>')

    sections = []
    for key, name, question in CATEGORIES:
        c = cats[key]
        rows = [row for row in CATALOG if row[1] == key]
        opps, passed, na = [], [], []
        for row in rows:
            res = results.get(row[0])
            if not res:
                continue
            if res["na"]:
                na.append((row, res))
            elif res["score"] is not None and res["score"] >= 0.9:
                passed.append((row, res))
            else:
                opps.append((row, res))
        opps.sort(key=lambda rr: -(rr[1].get("gain") or 0))
        summary = (report.get("summaries") or {}).get(key, "")
        capped = ""
        if c.get("capped_by"):
            capped = f'<p class="capped">Capped at 49 by a failed critical audit: {esc(", ".join(c["capped_by"]))}.</p>'
        sections.append(
            f'<section class="category" id="{key}"><header class="cat-head">{gauge_svg(c["score"], 72, 6)}'
            f'<div><h2>{esc(name)}</h2><p class="question">{esc(question)}</p>'
            + (f'<p class="cat-summary">{esc(summary)}</p>' if summary else "") + capped + "</div></header>"
            + audit_group("Opportunities", opps, by_code, open_=True, hint="ranked by estimated gain")
            + audit_group(f"Passed audits ({len(passed)})", passed, by_code, folded=True)
            + audit_group(f"Not applicable or not judged ({len(na)})", na, by_code, folded=True)
            + "</section>")

    inventory_rows = []
    for p in m.get("tools") or []:
        ann = p["annotations"]
        flags = " ".join(f'<span class="flag">{esc(lbl)}</span>' for k, lbl in
                         (("readOnlyHint", "read-only"), ("destructiveHint", "destructive"), ("idempotentHint", "idempotent"), ("openWorldHint", "open world"))
                         if ann.get(k))
        fd = f'{p["fields_described"]}/{p["fields"]}' if p["fields"] else "–"
        grade = tool_grade(p, results)
        inventory_rows.append(
            f'<tr><td><code>{esc(p["name"])}</code>' + (f'<div class="sub">{esc(p["title"])}</div>' if p["title"] else "") + "</td>"
            f'<td class="grade g-{grade}" data-v="{"ABCDF".index(grade)}">{grade}</td>'
            f'<td data-v="{p["description_chars"]}">{p["description_chars"]:,}</td>'
            f'<td data-v="{p["input_schema_bytes"]}">{esc(fmt_bytes(p["input_schema_bytes"]))}</td>'
            f'<td data-v="{p["model_bytes"]}">{esc(fmt_bytes(p["model_bytes"]))}</td>'
            f'<td data-v="{p["output_schema_bytes"]}">{esc(fmt_bytes(p["output_schema_bytes"]) if p["output_schema_bytes"] else "–")}</td>'
            f'<td data-v="{p["fields_described"] / p["fields"] if p["fields"] else 1}">{fd}</td><td>{flags}</td></tr>')

    notes = report.get("notes") or {}
    notes_html = ""
    if notes:
        parts = []
        if notes.get("summary"):
            parts.append(f'<p>{esc(notes["summary"])}</p>')
        for title, key in (("Where the reviewer agrees", "agree"), ("Where the reviewer disagrees", "disagree"), ("Not covered by the audits", "missing")):
            if notes.get(key):
                parts.append(f'<h3>{title}</h3><ul>' + "".join(f"<li>{esc(x)}</li>" for x in notes[key]) + "</ul>")
        notes_html = f'<section class="notes" id="notes"><h2>Reviewer notes</h2>{"".join(parts)}</section>'

    warn = ""
    if report.get("warnings"):
        warn = '<div class="warnings"><strong>Run warnings</strong><ul>' + "".join(f"<li>{esc(w)}</li>" for w in report["warnings"]) + "</ul></div>"

    badges = [meta["transport"]]
    if meta.get("judged"):
        badges.append("judged")
    if meta.get("calls"):
        badges.append(f'{meta["calls"]} read calls')
    if meta.get("repo"):
        badges.append("repo")
    template = TEMPLATE.read_text(encoding="utf-8")
    fill = {
        "TITLE": esc(f"MCP Insights: {meta['server_title']}"),
        "SERVER_TITLE": esc(meta["server_title"]),
        "SERVER_META": esc(" · ".join(x for x in (meta.get("server_name"), meta.get("server_version"),
                                                       f"protocol {meta.get('protocol')}", meta.get("target")) if x)),
        "BADGES": "".join(f'<span class="badge">{esc(b)}</span>' for b in badges),
        "DATE": esc(pretty_date(meta["collected_at"])),
        "GAUGES": "".join(gauges),
        "VITALS": "".join(vitals),
        "FIXES": "".join(fixes) or '<p class="empty">Nothing to fix above the noise.</p>',
        "TREEMAP": treemap_svg(m.get("tools") or []) if m.get("tools") else '<p class="empty">No tools.</p>',
        "TREEMAP_NOTE": esc(f"{fmt_bytes(m.get('tool_list_model_bytes'))} model-facing (name, title, description, input schema); "
                            f"{fmt_bytes(m.get('tool_list_wire_bytes'))} on the wire with output schemas and annotations."),
        "SECTIONS": "".join(sections),
        "INVENTORY": "".join(inventory_rows),
        "NOTES": notes_html,
        "WARNINGS": warn,
        "FOOTER": esc(f"mcp-insights probe {meta.get('probe_version')} · render {RENDER_VERSION} · audit catalog {CATALOG_VERSION} · "
                      f"collected {meta['collected_at']} · this is a lab run: one session, one machine"),
    }
    for k, v in fill.items():
        template = template.replace("{{" + k + "}}", v)
    return template


def pretty_date(stamp) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})", stamp or "")
    if not m:
        return stamp or ""
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{int(m[3])} {months[int(m[2]) - 1]} {m[1]}, {m[4]}:{m[5]} UTC"


def tool_grade(p, results) -> str:
    """A to F per tool from its judged description item, field coverage and size."""
    parts = []
    g10 = results.get("G10") or {}
    for it in g10.get("items") or []:
        if it.get("item") == p["name"]:
            parts.append(it["score"])
    parts.append(p["fields_described"] / p["fields"] if p["fields"] else 1)
    parts.append(lognormal_score(p["description_chars"], 1000, 2000))
    parts.append(1 if "readOnlyHint" in p["annotations"] else 0.5)
    s = sum(parts) / len(parts)
    return "A" if s >= 0.9 else "B" if s >= 0.8 else "C" if s >= 0.65 else "D" if s >= 0.5 else "F"


def audit_group(title, rows, by_code, open_=False, folded=False, hint="") -> str:
    if not rows:
        return ""
    items = []
    for row, res in rows:
        code = row[0]
        b = "na" if res["na"] else band(res["score"])
        gain = f'<span class="gain">+{res["gain"]:g}</span>' if res.get("gain") and not res["na"] and res["score"] < 0.9 else ""
        judged = '<span class="tag">judged</span>' if row[3] == "judged" else ""
        crit = '<span class="tag crit">critical</span>' if code in CRITICAL else ""
        spec = f' <a href="{SPEC}{row[8]}" target="_blank" rel="noopener">Spec</a>' if row[8] else ""
        detail = [f'<p class="why">{esc(row[5])}{spec}</p>']
        if res.get("note"):
            detail.append(f'<p class="note">{esc(res["note"])}</p>')
        if res.get("evidence"):
            detail.append(f'<blockquote>{esc(res["evidence"])}</blockquote>')
        its = res.get("items") or []
        if its:
            rows_html = []
            for it in its[:30]:
                ib = "na" if it.get("score") is None else band(it["score"])
                fix = f'<div class="item-fix"><span>Fix</span>{esc(it["fix"])}</div>' if it.get("fix") else ""
                rows_html.append(f'<tr><td>{shape(ib)}</td><td><code>{esc(it.get("item"))}</code></td>'
                                 f'<td>{esc(it.get("evidence", ""))}{fix}</td></tr>')
            more = f'<p class="more">{len(its) - 30} more in report.json</p>' if len(its) > 30 else ""
            detail.append(f'<table class="items"><tbody>{"".join(rows_html)}</tbody></table>{more}')
        if not res["na"] and res["score"] is not None and res["score"] < 0.9:
            detail.append(f'<div class="fixbox"><span>How to fix</span><p>{esc(row[6])}</p></div>')
        items.append(
            f'<details class="audit {b}" data-surfaces="{" ".join(row[7])}"><summary>{shape(b)}'
            f'<span class="audit-title">{esc(row[4])}</span>{judged}{crit}'
            f'<span class="display">{esc(res.get("display", ""))}</span>{gain}<span class="code">{code}</span></summary>'
            f'<div class="audit-body">{"".join(detail)}</div></details>')
    head = f'<h3 class="group-title">{esc(title)}' + (f' <span class="hint">{esc(hint)}</span>' if hint else "") + "</h3>"
    body = "".join(items)
    if folded:
        return f'<details class="group"><summary>{esc(title)}</summary>{body}</details>'
    return f'<div class="group">{head}{body}</div>'


def build(dir_: Path, findings_path: Path | None, baseline_path: Path | None) -> dict:
    probe = json.loads((dir_ / "probe.json").read_text(encoding="utf-8"))
    findings = {}
    fp = findings_path or (dir_ / "findings.json")
    if fp and fp.exists():
        findings = json.loads(fp.read_text(encoding="utf-8"))
    metrics, results = compute(probe)
    warnings = merge_judged(results, findings) if (probe.get("initialize") or {}).get("ok") else []
    cats = score_categories(results)
    recs = recommendations(results, findings, cats)
    init = probe.get("initialize") or {}
    info = init.get("serverInfo") or {}
    target = probe.get("target") or {}
    baseline = {}
    if baseline_path and baseline_path.exists():
        old = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline = {k: v.get("score") for k, v in (old.get("categories") or {}).items()}
    unjudged = [code for code, r in results.items() if r.get("unjudged")]
    if unjudged and findings:
        warnings.append(f"not judged: {', '.join(sorted(unjudged))}")
    elif not findings:
        warnings.append("No findings.json: judged audits are missing, so Agent guidance, Error recovery and Safety rest on the automatic checks only.")
    return {
        "meta": {
            "server_title": info.get("title") or target.get("label") or info.get("name") or "MCP server",
            "server_name": info.get("name"), "server_version": info.get("version"),
            "protocol": init.get("protocolVersion"), "transport": target.get("transport"),
            "target": target.get("label") or target.get("url") or "",
            "collected_at": probe.get("collected_at"), "probe_version": probe.get("probe_version"),
            "render_version": RENDER_VERSION, "catalog_version": CATALOG_VERSION,
            "judged": bool(findings), "calls": len([c for c in probe.get("calls") or [] if "bytes" in c]),
            "repo": bool((findings or {}).get("repo")),
        },
        "categories": cats,
        "audits": results,
        "metrics": {k: v for k, v in metrics.items()},
        "recommendations": recs,
        "summaries": (findings or {}).get("summaries") or {},
        "notes": (findings or {}).get("notes") or {},
        "baseline": baseline,
        "warnings": warnings,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir", help="directory with probe.json")
    ap.add_argument("--findings", help="findings.json (default DIR/findings.json)")
    ap.add_argument("--baseline", help="an earlier report.json to compare against")
    ap.add_argument("--open", action="store_true", help="open the report in the browser")
    args = ap.parse_args(argv)
    d = Path(args.dir)
    if not (d / "probe.json").exists():
        print(f"error: {d / 'probe.json'} is missing; run probe.py collect first", file=sys.stderr)
        return 1
    try:
        report = build(d, Path(args.findings) if args.findings else None, Path(args.baseline) if args.baseline else None)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"error: cannot read the inputs: {exc}", file=sys.stderr)
        return 1
    (d / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    (d / "report.html").write_text(render_html(report), encoding="utf-8")
    scores = " · ".join(f"{c['name']} {c['score'] if c['score'] is not None else '-'}" for c in report["categories"].values())
    print(f"{report['meta']['server_title']}: {scores}")
    for w in report["warnings"]:
        print(f"warning: {w}")
    print(f"report: {(d / 'report.html').resolve()}")
    if args.open:
        webbrowser.open((d / "report.html").resolve().as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
