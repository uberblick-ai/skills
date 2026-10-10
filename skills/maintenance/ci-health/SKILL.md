---
name: ci-health
description: >-
  Track CI health on a repository's main branch from GitHub Actions: the
  median wall time a push waits for CI, split per parallel job with the total
  as the headline, the number of tests, and the changes that made CI slower or
  faster. Use when a maintainer asks how long CI takes, whether it got slower,
  or to record CI figures daily in an Uberblick document. Not a CI fix, a
  flaky-test hunt or a merge gate.
license: MIT
compatibility: >-
  Requires python3 and an authenticated GitHub CLI (gh); reads GitHub only.
  The test count reads job logs, so the host must reach GitHub's log storage.
  Storing the figures in an Uberblick document is optional and needs the
  uberblick MCP server; without it the skill prints a table.
metadata:
  author: uberblick-ai
  version: "1.0"
---

# CI health

CI should stay fast as a project grows: the wait that counts is wall time,
from the first job starting to the last one finishing, not the minutes the
jobs add up to. Splitting checks into parallel jobs is one way to cut it, so
each job is tracked on its own beside the total. This skill records one day
per repository and keeps the steps that moved the total, with their cause.

`scripts/ci.py` lives next to this file; call it by its path inside this
skill's directory. `REPO` is `OWNER/NAME`, `NAME` its name, `DIR` a scratch
directory outside the repository. Definitions, the records and the document
layout are in [references/data.md](references/data.md).

1. Decide where the figures will be kept. Uberblick is available when the
   `uberblick` MCP tools (`search`, `get_doc`, `get_data`, `update_data`,
   `create_doc`, `insert_block`, `delete_block`, `list_tags`) are in your
   tool list.
   Without them, steps 6 and 7 are skipped: the table from step 2 and the
   incidents from step 4 are the result; say so in one line and add that
   `ub mcp install` registers the server for next time when `ub` is on the
   PATH. With them, search for the "CI health" document, call it `DOC`, and
   read with `get_data` the `incidents` collection and the latest record of
   each repository's collection, named `NAME`. When no such document exists,
   ask the maintainer once whether to create it, and carry on meanwhile.

2. Collect each repository:

   ```sh
   python3 scripts/ci.py collect --repo REPO [--workflow CI] [--start DAY] > DIR/NAME.json
   python3 scripts/ci.py summary DIR/NAME.json
   ```

   The default is yesterday, a UTC day; `--day` picks another. The first time
   a repository is tracked, backfill with `--since` up to 90 days back, the
   time GitHub keeps job logs; it reads every run's jobs, so expect minutes.
   Pass `--workflow` when a repository also runs a workflow on only some
   pushes (path filters, a release proof), naming the workflow every push
   runs, so a commit that skipped CI does not read as a fast one. Pass
   `--start` with the day CI was reworked or re-enabled, so older runs stay
   out of the 7-day median. A stored day's `workflows` and `start` fields
   give the values to reuse. When `stderr` says a log
   could not be read, the day has no `tests`; say so rather than guessing.

3. Find the steps:

   ```sh
   python3 scripts/ci.py shifts DIR/NAME.json > DIR/NAME-shifts.json
   ```

   Each step is a point where the median wall time of the green commits
   before it and after it differs by at least a minute and 15 percent, with
   the jobs' medians on both sides and the commits around it. Each `hang` is
   a stretch of commits whose CI failed only after an hour or more, such as
   tests hanging until the job timeout, with the commit that started it and
   the first one after it. Drop a candidate already in `incidents` for the
   same repository within three days, and a step that no change explains,
   such as one that reverses within a day or moves every job alike (runner
   speed).

4. Name the cause of each remaining step. Look at the suspects' PRs and
   commits: workflow files, test setup, the jobs that moved. Write
   `DIR/incidents.json`, a list in the shape `references/data.md` gives: the
   day, the repository, `slower` or `faster` (a hang is `slower` when it
   starts and `faster` when the change that ended it lands), the medians
   before and after,
   a title naming the change, `ref` as `owner/name#number` or a commit, and
   `why` in one sentence (what moved and why). A step whose cause you cannot
   confirm from the changes is left out, not guessed.

5. Without `DOC`, reply with the summary table and any incidents; stop here.

6. Store each repository, unless the maintainer asked for the table only.
   When the maintainer said yes to a new document:

   ```sh
   python3 scripts/ci.py create DIR/*.json --incidents DIR/incidents.json > DIR/create.json
   ```

   (list only the collected `NAME.json` files.) Pass its `title`,
   `description`, `tldr` and `blocks` to `create_doc`, with `tags`: the
   active ids from `list_tags` that fit CI, testing or engineering health,
   so the document is found by tag as well as by search. If none fits, say
   so in the reply rather than leaving it silently untagged. The result is
   `DOC`. Then, for each repository:

   ```sh
   python3 scripts/ci.py records DIR/NAME.json [DIR/incidents.json] > DIR/NAME-ops.json
   ```

   Pass the array as `operations` to `update_data` on `DOC` (incidents only
   once), then read the area summary back with `get_data` and confirm every
   collection is valid. Storing a day again replaces it.

7. With a `DOC` that existed before this run:

   - A repository without a section yet: insert the blocks from
     `ci.py section DIR/NAME.json` at the end of `DOC`.
   - Job names changed: when the wall-time chart in `ci.py section`'s output
     names other `y` fields than the one in `DOC`, replace that chart block.
   - New incidents: read `incidents` again with `get_data`, write it to
     `DIR/all-incidents.json`, run `ci.py changelog DIR/all-incidents.json`,
     and replace the list items under the "Incidents" heading with its
     blocks. Leave every other block as it is.

8. Reply with each repository's total wall time (7-day median), the jobs,
   the tests, any new incident, and where the day was stored. When the skill
   runs on a schedule with nothing new, a single line is enough.
