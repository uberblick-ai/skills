# The report

One page per repository per day, and one record of it. It answers, in this
order: how autonomous the day was, what to change, where the extra runs went,
how each item fared, how much context the runs used, what the roles said about
themselves.

## Runs

Every run gets a class from the repository's `ub-agents.yaml`. Roles run in
the order P preparer, Q issue reviewer, I implementer, R reviewer,
G integrator.

- **forward**: an accepted outcome the role declares, whose labels trigger the
  same or a later role, or none.
- **back**: an accepted outcome whose labels trigger only earlier roles, such
  as a reviewer's `changes`.
- **stop**: an outcome that adds a stop label (`needs-human` by default).
- **waste**: no accepted outcome the role declares: `retry`, `no report`,
  `blocked`, a deferral.
- **pending**: still running when the day was collected, with an unexpired
  lease. It counts toward nothing until a later collection sees its outcome.

A withdrawn lease, a claim that never started and a recovery lease that only
re-posts another run's report are not runs.

A **loop delivery** is an item delivered on the day that an implementer worked
on. Work that came from outside the loop, such as a PR written in an attended
session, is shown but not counted.

## KPIs

| KPI | Goal | Target | Definition | Fields |
| --- | --- | --- | --- | --- |
| Autonomous deliveries | up | 75% or more | Loop deliveries the integrator merged with no wasted run, no stop and no action-needed notice. A send-back from the issue reviewer or the reviewer still counts; one from the implementer or integrator does not. | `autonomous`, `autonomous_pct` |
| Wasted runs | down | under 10% | Runs started on the day that were wasted. | `wasted_runs`, `wasted_pct` |
| Human stops | down | | Action-needed notices on loop deliveries, and the hours from each to the next run on the item. | `human_stops`, `human_stops_per_delivery`, `human_wait_h` |
| Cycle | down | | First run to delivery, without the human wait. | `loop_cycle_h_median` (`cycle_h_median` with the wait) |
| Run time | down | | Run minutes summed per delivery, the touch time. | `run_h_median` (`run_h` for all runs on the day) |
| Run time, last 10 | down | | The same, over the last ten loop deliveries counting back from the day's last one: no queueing or human waits, so its direction shows whether the work itself takes longer. Left out until ten are known; only the last 14 days' items are kept. | `run_h_last10_avg`, `run_h_last10_median` |
| Runs with denials | down | under 10% | Claude runs on the day with a permission denial. ub-agents records denials from Claude output only, at most ten a run, and records before about 5 October 2026 carry none, so `denial_pct` is null for those days rather than zero. | `denial_pct`, `runs_with_denials`, `claude_runs` |

A target is guidance for reading a day, not a gate: the page colors a share
green when it meets its target and red when it misses. A day with few
deliveries swings widely, so judge a target over a week. A denial the role
needed points to its permissions or instructions; one that kept it out of
something it should not touch is the sandbox working, which is why the
denial target is not zero.

Shares are percentages, 0 to 100, so a chart plots them as stored. For
context only: `review_rounds_per_delivery`, `lead_h_median` (filed to
merged), PRs merged, lines, issues opened and closed. Run figures count runs
started on the day; delivery figures count a loop delivery's runs up to the end
of the day. Overnight launcher pauses still count toward cycle; ub-agents does
not record them yet. Collect a day a few hours after midnight, so runs still
going at midnight have reported.

Context used, for reading, not a target. ub-agents 0.5.0 and later records
each run's main-session `context` on its outcome: the window, the prompt
tokens of the first call, of call 10 and of the largest call, and how often the
runtime compacted. The day's figures are shares of each run's own window over
the runs started that day that carry it; runs without it are left out, never
counted as zero, and a day where none carries it has none of these fields.

| Field | What it is |
| --- | --- |
| `context_runs` | Runs with recorded context |
| `context_start_pct` | Median context after the first ten calls: how heavy runs start. 20% is the heavy-start level the chart marks |
| `context_peak_pct`, `context_peak_pct_max` | Median and largest peak |
| `context_compacted` | Runs that compacted their context |
| `context_by_runtime` | The same five, as `runs`, `start_pct`, `peak_pct`, `peak_pct_max` and `compacted`, per runtime (`claude`, `codex`) |

