---
name: uberblick-intake
description: >-
  Move a repository's knowledge into Uberblick. Reads every Markdown file,
  the git history and the test suite, then proposes the corpus: which files
  become product pages and which stay in the repository as technical,
  implementation or agent Markdown, the tags for this repository, decision
  records for the questions the history keeps reopening, ablauf drawings
  and wireframes where a picture says it better, pages as deep as the tests
  show the team cares, and a sidebar ready for the team. Shows the whole
  plan on one review page and writes it to the workspace once approved. Use
  when someone wants to set up Uberblick for an existing repository, migrate
  their docs into the corpus, or asks what an intake would create.
license: MIT
compatibility: >-
  Requires python3 and git, and Node.js 22.18 or newer with npm to check and
  draw ablauf and wireframe blocks. Writing to the corpus needs the Uberblick
  MCP tools or the `ub` command in a checkout bound to a workspace; without
  either it stops at the review page. Reads GitHub labels with an
  authenticated gh when there is one.
metadata:
  author: uberblick-ai
  version: "0.1"
---

# Intake

A new Uberblick workspace is only as useful as what it holds on day one. The
repository already knows a lot: what the product does (README, user docs),
how it is built (contributor and reference docs), what agents are told
(AGENTS.md and friends), which questions keep coming back (the history) and
what the team cares about enough to test end to end. This skill sorts that
into a corpus a person can trust: product intent as pages, the questions that
mattered as decision records, everything technical left as Markdown next to
the code, with a sidebar that opens on the right pages.

`scripts/intake.py` and `scripts/viz.mjs` live next to this file; call them by
their path inside this skill's directory. `CHECKOUT` is the repository's
checkout, `DIR` a scratch directory outside it. The plan's shape is in
[references/plan.md](references/plan.md), how to judge each part in
[references/analysis.md](references/analysis.md), drawings in
[references/visuals.md](references/visuals.md).

1. **Find the corpus.** The corpus is reachable when Uberblick MCP tools are
   in your tool list (whatever the server is called; load tools listed by
   name only), or through `ub` in a checkout bound to a workspace
   (`command -v ub` finds it, and the checkout or a parent holds
   `.uberblick.json`):

   ```sh
   python3 scripts/intake.py corpus --checkout CHECKOUT --dir DIR/corpus
   ```

   It prints the workspace, its documents, sidebar groups and tags, and
   saves them as `DIR/corpus/tags.json`, `sidebar.json` and `docs.json`.
   When the workspace is bound in another directory than the repository's
   checkout, pass that directory as `--checkout` here and to `ub`.
   Through the MCP tools, call `list_tags`, `get_sidebar`, `list_docs` and
   `list_docs` with `kind: decision` (decision records are listed only then),
   and save the `list_tags` answer as it stands (`{"tags": [{"id", "name"}],
   "complete": …}`; other keys are fine) as `DIR/corpus/tags.json`. When
   both routes are there, write through `ub` (step 8): one command, with
   the checks and the wait for the hub. It opens the same workspace replica
   as the connected MCP server, so both can run at once. A fresh workspace
   holds two starter pages in an "Uberblick" group (older versions spell
   it "Überblick"; go by what `get_sidebar` shows) and six starter tags
   (auth, billing, mcp, permissions, rfc, sync); reuse a starter tag only
   where it fits. A catalog marked `complete: false` has not synced yet:
   read it again before the writes. A local workspace (`"hubUrl": null` in
   `.uberblick.json`) syncs with the hub `ub open` serves on this machine:
   while that is not running, its catalog reads `complete: false` yet is the
   whole catalog, answers report the hub as `local` (older servers:
   `hub-down` with `retry`, which is expected here too), and the writes
   wait in the replica until it runs. Leave `ub open` to the person: it
   serves a web page that keeps running after you finish. With neither
   route, say so in one line: the run ends with the review page and the
   Markdown files. Read
   the repository's own rules for corpus pages if it has any (AGENTS.md and
   the files it points to); otherwise follow the rules in
   [references/analysis.md](references/analysis.md#writing-pages). Its
   rules for code changes (commit, branch, ask before acting) do not apply:
   an intake changes no file in the repository.

2. **Scan.**

   ```sh
   python3 scripts/intake.py scan CHECKOUT > DIR/scan.json
   python3 scripts/intake.py hot DIR/scan.json > DIR/hot.txt
   python3 scripts/intake.py tests DIR/scan.json > DIR/tests.txt
   ```

   `scan` lists every tracked Markdown file with its headings, size, history
   and a first guess at its class (`guess`, with `why`; a file with the
   same text as an earlier one is `duplicate`), finds a docs site (mkdocs, Docusaurus,
   mdBook and others), walks up to 5,000 commits for the files and areas that
   change most and the commits that changed direction, lists the largest
   changes on the main line over the whole history (a feature landing, a
   rewrite, a migration, merges included), and counts the tests
   per area and topic, by kind: `e2e` (a browser or device), `e2e-api`,
   `cli` (the built command, end to end), `integration`, `unit`. `hot` and
   `tests` print the same facts to read. Kinds, topics and direction changes
   are heuristics from names and messages: facts to check, not findings. It
   takes seconds to a few minutes, reads committed files and warns about
   uncommitted changes; the pages describe the commit in `ref`. Run git with
   `-c gc.auto=0` when you read further, so the checkout is left as it was.
   `hot.txt` and `tests.txt` run to tens of kilobytes on a large repository:
   read them in parts.

3. **Read.** The guesses are a starting point, never the answer. Read the
   README, the docs site's navigation file, every file guessed `product`,
   `decision` or `rfc`, and enough of the rest to confirm its class. Read the
   journey titles (`e2e` and, for a command-line product, `cli`): they name
   what the team protects. Read the
   code an area's page would describe, enough to state what a person can do
   there: commands, screens, settings, as the code has them today, not as
   old docs describe them. For each hot area, direction change and large
   change, open the patch (`git -c gc.auto=0 show SHA`) and the code it
   touched today before calling it a decision. A large docs site is too much
   to read whole: read its navigation, then the pages and code behind each
   capability, deepest where the tests are. The user documentation is not
   always Markdown: read a man page (`*.1`), a settings template
   (`.env.template`, a sample config) or the CLI's help text as the source
   it is.

4. **Decide** each part as [references/analysis.md](references/analysis.md)
   describes:

   - every Markdown file: `convert` into a named page, `keep` as Markdown, or
     `skip` (generated, fixture, release note fragment, duplicate), with one
     line of why; a folder can be one entry (`docs/reference/**`), a mixed
     file one entry per heading (`sections`). Installation, packages,
     building and other setup, and contributing, sponsors and other
     community sections, stay as Markdown (the scan lists them as
     `keep_sections`); a page links to them. Nothing converted leaves the
     repository unless a person accepts that change;
   - the capabilities: what a person can do with the product, each with its
     evidence and the page that covers it, or why none does;
   - the pages: one per product area or concept a person acts on, small,
     with the scenarios that matter to a person, deeper where tests and
     docs show the team's weight. A capability with its own journey tests
     or docs section and no page is a gap to fill, not a saving: coverage
     matters more than finishing fast;
   - the decision records: existing ADRs, and the few history candidates
     that meet all four criteria, `open` unless a person decided them;
   - 2 to 12 tags, reusing the catalog's names first (the plan proposes
     them even when the catalog lacks them and the writes leave them off);
   - where a drawing helps: ablauf for a flow with branches or phases,
     wireframe for a screen the page describes;
   - the sidebar: 3 to 6 groups, one per domain, topic or responsibility;
     each pins its entry points, pages that link on to the domain's
     other pages and records, so every document is reachable from a pin.

