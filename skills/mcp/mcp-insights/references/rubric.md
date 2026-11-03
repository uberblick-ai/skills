# Judged audits

Score each item 1, 0.5 or 0, and give every item `evidence`, passes
included: a quote from the server's text, a captured response, or what you
checked. An item without evidence is not scored. An audit has one of five
states:

- **pass or fail**: scored items with evidence.
- **not applicable**: `{"na": true, "reason": "..."}`, when the server has
  nothing the audit looks at (no help topics for G15, no destructive tools
  for S10). Not applicable leaves the category's coverage alone.
- **not tested here**: `{"untested": true, "reason": "..."}`, when the audit
  applies but this run could not test it, such as E12 on a server with write
  tools and no sandbox. It counts against coverage like an audit not checked,
  and the report shows the reason instead of a warning.
- **not checked**: no entry. The audit counts against coverage, and a
  category checked below 80% is marked provisional.
- For the audits that list only failures (G16, E11), record
  `{"score": 1, "display": "none found", "evidence": "what you checked"}`
  when you looked and found none. Not looking is "not checked", not a pass.

E12 and S12 are critical: one item scored 0 caps the category at 49.

When you judge a sample (6 of 33 help topics), add `"sample": "6 of 33
topics"` to the audit and say which and why in its `summary`. The report
marks the category as sampled and lists the sample beside its score, so a
reader does not take it for the whole surface. Context waste (C10, C11) is
marked the same way when `density` covers only some of the texts.

A schema check of an example (G13) shows it is valid, not that it is safe to
copy: still read what the call would do, and score 0.5 an example whose
values would cause an unwanted change if copied as they are.

