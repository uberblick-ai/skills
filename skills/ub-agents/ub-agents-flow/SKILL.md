---
name: ub-agents-flow
description: >-
  Explain how the ub-agents loop runs in a GitHub repository as three
  documents: an overview of the whole loop with one drawing, then one for the
  issue phase and one for the implementation and PR phase, each drawn with
  ablauf, every gate that holds work back (from the config and the agents'
  instruction files) numbered and highlighted, with the roles and the queue
  rules. Combines them into one document on request. Writes Uberblick Markdown
  and a matching page to read or print. Use when a maintainer asks how their loop works, what the flow or the
  gates look like, or wants an overview of the agents. Reads only. Not for a
  loop role.
license: MIT
compatibility: >-
  Requires python3 and Node.js 22.18 or newer with npm, to install the
  @uberblick/ablauf renderer into a scratch directory. Reads the repository's
  checkout, or GitHub through an authenticated gh without one.
metadata:
  author: uberblick-ai
  version: "0.1"
---

# Loop flow

A maintainer should be able to see in a few pages how work moves through their
loop: which agent picks up which label, what each one checks before it lets an
item move on, where work goes back and where it waits for a person. The config
says who runs when; the instruction files say what each agent checks. The
skill writes three documents: an overview with the whole loop in one drawing,
then one per phase with its gates: the issue phase, from a new issue to
`ready`, and the implementation and PR phase, from `ready` to the merge. When
the maintainer asks for one document, it combines them. It uses only what an
Uberblick document holds (headings, paragraphs, `ablauf` fences, tables, cards
and lists), so each Markdown file it writes is a document and the page shows
them the way Uberblick would.

`scripts/render.mjs` and `scripts/page.py` live next to this file; call them
by their path inside this skill's directory. `REPO` is the `OWNER/NAME` of the
repository the loop runs on, `DIR` a scratch directory outside the repository.

1. Read the config. In a checkout of REPO, read `ub-agents.yaml` and note the
   commit with `git rev-parse --short HEAD`. Without a checkout:

   ```sh
   gh api repos/REPO/contents/ub-agents.yaml -H "Accept: application/vnd.github.raw"
   gh api repos/REPO/commits/HEAD --jq .sha
   ```

   Without an `ub-agents.yaml` the repository does not run the loop; say so
   and stop. Note every agent with its `kind`, `trigger`, `outcomes` (the
   labels each adds and removes, any `max-rounds`), `instructions`,
   `different-runtime-from` and timeouts, and the top-level `stop-labels`,
   `approvals`, `trusted-pr-authors`, `queue`, `limits` and
   `shared-instructions`. Note any trigger label that no outcome adds, such as
   a bot's own label: work enters there without an issue.

2. Read the guidance with line numbers: `AGENTS.md`, the
   `shared-instructions` file, each agent's `instructions` file and the policy
   files they point to, from the checkout or with
   `gh api repos/REPO/contents/PATH -H "Accept: application/vnd.github.raw"`.
   Find the gates, the points where an item cannot move on until a check
   passes, and the line each comes from:

   - Launcher gates, from the config: stop labels pause all work; with
     `approvals` on (the default for public repositories) only a maintainer's
     trigger label starts work; open blocked-by issues hold an issue (unless
     `queue.dependencies` says otherwise); `milestones: gate` holds later
     milestones; `max-attempts` marks an item failed; `max-rounds` stops a
     loop back; `different-runtime-from` picks the reviewer's runtime.
   - Agent gates, from the instructions: what must be true before the agent
     reports its passing outcome (criteria, checks, the exact head, a ready
     PR), and what makes it send work back or stop for a person.
   - Person gates: what the shared policy leaves to maintainers, such as
     merges of certain paths or scope decisions.

   Merge what one agent checks into one gate unless the maintainer asks for
   every check. Sort every agent and gate into a phase: issue agents (`kind: issue`, such
   as the issue-preparer and an optional issue-reviewer) up to the label the
   implementer starts on, the rest after it. Note anything that does not fit: an outcome label no agent picks up, an
   agent no outcome reaches, a rule in the instructions the config cannot
   route, a role that can only stop by reporting blocked.

3. Write `DIR/flow.json` as [references/page.md](references/page.md)
   describes: the overview with a three-sentence summary and its notes, first
   one per `queue` setting in use, saying what it does and linking its section
   of https://agents.uberblick.ai/docs/configuration/queue.html, then the
   findings that span the loop; the two phases with a sentence each, their
   roles, their gates numbered from `G1` in the order an item meets them with
   one plain sentence each, and their own findings; and every role. Describe the queue as the launcher runs it; where
   the repository's own instructions say otherwise, add that as a finding.

4. Draw `DIR/overview.flow`, `DIR/issue.flow` and `DIR/pr.flow` as
   [references/flow.md](references/flow.md) describes, starting from
   [assets/overview.flow](assets/overview.flow),
   [assets/issue.flow](assets/issue.flow) and [assets/pr.flow](assets/pr.flow):
   the path an item takes when every gate passes down the middle, rework on
   the left, the stop panel on the right, every gate numbered as in its phase
   in `flow.json`. The overview adds any way work enters without an issue.

5. Render both, installing the renderer once per scratch directory:

   ```sh
   npm install --prefix DIR/ablauf @uberblick/ablauf@0.2.0
   node scripts/render.mjs DIR/ablauf DIR/overview.flow DIR/issue.flow DIR/pr.flow
   ```

   Each `.svg` lands next to its `.flow`. It fails on any diagnostic and
   names the line; fix it and render again until all three print `clean`.

6. Build the documents and open them:

   ```sh
   python3 scripts/page.py DIR/flow.json --out DIR/flow.html --open
   ```

   It writes `DIR/overview.md`, `DIR/issue.md` and `DIR/pr.md` in Uberblick
   Markdown, and `DIR/flow.html`, the same blocks styled like Uberblick
   documents with each `ablauf` fence drawn. When the maintainer asks for one
   document, add `--combine`: it writes `DIR/flow.md` instead, the overview
   followed by each phase under its own heading. Fix every warning it prints (an outcome label
   that starts nothing, a gate missing from the drawings, a text over its word
   budget) unless it is a real finding about the loop, which belongs in
   `notes`. Printed, each document starts a new A4 page, light even from a
   dark screen.

7. Tell the maintainer where the page and the Markdown are, then in a few
   sentences: the path an item takes in each phase, the gates where a person
   decides, and anything from the notes that looks like a mistake in the
   config or the instructions. Change nothing on GitHub; offer to open an
   issue only if they ask. When they store the documents in Uberblick, create
   the phase documents first, then the overview, and link each phase name in
   its table to that phase's document.
