---
name: mcp-audit
description: >-
  Review an MCP server the way PageSpeed Insights reviews a web page: five
  scores from 0 to 100 (protocol, agent guidance, error recovery, context
  cost, safety), context vitals such as tool list size, agent trials that show
  whether a fresh agent finds the help it needs, and ranked suggestions, in
  one self-contained HTML report. Use for "how good is our MCP server?",
  "why do agents struggle with this MCP?", "how much context do these tools
  cost?" or "what should we fix first in our MCP server?". Works on any stdio
  or Streamable HTTP server. Writes only to a scratch directory and calls only
  read tools, unless you point it at a sandbox for write probes. Not for load
  testing, a security pentest or debugging your MCP server.
license: MIT
compatibility: >-
  Requires python3 (standard library only) and a way to start or reach the
  server: its stdio command or its HTTP URL plus any auth header. Read-only
  by default: it calls only tools marked readOnlyHint or confirmed as reads.
metadata:
  author: uberblick-ai
  version: "0.1"
---

# MCP Audit

Scripts collect facts, you judge the text, and the renderer computes the
scores, so numbers are reproducible and every judgement shows its evidence.
The review works from the outside: it calls tools and judges how they
behave, above all when something goes wrong. It does not debug the server,
read its implementation or look for the cause of a failure; that is the
maintainer's part once the report shows what an agent meets.
The report is the result; the suggestions at its end are a starting point
for the maintainer. Each score shows how much of its category was checked,
and which audits rest on a sample, so a quick automatic run or a sampled
judgement is not mistaken for a full review.
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

Against a production server, look before anything runs: `collect --list-only`
lists the tools, resources and prompts and reads or calls nothing. Check what
the resources hold and which tools are reads, then collect in full.

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
server's stderr in `probe.json` under `stderr_tail`. The error probes go only
to tools marked `readOnlyHint`; tools you confirm as reads in step 3 get them
then. When `--cwd` is the server's git checkout, the record pins its commit
and notes uncommitted changes; otherwise pass `--commit SHA`. When the server
is an installed package that a project runs from its own directory, the
project's commit says nothing about it: pass `--package NAME@VERSION`. Without
either, the report warns that the run does not say which code it reviewed.
Secrets in anything the server returns are redacted before they reach disk;
`probe.json` keeps only their names, places and lengths under `secrets`, and
the report fails Safety when a likely real one turns up. Tell the user at once
when that happens. Email addresses in what the server returns are masked as
`[email]`, outside its own descriptions and help.

A server you can only reach through a client, such as a connector in
Claude's app, cannot be collected. Save the tool definitions the client shows
you as JSON lines, make the read calls through the client, and save each
call as a line with `tool`, `arguments`, `text`, `is_error` and `purpose` (or
`why` for an argument the schema forbids). Then:

```sh
python3 scripts/probe.py import --tools DIR/tools.jsonl --calls DIR/calls.jsonl --label NAME \
  --via "Claude's Gmail connector" --strip-prefix mcp__Gmail__ --instructions DIR/instructions.txt --out DIR
```

Only the error text of a call is kept, never a read's content. The report
marks the handshake, annotations and error codes as not visible.

## 3. Plan and run read calls

Read the tool list in `probe.json` and write `DIR/calls.json` with one
realistic call per read-only tool, so the report can measure response sizes
and check structured output. Response size depends on the data, so prefer a
workspace with real content (read-only) over an empty sandbox, and read its
largest items. Large reads are fair when they can be narrowed: for a read
that may come back large, call it once with its defaults and once with its
limit, page or filter, so the report can check that the agent can ask for
less (C13):

```json
{"calls": [
  {"tool": "list_items", "arguments": {}, "purpose": "list"},
  {"tool": "get_item", "arguments": {"id": "<id from list_items>"}, "purpose": "largest typical read"},
  {"tool": "list_items", "arguments": {"status": "<one status>"}, "purpose": "the list, narrowed"}
]}
```

Tool names in this file are placeholders: use the server's own.

