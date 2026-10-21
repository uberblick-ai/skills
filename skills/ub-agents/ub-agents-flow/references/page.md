# flow.json

`scripts/page.py` reads this file, each phase's `.flow` and the `.svg`
`render.mjs` drew next to it, and writes the report twice from the same
blocks: `flow.md` in Uberblick Markdown and `flow.html` styled like an
Uberblick document. The report is the title and summary, then per phase a
heading, its sentence, its drawing as an `ablauf` fence, a table of its roles
and a card per gate with its rule and the lines it comes from, then the notes
as a list. The example in [../assets/example.json](../assets/example.json) is
uberblick-ai/ub-agents.

```json
{
  "schema_version": 1,
  "repository": "OWNER/NAME",
  "ref": "a021eaa",
  "date": "2026-10-20",
  "summary": "Three sentences, at most 60 words: how work enters, where it is checked, where it returns and where it stops.",
  "phases": [
    {
      "name": "Issue phase",
      "summary": "One sentence, at most 30 words.",
      "flow": "issue.flow",
      "roles": ["issue-preparer"],
      "gates": ["G1", "G2"]
    },
    {
      "name": "Implementation and PR phase",
      "summary": "One sentence, at most 30 words.",
      "flow": "pr.flow",
      "roles": ["implementer", "reviewer", "integrator"],
      "gates": ["G3", "G4", "G5", "G6"]
    }
  ],
  "roles": [
    {
      "agent": "reviewer",
      "kind": "pr",
      "runtime": "claude:claude-opus-5-5:high",
      "triggers": ["needs-review"],
      "does": "At most 20 words: what the agent does, in its instructions' terms.",
      "outcomes": {"approved": ["ready-to-merge"], "changes-requested": ["needs-changes"]},
      "instructions": ".agents/reviewer.md"
    }
  ],
  "stop_labels": ["needs-human"],
  "gates": [
    {
      "id": "G4",
      "name": "Review",
      "at": "reviewer",
      "decides": "agent",
      "rule": "One sentence, at most 30 words: what lets the item move on, and where it goes otherwise.",
      "sources": [".agents/reviewer.md:3-17", "ub-agents.yaml:80"]
    }
  ],
  "notes": [
    "`queue.dependencies: wait` One or two sentences on what it does. [Queue: Dependencies](https://agents.uberblick.ai/docs/configuration/queue.html#dependencies)",
    "One sentence per surprise or inconsistency found while reading."
  ]
}
```

- `ref` is the commit the files were read at, so every source links to the
  lines as they were. `date` is today.
- `phases` are the issue phase and the implementation and PR phase, in that
  order. `flow` names the phase's ablauf source next to `flow.json`; its
  drawing is the `.svg` beside it. Every role and every gate belongs to
  exactly one phase: a gate drawn in both, such as a maintainer's decision,
  is listed where an item last meets it.
- `roles` lists every agent in `ub-agents.yaml`, in the order work passes
  through them. `kind` is the agent's `kind` (`issue`, `pr`) or `any` when
  unset. `runtime` is optional. `outcomes` maps every declared outcome to the
  labels it adds; an outcome that adds nothing maps to `[]`.
- `stop_labels` is the config's `stop-labels`, `["needs-human"]` when unset.
- `gates` are numbered `G1`, `G2`, ... in the order an item meets them, and
  the same numbers appear in the flow. `decides` is `launcher` (the launcher
  enforces it from the config), `agent` (an agent checks it per its
  instructions) or `person`. `rule` is the gate in one plain sentence, such
  as "A maintainer added the trigger label and nothing holds the issue: no
  open blocker, no `needs-human`, retries left." Name the labels it sends work
  to; leave the detail to the sources. `sources` are paths relative to the
  repository root, with a line or a line range where the rule is written.
- `notes` are optional. There is no table of settings: a limit that holds
  work back is part of a gate (`max-attempts`, stop labels and approvals sit
  in the launcher's gate), and timeouts and backoff are operations detail.
  Each `queue` setting in use gets the first notes, one each, saying what it
  does as the launcher runs it and linking its section of the
  [queue page](https://agents.uberblick.ai/docs/configuration/queue.html).
  The findings follow.

Text fields are inline Markdown as Uberblick reads it: `code`, **bold**,
*italic* and https links.

`page.py` stops with an error on a missing or malformed field, a role or gate
in no phase or in two, or a drawing not yet rendered. It warns, without
stopping, when an outcome adds a label that starts no agent and is no stop
label, when a gate number is missing from its phase's drawing or a drawing
shows one that is not a gate, and when a text runs past the word budgets above
or there are more than eight gates; past those each phase no longer fits its
printed page.
