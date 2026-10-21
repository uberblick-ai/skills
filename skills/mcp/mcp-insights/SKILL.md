---
name: mcp-insights
description: >-
  Review an MCP server the way PageSpeed Insights reviews a web page: five
  scores from 0 to 100 (protocol, agent guidance, error recovery, context
  cost, safety), context vitals such as tool list size, and a ranked list of
  fixes, in one self-contained HTML report. Use when someone asks how good
  an MCP server is, why agents struggle with it, how much context its tools
  cost, or what to fix first. Works on any stdio or Streamable HTTP server.
  Not a load test or a security pentest.
license: MIT
compatibility: >-
  Requires python3 (standard library only) and a way to start or reach the
  server: its stdio command or its HTTP URL plus any auth header. Read-only
  by default: it calls only tools marked readOnlyHint or confirmed as reads.
metadata:
  author: uberblick-ai
  version: "0.1"
---

# MCP Insights

Scripts collect facts, you judge the text, and the renderer computes the
scores, so numbers are reproducible and every judgement shows its evidence.
`scripts/probe.py` and `scripts/render.py` live next to this file; call them
by their path inside this skill's directory. `DIR` is a scratch directory
outside the server's repository.

## 1. Ask

Get the server's stdio command (and working directory) or its URL, and how
it authenticates. Take them from the project's `.mcp.json` or the client's
MCP settings when the user points at one. Pass secrets with `--env NAME=value`
or `--header 'Authorization: Bearer ...'`, never inside `--command`, because
the command is stored in `probe.json`. Ask whether a sandbox exists (a scratch
workspace or test instance) before any write; without one the run stays
read-only.

## 2. Collect

```sh
python3 scripts/probe.py collect --command "npx -y @scope/server" --cwd PATH --out DIR --label NAME
python3 scripts/probe.py collect --url https://host/mcp --header "Authorization: Bearer $TOKEN" --out DIR --label NAME
```

It initializes, lists tools, resources, templates and prompts through every
page, reads every resource and argument-free prompt, sends safe error probes
(unknown method, unknown tool, schema-invalid arguments to read-only tools,
malformed JSON on stdio, an unknown protocol version) and times the cold
start. It writes `DIR/probe.json` and transcripts. A failed start leaves the
server's stderr in `probe.json` under `stderr_tail`.

## 3. Plan and run read calls

Read the tool list in `probe.json` and write `DIR/calls.json` with one
realistic call per read-only tool, so the report can measure response sizes
and check structured output:

```json
{"calls": [
  {"tool": "list_docs", "arguments": {}, "purpose": "list"},
  {"tool": "get_doc", "arguments": {"uuid": "<id from list_docs>"}, "purpose": "largest typical read"}
]}
```

Chain them: list first, then use real ids. Prefer the largest realistic
object for the "get" calls. A tool not marked `readOnlyHint: true` runs only
with `"confirmed_read_only": true`, which you set after reading its
description and being sure it changes nothing. Then:

```sh
python3 scripts/probe.py call --command "..." --out DIR --calls DIR/calls.json
```

## 4. Judge

Read every model-facing text in `probe.json`: `initialize.instructions`, each
tool's description and field descriptions, resource and prompt texts, and the
error messages under `probes`. Score the judged audits with the anchors in
[references/rubric.md](references/rubric.md) and write `DIR/findings.json`
in the shape described there. Every score below 1 needs quoted evidence or it
is not counted. Write concrete fixes: for a description, the rewritten text
ready to paste.

## 5. Render

```sh
python3 scripts/render.py DIR --open
```

It merges `probe.json` and `findings.json`, scores each category, ranks the
fixes by estimated gain per effort, and writes `DIR/report.html` and
`DIR/report.json`. Add `--baseline OLD_DIR/report.json` to show changes since
an earlier run.

## 6. Reply

Give the five scores, the top three fixes and the path to `report.html`.
Mention any category that rests on automatic checks only because a judged
audit was not applicable.
