# Judged audits

Score each item 1, 0.5 or 0, and give every item `evidence`, passes
included: a quote from the server's text, a captured response, or what you
checked. An item without evidence is not scored. An audit has one of four
states:

- **pass or fail**: scored items with evidence.
- **not applicable**: `{"na": true, "reason": "..."}`, when the server has
  nothing the audit looks at (no help topics for G15, no destructive tools
  for S10). Not applicable leaves the category's coverage alone.
- **not checked**: no entry. The audit counts against coverage, and a
  category checked below 80% is marked provisional.
- For the audits that list only failures (G16, E11), record
  `{"score": 1, "display": "none found", "evidence": "what you checked"}`
  when you looked and found none. Not looking is "not checked", not a pass.

E12 and S12 are critical: one item scored 0 caps the category at 49.

When you judge a sample (6 of 33 help topics), say which and why in the
audit's `summary`.

| Audit | Item | 1 | 0.5 | 0 |
| --- | --- | --- | --- | --- |
| G10 descriptions | each tool | in plain sentences: what it does; what it returns (for a write, what the result confirms); when to use another tool, where another tool overlaps; and the main failure, where the tool takes input | one or two of those missing, or buried in syntax | one-liner, or mostly syntax grammar |
| G11 instructions | the server | names the cross-tool workflow and lists the help topics by name, named after what users ask for (tables, charts), nothing else | useful but padded, or help named only by area ("markdown") | absent, generic, or a tool list repeated |
| G12 single home | each format or syntax | explained in one place, others point to it | two or three copies that agree | four or more copies, or copies that disagree |
| G13 true examples | each example, in descriptions and help | valid against the input schema and the server's behaviour | valid but misleading (an unusual value the model will copy) | invalid, or rejected by the server |
| G14 no internals | the server's texts | none | a few internal names or history notes | internals, old-client notes or plans throughout |
| G15 help structure | each help topic | example, syntax, reading, editing, errors | some parts missing, editing absent | creation only, or a pasted schema |
| G16 no contradictions | each contradiction found | (list only contradictions, each scored 0) | | advice the server's behaviour or another text contradicts |
| E10 recovery | each observed error | names the cause and the fix (valid values, the field, the tool or topic) | names the cause only | generic text, or a raw JSON-RPC code |
| E11 real cause | each misleading error | (list only misleading ones) | | the stated cause is not the actual one |
| E12 no silent bad writes | each write probe (sandbox only) | refused, or stored with a diagnostic, naming the offending part | refused or flagged, part not named | succeeded silently and stored something else |
| S10 explicit target | each destructive tool | needs an id | accepts a filter but confirms the count | acts on a free-text query, or on everything with no target |
| S11 risk stated | each destructive tool | says what is lost and whether it can be undone | one of the two | neither |
| S12 honest reads | each tool that looks like a read (query, get, list, search) or touches credentials | cannot change data | changes only the caller's own settings, and says so | runs mutations, or stores, replaces or deletes credentials |

Judge what the server needs, not a house style. A one-tool fetch server has
no cross-tool workflow (G11 not applicable) and no sibling to point to (G10).
G11 and G15 apply only when the server has a workflow across tools or help
topics.

## findings.json

```json
{
  "repo": false,
  "judged": {
    "G10": {"items": [{"item": "get_doc", "score": 0.5, "evidence": "\"Returns the doc.\" says nothing about ...", "fix": "Rewritten description ..."},
                      {"item": "search", "score": 1, "evidence": "Says what it matches, what each hit carries, and that unknown tags refuse."}],
            "summary": "One sentence on the pattern."},
    "G11": {"score": 1, "display": "orients well", "evidence": "quote", "summary": "..."},
    "G15": {"na": true, "reason": "no help topics"}
  },
  "recommendations": [
    {"title": "Imperative, specific title", "category": "guidance",
     "audits": ["G10:get_doc", "G10:list_docs", "C03"],
     "targets": ["get_doc", "list_docs"],
     "why": "One or two sentences.", "fix": "Paste-ready text or concrete steps.",
     "check": "How the maintainer confirms it worked.",
     "saves": "about 2.5k tokens per turn", "evidence": "optional quote"}
  ],
  "help_resources": ["myserver://help/*"],
  "data_resources": ["myserver://tasks/*"],
  "density": {"texts": [
    {"text_id": "tool:create_doc", "clarity": 0.5,
     "waste": [{"quote": "exact text from the description", "why": "internals"}]}
  ]},
  "trials": {"t1-plain-read": {"outcome": "done", "success": 1, "evidence": "What the agent did and why it counts."}},
  "secrets": {"dismiss": [{"name": "DJANGO_SECRET_KEY", "reason": "documented dev placeholder"}]},
  "summaries": {"protocol": "One sentence per category, shown under its gauge."},
  "notes": {"summary": "The reviewer's overall take.", "agree": ["..."], "disagree": ["..."], "missing": ["..."]}
}
```

