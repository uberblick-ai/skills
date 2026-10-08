---
name: ub-agents-deliver-report
description: >-
  Report one calendar day of ub-agents loop deliveries in a GitHub repository
  when a maintainer asks: how many items the loop delivered on its own, which
  runs were wasted, where a person had to step in, the causes behind them and
  the few changes that would have saved runs. Writes an HTML report, opens it
  in the browser, leaves a JSON record of the day and can store the day in an
  Uberblick document's data to track KPIs over time. Do not use for a loop
  role, a PR review or a merge gate.
license: MIT
compatibility: >-
  Requires python3 and an authenticated GitHub CLI (gh); reads GitHub only.
  Storing the day needs the Uberblick MCP server (get_data, update_data).
metadata:
  author: uberblick-ai
  version: "1.0"
---

# Deliver report

The loop should move work forward alone and ask a person only for a real
decision. This report measures how close one day came, names the causes, and
keeps both over time so a fix that holds and a cause that returns are visible.

`scripts/review.py` lives next to this file; call it by its path inside this
skill's directory. `REPO` is the `OWNER/NAME` of the repository the loop runs
on, `DIR` a scratch directory outside the repository. The KPIs, the cause
classes, the page and the records are defined in
[references/report.md](references/report.md).

1. Collect:

   ```sh
   python3 scripts/review.py collect --repo REPO > DIR/data.json
   ```

   The day is a calendar day in local time, midnight to midnight; the default
   is yesterday, `--day 2026-10-07` picks another. Only runs that started
   before the day ended count, so a day reads the same whenever it is
   collected.

2. Find the project's delivery dataset: an Uberblick document holding the
   `days`, `items`, `findings`, `causes` and `lessons` collections (search for
   "Delivery Report"); call it `DOC`. With `DOC`, read its `causes` and
   `lessons` with `get_data` before naming anything.

3. For each loop delivery that is not autonomous, each wasted run and each
   reviewer send-back, name the cause from run summaries, denied commands and
   retrospectives. Reuse a cause id when the mechanism matches; create one only
   when none fits, named for the mechanism, not the incident. Count the runs
   each cause cost on this day, and mark it fixed, naming the change, when
   `main` or ub-agents already fixed it. A retrospective is a claim; count it
   only where the records agree.

4. Propose at most four changes, each giving clearer authority, better wording,
   fewer instructions or more autonomy. Quote any line you would change. Never
   add a role, label, gate, review round or checklist, and prefer deleting text
   or moving a step into config or tooling over adding prose. Reuse a lesson id
   the registry already has.

5. Write `DIR/notes.json` in the shape `references/report.md` gives (headline,
   one note per item, findings, lessons) and render:

   ```sh
   python3 scripts/review.py render DIR/data.json DIR/notes.json DIR
   ```

   This checks the notes, writes `DIR/report.html` and `DIR/report.json` and
   opens the page in the default browser. Pass `--no-open` where there is no
   browser, such as a remote session, and give the path or publish the page
   instead.

6. With `DOC`, store the day:

   ```sh
   python3 scripts/review.py records DIR/report.json > DIR/operations.json
   ```

   Pass the file's array as `operations` to `update_data` on `DOC`, then read
   the area summary back with `get_data` and confirm every collection is valid.
   Storing a day again overwrites its records; delete a finding that no
   longer applies with `deleteRecords`.

7. Reply with the headline, the KPIs and one line per change. The page and the
   records may be shared: keep credentials, local paths and hostnames out of
   the notes.
