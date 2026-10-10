# Data

What `scripts/ci.py` measures, the records it writes and the document that
holds them.

## Measures

The skill reads GitHub Actions runs on the repository's default branch
triggered by a push, grouped by commit. Dynamic workflows (Copilot review,
Dependabot) and runs on tags are left out. For each run it takes the latest
attempt's jobs, skipping jobs that were skipped.

| Field | Per commit | Per day |
| --- | --- | --- |
| `wall_min` | first job start to last job end, over every workflow of the push | median of the day's green commits |
| `wall_min_7d` | | median of green commits over the 7 days ending that day: the headline |
| `<job>_min` | one job's start to end | median of the day's green commits |
| `execution_min` | all job minutes added up | median, for contrast with wall time |
| `wait_min` | push to the first job starting: concurrency and runner queueing | median, context only |
| `commits`, `failed` | | commits whose runs all finished, and how many of them were not green |
| `tests` | tests the jobs report | from the day's last green commit |

- A day is a UTC calendar day; a commit belongs to the day its first run was
  created. A commit with a run still going is left for a later collection.
- Green means every workflow of the commit concluded `success`, `skipped` or
  `neutral`. Failed and cancelled commits count in `failed` only, since a run
  that stopped early would read as fast.
- With `--workflow`, a commit counts only when it ran one of the named
  workflows; the day's `workflows` field records them. With `--start`, runs
  before that day are ignored, also by the 7-day median; `start` records it.
- A job's field is its workflow and job name in lowercase, joined by
  underscores, plus `_min`, for example `ci_browser_e2e_min`; `jobs` in
  `data.json` maps each field to its display name. A renamed job starts a
  new field.
- `tests` sums what test runners print in the job logs: vitest and jest
  summaries, playwright, unittest (`Ran N tests`, less skipped), pytest, the
  node test runner's `ℹ tests` line, and one mark per test from its dot
  reporter. Skipped tests do not count. Jobs that differ only in their
  matrix values in parentheses run one suite, so they count once, at the
  largest. Logs are kept 90 days; older days have no `tests`.

## Incidents

An incident is a step in total wall time with a known cause. `ci.py shifts`
proposes candidates: at each green commit, the median of the eight green
commits before against the eight from it on; a step moves at least a minute
and 15 percent, and of nearby steps only the largest stays. It also lists
hangs: stretches of commits whose CI failed after at least an hour and three
times the green median, which wall time leaves out as failures. The agent
keeps a candidate only when a change explains it and writes
`incidents.json`:

```json
[{"day": "2026-10-04", "repo": "uberblick-ai/ub-agents", "direction": "faster",
  "before_min": 2.9, "after_min": 1.1, "change_min": -1.8, "change_pct": -62,
  "title": "Run the test suite on every core and trim slow tests",
  "ref": "uberblick-ai/ub-agents#189",
  "why": "Tests run in one worker per core and real-terminal checks wait for output instead of fixed delays."}]
```

`ref` is `owner/name#number` or a commit SHA, with `url` for a commit;
`records` derives `url` from a `#number` reference. The id is
`NAME/DAY`, so storing an incident again replaces it.

## Records

`ci.py records` writes one `update_data` batch:

| Collection | Key | One record per |
| --- | --- | --- |
| `NAME`, the repository's name | `2026-10-09` | day, every field above |
| `incidents` | `uberblick-2/2026-09-02` | incident |

Each repository has its own collection because a chart reads one
collection. The schema lists every job field seen, so a batch that adds a
job widens it; earlier records stay valid. A day takes about 400 bytes, so a
year of two repositories stays far below a document's 4 MiB.

## Document

"CI health", one document for every tracked repository, reads top to bottom:

1. **Intent.** One paragraph: what is measured and why wall time, not
   execution time. One more on how to read the charts and where the data
   comes from.
2. **Incidents.** The latest five, newest first, one list item each: the
   day and repository, the change linked, the direction with the medians
   before and after, and why. `ci.py changelog` rewrites this list.
3. **One section per repository.** A heading, then two line charts bound to
   its collection: wall time (the 7-day total first, then each job of the
   last three days with green commits, at most seven) and tests.

`create` writes the whole document; `section` writes one more repository's
blocks. Everything outside the Incidents list is written once and may be
edited by hand, except the wall-time chart, which the skill replaces when
the jobs change.
