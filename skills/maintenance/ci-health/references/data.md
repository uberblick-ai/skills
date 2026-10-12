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
| `late_start_min` | how long after the first job the last job of a minute or more started: runner waits (macOS, a busy pool) or `needs` | median, context only |
| `commits`, `failed` | | commits whose runs all finished, and how many of them were not green |
| `tests`, `tests_pattern` | tests the jobs report, and the patterns that read them | from the day's last green commit |
| `code_lines`, `test_lines`, `test_ratio` | | at the day's last green commit, by `measure` |
| `loc_tool`, `loc_paths` | | the line counter and the pathspecs it counted, joined by ` \|\| ` |
| `coverage_pct`, `measured_sha` | | the same commit, by `mise run codecov`; the last day only |

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
  integer they capture, on every line that matches, is added up per job,
  except a group named `skipped`, which is subtracted. Timestamps and
  terminal colors are stripped first. Count tests run or passed, not
  skipped. Jobs that differ only in their matrix values in parentheses run
  one suite, so they count once, at the largest. Logs are kept 90 days;
  older days have no `tests`.

## Code and coverage

`ci.py measure` checks out the last green commit of the last day in a
temporary worktree of a local clone and adds its figures to that day; with
`--every-day` it adds the lines to every day, while coverage, which runs the
suite, stays on the last day. It looks for two `mise` tasks by name and
trusts the worktree's mise config for that run:

| Task | Prints, as the last JSON line of its output | Without it |
| --- | --- | --- |
| `mise run codecov` | `{"coverage_pct": 81.2}`, line coverage in percent | no coverage |
| `mise run loc` | `{"code_lines": 12000, "test_lines": 4800}` | a built-in count |

