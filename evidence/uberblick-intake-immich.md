# uberblick-intake trial: immich-app/immich

## 1. Header

Temporary. Delete `evidence/` before merging PR #46.

## 2. The run

- **Repository:** immich-app/immich at `b7510e79a` (main, 2026-10-31). A single-branch clone with 11,423 commits, 3,594 tracked files and 135 documentation files. The docs site is Docusaurus, in `docs/`. The monorepo holds server, web, mobile (Flutter), machine-learning, CLI, SDK and plugin packages.
- **Skill:** `uberblick-intake` at `b822e3c` (branch `claude/project-thread-4oqqwx`, PR #46).
- **Model:** claude-opus-5-5. No sub-agents.
- **Workspace:** a temporary local workspace, "immich intake trial" (`615a1d1c`, `hubUrl: null`), bound in a scratch directory. The clone stayed clean.
- **Stopped at:** finished through step 11. Step 10 had no `uberblick-corpus-sync`, so the pages were checked by hand at `b7510e79a` and carry no recorded check.

Result in numbers:

| Item | Count |
| --- | --- |
| Markdown files the scan found | 135 |
| Fates (as the review page counts files) | 25 converted, 77 kept, 33 skipped |
| Markdown entries in the plan | 60 (25 convert, 30 keep, 5 skip), 4 of them with `sections` |
| Pages | 18 |
| Decision records | 4, all `open` (8 proposed at the checkpoint, 4 dropped after the person's answer) |
| Tags | 10 used: 9 created, 1 reused (`auth`) |
| Pins | 7, in 5 groups; the starter pages were unpinned and the "Uberblick" group deleted |
| Drawings | 2 ablauf, 1 wireframe; `viz.mjs` gave 5 warnings on its first run and none on its second |
| `check`, first run | 0 errors, 18 warnings, all "no tldr" |
| `check`, last run | 0 errors, 18 warnings, kept on purpose because the guidance says "No TL;DR" |
| Calls applied | 68 of 68 in 0.6 s: 9 `create_tag`, 22 `create_doc`, 22 `insert_block`, 7 `pin_doc`, 2 `unpin_doc`, 6 `sidebar_group` |

Time and cost per step (wall clock, +07:00). Token figures are rough estimates of tool output read.

| Step | Wall time | Tool calls | Rough tokens |
| --- | --- | --- | --- |
| 0. Read the skill (SKILL.md and 3 references) | 2 min | 5 | 15k |
| Setup: workspace create and clone | 9 min (clone 9:14, network-bound) | 6 | small |
| 1. Corpus read | under 1 s | 1 | 2k |
| 2. scan, hot, tests | 3.2 s for the scan | 3 | 25k (scan.json 169 KB, read in parts) |
| 3. Read docs, code, e2e titles and tracker | about 8 min | about 30 | 60k |
| 4. Checkpoint outline | about 3 min | 3 | 10k to write |
| Wait for the person, then read the guidance and starter pages | n/a | 3 | 10k |
| 5 and 6. Decide and draft 22 documents | about 10 min | about 40 | 70k, mostly docs and the i18n string catalogue |
| 7. viz, check, spot checks against code | about 3 min | 10 | 10k |
| 8. Review page | under 1 min | 2 | 3k |
| 9. Write | under 1 min | 3 | 5k |

## 3. Where a person had to step in

1. At the checkpoint, on the docs overlap, the person said: "coarser pages is fine - the corpus describes product intent - not the product itself. See guidance doc on uberblick-2. This should be respected by the skill."
   - **Gap 1.** The skill never pointed me to the workspace's guidance. The catalog had a `guidance` tag whose own description reads "Workspace rules for writing and editing pages; agents are pointed to these at startup and read them before their first write". SKILL.md step 1 only says "Read the repository's own rules for corpus pages if it has any (AGENTS.md and the files it points to); otherwise follow the rules in references/analysis.md". In this fresh workspace no page carried the tag, and the rules ("Writing pages") lived in another workspace. Only the person could know that.
   - **Gap 2.** The starter "Welcome to Uberblick" page in my own workspace already said "Product intent in your team's own words: what a feature is for and what it must not do". The "How to Use It" page's instruction block said "Pages describe intended behaviour, which may be ahead of the code." The skill does not ask me to read either.
   - **Gap 3.** The skill's own writing rules (analysis.md, "Writing pages") contradict the guidance in eight places (finding 4). Had I followed the skill as written, I would have described the product rather than stated its intent.
2. Questions 2 to 4 at the checkpoint went unanswered: admin pages in or out, who decided the feature freeze and the no-paywall stance, beta features. The person running the trial does not know the product, so this is expected. It still shows that the checkpoint asks product questions that only a maintainer can answer. The skill's "Run unattended... record `assumed`" path does not cover a checkpoint where some answers come back and the rest are assumed (finding 9).

## 4. Findings

1. **The test scan missed every end-to-end test. Severity: high.**
   - Evidence:
     - `tests` printed "Journeys (0 files)" and "e2e: 0 (0%); 16175 code lines".
     - Immich names all 77 e2e files `*.e2e-spec.ts`. `TEST_FILE` accepts `.spec.ts` and `.e2e.ts` only after a dot, so `-spec.ts` never matches.
     - The Playwright config the scan found and listed (`e2e/playwright.config.ts`) states `testMatch: /.*\.e2e-spec\.ts/`, but the scan does not read it.
     - I counted by hand about 495 cases: 286 API (vitest), 37 Playwright against a real server, 95 Playwright with a mocked network, 38 maintenance and backup, and 39 CLI and `immich-admin`.
     - As a result, `check`'s journey warning (tests.focus) could not fire for any topic.
   - Fix:
     - Accept `[.-](spec|test)` before the extension (`.e2e-spec.ts`, `.int-spec.ts`).
     - Read `testMatch` and `testDir` from any Playwright, Vitest or Jest config the scan already finds.
     - When a browser-test config exists but no e2e case was counted, print a warning in `tests`, and have `check` print it too.

2. **Dart and Flutter tests are not counted. Severity: medium.**
   - Evidence:
     - Mobile (101k code lines) showed 0 tests. `_test.dart` is in neither `TEST_FILE` nor `CASE_PATTERNS`, yet `pubspec.yaml` is in `MANIFESTS`, so the scan knows Dart is a stack.
     - By hand: 131 `_test.dart` files and about 939 `test()`/`testWidgets()` cases, plus `mobile/integration_test/` (7 device tests).
     - The "Not counted: 305 files below test folders" line did flag it, and that warning worked.
   - Fix:
     - Add `_test\.dart$` and a Dart case pattern (`test(`, `testWidgets(`, `patrolTest(`).
     - Treat `integration_test/` as a device journey folder.
     - Keep `CODE_EXT`, `lang_of` and `MANIFESTS` in step, so that no listed stack is uncounted.

3. **The skill does not look for the workspace's own writing rules. Severity: high.**
   - Evidence: section 3, quote 1. The catalog's `guidance` tag existed with that description, and the starter pages state the corpus's purpose. Neither is read in step 1.
   - Fix:
     - In step 1, after reading the catalog, list the documents tagged `guidance` (and any tag whose description says agents read it before writing) and read them in full.
     - Read the starter pages too.
     - When the catalog has a `guidance` tag but no document carries it, ask the person at the checkpoint where the writing rules live.
     - State the precedence explicitly: workspace guidance first, then the repository's rules, then analysis.md.

4. **analysis.md "Writing pages" contradicts the workspace guidance. Severity: high.** In each case below, the skill says the first sentence and the guidance says the second.
   - **4a.** Skill: "Write the product as it is, in the present tense." Guidance: "Never fill unknown intent by describing what the code does today." The workspace's own "How to Use It" page adds "Pages describe intended behaviour, which may be ahead of the code."
   - **4b.** Skill: "When the docs and the code disagree, the code wins. Write what the code does and list the drift in the plan's `notes`". Guidance: "A code change rarely changes a page: check the code against the promises, and add one only when a person decided it."
   - **4c.** Skill: "Start small: a one-line usage or example first, a short section per command, screen or setting with a snippet, then scenarios as H3 headings". Guidance gives the feature shape: "Purpose: one sentence on why the feature exists. What it promises: ... One rule per bullet ... What you can do: one short section per capability, with an example. Scenarios (optional) ... Notes".
   - **4d.** Skill (Tests): "An area with many journeys gets the scenarios a person needs, one H3 per scenario". Guidance: "Never on a page: ... Standard behaviour and edge cases nobody would lose data, access or trust over."
   - **4e.** Skill (plan.md): "the `tldr` for people", and `check` warns "no tldr; a person opening the page reads it first". Guidance: "No TL;DR."
   - **4f.** Skill: "a short section per command, screen or setting with a snippet". Guidance: "Never on a page: Guides and configuration in prose: steps to follow, lists of options or variables, defaults and version minimums."
   - **4g.** Skill: "A history decision is recorded `open`: the answer states the choice the code shows and why". Guidance: "For each open decision, recommend the technically leaner option that still meets the intent".
   - **4h.** Skill: "Getting the product running stays Markdown ... What a person can configure and do once it runs is product intent and gets pages". Guidance: "That holds for every page, setup and operations included". Setup and operations can carry intent pages too, stated as rules.
   - Fix:
     - Rewrite "Writing pages" around intent: purpose, promises (one rule per bullet), capabilities with an example, scenarios only where intent stops, notes.
     - Drop "the code wins" and "write the product as it is". The code checks a promise; it never supplies one.
     - Make the tldr warning in `check` conditional on the workspace's rules.
     - Better still, make analysis.md a fallback that defers to workspace guidance, as finding 3 proposes.

5. **Under intent-first writing, end-to-end weight does not set page depth. Severity: medium.**
   - Evidence:
     - The heaviest browser journeys are standard navigation: timeline (45 cases: arrow keys, `d`/`m`/`y` jumps, shift-select, scrubber) and asset viewer (about 55 cases: next after delete, face-box selector not overlapping, OCR box focus).
     - Under the guidance none of this belongs on a page, and `timeline-and-viewer` came out at about 400 words.
     - The journeys that did yield promises were small: shared links (password, metadata hidden, guest actions), maintenance (restore point and rollback), partner map (archived hidden).
     - So the test suite told me where to look for promises and gave me evidence that they hold. How much each page says followed from how much the team had written down.
   - Fix: in analysis.md "Tests", say that journeys show which areas the team protects and give evidence for promises, but scenarios are written only where a journey tests a rule a person relies on (access, loss, undo, limits). Navigation and layout journeys are not scenarios.

6. **The decision sources that mattered here are ones the skill does not name. Severity: medium.**
   - Evidence: there are no ADRs. The records came from:
     - FAQ stance answers ("Does Immich change the file?", "Can I sponsor development of it?");
     - CONTRIBUTING's "Feature freezes";
     - a UI string, `purchase_panel_info_2`: "As we're committed not to add paywalls, this purchase will not grant you any additional features";
     - maintainers' `changelog:breaking-change` pull requests (about 90).
   - The scan's `decision_sections` caught 8 FAQ headings starting "Why ..." (all troubleshooting) and missed both real stance answers, which start "Does" and "Can".
   - analysis.md names labels "decision, rfc, adr, design". This tracker has none of those, but it has `changelog:breaking-change` and `changelog:deprecated`.
   - Fix:
     - Add FAQ answers to the decision sources: a question about what the product does or refuses, answered yes or no.
     - Add breaking-change and deprecation labels to the label list.
     - Name UI string catalogues (finding 19).
     - Drop "Why" from `DECISION_HEADING` unless the heading sits outside a FAQ or troubleshooting file.

7. **`hot` and milestones surface tooling, not product history. Severity: medium.**
   - Evidence:
     - With `--max-commits` 5000, `hot` reached only 2025-03-10 in a history going back to 2022.
     - The 40 "largest changes" were dominated by mechanical sweeps: tsconfigs (900 files), line length 120 (517), PascalCase renames (498), Dart SDK bump (640).
     - Feature landings never appeared: workflow foundation (89 files), passkeys (61), OCR, maintenance mode, cluster groups. I found them with `git log --diff-filter=A` on the service files.
     - Every direction change in `hot` was tooling (mise, zod, eslint) and failed the four criteria.
   - Fix:
     - Rank milestones with formatting and rename sweeps filtered out (a high share of renamed files, or near-equal added and deleted lines per file).
     - List `feat` merges separately, by files touched.
     - For each workspace, list when its top-level service or route folders first appeared: a cheap map of when capabilities landed.

8. **Several Markdown class guesses were wrong. Severity: medium.**
   - Evidence:
     - `readme_i18n/README_*.md` (21 translated READMEs) were guessed `product`. analysis.md says translated copies are `skip`, but the scan has no translation detection.
     - `docs/docs/features/supported-formats.md` was guessed `community`, because `COMMUNITY` matches the `SUPPORT` prefix of "supported" (no word boundary).
     - `e2e/AGENTS.md` was guessed `fixture`, because the fixture rule runs before the harness rule.
     - 14 of 15 `docs/docs/install/**` files were guessed `product` (the folder name `install` is ignored).
     - 9 `docs/docs/partials/_*.md` fragments were guessed `product`.
     - `mobile/README.md` was guessed `product` (it covers dev setup and directory structure).
   - Fix:
     - Detect locale suffixes (`_xx_YY`, `.xx.md`) and folders named `i18n`/`translations`.
     - Add `\b`/`[-_.]` boundaries to `COMMUNITY`.
     - Run `HARNESS` before the fixture rule.
     - Treat a folder named `install`, `installation`, `deploy` or `self-hosting` as technical.
     - Treat `_`-prefixed files in a docs site as fragments.

9. **The checkpoint schema cannot hold a partial answer. Severity: medium.**
   - Evidence: the person answered question 1 and left 2 to 4 open. With `"status": "confirmed"` the review page shows "Outline and decisions confirmed by ..." and hides the `assumptions` list I recorded (the review HTML has no "assum" text).
   - Fix:
     - Allow `answers` and `assumptions` together under either status.
     - Have the review page show both, with the assumptions first.

10. **SKILL.md's starter catalogue is stale. Severity: medium.**
    - Evidence: SKILL.md says a fresh workspace holds "six starter tags (auth, billing, mcp, permissions, rfc, sync)". This one had eight: `guidance` and `technical-reference` too, both with descriptions.
    - The `technical-reference` tag and the guidance's technical-reference page shape are not mentioned anywhere in the skill. That left open whether reference material (the CLI, the API) could become tagged pages rather than staying Markdown.
    - Fix:
      - Stop listing starter tags by name. Say "read the catalog; it may hold page-type tags such as `technical-reference` and `guidance` whose descriptions are rules".
      - Explain when a `technical-reference` page beats keeping Markdown.

11. **A local workspace read `complete: true`. Severity: low.**
    - Evidence: `corpus` on the local workspace returned `"complete": true` and hub `local`. SKILL.md (and the brief) prepare for `complete: false`.
    - Fix: shorten that paragraph to "a local workspace reports hub `local`; its catalog is whole".

12. **`check` does not catch what the guidance bans. Severity: medium.**
    - Evidence:
      - I wrote "By default, backup uploads only on Wi-Fi" and `check` passed it. The guidance bans defaults; I caught it by hand and rewrote it as a rule ("Backup uses mobile data only when the user allows it").
      - `check` also cannot see a promise written from code alone. I cut about 12 of those by hand ("deleting an album keeps its photos", "an API key never exceeds its creator", "search returns only what you may see"...).
      - `check` warned 18 times for the missing tldr the guidance forbids.
    - Fix:
      - Add a pattern for defaults and version minimums ("by default", "defaults to", "default:", "requires version").
      - Allow a page to list `promises` with their source, so `check` can flag a promise whose only source is code or tests.

13. **A surface page needs real command output that the run cannot produce. Severity: low.**
    - Evidence: the guidance asks for "the command and its real output, help included, shown as is". The brief forbids running the clone's build tools, and the skill offers no fallback. The `cli` page shows syntax only, in an `sh` fence.
    - Fix: say what to do when the command cannot be run: show the help as declared in the source, labelled as such, or leave the output out and list it as a question.

14. **Discussions are named as a source, but the skill gives no way to read them. Severity: medium.**
    - Evidence: immich takes feature requests in GitHub Discussions, which hold most "won't do" answers. Its issues are bugs (a sample of 30 "not planned" issues were all bugs). `gh` has no `discussion list`, and the skill gives no query, so I skipped Discussions.
    - Fix: give a `gh api graphql` query for answered or closed discussions in a category, filtered by `authorAssociation` MEMBER/OWNER, or say to skip them and record that.

15. **The docs-site navigation file can be a stub. Severity: low.**
    - Evidence: `docs/sidebars.js` is `type: 'autogenerated'`. The real order sits in six `_category_.json` files (Overview 1, Install 2, Features 3, Administration 4, Developer 5, Guides 6).
    - Fix: in step 3 and in `find_site`, read `_category_.json`/`_meta.json`/`SUMMARY.md` when the sidebar is generated, and print the top-level order in `scan`.

16. **What worked: the docs-site overlap. Positive.**
    - Evidence:
      - analysis.md's default ("the corpus states intent at a coarser grain beside the site (the usual answer)") was the right recommendation, and the person confirmed it.
      - Result: 18 pages against 105 docs-site files.
      - Install, developer, guides, settings reference and server commands all stayed Markdown, linked from pages.
      - No change to the site was proposed.
      - The skill did lead to fewer Markdown files being converted. 25 entries convert, and 4 files take `sections`, so only the concept part of `oauth.md`, the CLI doc and the README converts.
    - Fix: none needed. Keep the default, and add "converting a docs-site page never shortens or removes it" to the repo-changes rule, which already says so for the site's source.

17. **What worked: monorepo grouping. Positive, with a small gap.**
    - Evidence:
      - `workspaces_of` found 14 packages.
      - "One code base shipped as several apps ... is one corpus" and "groups are domains" together led to five domain groups (Photos, Search and discovery, Sharing, Phone and uploads, Server administration) rather than one group per app. Web and mobile differences went onto the pages.
    - Gaps:
      - `.github` was listed as a workspace, which is noise.
      - Nothing says whether a monorepo of several products (server, ML service, CLI) should ever be grouped per app.
    - Fix:
      - Exclude dot-folders from `workspaces_of`.
      - Add one line to analysis.md "Sidebar": "In a monorepo, group by what a person does, not by package; a package gets its own group only when it has its own audience".

18. **What worked: writing, drawing and reading through `ub`. Positive.**
    - Evidence:
      - `calls` and `ub` applied 68 calls in 0.6 s with no refusal, unpinned the starters, deleted their group, created the tags and printed the sidebar.
      - Links resolved to UUIDs, and the decision rows showed on the related page (checked with `export_markdown`).
      - `viz.mjs` caught a real layout fault (an edge running through the Trash node) that a clean parse would have hidden.
      - `check` validated every FAQ and README heading I named in `sections`.
      - `intake.py ub` also runs read-only calls (`export_markdown`, `get_help`) with `--print`. That is how I read the starter pages and the ablauf and wireframe help in my own workspace.
    - Fix: document `intake.py ub --print` with read-only calls as the way to read help and pages in a `ub`-bound workspace.

19. **The UI string catalogue was the richest intent source after the docs. Severity: medium.**
    - Evidence: `i18n/en.json` states rules in the team's words. Examples: "Your copies on the server remain safe" (free up space), "These photos and video will be removed from all albums, and only viewable from the locked folder", "This action is irreversible" (merging people), "If you forgot your PIN code, you can contact the server administrator", "Changing this value will result in existing passkeys no longer working", "The map feature relies on an external tile service".
    - Under "never fill unknown intent from code", these strings carried about a third of the promises. The skill only says to read UI labels "from the code".
    - Fix: in analysis.md, name the string catalogue (`i18n`, `locales`, `*.arb`, `strings.xml`, `Localizable.strings`) as a source of stated rules. Grep it for confirmations, warnings and descriptions (keys ending `_description`, `_prompt`, `_confirmation`, `_warning`).

20. **There is nowhere to put promises a maintainer must confirm. Severity: medium.**
    - Evidence: the guidance says "When old text is the only evidence, you may regroup its rules into promises, adding none, and list them for confirmation". With a person who does not know the product, every promise on 18 pages needs that confirmation, and about 12 inferred promises were cut and turned into questions. The plan has only a free-text `notes` list for them, and the review page does not tie a question to its page.
    - Fix: add a per-document `questions` list (and optionally `promises` with sources) to plan.md. Have the review page show each page's open questions beside it, and have `calls` write them as comments or as an open-questions block.

21. **Drafting from promises compared with drafting from descriptions. Observation.**
    - Evidence:
      - Each promise needed a sentence the team had written, so drafting meant hunting sources across docs, FAQ, UI strings and PR text, then cutting what only the code showed.
      - Wall time was about the same as describing would have been (about 10 minutes for 22 documents), but more reading per page.
      - Pages came out shorter: most are 200 to 400 words, against docs pages of 1,000 to 10,000 words.
      - Intent was unknowable from the repository for:
        - workflows and plugins: no docs, empty PR description; left without a page;
        - FUTO Backups: a beta 3 days old; left out;
        - cluster groups: UI strings only;
        - whether deleting an album keeps its photos;
        - who may create a cluster group;
        - whether an API key can exceed its creator.
    - Fix: covered by findings 4, 19 and 20.

22. **The plan example has the wrong `schema_version`. Severity: low.**
    - Evidence: plan.md's example has `"schema_version": 1`, while `intake.py` uses `SCHEMA_VERSION = 2` for scans. `check` ignores the plan's version.
    - Fix: align the example, or say the plan has its own version.

23. **The checkpoint asked for decisions on pull-request-only evidence. Severity: low.**
    - Evidence: following analysis.md, I proposed D2 (database), D4 (mobile sync) and D8 (plugin runtime) from maintainers' pull requests. Judged afterwards by "is this intent a person relies on", all three were engineering and were dropped. The four criteria let them through.
    - Fix: add a fifth test before the four criteria: "would a user or admin notice if the choice went the other way?". Database engines and sync mechanisms fail it, while "photos never leave your server" passes.

## 5. Suggestions

| ID | Suggestion | Details | Where (skill file and section or function) | Finding | Also seen in |
| --- | --- | --- | --- | --- | --- |
| I1 | Match hyphenated spec suffixes and read test-runner configs | Accept `[.-](spec\|test)` before the extension; read `testMatch`/`testDir` from Playwright, Vitest and Jest configs; warn when a browser config exists but 0 journeys counted | `intake.py` `TEST_FILE`, `scan_tests`, `cmd_tests`; `validate` (tests.focus) | 1 | fzf F1 (e2e suite invisible, per-language warning, test commands from CI); backstage B7 (related); antennapod S12 (related) |
| I2 | Count Dart/Flutter tests | Add `_test.dart`, a Dart case pattern, `integration_test/` as device journeys; keep CODE_EXT, lang_of and MANIFESTS in step | `intake.py` `TEST_FILE`, `CASE_PATTERNS`, `lang_of`, `CODE_EXT` | 2 | fzf F1 (same pattern: one language's suite uncounted) |
| I3 | Read the workspace's guidance and starter pages in step 1 | List documents tagged `guidance` and read them in full; read the starter pages; ask where rules live when the tag exists but no page carries it; state precedence | SKILL.md step 1; `intake.py` `cmd_corpus` (print guidance docs) | 3 | antennapod S20 (matches; its F21 quotes this run's checkpoint) |
| I4 | Rewrite "Writing pages" as intent-first, deferring to workspace guidance | Purpose, promises, capabilities with an example, scenarios only where intent stops; drop "code wins" and "write the product as it is"; code checks promises | references/analysis.md "Writing pages", "Tests"; references/plan.md document file | 4, 5 | antennapod S20, S3 (match); backstage B15 (related) |
| I5 | Tests locate and verify promises, they do not set depth | Navigation and layout journeys are not scenarios; scenarios only for access, loss, undo, limits | references/analysis.md "Tests" | 5 | antennapod S12 (related); contradicts in part ablauf §5 "Depth without journey tests" (depth from other signals) |
| I6 | Widen decision sources | FAQ yes/no stance answers; breaking-change and deprecated labels; UI string catalogue; drop "Why" headings inside FAQ files | references/analysis.md "Decision records"; `intake.py` `DECISION_HEADING`, `md_facts` | 6, 19 | fzf F6 (declined requests, `wontfix`); antennapod S7; backstage B11 (decisions in documents and tracker) |
| I7 | Product-relevance test before the four criteria | "Would a user or admin notice if it went the other way?" | references/analysis.md "Decision records" | 23 | antennapod S4 (matches) |
| I8 | Better milestones | Filter formatting and rename sweeps; list `feat` merges separately; list when top-level route or service folders first appeared | `intake.py` `milestones`, `cmd_hot` | 7 | backstage B11 (matches); fzf F5 (tooling noise in direction changes) |
| I9 | Fix class guesses | Locale-suffix translation detection; `COMMUNITY` word boundary; harness before fixture; install folders technical; `_`-prefixed docs-site files as fragments | `intake.py` `guess_class`, `COMMUNITY`, `scan_markdown` | 8 | backstage B10 (translations, generated reports); fzf F4 (related); ablauf §1 (guess errors, related) |
| I10 | Mixed checkpoint | Allow `answers` and `assumptions` together; show both on the review page | references/plan.md `checkpoint`; `intake.py` `checkpoint_html`, `validate` | 9 | backstage B9 (matches) |
| I11 | Do not hard-code the starter catalogue | Read the catalog's tag descriptions as rules; explain `technical-reference` | SKILL.md step 1; references/analysis.md "Tags" | 10 | antennapod S17; backstage B17; fzf F14 |
| I12 | Shorten the local-workspace paragraph | Local workspace reports hub `local` and a whole catalog | SKILL.md step 1 | 11 | backstage B17 (matches) |
| I13 | `check` for banned page content | Pattern for defaults and version minimums; tldr warning conditional on workspace rules; optional `promises` with sources | `intake.py` `HISTORY`, `validate` | 12 | backstage B1 and fzf F12 (related; they verify defaults, this run bans them); antennapod S14 (related) |
| I14 | Fallback when a command cannot be run | Show the help as declared in source, labelled, or list the output as a question | references/analysis.md "Writing pages" | 13 | none |
| I15 | A route to Discussions | `gh api graphql` query for answered discussions by MEMBER/OWNER, or skip and record | references/analysis.md "Decision records"; SKILL.md step 3 | 14 | fzf F6 (related: where declined work gathers) |
| I16 | Read generated docs-site navigation | `_category_.json`, `_meta.json`, `SUMMARY.md` when the sidebar is autogenerated; print top-level order | `intake.py` `find_site`; SKILL.md step 3 | 15 | backstage B14 (matches) |
| I17 | Monorepo grouping line, no dot-folder workspaces | Group by what a person does; package group only for its own audience; skip `.github` | references/analysis.md "Sidebar"; `intake.py` `workspaces_of` | 17 | backstage B2 (complementary: scope from the default build); ablauf §5 (monorepo scoped per package, related) |
| I18 | Document `ub --print` for reads | Read help topics and pages in a `ub`-bound workspace | SKILL.md step 1 and 7 | 18 | fzf F13 (`intake.py help TOPIC` through `ub`, matches) |
| I19 | Per-page questions | `questions` (and `promises` with sources) per document; review page shows them beside the page | references/plan.md `documents`; `intake.py` `cmd_review`, `cmd_calls` | 20, 21 | antennapod S20 ("ask instead"); backstage B8 (mark least certain items, related) |
| I20 | Align plan schema_version | Example matches the script or the plan's own version is stated | references/plan.md | 22 | none |

## 6. Overlap

Written after sections 1 to 5, from the antennapod, ablauf, fzf and backstage files. My findings are unchanged.

### My suggestions against the other files

1. I1 matches fzf F1: a second run where a whole end-to-end suite was invisible for a naming reason (minitest `test_*.rb` there, `*.e2e-spec.ts` here), and the "not counted" warning was too weak or absent. Related to backstage B7 and antennapod S12 (journey kinds miscounted).
2. I2 matches fzf F1 in pattern: a language the repository builds in has no test pattern.
3. I3 matches antennapod S20. That run already cites this run's checkpoint quote.
4. I4 matches antennapod S20 and S3, and relates to backstage B15 (developer symbols on pages).
5. I5 contradicts ablauf §5 "Depth without journey tests" in part. ablauf asks for other signals to set depth when journeys are missing. This run says that even with about 495 journeys, depth should follow what the team wrote, not test weight. Relates to antennapod S12.
6. I6 matches fzf F6 (declined requests as the richest source), antennapod S7 (founding decisions come from docs, not `hot`) and backstage B11.
7. I7 matches antennapod S4 (an engineering choice qualifies only where it changes what people get).
8. I8 matches backstage B11 (mechanical sweeps and bots in the largest changes) and fzf F5 (tooling in direction changes).
9. I9 matches backstage B10 (`README-<locale>` as translations). Relates to fzf F4 and ablauf §1.
10. I10 matches backstage B9 exactly: answers and assumptions with a confirmed checkpoint.
11. I11 matches antennapod S17, backstage B17 and fzf F14 (eight starter tags, not six).
12. I12 matches backstage B17 (`complete: true` on a local workspace).
13. I13 relates to backstage B1 and fzf F12, which check stated defaults against the code. This run, under the workspace guidance, bans defaults from pages. The two agree only if B1 becomes "check conditions and lists; rewrite defaults as rules".
14. I15 relates to fzf F6: both look for where maintainers' "no" answers gather.
15. I16 matches backstage B14 (name each site's navigation file).
16. I17 complements backstage B2: B2 scopes a monorepo by what a user gets by default, I17 groups by what a person does.
17. I18 matches fzf F13 (help topics through `ub`).
18. I19 relates to antennapod S20 ("ask instead") and backstage B8 (mark the least certain items).
19. I14 and I20 appear in no other file.

### Other files' suggestions this run gave evidence for or against

- **antennapod S1 (always stop at the checkpoint): for.** I stopped because the brief said so; SKILL.md step 4 still reads as if a trial could run on.
- **antennapod S2 (recommend, don't quiz): for.** The person answered one of four questions; the recommendations carried the other three as assumptions.
- **antennapod S4 (records in the product's words): for.** Three of my eight candidates (database, sync mechanism, plugin runtime) were engineering and were dropped once judged by what a person relies on.
- **antennapod S5 (read the homepage and published docs): neutral.** Here the published docs sit in the repository, so there was nothing outside to fetch.
- **antennapod S9 (dry-run recipe): for.** The scratch `ub workspace create` plus `--checkout` worked with no friction.
- **antennapod S10 (fewer Markdown files as a goal): neutral.** The docs site stays the published documentation, so `repo_changes` proposed only an AGENTS.md line and one drift fix.
- **antennapod S13 (where capabilities live by product kind): for.** Web routes, the mobile router, the sidebar component and the string catalogue gave the capability list in minutes.
- **antennapod S14 and backstage B12 (string resources): strongly for.** `i18n/en.json` carried about a third of the promises (finding 19).
- **antennapod S18 (renderer versions in help): against, in part.** With ub 0.4.13 the `wireframe` help names "@uberblick/wireframe 0.3.2"; the `ablauf` help names its version only through the primer link, as antennapod says.
- **antennapod S19 and backstage B18 (drawing status on write): for.** `applied.json` flagged no drawings, and I cannot tell "clean" from "not reported".
- **backstage B3 (blobless clone): for, untested.** A full single-branch clone of a 320 MB repository took 9 min 14 s. The scan needed only the history.
- **backstage B13 (wireframes cannot be looked at): for.** `viz.mjs` printed "1 wireframes checked" and wrote no SVG, so I did not look at the shared-links wireframe; I only looked at the two ablauf drawings. I missed saying so until I read B13.
- **fzf F9 (review page disagrees with `check`): no evidence.** Both said 0 errors and 18 warnings here, because none of the warnings needed `--checkout`.
- **fzf F10 and F11 (`answer.when`, tracker sources): not reached.** No record was decided.
- **fzf F2 (setext headings): not hit.** immich uses ATX headings.
- **ablauf §5 "Any code host": not tested.** GitHub only.
- **ablauf §5 "Pins on a changed plan": not hit.** The plan was written once.
