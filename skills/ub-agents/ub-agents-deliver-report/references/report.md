# The report

One page per repository per day, and one record of it. It answers, in this
order: how autonomous the day was, what to change, where the extra runs went,
how each item fared, what the roles said about themselves.
`scripts/review.py render` lays the page out from `data.json` and
`notes.json`; `scripts/review.py records` turns the result into dataset
records. This file says what each holds.

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
re-posts another run's report are not runs. Every record version the loop has
written (`ub-agent:v1`, `ub-agent:v2`, `ub-agents:v2`, `ub-agents:v3`) carries the
same JSON record, and all are read.

A **loop delivery** is an item delivered on the day that an implementer worked
on. Work that came from outside the loop, such as a PR written in an attended
session, is shown but not counted.

## KPIs

| KPI | Goal | Definition | Fields |
| --- | --- | --- | --- |
| Autonomous deliveries | up | Loop deliveries the integrator merged with no wasted run, no stop and no action-needed notice. A send-back from the issue reviewer or the reviewer still counts; one from the implementer or integrator does not. | `autonomous`, `autonomous_pct` |
| Wasted runs | down | Runs started on the day that were wasted. | `wasted_runs`, `wasted_pct` |
| Human stops | down | Action-needed notices on loop deliveries, and the hours from each to the next run on the item. | `human_stops`, `human_stops_per_delivery`, `human_wait_h` |
| Cycle | down | First run to delivery, without the human wait. | `loop_cycle_h_median` (`cycle_h_median` with the wait) |
| Run time | down | Run minutes summed per delivery, the touch time. | `run_h_median` (`run_h` for all runs on the day) |
| Runs with denials | down | Claude runs on the day with a permission denial. ub-agents records denials from Claude output only, at most ten a run, and records before about 5 October 2026 carry none, so `denial_pct` is null for those days rather than zero. | `denial_pct`, `runs_with_denials`, `claude_runs` |

Shares are percentages, 0 to 100, so a chart plots them as stored. For
context only: `review_rounds_per_delivery`, `lead_h_median` (filed to
merged), PRs merged, lines, issues opened and closed. Run figures count runs
started on the day; delivery figures count a loop delivery's runs up to the end
of the day. Overnight launcher pauses still count toward cycle; ub-agents does
not record them yet. Collect a day a few hours after midnight, so runs still
going at midnight have reported.

Inflow and capacity, also context:

| Field | What it counts |
| --- | --- |
| `backlog_unprepared` | Open issues at the end of the day waiting for preparation (the preparer's trigger labels) |
| `backlog_prepared` | Open issues at the end of the day already prepared: waiting for issue review or ready to implement |
| `backlog` | The two together: the actionable queue. |
| `waiting_to_start` | Open issues no role can take until a person starts them: no workflow label (drafts, sub-issues not yet started, agent-filed follow-ups awaiting approval) or parked at a stop label. Parents with sub-issues are left out; their work counts in the children. |
| `open_issues` | All open issues at the end of the day, parents included. Issues opened above deliveries day after day shows as this rising. |
| `machines` | Distinct hosts that ran a role that day |
| `loops` | Distinct loop checkouts that ran a role that day |
| `peak_runs` | The most runs that overlapped at any moment that day |

The queue is reconstructed from today's labels with every later label and
state change undone, so a past day reads the same whenever it is collected;
parent links are today's. `review.py queue --repo REPO --day DAY` prints just
these figures, from issue lists and events without run records.
Hosts and checkouts are counted, never stored: the collector keys on short
hashes.

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
2. **Figures.** Ten tiles: autonomous deliveries, wasted runs, human stops
   with the hours waited, cycle with and without the wait, run time, runs with
   denials, PRs merged with lines and files, issues closed and opened, the open
   queue split into to-prepare and prepared, and machines with loops and peak
   parallel runs.
3. **What to change.** At most four cards, each one lesson: the lever
   (clearer authority, better wording, fewer instructions, more autonomy), a
   title, the change in one or two sentences quoting any line it would
   change, where it lives, what it cost, the causes it targets and the items
   that are its evidence. Never a new role, label, gate, review round or
   checklist.
4. **Where extra runs went.** One card per finding, costliest first: the cost
   and class as the label, the concrete example, the cause id with its
   mechanism and state, and the items.
5. **Each delivery.** One row per item the loop touched on that day,
   delivered first, then the costliest: the item with links to its PRs and
   retrospectives, one chip per run in order (green forward, amber back, red
   stop or waste, grey pending), autonomous, wasted runs, review rounds, human stops, lines
   changed, lead, cycle without the wait, run time, and the note.
6. **Retrospectives.** The day's board posts grouped by cause: one card per
   group with the number of posts, the cause, a one-sentence summary and links
   to the posts by role. Posts the notes did not group share one last card. A
   line says when none was posted or which board could not be read.

Nothing on the page or in the records is a secret: no credentials, local paths
or hostnames. The script replaces local paths in run summaries; the notes must
not add any.

## Notes

The reviewing agent writes `notes.json`; `render` refuses notes with an
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

A lesson is `proposed` until an issue or PR addresses it: `tracked` while that
is open, `applied` once it merged, `rejected` when a person declines it.
`addressed_by` names it as `owner/name#number`. `actions` ranks up to five
proposed lessons proposed or re-proposed in the last 14 days, most runs saved
first; an older lesson drops off until a day proposes it again. A change is anything
that landed on this day to fix a cause or apply a lesson; `ref` is
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
 "repo": "owner/name", "day": "2026-10-07", "timezone": "CEST +0200",
 "since": "2026-10-06T22:00:00Z", "until": "2026-10-07T22:00:00Z",
 "summary": {"repo": "owner/name", "day": "2026-10-07", "headline": "...",
             "deliveries": 5, "autonomous": 2, "autonomous_pct": 40,
             "runs": 54, "wasted_runs": 12, "wasted_pct": 22.2, "run_h": 8.51,
             "human_stops": 2, "human_stops_per_delivery": 0.4, "human_wait_h": 26.92,
             "review_rounds_per_delivery": 1.4, "lead_h_median": 55.05, "cycle_h_median": 20.13,
             "loop_cycle_h_median": 3.83, "run_h_median": 1.76,
             "claude_runs": 40, "runs_with_denials": 28, "denial_pct": 70, "denials": 54,
             "prs_merged": 7, "prs_merged_by_loop": 6, "additions": 4346, "deletions": 735, "files": 106,
             "issues_closed": 8, "issues_opened": 11, "retrospectives": 10},
 "issues": [{"number": 1281, "title": "...", "url": "...", "delivered": true, "loop": true, "autonomous": true,
             "sequence": "P Q< P I R< I R G", "attempts": 8, "wasted_runs": 0, "review_rounds": 2,
             "human_stops": 0, "human_wait_h": 0, "lead_h": 55.05, "cycle_h": 1.85, "loop_cycle_h": 1.85,
             "run_h": 1.55, "denials": 4, "runs_with_denials": 3, "lines": 889, "note": "...",
             "prs": [], "runs": [], "retrospectives": []}],
 "findings": [], "lessons": [], "actions": [], "changes": [], "retrospective_groups": [],
 "retrospectives": {"errors": [], "in_window": []}}