The built-in count lists the files git tracks under the `--path`
pathspecs, all of them without one, so untracked trees such as
dependencies, build output or nested worktrees never count. It runs the
first line counter installed, [scc](https://github.com/boyter/scc) or
[cloc](https://github.com/AlDanial/cloc); both know the comment syntax of
hundreds of languages, and a line of code is neither blank nor only a
comment, so trimming comments does not read as less code. Prose and data
(Markdown, text, JSON, YAML, TOML, XML, CSV and the like) are left out;
style, markup and scripts count. A file is a test when its path matches
the usual test locations (`tests/`, `__tests__/`, `spec/`, `e2e/`,
`test_*`, `*_test.*`, `*.test.*`, `*.spec.*`, `*Tests.*`).

The paths are the agent's call: the main source directories, as the build
declares them, without documentation, sites, examples, scripts, fixtures,
generated or vendored code. Without either counter, `measure` suggests
the install command for the first package manager on the host: scc from
Homebrew, MacPorts, Scoop, WinGet, Chocolatey or FreeBSD's pkg, cloc from
apt, dnf, pacman or apk, scc through `go install`, or else an scc release.
A repository whose layout the paths cannot express defines `loc`. `test_ratio` is test lines per code line. The two
counters differ by about one percent, so `loc_tool` records which counted;
a change of counter or paths moves the ratio without a change in the code.

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
and 15 percent, and of nearby steps only the largest stays, placed where
the means before and after differ most. Its suspects are every commit since
two green commits before it, failed ones included. It also lists hangs:
stretches of commits whose CI failed after at least an hour and three times
the green median, which wall time leaves out as failures. Both list only
what falls on the collected days. The agent keeps a candidate only when a
change explains it and writes `incidents.json`:

```json
[{"day": "2026-10-04", "time": "2026-10-04T09:12:31Z", "repo": "acme/app",
  "direction": "faster", "before_min": 2.9, "after_min": 1.1,
  "change_min": -1.8, "change_pct": -62,
  "title": "Run the test suite on every core", "ref": "acme/app#189",
  "why": "The suite ran in one process; it now runs one worker per core."}]
```

`ref` is `owner/name#number` or a commit SHA, with `url` for a commit;
`records` derives `url` from a `#number` reference. `time` is when the
change's first run started, as `shifts` gives it; it orders several
incidents on one day. The id is
`DAY/CHANGE`, the change being `ref` (or the title) in lowercase with
hyphens, so several changes on one day stay apart and storing an incident
again replaces it.

## Actions

The top three changes that would most cut the time pushes wait for a green
main, judged again on every run. `ci.py signals` gives the evidence over
the 7 days ending the last day: pushes a day, failed pushes, the green
median and P95, and per job its median minutes, how often it ends last on
a green push and by how much (`ends_last`, `ahead_min`; a job under half a
minute, such as a summary job, is left out), and how often it failed. It
also lists hangs, and `waiting_min_per_day` puts each on one scale, the
rough minutes of waiting a day they account for:

| Key | Estimate |
| --- | --- |
| `slowest_job` | the last job's lead over the next one, on every green push it ends |
| `failed_pushes` | one more green run for every failed push |
| `runner_waits` | queueing plus late starts, on every push |
| `hangs` | the time hung runs held before failing |

The agent writes `actions.json`, at most three, in rank order:

```json
[{"id": "split-browser-e2e", "since": "2026-10-11", "area": "Wall time",
  "title": "Split browser e2e across parallel runners",
  "why": "Browser e2e ends 10.7 min after the other jobs on every green push, 27 pushes a day. Three shards would save about 200 min of waiting a day.",
  "check": "Read .github/workflows/ci.yml and the Playwright config.",
  "impact_min_per_day": 200}]
```

`id` and `since` carry over from the stored action an entry keeps; a new
one gets its `id` from the title and starts on the last collected day.
`rank` and `updated` are set when stored. `ci.py cards` renders each as a
card: the area and since when as its label, the title, `why` as its body,
and a footer link, "Discuss in Claude Code", to
`claude://code/new?q=PROMPT`, which opens a new session in the Claude
desktop app with the prompt filled in, not sent. The prompt names the
repository and the document, the day of the data, the recommendation, its
evidence and `check`, and asks for a plan before any change; the link
cannot select a repository by name, only a local folder, so the prompt
names it.

## Records

`ci.py records` writes one `update_data` batch for the repository's
document; with `--doc UUID` it prints the full `update_data` arguments:

| Collection | Key | One record per |
| --- | --- | --- |
| `days` | `2026-10-09` | day, every field above |
| `incidents` | `2026-10-04/acme-app-189` | incident |
| `actions` | `split-browser-e2e` | current action; `--actions` replaces the set |

The schema lists every job field seen, so a batch that adds a job widens it;
earlier records stay valid. A day takes about 400 bytes, so a year stays far
below a document's 4 MiB. `records` refuses an incident for another
repository.

## Document

Each repository has its own "CI Health Report" document, in the Uberblick workspace
of that repository's corpus. It reads top to bottom:

1. **Intent.** One paragraph: what is measured and why wall time, not
   execution time. One more on how to read the charts and where the data
   comes from.
2. **Charts.** Line charts bound to `days`: total wall time (the 7-day
   median and P95), tests, and, once measured, the test-to-code ratio and
   coverage. Per-job times are in the data, not drawn.
3. **Actions.** Below the charts, the current top three as cards, each
   with a link to discuss it in Claude Code. `ci.py cards` rewrites them
   on every run.
4. **Incidents.** Below the actions, the latest five, newest first, one list
   item each: the day, the change linked, the direction with the medians
   before and after, and why. `ci.py changelog` rewrites this list.

Search indexes the title, description and block text, not the records, so
the description names what the data holds, and the agent adds the fitting
catalog tags. The document has no TL;DR; the charts, actions and incidents
are the summary. `create` writes the whole document.
Everything outside the charts, the action cards and the Incidents list is
written once and may be edited by hand. The skill replaces a chart when `ci.py charts` gives
a different one, after a skill update, and adds one when a new measure
appears.
