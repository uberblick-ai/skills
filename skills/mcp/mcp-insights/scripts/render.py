#!/usr/bin/env python3
"""Score an MCP server from probe.json (+ findings.json) and render the report.

  python3 render.py DIR [--findings FILE] [--baseline OLD/report.json] [--open]

Reads DIR/probe.json (from probe.py) and, when present, DIR/findings.json
(the agent's judged audits and recommendations). Writes DIR/report.json and
DIR/report.html. Standard library only.
"""

from __future__ import annotations

import argparse
import fnmatch
import html
import json
import math
import re
import sys
import webbrowser
from pathlib import Path

RENDER_VERSION = "0.2"
CATALOG_VERSION = "0.2"
HERE = Path(__file__).resolve().parent
TEMPLATE = HERE.parent / "assets" / "report.html"
sys.path.insert(0, str(HERE))
from probe import TOKEN_ESTIMATOR, estimate_tokens  # noqa: E402

CATEGORIES = [
    ("protocol", "Protocol", "Does it speak MCP correctly?"),
    ("guidance", "Agent guidance", "Can an agent use it from the text alone?"),
    ("errors", "Error recovery", "When a call goes wrong, does the agent learn how to fix it?"),
    ("context", "Context cost", "How much of the agent's context does it spend?"),
    ("safety", "Safety and trust", "Does it tell the agent what is risky, and resist misuse?"),
]

SPEC = "https://modelcontextprotocol.io/specification/2025-11-25"

