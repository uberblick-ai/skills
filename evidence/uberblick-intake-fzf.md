# Evidence: uberblick-intake on junegunn/fzf

> Temporary. This folder collects evidence from trial runs of the skill for PR #46.
> Delete `evidence/` before merging. One file per run, named `<skill>-<repo>.md`.

## The run

| | |
| --- | --- |
| Repository | [junegunn/fzf](https://github.com/junegunn/fzf) at `26ff936d` (2026-10-25) |
| Product | Command-line fuzzy finder (Go, about 27k code lines), 84k stars, 3,766 commits since 2013 |
| Docs in the repository | 9 Markdown files: a long README (4,370 words), ADVANCED.md (a cookbook), README-VIM.md, CHANGELOG, BUILD, RELEASE, SECURITY, a PR template and one internals note. The full reference is the man page (`man/man1/fzf.1`, 2,447 lines). The published guide is junegunn.github.io/fzf, in another repository. The GitHub wiki is on, with 16 pages and 801 commits. |
| Tests | 151 Go unit tests and **456 end-to-end tests** in Ruby minitest that drive the built `fzf` through tmux (`test/test_*.rb`, run by `make itest` and CI) |
| Skill | `uberblick-intake` 0.1 at `d5c3ad5`, run by Claude Opus 5.5 on 2026-11-01 |
| Corpus | A temporary local workspace (`ub workspace create fzf-intake-trial`, ub 0.4.13), bound in a scratch folder and passed as `--checkout`. No shared workspace was touched. |
| Person | The session's user, standing in for the owner |

Why fzf: it is the "Go CLI" from the wider-validation list, and it covers two of the "unlike the ones already tried" kinds: its tests are mostly end to end, and its product docs live largely outside the repository (the man page, an external site and the wiki).

**Result.**

| Item | Result |
| --- | --- |
| Markdown files | 2 converted, 5 kept, 2 skipped |
| Documents | 10 pages and 5 decision records: 1 `decided` (a maintainer's answer on the tracker), 4 `open` |
| Tags | 6 new; no starter tag fitted |
| Sidebar | 5 groups and 10 pins; the starter pages are unpinned |
| Drawings | 1 ablauf (one warning from `viz.mjs`, fixed), no wireframes |
| `check` | 5 errors and 11 warnings on the first run; 0 errors and 9 warnings kept knowingly (finding 2) |
| Writes | 20 of 53 calls applied, then a refusal (finding 10); after the fix, `--resume` applied the remaining 33 |
| Read back | `corpus` shows 17 documents (15 new, 2 starter pages), 5 groups, 14 tags |

Wall time from clone to read-back was about 12 minutes. Tokens weren't measured. Reading was done inline, with no delegated agent. It took about 25 tool calls, mostly the man page, the README and spot checks in `src/`. A CLI whose options are all in a man page is cheap to read compared with AntennaPod's app code.

**The corpus.** It has 5 groups:
- **fzf:** overview, with an ablauf of a run: input piped or walked, narrowing, how it ends
- **Finding:** search syntax and ranking; picking and output
- **Looks:** display and layout; preview window
- **Scripting:** key bindings and actions; remote control
- **Integrations:** shell integration; Vim and Neovim; using fzf in a program

The 5 records:
- A text filter, not a finder (decided: the maintainer on #3126, also #3015, #4105, #4321)
- What fzf lists when nothing is piped in
- One portable binary
- How fzf is extended
- How fzf ranks matches

## Where a person had to step in

At the checkpoint the person accepted every recommendation: "Keep as proposed", "All five as proposed" and "Yes, all of it". No answer corrected the skill.

One message during the run was about the trial, not the skill: "see evidence/uberblick-intake-antennapod.md for a structure on how to collect evidence - and re-read issue description - goal is to see if the skill works as intended and collect evidence and notes on how to improve". It shows that the PR's "How to record it" was not enough to go on from the start: the agent had not yet said how it would record the run.

The checkpoint held because the PR's "How to run one" says to stop there. SKILL.md at `d5c3ad5` still doesn't, which is AntennaPod finding 8.

## Findings

Severity: **high** = wrong output, blocks the run, or makes a person step in; **medium** = slows the run or
misleads; **low** = polish. fzf supplies the evidence; every fix is written so it holds for any repository.

### Scan and tests (step 2)

1. **High: the end-to-end suite was invisible.** `tests` reported "151 test declarations … unit 151", "Journeys (0 files)" and `test: 0 (0%); 8331 code lines`. The 456 tmux-driven cases in `test/test_*.rb` are the suite fzf protects its behaviour with: core 223, layout 83, shell integration 42, preview 41, exec 28, filter 27. No warning fired. `tests.summary` and `tests.focus` had to be written by hand from `grep -c 'def test_'`. Causes:
   - `TEST_FILE` matches Ruby only as `_spec.rb` or `test/*_test.rb`. Minitest's own default, `test/test_*.rb`, is missed, so the files count as code.
   - `CASE_PATTERNS["rb"]` knows only `it`/`scenario`/`specify`, not `def test_…`.
   - The "Not counted" warning needs uncounted files ≥ max(10, counted files). Here 12 uncounted against 31 counted, so a healthy unit suite in one language hides a missing suite in another.

   Fixes, all generic:
   - match `test_*.rb` and `def test_`;
   - warn per language, so a test folder whose files in one language are all uncounted is named whatever the other suites count;
   - read the CI workflow and the Makefile for test commands (`ruby test/runner.rb`, `make itest`) as evidence that a suite exists;
   - count a test that drives the built binary through a terminal (tmux `send-keys`, a pty, `expect`) as `cli`.
2. **Medium: setext headings aren't read.** README.md has 18 headings underlined with `---`/`===`; the scan saw none, and the same holds for CHANGELOG, README-VIM and BUILD. Titles became file stems, and `keep_sections` came back empty, so Installation, Building and Sponsors weren't proposed as `keep`. `check` uses its own ATX-only regex for section headings (`intake.py` around line 1297). When the plan named README's sections, it warned 9 times "README.md has no heading 'Installation'". A mixed README in this style can't get per-section fates without warnings. Fix: one heading parser for `scan` and `check` that reads setext headings.
3. **Low: a code fence that opens a list item flips the fence count.** In ADVANCED.md line 323, a fence opens on a list item (`- ` followed by three backticks). After it, shell comments inside code became headings. The title came out as "1. Search for text in files using Ripgrep", and the headings include "# junegunn/seoul256.vim (dark)". Fix: allow a list marker before an opening fence, or close a fence only on a line with the same indent and marker.
4. **Low: an internals note was guessed `product`.** `src/algo/SIMD.md` ("SIMD byte search", headings "Running tests", "Running micro-benchmarks") was guessed `product` with "describes what a user can do". Fix: a Markdown file below a source folder whose headings are about tests, benchmarks or file layout is `technical`.
5. **Medium: "direction changes" were mostly noise.**
   - Of 10 entries, these weren't product directions: a reverted labeler workflow, a Makefile `bash`→`sh` switch, a reverted sponsor action, the GitHub Actions migration and go.mod dependency swaps. Only the built-in walker (`208e556332`) and the Go rewrite were.
   - The sample commits under hot areas are mostly "Replace X with builtin min, max" refactors, matched by the word "replace".

   Fixes:
   - leave CI and tooling files (`.github/**`, Makefile, lint config) out of direction changes;
   - rank a direction change higher when the same commit changes the user docs (README, man page, docs site): the walker commit did, and the refactors didn't.
6. **Medium: the richest decision source was the tracker's declined requests, and the skill doesn't point there.** fzf has no decision label. The product's principle, that fzf is a filter like grep and not a finder, pager or table viewer, is in the maintainer's answers on issues closed `wontfix` (#3126, #3015, #4105, #4321). The history has no commit for it. analysis.md asks for "a decision label … or a maintainer's recorded answer", but doesn't say where those answers gather. Fix:
   - name the labels and states that hold declined work (`wontfix`, `declined`, `not planned`, `by design`, GitHub's "closed as not planned");
   - have `scan` count them when it reads labels;
   - read the maintainer's comments on the most-discussed ones.

   A principle repeated across several declined requests is a strong decision candidate.
7. **Medium: the wiki and the homepage weren't scanned (AntennaPod 10 and 11 again).** `doc_sites` is empty because the site lives in another repository. The site's navigation gave the group shape, and its "Using fzf in your program" page corrected a wrong assumption: that capability is about calling the binary from any language, not mainly the Go library. The wiki (801 commits) has setup recipes the shell page links to.

### Checkpoint and review (steps 4 and 8)

8. **Good, with one deviation.** One dialog of three recommendations, each with its evidence, was enough for a person who didn't need to know the product. The deviation: I asked for write approval in the same dialog as the outline, before the review page existed. Step 8 says to ask after the review. Bundling saved a round-trip, but the person approved pages they hadn't seen. Fix: say plainly that write approval comes after the review page, even when the outline was accepted unchanged.
9. **Low: the review page disagreed with `check`.** `review` printed "0 errors, 0 warnings" and the page says "The plan passes every check", while `check` gave 9 warnings. `review` validates without `--checkout`, so the section-heading check never runs. Fix: pass the checkout to `review` too, or say which checks it left out.

### Checking and writing (steps 7 and 9)

10. **High (blocked the writes): `answer.when` as a date passes `check` but the server refuses it.** plan.md says a decided record's `when` is "its date", and `check` accepted `2023-01-16`. `create_doc` refused call 21 of 53: "Use an ISO 8601 date-time with a time zone, e.g. 2026-10-24T10:55:00Z". Fix: `check` validates `answer.when` as an ISO date-time with a zone, and plan.md's text and example say so. `ub --resume` after regenerating `calls.json` continued exactly where it stopped, which is good.
11. **Medium: `check` refuses tracker sources.** A decided record's evidence was four issue URLs; `check` gave 5 errors: "source https://github.com/junegunn/fzf/issues/3126 does not exist in the checkout". analysis.md makes a maintainer's tracker answer the one route to `decided` besides an ADR, but `sources` takes only paths and `git:SHA`. Workaround: the issues went into `candidates.evidence` and `answer.where`. Fix: accept `issue:N` or the host's issue URL in a decision's `sources`, and link them on the review page.
12. **Medium: `check` missed four false claims, found by reading the code.** This is the same pattern as AntennaPod 17, and here none of them was a label:
    - `--listen` refuses command actions only from non-local addresses; I had written that it refuses them always without `--listen-unsafe`.
    - Image previews support Kitty and Sixel only, and the feature is experimental; I had added iTerm2.
    - The scroll-offset example `+{2}-/2` was invalid.
    - Vim's default layout prefers a tmux floating pane; I had written "a popup".

    Each one was a condition, a list of supported things or a default. Fix: step 7 names those three as the claims to check first against the code. `uberblick-corpus-sync`, where installed, should check the same.
13. **Low: the ablauf help has no `ub` route.** Step 7 says to read the renderer versions and the syntax from `get_help`. With `ub` as the only route there is no command for help topics; I read it through the connected MCP server, which is workspace-agnostic. Fix: `intake.py help TOPIC` through `ub mcp serve`.
14. **Low: still open from AntennaPod.**
    - Starter tags: SKILL.md lists six; the workspace has eight (AntennaPod 3).
    - Drawings: there was no `drawing` status on write with ub 0.4.13 (AntennaPod 19). `viz.mjs` caught an edge running through a decision; after the fix, the drawing was looked at, rasterised with `qlmanage`.
    - Grounding: `uberblick-corpus-sync` isn't installed, so step 10 didn't run. The pages were checked by hand at `26ff936d` and carry no recorded check (AntennaPod 20).

### Is it product intent?

Mostly yes. Someone new learns from the overview and the five group entry pages what fzf is, how a run goes and what to reach for. Two pages lean toward option reference, Display and layout and Preview window, because fzf's behaviour *is* its options. AntennaPod finding 13 (a rule of thumb for settings-heavy products) applies to CLI options as well. The records are in the product's words; none names a code symbol.

### Fewer Markdown files

The skill didn't prompt for it (AntennaPod 15 is still open at `d5c3ad5`). `repo_changes` says "nothing to reduce", written by hand: 9 files, none a duplicate. The README overlaps the site's Getting Started and Shell Integration pages, which is upstream's choice.

### What worked

- `scan` took 1.8 s on 3.7k commits. `corpus`, `calls` and `ub` worked first time; 53 calls ran in under a second, and `--resume` recovered cleanly.
- "Open the patch and check the code today" prevented a wrong record. `b7bb973118` reverted the GET state endpoints "to completely remove the risk of misuse", but the man page at `ref` documents GET again. The record now says the API exists.
- The `decided` rule held: the only decided record rests on the maintainer's own words, with who, when and where. The other four stay open.
- Of the five records, two came from the largest changes (the Go rewrite, the ranking rewrite), one from hot areas and direction changes (the walker), one from the tracker, and one from the tracker and history together.

## Proposed changes, ranked

All repository-agnostic.

1. Test detection (finding 1): minitest file and case patterns, a per-language "not counted" warning, test commands from CI and the Makefile as evidence, and terminal-driving tests as `cli`.
2. Plan contract (findings 10 and 11): validate `answer.when` as a date-time in `check`, and accept tracker references as decision sources.
3. Headings (findings 2 and 3): one parser for `scan` and `check`, with setext headings and fences inside list items.
4. Decision sources (findings 5 and 6): point to declined requests and the maintainer's answers on them; drop CI and tooling from direction changes, and rank changes that touched user docs higher.
5. Sources beyond the repository (finding 7, same as AntennaPod 10–12): the homepage, the docs site in another repository, the wiki.
6. Claims to check first (finding 12): conditions, supported lists and defaults.
7. Smaller items: findings 4, 8, 9, 13 and 14.
