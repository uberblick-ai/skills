# flow.json

`scripts/page.py` reads this file, every `.flow` it names and the `.svg`
`render.mjs` drew next to each, and writes Uberblick Markdown and a page from
the same blocks. By default that is three documents: `overview.md`, the whole
loop at a glance (the summary, one drawing from a new issue to the merge, a
table of the phases and the notes on the queue and the loop as a whole), then
one document per phase named after its flow, such as `issue.md` and `pr.md`,
each with its sentence, its drawing, a table of its roles, a card per gate and
its own notes. `--combine` writes them as one document, `flow.md`, instead.
`flow.html` shows the documents styled like Uberblick, each starting a new
printed page. The example in [../assets/example.json](../assets/example.json)
is uberblick-ai/ub-agents.

```json
{
  "schema_version": 2,
  "repository": "OWNER/NAME",
  "ref": "a021eaa",
  "date": "2026-10-20",
  "overview": {
    "summary": "Three sentences, at most 60 words: how work enters, where it is checked, where it returns and where it stops.",
    "flow": "overview.flow",
    "notes": [
      "`queue.dependencies: wait` One or two sentences on what it does. [Queue: Dependencies](https://agents.uberblick.ai/docs/configuration/queue.html#dependencies)"
    ]
  },
  "phases": [
    {
      "name": "Implementation and PR phase",
      "summary": "One sentence, at most 30 words.",
      "starts": "`ready`",
      "ends": "Squash-merged",
      "flow": "pr.flow",
      "roles": ["implementer", "reviewer", "integrator"],
      "gates": [
        {
          "id": "G3",
          "name": "Review",
          "at": "reviewer",
          "decides": "agent",
          "rule": "One sentence, at most 30 words: what lets the item move on, and where it goes otherwise.",
          "sources": [".agents/reviewer.md:3-17", "ub-agents.yaml:80"]
        }
      ],
      "notes": ["One sentence per surprise or inconsistency found in this phase."]
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
  "stop_labels": ["needs-human"]
}
```

- `ref` is the commit the files were read at, so every source links to the
  lines as they were. `date` is today.
- `overview` holds the summary of the whole loop, its drawing and the notes
  that concern more than one phase. An optional `title` replaces "How the
  loop runs in OWNER/NAME".
- `phases` are the issue phase and the implementation and PR phase, in that
  order. `starts` and `ends` are the label or state an item enters and leaves
  the phase with, for the overview's table. `flow` names the phase's ablauf
  source next to `flow.json`; its Markdown takes the same name, so a phase
  flow is never `overview.flow` or `flow.flow`. An optional `title` replaces
  "The loop in OWNER/NAME: issue phase". Every role belongs to exactly one
  phase.
- `roles` lists every agent in `ub-agents.yaml`, in the order work passes
  through them. `kind` is the agent's `kind` (`issue`, `pr`) or `any` when
  unset. `runtime` is optional. `outcomes` maps every declared outcome to the
  labels it adds; an outcome that adds nothing maps to `[]`. The documents
  show each role's triggers and what it does; the outcomes feed the checks.
- `stop_labels` is the config's `stop-labels`, `["needs-human"]` when unset.
- Each phase's `gates` are numbered `G1`, `G2`, ... in the order an item
  meets them in that phase, and the same numbers appear in its flow, so each
  document stands on its own. A gate both phases meet, such as the launcher's
  or a maintainer's answer, is listed in both. `decides` is `launcher` (the
  launcher enforces it from the config), `agent` (an agent checks it per its
  instructions) or `person`. `rule` is the gate in one plain sentence, such
  as "A maintainer added the trigger label and nothing holds the issue: no
  open blocker, no `needs-human`, retries left." Name the labels it sends work
  to; leave the detail to the sources. `sources` are paths relative to the
  repository root, with a line or a line range where the rule is written;
  they ground the gate and stay in `flow.json`, out of the documents.
- `notes` are optional, in the overview and in each phase. There is no table
  of settings: a limit that holds work back is part of a gate (`max-attempts`,
  stop labels and approvals sit in the launcher's gate), and timeouts and
  backoff are operations detail. Each `queue` setting in use gets the
  overview's first notes, one each, saying what it does as the launcher runs
  it and linking its section of the
  [queue page](https://agents.uberblick.ai/docs/configuration/queue.html).
  Findings follow, in the overview when they span the loop and in the phase
  they concern otherwise.

Text fields are inline Markdown as Uberblick reads it: `code`, **bold**,
*italic* and https links.

`page.py` stops with an error on a missing or malformed field, a role in no
phase or in two, gates not numbered from `G1` in order, or a drawing not yet
rendered. It warns, without stopping, when an outcome adds a label that starts
no agent and is no stop label, when a gate number is missing from its phase's
drawing or a drawing shows one that is not among its gates, and when a text
runs past the word budgets above.
