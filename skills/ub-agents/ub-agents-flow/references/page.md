# flow.json

`scripts/page.py` turns this file and the drawings it names into the
documents: the overview, then one per phase with its drawing, roles, a card
per gate and its notes. [../assets/example.json](../assets/example.json) is an
illustration from uberblick-ai/ub-agents, not a default.

```json
{
  "schema_version": 2,
  "repository": "OWNER/NAME",
  "ref": "a021eaa",
  "date": "2026-10-20",
  "overview": {
    "summary": "At most 60 words: what the loop is for, its delivery model (where work lands, how it reaches a release), who carries it and where a person steps in.",
    "flow": "overview.flow",
    "points": [
      "**Preparation.** At most 30 words on what happens in the phase.",
      "**Implementation.** At most 30 words on what happens in the phase."
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
      "sections": [
        {
          "heading": "Pull requests from a trusted bot",
          "text": "One or two sentences on where this work enters the phase and what it skips.",
          "items": ["**Merge.** One sentence per rule that differs for this work."]
        }
      ],
      "notes": [
        "`queue.dependencies: wait` One or two sentences on what it does. [Queue: Dependencies](https://agents.uberblick.ai/docs/configuration/queue.html#dependencies)",
        "One sentence per surprise or inconsistency found in this phase."
      ]
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

- `ref` is the commit the files were read at, so every source points at the
  lines as they were. `date` is today.
- `overview` holds the summary of the whole loop, its drawing and its
  `points`. The summary says what the repository uses the loop for and its
  delivery model in the team's terms: where work lands (the default branch,
  release or milestone branches) and how it reaches a release, rather than
  how the config differs from the starter `ub-agents init` writes. The
  documents line after it is generated from the phase names. The `points`
  are one sentence per phase or step, in the drawing's order, and a last one
  on where a person steps in at any point (unclear intent, work too big for
  one PR, a decision only a maintainer can make). The ways work enters stay
  in the drawing: a sentence repeating them adds nothing. It names no labels
  and has no table or notes; those belong to the phases. An optional `title`
  replaces "How the loop runs in OWNER/NAME".
- `phases` are the issue phase and the implementation and PR phase, in that
  order. A step with its own entries, forks and person gates, such as the
  merge when a bot's pull requests enter there, can be a phase of its own
  after them, with `"continues": "Implementation and PR phase"`: its gates
  continue that phase's numbers, and that phase's drawing ends where the step
  begins, in an `end` node saying what the item waits for. Use it when one
  drawing would pass about 20 nodes. `flow` names the phase's ablauf source
  next to `flow.json`. An optional `title` replaces "The loop in OWNER/NAME:
  issue phase". The `summary` follows the
  "Details of" line, so it reads as one paragraph: the journey of one item
  through the phase and the document it hands over to. When the phase's
  first agent owns more than its box says, such as creating branches or
  choosing a pull request's base, say so in it.
- `roles` lists every agent in `ub-agents.yaml`, in the order work passes
  through them. `kind` is the agent's `kind` (`issue`, `pr`) or `any` when
  unset. `runtime` is optional. `outcomes` maps every declared outcome to the
  labels it adds; an outcome that adds nothing maps to `[]`. The documents
  show each role's triggers and what it does; the outcomes feed the checks.
- `stop_labels` is the config's `stop-labels`, `["needs-human"]` when unset.
- Each phase's `gates` are numbered `G1`, `G2`, ... in the order an item
  meets them in that phase, and the same numbers appear in its flow, so each
  document stands on its own. A gate both phases meet, such as the launcher's
  or a maintainer's answer, is listed in both. A phase that `continues`
  another carries on its numbers; a gate the two share keeps its number and
  name in both, and a number the earlier phase skips belongs to the later
  one. `decides` is `launcher` (the
  launcher enforces it from the config), `agent` (an agent checks it per its
  instructions) or `person`. `rule` is the gate in one plain sentence, such
  as "A maintainer added the trigger label and nothing holds the issue: no
  open blocker, no `needs-human`, retries left." Name the labels it sends work
  to; leave the detail to the sources. `sources` are paths relative to the
  repository root, with a line or a line range where the rule is written;
  they ground the gate and stay in `flow.json`, out of the documents.
- `sections` are optional, per phase, each a heading with a paragraph, a list
  or both, placed before the notes. Use one for work that enters the phase
  without an issue, such as a trusted bot's pull requests, when its rules
  differ: what it skips, what review it owes, how it merges, how often it goes
  back.
- `notes` are optional, per phase. There is no table
  of settings: a limit that holds work back is part of a gate (`max-attempts`,
  stop labels and approvals sit in the launcher's gate), and timeouts and
  backoff are operations detail. Each `queue` setting in use gets the issue
  phase's first notes, one each, saying what it does as the launcher runs it
  and linking its section of the
  [queue page](https://agents.uberblick.ai/docs/configuration/queue.html);
  where the repository's own instructions describe the queue otherwise, that
  is a finding. Findings follow, in the phase they concern, and only those about how work
  moves: how a workflow authenticates, the tokens it uses or how a file is
  formatted belong in the repository's own files, not in a note. Every note
  says what happens at the top level, in a sentence or two: no technical
  detail (sort rules, tie-breaks, status output, upgrade steps) and no
  setting or mode the config does not use. A finding is a gap nobody chose:
  before writing one, check the config's comments and the history of the
  line, and leave out a deliberate exemption. Settings that only tune detail,
  such as a trusted bot's feedback or an unset `kind` behaving as its default,
  get no note.

Write every text in the present tense, as the loop runs. A route the
maintainer has decided, in the conversation or in an open pull request they
wrote or approved, counts as running even before the default branch has it:
describe it as it works, never as planned. Leave out history and
provenance: no issue or PR number, release, date or "since" clause.

Text fields are inline Markdown as Uberblick reads it: `code`, **bold**,
*italic* and https links.
