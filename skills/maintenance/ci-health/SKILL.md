---
name: ci-health
description: >-
  Track CI health on a repository's main branch from GitHub Actions: the wall
  time a push waits for CI and its slow tail, the share of failed runs, the
  test count, optionally coverage and the test-to-code ratio, the changes that
  made CI slower or faster, and the top three actions that would cut the wait.
  Use for "how long does CI on main take?", "did CI get slower this week?",
  "what would make CI faster?" or "record yesterday's CI figures". Works for
  any repository and language. Writes only to a scratch directory and, when
  one exists, the repository's CI Health Report document. Not for fixing CI,
  hunting flaky tests or gating merges.
license: MIT
compatibility: >-
  Requires python3 and an authenticated GitHub CLI (gh); reads GitHub only.
  The test count reads job logs, so the host must reach GitHub's log storage.
  Coverage and line counts need a local checkout; line counts also need
  scc or cloc, and coverage a `mise run codecov` task. Storing the figures
  in an Uberblick document is optional and needs the uberblick MCP tools or
  the `ub` command; without either the skill prints a table.
metadata:
  author: uberblick-ai
  version: "1.9"
---

# CI health

CI should stay fast as a project grows. The wait that counts is wall time,
from the first job starting to the last one finishing, not the minutes the
jobs add up to. This skill records one repository's days since the last one
stored, or yesterday alone when nothing is stored yet, names the changes
that moved the wall time, and keeps up to three actions that would most cut
the wait, judged again on every run.

`scripts/ci.py` lives next to this file; call it by its path inside this
skill's directory. `REPO` is `OWNER/NAME`, `DIR` a scratch directory outside
the repository. What the script measures and how, the records, the `mise`
task conventions and the document layout are in
[references/data.md](references/data.md); the steps below are what you
decide.

1. Decide where the figures will be kept. Each repository keeps its own "CI
   Health Report" document in the Uberblick workspace its checkout is bound
   to; never put two repositories in one document. Uberblick is reached one of
   two ways:

   - the `uberblick` MCP tools (`search`, `get_doc`, `get_data`,
     `update_data`, `create_doc`, `insert_block`, `delete_block`,
     `list_tags`) are in your tool list: call them directly;
   - otherwise the `ub` command is on the PATH: call a tool with `python3
     scripts/ci.py ub TOOL 'ARGS' --checkout PATH`, where `ARGS` is the
     tool's arguments as inline JSON or a JSON file and `PATH` the
     repository's checkout. Each invocation starts one server, which shows
     as one agent in the workspace, so put several calls in one file,
     `[{"tool": ..., "arguments": {...}}]`, and pass it with `--calls`.
     After a write it waits for the hub to acknowledge before exiting. When
     it fails because the checkout is not bound, say so and go on without
     Uberblick.

   With neither, steps 9 and 10 are skipped: the table, the incidents and
   the actions are the result; say so in one line. With one, `search` for
   "CI health" in the workspace; when the document found is about this
   repository, call it `DOC` and read with `get_data` its `incidents`, its
   `actions`, its `applied` marks and its `days`, saving the `days` as
   `DIR/days.json`. When no such document exists,
   ask the maintainer once whether to create it, and carry on meanwhile.

2. Collect:

   ```sh
   python3 scripts/ci.py collect --repo REPO --after DIR/days.json --cache DIR/cache [--workflow W] [--start DAY] > DIR/data.json
   ```

   Days are UTC days. With `DOC`, `--after` collects every day after the
   newest stored one up to yesterday, so three days missing means three days
   collected; with nothing missing it collects yesterday again. GitHub keeps
   job logs 90 days, so a gap reaches no further back than that. Without
   `DOC`, or for a document created in step 9, leave `--after` out: the
   default is yesterday alone. `--day` picks one day instead when the
   maintainer names it, and `--since` (with `--until`) a longer history only
   when they ask for one. A long span takes minutes. When the command fails,
   run it again: the cache resumes the reads that succeeded. Use the same
   cache for this report's `collect`, `logs` and `tests`, and a fresh scratch
   directory for a new report.

   Pass `--workflow` when the repository also runs a workflow on only some
   pushes (path filters, a release proof), naming the workflow every push
   runs, so a commit that skipped CI does not read as a fast one. Pass
   `--start` only when the runs before a day cannot be compared at all: CI
   re-enabled after a gap, or moved to another system. A rework of the
   workflow is not a reason; it is an incident, and the step should show.
   Once a document holds days, reuse their `workflows` and `start` fields on
   every run, or the history shifts. A document whose days lack
   `failure_pct` gets it by collecting those days again with `--since`.

