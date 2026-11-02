---
name: ub-agents-deliver-report
description: >-
  Report a calendar day of ub-agents loop deliveries in a GitHub repository:
  how many items the loop delivered on its own, which runs were wasted, where
  a person had to step in, the causes behind them and the few changes that
  would have saved runs. Use for "how did the loop do yesterday?", "run the
  deliver report for 2026-10-07" or "why did the preparer keep retrying last
  Tuesday?". Writes an HTML report and a JSON record of the day and, when an
  Uberblick MCP server is connected, stores every day missing since the last
  one in the project's delivery report document. Not for a loop role, a PR
  review or a merge gate.
license: MIT
compatibility: >-
  Requires python3 and an authenticated GitHub CLI (gh); reads GitHub only.
  Storing the days needs an Uberblick MCP server; without one the skill
  writes the page only.
metadata:
  author: uberblick-ai
  version: "1.13"
---

# Deliver report

The loop should move work forward alone and ask a person only for a real
decision. This report measures how close a day came, names the causes, and
keeps both over time, so a fix that holds and a cause that returns both show.

`scripts/review.py` is next to this file. `REPO` is the `OWNER/NAME` the loop
runs on, `DIR` a scratch directory outside the repository.
[references/report.md](references/report.md) defines the KPIs, cause classes,
notes, page and records.

1. **Find the days.** With an Uberblick MCP server connected, whatever its
   name (load its tools first; with several servers, search each), find the
   "Delivery report" document holding `days`, `causes` and `lessons`: `DOC`.
   Read those three with `get_data`, save `days` as `DIR/days.json`, and run
   `python3 scripts/review.py missing DIR/days.json`. It lists the days to
   report, oldest first, or yesterday when none is missing.
   - No `DOC`: ask once whether to create it, and carry on meanwhile; a no
     means the page only.
   - No server: the page is the whole result. Skip steps 6 and 7, say so in
     the reply, and mention `ub mcp install` when `ub` is on the PATH.
   - Without `DOC`, or when the maintainer names a day, report one day: the
     one named, or yesterday.

2. **Collect.** Steps 2 to 6 run once per day, oldest first, each day
   adding its causes and lessons to the registry you read in step 1:

   ```sh
   mkdir -p DIR/DAY
   python3 scripts/review.py collect --repo REPO --day DAY > DIR/DAY/data.json
   python3 scripts/review.py digest DIR/DAY/data.json
   ```

   Days are UTC. Work from the digest; open `data.json` only for a field it
   leaves out.

3. **Name causes** for each loop delivery that was not autonomous, each
   wasted run and each send-back, from the digest. Look further on GitHub
   only where it leaves a cause open. Reuse a cause id when the mechanism
   matches; a new id names the mechanism, not the incident. Count the runs
   each cause cost. Mark it fixed when `main` or ub-agents already fixed it,
   and add each change that landed on the day to `changes` with why. A
   retrospective is a claim: count it only where the records agree, and group
   the day's posts by cause.

4. **Propose lessons**, at most four, each giving clearer authority, better
   wording, fewer instructions or more autonomy. Quote any line you would
   change. Never add a role, label, gate, review round or checklist; prefer
   deleting text or moving a step into config or tooling. Reuse registry
   ids, and write `cost` with dates ("5 runs on 11 October"). For each lesson,
   search the repositories' issues and PRs for one already making the change,
   so nobody builds it twice: open ones, drafts included, and ones merged or
   closed in the last 30 days (`gh pr list` and `gh issue list` with
   `--state all --search "WORDS updated:>=DAY"`); only one that makes this
   change counts. `tracked` with `addressed_by` while it is open, `applied`
   once it merged. One closed unmerged keeps the lesson only if its reason
   for closing does not rule the change out; name it and why in `change`.
   Keep `addressed_as` from the registry. `actions` ranks up to five
   still-proposed lessons from the last 14 days, most runs saved first.

5. **Render.** Write `DIR/DAY/notes.json` as report.md shows, then:

   ```sh
   python3 scripts/review.py render DIR/DAY/data.json DIR/DAY/notes.json DIR/DAY --days DIR/days.json
   ```

   During a backfill, add `--days DIR/EARLIER/report.json` for each day
   already reported. Pass `--no-open` for every day but the newest, and
   where there is no browser; then publish the page or give its path.

6. **Store**, unless the maintainer asked for the page only. For a new
   document, pass the `title`, `description` and `blocks` from
   `python3 scripts/review.py create DIR/DAY/report.json` to `create_doc`;
   the result is `DOC`. Then pass the array from
   `python3 scripts/review.py records DIR/DAY/report.json` as `operations`
   to `update_data`, and check with `get_data` that every collection is
   valid. Add `--schemas` to `records` for a new document, a missing
   collection or a record a stored schema refuses. Delete a finding that no
   longer applies with `deleteRecords`.

7. **Update the document** once, after the newest day; a document created
   in step 6 is already current. Write `DIR/dataset.json` as
   `{"lessons": [...]}`, with `{id, value}` from the registry for each lesson
   the newest `actions` name and each `tracked` one from the last 14 days
   that the notes leave out. After a backfill, write `lessons` and `changes`
   as `get_data` returns them now and pass the first day reported as
   `--since`.

   ```sh
   python3 scripts/review.py document DIR/dataset.json DIR/DAY/report.json --doc DOC [--since FIRST] > DIR/sections.json
   ```

   Read `DOC` with `get_doc` and change one block at a time, never a whole
   section:

   - **Recommended Actions** (rename a heading that still reads "Actions"):
     delete a card whose title is not in `cards`; edit a `changed` card in
     place with `edit_block` so its comments stay, but delete and reinsert a
     `struck` one; insert a missing card after the one before it in `cards`,
     or after the intro.
   - **Changelog**: insert the first `changelog_new` items after the heading
     and delete those past the fifth.
   - Without a chart titled `context_chart.title`, insert
     `context_chart.block` after the last chart before "Recent days".

   If Uberblick refuses a card with `invalid_card`, run `create` or
   `document` again with `--no-button`. If it refuses the context chart,
   leave it out and say so.

8. **Reply** with the newest day's headline, the KPIs against their
   targets, one line per change and where the days were stored, plus one
   line per earlier day filled in. With your own figures, leaving out empty
   lines:

   ```text
   14 October: 6 of 8 deliveries went through alone; the preparer asked twice about scope the corpus already settles.
   Autonomous 75% (target 75% or more), wasted runs 12% (under 10%), runs with denials 4% (under 10%).
   Context: median peak 12% of the window, largest 56% (#2195 implementer, Codex), none compacted.
   Changes: acme/app#2201, the preparer reads the corpus before asking, ends 3 wasted runs a day.
   Stored 12 to 14 October in the Delivery report.
   12 October: every delivery alone. Autonomous 100%, wasted 0%.
   13 October: one stop on a migration question. Autonomous 80%, wasted 5%.
   ```

   A day without loop runs gets one line saying so. Keep credentials, local
   paths and hostnames out of the notes.