```

`sequence` writes the runs as role letters, marking `<` sent back, `x` wasted,
`!` stopped and `?` pending. Durations are hours.

`records` turns `report.json` into one `update_data` batch for the dataset
document, each collection with its schema:

| Collection | Key | One record per |
| --- | --- | --- |
| `days` | `2026-10-07` | day: the summary and headline |
| `items` | `2026-10-07` | day: that day's loop deliveries, compact, kept 14 days |
| `findings` | `2026-10-07/report-lost-on-upgrade` | day and cause |
| `causes` | `report-lost-on-upgrade` | cause: class, mechanism, state, `fixed_by` |
| `lessons` | `launcher-installs-dependencies` | lesson: lever, change, causes, state, `addressed_by` |
| `changes` | `uberblick-ai/ub-agents#361` | change that landed: day, title, why, causes, lessons |

Storing a day again overwrites its records; a finding that no longer applies
stays until `deleteRecords` removes it. A person's verdict on a cause or
lesson belongs in a separate `verdicts` collection keyed by the same id; the
skill never writes it, so a refresh cannot overwrite it. Item detail is a recent snapshot: each item leaves out zero, empty and derivable
fields, and storing a day deletes `items` records older than 14 days. `days`,
`findings`, `causes`, `lessons` and `changes` stay, so trends cover 180 days
and more. A document's data is limited to 4 MiB; a year of days and findings
takes about 2 MB.

## Document

The dataset document is optional: the skill updates it when it exists,
offers to create it when Uberblick is available but no document holds the
collections above, and leaves the page as the whole result when Uberblick is
not available. `scripts/review.py create` writes the `create_doc` arguments
for a new one, from `report.json`, in the layout below. It reads top to
bottom:

1. **Intro.** What the loop is, what the report measures, and where the skill
   lives.
2. **KPIs.** The table above in short: each KPI, its goal and one line of
   definition.
3. **Data.** Line charts bound to `days`, then a "Recent days" table of the
   last seven days. Both are `chart` blocks holding a version-1 mapping, for
   example:

   ```json
   {"version": 1, "type": "line", "collection": "days", "title": "Autonomy and waste",
    "x": {"field": "day", "type": "date"},
    "y": [{"field": "autonomous_pct", "label": "Autonomous", "unit": "%"},
          {"field": "wasted_pct", "label": "Wasted runs", "unit": "%"},
          {"field": "denial_pct", "label": "Runs with denials", "unit": "%"}]}
   ```

   ```json
   {"version": 1, "type": "table", "collection": "days", "title": "Recent days",
    "columns": [{"field": "day", "label": "Day", "format": "date"},
                {"field": "autonomous", "label": "Autonomous", "format": "number"},
                {"field": "wasted_pct", "label": "Wasted share", "format": "number", "unit": "%", "decimals": 0}],
    "sort": {"field": "day", "direction": "desc"}, "pageSize": 7}
   ```

4. **Actions.** The day's `actions`: up to five proposed lessons, each a
   heading, the change, and a line with the lever, where it lives, its cost,
   its causes and its evidence. A lesson leaves the list once an issue or PR
   addresses it.
5. **Changelog.** A bullet list of the five latest `changes`, newest first:
   the day, the change linked to its issue, PR or commit in ub-agents or the
   project, and why it was made.

The skill rewrites the "Actions" and "Changelog" sections, from `document`'s
output, after each stored day. Everything else is written once, by `create` or by a person,
and may be edited by hand; the charts and tables follow the data by
themselves.