3. Count the tests. Test runners differ by language and setup, so you read
   the summary off the logs rather than the script guessing:

   ```sh
   python3 scripts/ci.py logs DIR/data.json --out DIR/logs --cache DIR/cache
   ```

   It saves the cleaned log of each job of the last day's last green commit.
   Find the lines where the repository's test runners say how many tests
   ran; the checkout's languages and test setup tell you which runners to
   look for. Write one regular expression per runner whose groups capture
   the counts to add up: tests run or passed, not skipped ones. When a
   runner's total includes skipped tests, add a pattern for its skipped
   count with a group named `skipped`, which is subtracted, for example
   `^OK \(skipped=(?P<skipped>\d+)\)`. Then count every collected day:

   ```sh
   python3 scripts/ci.py tests DIR/data.json --cache DIR/cache --pattern 'REGEX' [--pattern 'REGEX']
   ```

   Check the day's `tests` against the logs before going on. A stored day's
   `tests_pattern` holds the patterns joined by ` || `; reuse them while they
   still match. When no job prints a count, leave `tests` out and say so.

4. Measure the code, given a local clone of `REPO`; a scratch clone works
   and keeps the maintainer's checkout untouched. First choose what to
   count: the main source directories, where the product's code and its
   tests live. The build usually declares them (workspace members in
   `pnpm-workspace.yaml`, `package.json`, `Cargo.toml`, `go.work` or
   `settings.gradle`, the projects of a `.sln`); otherwise `src/` and
   `tests/`. Leave out documentation, websites, examples, scripts and
   tooling, fixtures, generated and vendored code. Give each as a git
   pathspec with `--path`, `:!DIR` to leave one out inside another. A
   stored day's `loc_paths` holds them joined by ` || `; reuse them while
   the layout holds, since a change of paths moves the ratio.

   ```sh
   python3 scripts/ci.py measure DIR/data.json --checkout PATH --path SPEC [--path SPEC]... [--every-day]
   ```

   It adds `test_ratio` to the last day, or to every day with
   `--every-day`, which more than one collected day wants, plus
   `coverage_pct` when the checkout defines `mise run codecov`. If installed
   counters fail their probes, or the selected counter fails its count,
   `measure` reports the error and leaves the data file unchanged; fix it
   and retry. When it finds no line counter, say so in one line with the
   install command it suggests for this host, and go on without the ratio.
   Without a coverage task, mention once that adding one charts coverage
   too; the conventions are in `references/data.md`. Skip this step without
   a clone.

5. Find the steps:

   ```sh
   python3 scripts/ci.py summary DIR/data.json
   python3 scripts/ci.py shifts DIR/data.json > DIR/shifts.json
   ```

   `shifts` lists candidate steps in wall time and hangs (CI failing only
   after an hour or more, such as tests hanging until the job timeout), each
   with the commits that can explain it; `references/data.md` defines both.
   Drop a candidate already in `incidents` within three days, and a step
   that no change explains, such as one that reverses within a day or moves
   every job alike (runner speed). A step right after a hang is usually the
   change that ended it: name it once, as the hang's `faster` incident, with
   the new green time in `why`. A step needs eight green commits on each
   side, so a change in the last day or two shows only in the summary; when
   it shows jobs added or dropped, or the day's wall time moving by a minute
   and 15 percent, find that change too.

6. Name the cause of each remaining step. Look at the suspects' PRs and
   commits: workflow files, test setup, the jobs that moved. Write
   `DIR/incidents.json`, a list in the shape `references/data.md` gives: the
   day, the repository, `slower` or `faster` (a hang is `slower` when it
   starts and `faster` when the change that ended it lands), the medians
   before and after, a title naming the change, `ref` as `owner/name#number`
   or a commit, `time` from the candidate (it keeps several incidents on one
   day in order), and `why` in one sentence (what moved and why). A step
   whose cause you cannot confirm from the changes is left out, not
   guessed.

