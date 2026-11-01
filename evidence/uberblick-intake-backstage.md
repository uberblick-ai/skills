# Evidence: uberblick-intake on backstage/backstage

> Temporary. This folder collects evidence from trial runs of the skill for PR #46.
> Delete `evidence/` before merging. One file per run, named `<skill>-<repo>.md`.

## The run

| | |
| --- | --- |
| Repository | [backstage/backstage](https://github.com/backstage/backstage) at `24deeed960` (2026-10-31) |
| Product | A TypeScript framework for building developer portals: a monorepo of 261 workspace packages (core packages, about 200 plugins and modules, a scaffolded-app template), 76,879 commits since 2020, 12,391 files |
| Docs in the repository | 2,095 documentation files: the backstage.io docs site source (`docs/`, Docusaurus in `microsite/`), a second docs site for the component library (`docs-ui/`, Next.js MDX), 16 ADRs, 15 enhancement proposals (`beps/`), about 480 package READMEs, about 570 generated reports, about 655 changelogs and release notes. No wiki. |
| Skill | `uberblick-intake` 0.1, skill files as of `d5c3ad5` (unchanged at `80e5b09`, the branch head when the run started), run by Claude Opus 5.5 on 2026-11-01 |
| Corpus | A temporary local workspace `backstage-intake-trial` (`ub workspace create`, ub 0.4.13) in a scratch folder passed as `--checkout`. The connected MCP server was not used; help was read through `ub mcp serve` in the scratch workspace. |
| Person | The session's user, standing in for the owner, answering through the parent session |

**Result.**

| Item | Result |
| --- | --- |
| Markdown files | 2,095 files covered by 75 plan entries: 39 convert entries (sources; every file stays), 19 keep globs, 17 skip globs |
| Documents | 17 pages and 7 decision records, all `open` |
| Tags | 6 new (`catalog`, `software-templates`, `techdocs`, `search`, `plugins`, `integrations`) and 3 starter tags reused (`auth`, `permissions`, `mcp`) |
| Sidebar | 6 groups and 7 pins; the starter pages unpinned and their group deleted |
| Drawings | 2 ablauf, 1 wireframe; all looked at after rasterising |
| `viz.mjs` | 9 diagnostics in 2 drawings on the first run, 0 after fixes |
| `check` | 8 errors and 3 warnings on the first run, 0 after fixes; 14 false or imprecise claims caught by hand, none by `check` |
| Writes | 70 of 70 calls applied in 0.6 s; read back with `intake.py corpus`: 26 documents (24 plus the 2 starter pages), the 6 groups in order, 14 tags |

**Cost.** Wall time about 66 minutes from start to read-back, of which about 14 were waits for the person
(checkpoint 18:31 to 18:39, review 19:04 to 19:10). Not counting waits:

| Step | Wall time | Tool calls (about) |
| --- | --- | --- |
| Clone (full clone aborted, then blobless) | 11 min | 10 |
| 1 Corpus, 2 Scan (first scan stalled, killed; second 7.9 s) | 5 min | 10 |
| 3 Read, 4 Outline | 9 min | 45 |
| 5 to 7 Decide, draft, check claims against code | 22 min | 95 |
| 8 Review | 1 min | 4 |
| 9 to 11 Write, read back | 2 min | 6 |

No delegation. Tokens were not measured. Reading code to check claims was the dominant cost, as on AntennaPod.

**The corpus.** 6 groups:
- **Backstage:** overview; your app (home page, sidebar, settings, app-config); notifications
- **Software catalog:** catalog (with a wireframe of the catalog page) → entities, adding software, APIs, Kubernetes
- **Software templates:** using templates (with an ablauf of a task's life) → writing templates
- **TechDocs and search:** TechDocs (with an ablauf of how a site gets built); search
- **Access:** sign-in and identity → permissions
- **Extending Backstage:** extending → integrations, AI actions and MCP

The 7 records, all `open`: how software is described in the catalog (ADR002, ADR008); which entities the
catalog models (ADR005); how entities refer to each other (ADR009); who may call an instance's APIs
(BEP 0003, 0007); how an app adds frontend features; how backend features are composed (maintainer RFC
#11611); which design system plugin screens use (maintainer RFC #27726).

## Where a person stepped in

The person answered two questions at the checkpoint and one at the review. Each accepted the recommendation:

1. Scope, 6 groups and 17 pages, the other plugins on one Integrations page: "Keep as proposed (Recommended)".
2. Records: "R1-R7, drop R8 (Recommended)". R8 was the one record built on a proposal not yet in place.
3. Writes, starter unpin and new tags: "Yes, all of it (Recommended)".

File fates and tags weren't asked separately; the person saw them in the summary and changed nothing. That
is recorded as an assumption in the plan's `checkpoint`.

Nothing had to be corrected, so this run has no quote that names a gap. The gaps below are what the agent
hit on its own, and the recommendations the person accepted are only as good as the agent's reading: the
person did not know the product either.

## Findings

Severity: **high** = wrong output, blocks the run, or makes a person step in; **medium** = slows the run or
misleads; **low** = polish. Backstage supplies the evidence; every fix is written so it holds for any repository.

### Getting the repository (before step 1)

1. **High (cost): the skill assumes a full clone, and a large repository can't be cloned in reasonable time.**
   The repository is 7.9 GB (`gh api repos/... --jq .size` = 7,948,952 KB). A full clone ran at about
   0.7 MB/s and would have taken hours; I aborted it after 97 s. A blobless clone
   (`git clone --filter=blob:none`) took 9 min 21 s, holds every commit and tree, and `scan` needs nothing
   else, since it reads blobs only for files at HEAD. Fix: say in step 2 that a blobless clone is enough
   for the scan, and that the scan needs the full commit history, not every blob.
2. **High (cost): in a blobless clone, `scan` stalls on rename detection.** `churn()` (`intake.py` line 438)
   and `md_history()` (line 399) run `git log --name-only` without `--no-renames`, so git fetches blobs one
   by one from the remote to detect renames. The first scan was still fetching after more than 3 minutes
   (a `git fetch --filter=blob:none` child process, seen with `ps`); I killed it. After those blobs were
   cached, the same scan took 7.9 s. `milestones()` (line 419) already passes `--no-renames`. Fix: pass
   `--no-renames` (or `-c diff.renames=false`) to every history walk; the counts per path barely change.

### Finding the corpus (step 1)

3. **Low: step 1's description of a fresh workspace is out of date.** It names six starter tags
   (`SKILL.md` line 75); ub 0.4.13 seeds eight (`guidance` and `technical-reference` as well, both with
   descriptions). It says a local workspace's catalog reads `complete: false` while `ub open` isn't running
   (line 86); here `list_tags` answered `complete: true` with hub status `local`. Neither misled the run.
   Fix: say "the starter tags `list_tags` shows" and drop the claim about `complete` for a local workspace,
   or make it conditional on the server version.

### Scan and tests (step 2)

4. **High: the root README was guessed `agent-guide`, which means "keep".** A skill file under
   `.agents/skills/` mentions a different `README.md` in backticks ("Skip `README.md`", meaning the one in
   `.changeset/`). `scan_markdown()` resolves every named file twice, as written from the root and relative
   to the naming file (`intake.py` line 385, `ref.lstrip("./")`), so a bare file name matches the root
   README. The README lost its `keep_sections` and would have stayed out of the overview if read at face
   value. Fix: resolve a name relative to the naming file first and from the root only when it holds a `/`;
   and take sources only from agent instruction files, not from every file under a skills folder.
5. **High: enhancement proposals with status frontmatter were guessed `product`.** 14 of the 16 files in
   `beps/` (`NNNN-title/README.md`, YAML frontmatter with `status: implemented | implementable |
   provisional`, `owners`, `creation-date`) were guessed `product`, with "Dependencies" as a section to keep.
   The `RFC` pattern (line 78) knows `rfcs/`, `proposals/`, `design-docs/`, `specs/` and `plans/`, and
   `md_facts()` keeps only frontmatter keys (line 270), not values. These files were the best decision
   evidence in the repository after the ADRs. Fix: treat a file whose frontmatter has a `status` with a
   proposal value (draft, provisional, proposed, implementable, accepted, implemented, rejected,
   withdrawn) as `rfc`, and keep that value in `scan.json` so step 5 can tell accepted from open; also
   match the common `*eps/` folder names and numbered proposal folders.
6. **Medium: 221 generated reports were guessed `product`.** Every package has a `knip-report.md`
   (`# Knip report` and a table), with no "do not edit" marker, so `guess_class()` falls through to
   `product` (line 315). That is 221 of the 591 `product` guesses; translated READMEs (`README-fr_FR.md`
   and three more) and community lists (`ADOPTERS.md`, `OWNERS.md`, `LABELS.md`) add 7 more. Fix: a file
   name that recurs in many package folders with the same headings is a report: guess `generated`; and
   guess `README-<locale>.md` and `README.<locale>.md` as translations (`skip`).
7. **Medium: `tests` counts 52 browser journeys where there are 6, and misses the real end-to-end suite.**
   - 44 cases come from one unit test of a UI hook. `test_kind()` matches `onView\(` (Espresso) without a
     word boundary (line 513), so a component named `AnchorNavigationView(` makes the file `e2e`.
   - 2 more are a helper's unit test in a package named `e2e-test`: `E2E_PATH` matches the package folder.
   - The real journeys are 6 Playwright cases, 2 of them in templates that copy the app.
   - The end-to-end weight sits in CI scripts the scan doesn't see: a package scaffolds a fresh app and
     runs its Playwright tests, and a CI job runs the docs CLI end to end (`verify_e2e-*.yml`).
   - Fix: `\bonView\(`; don't read a test kind from a workspace package's name; and list CI workflows
     whose names say e2e, so the agent knows where to look.
8. **Medium: a package named `integration` makes all its tests `integration`.** `INTEGRATION_PATH`
   (line 135) matches `(^|/)integration/`, so the 418 unit tests of `packages/integration` (code-host
   clients) count as integration tests, 3% of the suite. Fix: match the kind folders only below a test
   root, or never for a workspace package's own folder.
9. **Medium: the history views say little about a large monorepo.**
   - `churn` reads 5,000 commits, which here is 9 months of 6 years (2026-01-29 to 2026-10-31).
   - The hot files are dominated by generated API reports (`packages/ui/report.api.md` with 139 commits
     tops the list).
   - The largest changes on the main line are mostly mechanical: import sweeps, lint and knip passes, and
     11 of the top 30 are release merges (`changeset-release/master`). One is a dependabot merge:
     `milestones()` checks the bot pattern against the first 40 characters of the subject (line 425), and
     "Merge pull request #6756 from backstage/" ends just before "dependabot".
   - The decisions that mattered came from ADRs, proposals and two maintainer RFC issues, not from `hot`.
   - Fix:
     - leave files the scan guessed `generated` out of the hot files;
     - check the whole subject, or the merged branch name, for bots and release automation;
     - say in `analysis.md` that in a large repository the decision sources are documents and the tracker,
       and `hot` shows recent direction only.
10. **Low: the scan finds one docs site of two and doesn't name the navigation file.** `doc_sites` lists
    `mkdocs.yml` (the repository's own docs config) and the Docusaurus config, but not the Next.js MDX site
    in `docs-ui/` (49 `page.mdx` files guessed `product`), and not `microsite/sidebars.ts`, which step 3
    asks the agent to read. Fix: name the navigation file per site kind where one exists, and detect MDX
    page trees (`app/**/page.mdx`) as a site.
11. **Low: a symlinked agent file makes the real one a duplicate.** `.claude/CLAUDE.md` is a symlink to
    `AGENTS.md`; `scan_markdown()` reads both, sees `.claude/CLAUDE.md` first and guesses `AGENTS.md` a
    `duplicate`. Fix: skip tracked symlinks (`git ls-files -s` mode `120000`), or mark the link, not the
    target.

### Reading and the outline (steps 3 and 4)

12. **High: nothing in the skill says how to scope a monorepo of several products.** `analysis.md` names
    "a monorepo of several" as a kind and stops. With 261 packages, the agent has to choose what "the
    product" is. What worked here was a rule the skill already has for another case, "describe what the
    default release build does": for a framework, that is what its own scaffolder installs. The scaffolded
    app's backend, app and config named exactly the plugins to cover, and its config gave the defaults to
    check pages against. Fix: in `analysis.md`, under the product's kind, say how to scope a monorepo:
    - start from what a user gets by default: the default build, the starter or template the project
      scaffolds, or the packages its install docs name;
    - give the rest one page per family (integrations, providers), not one per package;
    - propose that scope at the checkpoint.
13. **Medium: the person accepts recommendations they can't judge.** Every answer was "(Recommended)". The
    checkpoint now gives each item with its evidence, which made that fast, but nothing in the outline
    showed where the agent was least sure. Here that was the records: whether a merged proposal counts as
    decided, and whether a proposal not yet implemented belongs. Fix: in step 4, mark the two or three items
    the agent is least sure of and ask about those first.
14. **Medium: proposals approved by merge don't fit the "decided" rule.** The proposals' process document
    says merging a proposal means the owning maintainers approved it, and four are `implemented`. Yet none
    names who approved it or when, so `analysis.md`'s rule (an accepted RFC "that names who decided and
    when") keeps them `open`. That is the right default, and the person agreed; but the skill doesn't say
    whether a merge by maintainers, which the host records, is a person's answer on record. Fix: say
    whether a proposal merged by a person with write access, with its merge date and pull request, counts
    as `answer: {who, when, where}`, or that it doesn't and stays `open`.

### Pages and records (steps 5 and 6)

15. **High: `check` caught none of the 14 false or imprecise claims; reading the code did.** Every one came
    from writing from the docs or from memory, and every one was a condition, a default or a list:
    - **conditions:**
      - a notification to a group reaches its members and its child groups, and to any other entity its
        owner (not "the people behind it");
      - template form fields are checked on **Next**, not as the person types;
      - a document engine needs a backend module that the scaffolded app doesn't have;
      - the language switch is hidden when the app has one language;
      - a static token runs as its subject, not as a person;
    - **defaults:**
      - an owner without a kind means a group;
      - entities are orphaned when nothing references them, not when their file is missing;
      - changing the landing page is two edits, not one;
    - **lists:**
      - one code host has no pull-request action;
      - templates aren't grouped by category, they are filtered by it;
      - the inspect dialog shows relations, status, raw data and origin, not processing errors;
      - unregister has two choices;
      - example table rows came from another dataset;
      - a claim about community plugins couldn't be verified.

    Fix: in step 7, tell the agent to list each condition, default and enumeration a page states and find
    each in the code before review. A page that says "every", "only", "by default" or "unless" deserves a
    look.
16. **Medium: product UI strings were the fastest ground truth.** Every UI label on the pages came from the
    plugins' translation files (`translation.ts`), and the scaffolded app's config gave every default. That
    made checking labels cheap, as AntennaPod's string resources would have. Fix: in `analysis.md`, name
    translation or string resources and the default config as the first places to read labels and
    defaults, whatever the stack.
17. **Low: a framework's pages pull toward developer reference.** The extending page first named
    extension blueprint symbols; I cut them, keeping what an author can do. The audience here is partly
    developers, so the line is harder to hold than for an end-user app. Fix: say in `analysis.md` that for
    an audience of developers, a page states what they can build and configure, and leaves symbol names to
    the reference it links.

### Checking, review and writing (steps 7 to 11)

18. **Medium: the wireframe can't be looked at with the skill's tools, and the format can't draw the real
    layout.** `viz.mjs` parses wireframes but draws only ablauf, so there is no SVG to rasterise
    (`visuals.md` asks to "look at each drawing"). I rendered it with `renderWireframe` and an ad hoc jsdom
    install, then `qlmanage`. The catalog page has a left column of filter selects; the format allows
    `select` only in roots, docks and rows, so the sketch shows the filters as a row. Fix: have `viz.mjs`
    write an HTML file per wireframe that a rasterizer can open; and say in `visuals.md` that a sketch may
    rearrange a layout the format can't express, and should say so in the prose.
19. **Medium: the review page drops the person's answers.** With `"status": "confirmed"`,
    `checkpoint_html()` (`intake.py` line 1946) shows who, when and where only. The answers, quoted as the
    brief asked, and the assumption that fates and tags were taken as proposed (`assumptions` alongside
    `confirmed`) don't appear, and `plan.md` has no field for them. Fix: add `answers` (question and
    answer) to `checkpoint`, accept `assumptions` with either status, and show both on the review page.
20. **Low: `check`'s errors were all mechanical, and two needed many edits.** 5 descriptions over 300
    characters, 3 Markdown files outside every glob (`.patches/README.md`, `scripts/**`, `workspaces/**`),
    1 history phrase ("since the last"), 2 tags used once. Fine as checks. The description limit is hit
    easily by a page that lists terms for search; saying so in `plan.md` next to the example would save a
    round.
21. **Low: no drawing status after writing, and `applied.json` can't tell why.** ub 0.4.13's
    `insert_block` answers carried no `drawing` key for the two ablauf blocks, and `get_doc` shows none.
    `brief()` keeps a drawing only when it isn't clean (line 686), so `applied.json` can't tell "clean" from
    "not checked". The drawings were checked by `viz.mjs` and looked at. Fix: record `drawings: n checked,
    all clean` or `not reported by the server` in `applied.json`.
22. **Low: `uberblick-corpus-sync` isn't installed, so step 10 can't run.** The pages were checked by hand
    at `24deeed960` and carry no recorded check.

### What worked

- **The checkpoint as recommendations.** The outline gave each item with its evidence; the person answered
  two questions and the run went on. No step had to be redone.
- **The ADR rule.** The four-criteria test and "engineering-only ones stay Markdown" sorted 15 ADRs in
  minutes: 4 records, 11 left out with one reason each.
- **"Describe the default release build"** gave the monorepo its scope (finding 12).
- **The tracker.** `gh search issues` with author association found the two maintainer RFCs behind
  records R6 and R7 in one call.
- **`check` and `viz.mjs`** caught every mechanical problem, and the second runs were clean.
- **The writes.** 70 calls applied in 0.6 s, with links resolved to UUIDs, records related to their pages,
  starter pages unpinned and their group deleted. `corpus` read it all back.
- **`repo_changes`** said what could shrink, and here the answer was "nothing", with a reason for each
  folder.

## Proposed changes, ranked

Each is written to hold for any repository. **F** is the finding above. IDs are this run's. **Also seen in** was filled in only after the
findings were written, from the AntennaPod, fzf and ablauf evidence.

| ID | Change | Where | F | Also seen in |
| --- | --- | --- | --- | --- |
| B1 | Check conditions, defaults and lists against the code: list each one a page states and find it in the code before review | `SKILL.md` step 7; `analysis.md` → Writing pages | 15 | AntennaPod 17 (S14); fzf 12. Three runs: the strongest recurring gap |
| B2 | Scope a monorepo from what a user gets by default (default build, starter, template, install docs); one page per family for the rest; propose it at the checkpoint | `analysis.md` → Product, audience and scope | 12 | ablauf §5 lists a monorepo as still to try; new here |
| B3 | Large repositories: a blobless clone is enough; pass `--no-renames` to every history walk | `SKILL.md` step 2; `intake.py` `churn`, `md_history` | 1, 2 |  |
| B4 | Resolve files named by agent instructions relative to the naming file; root only for paths with `/`; sources from instruction files, not skill bodies | `intake.py` `scan_markdown` | 4 |  |
| B5 | Recognise proposals by status frontmatter and keep the status value | `intake.py` `md_facts`, `guess_class`, `RFC` | 5 | ablauf §1 and fzf 6 (decisions sit in documents and the tracker, not history; related) |
| B6 | Say whether a proposal merged by maintainers counts as a person's answer | `analysis.md` → Confirm before recording | 14 |  |
| B7 | Fix test kinds: `\bonView\(`; no kind from a package's own name (`e2e-test`, `integration`); list e2e CI workflows | `intake.py` `test_kind`, `E2E_PATH`, `INTEGRATION_PATH`, `cmd_tests` | 7, 8 | AntennaPod 4 (S12); fzf 1 (CI commands as evidence of a suite) |
| B8 | Mark the least certain checkpoint items and ask about them first | `SKILL.md` step 4 | 13 | AntennaPod 9 (S2, recommend, don't quiz; this extends it) |
| B9 | Store and show the checkpoint's answers and assumptions | `plan.md` → checkpoint; `intake.py` `checkpoint_html`, `validate` | 19 | fzf 8 (approval timing; related) |
| B10 | Generated reports and translations: a recurring per-package file is `generated`; `README-<locale>` is a translation | `intake.py` `guess_class` | 6 | fzf 4 (an internals note guessed product; related) |
| B11 | History in large repositories: leave generated files out of hot files; check the whole subject for bots and release automation; say documents and the tracker hold the decisions | `intake.py` `churn`, `milestones`; `analysis.md` → Decision records | 9 | AntennaPod 12 (S7); fzf 5; ablauf §1 |
| B12 | Read labels from translation or string resources and defaults from the default config | `analysis.md` → Writing pages | 16 | AntennaPod 17 (S14, labels from string resources; related) |
| B13 | Draw wireframes to a file a rasterizer opens; allow a sketch to rearrange what the format can't express | `scripts/viz.mjs`; `references/visuals.md` | 18 |  |
| B14 | Name each docs site's navigation file; detect MDX page trees | `intake.py` `find_site` | 10 | AntennaPod 10 (S5); fzf 7 (docs sites and their navigation; related) |
| B15 | For an audience of developers, state what they can build; leave symbols to the reference | `analysis.md` → Writing pages | 17 | AntennaPod 13 and 14 (S3, S4) |
| B16 | Skip tracked symlinks in the scan | `intake.py` `scan_markdown` | 11 |  |
| B17 | Update the starter tags and the `complete` claim for local workspaces | `SKILL.md` step 1 | 3 | AntennaPod 3 (S17); fzf 14 |
| B18 | Record the drawing status, or its absence, in `applied.json` | `intake.py` `brief`, `cmd_ub` | 21 | AntennaPod 19 (S19); fzf 14 |
| B19 | Note the description limit next to the example | `plan.md` | 20 |  |

## Compared with earlier runs

Written after the findings above, from `uberblick-intake-antennapod.md`, `uberblick-intake-fzf.md` and
`uberblick-intake-ablauf.md`.

- **Recurs in all three product runs: claims about conditions, defaults and lists get past `check`.**
  AntennaPod 17 (labels and one false claim), fzf 12 (four, all conditions, supported lists or defaults),
  here 14 of the same kinds. B1 is the change with the most evidence behind it.
- **Recurs: test detection misjudges the suite.** AntennaPod counted service tests as journeys, fzf missed
  its whole end-to-end suite, and here a regex false match made a unit test the largest "journey" file
  while the real end-to-end runs sat in CI scripts. Reading CI workflows as evidence of a suite (fzf 1) would
  have found Backstage's too.
- **Recurs: the history is not where the decisions are.** ablauf (nothing in `hot`), AntennaPod (founding
  decisions on the website and wiki), fzf (declined issues), and here ADRs, proposals and two maintainer
  RFC issues. In a repository this size `hot` covers 9 months, so the gap is wider.
- **Still open from earlier runs, seen again:** the starter tags (AntennaPod 3, fzf 14), no drawing status
  on write (AntennaPod 19, fzf 14), `uberblick-corpus-sync` not installed (AntennaPod 20, fzf 14).
- **Contradicts fzf 13 in part:** help topics can be read through `ub` without the connected server. A calls
  file of `get_help` calls run with `intake.py ub` printed the `ablauf`, `wireframe` and `edit_doc` topics
  from the scratch workspace (`get_help` is in `READ_TOOLS`). It is a workaround, not a documented route,
  so a `help` subcommand would still help.
- **Confirms AntennaPod 7 and 9 and fzf 8:** the checkpoint as recommendations with evidence works for a
  person who doesn't know the product; here it took two questions. Unlike fzf, write approval was asked
  after the review page, as step 8 says.
- **New in this run:** the size of the repository (B3), scoping a monorepo (B2), the README resolved as an
  agent guide (B4), proposals with status frontmatter (B5, B6), generated reports guessed `product` (B10),
  wireframes that can't be looked at (B13), and the checkpoint's answers missing from the review page (B9).