`repo` is true only when you read the server's source. Without it,
suggestions stay at the surface the agent saw (descriptions, errors,
responses) and carry no effort estimate; with it, they can name files and
add `"effort": "S" | "M" | "L"`.

A recommendation's `audits` are what it moves: an audit id, or
`AUDIT:item` when it fixes one item, such as `G10:get_doc`. The report
re-scores the categories as if those passed, so the effect it shows is real,
and a suggestion that lifts a critical cap ranks first. Two suggestions that
only lift a cap together are shown as a pair. `targets` names the tools,
fields or topics to change and `check` says how to confirm the change; the
renderer warns when either is missing. Failed audits that no recommendation
covers get a generic one from the catalog.

A rewrite must keep every guarantee the old text gave: what is refused
before writing, partial-write and recovery behaviour, concurrency and
revision rules, error names. A shorter description that drops one of these
makes the server worse while raising its score.

`help_resources` and `data_resources` are globs that say which resources
are help and which are data, when the names do not make it clear. Help
counts toward help size (C05, C06, C11); data does not.

`category` is one of `protocol`, `guidance`, `errors`, `context`, `safety`.

`density` lists the wasted spans of always-loaded texts and help topics. Text
ids are `instructions`, `tool:NAME`, `field:NAME.PATH` (for example
`field:create_doc.blocks[].text`) and `topic:URI`. Each quote must appear in
the text (whitespace is normalized) or it is dropped with a warning. Waste is
repetition, internals, history, restated schema, text about other tools and
filler; a long text that is all signal has no waste. Filler is reported over
the texts you reviewed, and the report says how many that is.

`trials` records each trial's `outcome`:

- `done`: the task was carried out and the result checked.
- `partial`: some of it, with `success` between 0 and 1.
- `drafted`: the right call was found but a blocked write kept it from
  running. The report infers this when the task's main call was denied.
- `failed`: wrong or no result.
- `blocked`: the environment stopped the trial before it said anything about
  the server.
- `declined`: the agent rightly refused.

Blocked and declined trials do not count toward "tasks completed". Trials are
shown beside the scores and never change them, because which trials run is
the reviewer's choice. `secrets.dismiss` clears a redacted value that is not
a real secret; it needs a reason.

## trials.json

```json
{
  "help": {"tools": ["get_help"], "resources": ["uberblick://help/*"]},
  "trials": [
    {"id": "t1-plain-read", "question": "Do plain reads work from the descriptions alone?",
     "task": "When was the document titled 'Roadmap' last updated?",
     "expects_help": false, "needs": []},
    {"id": "t2-chart", "question": "Is the data help read before a chart is written?",
     "task": "Create a document with a bar chart of ...", "expects_help": true,
     "needs": ["create_doc", "update_data"],
     "rules": [{"label": "reads the doc before editing", "first": ["insert_block"], "before": ["get_doc"]}]},
    {"id": "t2-chart@sonnet", "model": "sonnet", "...": "same task, another model"}
  ]
}
```

`help` says which calls count as reading help (globs; default: tools named
like help, and every resource read). `task` is what a user would type, with
no hint about help. `needs` names the tools whose first call should come after
a help read when `expects_help` is true. `rules` check a written rule: some
call in `before` must come before the first call in `first`. Name the exact
call, `tool` or `tool:pattern` (the pattern matches a resource URI as a glob or
appears in the arguments), for example `ReadMcpResourceTool:mise://tasks` or
`get_help:markdown`; `"help"` accepts any help read.
Use names and data that exist in the server's workspace or sandbox.

An error counts as recovered when the agent's next call to the same tool,
with at most two other server calls in between, has changed input and
succeeds.