5. **Write** `DIR/docs/<slug>.md`, one Uberblick Markdown file per document,
   and `DIR/intake.json`, as [references/plan.md](references/plan.md)
   describes. Link pages to each other with `[text](ref:slug)`; the writer
   turns these into document links. Never copy a source file: rewrite it as
   the page it should be.

6. **Check** the drawings, the plan and the claims, installing the
   renderers once per scratch directory (skip both when no page has an
   `ablauf` or `wireframe` block):

   ```sh
   npm install --prefix DIR/node @uberblick/ablauf@0.2.0 @uberblick/wireframe@0.3.2
   node scripts/viz.mjs DIR/node DIR/docs/*.md
   python3 scripts/intake.py check DIR/intake.json --scan DIR/scan.json --checkout CHECKOUT --tags DIR/corpus/tags.json
   ```

   `viz.mjs` draws each ablauf block into `DIR/docs/viz/` and fails on any
   diagnostic with the file and line; fix and run again until it prints no
   diagnostics. `check` stops on an error (a Markdown file nobody accounted
   for, a link to no document, a decision answer over 60 words, a tag not in
   the plan) and warns on what usually needs a fix (history or plans in a
   page, a page over 900 words, a group pinning more than 3 entry points, a
   document no pin leads to). Fix every
   warning or keep it knowingly.

   Then check every page against the code at `ref`: each command, option,
   label, default and behaviour it states. When the `uberblick-corpus-sync`
   skill is installed, run it in report mode on the drafts
   (`DIR/docs/*.md`, with `sources` and `tests` from the plan); otherwise
   re-read the sources yourself. Fix what does not hold before the review:
   the person approves pages that are already true.

7. **Review.** Build the page and open it (leave off `--open` when nobody
   is there to look):

   ```sh
   python3 scripts/intake.py review DIR/intake.json --scan DIR/scan.json --out DIR/review.html --open
   ```

   It shows the sidebar beside every document as it will be written, with
   the drawings, the tags, every Markdown file's fate, the decision
   candidates with their commits, the test focus and the proposed
   repository changes. Tell the person in a few sentences what the corpus
   will hold and where it overlaps a published docs site, then ask once for
   approval to write it, whether to unpin the starter pages (their emptied
   "Uberblick" group is deleted; the pages stay in the workspace), and
   whether to create the new tags. Writes go to a workspace the team shares: wait for the
   answer. Change the plan as they ask and build the page again. When you
   run unattended and were told the review counts as approved, write the
   page anyway, follow what you were told about the starter pages and the
   tags, and name those choices in the report.