7. Choose the top three actions: the changes that would most cut the time
   pushes wait for a green main, judged on the last days, not the collected
   day alone:

   ```sh
   python3 scripts/ci.py signals DIR/data.json > DIR/signals.json
   ```

   It covers the 7 days ending the last day, with a rough count of the
   minutes of waiting a day each problem accounts for
   (`waiting_min_per_day`). Add what the workflow files, the incidents and,
   with `DOC`, its recent `days` show: a job that sets the wall time (split,
   shard or cache it, or move work off the critical path), jobs that fail or
   hang on changes they should not care about, runner waits, a suite that
   runs twice. Each action is one change a person can make in the
   repository, with its evidence in numbers and dates and the minutes a day
   it could save; rank by those minutes.

   Those minutes are an estimate: write them as "could save about", never
   as a measured result. Measurement comes after the change: once an action's
   pull request has merged, the step it caused shows in `shifts` and step 6
   records it as an incident naming that pull request, so the reply can set
   the estimate beside what the days measured.

   With `DOC`, start from its stored `actions`. Keep one while its evidence
   holds, with its `id` and `since` and today's numbers in `why`; drop one
   that a merged change addressed or the data no longer shows; replace one
   only when a candidate saves clearly more. An action with an `applied`
   mark is being handled: someone discussed it and opened the pull request
   or issue the mark names. Keep it, struck through, in its place while that
   pull request or issue is open, and drop it once it is merged or closed.
   Without `DOC`, nothing keeps actions between runs, so choose them afresh.
   Fewer than three is fine, and no action goes without data behind it.
   Write `DIR/actions.json` in rank order, in the shape `references/data.md`
   gives: `why` holds the evidence and the expected saving in two or three
   sentences, `check` what to read in the repository before changing
   anything, and a kept action its `id` and `since`.

8. Without `DOC`, reply as step 11 shows, with the summary table above it;
   stop here.

9. Store the day, unless the maintainer asked for the table only. For a new
   document the maintainer said yes to, pick from `list_tags` the active ids
   that fit CI, testing or engineering health, then:

   ```sh
   python3 scripts/ci.py create DIR/data.json --incidents DIR/incidents.json --actions DIR/actions.json [--tag ID]... > DIR/create.json
   ```

   Pass it as the arguments of `create_doc`; the result's uuid is `DOC`. If
   no tag fits, say so in the reply rather than leaving it silently
   untagged. Then, for a new document or an existing one:

   ```sh
   python3 scripts/ci.py records DIR/data.json [DIR/incidents.json] --actions DIR/actions.json [--applied DIR/applied.json] --doc DOC > DIR/update.json
   ```

   `DIR/applied.json` is the `applied` collection as `get_data` returned
   it; the marks of dropped actions are deleted with them.

   Pass it as the arguments of `update_data`, then read the area summary
   back with `get_data` and confirm `days`, `incidents` and `actions` are
   valid. Storing a day again replaces it; the actions replace the stored
   set.

10. With a `DOC` that existed before this run, compare its chart blocks with
    `ci.py charts DIR/data.json`: replace a chart whose JSON differs and
    insert one that is new (the ratio or coverage measured for the first time)
    after the last chart. When there are new incidents, read `incidents` again
    with `get_data`, write it to `DIR/all-incidents.json`, run `ci.py
    changelog DIR/all-incidents.json`, and replace the list items under the
    "Incidents" heading, below the charts, with its blocks. On every run,
    since their numbers move, run `ci.py cards DIR/data.json DIR/actions.json
    --doc DOC [--applied DIR/applied.json]` and replace the cards under the
    "Recommended Actions" heading, or its "No action proposed yet."
    paragraph, with its blocks; a document without that heading gets it
    after the last chart, with the paragraph `create` writes below it. If
    Uberblick refuses a card with `invalid_card` (0.4.3 has no card buttons),
    run `cards` or `create` again with `--no-button`. Leave every other block
    as it is, since people may have edited it. The document has no TL;DR:
    the charts, actions and incidents are the summary, so do not add one
    when a tool suggests it. Through `ub`, gather these writes into one
    `--calls` file; several blocks inserted after the same block, in reverse
    order, end up in order, so the file needs only ids read before.

11. Reply in this shape, with your own numbers (these are an example). Leave
    out a line that has nothing in it, and number the actions so the
    maintainer can say "discuss 2":

    ```text
    CI on main, 7 days to 28 October: 9.7 min median (± 1.2), P95 14.1 min. 6% of runs failed. 2,431 tests, test ratio 0.82, coverage 71%.
    New incident: 27 October, 2.5 min slower, job e2e, after acme/app#412 added browser tests.
    Actions: 1. Shard the e2e job, could save about 60 min of waiting a day (new). 2. Cache the pnpm store (kept). Dropped: retry the flaky sync test, fixed by acme/app#405.
    Measured: acme/app#398 (cache Playwright browsers) estimated 20 min a day; the days since show 1.1 min less per push, about 25 min a day.
    Stored 26 to 28 October in the CI Health Report.
    ```

    Without `DOC`, the last line says the figures were not stored and why.
    When the skill runs on a schedule with nothing new, one line is enough:
    `CI on main: 9.7 min median, P95 14.1 min, no new incident or action.`