# id, category, weight, kind (auto|metric|judged|waste|trial), title, why, fix, surfaces, spec link, critical
CATALOG = [
    # Protocol
    ("P01", "protocol", 10, "auto", "Completes a handshake clients understand",
     "Without a valid initialize result (up to 2025-11-25) or server/discover result (2026-07-28) no client can use the server at all.",
     "Return protocolVersion, capabilities and serverInfo from initialize, or implement server/discover.", ["transport"], "/basic/lifecycle", True),
    ("P02", "protocol", 3, "auto", "Speaks a current protocol revision",
     "2025-11-25 is the most widely adopted revision and 2026-07-28 the newest; older ones miss structured output, annotations and elicitation.",
     "Upgrade the SDK and negotiate 2025-11-25; add 2026-07-28 (stateless) when your SDK supports it.", ["transport"], "/basic/lifecycle#version-negotiation", False),
    ("P03", "protocol", 4, "auto", "Answers an unknown protocol version with one it supports",
     "Up to 2025-11-25 the server must counter-offer a version in initialize; under 2026-07-28 it must reply UnsupportedProtocolVersionError (-32022) listing data.supported.",
     "On an unsupported version, counter-offer in initialize, or return -32022 with the supported versions.", ["transport"], "/basic/lifecycle#version-negotiation", False),
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
    ("P08", "protocol", 1, "auto", "Answers ping",
     "Clients up to 2025-11-25 use ping for health checks. 2026-07-28 deprecates ping, so it is not checked there.",
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
    ("P15", "protocol", 3, "auto", "Missing resources get the right error code",
     "Clients branch on the code: -32002 Resource not found up to 2025-11-25, -32602 under 2026-07-28 (SEP-2164).",
     "Answer resources/read for an unknown URI with the code of the negotiated revision.", ["resources", "errors"], "/server/resources#error-handling", False),
    ("P16", "protocol", 3, "auto", "List results carry cache hints (2026-07-28)",
     "Stateless servers must say how long list and read results stay valid (ttlMs, cacheScope) so clients can cache them.",
     "Return ttlMs and cacheScope on server/discover, list and read results.", ["tools", "resources", "prompts"], "", False),
    ("P17", "protocol", 1, "auto", "Avoids features deprecated in 2026-07-28",
     "Logging, sampling, roots and ping are deprecated in 2026-07-28; servers should log to stderr and not depend on them.",
     "Drop the logging capability and log to stderr; avoid depending on sampling and roots.", ["transport"], "", False),
    # Agent guidance
    ("G01", "guidance", 4, "auto", "Ships startup instructions",
     "Instructions are the one text a client shows the model before any tool: the cross-tool workflow belongs there.",
     "Add short instructions: the workflow that spans tools, and where help lives.", ["transport"], "/basic/lifecycle#initialization", False),
    ("G07", "guidance", 3, "auto", "Startup instructions fit what clients show",
     "Claude Code shows only about the first 2 KB of the instructions; anything after that never reaches the model.",
     "Keep instructions under 2 KB, with the workflow and the help topic names first.", ["transport"], "", False),
    ("G08", "guidance", 2, "auto", "No code leftovers in tool text",
     "Docstring sections (Args:, Returns:, ctx:), type hints and TODOs describe the implementation, not the tool, and cost context on every turn.",
     "Write descriptions for the model: drop docstring sections, internal arguments the client never sends, and notes for developers.", ["tools"], "", False),
    ("G02", "guidance", 6, "auto", "Every tool has a real description",
     "The description is how a model picks a tool; a missing or one-line one leads to wrong calls.",
     "Give each tool a description that says what it does and what it returns, not just its name again.", ["tools"], "/server/tools#tool", False),
    ("G03", "guidance", 6, "auto", "Input fields are described",
     "An undescribed field leaves the model to guess formats, units and meaning.",
     "Add a description to every input field, with format and an example where it can be read several ways.", ["tools"], "/server/tools#tool", False),
    ("G04", "guidance", 1, "auto", "Tools have human-readable titles",
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
    # Agent trials: a fresh headless agent with only this server, one trial per open question
    ("G17", "guidance", 6, "trial", "Agents read help before the tools that need it",
     "In trials that need the server's syntax, a fresh agent should find the right help on its own before the first call that depends on it.",
     "Name the topic to read first in the instructions and in each syntax-heavy tool's description.", ["tools", "resources", "transport"], "", False),
    ("G18", "guidance", 2, "trial", "Plain tasks need no help",
     "Most tools should work from their description alone; reading help for a simple read costs context every time.",
     "Put what a simple call needs into its description and keep help for syntax and workflows.", ["tools"], "", False),
    ("G19", "guidance", 5, "trial", "Fresh agents complete the tasks",
     "The end-to-end test of guidance: a new agent with only this server finishes a realistic task correctly. Judged from the transcript.",
     "Read the failed trial's transcript and fix the description, help or error that misled the agent.", ["tools", "resources"], "", False),
    ("G20", "guidance", 3, "trial", "Agents follow the server's written rules",
     "Rules like 'read before you edit' only help if a fresh agent actually follows them.",
     "Move the rule into the description of the tool it guards, as a precondition.", ["tools", "transport"], "", False),
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
    ("E05", "errors", 5, "auto", "Failed calls are flagged as errors",
     "A result that says \"error\" or \"HTTP 404\" with isError false reads as success to the client, so the agent may report a failure as an answer.",
     "Set isError: true on every failed call, with the cause and the fix in the text.", ["tools", "errors"], "/server/tools#error-handling", False),
    ("E10", "errors", 8, "judged", "Errors say how to recover",
     "An error that names the fix or the help topic turns a failed call into a corrected one.",
     "Add the recovery step to each error: the valid values, the field, or the tool or topic that helps.", ["errors"], "/server/tools#error-handling", False),
    ("E11", "errors", 4, "judged", "Errors state the real cause",
     "A wrong cause sends the agent to fix the wrong thing.",
     "Report each failure by what actually went wrong.", ["errors"], "", False),
    ("E12", "errors", 8, "judged", "Writes never store something else silently",
     "A write that silently drops or mangles input is the worst failure: every call reports success.",
     "Return the checker's diagnostics with the write result, naming the part that will not round-trip; refuse only when nothing sensible can be stored.", ["tools", "errors"], "", True),
    ("E13", "errors", 3, "trial", "Agents recover from errors in one step",
     "In trials, an error should tell the agent enough to get the next call right.",
     "Put the valid values or the corrected call in the error text.", ["tools", "errors"], "", False),
    # Context cost
    ("P18", "protocol", 1, "auto", "Schemas use the default JSON Schema dialect",
     "Since 2025-11-25 tool schemas default to JSON Schema 2020-12; an explicit older $schema still works but some clients validate it differently.",
     "Emit 2020-12 schemas, or drop the $schema line.", ["tools"], "/server/tools#tool", False),
    ("C01", "context", 7, "metric", "Tool list fits the budget",
     "Clients that load every tool send each one's name, description and input schema with every request; clients with tool search pay it per tool the agent picks.",
     "Move syntax and examples into help topics and keep descriptions to plain sentences.", ["tools"], "", False),
    ("C02", "context", 3, "metric", "Startup instructions fit the budget",
     "Instructions are always in context; long ones crowd out the task.",
     "Keep instructions to the cross-tool workflow and a pointer to help.", ["transport"], "", False),
    ("C03", "context", 3, "metric", "Largest tool description fits the budget",
     "A long description usually carries syntax that belongs in a help topic.",
     "Cut the description to what, returns, when not, main failure, and a pointer.", ["tools"], "", False),
    ("C04", "context", 2, "metric", "Largest field description fits the budget",
     "Field descriptions are read on every turn too; long ones are usually tutorials.",
     "Keep field descriptions to meaning, format and one example.", ["tools"], "", False),
    ("C05", "context", 3, "metric", "Largest help topic fits the budget",
     "A topic is read in full when the agent asks; oversized topics push the task out of context.",
     "Split large topics by job and drop pasted schemas.", ["resources", "prompts"], "", False),
    ("C06", "context", 1, "metric", "All help together fits the budget",
     "Total help size is a proxy for duplication and drift.",
     "Remove duplicated syntax and history from help.", ["resources", "prompts"], "", False),
    ("C13", "context", 5, "auto", "Large reads can be bounded",
     "Some reads are large by nature, like a long document; what matters is whether the agent can ask for less. A read over 8k tokens with no limit, page, field selection or filter can fill the context in one call.",
     "Give large reads a way to narrow them (a limit with a cursor, a field or name selection, a filter or range) and keep the default small.", ["tools"], "", True),
    ("C08", "context", 3, "metric", "Starts quickly",
     "Slow starts delay every session and time out some clients.",
     "Defer heavy work until the first call that needs it.", ["transport"], "", False),
    ("C09", "context", 3, "metric", "Little text is repeated across tools",
     "The same sentence in many descriptions is paid for many times.",
     "Say shared rules once, in instructions or a help topic.", ["tools"], "", False),
    ("C10", "context", 8, "waste", "Always-loaded text earns its place",
     "Instructions, tool and field descriptions are paid for on every turn. A long text that is all signal beats a short one full of filler, so this measures waste, not length.",
     "Cut the quoted spans: repetition, internals, history, restated schema and filler.", ["tools", "transport"], "", False),
    ("C11", "context", 3, "waste", "Help topics earn their size",
     "Topics are read on demand, but every wasted paragraph is read in full each time.",
     "Cut the quoted spans from the help topics.", ["resources", "prompts"], "", False),
    ("C12", "context", 3, "metric", "Help does not paste JSON schemas",
     "The client already has every tool's schema; a schema pasted into help is paid again each time the topic is read and drifts from the real one.",
     "Replace pasted schemas with one example call, the fields that need explaining, and a pointer to the tool.", ["resources", "prompts"], "", False),
    # Safety and trust
    ("S01", "safety", 6, "auto", "Risk annotations match what tools do",
     "A write tool marked read-only can be auto-approved; a read tool without the hint asks for needless approval. (Heuristic on tool names.)",
     "Mark read tools readOnlyHint: true, never mark writes read-only, and keep destructiveHint on deleting tools.", ["tools"], "/server/tools#tool-annotations", False),
    ("S02", "safety", 6, "auto", "No instructions aimed at hijacking the model",
     "Text like 'ignore previous instructions' or 'do not tell the user' is how tool poisoning works, and clients flag it.",
     "Remove instructions that reach beyond the tool's own use.", ["tools", "resources", "prompts"], "/server/tools#security-considerations", False),
    ("S03", "safety", 8, "auto", "No secrets in anything the model reads",
     "Descriptions, help, resources and tool results are sent to the model, its logs and every agent session that loads the server. The probe redacts what it finds before writing to disk and keeps only names and lengths.",
     "Stop returning the value: mask it in the resource or response, or drop the resource. Rotate any key that was exposed.", ["tools", "resources", "prompts"], "", True),
    ("S04", "safety", 5, "auto", "Refuses requests from foreign origins",
     "Local HTTP servers must check Origin, or any web page can drive them (DNS rebinding).",
     "Validate the Origin header and refuse unknown origins with 403.", ["transport"], "/basic/transports#security-warning", False),
    ("S10", "safety", 4, "judged", "Destructive tools need an explicit target",
     "A delete driven by a free-text query can hit more than intended.",
     "Require an id for destructive tools; offer search as a separate read.", ["tools"], "", False),
    ("S11", "safety", 3, "judged", "Risky tools say what is lost and whether it can be undone",
     "An agent asks before acting only when it knows the step is irreversible.",
     "State in the description what the tool removes and how to undo it.", ["tools"], "", False),
    ("S12", "safety", 5, "judged", "Tools that look like reads cannot write",
     "A query or get tool that also accepts mutations, or a tool that changes credentials, slips past an agent's and a client's caution.",
     "Split writes into their own tool with honest annotations, or refuse mutations in the read tool.", ["tools"], "", True),
]

CRITICAL = {row[0] for row in CATALOG if row[9]}
# Audits measured on the data the server returned during the review, not on
# the server alone: the same server scores differently on a busier workspace.
DATA_DEPENDENT = {"C13": "Judged on the reads that came back over 8k tokens on this workspace; a busier workspace may show more."}
# Audits that are only shown, never scored.
BIG_READ, HUGE_READ = 8000, 32_000  # tokens: a read worth bounding, and one that floods a context
NARROW_WORDS = {"limit", "max", "page", "cursor", "offset", "after", "before", "top", "first", "last", "count", "size",
                "field", "fields", "select", "column", "columns", "properties", "include", "exclude", "range", "since",
                "until", "from", "to", "start", "end", "filter", "filters", "query", "where", "depth", "summary",
                "truncate", "names", "ids", "keys", "types", "metrics", "bytes", "lines", "window", "period", "section",
                "format", "view", "detail", "verbosity"}
HELP_WORDS = re.compile(r"help|guide|docs?\b|documentation|manual|readme|instruction|tutorial|how-?to|syntax|reference|faq|usage|example|cheat", re.I)
PROVISIONAL = 0.8  # categories with less of their applicable weight checked are marked provisional

# Metric thresholds: (good, poor, unit). Good scores 0.9, poor 0.5 (Lighthouse-style log-normal).
# Calibrated 2026-10-21 on 15 servers (13 public, the reference server, Uberblick):
# good is about the 75th percentile, poor about the 90th. Sizes are effective
# sizes: text the reviewer quoted as waste counts twice. Context sizes are in
# Claude tokens (probe.estimate_tokens); single texts are in characters.
BUDGETS = {
    "C01": (10_000, 20_000, "tok"),
    "C02": (500, 1000, "tok"),
    "C03": (1000, 2000, "ch"),
    "C04": (300, 600, "ch"),
    "C05": (2500, 5000, "tok"),
    "C06": (50_000, 100_000, "tok"),
    "C08": (1000, 3500, "ms"),
    "C09": (0.05, 0.20, "%"),
    "C10": (0.05, 0.25, "%"),
    "C11": (0.10, 0.35, "%"),
    "C12": (0.05, 0.25, "%"),
}
LEFTOVERS = (r"^\s*(Args|Arguments|Parameters|Returns|Raises|Yields|Example usage):\s*$|\bctx\s*:\s*\w|\bself\b\.|"
             r"\b(TODO|FIXME|XXX)\b|\bOptional\[|\bList\[|->\s*(dict|str|list|None)\b|:param \w+:|@param\b|:returns?:")
INSTRUCTIONS_SHOWN = 2048  # bytes of instructions Claude Code shows (Uberblick's help review, 2026-10-21)

READ_VERBS = r"^(get|list|search|read|find|fetch|query|describe|show|export|lookup|view|count|status|sync status|backlinks)\b"
WRITE_VERBS = r"\b(create|update|delete|remove|set|edit|insert|write|archive|restore|pin|unpin|move|send|post|add|annotate|link|upload|merge|close|toggle|trigger|run|execute)\b"
DESTRUCTIVE_VERBS = r"\b(delete|remove|drop|purge|destroy|reset|wipe|archive)\b"
# Audits that match on names or patterns rather than behaviour: a hit is a lead to verify, not a proven defect.
HEURISTIC = {"S01": "Matched on tool names, not on what the tools do: a hit is a lead to check, not a verified defect.",
             "G08": "Matched on wording patterns: check each hit in context."}
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


def schema_bytes(text: str) -> int:
    """Bytes of JSON Schema pasted into a help text: fenced blocks or bare objects that declare properties or types."""
    total, seen = 0, []
    for mt in re.finditer(r"```(?:json|jsonc)?\s*\n(.*?)```", text, re.S):
        body = mt.group(1)
        if re.search(r'"(properties|additionalProperties|\$schema|inputSchema|outputSchema)"\s*:', body) or \
                len(re.findall(r'"type"\s*:\s*"(object|string|integer|number|boolean|array)"', body)) >= 3:
            total += len(body.encode("utf-8"))
            seen.append(mt.span())
    rest = text
    for a, b in reversed(seen):
        rest = rest[:a] + rest[b:]
    # Unfenced schema: a run of lines dense with "type"/"properties" keys.
    for mt in re.finditer(r'(?:^.*"(?:type|properties|required|items|enum|description)"\s*:.*\n){6,}', rest, re.M):
        total += len(mt.group(0).encode("utf-8"))
    return total


def looks_like_error(text: str) -> bool:
    """A successful result whose body is really a failure."""
    head = text.strip()
    try:
        obj = json.loads(head)
    except ValueError:
        obj = None
    if isinstance(obj, dict) and set(obj) & {"error", "errors"} and not set(obj) & {"data", "result", "results", "items"}:
        return bool(obj.get("error") or obj.get("errors"))
    return bool(re.match(r"(?i)(error\b|http \d{3}\b(?<!http 200)|failed\b|exception\b|unauthorized|forbidden|not found)", head[:120]))


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


def described_in_text(path: str, text: str) -> bool:
    """A field explained in the tool description ("page_guid: The GUID of ...", as in a docstring's Args) reaches the
    model as well as a schema description does."""
    name = re.escape(path.split(".")[-1].replace("[]", ""))
    return bool(re.search(rf"(?m)^\s*[-*]?\s*`?{name}`?\s*(\([^)]*\))?\s*:\s*\S", text))


def model_facing(tool: dict) -> dict:
    keep = {k: tool[k] for k in ("name", "title", "description", "inputSchema") if k in tool}
    return keep


def fmt_bytes(n) -> str:
    if n is None:
        return "n/a"
    if n < 1024:
        return f"{n:,} B"
    return f"{n / 1024:,.1f} KB"


def fmt_tokens(n) -> str:
    if n is None:
        return "n/a"
    if n < 1000:
        return f"{round(n):,} tokens"
    if n < 100_000:
        return f"{n / 1000:,.1f}k tokens"
    return f"{n / 1000:,.0f}k tokens"


def short_tokens(n) -> str:
    return fmt_tokens(n).replace(" tokens", "")


def value_html(value, unit) -> str:
    """A vital's number large and its unit small, so long units don't wrap."""
    text = fmt_value(value, unit)
    num, _, rest = text.partition(" ")
    if value is None or unit not in ("tok", "ch") or not rest:
        return esc(text)
    return f'{esc(num)}<span class="unit">{esc(rest)}</span>'


def fmt_value(value, unit) -> str:
    if value is None:
        return "not measured"
    if unit == "tok":
        return fmt_tokens(value)
    if unit == "B":
        return fmt_bytes(value)
    if unit == "ch":
        return f"{value:,} chars"
    if unit == "ms":
        return f"{value / 1000:.1f} s" if value >= 1000 else f"{value} ms"
    if unit == "%":
        return f"{value * 100:.0f}%"
    return str(value)


# The context vitals: (audit, label, what the (i) explains).
VITALS = [
    ("C01", "Tool list",
     "Name, title, description and input schema of every tool: what a client that loads all tools sends with every request. "
     "Output schemas are left out because clients don't pass them to the model. Clients with tool search, like Claude Code, "
     "load the names first and a tool's full definition once the agent picks it. Effective size counts text quoted as waste twice."),
    ("C10", "Filler",
     "Share of the always-loaded text (startup instructions, tool and field descriptions) that the review quoted as waste: "
     "repetition, internals, history, schema restated in prose, and filler. It measures waste, not length, so a long dense text scores well."),
    ("C02", "Startup instructions",
     "Text the server sends at startup. Clients keep it in the system prompt for the whole session; Claude Code shows only about the first 2 KB."),
    ("C03", "Largest tool description",
     "The longest tool description, in characters. A long description usually carries syntax that belongs in a help topic."),
    ("C08", "Cold start",
     "Time from starting the server to its first answer. Slow starts delay every session, and some clients give up."),
]


def info_html(label: str, text: str, budget: str = "") -> str:
    tail = f"<p>{esc(budget)}</p>" if budget else ""
    return (f'<details class="info"><summary aria-label="About {esc(label)}" title="About {esc(label)}">i</summary>'
            f'<div class="info-pop"><p>{esc(text)}</p>{tail}</div></details>')


def fmt_budget(code) -> str:
    good, poor, unit = BUDGETS[code]
    return f"good ≤ {fmt_value(good, unit)}, poor ≥ {fmt_value(poor, unit)}"


EFFECTIVE_NOTE = ("Effective size counts the text quoted as waste twice, so a dense text can be longer than a "
                  "wasteful one and still score better.")


def budget_bytes(code, bpt) -> str:
    """Token budgets in bytes, for maintainers whose own limits are in KB."""
    good, poor, unit = BUDGETS[code]
    if unit != "tok" or not bpt:
        return ""
    return (f"In this server's text that is about {fmt_bytes(good * bpt)} and {fmt_bytes(poor * bpt)} "
            f"({bpt:.1f} bytes per token; JSON and indented text fit fewer bytes in a token than prose).")


def sentences(text: str):
    for s in re.split(r"(?<=[.!?])\s+|\n+", text or ""):
        s = s.strip()
        if len(s) >= 60:
            yield s


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def text_index(probe: dict) -> dict:
    """Every model-facing text by the id findings.json uses for it."""
    init = probe.get("initialize") or {}
    idx = {}
    if init.get("instructions"):
        idx["instructions"] = init["instructions"]
    for t in probe.get("tools") or []:
        idx[f"tool:{t.get('name')}"] = t.get("description") or ""
        for path, prop in walk_fields(t.get("inputSchema") or {}):
            if prop.get("description"):
                idx[f"field:{t.get('name')}.{path}"] = prop["description"]
    for x in probe.get("resource_reads") or []:
        if x.get("text"):
            idx[f"topic:{x['uri']}"] = x["text"]
    for x in probe.get("prompt_gets") or []:
        if x.get("text"):
            idx[f"topic:prompt:{x['name']}"] = x["text"]
    return idx


def waste_index(probe: dict, findings: dict) -> tuple[dict, list]:
    """Bytes quoted as waste per text id. Quotes must appear in the text."""
    idx = text_index(probe)
    out, problems = {}, []
    for entry in ((findings or {}).get("density") or {}).get("texts") or []:
        tid = entry.get("text_id")
        text = idx.get(tid)
        if text is None:
            problems.append(f"density: unknown text_id {tid}")
            continue
        hay = norm(text)
        spans = []
        kept = []
        for w in entry.get("waste") or []:
            q = norm(w.get("quote"))
            if not q:
                continue
            at = hay.find(q)
            if at < 0:
                problems.append(f"density: quote not found in {tid}: {q[:60]}")
                continue
            spans.append((at, at + len(q)))
            kept.append({"quote": w.get("quote"), "why": w.get("why", "")})
        spans.sort()
        merged = []
        for a, b in spans:
            if merged and a <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], b))
            else:
                merged.append((a, b))
        wasted = sum(len(hay[a:b].encode("utf-8")) for a, b in merged)
        out[tid] = {"bytes": wasted, "chars": sum(b - a for a, b in merged), "total": len(text.encode("utf-8")),
                    "tokens": sum(estimate_tokens(hay[a:b]) for a, b in merged), "total_tokens": estimate_tokens(text),
                    "waste": kept, "clarity": entry.get("clarity"), "note": entry.get("note", "")}
    return out, problems