8. **Write to the corpus.** Read the workspace again (step 1) so the writes
   use only tags that exist, then, with `ub`:

   ```sh
   python3 scripts/intake.py calls DIR/intake.json --tags DIR/corpus/tags.json --create-tags > DIR/calls.json
   python3 scripts/intake.py ub --calls DIR/calls.json --checkout CHECKOUT --out DIR/applied.json
   ```

   Leave off `--create-tags` when the person did not approve the new tags.
   It needs ub 0.4.11 or newer (the server lists `create_tag`); with an
   older one, a person creates them under Workspace settings → Tags.

   `calls` writes in two passes, so every link can name its target. With
   `--create-tags` it starts with a `create_tag` for each new tag. Then
   `create_doc` for every document with its metadata only (pages, then
   decision records with `related` naming their page); then `insert_block`
   with each document's blocks, links included; then the pins group by
   group, the starter cleanup when the plan unpins the starter pages (marked
   `optional`: a page already unpinned is fine), and the groups' order.
   `{"$ref": slug}`, `{"$doc": slug}` and `{{uuid:slug}}` stand for the
   UUID that slug's `create_doc` returned.

   `ub` runs them through one `ub mcp serve`. Before the first write it
   refuses when the workspace already has a document with a planned title
   (rename it in the plan, mark it `existing: UUID`, or pass `--adopt` to use
   the one there). It records the workspace, the calls and the UUIDs in
   `DIR/applied.json`, stops at the first refusal (fix it and re-run the
   same calls with `--resume`), waits for the hub to acknowledge and prints
   the sidebar as written. Where the server checks the drawings it writes,
   `ub` prints each one that is not `clean`, with its first diagnostic; fix
   those with `edit_block`.

   With the MCP tools instead of `ub`, `resolve` hands you the calls in
   batches, one per line, each with the UUIDs it can fill in:

   ```sh
   python3 scripts/intake.py resolve --calls DIR/calls.json --uuids DIR/uuids.json
   ```

   The first batch is the `create_tag` calls and the pages' `create_doc` calls; notes on where it
   stopped go to stderr. Send each `arguments` to the tool named `tool`, add
   `"slug": "uuid"` from each answer to `DIR/uuids.json` (a plain JSON
   object; each line names its `slug`), and run `resolve` again: it skips
   what is done and stops before the next call that needs a UUID you have
   not saved yet. Two or three rounds cover a corpus. If the server's
   `insert_block` schema has no `blocks` (older versions; go by the
   schema, not `ub --version`, which a development build prints as 0.0.0;
   `intake.py ub` handles this itself), add `--one-block`: each insert goes in at the top,
   so they come last block first, and sending them in order puts the page
   together. Send the calls in
   order; the first pin into a group creates it, so never send two pins in
   parallel while their group does not exist yet. The starter cleanup is
   two `unpin_doc` calls and a `sidebar_group` `delete` of the emptied
   starter group, all marked `optional`: a refused one is fine; stop at
   any other refusal and fix it. When a write answer carries a `drawing`
   whose status is not `clean`, fix that block with `edit_block`. The group moves at the
   end can be left out when `get_sidebar` already shows the plan's order.
   Last, call `sync_status`: the writes are done once nothing is unsynced.
   A local workspace has no hub until `ub open` runs in the checkout, so
   there the writes are done once applied; say they sync while `ub open`
   runs, and leave starting it to the person.

   Tags the catalog still lacks are left off and named. Once a person
   creates them, or to write a changed plan, read the workspace again and
   pass `--applied DIR/applied.json` (or `DIR/uuids.json`) to `calls`, with
   a new `--out` for `ub` (or a new uuids file for `resolve`): documents
   already written are not created again, only given their tags with
   `set_metadata` and pinned; their content stays as written. To change a
   written page, edit it with the MCP tools (`get_help` topic `edit_doc`).
   `get_doc` shows a prose block's formatting as `inline` runs where the
   server returns them; otherwise `export_markdown` shows it.

9. **Record the grounding.** When the `uberblick-corpus-sync` skill is
   installed, run it in apply mode on the pages just written (their UUIDs
   from `applied.json`) and in report mode on the Markdown kept in the
   repository, at the same commit: it records on each page which commit it
   was checked against. Without it, say that the pages were checked by
   hand at `ref` and carry no recorded check. Intake never records
   `code_check` itself.

10. **Report.** Tell the person what was created (pages, decision records,
    pins, tags), what stays in the repository as Markdown, what was skipped,
    the decision candidates left out and why, and the repository changes
    from the plan: converted files to remove or shorten to a pointer, and a
    line in AGENTS.md or the README naming the corpus as the home of product
    intent. Make those repository changes only when asked, on a branch.