Inflow and capacity, also context:

| Field | What it counts |
| --- | --- |
| `backlog_unprepared` | Open issues at the end of the day waiting for preparation (the preparer's trigger labels) |
| `backlog_prepared` | Open issues at the end of the day already prepared: waiting for issue review or ready to implement |
| `backlog` | The two together: the actionable queue. |
| `waiting_to_start` | Open issues no role can take until a person starts them: no workflow label (drafts, sub-issues not yet started, agent-filed follow-ups awaiting approval) or parked at a stop label. Parents with sub-issues are left out; their work counts in the children. |
| `open_issues` | All open issues at the end of the day, parents included. Issues opened above deliveries day after day shows as this rising. |
| `machines` | Distinct hosts that ran a role that day; absent for days whose records name no host (before 2 October 2026) |
| `loops` | Distinct loop checkouts that ran a role that day; absent for days whose records name no checkout (ub-agents 0.3.6 and later) |
| `peak_runs` | The most runs that overlapped at any moment that day |

The queue is reconstructed from today's labels with every later label and
state change undone, so a past day reads the same whenever it is collected;
parent links are today's. `review.py queue --repo REPO --day DAY` prints just
these figures.

## Causes

A finding is one cause on one day: what it cost and one concrete example. The
cause is a mechanism kept in a registry, so the same cause on another day is
the same id, a fixed cause that returns is a regression, and a lesson's effect
shows as its causes stopping.

- The id is lowercase and hyphenated and names the mechanism
  (`report-lost-on-upgrade`), not the incident.
- `mechanism` says in one sentence how it costs runs, without item numbers.
- `state` is `open`, `fixed` (with `fixed_by` naming the PR, commit or issue)
  or `accepted` (a known cost nobody will fix).
- `class` is one of:

| Class | The run lost time because |
| --- | --- |
| `launcher` | the loop runner lost, interrupted or misreported a run |
| `environment` | the checkout, dependencies or tools it started with were wrong |
| `context` | a required document or corpus was missing or unreadable |
| `sandbox` | a permission denial blocked a step it needed |
| `scheduling` | ordering, overlap or blocker rules between items held it |
| `routing` | the wrong role, runtime or reviewer picked it up |
| `integration` | main moved, the merge conflicted or the merged-tree gate failed |
| `ci` | a check was flaky or slow |
| `contract` | preparation or implementation missed something a reviewer caught |
| `decision` | a person's decision was genuinely needed |

Reviewer send-backs get `contract` findings. They do not cost autonomy, but the
same gap recurring is worth fixing.

## Page

1. **Header.** Repository, the day and its time zone, the title "Delivery
   report", then the headline: one sentence saying how the day went and the
   biggest lesson. The headline is the only thing many readers take in.
2. **Figures.** Eleven tiles: autonomous deliveries, wasted runs, human stops
   with the hours waited, cycle with and without the wait, run time, run time
   of the last ten deliveries with its value on the day before, runs with
   denials, PRs merged with lines and files, issues closed and opened, the open
   queue split into to-prepare and prepared, and machines with loops and peak
   parallel runs.
3. **What to change.** At most four cards, each one lesson the day
   proposed: the lever (clearer authority, better wording, fewer
   instructions, more autonomy), a title, the change in one or two
   sentences quoting any line it would change, where it lives, what it
   cost, the causes it targets, the items that are its evidence, and, for a
   lesson still `proposed`, a link to discuss it in Claude Code. Never a new
   role, label, gate, review round or checklist. The document's Recommended
   Actions rank lessons across 14 days instead.
4. **Where extra runs went.** One card per finding, costliest first: the cost
   and class as the label, the concrete example, the cause id with its
   mechanism and state, and the items.
5. **Each delivery.** One row per item the loop touched on that day,
   delivered first, then the costliest: the item with links to its PRs and
   retrospectives, one chip per run in order (green forward, amber back, red
   stop or waste, grey pending), autonomous, wasted runs, review rounds, human
   stops, lines changed, lead, cycle without the wait, run time, and the note.
6. **Context used.** One chart over the stored days (the newest 30) and this
   one, on one 0 to 100% axis: bars for the median start, a line each for
   the median and the largest peak, `↻N` above a day where N runs compacted,
   and a dashed line at 20%. Buttons switch between all runtimes and each
   runtime; hovering a day shows its figures. Below it, one row per agent and
   runtime (runs, start, call 10 in tokens, median and largest peak,
   compacted), and the three runs that came closest to their window, with
   links. `render --days` supplies the stored days; without them the chart
   shows this day alone.
7. **Retrospectives.** The day's board posts grouped by cause: one card per
   group with the number of posts, the cause, a one-sentence summary and links
   to the posts by role. Posts the notes did not group share one last card. A
   line says when none was posted or which board could not be read.

Nothing on the page or in the records is a secret: no credentials, local paths
or hostnames. The script replaces local paths in run summaries; the notes must
not add any.

## Notes

`render` refuses notes with an
unknown class, state or lever, a missing field, one cause in two findings, a
retrospective in two groups or not posted that day, a tracked or applied
lesson without `addressed_by`, or more than five actions.

```json
{"headline": "One sentence: how the day went and the biggest lesson.",
 "items": {"227": "One sentence on what cost runs, or why it was autonomous."},
 "findings": [{"cause": "report-lost-on-upgrade", "class": "launcher",
               "mechanism": "A ub-agents upgrade during active runs removed the report command, so runs exited without an outcome.",
               "state": "fixed", "fixed_by": "uberblick-ai/ub-agents#361",
               "cost": "9 runs", "runs": 9, "items": [1308, 1139],
               "example": "#1308's reviewer ran five times without a report, holding the review for nine hours."}],
 "lessons": [{"id": "launcher-installs-dependencies", "lever": "authority | wording | fewer-instructions | autonomy",
              "title": "...", "change": "...", "where": "file", "cost": "...",
              "causes": ["checkout-deps-stale"], "evidence": [1072], "state": "applied",
              "addressed_by": "uberblick-ai/uberblick-2#1448"}],
 "actions": ["review-runtime-from-author", "ci-leaves-readable-summary"],
 "changes": [{"ref": "uberblick-ai/ub-agents#361", "day": "2026-10-07",
              "title": "Keep in-run commands and helpers on the launcher's startup code",
              "why": "Upgrading ub-agents mid-run removed the report command, so runs ended without an outcome.",
              "causes": ["report-lost-on-upgrade"], "lessons": []}],
 "retrospectives": [{"cause": "report-lost-on-upgrade", "summary": "One sentence for the group.",
                     "posts": ["https://github.com/owner/name/discussions/1014#discussioncomment-1"]}]}
```

Three words keep one meaning each. A **lesson** is a change someone could
make, kept in the `lessons` registry; the **actions** are the lessons the
document recommends now, up to five; a **change** is something that
landed, kept in `changes` and listed in the Changelog.

A lesson is `proposed` until an issue or PR addresses it: `tracked` while that
is open, `applied` once it merged, `rejected` when a person declines it.
`addressed_by` names it as `owner/name#number`, and `addressed_as` says
whether it is a pull request that implements the lesson (`implemented`) or an
issue that plans it (`planned`, the default). `actions` lists up to five
lessons still `proposed` that this day or one of the 13 before it proposed,
most runs saved first; an older lesson drops off until a day proposes it
again. A change is anything that landed on this day to fix a cause or apply a lesson; `ref` is
`owner/name#number` or a commit, with `url` for a commit. `records` gives every
change a `url`, derived from `ref` when the notes give none.

`runs` counts the runs the cause cost on this day: wasted runs, and the
correction and re-review runs a send-back caused. A cause that cost minutes
rather than runs has `runs: 0` and says so in `cost`.

## Records

`collect` writes `data.json`; `render` adds the notes and writes the result as
`report.json` next to the page:

```json
{"schema": "ub-agents-deliver-report/1",
 "repo": "owner/name", "day": "2026-10-07", "timezone": "UTC +0000",
 "since": "2026-10-07T00:00:00Z", "until": "2026-10-08T00:00:00Z",
 "summary": {"repo": "owner/name", "day": "2026-10-07", "headline": "...",
             "deliveries": 5, "autonomous": 2, "autonomous_pct": 40,
             "runs": 54, "wasted_runs": 12, "wasted_pct": 22.2, "run_h": 8.51,
             "human_stops": 2, "human_stops_per_delivery": 0.4, "human_wait_h": 26.92,
             "review_rounds_per_delivery": 1.4, "lead_h_median": 55.05, "cycle_h_median": 20.13,
             "loop_cycle_h_median": 3.83, "run_h_median": 1.76,
             "run_h_last10_avg": 1.92, "run_h_last10_median": 1.68,
             "claude_runs": 40, "runs_with_denials": 28, "denial_pct": 70, "denials": 54,
             "prs_merged": 7, "prs_merged_by_loop": 6, "additions": 4346, "deletions": 735, "files": 106,
             "issues_closed": 8, "issues_opened": 11, "retrospectives": 10},
 "issues": [{"number": 1281, "title": "...", "url": "...", "delivered": true, "loop": true, "autonomous": true,
             "sequence": "P Q< P I R< I R G", "attempts": 8, "wasted_runs": 0, "review_rounds": 2,
             "human_stops": 0, "human_wait_h": 0, "done": "2026-10-07T14:02:11Z", "lead_h": 55.05, "cycle_h": 1.85, "loop_cycle_h": 1.85,
             "run_h": 1.55, "denials": 4, "runs_with_denials": 3, "lines": 889, "note": "...",
             "prs": [], "runs": [], "retrospectives": [],
             "evidence": {"commits": [], "events": [], "ci": [], "errors": []}}],
 "findings": [], "lessons": [], "actions": [], "changes": [], "retrospective_groups": [],
 "retrospectives": {"errors": [], "in_window": []}}
```

`sequence` writes the runs as role letters, marking `<` sent back, `x` wasted,
`!` stopped and `?` pending. Durations are hours.

An item that needs a cause (a send-back, a stop or a wasted run, or a loop
delivery that was not autonomous) carries `evidence`, which its run summaries
leave out: `commits` pushed while none of its runs was going, `events` (label
and state changes, merges) by anyone but the accounts that post run records,
and `ci`, the workflow runs on its PRs with their result, attempt and minutes.
Empty lists are left out. `digest` prints every run of such an item with its
summary, denials and evidence, and one line for every other item.

`records` turns `report.json` into one `update_data` batch. The document
keeps each collection's schema and checks every record against it, so the
batch leaves schemas out unless `--schemas` is passed:

| Collection | Key | One record per |
| --- | --- | --- |
| `days` | `2026-10-07` | day: the summary and headline |
| `items` | `2026-10-07` | day: that day's loop deliveries, compact, kept 14 days |
| `findings` | `2026-10-07/report-lost-on-upgrade` | day and cause |
| `causes` | `report-lost-on-upgrade` | cause: class, mechanism, state, `fixed_by` |
| `lessons` | `launcher-installs-dependencies` | lesson: lever, change, causes, state, `addressed_by` |
| `changes` | `uberblick-ai/ub-agents#361` | change that landed: day, title, why, causes, lessons |

Storing a day again overwrites its records. A person's verdict on a cause or
lesson belongs in a separate `verdicts` collection keyed by the same id; the
skill never writes it, so a refresh cannot overwrite it.

Item detail is a recent snapshot: each item leaves out zero, empty and
derivable fields, and storing a day deletes `items` records older than 14 days.
`days`, `findings`, `causes`, `lessons` and `changes` stay, so trends cover
180 days and more; a year takes about 2 MB of the document's 4 MiB.

## Document

`create` lays a new document out as below, top to bottom:

1. **Intro.** What the loop is, what the report measures, and where the skill
   lives.
2. **Data.** Line charts bound to `days`, then a "Recent days" table, newest
   first. Both are `chart` blocks holding a version-1 mapping, for example:

   ```json
   {"version": 1, "type": "line", "collection": "days", "title": "Autonomy and waste",
    "x": {"field": "day", "type": "date"},
    "y": [{"field": "autonomous_pct", "label": "Autonomous", "unit": "%"},
          {"field": "wasted_pct", "label": "Wasted runs", "unit": "%"},
          {"field": "denial_pct", "label": "Runs with denials", "unit": "%"}],
    "missing": "connect"}
   ```

   A day without loop runs stores its shares and medians as null, not zero,
   since a share of no deliveries is undefined. The charts that plot them
   (autonomy, cycle and run time, context) set `"missing": "connect"`, so
   their lines bridge such a day instead of breaking at it.

   ```json
   {"version": 1, "type": "table", "collection": "days", "title": "Recent days",
    "columns": [{"field": "day", "label": "Day", "format": "date"},
                {"field": "autonomous", "label": "Autonomous", "format": "number"},
                {"field": "wasted_pct", "label": "Wasted share", "format": "number", "unit": "%", "decimals": 0}],
    "sort": {"field": "day", "direction": "desc"}, "limit": 7}
   ```

   The context chart mixes bars and lines on one axis and draws the
   heavy-start level as a reference line. Chart blocks have no point
   annotations, so compactions are a column of the Recent days table, not a
   mark on the chart:

   ```json
   {"version": 1, "type": "line", "collection": "days", "title": "Context used, as a share of the window",
    "x": {"field": "day", "type": "date", "label": "Day"},
    "y": [{"field": "context_start_pct", "label": "Median start (call 10)", "unit": "%", "type": "bar",
           "range": [0, 100], "reference": 20},
          {"field": "context_peak_pct", "label": "Median peak", "unit": "%", "range": [0, 100]},
          {"field": "context_peak_pct_max", "label": "Largest peak", "unit": "%", "range": [0, 100]}],
    "missing": "connect"}
   ```

   `document` returns the same block as `context_chart`, so a document
   created before it gets the chart once.

3. **Recommended Actions.** The day's `actions`, each a card: the lever as
   its label, the title, the change as its body, and a footer with where it
   lives, its cost, causes and evidence. Each has a "Discuss in Claude Code"
   button (`claude://code/new?q=PROMPT`, a `button:` line that Uberblick
   reads from the release after 0.4.3) whose prompt names the repository,
   the document, the lesson's day, the change and its evidence. It first has
   the session search the issues and pull requests for the same change, open
   ones (drafts included) and ones merged or closed in the last 30 days, and
   work from one that covers it instead of starting another; then it asks for
   a plan. When that discussion settles on the lesson, or the search finds an
   open pull request or issue already making it, the session replaces the
   card with a struck-through one as soon as a pull request (a draft counts)
   or issue exists, and sets the lesson to `tracked` with `addressed_by` and
   `addressed_as`. Below the proposed
   cards, `tracked` lessons of the last 14 days stay struck through, with
   no button and a footer such as `Planned in
   [acme/app#212](https://github.com/acme/app/issues/212).`, until that
   change merges or closes.
4. **Changelog.** The five latest `changes`, newest first, such as `20 Oct:
   Quarantine six flaky tests
   ([uberblick-2#2004](https://github.com/uberblick-ai/uberblick-2/pull/2004)).
   Six tests turned main red;
   [#2003](https://github.com/uberblick-ai/uberblick-2/issues/2003) tracks
   them.` Uberblick draws a GitHub pill only for a link whose text names the
   item, so the reference is the link, with GitHub's own `/pull/` or
   `/issues/` address, and `#n`, `name#n` and `owner/name#n` in `why` are
   linked the same way. A commit keeps its title linked to the commit.

`document` marks each card `changed` and counts new changelog items in
`changelog_new`, so the skill updates these two sections one block at a time.
Everything else is written once, by `create` or a person; the charts plot
every stored day and the Recent days table the newest seven.
