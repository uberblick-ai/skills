---
name: ub-agents-flow
description: >-
  Explain how the ub-agents loop runs in a repository as an overview and one
  document per phase, each with an ablauf drawing and every gate that holds
  work back, numbered, from the config and the agents' instruction files.
  Use for "how does our loop work?", "draw the agent flow and its gates",
  "update the loop docs after the config change" or "where does a person step
  in?". Writes Uberblick Markdown and a printable page to a scratch directory
  and, when an Uberblick MCP server is connected, creates or updates the loop
  documents in the corpus; changes nothing on GitHub. Not for running a loop
  role, reviewing a pull request or reporting a day's deliveries.
license: MIT
compatibility: >-
  Requires python3 and Node.js 22.18 or newer with npm, to install the
  @uberblick/ablauf renderer into a scratch directory. Reads the repository's
  checkout, or GitHub through an authenticated gh without one, and the
  Uberblick corpus through a connected Uberblick MCP server when there is one.
metadata:
  author: uberblick-ai
  version: "0.1"
---

# Loop flow

A maintainer should see in a few pages how work moves through their loop:
which agent picks up which label, what each checks before an item moves on,
where work goes back and where it waits for a person. The config says who runs
when; the instruction files say what each agent checks. The skill writes an
overview with the whole loop in one drawing, then one document per phase with
its gates, in Uberblick Markdown.

`scripts/render.mjs` and `scripts/page.py` live next to this file; call them
by their path inside this skill's directory. `REPO` is the `OWNER/NAME` of the
repository the loop runs on, `DIR` a scratch directory outside the repository.

1. Read the config as the default branch has it, whatever the checkout is
   on. In a checkout of REPO, `git fetch origin`, then read the files with
   `git show origin/HEAD:PATH` and note `git rev-parse --short origin/HEAD`.
   Without a checkout:

   ```sh
   gh api repos/REPO/contents/ub-agents.yaml -H "Accept: application/vnd.github.raw"
   gh api repos/REPO/commits/HEAD --jq .sha
   ```

   Without an `ub-agents.yaml` the repository does not run the loop; say so
   and stop. Note every agent with its `kind`, `trigger`, `outcomes` (the
   labels each adds and removes, any `max-rounds`), `instructions`,
   `different-runtime-from` and timeouts, and the top-level `stop-labels`,
   `approvals`, `trusted-pr-authors`, `queue`, `limits`, `events` and
   `shared-instructions`, and any outcome's `sub-issues` labels. Note any
   trigger label that no outcome adds, such as a bot's own label: work enters
   there without an issue.

