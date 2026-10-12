---
name: ci-health
description: >-
  Track CI health on a repository's main branch from GitHub Actions: the
  median wall time a push waits for CI and its slow tail, the number of
  tests, optionally coverage and the test-to-code ratio, and the changes that
  made CI slower or faster. Use when a maintainer asks how long CI takes,
  whether it got slower, or to record CI figures daily. Works for any
  repository and language. Not a CI fix, a flaky-test hunt or a merge gate.
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
  version: "1.1"
---

# CI health

CI should stay fast as a project grows: the wait that counts is wall time,
from the first job starting to the last one finishing, not the minutes the
jobs add up to. The charts show that total only; each job's time stays in
the data to show which job moved when the total steps. This skill records
one day for one repository and keeps the steps that moved the total, with
their cause.

`scripts/ci.py` lives next to this file; call it by its path inside this
skill's directory. `REPO` is `OWNER/NAME`, `DIR` a scratch directory outside
the repository. Definitions, the records, the `mise` task conventions and
the document layout are in [references/data.md](references/data.md).

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

   With neither, steps 8 and 9 are skipped: the table and the incidents are
   the result; say so in one line. With one, `search` for "CI health" in
   the workspace; when the document found is about this repository, call it
   `DOC` and read with `get_data` its `incidents` and its latest `days`
   record. When no such document exists, ask the maintainer once whether to
   create it, and carry on meanwhile.

2. Collect:

   ```sh
   python3 scripts/ci.py collect --repo REPO [--workflow W] [--start DAY] > DIR/data.json
   ```

   The default is yesterday, a UTC day; `--day` picks another. The first time
   a repository is tracked, backfill with `--since` up to 90 days back, the
   time GitHub keeps job logs; it reads every run's jobs, so expect minutes.
   Pass `--workflow` when the repository also runs a workflow on only some
   pushes (path filters, a release proof), naming the workflow every push
   runs, so a commit that skipped CI does not read as a fast one. Pass
   `--start` only when the runs before a day cannot be compared at all: CI
   re-enabled after a gap, or moved to another system. A rework of the
   workflow is not a reason; it is an incident, and the step should show.
   Once a document holds days, reuse their `workflows` and `start` fields on
   every run, or the history shifts.

3. Count the tests. Test runners differ by language and setup, so you read
   the summary off the logs rather than the script guessing:

   ```sh
   python3 scripts/ci.py logs DIR/data.json --out DIR/logs
   ```

   It saves the cleaned log of each job of the last day's last green commit.
   Find the lines where the repository's test runners say how many tests
   ran; the checkout's languages and test setup tell you which runners to
   look for. Write one regular expression per runner whose groups capture
   the counts to add up: tests run or passed, not skipped ones. When a
   runner's total includes skipped tests, add a pattern for its skipped
   count with a group named `skipped`, which is subtracted, for example
   `^OK \(skipped=(?P<skipped>\d+)\)`. Then:

   ```sh
   python3 scripts/ci.py tests DIR/data.json --pattern 'REGEX' [--pattern 'REGEX']
   ```

   Every integer the groups capture, on every matching line, is summed per
   job; jobs that differ only in a parenthesised matrix value count once.
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

   It fetches the last green commit if the clone lacks it, checks it out in
   a temporary worktree, which it removes afterwards, and adds
   `test_ratio` (with `code_lines` and `test_lines`) to the last day, or to
   every day with `--every-day`, which a backfill wants, plus
   `coverage_pct` when the checkout defines `mise run codecov`. Lines are
   counted by `scc`, or `cloc` without it, over the files git tracks, so
   blank and comment lines, prose and data never count; `loc_tool` records
   which. A `mise run loc` task replaces that count. When `measure` finds
   no line counter, say so in one line with the install command it
   suggests for this host, and go on without the ratio. Without a coverage task,
   mention once that adding one charts coverage too; the conventions are in
   `references/data.md`. Skip this step without a clone.

5. Find the steps:

   ```sh
   python3 scripts/ci.py summary DIR/data.json
   python3 scripts/ci.py shifts DIR/data.json > DIR/shifts.json
   ```

   Each step is a point where the median wall time of the green commits
   before it and after it differs by at least a minute and 15 percent, with
   the jobs' medians on both sides and the commits that can explain it,
   failed ones included. Each `hang` is a stretch of commits whose CI failed
   only after an hour or more, such as tests hanging until the job timeout,
   with the commit that started it and the first one after it. Only
   candidates on the collected days are listed; the weeks before them only
   feed the medians. Drop a candidate already in `incidents` within three
   days, and a step that no change explains, such as one that reverses
   within a day or moves every job alike (runner speed). A step right after
   a hang is usually the change that ended it: name it once, as the hang's
   `faster` incident, with the new green time in `why`. A step needs eight
   green commits on each side, so a change in the last day or two shows only
   in the summary; when it shows jobs added or dropped, or the day's wall
   time moving by a minute and 15 percent, find that change too.

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

7. Without `DOC`, reply with the summary table and any incidents; stop here.

8. Store the day, unless the maintainer asked for the table only. For a new
   document the maintainer said yes to, pick from `list_tags` the active ids
   that fit CI, testing or engineering health, then:

   ```sh
   python3 scripts/ci.py create DIR/data.json --incidents DIR/incidents.json [--tag ID]... > DIR/create.json
   ```

   Pass it as the arguments of `create_doc`; the result's uuid is `DOC`. If
   no tag fits, say so in the reply rather than leaving it silently
   untagged. Then, for a new document or an existing one:

   ```sh
   python3 scripts/ci.py records DIR/data.json [DIR/incidents.json] --doc DOC > DIR/update.json
   ```

   Pass it as the arguments of `update_data`, then read the area summary
   back with `get_data` and confirm `days` and `incidents` are valid.
   Storing a day again replaces it.

9. With a `DOC` that existed before this run, compare its chart blocks with
   `ci.py charts DIR/data.json`: replace a chart whose JSON differs and
   insert one that is new (the ratio or coverage measured for the first
   time) after the last chart. When there are new incidents, read
   `incidents` again with `get_data`, write it to `DIR/all-incidents.json`,
   run `ci.py changelog DIR/all-incidents.json`, and replace the list items
   under the "Incidents" heading, below the charts, with its blocks. Leave
   every other block as it is, since people may have edited it. The
   document has no TL;DR: the charts and incidents are the summary, so do
   not add one when a tool suggests it. Through `ub`, gather
   these writes into one `--calls` file; several blocks inserted after the
   same block, in reverse order, end up in order, so the file needs only
   ids read before.

10. Reply with the total wall time (the 7-day median with its ± and the
    P95), the tests, the test ratio and any coverage, any new incident with
    the job that moved, and where the day was stored. When the skill runs on
    a schedule with nothing new, a single line is enough.
