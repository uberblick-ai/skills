# Evidence: uberblick-intake on AntennaPod/AntennaPod

> Temporary. This folder collects evidence from trial runs of the skill for PR #46.
> Delete `evidence/` before merging. One file per run, named `<skill>-<repo>.md`.

## The run

| | |
| --- | --- |
| Repository | [AntennaPod/AntennaPod](https://github.com/AntennaPod/AntennaPod) at `047e35079` (2026-10-29) |
| Product | Android podcast app (Java), 37 Gradle modules, 9,535 commits since 2012 |
| Docs in the repository | 50 Markdown files: a short README, CONTRIBUTING, AGENTS.md, 45 module READMEs. The user docs live on antennapod.org, in another repository. The GitHub wiki is switched off and empty. |
| Skill | `uberblick-intake` 0.1 at `1168571`, run by Claude Opus 5.5 on 2026-11-01 |
| Corpus | A temporary local workspace (`ub workspace create`, ub 0.4.13), bound in a scratch folder. No shared workspace was touched. |
| Person | The skill author, standing in for the owner, but without knowing the product |

**Result.**

| Item | Result |
| --- | --- |
| Markdown files | 1 converted, 48 kept, 1 skipped |
| Documents | 15 pages and 5 decision records, all `open` |
| Tags | 6 new and 1 starter tag (`sync`) |
| Sidebar | 5 groups and 11 pins; the starter pages are unpinned |
| Drawings | 1 ablauf, no wireframes |
| `check` | 5 errors and 1 warning on the first run, 0 after fixes |
| Writes | 65 of 65 calls applied in under 1 s |

Reading the code for capabilities was the dominant cost. One delegated agent spent 96 minutes and 191k tokens, with 94 tool calls, inventorying 12 areas.

**The corpus.** It has 5 groups:
- **AntennaPod:** overview; home and navigation
- **Podcasts:** add podcasts; subscriptions → podcast settings, parental controls
- **Listening:** queue (with an ablauf drawing of how an episode ends); episode lists; player → sleep timer, controls outside the app
- **Automation:** downloads and refresh
- **Your data:** sync; backup and restore; statistics and Echo

The 5 records:
- Which builds ship
- Which navigation
- How devices sync
- Which states an episode goes through
- What AntennaPod promises its listeners

## Where a person had to step in

Each line is something the user had to say that the skill should have made unnecessary. The finding numbers refer to the next section.

1. "its ok to create a temp local workspace": there's no dry-run recipe (finding 2).
2. "assume that the person running the skill is the owner … asking for guidance is ok": the agent skipped the checkpoint (finding 8).
3. "I don't know the answers, I don't know the repo or the product - can you check their homepage": the checkpoint assumes product knowledge (findings 9 and 10).
4. "is there a github wiki?": wikis aren't scanned (finding 11).
5. "product intent is what we are looking for, right": the pages drifted toward settings reference (finding 13).
6. "the corpus should not be developer reference": the decision records named code symbols and an engine choice (finding 14).
7. "it can be, where it matters - but product intent and pages to allow an easy understanding of the product is the key": same as finding 14.
8. "the skill should also suggest to reduce markdown files if this isn't clear yet": finding 15.
9. "ensure the skill stays agnostic and nothing from the repo leaks into the skill": applies to every proposed fix below.

## Findings

Severity: **high** = wrong output, blocks the run, or makes a person step in; **medium** = slows the run or
misleads; **low** = polish. AntennaPod supplies the evidence; every fix is written so it holds for any repository.

### Finding the corpus (step 1)

1. **High: `intake.py corpus` crashes on an unbound checkout.** Without `.uberblick.json` it starts
   `ub mcp serve`, which exits, and the script dies with a 20-line traceback ending in
   `RuntimeError: ub mcp serve stopped before answering initialize`. Fix: check for a binding first,
   and say how to get one: bind the checkout, or `ub workspace create NAME` in a scratch folder
   passed as `--checkout`.
2. **Medium: no dry-run path.** The description offers "what would an intake of this repo create?",
   but the steps never say where a dry run stops or which corpus it checks tags against. What
   worked: `ub workspace create` in a separate scratch folder. The checkout stays clean, and the MCP
   server already connected (bound to another repository's workspace) is never touched. Fix: name
   this recipe, and say never to read or write a workspace bound to a different repository.
3. **Low: the starter tags are out of date.** SKILL.md lists six; ub 0.4.13 creates eight (it adds
   `guidance` and `technical-reference`). Fix: say "the starter tags `list_tags` shows" instead of
   listing them.

### Scan and tests (step 2)

4. **Medium: `tests` contradicts itself and miscounts journeys.** It prints "Browser or device test
   configuration: none found", then counts 106 on-device `e2e` cases. 37 of them never run: the
   largest file has a class-level `@Ignore`, and another a custom `@IgnoreOnCi`. Yet the header says
   "2 marked skipped". About 48 are service tests, not journeys, and 9 zero-case helper files are
   listed as journeys. Fixes, all generic:
   - count class-level and custom `@Ignore*` annotations;
   - drop zero-case files from the journey list;
   - recognise an instrumented-test source set and its runner as device test configuration;
   - count a file as a journey only when it drives the UI.
5. **Low: `hot` ranks areas that are gone at `ref`.** The two top areas are a module deleted two
   years earlier. Fix: mark an area "(gone at ref)".
6. **Low: `workspaces` misses nested modules.** It lists 5 of 37 Gradle modules (only top-level
   names). Tags draw on workspace names. Fix: read nested module paths.

### Reading (step 3)

7. **High (cost): a product whose intent lives only in code is expensive to read, and the skill has
   no recipe for it.** The README pitch was the only product prose in the repository. Fix:
   - ask at the checkpoint which areas matter before reading all of them (finding 9);
   - add a short "where capabilities live, by product kind" table to analysis.md: an app's
     settings definitions, menus, navigation and string resources; a web app's routes; a CLI's help;
   - consider letting `scan` dump the obvious UI facts, the way `tests` dumps test titles.

   The delegated inventory was accurate where spot-checked. Even so, my own drafts had 3 wrong
   labels before `check` (finding 17).
8. **High: a "dry run" was read as "unattended", so the checkpoint was skipped.** Step 4's only
   exception is "run unattended with leave to go on". I drafted 9 documents before asking anything.
   Fix:
   - say that a dry run still stops at the checkpoint when a person is in the session;
   - say that the person running the skill counts as the owner unless they say otherwise;
   - say that asking at the checkpoint is preferred to gathering everything alone.
9. **High: the checkpoint assumes the person knows the product.** Six open questions got "I don't
   know the repo or the product". Fix: state every outline item as a recommendation with its
   evidence, and ask "change anything?". "Don't know" keeps the recommendation and goes into
   `assumptions`.
10. **Medium: the project's homepage and published docs navigation aren't mentioned.** Two fetches
    gave the product's stated principles (absent from the repository) and the group names; the
    docs' sections matched the app's own settings words. Fix: in step 3, *when* the README, the
    host's `homepage` field or a package manifest links a homepage or published docs, read the
    homepage and the docs navigation; their words are good group and tag names. Many repositories
    have neither. Then fall back to what the repository says about itself: the README's opening, a
    manifest's `description`, store or package listing metadata kept in the repo, and the tracker's
    area labels. With none of these, ask at the checkpoint (finding 9). Outside sources show
    emphasis and words, never behaviour: the code still wins. Skip pages that need signing in, and
    for a private repository fetch nothing unless the person says so.
11. **Medium: GitHub wikis aren't scanned.** The repository reports `has_wiki: false`, yet
    `<repo>.wiki.git` clones with 309 commits. Its deleted pages held the episode state model, which
    became a decision record. Fix: `scan` tries the wiki remote, quietly skipping it when there is
    none (most repositories), and lists current and deleted pages.
    Deleted pages are evidence for decision candidates, never a source for pages.
12. **Medium: the history heuristics miss decisions made at the start.** Two of the five records
    (the episode state model and the listener promises) never had a "switch to" commit; the wiki and
    the homepage found them. A related point: a rewrite looked like an experiment until a build flag
    showed it was the only path. Fix:
    - say that early decisions come from the homepage, the wiki and the docs, not from `hot`;
    - for history candidates, check build flags that switch a new path on.

### What a page and a record are for (steps 5 and 6)

13. **Medium: pages drift toward settings reference in a settings-heavy product.** analysis.md keeps
    "config option lists" out of the corpus but doesn't say how to write a product whose behaviour
    *is* its settings. Fix, a rule of thumb: name a setting when it changes what a person
    experiences, and say what it does for them. Don't list every value; prefer a scenario.
14. **Medium: decision records slip into developer reference.** Drafts named code symbols and build
    flavor names, and one recorded which library plays audio. The criteria let "a framework or
    library the product is built on" through, which invites this. Fix:
    - write a record's answer in the product's words, for someone learning the product;
    - keep an engineering choice only where it changes what people get, and leave it out (as a
      candidate with its reason) when the repository already records it next to the code.
15. **Medium: the skill proposes reducing Markdown only for converted files.** analysis.md asks,
    per converted file, whether to delete or shorten it, and forbids touching `keep` files. It is
    silent on these cases:
    - Markdown that duplicates the published docs or the new pages;
    - stale or stub docs (here 45 module READMEs of 11–181 words, most under 50);
    - repositories whose intent was never in Markdown.

    Fix: make "fewer Markdown files" an explicit goal of `repo_changes`. Propose merging stubs,
    pointing duplicated prose to the corpus or the docs site, and say so even when the answer is
    "nothing to reduce". It stays a proposal, made only when asked.

### Checking, review and writing (steps 7 to 10)

16. **Medium: step 7 says the corpus help names the renderer versions; it doesn't.** `get_help`
    `ablauf` names the version only through the primer link, and nothing names the wireframe
    version. Fix: make the help name both packages, or drop the sentence.
17. **Medium: `check` can't catch wrong labels.** Three wrong UI labels and one false claim got
    past it and were caught by hand. Fix: a check that extracts each backticked label from a page
    and finds it in the product's strings (string resources, help text) would catch most of them.
18. **Good: `check` caught invented source paths.** 5 of about 70 source paths I wrote from memory
    didn't exist. `check` named each one.
19. **Low: no `drawing` status on write.** ub 0.4.13 returned none for the ablauf block, so only
    `viz.mjs` checked it. As the skill says: say the drawings were looked at, here after
    rasterising with `qlmanage`.
20. **Low: `uberblick-corpus-sync` isn't installed, so step 10 can't run.** The pages were checked
    by hand at `047e35079` and carry no recorded check.

### What worked

- `scan` took 5.6 s on 9.5k commits; `markdown_dirs` gives the bulk fates at once.
- The four decision criteria quickly dismissed all 17 closed "Needs: Decision" issues as single
  features.
- "Open the patch and confirm the current code still follows it" turned a rewrite that looked
  experimental into a fact.
- The write step: one command, 65 calls, under a second; the sidebar is printed as written.
- The review page and `check` ran cleanly once the plan was fixed.

## Suggestions

Filed here for now, not made: more runs will show which ones recur. Each has a stable ID, so another
run can add itself to **Also seen in** (or "contradicts") instead of filing it again. Ranked by this run;
**F** is the finding above. Every suggestion is written to hold for any repository.

| ID | Suggestion | Details | Where | F | Also seen in |
| --- | --- | --- | --- | --- | --- |
| S1 | Always stop at the checkpoint | A dry run still stops at step 4 whenever a person is in the session. The person running it counts as the owner unless they say otherwise. Asking beats gathering everything alone. | `SKILL.md` step 4 ("Run unattended…") | 8 | ablauf §2 (checkpoint run by hand; related) |
| S2 | Recommend, don't quiz | Give every outline item as a recommendation with its evidence, then ask "change anything?". "Don't know" keeps the recommendation and goes into `checkpoint.assumptions`. | `SKILL.md` step 4; `analysis.md` → Confirm before recording | 9 | |
| S3 | Pages state intent, not reference | Name a setting when it changes what a person experiences, and say what it does for them. Prefer a scenario to a list of values; give exhaustive lists only on request. | `analysis.md` → Writing pages | 13 | ablauf §4.2 (intent is the point; related) |
| S4 | Records in the product's words | No code symbols or build names. An engineering choice qualifies only where it changes what people get; leave it out, as a candidate with its reason, when the repo records it next to the code. | `analysis.md` → Decision records (the "framework or library" line) | 14 | |
| S5 | Read what the team publishes, when there is any | When the README, the host's `homepage` field or a manifest links a homepage or docs site, read the homepage and the docs navigation for emphasis, group names and tags. Otherwise use the README's opening, a manifest's `description`, listing metadata in the repo and area labels; with none of these, ask (S2). Never a source for behaviour. Skip pages behind a sign-in, and fetch nothing for a private repository unasked. | `SKILL.md` step 3; `analysis.md` → Product, audience and scope | 10 | ablauf §5 "Product intent from the host" (related) |
| S6 | Scan the wiki, when there is one | `scan` tries `git ls-remote <repo>.wiki.git` even when the host reports no wiki, skips quietly when it fails, and lists current and deleted pages. Deleted pages are evidence for decisions, never page sources. | `intake.py` `cmd_scan` (beside `labels_of`); `analysis.md` → Decision records | 11 | |
| S7 | Founding decisions aren't in the history | Say so: they come from the homepage, wiki, docs, specs and agent instructions, not `hot`. Before calling a rewrite experimental, check for build flags that switch the new path on. | `analysis.md` → Decision records, history candidates | 12 | ablauf §1 (`hot` found nothing; the decisions were in docs and the tracker) |
| S8 | Clear error on an unbound checkout | Look for `.uberblick.json` in the checkout or a parent before starting `ub mcp serve`. Without one, print one line naming both fixes, with no traceback. | `intake.py` `cmd_corpus`, `cmd_ub` | 1 | |
| S9 | A dry-run recipe | Name it: a separate scratch folder and `ub workspace create`, writing only there. Never read or write a workspace bound to another repository, even when its MCP server is connected. | `SKILL.md` step 1 | 2 | ablauf (a workspace created per run; related) |
| S10 | Fewer Markdown files as a goal | `repo_changes` also proposes merging stub docs and pointing duplicated prose at the corpus or docs site. It says "nothing to reduce" when that's the answer. Proposals only. | `analysis.md` → Repository changes; `SKILL.md` step 11 | 15 | |
| S11 | Count skips right | A class-level `@Ignore` counts as one skip, not every case in the class. Count them all, and match custom `@IgnoreOn*` annotations. | `intake.py` `SKIPPED` regex, `scan_tests` | 4 | |
| S12 | Detect journeys right | Drop zero-case helper files. A file is a journey only when it drives the UI; otherwise it's an integration test. An instrumented-test source set and its runner count as device test configuration. | `intake.py` `test_kind`, `journeys`, `cmd_tests` | 4 | ablauf §5 "Depth without journey tests" (related) |
| S13 | Cheaper reading of products whose intent lives in code | A "where capabilities live, by product kind" table: settings definitions, menus, navigation and strings for an app; routes for web; help text for a CLI. At the checkpoint, ask which areas matter before reading them all. | `analysis.md` → Capabilities, then pages | 7 | ablauf §5 "the product's kind" (related) |
| S14 | Catch wrong labels and claims | `check` warns about each backticked label not found in the product's strings (string resources, help output). Claims still need reading against the code. | `intake.py` `validate` | 17 | ablauf §4.3 (a claim the host contradicts) |
| S15 | Mark areas gone at `ref` | `hot` marks areas with no files at `ref`. | `intake.py` `churn`, `cmd_hot` | 5 | |
| S16 | Nested workspaces | Read nested module paths, such as Gradle `:a:b`. | `intake.py` `workspaces_of` | 6 | |
| S17 | Don't list the starter tags | Say "the starter tags `list_tags` shows". | `SKILL.md` step 1 | 3 | |
| S18 | Renderer versions named in help | `get_help` `ablauf`/`wireframe` names the npm versions; otherwise drop the sentence in step 7. | Uberblick product (help); `SKILL.md` step 7 | 16 | ablauf §1 (renderer version lacked a kind) |
| S19 | Drawing status on write | The server answers each ablauf write with a `drawing` status. | Uberblick product (`ub mcp serve`) | 19 | |

S18 and S19 belong in the Uberblick product repository, not this skill.