def is_help(uri: str, probe: dict, findings: dict | None) -> bool:
    """A resource counts as help when the reviewer says so, or its uri, name or description reads like help."""
    f = findings or {}
    if any(fnmatch.fnmatch(uri, g) for g in f.get("data_resources") or []):
        return False
    if any(fnmatch.fnmatch(uri, g) for g in f.get("help_resources") or []):
        return True
    meta = next((x for x in probe.get("resources") or [] if x.get("uri") == uri), {})
    return bool(HELP_WORDS.search(" ".join(str(v) for v in (uri, meta.get("name"), meta.get("title"), meta.get("description")) if v)))


def narrowing_params(tool: dict) -> list[str]:
    """Optional arguments that can make a read smaller: limits, pages, selections, filters, ranges."""
    schema = tool.get("inputSchema") or {}
    required = set(schema.get("required") or [])
    out = []
    for name, prop in (schema.get("properties") or {}).items():
        if name in required:
            continue
        words = {w.lower() for w in re.findall(r"[A-Za-z][a-z]*|[A-Z]+(?![a-z])", name)}
        alts = [prop] + list((prop or {}).get("anyOf") or []) + list((prop or {}).get("oneOf") or [])
        if words & NARROW_WORDS or any(isinstance(a, dict) and a.get("type") == "array" for a in alts):
            out.append(name)
    return out