When the server serves help through a tool instead of resources (a help,
guide or docs tool), add one call per topic with `"help": true` and the
topic's name in `"topic"`, for example
`{"tool": "get_help", "arguments": {"topic": "queries"}, "help": true, "topic": "get_help:queries"}`.
Those answers count toward help size like help resources (C05, C06, C11) and
are judged with them; a topic a help resource also serves is counted once.

Chain them: list first, then use real ids. A tool not marked
`readOnlyHint: true` runs only with `"confirmed_read_only": true`, which you
set after reading its description and being sure that call, with those
arguments, changes nothing. Then:

```sh
python3 scripts/probe.py call --command "..." --out DIR --calls DIR/calls.json
```

## 4. Trials

Trials show what a fresh agent does with only this server loaded. Run one
trial per behavioural question the report leaves open, never a fixed set.
Test the claims the server's own text makes, because that is where agents go
wrong:

- each syntax the server asks the agent to write (a query or filter
  language, a template, a diagram or markup format): one trial per syntax,
  graded by a real parser or the server's own validation through `verify`,
  not by reading the transcript
- each write rule the text states (what a field must contain, read before
  writing, a version or etag to send, what an update keeps): one trial that
  depends on the rule, checked by reading the result back
- help or syntax that must be read before a tool works
- a syntax a tool requires that no text explains, such as a filter or query
  field typed as a plain string
- tools that change things with unclear or missing annotations
- tool names that are easy to confuse

Skip trials for small read-only servers, for a server already tried under
another name, and for anything that would write outside a sandbox. Include a
plain task that should need no help, to check the descriptions stand alone.
Trials are shown beside the scores and never change them, because which
trials run is your choice; they show what the scores cannot.

One run shows what an agent can do, not how often it succeeds. Give each
trial `"repeat": 3` (5 when the result decides a fix) and a Sonnet copy, so
the report shows "k of n" per model. `verify` is a shell command run after
each attempt: exit 0 means the task is done, and its output appears on the
trial card. Write it against the server's own reads or the format's parser,
for example a script that reads the result back and parses it.

When the maintainer has a fix on a branch, run the same plan against the
baseline and the branch, with the same models and repeats, and render the
branch with `--baseline`: that measures a suggestion's effect instead of
assuming it. When the startup instructions can be changed locally, an
ablation does the same for discovery: the same trial with and without the
help topics listed in the instructions.