| Audit | Item | 1 | 0.5 | 0 |
| --- | --- | --- | --- | --- |
| G10 descriptions | each tool | in plain sentences: what it does; what it returns (for a write, what the result confirms); when to use another tool, where another tool overlaps; and the main failure, where the tool takes input | one or two of those missing, or buried in syntax | one-liner, or mostly syntax grammar |
| G11 instructions | the server | names the cross-tool workflow and lists the help topics by name, named after what users ask for (tables, charts), nothing else | useful but padded, or help named only by area ("markdown") | absent, generic, or a tool list repeated |
| G12 single home | each format or syntax | explained in one place, others point to it | two or three copies that agree | four or more copies, copies that disagree, or a syntax a tool requires that no text explains |
| G13 true examples | each example, in descriptions and help | valid against the input schema and the server's behaviour | valid but misleading (an unusual value the model will copy) | invalid, or rejected by the server |
| G14 no internals | the server's texts | none | a few internal names or history notes | internals, old-client notes or plans throughout |
| G15 help structure | each help topic | an example, the syntax or rules, how to use it for each job it covers, and its errors | some parts missing | one job only, or a pasted schema |
| G16 no contradictions | each contradiction found | (list only contradictions, each scored 0) | | advice the server's behaviour or another text contradicts |
| E10 recovery | each observed error | names the cause and the fix (valid values, the field, the tool or topic) | names the cause only | generic text, or a raw JSON-RPC code |
| E11 real cause | each misleading error | (list only misleading ones) | | the stated cause is contradicted by what the review saw: another call, a read-back or the server's own text |
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
  "judged": {
    "G10": {"items": [{"item": "get_item", "score": 0.5, "evidence": "\"Returns the item.\" says nothing about ...", "fix": "Rewritten description ..."},
                      {"item": "search", "score": 1, "evidence": "Says what it matches, what each hit carries, and that unknown tags refuse."}],
            "summary": "One sentence on the pattern."},
    "G11": {"score": 1, "display": "orients well", "evidence": "quote", "summary": "..."},
    "G15": {"items": [...], "sample": "6 of 33 topics", "summary": "Which topics and why."},
    "S10": {"na": true, "reason": "no destructive tools"}
  },
  "recommendations": [
    {"title": "Imperative, specific title", "category": "guidance",
     "audits": ["G10:get_item", "G10:list_items", "C03"],
     "targets": ["get_item", "list_items"],
     "why": "One or two sentences.", "fix": "Paste-ready text or concrete steps.",
     "check": "How the maintainer confirms it worked.",
     "saves": "could save about 2.5k tokens per turn", "evidence": "optional quote"}
  ],
  "help_resources": ["myserver://help/*"],
  "data_resources": ["myserver://tasks/*"],
  "density": {"texts": [
    {"text_id": "tool:create_item",
     "waste": [{"quote": "exact text from the description", "why": "internals"}]}
  ]},
  "trials": {"t1-plain-read": {"outcome": "done", "success": 1, "evidence": "What the agent did and why it counts."},
             "t3-query#2": {"outcome": "failed", "evidence": "A repeated trial is judged per attempt."}},
  "sdk": {"P18": "draft-07 schemas come from the SDK's schema converter"},
  "secrets": {"dismiss": [{"name": "DJANGO_SECRET_KEY", "reason": "documented dev placeholder"}]},
  "summaries": {"protocol": "One sentence per category, shown under its gauge."},
  "notes": {"summary": "The reviewer's overall take.", "agree": ["..."], "disagree": ["..."], "missing": ["..."]}
}
```

Suggestions stay at the surface the agent saw: descriptions, errors,
responses and what was stored. They say what the agent should see instead,
not where in the code or how to build it, and carry no effort estimate,
because the review does not read the server's source.

A recommendation's `audits` are what it moves: an audit id, or
`AUDIT:item` when it fixes one item, such as `G10:get_item`. The report
re-scores the categories as if those passed, so the effect it shows is real,
and a suggestion that lifts a critical cap ranks first. Two suggestions that
only lift a cap together are shown as a pair. A suggestion in a capped
category is scored as if the cap-lifting fix were done, and shows that gain
"after" it. Gains are what a complete fix would earn under the rubric, not a
forecast, and they do not add up across suggestions. `targets` names the tools,
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
`field:create_item.tags[]`) and `topic:URI`. Each quote must appear in
the text (whitespace is normalized) or it is dropped with a warning. Waste is
repetition, internals, history, restated schema, text about other tools and
filler; a long text that is all signal has no waste. A sentence that states
a guarantee (nothing is rolled back, which side wins a concurrent change,
what still works offline) is signal even when it uses internal names: quote
only the internal name, and suggest the guarantee in plain words. Filler is reported over
the texts you reviewed, and the report says how many that is. Context waste
measures waste, not usefulness: a one-line description costs little and scores
well here, and that it says too little is marked down under G02 and G10.

`trials` records each trial's `outcome`:

- `done`: the task was carried out and the result checked.
- `partial`: some of it, with `success` between 0 and 1.
- `drafted`: the right call was found but a blocked write kept it from
  running. The report infers this when the task's main call was denied.
- `failed`: wrong or no result.
- `blocked`: the environment stopped the trial before it said anything about
  the server.
- `declined`: the agent rightly refused.

A trial with `verify` is `done` when the check passes and `failed` when it
does not, unless you record another outcome. Blocked and declined trials do
not count toward "runs done". Trials are
shown beside the scores and never change them, because which trials run is
the reviewer's choice. `secrets.dismiss` clears a redacted value that is not
a real secret; it needs a reason. `sdk` names audits whose response matches
the SDK's default, with the reason; the report labels them, and a suggestion
whose audits all match the SDK's defaults ranks below the server's own fixes.

## trials.json

```json
{
  "help": {"tools": ["get_help"], "resources": ["myserver://help/*"]},
  "confirmed_read_only": ["get_stats"],
  "trials": [
    {"id": "t1-plain-read", "question": "Do plain reads work from the descriptions alone?",
     "task": "When was the item titled 'Q3 launch' last updated?",
     "expects_help": false, "needs": []},
    {"id": "t2-update", "question": "Is the version rule followed before an update?",
     "task": "Rename the item 'Q3 launch' to 'Q3 launch (moved)'.", "expects_help": false,
     "needs": ["update_item"],
     "rules": [{"label": "reads the item before changing it", "first": ["update_item"], "before": ["get_item"]}]},
    {"id": "t2-update@sonnet", "model": "sonnet", "...": "same task, another model"},
    {"id": "t3-query", "question": "Is the query syntax found, and does the server accept the saved query?",
     "task": "Save a view of the open items assigned to Ana that are due this week.", "expects_help": true,
     "needs": ["save_view"], "repeat": 3, "verify": "python3 check_view.py sandbox.db"}
  ]
}
```

`help` says which calls count as reading help (globs). Set it: the default
counts tools named like help, guide or manual and every resource read, which
misses a help tool with another name, and `trial.py` prints what it guessed.
`confirmed_read_only` lists tools not marked `readOnlyHint` that you have
checked change nothing; trials may call them, with any arguments, while
writes are blocked. Leave out a tool that is a read only with some arguments
(a query tool that also takes mutations, a credentials tool whose status
action reads), and any tool you are unsure of: its calls are then blocked and
recorded as what the agent would have sent. `task` is what a user would type, with
no hint about help. `needs` names the tools whose first call should come after
a help read when `expects_help` is true. `rules` check a written rule: some
call in `before` must come before the first call in `first`. Name the exact
call, `tool` or `tool:pattern` (the pattern matches a resource URI as a glob or
appears in the arguments), for example `ReadMcpResourceTool:mise://tasks` or
`get_help:markdown`; `"help"` accepts any help read.
Use names and data that exist in the server's workspace or sandbox.
`repeat` runs the trial that many times (ids become `t3-query#1` and so
on), and `verify` is a shell command run after each attempt whose exit code
grades it. It gets `MCPI_TRIAL_ID`, `MCPI_ATTEMPT`, `MCPI_TRANSCRIPT` (the
attempt's transcript, whose last line holds the agent's answer) and
`MCPI_RUN_DIR`, so one script can grade every attempt. With writes allowed,
pair it with `--before-each` so every attempt starts from the same sandbox.

An error is a call that failed (`isError`) or a result that reports a
failure in its body: an `error` field, a non-empty `errors` list, a text that
opens like an error. The second kind is marked "as a normal result". An error
counts as recovered when the agent's next call to the same tool, with at most
two other server calls in between, has changed input and succeeds.