def compute(probe: dict, findings: dict | None = None) -> tuple[dict, dict]:
    """Return (metrics, auto audit results) from probe.json."""
    waste, waste_problems = waste_index(probe, findings or {})
    judged_waste = bool(waste)
    init = probe.get("initialize") or {}
    tools = probe.get("tools") or []
    probes = probe.get("probes") or {}
    stdio = (probe.get("target") or {}).get("transport") == "stdio"
    m: dict = {}
    r: dict = {}

    def res(code, score, display="", items=None, note="", na=False, untested=False):
        # na: does not apply to this server; untested: applies but could not be checked in this run.
        na = na or untested
        r[code] = {"score": None if na else round(max(0.0, min(1.0, score)), 2), "display": display,
                   "items": items or [], "note": note, "na": na, "untested": untested}

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
            "model_tokens": estimate_tokens(json.dumps(mf, ensure_ascii=False, separators=(",", ":"))),
            "description_tokens": estimate_tokens(t.get("description") or ""),
            "output_schema_tokens": estimate_tokens(json.dumps(t["outputSchema"], ensure_ascii=False, separators=(",", ":")))
                                    if t.get("outputSchema") else 0,
            "fields": len(fields),
            "fields_described": sum(1 for path, p in fields if (p.get("description") or "").strip()
                                    or described_in_text(path, t.get("description") or "")),
            "max_field_desc": max([len(p.get("description") or "") for _, p in fields] or [0]),
            "annotations": t.get("annotations") or {},
            "waste_bytes": (waste.get(f"tool:{t.get('name')}") or {}).get("bytes", 0)
                           + sum(v["bytes"] for k, v in waste.items() if k.startswith(f"field:{t.get('name')}.")),
            "desc_waste_chars": (waste.get(f"tool:{t.get('name')}") or {}).get("chars", 0),
            "waste_tokens": (waste.get(f"tool:{t.get('name')}") or {}).get("tokens", 0)
                            + sum(v["tokens"] for k, v in waste.items() if k.startswith(f"field:{t.get('name')}.")),
        })
    m["tools"] = per_tool
    m["tool_count"] = len(tools)
    m["tool_list_model_bytes"] = sum(p["model_bytes"] for p in per_tool) if tools else 0
    m["tool_list_waste_bytes"] = sum(p["waste_bytes"] for p in per_tool)
    m["tool_list_model_tokens"] = sum(p["model_tokens"] for p in per_tool) if tools else 0
    m["tool_list_waste_tokens"] = sum(p["waste_tokens"] for p in per_tool)
    m["bytes_per_token"] = (m["tool_list_model_bytes"] / sum(p["model_tokens"] for p in per_tool)
                            if tools and sum(p["model_tokens"] for p in per_tool) else 4.0)
    m["tool_list_wire_tokens"] = estimate_tokens(json.dumps(tools, ensure_ascii=False, separators=(",", ":")))
    m["waste_judged"] = judged_waste
    m["waste_problems"] = waste_problems
    m["tool_list_wire_bytes"] = size(tools)
    instr = init.get("instructions") or ""
    m["instructions_bytes"] = len(instr.encode("utf-8")) if instr else None
    m["instructions_waste_bytes"] = (waste.get("instructions") or {}).get("bytes", 0)
    m["instructions_tokens"] = estimate_tokens(instr) if instr else None
    m["instructions_waste_tokens"] = (waste.get("instructions") or {}).get("tokens", 0)
    if per_tool:
        top_desc = max(per_tool, key=lambda p: p["description_chars"] + p["desc_waste_chars"])
        m["max_tool_desc"] = {"value": top_desc["description_chars"], "where": top_desc["name"],
                              "effective": top_desc["description_chars"] + top_desc["desc_waste_chars"]}
        best_field = (0, "", 0)
        for t in tools:
            for path, p in walk_fields(t.get("inputSchema") or {}):
                n = len(p.get("description") or "")
                eff = n + (waste.get(f"field:{t.get('name')}.{path}") or {}).get("chars", 0)
                if eff > best_field[2]:
                    best_field = (n, f"{t.get('name')}.{path}", eff)
        m["max_field_desc"] = {"value": best_field[0], "where": best_field[1], "effective": best_field[2]}
    topics = [dict(x) for x in probe.get("resource_reads") or [] if x.get("text_bytes") and is_help(x["uri"], probe, findings)]
    topics += [{"uri": f"prompt:{x['name']}", "text_bytes": len((x.get("text") or "").encode("utf-8")), "text": x.get("text")}
               for x in probe.get("prompt_gets") or [] if x.get("text")]
    for x in topics:
        # Probes keep the text; without it, assume the help average of 3 bytes per token.
        x["tokens"] = estimate_tokens(x["text"]) if x.get("text") else round(x["text_bytes"] / 3)
    def topic_waste(x):
        return (waste.get(f"topic:{x['uri']}") or {}).get("tokens", 0)
    m["topics"] = [{"uri": x["uri"], "bytes": x["text_bytes"], "tokens": x["tokens"], "waste": topic_waste(x)} for x in topics]
    if topics:
        big = max(topics, key=lambda x: x["tokens"] + topic_waste(x))
        m["max_topic"] = {"value": big["tokens"], "where": big["uri"], "effective": big["tokens"] + topic_waste(big)}
        m["total_topics"] = sum(x["tokens"] for x in topics)
        m["total_topics_waste"] = sum(topic_waste(x) for x in topics)
    calls = [c for c in probe.get("calls") or [] if "bytes" in c]
    for c in calls:
        # Older probes measured the whole result, structuredContent included; JSON averages 2.7 bytes per token.
        c["tokens_est"] = c["tokens"] if "tokens" in c else round(c["bytes"] / 2.7)
    if calls:
        big = max(calls, key=lambda c: c["tokens_est"])
        m["max_response"] = {"value": big["tokens_est"], "where": big["tool"], "bytes": big.get("text_bytes", big["bytes"]),
                             "from_whole_result": "tokens" not in big}
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
    lifecycle = probe.get("lifecycle") or ("legacy" if ok else "none")
    disc = probes.get("discover_first") or {}
    m["lifecycle"] = lifecycle
    label = {"legacy": "initialize (up to 2025-11-25)", "modern": "stateless (2026-07-28)",
             "dual": "both initialize and stateless", "none": "failed"}[lifecycle]
    res("P01", 1 if ok else 0, label,
        note="" if ok else f"initialize failed: {json.dumps(init.get('error'))}")
    if not ok:
        return m, r
    pv = init.get("protocolVersion")
    versions = [pv] + list(disc.get("supportedVersions") or [])
    best = 1 if any(v in ("2026-07-28", "2025-11-25") for v in versions) else 0.5 if "2025-06-18" in versions else 0
    res("P02", best, " + ".join(dict.fromkeys(str(v) for v in versions if v)),
        note="Speaks 2026-07-28 as well." if lifecycle == "dual" else
             "2025-11-25 is the widely adopted baseline; 2026-07-28 support is a plus, not required yet." if pv == "2025-11-25" else "")
    uv = (probes.get("unknown_version") or {}).get("response") or {}
    muv = disc.get("unknown_version") or {}
    if lifecycle == "modern":
        good = muv.get("code") == -32022 and isinstance(muv.get("data"), dict) and muv["data"].get("supported")
        res("P03", 1 if good else 0.5 if muv.get("kind") == "protocol" else 0,
            "-32022 with supported versions" if good else f"code {muv.get('code')}" if muv.get("kind") == "protocol" else muv.get("kind", "no answer"))
    elif uv.get("kind") == "success" and uv.get("protocolVersion") and uv.get("protocolVersion") != "1999-01-01":
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
        if pr.get("repeated_cursor"):
            checks.append({"item": f"{method} paging", "score": 0,
                           "evidence": f"nextCursor repeated after {pr.get('pages')} pages: a client would page forever"})
        elif pr.get("page_limit_hit"):
            checks.append({"item": f"{method} paging", "score": 0.5,
                           "evidence": f"still paging after {pr.get('pages')} pages; the probe stopped there"})
    res("P07", sum(c["score"] for c in checks) / len(checks), f"{sum(c['score'] for c in checks)} of {len(checks)}", items=checks)
    ping = probes.get("ping") or {}
    if lifecycle == "modern":
        res("P08", 0, na=True, note="ping is deprecated in 2026-07-28")
    else:
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
    if tools:
        dialects = []
        for t in tools:
            for key in ("inputSchema", "outputSchema"):
                sch = t.get(key)
                if isinstance(sch, dict) and sch.get("$schema") and "2020-12" not in sch["$schema"]:
                    dialects.append({"item": f"{t.get('name')}.{key}", "score": 0.5, "evidence": sch["$schema"]})
        older = {d["item"].split(".")[0] for d in dialects}
        res("P18", 1 - 0.5 * len(older) / len(tools), f"{len(tools) - len(older)} of {len(tools)} on 2020-12",
            items=dialects[:10] + ([{"item": f"{len(dialects) - 10} more", "score": 0.5, "evidence": ""}] if len(dialects) > 10 else []))
    else:
        res("P18", 0, na=True)
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
        res("P13", 0, na=True, untested=any(t.get("outputSchema") for t in tools), note="no calls to tools with an output schema")
    # Prefer the probe that reached the server's own handler; the other is usually the SDK's answer.
    own = probes.get("resource_not_found_template") or {}
    rnf = own.get("response") or (probes.get("resource_not_found") or {}).get("response")
    if "resources" not in caps or rnf is None:
        res("P15", 0, na=True, untested="resources" in caps, note="no resources capability" if "resources" not in caps else "not probed")
    else:
        want = -32602 if lifecycle == "modern" else -32002
        code = rnf.get("code")
        where = (f"Asked for {own['uri']}, which fits the server's template, so its own handler answered. " if own else
                 "Asked for a URI no template matches; an SDK often answers that before the server's code runs. ")
        res("P15", 1 if code == want or (lifecycle == "dual" and code in (-32002, -32602)) else 0.5 if rnf.get("kind") in ("protocol", "tool") else 0,
            f"code {code}" if code is not None else rnf.get("kind", "?"),
            note=f"{where}Expected {want} for this lifecycle. {rnf.get('message', '')[:200]}")
    if lifecycle in ("modern", "dual"):
        hints = [disc.get("cache") or {}] + [(probes.get(k) or {}).get("cache") or {} for k in ("tools_list", "resources/list", "prompts/list")]
        hints = [h for h in hints if h]
        have = [h for h in hints if h.get("ttlMs") is not None and h.get("cacheScope")]
        res("P16", len(have) / len(hints) if hints else 0, f"{len(have)} of {len(hints)} results")
    else:
        res("P16", 0, na=True, note="only required by 2026-07-28")
    deprecated = [k for k in ("logging",) if k in caps]
    if lifecycle in ("modern", "dual"):
        res("P17", 0.5 if deprecated else 1, ", ".join(deprecated) + " capability declared" if deprecated else "none used",
            note="Logging is deprecated in 2026-07-28." if deprecated else "")
    else:
        res("P17", 0, na=True, note="only applies to servers that speak 2026-07-28")
    ut = (probes.get("unknown_tool") or {}).get("response") or {}
    if ut.get("kind") in ("tool", "protocol"):
        named = "mcp_insights_no_such_tool" in (ut.get("message") or "")
        res("P14", 1 if named else 0.5, "names the tool" if named else "generic error",
            items=[{"item": "tools/call", "score": 1 if named else 0.5, "evidence": ut.get("message", "")}])
    else:
        res("P14", 0, ut.get("kind", "no answer"))

    # --- guidance
    # Prompts are picked by the user, not the model, so they need no pointer in the instructions.
    small = len(tools) <= 3 and not probe.get("resources") and not probe.get("resourceTemplates")
    if instr.strip() or not small:
        res("G01", 1 if instr.strip() else 0, fmt_bytes(m["instructions_bytes"]) if instr else "none")
    else:
        res("G01", 0, na=True, note="Three tools or fewer and no resources: the tool descriptions can carry everything.")
    if tools:
        leftovers = []
        for t in tools:
            mt = re.search(LEFTOVERS, t.get("description") or "", re.M)
            if mt:
                a = max(0, mt.start() - 40)
                leftovers.append({"item": t.get("name"), "score": 0, "evidence": (t.get("description") or "")[a:mt.end() + 60].replace("\n", " ")})
        res("G08", 1 - len(leftovers) / len(tools), f"{len(leftovers)} of {len(tools)} tools" if leftovers else "none", items=leftovers[:12],
            note=HEURISTIC["G08"] if leftovers else "")
    else:
        res("G08", 0, na=True)
    if instr.strip():
        cut = max(0, m["instructions_bytes"] - INSTRUCTIONS_SHOWN)
        res("G07", 1 if not cut else max(0.0, 1 - cut / INSTRUCTIONS_SHOWN), "all shown" if not cut else f"{fmt_bytes(cut)} cut",
            note="" if not cut else "Cut off in Claude Code: " + json.dumps(instr.encode("utf-8")[INSTRUCTIONS_SHOWN:].decode("utf-8", "ignore")[:200]))
    else:
        res("G07", 0, na=True, note="no instructions")
    if tools:
        def restates(t):
            words = set(re.findall(r"[a-z]+", (t.get("description") or "").lower())) - {"a", "an", "the", "of", "to", "for"}
            return words <= set(re.findall(r"[a-z]+", (t.get("name") or "").lower().replace("_", " ")))
        weak = [p for p, t in zip(per_tool, tools) if p["description_chars"] < 20 or restates(t)]
        res("G02", 1 - len(weak) / len(tools), f"{len(tools) - len(weak)} of {len(tools)}",
            items=[{"item": p["name"], "score": 0, "evidence": f"{p['description_chars']} characters" if p["description_chars"] < 20
                    else "only restates the name"} for p in weak])
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
        answered = [c for c in probe.get("calls") or [] if "bytes" in c]
        structured = {c["tool"] for c in answered if c.get("has_structured") or (c.get("text_head") or "").lstrip()[:1] in ("{", "[")}
        by_name = {t.get("name"): t for t in tools}
        if structured:
            with_out = [n for n in structured if (by_name.get(n) or {}).get("outputSchema")]
            res("G06", len(with_out) / len(structured), f"{len(with_out)} of {len(structured)} tools with structured results",
                items=[{"item": n, "score": 0, "evidence": "returns JSON without an outputSchema"} for n in sorted(structured - set(with_out))])
        else:
            res("G06", 0, na=True, untested=not answered, note="no read call returned structured data" if answered else "no read calls")
    else:
        for code in ("G02", "G03", "G04", "G05", "G06"):
            res(code, 0, na=True)

    # --- errors
    inv = probes.get("invalid_arguments") or []
    if inv:
        rejected = [x for x in inv if (x.get("response") or {}).get("kind") in ("tool", "protocol", "client")]
        res("E01", len(rejected) / len(inv), f"{len(rejected)} of {len(inv)}",
            items=[{"item": x["tool"], "score": 1 if x in rejected else 0,
                    "evidence": f"{x['why']}: " + ((x.get("response") or {}).get("message") or (x.get("response") or {}).get("kind", ""))[:300]}
                   for x in inv])
        named = []
        for x in rejected:
            msg = (x["response"].get("message") or "")
            fields = list((x.get("arguments") or {}).keys()) or ((x.get("why") or "").replace("missing required ", "").split(", "))
            # page_size names pageSize as well as pageSize does.
            flat = re.sub(r"[_\W]", "", msg.lower())
            named.append({"item": x["tool"], "score": 1 if any(f and re.sub(r"[_\W]", "", f.lower()) in flat for f in fields) else 0,
                          "evidence": msg[:300]})
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
            res(code, 0, untested=True, note="no read-only tool to probe with invalid arguments")
    messages = [((x.get("response") or {}).get("message") or "") for x in inv]
    messages += [ut.get("message") or "", um.get("message") or ""]
    traces = [msg for msg in messages if re.search(r"\n\s+at .+:\d+:\d+|Traceback \(most recent call last\)", msg)]
    res("E04", 0 if traces else 1, f"{len(traces)} with traces" if traces else "clean",
        items=[{"item": "error", "score": 0, "evidence": t[:300]} for t in traces[:3]])
    answered = [c for c in probe.get("calls") or [] if "bytes" in c]
    if answered:
        hidden = [c for c in answered if not c.get("isError") and looks_like_error(c.get("text_head") or "")]
        res("E05", 1 - len(hidden) / len(answered), f"{len(hidden)} of {len(answered)} hidden" if hidden else "all flagged",
            items=[{"item": c["tool"], "score": 0, "evidence": (c.get("text_head") or "")[:200]} for c in hidden])
    else:
        res("E05", 0, untested=True, note="no read calls")

    # --- context
    def metric(code, value, where="", effective=None):
        good, poor, unit = BUDGETS[code]
        if value is None:
            if code == "C02":
                res(code, 0, na=True, note="no instructions")
            else:
                res(code, 0, untested=True, note="not measured")
            return
        eff = effective if effective is not None else value
        shown = fmt_value(value, unit)
        if eff != value:
            shown += f" ({fmt_value(eff, unit)} effective)"
        note = fmt_budget(code) + "."
        if budget_bytes(code, m.get("bytes_per_token")):
            note += " " + budget_bytes(code, m.get("bytes_per_token"))
        if code in ("C01", "C02", "C03", "C04", "C05", "C06"):
            note += " " + (EFFECTIVE_NOTE if judged_waste else "Waste not judged: raw size only.")
        res(code, lognormal_score(eff, good, poor), shown + (f" \u00b7 {where}" if where else ""), note=note)
        r[code]["value"] = value
        r[code]["effective"] = eff
        r[code]["unit"] = unit
    metric("C01", m["tool_list_model_tokens"] if tools else None, effective=(m["tool_list_model_tokens"] + m["tool_list_waste_tokens"]) if tools else None)
    metric("C02", m["instructions_tokens"], effective=(m["instructions_tokens"] or 0) + m["instructions_waste_tokens"] if instr else None)
    metric("C03", (m.get("max_tool_desc") or {}).get("value"), (m.get("max_tool_desc") or {}).get("where", ""), (m.get("max_tool_desc") or {}).get("effective"))
    metric("C04", (m.get("max_field_desc") or {}).get("value"), (m.get("max_field_desc") or {}).get("where", ""), (m.get("max_field_desc") or {}).get("effective"))
    metric("C05", (m.get("max_topic") or {}).get("value"), (m.get("max_topic") or {}).get("where", ""), (m.get("max_topic") or {}).get("effective"))
    metric("C06", m.get("total_topics"), effective=(m.get("total_topics") or 0) + m.get("total_topics_waste", 0) if topics else None)
    if topics:
        pasted = [(x["uri"], schema_bytes(x.get("text") or "")) for x in topics]
        total_schema = sum(b for _, b in pasted)
        share = total_schema / max(1, sum(x["text_bytes"] for x in topics))
        res("C12", lognormal_score(max(share, 1e-6), *BUDGETS["C12"][:2]),
            f"{fmt_tokens(share * m['total_topics'])} of {fmt_tokens(m['total_topics'])} ({share * 100:.0f}%)",
            items=[{"item": uri, "score": 0, "evidence": f"{fmt_tokens(b / 2.7)} of pasted schema"}
                   for uri, b in sorted(pasted, key=lambda kv: -kv[1]) if b > 1024][:10])
        r["C12"]["value"] = share
    else:
        res("C12", 0, na=True, note="no help topics")
    always = {k: v for k, v in waste.items() if k == "instructions" or k.startswith("tool:") or k.startswith("field:")}
    help_uris = {x["uri"] for x in topics}
    on_demand = {k: v for k, v in waste.items() if k.startswith("topic:") and k[len("topic:"):] in help_uris}
    field_tokens = sum(estimate_tokens(v) for k, v in text_index(probe).items() if k.startswith("field:"))
    n_always = sum(1 for k in text_index(probe) if k == "instructions" or k.startswith(("tool:", "field:")))
    # Both shares divide by the text that was reviewed, so a partial review is a sample, not a pass for the rest.
    always_total = sum(v["total_tokens"] for v in always.values())
    for code, group, total, n_all in (("C10", always, always_total, n_always),
                                      ("C11", on_demand, sum(v["total_tokens"] for v in on_demand.values()), len(topics))):
        if not n_all:
            res(code, 0, na=True, note="no text")
            continue
        if not group or not total:
            res(code, 0, untested=True, note="waste not judged")
            continue
        wasted = sum(v["tokens"] for v in group.values())
        ratio = wasted / total
        good, poor, _ = BUDGETS[code]
        items = []
        for tid, v in sorted(group.items(), key=lambda kv: -kv[1]["tokens"]):
            for w in v["waste"]:
                items.append({"item": tid, "score": 0, "evidence": f"\u201c{norm(w['quote'])[:260]}\u201d \u2014 {w['why']}"})
        res(code, lognormal_score(max(ratio, 1e-6), good, poor), f"{fmt_tokens(wasted)} of {fmt_tokens(total)} ({ratio * 100:.0f}%)",
            items=items, note=f"Share of the reviewed text quoted as waste ({len(group)} of {n_all} texts reviewed); good \u2264 {good * 100:.0f}%, poor \u2265 {poor * 100:.0f}%.")
        r[code]["value"] = wasted
        r[code]["ratio"] = ratio
    m["waste_per_turn"] = {"tokens": sum(v["tokens"] for v in always.values()), "total": always_total,
                           "ratio": (r.get("C10") or {}).get("ratio")}
    if not calls:
        res("C13", 0, untested=True, note="no read calls")
    else:
        biggest: dict = {}
        for c in calls:
            if c["tokens_est"] > BIG_READ and c["tokens_est"] > biggest.get(c["tool"], {}).get("tokens_est", 0):
                biggest[c["tool"]] = c
        by_name = {t.get("name"): t for t in tools}
        items = []
        for name, c in sorted(biggest.items(), key=lambda kv: -kv[1]["tokens_est"]):
            narrow = narrowing_params(by_name.get(name) or {})
            used = [a for a in narrow if a in (c.get("arguments") or {})]
            size_ = fmt_tokens(c["tokens_est"]) + (" (whole result)" if "tokens" not in c else "")
            # The same read narrowed: the largest one, so a headers-only view does not flatter the default.
            narrowed = [o for o in calls if o["tool"] == name and o is not c and not o.get("isError")
                        and any(a in (o.get("arguments") or {}) for a in narrow)]
            alt = max(narrowed, key=lambda o: o["tokens_est"]) if narrowed and not used else None
            if alt and c["tokens_est"] >= 4 * max(alt["tokens_est"], 1) and c["tokens_est"] < HUGE_READ:
                args_ = ", ".join(f"{a}={alt['arguments'][a]}" for a in narrow if a in alt["arguments"])
                score, why = 0.5, (f"{size_} by default, {fmt_tokens(alt['tokens_est'])} with {args_}: "
                                   "the default is the heavy read")
            elif narrow and c["tokens_est"] >= HUGE_READ:
                score, why = 0.5, (f"{size_} even with {', '.join(used)}" if used else
                                   f"{size_} by default; {', '.join(narrow)} can narrow it, but the default returns everything")
            elif narrow:
                score, why = 1, f"{size_}; can narrow with {', '.join(narrow)}"
            elif c["tokens_est"] < HUGE_READ:
                score, why = 0.5, f"{size_}; no way to ask for less"
            else:
                score, why = 0, f"{size_}; no way to ask for less"
            items.append({"item": name, "score": score, "evidence": why})
        if items:
            res("C13", sum(i["score"] for i in items) / len(items), f"{sum(1 for i in items if i['score'] >= 1)} of {len(items)} large reads",
                items=items, note=DATA_DEPENDENT["C13"])
        else:
            res("C13", 0, na=True, note=f"no read over {BIG_READ // 1000}k tokens on this workspace")
    metric("C08", m.get("cold_start_ms"))
    if tools:
        metric("C09", m["duplication"]["value"])
        r["C09"]["items"] = [{"item": ", ".join(names[:4]) + (" …" if len(names) > 4 else ""), "score": 0,
                              "evidence": f"{len(names)}× {s[:220]}"} for s, names in m["duplication"]["examples"]]
    else:
        res("C09", 0, na=True)
    if tools:
        r["C01"]["items"] = [{"item": p["name"], "score": None, "evidence": fmt_tokens(p["model_tokens"])}
                             for p in sorted(per_tool, key=lambda p: -p["model_tokens"])[:8]]
    if topics:
        r["C05"]["items"] = [{"item": x["uri"], "score": round(lognormal_score(x["tokens"], *BUDGETS["C05"][:2]), 2),
                              "evidence": fmt_tokens(x["tokens"])}
                             for x in sorted(topics, key=lambda x: -x["tokens"])[:10]]

    # --- agent trials
    runs = [t for t in (probe.get("trials") or {}).get("runs") or [] if not t.get("invalid")]
    verdicts = (findings or {}).get("trials") or {}
    if runs:
        helpy = [t for t in runs if t.get("expects_help") is True and t.get("help_before_use") is not None]
        if helpy:
            res("G17", sum(1 for t in helpy if t["help_before_use"]) / len(helpy),
                f"{sum(1 for t in helpy if t['help_before_use'])} of {len(helpy)} trials",
                items=[{"item": t["id"], "score": 1 if t["help_before_use"] else 0,
                        "evidence": f"{t['help_reads']} help reads ({help_size(t)}) "
                                    + ("before" if t["help_before_use"] else "none before") + f" the first {'/'.join(t['needs'])} call"}
                       for t in helpy])
        else:
            res("G17", 0, na=True, note="no trial used a tool that needs help")
        plain = [t for t in runs if t.get("expects_help") is False]
        if plain:
            res("G18", sum(1 for t in plain if not t["help_reads"]) / len(plain),
                f"{sum(1 for t in plain if not t['help_reads'])} of {len(plain)} without help",
                items=[{"item": t["id"], "score": 0 if t["help_reads"] else 1,
                        "evidence": f"{t['calls']} calls, {t['help_reads']} help reads ({help_size(t)})"} for t in plain])
        else:
            res("G18", 0, na=True, note="no plain-task trial")
        judged_runs = []
        for t in runs:
            v = verdicts.get(t["id"]) if isinstance(verdicts.get(t["id"]), dict) else {}
            o = trial_outcome(t, v)
            # Blocked and declined runs say nothing about the server; anything short of done needs evidence.
            if o is None or o in UNCOUNTED_OUTCOMES or (o != "done" and not (v.get("evidence") or "").strip()):
                continue
            judged_runs.append((t, v, o, outcome_score(o, v)))
        if judged_runs:
            done = sum(1 for *_, o, _ in judged_runs if o == "done")
            drafted = sum(1 for *_, o, _ in judged_runs if o == "drafted")
            res("G19", sum(sc for *_, sc in judged_runs) / len(judged_runs),
                f"{done} of {len(judged_runs)} done" + (f", {drafted} drafted" if drafted else ""),
                items=[{"item": t["id"], "score": sc, "evidence": f"{OUTCOMES[o]}. {v.get('evidence', '')}".strip()}
                       for t, v, o, sc in judged_runs])
        else:
            res("G19", 0, na=True, note="trial outcomes not judged")
        rules = [(t["id"], r) for t in runs for r in t.get("rules") or [] if r.get("applies")]
        if rules:
            res("G20", sum(1 for _, r in rules if r["followed"]) / len(rules),
                f"{sum(1 for _, r in rules if r['followed'])} of {len(rules)} followed",
                items=[{"item": tid, "score": 1 if r["followed"] else 0, "evidence": r["label"]} for tid, r in rules])
        else:
            res("G20", 0, na=True, note="no trial checked a written rule")
        errs = [t for t in runs if t.get("errors")]
        if errs:
            res("E13", sum(t["recovered"] for t in errs) / sum(t["errors"] for t in errs),
                f"{sum(t['recovered'] for t in errs)} of {sum(t['errors'] for t in errs)} errors",
                items=[{"item": t["id"], "score": t["recovered"] / t["errors"],
                        "evidence": "; ".join((e.get("error") or "")[:160] for e in t["events"] if e.get("is_error"))[:400]} for t in errs])
        else:
            res("E13", 0, na=True, note="no errors in the trials")
    else:
        for code in ("G17", "G18", "G19", "G20", "E13"):
            res(code, 0, na=True, note="agent trials not run")

    # --- safety
    if tools:
        checks = []
        for t in tools:
            # Whole words only: "backlinks" is not a "link" tool.
            words = re.split(r"[_\-\s.]+", re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", t.get("name") or "").lower())
            name = " ".join(words)
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
                items=[c for c in checks if c["score"] < 1], note=HEURISTIC["S01"])
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
    if "secrets" in probe or probe.get("probe_version", "0.1") != "0.1":
        dismissed = {d.get("name"): d.get("reason", "") for d in ((findings or {}).get("secrets") or {}).get("dismiss") or []
                     if d.get("reason")}
        leaks = [{"item": x["where"], "score": 1 if x["name"] in dismissed else 0 if x["likely_real"] else 0.5,
                  "evidence": f'{x["name"]}, {x["length"]} characters, redacted'
                              + (f'; dismissed: {dismissed[x["name"]]}' if x["name"] in dismissed else
                                 "" if x["likely_real"] else "; looks like a placeholder")}
                 for x in probe.get("secrets") or []]
        real = [x for x in leaks if x["score"] == 0]
        places = sorted({x["item"] for x in real})
        res("S03", 0 if real else 1, f"{len(real)} in {', '.join(places[:2])}" if real else "none found",
            items=sorted(leaks, key=lambda x: x["score"])[:30])
    else:
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
        if st == 401 and not origin.get("with_auth"):
            # The server asked for credentials before it looked at the Origin, so the check was never reached.
            res("S04", 0, f"HTTP {st}", untested=True, note="Refused for missing credentials; rerun the probe with --header to test the Origin check.")
        else:
            res("S04", 1 if st in (400, 401, 403) else 0, f"HTTP {st}")
    else:
        res("S04", 0, na=True, untested=not stdio, note="stdio transport" if stdio else "not probed")
    if (probe.get("target") or {}).get("transport") == "client":
        # Seen through a client: the tool text is what the model gets, the wire is out of sight.
        via = (probe.get("target") or {}).get("via") or "the client"
        res("P01", 1, "the client connected", note=f"Collected through {via}; the handshake itself was not visible.")
        for code in CLIENT_UNSEEN:
            res(code, 0, untested=True, note=f"Not visible through {via}.")
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
                             "na": True, "untested": True, "judged": True, "unjudged": True}
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
            # A pass is a claim too: without evidence it is not scored either.
            if not (it.get("evidence") or "").strip():
                warnings.append(f"{code} {it.get('item')}: score {s} without evidence, not scored")
                continue
            items.append({"item": it.get("item"), "score": float(s), "evidence": it.get("evidence", ""), "fix": it.get("fix", "")})
        if items:
            score = sum(i["score"] for i in items) / len(items)
            display = f"{sum(1 for i in items if i['score'] >= 1)} of {len(items)} pass"
        elif j.get("score") is not None and (j.get("evidence") or "").strip():
            score = float(j["score"])
            display = j.get("display") or ""
        else:
            warnings.append(f"{code}: no scored items with evidence")
            results[code] = {"score": None, "display": "not judged", "items": [], "note": "", "na": True, "untested": True,
                             "judged": True, "unjudged": True}
            continue
        results[code] = {"score": round(score, 2), "display": j.get("display") or display, "items": items,
                         "note": j.get("summary", ""), "evidence": j.get("evidence", ""), "na": False, "judged": True}
    return warnings


