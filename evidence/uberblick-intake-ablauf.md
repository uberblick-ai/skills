# uberblick-intake on uberblick-ai/ablauf: evidence

Working notes for PR #46. **Remove this file before merging.**

Repository: [uberblick-ai/ablauf](https://github.com/uberblick-ai/ablauf) at `b75fcd5`: a spec-first TypeScript library and text format with a format spec (`docs/plan.md`), an authoring guide agents read (`spike/PRIMER.md`), research notes, a published site, and 146 tests, all unit tests. Corpus: workspace `45be44e6-d81e-4739-b911-893a98cc1d09` on hub.uberblick.ai, created and promoted for this run (`ub workspace create ablauf`, `ub workspace promote`).

## 1. First dry run, skill as first pushed (`fe41d6b`)

- **Scan guesses that were wrong for this kind of repository:**
  - `docs/plan.md` (the format spec, which AGENTS.md names as the authority): `product`.
  - `spike/PRIMER.md` (the agents' authoring guide, shipped with the package): `product`.
  - `docs/releases.md` (the maintainer release procedure): `changelog`, from its name.
  - `spike/FINDINGS.md` and `spike/trials/**` (research records): `product`.
- **Decisions:** `hot` found no direction changes in 44 commits; the largest changes were feature landings. The real decisions were in `plan.md` (intro, Non-goals), AGENTS.md (its constraints) and maintainers' comments on closed issues (#4, #24, #75). The skill reads none of these.
- **An inferred decider:** the agent marked "Who places a diagram's parts?" as `decided` and credited the maintainer, based on `plan.md`'s "after the owner's direction". Nothing named a person. `check` only warned.
- **The repository's own rules:** AGENTS.md said the corpus holds decision records. The skill didn't make this a scope question; the agent drafted five pages anyway.
- **Smaller issues:**
  - A document already in the corpus needed a stub file and got a "no sources" warning.
  - Drawings are checked with `@uberblick/ablauf@0.2.0`, which has no sequence kind.
  - The tag catalog read `complete: false` with no tags.
- **Result:** 5 pages and 5 records planned, 0 errors, 1 warning, 3 drawings clean.

## 2. Second dry run, with a checkpoint run by hand

The outline and the candidates were shown to the maintainer before drafting. Answers:
- scope: decisions only;
- four records: who places parts, narrow screens, runtime dependencies, string quoting;
- all open; "What may a rendered SVG contain?" dropped.

`check` gave 8 warnings for that plan: no capabilities, 2 groups instead of 3–6, records pinned as entry points. Its rules assumed pages.

## 3. Changes in this branch

| Commit | What |
| --- | --- |
| `7859949` | Neutral analysis: rST, AsciiDoc and Org; `spec`, `agent-guide` and `research` guesses; release files decided by content; `decision_sections`; decision sources (specs, design docs, tracker, history); the step 4 checkpoint; `decided` needs a person's answer (error); `scope` and `checkpoint` in the plan; existing documents need no file; renderer versions from the corpus help |
| `87fa7fe` | Description in the house style from #51 |
| `1168571` | Product intent is the point: the scope defaults to `full`; `check` warns about `decisions` and `pages`; a changed plan unpins nothing (documented) |

Scan of ablauf after `7859949`:

| File | Before | After |
| --- | --- | --- |
| `docs/plan.md` | product | spec (decision section: Non-goals) |
| `spike/PRIMER.md`, `docs/playground.md` | product | agent-guide |
| `docs/releases.md` | changelog | agent-guide |
| `spike/FINDINGS.md`, `spike/trials/**` | product | research |
| `README.md` | product | product (decision section: "Why ablauf") |

## 4. Real run, with writes

1. **Decisions only, as confirmed at the checkpoint:** 0 errors, 0 warnings (8 before the changes). 22 calls applied: tags `format` and `hosting`, four open records, `retag` on the existing Mermaid record, two groups, starter cleanup. `ub` then printed "no hub is reachable". A session opened next was connected and caught up with 0 unsynced changes, so the writes had reached the hub (see uberblick-ai/uberblick-2#2532).
2. **The maintainer asked "what about corpus docs?"** The decisions-only corpus left out the product's intent, which led to `1168571`. Five pages were then added: an overview, Flows, Fan-outs, Sequences, and Show diagrams in a host. The run created tags `flow`, `fan-out` and `sequence`, gave 0 errors and 0 warnings, and rendered 3 drawings with no diagnostics. The five records were unpinned by hand, because `calls` doesn't remove pins a changed plan drops; they now hang off the pages through links.
3. **A missed page:** the maintainer said the intake should have produced a page for the diagram's UI: the Source and Expand toolbar, the full-screen viewer, zoom and Copy. That intent lives in the host: Uberblick's product corpus, "Web UI: blocks". It isn't in this repository, which only has the maintainers' playground toggles. Added by hand as "Reading a diagram in a document". It contradicted two of the intake's texts ("narrow hosts scroll sideways", where Uberblick scales the diagram to fit and never scrolls), which were corrected.
4. **A by-hand edit:** "Placing steps" and "Routing edges" on the Flows page were turned into tables at the maintainer's request. This is for this workspace only; no skill change.

## 5. Still to do in this PR

These were filed as #56–#59 and closed: they belong in this PR, not in separate issues. Each item is a skill change with its evidence.

- [ ] **Product intent from the host.** When the repository names where people meet the product (a host app, an embedding, an editor plugin, a site), the controls they use around its output are capabilities too. Examples: Source and Expand, a full-screen viewer, zoom, copy. Read the host's docs, corpus or code; write the intent from the reader's side, and say where it comes from. Evidence: ablauf's corpus needed "Reading a diagram in a document" by hand, from Uberblick's "Web UI: blocks". Without it, two pages stated "narrow hosts scroll sideways", which the host contradicts: it scales the diagram to fit and never scrolls. Change: a "Hosts" paragraph in `analysis.md`'s capabilities section, and step 3 reads the host's sources.
- [ ] **Depth without journey tests, and the product's kind** (was #56). When the suite has no journeys, weigh areas by history per area, docs volume, issue counts per label, public surface (exports, commands, routes, configuration schema) and the examples folder; `tests.summary` names the signal used. The scan proposes the product's kind from manifests and entry points for the checkpoint to confirm. A monorepo can be scoped to one package or path, with a group per product. Evidence: ablauf's 146 tests are all unit tests.
- [ ] **Any code host** (was #57). Commit and file links come from the remote's host: GitHub `blob/`/`commit/`, GitLab `-/blob/`/`-/commit/`, Bitbucket `src/`/`commits/`, Gitea `src/commit/`, and none without a web view. Today `churn` hard-codes `https://github.com/{remote}/commit/`. Labels and tracker decisions come from whichever command is signed in (`gh`, `glab`, `tea`); today `labels_of` uses `gh label list` only. SKILL.md says a private repository's content goes only to the corpus, and the review page loads no remote resources.
- [x] **Sync state** (was #58). Done: `corpus` and `ub` wait on `sync_status` (`--sync-wait`, 30 s) before any read, which also protects the title-clash check from missing existing documents; a hub still `connecting` (uberblick-2#2532, assumed landed) or `hub-down` with `retry` is waited for until `--settle` and then named as still connecting. Real hub: `corpus` read 11 documents and a `complete` catalog in 3 s, where it read 1 document and an incomplete, empty catalog before. `corpus` waits for the directory and the tag catalog to sync (`sync_status`, with a timeout) before reading, and says whether an empty catalog is synced or not. `ub` checks `sync_status` before reporting, and calls the hub unreachable only when the connection has failed. Evidence: `complete: false` from a short read, synced and empty in a longer session; "no hub is reachable" after 22 writes that had synced. The server side is uberblick-ai/uberblick-2#2532.
- [ ] **Pins on a changed plan.** `calls` reconciles pins when the sidebar changed, or lists the documents to unpin. Today it is only documented in step 9; ablauf's five records were unpinned by hand.
- [ ] **Tag counts.** Count the `tags` of documents marked `existing` (now documented in `plan.md`; `check` still warns when they're left out). Evidence: a `hosting` warning until the tag was marked `core`.
- [ ] **Adding a page by hand.** `intake.py blocks` prints `{meta, blocks, refs}`, not `create_doc` arguments. Either print arguments ready to send, or say so in its help. Evidence: a refused `create_doc` call.
- [ ] **Editing a written page.** `edit_block` needs `rev`, and its `old_text` must be the block's whole current text, not a fragment; links survive because the server diffs. Add this to step 9's "To change a written page".
- [ ] **Wider validation** (was #59). Run dry, and with writes into a sandbox workspace, on a Sphinx/rST Python library, a Java or Kotlin project with AsciiDoc, a Go CLI, a monorepo, a repository whose docs aren't in English, and a private GitLab repository. Record the guesses against the decisions, candidates by source, and what the checkpoint changed.
