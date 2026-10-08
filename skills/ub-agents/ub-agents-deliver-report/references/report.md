# The report

One page per repository per day. It answers, in this order: what shipped,
what to change, where the extra runs went, how each item fared, what the
roles said about themselves. `scripts/review.py render` lays it out from
`data.json` and `notes.json`; this file says what goes where.

## Page

1. **Header.** Repository, the day and its time zone, the title "Delivery
   report", then the headline: one sentence saying what shipped and the
   biggest lesson. The headline is the only thing many readers take in.
2. **Figures.** Six tiles: PRs merged (and how many by the integrator),
   lines added and removed with the file count, issues closed and opened,
   agent runs with how many were accepted and the hours they took, first-pass
   deliveries out of all deliveries, denied commands.
3. **What to change.** At most four cards, each one lesson: the lever
   (clearer authority, better wording, fewer instructions, more autonomy), a
   title, the change in one or two sentences quoting any line it would
   change, where it lives, what it cost, and the items that are its evidence.
   Never a new role, label, gate, review round or checklist.
4. **Where extra runs went.** One card per cause, grouped by mechanism and
   costliest first: the cost in runs or hours waited as the card's label, the
   cause in one or two sentences, its state in a muted line (fixed by a merged
   PR, covered by an open issue, or open), and the items it touched.
5. **Each delivery.** One row per item the loop touched on that day, delivered
   first and the costliest first: the item with links to its PRs and
   retrospectives, one chip per run in role order (P preparer, Q issue
   reviewer, I implementer, R reviewer, G integrator; green moved forward,
   amber sent back, red blocked, retried or no report), lines changed, lead
   time from filing to merge, and the note naming what cost runs.
6. **Retrospectives.** Every board post from that day, as written, linked to
   its source, or a line saying none was posted or which board could not be
   read.

Nothing on the page is a secret: no credentials, local paths or hostnames.
The script replaces local paths in run summaries; the notes must not add any.

## Records

`collect` writes `data.json`, `render` adds the notes to it and writes the
result as `report.json` next to the page. The shape is one `summary` record
for the day and one record per item in `issues`, each keyed by `repo`, `day`
and `number`, so a producer can append them to a document-owned dataset
(uberblick-2 #1397 keeps daily `summaries` and per-issue `issues` arrays in
one document) without reshaping them. `schema` names the version of this
shape.

```json
{"schema": "ub-agents-deliver-report/1",
 "repo": "owner/name", "day": "2026-10-07", "timezone": "CEST +0200",
 "since": "2026-10-06T22:00:00Z", "until": "2026-10-07T22:00:00Z",
 "summary": {"repo": "owner/name", "day": "2026-10-07",
             "prs_merged": 4, "prs_merged_by_loop": 4, "additions": 512, "deletions": 120, "files": 18,
             "issues_closed": 3, "issues_opened": 2,
             "runs": 14, "runs_accepted": 12, "agent_hours": 3.4,
             "deliveries": 4, "first_pass": 2, "denials": 1,
             "headline": "...", "causes": [], "lessons": []},
 "issues": [{"repo": "owner/name", "day": "2026-10-07", "number": 227, "title": "...", "url": "...",
             "delivered": true, "prs": [], "runs": [], "extra_runs": 1, "resets": 0, "notices": 0,
             "lead": 410.5, "agent_minutes": 52.0, "retrospectives": [], "note": "..."}],
 "retrospectives": {"errors": [], "in_window": []}}
```

`headline`, `causes`, `lessons` and each issue's `note` come from
`notes.json`, which the reviewing agent writes:

```json
{"headline": "One sentence: what shipped and the biggest lesson.",
 "items": {"227": "One sentence on what cost runs."},
 "causes": [{"cause": "...", "cost": "21 runs", "items": [252], "state": "Fixed by #276"}],
 "lessons": [{"lever": "authority | wording | fewer-instructions | autonomy", "title": "...",
              "change": "...", "where": "file", "cost": "...", "evidence": [248]}]}
```

Minutes are minutes; `lead` is from the item's creation to its merge or
close; `agent_hours` sums run durations and is not elapsed time; `first_pass`
counts deliveries where no role ran twice. Keep these definitions when a
producer derives charts from the records.