def category_score(key: str, results: dict) -> dict:
    """Score one category. Trials and info audits are shown but never scored, so reviews stay comparable."""
    rows = [row for row in CATALOG if row[1] == key and row[3] != "trial"]
    applicable = [(row, results[row[0]]) for row in rows if results.get(row[0]) and not results[row[0]]["na"]]
    scored_w = sum(row[2] for row, _ in applicable)
    untested_w = sum(row[2] for row in rows if not results.get(row[0]) or results[row[0]].get("untested"))
    coverage = scored_w / (scored_w + untested_w) if scored_w + untested_w else 0.0
    out = {"score": None, "coverage": round(coverage, 2), "provisional": False, "capped_by": [], "weight": scored_w}
    if not scored_w or coverage < 1 / 3:
        out["note"] = "Too few checks applied to score this category." if scored_w else "No check applied."
        return out
    score = round(sum(row[2] * res["score"] for row, res in applicable) / scored_w * 100)
    # A critical audit caps on any failed item, not only on a failing average:
    # one silent truncation, one read tool that writes or one unbounded huge read is enough.
    capped = [row[0] for row, res in applicable if row[0] in CRITICAL
              and (res["score"] < 0.1 or any(it.get("score") == 0 for it in res.get("items") or []))]
    if capped:
        score = min(score, 49)
    out.update(score=score, capped_by=capped, provisional=coverage < PROVISIONAL)
    return out


def score_categories(results: dict) -> dict:
    cats = {}
    for key, name, question in CATEGORIES:
        cats[key] = {**category_score(key, results), "name": name, "question": question}
    # Without a handshake nothing else can be checked: say so instead of scoring around it.
    if (results.get("P01") or {}).get("score") == 0:
        for key, c in cats.items():
            if key == "protocol":
                c.update(score=0, capped_by=["P01"], provisional=False, note="Unusable: the handshake failed.")
            else:
                c.update(score=None, note="Not scored: the server did not complete a handshake.")
    for key, _, _ in CATEGORIES:
        for row in CATALOG:
            res = results.get(row[0])
            if row[1] == key and res and not res["na"]:
                res["gain"] = fix_effects(results, cats, [row[0]]).get(key, 0.0)
    return cats


def passed(code: str, res: dict, item: str | None = None) -> dict:
    """The audit result as it would be after the fix: the whole audit, or one item of it."""
    new = {**res, "items": [dict(it) for it in res.get("items") or []]}
    if item is not None and new["items"]:
        for it in new["items"]:
            if it.get("item") == item:
                it["score"] = 1.0
        new["score"] = round(sum(it["score"] for it in new["items"]) / len(new["items"]), 2)
        return new
    for it in new["items"]:
        it["score"] = 1.0
    new["score"] = 1.0
    if code in BUDGETS:
        new["value"] = new["effective"] = BUDGETS[code][0]
    return new


PER_TURN = {"C01", "C02"}  # size metrics paid on every turn, where a suggestion's "saves" can be subtracted


def per_turn_saving(text: str | None) -> int | None:
    """'about 2.7k tokens per turn' -> 2700."""
    mt = re.search(r"([\d.,]+)\s*(k)?\s*tokens per turn", text or "")
    return round(float(mt.group(1).replace(",", "")) * (1000 if mt.group(2) else 1)) if mt else None


def apply_fix(results: dict, targets: list[str], saves: int | None = None) -> dict:
    """The results as they would be if the targets passed. Targets are audit ids or 'AUDIT:item'.
    A per-turn size target with a stated saving shrinks by that saving instead of passing outright."""
    changed = dict(results)
    for t in targets:
        code, _, item = t.partition(":")
        res = changed.get(code)
        if res and not res["na"] and res["score"] is not None:
            if saves and code in PER_TURN and not item and res.get("effective") is not None:
                eff = max(0, res["effective"] - saves)
                changed[code] = {**res, "score": round(lognormal_score(eff, *BUDGETS[code][:2]), 2),
                                 "value": max(0, res["value"] - saves), "effective": eff}
            else:
                changed[code] = passed(code, res, item or None)
    return changed