Write `DIR/mcp.json` in Claude Code's MCP config format with only this
server (take secrets from the user's secret manager, never from a file in
the repo). The format has no working directory: for a server that must start
in one, use `{"command": "sh", "args": ["-c", "cd /path/to/project && exec SERVER-COMMAND"]}`.
Write `DIR/trials.json` as described in
[references/rubric.md](references/rubric.md#trialsjson). Then:

```sh
python3 scripts/trial.py run --mcp-config DIR/mcp.json --server NAME --plan DIR/trials.json --out DIR
```

It needs Claude Code (`claude`) on PATH and costs a few cents per trial with
the default Haiku; add a `"model": "sonnet"` copy of a trial to compare.
What the trials measure is what an agent in Claude Code does; the report tags
those audits, and the instructions cut-off (G07), with the client's name.
Write tools are blocked, and the blocked call is recorded as what the agent
would have sent. Claude Code saves a result over its output limit to a file
under `~/.claude/projects/`, in full and unredacted, and shows the agent a
notice instead; `trial.py` records the real size and prints where those files
are. Tell the user, and delete them once the review is done. In a sandbox, add `--allow-writes` and `--before-each` with a
command that restores the sandbox, so every trial starts from the same state.
Then read what the agent wrote back through the server and check it with the
server's own reads; that is how silent truncation, dropped fields and
formatting stored as literal text show up (E12).

With a sandbox, also send deliberately wrong writes yourself: add calls with
`"write_probe": true`, an `expect` and a `read_back` read to `calls.json` and
run `probe.py call --allow-writes` against the sandbox. Derive each probe
from a rule the server's own text states, then break it the way an agent
would: a value the schema accepts but the text forbids (too long, one list
item too many, nested data in the wrong shape), part of a value where the
text asks for the whole, a stale or missing version token, an id that does
not exist, the same create sent twice, and an unknown key:

```json
{"tool": "update_item", "write_probe": true, "purpose": "stale version token", "expect": "refused, naming the current version",
 "arguments": {"id": "<sandbox item>", "version": 1, "title": "Renamed"},
 "read_back": {"tool": "get_item", "arguments": {"id": "<sandbox item>"}}}
```

Each probe keeps the server's answer and what the read-back shows was
stored: the evidence for E11 (does the error name the real cause) and E12
(was something else stored without a word).

## 5. Judge

Read every model-facing text in `probe.json`: `initialize.instructions`, each
tool's description and field descriptions, resource and prompt texts, and the
error messages under `probes`. Score the judged audits with the anchors in
[references/rubric.md](references/rubric.md) and write `DIR/findings.json`
in the shape described there. Every score needs evidence, passes included,
or it is not counted. Judge what the server needs: a one-tool server is not
marked down for lacking a workflow or help topics. Write concrete fixes: for
a description, the rewritten text ready to paste, keeping every guarantee
the old text gave (what refuses before writing, partial writes, recovery).
For behaviour, say what the agent should see (refused with an error naming
the row), not how to build it. Quote wasted spans under `density`, so context cost counts
waste rather than length. An audit that applies but cannot be tested in this
run, such as E12 without a sandbox, gets `{"untested": true, "reason": ...}`. For a server with many formats or a large help
surface, judge one content family at a time (a syntax, a resource type, a
workflow), one sub-agent per family when you can start them: each reads the
help for its family and reports the copies that drift, editing that is not
taught, and internals that leak. Read each trial's transcript in `DIR/trials/` and
record whether it succeeded under `trials`; a trial with `verify` is graded
by its check unless you record otherwise.

Some audits match on names or patterns (S01, G08); the report tags them
heuristic, so read the tool's description, or call it in a sandbox, before
citing one. When a response is recognisably an SDK's default (its standard
wording for a schema rejection, the draft-07 `$schema` line it emits), you
may list the audit under `sdk` in `findings.json` with the reason: the
report tags it and ranks its suggestion lower. Go by the response alone;
don't trace a finding into the server's code.

## 6. Render

```sh
python3 scripts/render.py DIR --open
```

It merges `probe.json` and `findings.json`, scores each category, ranks the
suggestions by their effect (re-scoring the categories as if each one were
done, those that lift a critical cap first), and writes `DIR/report.html`
and `DIR/report.json`. Fix any warning it prints about suggestions without
`targets` or `check`, or scores without evidence. Check each `lead:` it
prints, such as a limit that returned the same answer as the default, and
judge it before you reply. Add `--baseline OLD_DIR/report.json` to show
changes since an earlier run or against the baseline of a branch comparison;
the report says when the baseline differs in more than the code (another
version, a changed tool list, an older audit catalog).

## 7. Reply

Reply in this shape, with your own numbers (these are an example for a
made-up server). Number the suggestions so the maintainer can say "do 2",
and leave out a line that has nothing in it:

```text
acme-tasks at 4f2c1e0: protocol 96, agent guidance 71, error recovery 49 (capped: a write stored something else silently), context cost 64, safety 92.
Every audit judged; agent guidance and context cost rest on samples (8 of 30 help topics, 20 of 140 texts).
Trials: 4 tasks, 3 runs each on Haiku and Sonnet, 22 of 24 done (12 graded by a check script).
Suggestions: 1. Refuse a due date in the past instead of storing today (lifts the cap). 2. Name the missing field and where its value comes from in validation errors. 3. Drop the 300-character id pattern from 18 fields, could save about 2k tokens per turn.
Report: DIR/report.html
```

With `--baseline`, add a line with what moved and why, and say which
suggestion's effect the baseline-versus-branch run measured. When a re-run
finds nothing new, one line is enough:
`acme-tasks at 9b1d2a7: no score moved since 4f2c1e0, same three suggestions.`
Scores are for the team's own use: do not publish them.
