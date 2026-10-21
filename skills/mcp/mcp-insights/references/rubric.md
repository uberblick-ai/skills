# Judged audits

Score each item 1, 0.5 or 0. An item below 1 needs `evidence`: a quote from
the server's text or a captured response. Without evidence it is not scored.
Mark an audit `{"na": true, "reason": "..."}` when it does not apply. For the
audits that list only failures (G16, E11), record `{"score": 1, "display":
"none found"}` when you looked and found none.

E12 and S12 are critical: one item scored 0 caps the category at 49.

| Audit | Item | 1 | 0.5 | 0 |
| --- | --- | --- | --- | --- |
| G10 descriptions | each tool | says what it does, what it returns, when to use another tool, and the main failure, in plain sentences | two or three of the four, or buried in syntax | one-liner, or mostly syntax grammar |
| G11 instructions | the server | names the cross-tool workflow and lists the help topics by name, named after what users ask for (tables, charts), nothing else | useful but padded, or help named only by area ("markdown") | absent, generic, or a tool list repeated |
| G12 single home | each format or syntax | explained in one place, others point to it | two or three copies that agree | many copies, or copies that disagree |
| G13 true examples | each example | valid against the input schema and the server's behaviour | valid but misleading (an unusual value the model will copy) | invalid, or rejected by the server |
| G14 no internals | the server's texts | none | a few internal names or history notes | internals, old-client notes or plans throughout |
| G15 help structure | each help topic | example, syntax, reading, editing, errors | some parts missing, editing absent | creation only, or a pasted schema |
| G16 no contradictions | each contradiction found | (list only contradictions, each scored 0) | | advice the server's behaviour or another text contradicts |
| E10 recovery | each observed error | names the cause and the fix (valid values, the field, the tool or topic) | names the cause only | generic text, or a raw JSON-RPC code |
| E11 real cause | each misleading error | (list only misleading ones) | | the stated cause is not the actual one |
| E12 no silent bad writes | each write probe (sandbox only) | refused, or stored with a diagnostic, naming the offending part | refused or flagged, part not named | succeeded silently and stored something else |
| S10 explicit target | each destructive tool | needs an id | accepts a filter but confirms the count | acts on a free-text query |
| S11 risk stated | each destructive tool | says what is lost and whether it can be undone | one of the two | neither |
| S12 honest reads | each tool that looks like a read (query, get, list, search) or touches credentials | cannot change data | changes only the caller's own settings, and says so | runs mutations, or stores, replaces or deletes credentials |

## findings.json

```json
{
  "judged": {
    "G10": {"items": [{"item": "get_doc", "score": 0.5, "evidence": "\"Returns the doc.\" says nothing about ...", "fix": "Rewritten description ..."}],
            "summary": "One sentence on the pattern."},
    "G11": {"score": 1, "display": "orients well", "summary": "..."},
    "G15": {"na": true, "reason": "no help topics"}
  },
  "recommendations": [
    {"title": "Imperative, specific title", "category": "guidance", "audits": ["G10", "C03"],
     "effort": "S", "why": "One or two sentences.", "fix": "Paste-ready text or concrete steps.",
     "saves": "-2.5k tokens per turn", "evidence": "optional quote"}
  ],
  "density": {"texts": [
    {"text_id": "tool:create_doc", "clarity": 0.5,
     "waste": [{"quote": "exact text from the description", "why": "internals"}]}
  ]},
  "trials": {"t1-plain-read": {"success": 1, "evidence": "What the agent did and why it counts."}},
  "secrets": {"dismiss": [{"name": "DJANGO_SECRET_KEY", "reason": "documented dev placeholder"}]},
  "summaries": {"protocol": "One sentence per category, shown under its gauge."},
  "notes": {"summary": "The reviewer's overall take.", "agree": ["..."], "disagree": ["..."], "missing": ["..."]}
}
```

`category` is one of `protocol`, `guidance`, `errors`, `context`, `safety`.
`effort` is `S`, `M` or `L`; the report ranks fixes by the points the listed
audits would gain divided by effort. Failed automatic audits that no
recommendation covers get a generic one from the catalog.

`density` lists the wasted spans of always-loaded texts and help topics. Text
ids are `instructions`, `tool:NAME`, `field:NAME.PATH` (for example
`field:create_doc.blocks[].text`) and `topic:URI`. Each quote must appear in
the text (whitespace is normalized) or it is dropped with a warning. Waste is
repetition, internals, history, restated schema, text about other tools and
filler; a long text that is all signal has no waste.

`trials` scores each trial's outcome 1, 0.5 or 0 from its transcript, with
evidence below 1. `secrets.dismiss` clears a redacted value that is not a real
secret; it needs a reason.

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
