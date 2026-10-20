# flow.json

`scripts/page.py` reads this file and the SVG `render.mjs` drew, and builds a
page that prints on two A4 pages: the flow with the roles beside it on the
first, the gates, limits and notes on the second. The example in
[../assets/example.json](../assets/example.json) is uberblick-ai/ub-agents.

```json
{
  "schema_version": 1,
  "repository": "OWNER/NAME",
  "ref": "a021eaa",
  "date": "2026-10-20",
  "summary": "Three sentences, at most 60 words: how work enters, where it is checked, where it returns and where it stops.",
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
      "passes": "At most 35 words: what must be true for the item to move on.",
      "holds": "At most 35 words: what holds it and the outcome or label that says so.",
      "sources": [".agents/reviewer.md:3-17", "ub-agents.yaml:80"]
    }
  ],
  "settings": [
    {"name": "max-attempts", "value": "5", "meaning": "Failed runs in a row before the item is marked failed."}
  ],
  "notes": ["One sentence per surprise or inconsistency found while reading."]
}
```

- `ref` is the commit the files were read at, so every source links to the
  lines as they were. `date` is today.
- `roles` lists every agent in `ub-agents.yaml`, in the order work passes
  through them. `kind` is the agent's `kind` (`issue`, `pr`) or `any` when
  unset. `runtime` is optional. `outcomes` maps every declared outcome to the
  labels it adds; an outcome that adds nothing maps to `[]`.
- `stop_labels` is the config's `stop-labels`, `["needs-human"]` when unset.
- `gates` are numbered `G1`, `G2`, ... in the order an item meets them, and
  the same numbers appear in the flow. `decides` is `launcher` (the launcher
  enforces it from the config), `agent` (an agent checks it per its
  instructions) or `person`. `sources` are paths relative to the repository
  root, with a line or a line range where the rule is written.
- `settings` and `notes` are optional. Settings are the config values that
  change how work moves: limits, queue order, approvals, runtime rules.

`page.py` stops with an error on a missing or malformed field. It warns,
without stopping, when an outcome adds a label that starts no agent and is no
stop label, when a gate number is missing from the flow or the flow shows one
that is not a gate, and when a text runs past the word budgets above or there
are more than eight gates; past those the report no longer fits two pages.
