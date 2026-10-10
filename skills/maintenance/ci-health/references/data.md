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
| `wall_spread_7d` | | half the interquartile range over the same commits: the ± around the headline |
| `wall_p95_7d` | | 95th percentile by nearest rank over the same commits: the slow tail |
| `<job>_min` | one job's start to end | median of the day's green commits |
| `execution_min` | all job minutes added up | median, for contrast with wall time |
| `wait_min` | push to the first job starting: concurrency and runner queueing | median, context only |
| `commits`, `failed` | | commits whose runs all finished, and how many of them were not green |
| `tests`, `tests_pattern` | tests the jobs report, and the patterns that read them | from the day's last green commit |
| `code_lines`, `test_lines`, `test_ratio` | | at the last green commit, by `measure` |
| `coverage_pct`, `measured_sha` | | the same commit, by `mise run codecov` |

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
- With under 20 green commits in the 7 days, `wall_p95_7d` is the slowest
  of them, so it is noisy on quiet repositories.
- `tests` is read from the job logs with patterns the agent writes for the
  repository's test runners, since every language prints its own summary.
  Each pattern is a regular expression whose groups capture counts; every
  integer they capture, on every line that matches, is added up per job.
  Timestamps and terminal colors are stripped first. Count tests run or
  passed, not skipped. Jobs that differ only in their matrix values in
  parentheses run one suite, so they count once, at the largest. Logs are
  kept 90 days; older days have no `tests`.

## Code and coverage

`ci.py measure` checks out the last green commit of the last day in a
temporary worktree of a local clone and adds its figures to that day. It
looks for two `mise` tasks by name and trusts the worktree's mise config for
that run:

| Task | Prints, as the last JSON line of its output | Without it |
| --- | --- | --- |
| `mise run codecov` | `{"coverage_pct": 81.2}`, line coverage in percent | no coverage |
| `mise run loc` | `{"code_lines": 12000, "test_lines": 4800}` | a built-in count |

The built-in count takes the source files git tracks, by extension, and
counts non-blank lines; a file is a test when its path matches the usual
test locations (`tests/`, `__tests__/`, `spec/`, `test_*`, `*_test.*`,
`*.test.*`, `*.spec.*`, `*Tests.*`). A repository whose layout differs
defines `loc`. `test_ratio` is test lines per code line.

The coverage task runs the test suite with the language's own coverage tool
and prints the total. For example, in `mise.toml`:

```toml
# Python, coverage.py
[tasks.codecov]
run = """
coverage run -m pytest -q >/dev/null
coverage json -q -o - | python3 -c 'import json,sys; print(json.dumps({"coverage_pct": json.load(sys.stdin)["totals"]["percent_covered"]}))'
"""

# Rust, cargo-llvm-cov
[tasks.codecov]
run = """
cargo llvm-cov --json --summary-only | jq -c '{coverage_pct: .data[0].totals.lines.percent}'
"""

# C#, coverlet (dotnet test --collect "XPlat Code Coverage" works as well)
[tasks.codecov]
run = """
dotnet test /p:CollectCoverage=true /p:CoverletOutputFormat=json /p:CoverletOutput=./coverage/ >/dev/null
jq -c '[.[] | .[] | .[] | .[]] | {coverage_pct: (100 * ([.[].Lines | to_entries[] | select(.value > 0)] | length) / ([.[].Lines | length] | add))}' coverage/coverage.json
"""

# TypeScript, vitest with the json-summary reporter
[tasks.codecov]
run = """
vitest run --coverage --coverage.reporter=json-summary >/dev/null
jq -c '{coverage_pct: .total.lines.pct}' coverage/coverage-summary.json
"""
```

These are starting points, not requirements: any command that prints the
JSON line works, and a task may take up to `--timeout` seconds (30 minutes
by default).

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
[{"day": "2026-10-04", "repo": "acme/app", "direction": "faster",
  "before_min": 2.9, "after_min": 1.1, "change_min": -1.8, "change_pct": -62,
  "title": "Run the test suite on every core and trim slow tests",
  "ref": "acme/app#189",
  "why": "Tests run in one worker per core and real-terminal checks wait for output instead of fixed delays."}]
```

`ref` is `owner/name#number` or a commit SHA, with `url` for a commit;
`records` derives `url` from a `#number` reference. The id is
`DAY/CHANGE`, the change being `ref` (or the title) in lowercase with
hyphens, so several changes on one day stay apart and storing an incident
again replaces it.

## Records

`ci.py records` writes one `update_data` batch for the repository's
document; with `--doc UUID` it prints the full `update_data` arguments:

| Collection | Key | One record per |
| --- | --- | --- |
| `days` | `2026-10-09` | day, every field above |
| `incidents` | `2026-10-04/acme-app-189` | incident |

The schema lists every job field seen, so a batch that adds a job widens it;
earlier records stay valid. A day takes about 400 bytes, so a year stays far
below a document's 4 MiB. `records` refuses an incident for another
repository.

## Document

Each repository has its own "CI health" document, in the Uberblick workspace
of that repository's corpus. It reads top to bottom:

1. **Intent.** One paragraph: what is measured and why wall time, not
   execution time. One more on how to read the charts and where the data
   comes from.
2. **Charts.** Line charts bound to `days`: wall time (the 7-day median and
   P95 of the total first, then each job of the last three days with green
   commits, at most six), tests, and, once measured, code against test lines
   and coverage.
3. **Incidents.** Below the charts, the latest five, newest first, one list
   item each: the day, the change linked, the direction with the medians
   before and after, and why. `ci.py changelog` rewrites this list.

Search indexes the title, description and block text, not the records, so
the description names what the data holds; `create` also gives a TL;DR, and
the agent adds the fitting catalog tags. `create` writes the whole document.
Everything outside the Incidents list is written once and may be edited by
hand, except the charts, which the skill replaces or adds from `ci.py
charts` when the jobs change or a new measure appears.