2. Read the guidance with line numbers: `AGENTS.md`, the
   `shared-instructions` file, each agent's `instructions` file and the policy
   files those point to directly, from the checkout or with
   `gh api repos/REPO/contents/PATH -H "Accept: application/vnd.github.raw"`.
   Find the gates, the points where an item cannot move on until a check
   passes, and the line each comes from:

   - Launcher gates, from the config: stop labels pause all work; with
     `approvals` on (the default for public repositories) only a maintainer's
     trigger label starts work; open blocked-by issues hold an issue (unless
     `queue.dependencies` says otherwise); `milestones: gate` holds later
     milestones while an earlier one has work that can start; `max-attempts` marks an item failed; `max-rounds` stops a
     loop back; `different-runtime-from` picks the reviewer's runtime;
     `on-conflict` routes a conflicting pull request; `trusted-pr-authors`
     lets a bot's pull requests start without a maintainer. For what a
     setting does, read the launcher's docs
     (https://agents.uberblick.ai/docs/) for the version installed
     (`ub-agents --version`), not the repository's description of it.
   - Agent gates, from the instructions: what must be true before the agent
     reports its passing outcome (criteria, checks, the exact head, a ready
     PR), and what makes it send work back or stop for a person.
   - Person gates: what the shared policy leaves to maintainers, such as
     merges of certain paths or scope decisions.

   Merge what one agent checks after its work into one gate, and a check
   before its work into another, unless the maintainer asks for every check. Sort every agent and gate into a phase: issue agents (`kind:
   issue`, such as the issue-preparer and an optional issue-reviewer) up to
   the label the implementer starts on, the rest after it. For every stop,
   note why an agent takes it, in the instructions' words: these reasons
   label the edges into the stop panel.

   Read the CI workflows the instructions name and the command `events` runs,
   for what each changes and who hears of what.

   Note anything that does not fit: an outcome label no agent picks up, an
   agent no outcome reaches, a rule in the instructions the config cannot
   route, a role that can only stop by reporting blocked (a blocked report
   adds no label, so label views and hooks that filter on labels miss it),
   sub-issues that get no label from a `sub-issues` outcome or from the
   instructions and so wait for a person.

3. Read the corpus, if there is one. The corpus is available when an
   Uberblick MCP server is connected, whatever its name, such as `uberblick`
   or `uberblick-agents`. Its tools may be listed by name only; load them
   before using them, and with more than one server, search each. Search for
   documents on the loop, the agents or the delivery workflow (`search`,
   `list_docs`), including the ones an earlier run of this skill wrote, and
   read each one (`export_markdown` or `get_doc`). Read the repository's own
   rules for writing corpus pages too, if it has any (in `AGENTS.md` or the
   files it points to). Without a server there is no corpus; skip this step. Compare what the documents say with what steps 1
   and 2 found, and keep a list of the differences that matter: a gate, a
   route, a label, an agent, a rule or a person's decision that the corpus
   describes otherwise or leaves out, each with the document, what it says
   and what the config or the instructions say, with the line. Leave out
   wording and layout. Step 8 fixes in place what the corpus states wrongly;
   the list itself goes in no document. A gap between the config and the
   instructions is a finding for the notes instead.

4. Write `DIR/flow.json` from what steps 1 and 2 found, as
   [references/page.md](references/page.md) describes. When step 3 found
   earlier documents, steps 4 to 7 are a check on the gates and drawings:
   what you store is step 8's list of block edits.

5. Draw every `.flow` that `flow.json` names as
   [references/flow.md](references/flow.md) describes. When step 3 found the
   drawings an earlier run stored, start from those, so a maintainer's layout
   survives; otherwise start from [assets/](assets/).

6. Render them all, installing the renderer once per scratch directory:

   ```sh
   npm install --prefix DIR/ablauf @uberblick/ablauf@0.2.0
   node scripts/render.mjs DIR/ablauf DIR/*.flow
   ```

   Each `.svg` lands next to its `.flow`. It fails on any diagnostic and names
   the line; fix it, usually by moving a node with `row=` or an edge end with
   `to=`, until every drawing prints `clean`. Then look at each drawing
   (rasterize the `.svg` at its full width and read the image), since a clean
   render can still read badly: the passing path runs straight down, a
   side route that rejoins it runs straight across, and every label reads.

7. Build the documents and open them:

   ```sh
   python3 scripts/page.py DIR/flow.json --out DIR/flow.html --open
   ```

   It writes one Markdown file per document and `DIR/flow.html`, the same
   blocks styled like Uberblick. When the maintainer asks for one document,
   add `--combine`: it writes `DIR/flow.md` instead. Fix every warning it
   prints unless it is a real finding about the loop, which belongs in
   `notes`.

8. Store the documents in the corpus whenever there is one, unless the
   maintainer asked for files only. Follow the repository's rules for corpus
   pages from step 3. When step 3 found the documents an earlier run wrote,
   update them in place: change only the blocks whose facts changed, and keep
   every edit a maintainer made (wording, added or removed blocks, links,
   headings, merged paragraphs, a removed TL;DR). Never add back what a
   maintainer removed. Maintainers edit while you work: read a document again
   right before editing it. Revisions (`list_revisions`) tell a maintainer's
   change from an earlier run's output. Where a maintainer's layout and a
   drawing convention pull apart, keep the layout and change only what a
   missing or wrong fact needs. A text edit cannot add a link and can shift
   the formatting next to it; to add a link, or to change text that touches
   bold, code or a link, replace the block (`insert_block` the new one, then
   `delete_block` the old). A block that carries comments is never replaced:
   edit only its outdated words. Update a document's description when it
   names something that changed. Check every edited block with
   `export_markdown` afterwards, and name to the maintainer any whose
   formatting you could not keep. Otherwise
   create them: the phase documents first, then the overview, with each
   document's name linked in the overview's documents line and in the bold
   name that starts its point, and the overview's title linked in each phase
   document's opening "Details of" line. Set no TL;DR: each document's first paragraph is its
   summary. Tag
   every document with the corpus's tag for workflow documents, such as
   `workflow`, when it has one; never invent a tag. With
   `--combine`, store the one document. Check that every write was applied
   and synced, and name any that was not. Without a corpus, the Markdown files
   are the result.

9. Tell the maintainer which documents were created or updated, or where the
   page and the Markdown are, then in a few sentences: the path an item takes
   in each phase, the gates where a person decides, and anything from the
   notes that looks like a mistake in the config or the instructions. Then
   number the differences from step 3, one line each. Change nothing on
   GitHub; offer to open an issue only if they ask. For example:

   ```text
   Updated "Loop: issue phase" (G2 card, one note) and "Loop: PR phase" (drawing).
   Issue phase: a maintainer adds needs-preparation; the preparer checks intent
   and scope (G2-G4) and marks small work ready, the rest gets one review (G5).
   PR phase: one PR, a review on another runtime when owed, the integrator's
   final gates, then the merge. A person decides at needs-human and tier-3 merges.
   Looks like a mistake: workflow.md describes the milestone order otherwise
   than the launcher runs it.
   Corpus differences:
   1. G2 card: another PR for the issue goes to needs-human, not returned.
   ```

   When nothing changed: `The loop documents match <ref>; nothing to update.`