def caps_after(results: dict, targets: list[str], saves: int | None = None) -> set:
    changed = apply_fix(results, targets, saves)
    return {code for key, _, _ in CATEGORIES for code in category_score(key, changed)["capped_by"]}


def fix_effects(results: dict, cats: dict, targets: list[str], saves: int | None = None) -> dict:
    """Points each category gains if the targets pass."""
    changed = apply_fix(results, targets, saves)
    effects = {}
    for key in {row[1] for row in CATALOG if row[0] in {t.partition(":")[0] for t in targets}}:
        before = (cats.get(key) or {}).get("score")
        after = category_score(key, changed)["score"]
        if before is not None and after is not None and after > before:
            effects[key] = float(after - before)
    return effects


EFFORT = {"S": 1, "M": 2, "L": 3}
# What a client hides when it hands tools to the model: the wire, server metadata, annotations and output schemas.
CLIENT_UNSEEN = ["P02", "P03", "P04", "P05", "P06", "P07", "P08", "P09", "P10", "P13", "P14", "P15", "P16", "P17", "P18",
                 "G04", "G05", "G06", "S01", "S04", "C08", "E03"]
ALIASES = {"C07": "C13"}  # audits renamed since older findings were written


def recommendations(results: dict, findings: dict, cats: dict) -> list[dict]:
    # Effort is only knowable with the source; from the outside, suggestions rank by their effect alone.
    repo = bool((findings or {}).get("repo"))
    recs = []
    covered = set()
    by_code = {row[0]: row for row in CATALOG}
    cat_names = {k: n for k, n, _ in CATEGORIES}
    capped = {code for c in cats.values() for code in c.get("capped_by") or []}
    for rec in (findings or {}).get("recommendations") or []:
        targets = []
        for a in rec.get("audits") or []:
            code, sep, item = a.partition(":")
            code = ALIASES.get(code, code)
            if code in by_code:
                targets.append(code + sep + item)
        audits = list(dict.fromkeys(t.partition(":")[0] for t in targets))
        covered.update(targets)
        cat = rec.get("category") or (by_code[audits[0]][1] if audits else "guidance")
        recs.append({**rec, "audits": audits, "targets_audits": targets, "category": cat,
                     "effects": fix_effects(results, cats, targets, per_turn_saving(rec.get("saves"))),
                     "effort": rec.get("effort", "M"), "source": "agent"})
    for row in CATALOG:
        code = row[0]
        res = results.get(code)
        if not res or res["na"] or code in covered or res["score"] is None or res["score"] >= 0.9 or row[3] == "trial":
            continue
        # Items an agent suggestion already fixes are left out; the generic one covers the rest.
        failing = [it for it in res.get("items") or [] if (it.get("score") or 0) < 1 and f"{code}:{it.get('item')}" not in covered]
        if res.get("items") and not failing:
            continue
        targets = [f"{code}:{it.get('item')}" for it in failing] if res.get("items") and row[3] != "metric" else [code]
        action = re.split(r"(?<=[.;])\s", row[6])[0].rstrip(".;")
        recs.append({"title": action, "category": row[1], "audits": [code], "targets_audits": targets,
                     "targets": list(dict.fromkeys(str(it.get("item")) for it in failing))[:8],
                     "why": row[5], "fix": row[6], "effort": "M" if row[3] == "metric" else "S",
                     "evidence": "; ".join(f"{it.get('item')}: {it.get('evidence', '')}" for it in failing[:3]),
                     "effects": fix_effects(results, cats, targets), "source": "catalog"})
    for rec in recs:
        rec["sdk"] = bool(rec["audits"]) and all((results.get(a) or {}).get("sdk") for a in rec["audits"])
        touched = capped & set(rec["audits"])
        rec["lifts_cap"] = bool(touched) and not touched & caps_after(results, rec["targets_audits"], per_turn_saving(rec.get("saves")))
    # A cap held by two failing items lifts only when both are fixed: say so instead of showing no effect.
    for code in capped:
        group = [r for r in recs if code in r["audits"] and r["source"] == "agent"]
        if len(group) > 1 and not any(r["lifts_cap"] for r in group):
            joint = [t for r in group for t in r["targets_audits"]]
            if code not in caps_after(results, joint):
                eff = fix_effects(results, cats, joint)
                for r in group:
                    r["lifts_cap_with"] = [g["title"] for g in group if g is not r]
                    r["joint_effects"] = eff
    for rec in recs:
        rec["gain"] = round(sum(rec["effects"].values()), 1)
        joint_gain = sum((rec.get("joint_effects") or {}).values()) / (len(rec.get("lifts_cap_with") or []) + 1)
        # A fix that lifts a critical cap goes first; the rest rank by points per effort.
        rec["rank_value"] = ((1000 if rec["lifts_cap"] or rec.get("lifts_cap_with") else 0)
                             + max(rec["gain"], joint_gain) / (EFFORT.get(rec["effort"], 2) if repo else 1)
                             - (100 if rec["sdk"] else 0))
        if rec["sdk"]:
            rec["why"] = (rec.get("why") or "") + " This comes from the SDK, so it is fixed by upgrading it rather than in the server's code."
        if not repo:
            rec.pop("effort", None)
        effects = ", ".join(f"+{v:g} {cat_names.get(k, k)}" for k, v in sorted(rec["effects"].items(), key=lambda kv: -kv[1]))
        if rec.get("lifts_cap_with"):
            joint = ", ".join(f"+{v:g} {cat_names.get(k, k)}" for k, v in sorted(rec["joint_effects"].items(), key=lambda kv: -kv[1]))
            effects = (effects + "; " if effects else "") + f"{joint} together with: {'; '.join(rec['lifts_cap_with'])}"
        body = [f"**Expected effect:** {effects or 'no score change (category not scored or already capped elsewhere)'}"]
        if rec.get("targets"):
            body += [f"**Where:** {', '.join(rec['targets'])}"]
        body += ["", rec.get("why", ""), "", "**Fix**", "", rec.get("fix", "")]
        if rec.get("check"):
            body += ["", "**Done when**", "", rec["check"]]
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
    items = sorted(((p["name"], p["model_tokens"]) for p in per_tool), key=lambda kv: -kv[1])
    rects = squarify(items, 0, 0, W, H)
    by = {p["name"]: p for p in per_tool}
    parts = [f'<svg class="treemap" viewBox="0 0 {W} {H}" role="img" aria-label="Model-facing tool list tokens by tool">']
    for name, x, y, w, h in rects:
        p = by[name]
        desc_share = p["description_tokens"] / p["model_tokens"] if p["model_tokens"] else 0
        dh = h * desc_share
        tip = (f"{name}: {fmt_tokens(p['model_tokens'])} (description {fmt_tokens(p['description_tokens'])}, "
               f"input schema and name {fmt_tokens(p['model_tokens'] - p['description_tokens'])})")
        parts.append(f'<g><title>{esc(tip)}</title>'
                     f'<rect class="tm-desc" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{dh:.1f}"/>'
                     f'<rect class="tm-schema" x="{x:.1f}" y="{y + dh:.1f}" width="{w:.1f}" height="{h - dh:.1f}"/>'
                     f'<rect class="tm-border" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}"/>')
        if w > 70 and h > 34:
            fit = max(3, int((w - 14) / 7.9))
            label = name if len(name) <= fit else name[:fit - 1] + "\u2026"
            parts.append(f'<text x="{x + 8:.1f}" y="{y + 18:.1f}" class="tm-name">{esc(label)}</text>'
                         f'<text x="{x + 8:.1f}" y="{y + 34:.1f}" class="tm-size">{esc(fmt_tokens(p["model_tokens"]))}</text>')
        elif w > 44 and h > 20:
            parts.append(f'<text x="{x + 5:.1f}" y="{y + 15:.1f}" class="tm-size">{esc(fmt_tokens(p["model_tokens"]))}</text>')
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
        sub = ("unusable" if c.get("capped_by") == ["P01"] and c["score"] == 0 else
               "capped by " + ", ".join(c["capped_by"]) if c.get("capped_by") else
               f'provisional \u00b7 {round(c.get("coverage", 0) * 100)}% checked' if c.get("provisional") else
               "not scored" if c["score"] is None else f'{round(c.get("coverage", 0) * 100)}% checked')
        gauges.append(f'<a class="gauge-link{" provisional" if c.get("provisional") else ""}" href="#{key}">{gauge_svg(c["score"])}'
                      f'<span class="gauge-name">{esc(name)}</span><span class="gauge-sub">{esc(sub)}</span>{delta}</a>')

    vitals = []
    for code, label, info in VITALS:
        res = results.get(code) or {}
        good, poor, unit = BUDGETS[code]
        value = res.get("value")
        b = band(res.get("score")) if not res.get("na") else "na"
        where = ""
        if code == "C03":
            where = (m.get("max_tool_desc") or {}).get("where", "")
        elif code == "C04":
            where = (m.get("max_field_desc") or {}).get("where", "")
        elif code == "C01":
            where = f"{m.get('tool_count', 0)} tools"
            if res.get("effective") and res.get("effective") != value:
                where += f" \u00b7 {short_tokens(res['effective'])} effective"
        elif code == "C02" and res.get("effective") and res.get("effective") != value:
            where = f"{short_tokens(res['effective'])} effective"
        elif code == "C10":
            wpt = m.get("waste_per_turn") or {}
            value = wpt.get("ratio")
            where = (f"{short_tokens(wpt.get('tokens'))} of {short_tokens(wpt.get('total'))} tokens" if value is not None
                     else "needs the reviewer to quote filler in findings.json")
        pos = 0
        if value is not None and code == "C10":
            value = max(value, 1e-4)
        if value is not None:
            # position on a log scale from good/4 to poor*2
            lo, hi = math.log(good / 4), math.log(poor * 2)
            pos = max(0, min(100, (math.log(max(value, 1e-9)) - lo) / (hi - lo) * 100))
        g_at = (math.log(good) - math.log(good / 4)) / (math.log(poor * 2) - math.log(good / 4)) * 100
        p_at = (math.log(poor) - math.log(good / 4)) / (math.log(poor * 2) - math.log(good / 4)) * 100
        bar = (f'<div class="scale" aria-hidden="true"><span class="seg good" style="width:{g_at:.1f}%"></span>'
               f'<span class="seg avg" style="width:{p_at - g_at:.1f}%"></span><span class="seg poor" style="width:{100 - p_at:.1f}%"></span>'
               + (f'<span class="pin" style="left:{pos:.1f}%"></span>' if value is not None else "") + "</div>")
        vitals.append(f'<div class="vital {b}"><div class="vital-label">{shape(b)}<span class="grow">{esc(label)}</span>'
                      f'{info_html(label, info, " ".join(filter(None, [fmt_budget(code) + ".", budget_bytes(code, m.get("bytes_per_token")), EFFECTIVE_NOTE if res.get("effective") not in (None, value) else ""])))}</div>'
                      f'<div class="vital-value">{"none sent" if code == "C02" and m.get("instructions_bytes") is None else "not reviewed" if code == "C10" and value is None else value_html(value, unit)}</div>'
                      f'<div class="vital-where">{esc(where)}</div>{bar}'
                      f'<div class="vital-budget">{esc(fmt_budget(code))}</div></div>')

    cat_names = {k: n for k, n, _ in CATEGORIES}
    fixes = []
    for i, rec in enumerate(report["recommendations"][:5], 1):
        effects = [f'<span class="pill cat-{esc(k)}">+{v:g} {esc(cat_names.get(k, k))}</span>'
                   for k, v in sorted((rec.get("effects") or {}).items(), key=lambda kv: -kv[1])]
        if rec.get("lifts_cap_with"):
            ranks = [str(j) for j, other in enumerate(report["recommendations"], 1) if other["title"] in rec["lifts_cap_with"]]
            effects = [f'<span class="pill crit">lifts a cap with #{", #".join(ranks)}</span>'] + [
                f'<span class="pill cat-{esc(k)}">+{v:g} {esc(cat_names.get(k, k))} together</span>'
                for k, v in sorted(rec["joint_effects"].items(), key=lambda kv: -kv[1])]
        elif not effects:
            effects = [f'<span class="pill effort">{esc(cat_names.get(rec["category"], ""))}</span>']
        if rec.get("lifts_cap"):
            effects.insert(0, '<span class="pill crit">lifts a cap</span>')
        saves = f'<span class="pill">{esc(rec["saves"])}</span>' if rec.get("saves") else ""
        effort = f'<span class="pill effort">Effort {esc(rec["effort"])}</span>' if rec.get("effort") else ""
        where = f'<p class="fix-where"><span>Where</span>{esc(", ".join(rec["targets"]))}</p>' if rec.get("targets") else ""
        check = f'<p class="fix-where"><span>Done when</span>{esc(rec["check"])}</p>' if rec.get("check") else ""
        fixes.append(
            f'<article class="fix"><div class="fix-rank">{i}</div><div class="fix-body">'
            f'<div class="fix-meta">{"".join(effects)}{saves}{effort}</div>'
            f'<h3>{esc(rec["title"])}</h3><p>{esc(rec.get("why", ""))}</p>{where}'
            f'<details class="fix-detail"><summary>The suggestion</summary><pre>{esc(rec.get("fix", ""))}</pre>{check}</details>'
            f'<div class="fix-actions"><button type="button" data-copy="{esc(rec.get("fix", ""))}">Copy suggestion</button>'
            f'<button type="button" data-copy="{esc("# " + rec["issue"]["title"] + chr(10) + chr(10) + rec["issue"]["body"])}">Copy as issue</button></div>'
            f'</div></article>')

    sections = []
    for key, name, question in CATEGORIES:
        c = cats[key]
        rows = [row for row in CATALOG if row[1] == key and row[3] != "trial"]
        opps, passed, na, untested = [], [], [], []
        for row in rows:
            res = results.get(row[0])
            if not res:
                continue
            if res.get("untested"):
                untested.append((row, res))
            elif res["na"]:
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
        elif c.get("note"):
            capped = f'<p class="question">{esc(c["note"])}</p>'
        if c.get("provisional"):
            capped += (f'<p class="question">Provisional: {round(c.get("coverage", 0) * 100)}% of the applicable checks ran. '
                       "Audits that were not checked are listed below; the score can move either way once they are.</p>")
        sections.append(
            f'<section class="category" id="{key}"><header class="cat-head">{gauge_svg(c["score"], 72, 6)}'
            f'<div><h2>{esc(name)}</h2><p class="question">{esc(question)}</p>'
            + (f'<p class="cat-summary">{esc(summary)}</p>' if summary else "") + capped + "</div></header>"
            + audit_group("Opportunities", opps, by_code, open_=True, hint="ranked by estimated gain")
            + audit_group(f"Passed audits ({len(passed)})", passed, by_code, folded=True)
            + audit_group(f"Not checked in this run ({len(untested)})", untested, by_code, folded=True)
            + audit_group(f"Not applicable ({len(na)})", na, by_code, folded=True)
            + "</section>")

    inventory_rows = []
    for p in m.get("tools") or []:
        ann = p["annotations"]
        flags = " ".join(f'<span class="flag">{esc(lbl)}</span>' for k, lbl in
                         (("readOnlyHint", "read-only"), ("destructiveHint", "destructive"), ("idempotentHint", "idempotent"), ("openWorldHint", "open world"))
                         if ann.get(k)) or ('<span class="sub">not visible</span>' if meta.get("via") else "")
        fd = f'{p["fields_described"]}/{p["fields"]}' if p["fields"] else "–"
        grade = tool_grade(p, results)
        ost = f'{p["output_schema_tokens"]:,}' if p["output_schema_tokens"] else "–"
        inventory_rows.append(
            f'<tr><td><code>{esc(p["name"])}</code>' + (f'<div class="sub">{esc(p["title"])}</div>' if p["title"] else "") + "</td>"
            f'<td class="grade g-{grade}" data-v="{"ABCDF–".index(grade)}">{grade}</td>'
            f'<td data-v="{p["description_chars"]}">{p["description_chars"]:,}</td>'
            f'<td data-v="{p["model_tokens"] - p["description_tokens"]}">{p["model_tokens"] - p["description_tokens"]:,}</td>'
            f'<td data-v="{p["model_tokens"]}">{p["model_tokens"]:,}</td>'
            f'<td data-v="{p["output_schema_tokens"]}">{ost}</td>'
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

    badges = ["seen through a client" if meta.get("via") else meta["transport"], meta.get("review_mode") or ("reviewed" if meta.get("judged") else "automatic checks only")]
    if meta.get("trial_count"):
        badges.append(f'{meta["trial_count"]} agent trials')
    if meta.get("calls"):
        badges.append(f'{meta["calls"]} read call{"" if meta["calls"] == 1 else "s"}')
    if meta.get("repo"):
        badges.append("repo")
    template = TEMPLATE.read_text(encoding="utf-8")
    fill = {
        "TITLE": esc(f"MCP Insights: {meta['server_title']}"),
        "SERVER_TITLE": esc(meta["server_title"]),
        "SERVER_META": esc(" · ".join(dict.fromkeys(x for x in (
            meta.get("server_name"), meta.get("server_version"), meta.get("protocol") and f"protocol {meta['protocol']}",
            meta.get("target"), meta.get("commit") and f"commit {meta['commit']}",
            meta.get("via") and f"seen through {meta['via']}") if x))),
        "BADGES": "".join(f'<span class="badge">{esc(b)}</span>' for b in badges),
        "DATE": esc(pretty_date(meta["collected_at"])),
        "GAUGES": "".join(gauges),
        "VITALS": "".join(vitals),
        "TRIALS": trials_html(report.get("trials"), results),
        "FIXES": "".join(fixes) or '<p class="empty">Nothing to suggest above the noise.</p>',
        "FIXES_LEAD": esc("The five changes with the largest expected effect on the scores; those that lift a cap come first. "
                          "Each gain is the category re-scored as if the audits the suggestion names passed, or, for a size fix "
                          "with a stated saving, as if the text were that much smaller: what a complete fix would earn, not a forecast. "
                          + ("Based on the source checkout, with effort estimates." if meta.get("repo") else
                             "Made from the outside, without the source: they describe what the agent saw and what it should see instead, "
                             "so check them against the code before acting.")),
        "TREEMAP": treemap_svg(m.get("tools") or []) if m.get("tools") else '<p class="empty">No tools.</p>',
        "TREEMAP_NOTE": esc(f"{fmt_tokens(m.get('tool_list_model_tokens'))} reach the model (name, title, description and input schema of every tool"
                            + ("), as the client shows them; the server's own tools/list was not visible." if meta.get("via") else
                               f"). The full tools/list is {fmt_tokens(m.get('tool_list_wire_tokens'))}; output schemas and annotations stay with the client.")),
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
    """A to F for what the model reads about one tool: its judged description and, if it takes input, its field
    descriptions. Size and annotations have their own columns and audits; '–' when the description was not judged."""
    g10 = results.get("G10") or {}
    parts = [it["score"] for it in g10.get("items") or [] if it.get("item") == p["name"]]
    if not parts:
        return "–"
    if p["fields"]:
        parts.append(p["fields_described"] / p["fields"])
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
        judged = ('<span class="tag">judged</span>' if row[3] in ("judged", "waste") else
                  '<span class="tag">trial</span>' if row[3] == "trial" else "")
        crit = '<span class="tag crit">critical</span>' if code in CRITICAL else ""
        if code in DATA_DEPENDENT:
            crit += '<span class="tag">depends on data</span>'
        if code in HEURISTIC:
            crit += '<span class="tag">heuristic</span>'
        if res.get("sdk"):
            crit += '<span class="tag">SDK default</span>'
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


def trials_report(probe: dict, findings: dict) -> dict | None:
    t = probe.get("trials")
    if not t:
        return None
    verdicts = (findings or {}).get("trials") or {}
    runs = []
    for r in t.get("runs") or []:
        v = verdicts.get(r["id"]) if isinstance(verdicts.get(r["id"]), dict) else {}
        runs.append({**r, "verdict": v, "outcome": trial_outcome(r, v)})
    return {**t, "runs": runs}


OUTCOMES = {"done": "Done", "partial": "Partly done", "drafted": "Drafted, not run", "failed": "Failed",
            "blocked": "Blocked", "declined": "Declined"}
UNCOUNTED_OUTCOMES = {"blocked", "declined"}


def trial_outcome(run: dict, verdict: dict) -> str | None:
    """done, partial, drafted or failed; blocked (by the environment) and declined (rightly) do not count."""
    if not isinstance(verdict, dict):
        return None
    if not verdict and run.get("verify"):
        # A trial with a parser check is graded by it unless the reviewer judged otherwise.
        return "done" if run["verify"].get("ok") else "failed"
    if verdict.get("outcome") in OUTCOMES:
        return verdict["outcome"]
    s = verdict.get("success")
    if s is None:
        return None
    # A right call that was denied is a draft: the agent found the call, nobody saw it work.
    main_denied = any(e.get("denied") and e.get("tool") in (run.get("needs") or []) for e in run.get("events") or [])
    if s >= 1:
        return "drafted" if main_denied else "done"
    return "partial" if s > 0 else "failed"


def outcome_score(outcome: str, verdict: dict) -> float:
    if outcome == "partial":
        return max(0.0, min(1.0, float(verdict.get("success") or 0.5)))
    return {"done": 1.0, "drafted": 0.5}.get(outcome, 0.0)


def help_size(t: dict) -> str:
    return fmt_tokens(t["help_tokens"]) if "help_tokens" in t else fmt_bytes(t.get("help_bytes", 0))


def median(xs):
    xs = sorted(xs)
    return None if not xs else xs[len(xs) // 2] if len(xs) % 2 else (xs[len(xs) // 2 - 1] + xs[len(xs) // 2]) / 2


def short_command(cmd: str) -> str:
    """A check command as the reader needs it: without the cd into the reviewer's scratch directory or its paths."""
    cmd = re.sub(r"^cd \S+ && ", "", cmd.strip())
    return re.sub(r"(?<![\w.])/(?:[^\s/]+/)+([^\s/]+)", r"\1", cmd)


def trials_html(trials: dict | None, results: dict) -> str:
    if not trials:
        return ('<p class="section-lead">Not run. <code>scripts/trial.py</code> gives a fresh agent a task with only this server '
                'loaded and records what it does, so Guidance here rests on the text alone.</p>')
    runs = [r for r in trials.get("runs") or [] if not r.get("invalid")]
    models = sorted({str(r.get("model") or "?").replace("claude-", "") for r in runs})
    stats = []
    for code, label in (("G17", "Help read when needed"), ("G18", "Plain tasks without help"),
                        ("G19", "Tasks completed"), ("G20", "Written rules followed"), ("E13", "Errors recovered")):
        res = results.get(code) or {}
        if res.get("na"):
            continue
        b = band(res.get("score"))
        mt = re.match(r"\d+ of \d+", res.get("display", ""))
        short = mt.group(0) if mt else res.get("display", "")
        why = next((row[5] for row in CATALOG if row[0] == code), "")
        stats.append(f'<div class="vital {b}"><div class="vital-label">{shape(b)}<span class="grow">{esc(label)}</span>'
                     f'{info_html(label, why)}</div>'
                     f'<div class="vital-value">{esc(short)}</div>'
                     f'<div class="vital-where">{esc(code)}</div></div>')
    peaks = [r["context_peak"] for r in runs if r.get("context_peak")]
    cost = sum(r.get("cost_usd") or 0 for r in runs)
    if peaks:
        stats.append(f'<div class="vital na"><div class="vital-label"><span class="grow">Context at the end</span>'
                     f'{info_html("Context at the end", "Tokens the agent held at its last step: the client and its system prompt, this server, the tool definitions it loaded, and every answer it got. Median over the trials.")}</div>'
                     f'<div class="vital-value plain">{value_html(median(peaks), "tok")}</div>'
                     f'<div class="vital-where">median; {esc(short_tokens(min(peaks)))} to {esc(short_tokens(max(peaks)))}</div></div>')
    stats.append(f'<div class="vital na"><div class="vital-label">Trial cost</div>'
                 f'<div class="vital-value plain">${cost:.2f}</div><div class="vital-where">{len(runs)} trials</div></div>')
    groups: dict = {}
    for r in trials.get("runs") or []:
        groups.setdefault((r.get("base_id") or r["id"]).split("@")[0].split("#")[0], []).append(r)
    cards = []
    for gid, rs in groups.items():
        rows = []
        for r in rs:
            steps = []
            for e in r.get("events") or []:
                if e["kind"] == "client" and e["tool"] == "ToolSearch":
                    continue
                cls = ("err" if e.get("is_error") else "denied" if e.get("denied") else e["kind"] if e["kind"] in ("help", "client")
                       else "write" if e["tool"] in (r.get("needs") or []) else "read")
                label = e.get("uri", "").rsplit("/", 1)[-1] if e.get("uri") else e["tool"]
                if e["tool"] == "get_help" and '"topic"' in e.get("input", ""):
                    try:
                        label = f'get_help({json.loads(e["input"]).get("topic")})'
                    except ValueError:
                        pass
                size_ = fmt_tokens(e["tokens"]) if "tokens" in e else fmt_bytes(e.get("bytes"))
                steps.append(f'<li class="step {cls}" title="{esc(e["tool"])}: {esc(size_)}">'
                             f'<span>{esc(label)}</span><small>{esc(size_.replace(" tokens", ""))}</small></li>')
            v = r.get("verdict") or {}
            if r.get("invalid"):
                verdict = f'<p class="trial-verdict na">{shape("na")}{esc(r.get("status"))}</p>'
            elif r.get("outcome"):
                o = r["outcome"]
                vb = "na" if o in UNCOUNTED_OUTCOMES else band(outcome_score(o, v))
                verdict = f'<p class="trial-verdict {vb}">{shape(vb)}<span><b>{OUTCOMES[o]}.</b> {esc(v.get("evidence", ""))}</span></p>'
            else:
                verdict = f'<p class="trial-verdict na">{shape("na")}<span>Outcome not judged.</span></p>'
            hb = r.get("help_before_use")
            facts = [f'{r.get("calls", 0)} calls', f'{r.get("help_reads", 0)} help reads ({help_size(r)})']
            if hb is not None and r.get("expects_help"):
                facts.append(("help before" if hb else "no help before") + f' the first {"/".join(r.get("needs") or [])}')
            for rule in r.get("rules") or []:
                if rule.get("applies"):
                    facts.append(("\u2713 " if rule["followed"] else "\u2717 ") + rule["label"])
            if r.get("verify"):
                said = (r["verify"].get("output") or "").strip().splitlines()
                said = said[0] if said else ""
                said = said[:160] + "\u2026" if len(said) > 160 else said
                facts.append(("\u2713 check passed" if r["verify"].get("ok") else "\u2717 check failed")
                             + (f": {said}" if said and not r["verify"].get("ok") else ""))
            if r.get("errors"):
                facts.append(f'{r["errors"]} errors, {r.get("recovered", 0)} recovered')
            if r.get("context_peak"):
                facts.append(f'context {fmt_tokens(r.get("context_start"))} \u2192 {fmt_tokens(r["context_peak"])}')
            facts.append(f'{fmt_tokens(r.get("tokens") or 0)} billed, ${r.get("cost_usd") or 0:.3f}')
            model = str(r.get("model") or "").replace("claude-", "") + (f' #{r["attempt"]}' if "#" in r["id"] else "")
            facts_html = " \u00b7 ".join(esc(f) for f in facts)
            steps_html = "".join(steps) or '<li class="step">no calls</li>'
            rows.append(f'<div class="trial-run"><span class="pill effort">{esc(model)}</span>'
                        f'<ol class="steps">{steps_html}</ol><p class="trial-facts">{facts_html}</p>{verdict}'
                        f'<details class="fix-detail"><summary>Final answer</summary><pre>{esc(r.get("answer", ""))}</pre></details></div>')
        first = rs[0]
        # With repeats, the rate per model is the finding; one run alone shows a behaviour.
        tally = {}
        for r in rs:
            if r.get("outcome") and r["outcome"] not in UNCOUNTED_OUTCOMES and not r.get("invalid"):
                m_ = str(r.get("model") or "?").replace("claude-", "")
                done_, n_ = tally.get(m_, (0, 0))
                tally[m_] = (done_ + (r["outcome"] == "done"), n_ + 1)
        rate = " \u00b7 ".join(f"{m_}: {d} of {n} done" for m_, (d, n) in sorted(tally.items()) if n > 1)
        cards.append(f'<article class="trial"><header><span class="trial-id">{esc(gid)}</span>'
                     f'<h3>{esc(first.get("question") or first.get("task"))}</h3></header>'
                     f'<p class="trial-task">Task: {esc(first.get("task"))}</p>'
                     + (f'<p class="trial-task"><b>{esc(rate)}</b></p>' if rate else "")
                     + (f'<p class="trial-task">Checked with: <code>{esc(short_command(first["verify"]["command"]))}</code></p>' if first.get("verify") else "")
                     + f'{"".join(rows)}</article>')
    repeated = {gid for gid, rs in groups.items() if any("#" in r["id"] for r in rs)}
    once = ("Each trial ran once per model, so these show what an agent can do, not how often it succeeds. " if not repeated else
            "" if len(repeated) == len(groups) else
            "Trials with a \u201ck of n\u201d line ran several times per model; the others ran once, so they show what an agent can do, "
            "not how often it succeeds. ")
    lead = (f'What a fresh agent did with only this server loaded: one trial per question the text alone cannot answer. '
            f'Claude Code in print mode ({esc(", ".join(models))}); writes {esc(trials.get("writes", "blocked"))}. '
            + esc(once) + "The tasks were the reviewer\u2019s choice, so they say nothing about tasks that were not tried.")
    legend = ('<div class="tm-legend steps-legend"><span><i class="k help"></i>help read</span><span><i class="k read"></i>other call</span>'
              '<span><i class="k write"></i>the task\u2019s main call</span><span><i class="k denied"></i>blocked write</span>'
              '<span><i class="k err"></i>error</span></div>')
    judged = [r for r in runs if r.get("outcome") and r["outcome"] not in UNCOUNTED_OUTCOMES]
    done = sum(1 for r in judged if r["outcome"] == "done")
    drafted = sum(1 for r in judged if r["outcome"] == "drafted")
    helpy = [r for r in runs if r.get("expects_help") is True and r.get("help_before_use") is not None]
    plain = [r for r in runs if r.get("expects_help") is False]
    parts = [f"{done} of {len(judged)} tasks done" if judged else f"{len(runs)} trials, outcomes not judged"]
    if drafted:
        parts.append(f"{drafted} more drafted with the write blocked")
    if helpy:
        parts.append(f"help read first in {sum(1 for r in helpy if r['help_before_use'])} of {len(helpy)} that needed it")
    if plain:
        parts.append(f"{sum(1 for r in plain if not r.get('help_reads'))} of {len(plain)} plain tasks without help")
    blocked = sum(len(r.get("drafts") or []) for r in runs)
    if blocked and not drafted:
        parts.append(f"{blocked} blocked writes recorded as drafts")
    summary = "; ".join(parts) + "."
    return (f'<p class="section-lead">{lead}</p><div class="vitals trial-stats">{"".join(stats)}</div>'
            f'<p class="trials-summary">{esc(summary[0].upper() + summary[1:])}</p>'
            f'<details class="trials-more"><summary>Show the {len(groups)} trials step by step</summary>'
            f'<div class="trials">{"".join(cards)}</div>{legend}</details>')


def backfill_call_text(probe: dict, transcript: Path) -> None:
    """Older probes kept only the size of the whole result; recover the content text from the call transcript."""
    calls = [c for c in probe.get("calls") or [] if "bytes" in c and "tokens" not in c]
    if not calls or not transcript.exists():
        return
    asked, answers = [], {}
    for line in transcript.open(encoding="utf-8"):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        msg = rec.get("msg")
        if not isinstance(msg, dict):
            continue
        if rec.get("dir") == "out" and msg.get("method") == "tools/call":
            asked.append((msg.get("id"), (msg.get("params") or {}).get("name"), (msg.get("params") or {}).get("arguments") or {}))
        elif rec.get("dir") == "in" and "id" in msg:
            answers[msg["id"]] = msg
    for c in calls:
        hit = next((a for a in asked if a[1] == c["tool"] and a[2] == (c.get("arguments") or {})), None)
        if hit is None:
            continue
        asked.remove(hit)
        res = (answers.get(hit[0]) or {}).get("result") or {}
        text = "\n".join(str(x.get("text", "")) for x in res.get("content") or [] if isinstance(x, dict) and x.get("type") == "text")
        c["text_bytes"] = len(text.encode("utf-8"))
        c["tokens"] = estimate_tokens(text)


def build(dir_: Path, findings_path: Path | None, baseline_path: Path | None) -> dict:
    probe = json.loads((dir_ / "probe.json").read_text(encoding="utf-8"))
    backfill_call_text(probe, dir_ / "transcript-calls.jsonl")
    findings = {}
    fp = findings_path or (dir_ / "findings.json")
    if fp and fp.exists():
        findings = json.loads(fp.read_text(encoding="utf-8"))
    metrics, results = compute(probe, findings)
    warnings = merge_judged(results, findings) if (probe.get("initialize") or {}).get("ok") else []
    # Behaviour the server's SDK produces, not its own code: still what the agent sees, so it is scored,
    # but labelled, and its suggestion goes last.
    for code, why in ((findings or {}).get("sdk") or {}).items():
        if code in results:
            results[code] = {**results[code], "sdk": True, "note": " ".join(x for x in (results[code].get("note"), f"From the SDK: {why}") if x)}
    cats = score_categories(results)
    recs = recommendations(results, findings, cats)
    init = probe.get("initialize") or {}
    info = init.get("serverInfo") or {}
    target = probe.get("target") or {}
    baseline = {}
    if baseline_path and baseline_path.exists():
        old = json.loads(baseline_path.read_text(encoding="utf-8"))
        baseline = {k: v.get("score") for k, v in (old.get("categories") or {}).items()}
    warnings += metrics.get("waste_problems") or []
    # A released version names the code; a placeholder such as 0.0.0 does not.
    unpinned = not re.match(r"\d+\.\d+", str(info.get("version") or "")) or re.search(r"^0\.0\.0|dev|local|snapshot", str(info.get("version")), re.I)
    if not probe.get("source") and target.get("transport") != "client" and unpinned:
        warnings.append("The run does not pin the server's code (version "
                        f"{info.get('version') or 'unknown'}): pass --cwd with its git checkout or --commit to collect.")
    for rec in (findings or {}).get("recommendations") or []:
        missing = [f for f in ("targets", "check") if not rec.get(f)]
        if not rec.get("audits"):
            missing.append("audits")
        if missing:
            warnings.append(f"suggestion \"{rec.get('title', '?')}\" has no {', '.join(missing)}: name the tools or fields, "
                            "how to confirm the fix, and the audits it moves")
    # Trials sit beside the review, not in it: they never change a score.
    judged_rows = [results.get(row[0]) or {} for row in CATALOG if row[3] == "judged"]
    n_judged = sum(1 for x in judged_rows if x and not x.get("na"))
    n_open = sum(1 for x in judged_rows if not x or x.get("untested"))
    review_mode = ("handshake failed" if not init.get("ok") else "automatic checks only" if not n_judged
                   else "full review" if not n_open else "partial review")
    n_trials = len([r for r in (probe.get("trials") or {}).get("runs") or [] if not r.get("invalid")])
    unjudged = [code for code, r in results.items() if r.get("unjudged")]
    if not init.get("ok"):
        warnings.append("The handshake failed, so nothing beyond it could be checked. See stderr_tail in probe.json.")
    elif unjudged and findings:
        warnings.append(f"not judged: {', '.join(sorted(unjudged))}")
    elif not findings:
        warnings.append("No findings.json: judged audits are missing, so Agent guidance, Error recovery and Safety rest on the automatic checks only.")
    return {
        "meta": {
            "server_title": info.get("title") or target.get("label") or info.get("name") or "MCP server",
            "server_name": info.get("name"), "server_version": info.get("version"),
            "protocol": init.get("protocolVersion"), "transport": target.get("transport"),
            "via": target.get("via") if target.get("transport") == "client" else None,
            "commit": ((probe.get("source") or {}).get("commit") or "")[:12] + ("+dirty" if (probe.get("source") or {}).get("dirty") else "")
                      if (probe.get("source") or {}).get("commit") else None,
            "target": target.get("label") or target.get("url") or "",
            "collected_at": probe.get("collected_at"), "probe_version": probe.get("probe_version"),
            "render_version": RENDER_VERSION, "catalog_version": CATALOG_VERSION,
            "judged": bool(n_judged), "review_mode": review_mode, "trial_count": n_trials,
            "token_estimator": TOKEN_ESTIMATOR,
            "calls": len([c for c in probe.get("calls") or [] if "bytes" in c]),
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
        "trials": trials_report(probe, findings),
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
