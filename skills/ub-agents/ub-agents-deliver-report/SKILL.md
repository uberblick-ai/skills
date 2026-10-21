---
name: ub-agents-deliver-report
description: >-
  Report a calendar day of ub-agents loop deliveries in a GitHub repository
  when a maintainer asks: how many items the loop delivered on its own, which
  runs were wasted, where a person had to step in, the causes behind them and
  the few changes that would have saved runs. Writes an HTML report, opens it
  in the browser, leaves a JSON record of the day and, when an Uberblick MCP
  server is connected, stores the day in an Uberblick document's data to track
  KPIs over time, filling in every day missing since the last one stored. Do
  not use for a loop role, a PR review or a merge gate.
license: MIT
compatibility: >-
  Requires python3 and an authenticated GitHub CLI (gh); reads GitHub only.
  Storing the days in an Uberblick document needs an Uberblick MCP server;
  the skill stores them whenever one is connected and otherwise still writes
  the page.
metadata:
  author: uberblick-ai
  version: "1.6"
---

# Deliver report

The loop should move work forward alone and ask a person only for a real
decision. This report measures how close one day came, names the causes, and
keeps both over time so a fix that holds and a cause that returns are visible.
When the stored days stop short of yesterday, it reports each missing day, so
the history has no gaps.

`scripts/review.py` lives next to this file; call it by its path inside this
skill's directory. `REPO` is the `OWNER/NAME` of the repository the loop runs
on, `DIR` a scratch directory outside the repository. The KPIs, the cause
classes, the page and the records are defined in
[references/report.md](references/report.md).

1. Decide where the days will be kept and which days to report. Uberblick
   is available when an Uberblick MCP server is connected, whatever its name,
   such as `uberblick` or `uberblick-agents`. Its tools (`search`, `get_doc`,
   `get_data`, `update_data`, `create_doc`, `insert_block`, `edit_block`,
   `delete_block`) may be listed by name only; load them before using them,
   and with more than one server, search each for the document.
   Without them, the page is the whole result: steps 3 and 4 name causes and
   lessons from this day alone, since there is no registry to reuse; skip
   steps 6 and 7, say so in one line of the reply, and add that
   `ub mcp install` registers the server for next time when `ub` is on the
   PATH. With them, find the project's delivery dataset:
   an Uberblick document holding the `days`, `items`, `findings`, `causes`,
   `lessons` and `changes` collections (search for "Delivery report"); call it
   `DOC`, and read its `causes` and `lessons` with `get_data` before naming
   anything. Step 7 reuses this read. When no such document exists, ask the maintainer once whether to
   create the delivery report document, and carry on with the page while
   waiting: a yes creates `DOC` in step 6, a no skips steps 6 and 7.

   With `DOC`, read its `days` with `get_data` too, save the result as
   `DIR/days.json` and list the days to report:

   ```sh
   python3 scripts/review.py missing DIR/days.json
   ```

   It prints every day after the newest stored one up to yesterday, oldest
   first, so a run fills in each day nobody reported: three days missing
   means three days reported. With nothing missing it prints yesterday, which
   is reported again. Without `DOC`, for a document created in step 6, when
   the maintainer names a day, or when they ask for the page only, report
   one day: the one named, or yesterday.

2. Collect each day, then read its digest:

   ```sh
   mkdir -p DIR/DAY
   python3 scripts/review.py collect --repo REPO --day DAY > DIR/DAY/data.json
   python3 scripts/review.py digest DIR/DAY/data.json
   ```

   The day is a calendar day in UTC, midnight to midnight, whatever the
   machine's time zone; without `--day` it is yesterday. Only runs that started
   before the day ended count, so a day reads the same whenever it is
   collected, and a missed day can be filled in later. The digest gives every run of each item that needs a cause with
   its summary and denials, the evidence the runs leave out (commits pushed
   outside any run, label and state changes by a person, CI runs on its PRs),
   one line per item that went through cleanly, and the day's
   retrospectives. Work from it; open `data.json` only for a field it leaves
   out.

   Steps 2 to 6 run once per day, oldest first, each day in its own
   `DIR/DAY`, so a day reuses the causes and lessons the days before it
   registered. Keep the step 1 read current with what each stored day adds
   rather than reading the registry again. Step 7 runs once, after the
   newest day.

3. For each loop delivery that is not autonomous, each wasted run and each
   reviewer send-back, name the cause from run summaries, the evidence, denied
   commands and retrospectives; look further on GitHub only where the digest
   leaves the cause open. Reuse a cause id when the mechanism matches; create one only
   when none fits, named for the mechanism, not the incident. Count the runs
   each cause cost on this day, and mark it fixed, naming the change, when
   `main` or ub-agents already fixed it; record each such change that landed on
   this day in `changes` with why it was made. A retrospective is a claim;
   count it only where the records agree. Group the day's retrospectives by
   cause, one summary sentence per group.

4. Propose at most four changes, each giving clearer authority, better wording,
   fewer instructions or more autonomy. Quote any line you would change. Never
   add a role, label, gate, review round or checklist, and prefer deleting text
   or moving a step into config or tooling over adding prose. Reuse a lesson id
   the registry already has. Then search the repositories' issues and PRs for
   one that addresses each proposed lesson, new or registered: mark it
   `tracked` with `addressed_by` when an open one does, `applied` when a merged
   one did. Keep `addressed_as` (`implemented` or `planned`) from the registry;
   the session that discussed an action card writes it. Rank up to five still-proposed lessons from the last 14 days,
   most runs saved first, as the day's `actions`; re-propose an older lesson
   when the day shows it again.

5. Write `DIR/DAY/notes.json` in the shape `references/report.md` gives (headline,
   one note per item, findings, lessons, actions, changes, retrospective
   groups) and render:

   ```sh
   python3 scripts/review.py render DIR/DAY/data.json DIR/DAY/notes.json DIR/DAY
   ```

   This checks the notes, writes `DIR/DAY/report.html` and `DIR/DAY/report.json` and
   opens the page in the default browser. Pass `--no-open` for every day but
   the newest, and where there is no
   browser, such as a remote session, and give the path or publish the page
   instead.

6. Store the day, unless the maintainer asked for the page only. When the
   maintainer said yes to a new document:

   ```sh
   python3 scripts/review.py create DIR/DAY/report.json > DIR/create.json
   ```

   Pass the file's `title`, `description` and `blocks` to `create_doc`; the
   document it returns is `DOC`, laid out as `references/report.md` describes
   with this day's actions already in place. If it refuses an action card with
   `invalid_card` (Uberblick 0.4.3 has no card buttons), run `create` again
   with `--no-button`. Then, with `DOC`:

   ```sh
   python3 scripts/review.py records DIR/DAY/report.json > DIR/DAY/operations.json
   ```

   Pass the file's array as `operations` to `update_data` on `DOC`, then read
   the area summary back with `get_data` and confirm every collection is valid.
   The batch leaves the collection schemas out, since `DOC` keeps them and
   checks every record against them. Run `records` with `--schemas` for a
   document created in this step, when the area summary lacks a collection, or
   when `update_data` refuses a record against a stored schema.
   Storing a day again overwrites its records; delete a finding that no
   longer applies with `deleteRecords`.

7. With a `DOC` that existed before this run, bring its Recommended Actions
   and Changelog up to date (a document created in step 6 already carries
   them). Write `DIR/dataset.json` as `{"lessons": [...]}`: the registry
   lessons the newest day's `actions` name and the `tracked` ones from the last 14
   days, those its `notes.json` leaves out, each as `{id, value}` from the step 1
   read. `document` stops if one is missing. After more than one day, read
   `lessons` and `changes` again with `get_data` instead and write both,
   `{"lessons": ..., "changes": ...}`, as returned, so the earlier days'
   lessons and changes show too, and pass the first day reported as `--since`.
   Then:

   ```sh
   python3 scripts/review.py document DIR/dataset.json DIR/DAY/report.json --doc DOC [--since FIRST] > DIR/sections.json
   ```

   Read `DOC` with `get_doc` and change only the blocks that differ, one
   block at a time; never rewrite a whole section. Under "Recommended
   Actions", `cards` lists the cards in order, each with its title and
   whether the days reported changed its lesson, and `actions` holds their blocks
   after the intro paragraph:

   - Delete a card whose title is not in `cards`.
   - Edit a card marked `changed` in place with `edit_block`, passing its
     text and `rev` from `get_doc`, so comments on it stay. A card marked
     `struck` is struck through, which `edit_block` cannot change: delete
     it and insert it again instead.
   - Insert a card that is not in `DOC` yet after the card before it in
     `cards`, or after the intro paragraph.
   - Leave every other card as it is; move one only when it is out of order.

   Under "Changelog", insert the first `changelog_new` items of `changelog`
   after the heading and delete the items past the fifth; when
   `changelog_new` is 0, leave it as it is. A document whose heading still
   reads "Actions" gets it renamed. Each action is a card whose "Discuss in
   Claude Code" button opens a new session with a prompt to discuss the
   change before making it. When that discussion settles on applying it,
   the prompt has the session strike the card through, with the pull
   request or issue as a GitHub pill below, and mark the lesson `tracked`,
   so `document` keeps it that way until the change is done. If Uberblick refuses a card with `invalid_card`
   (0.4.3 has no card buttons), run `document` again with `--no-button`. The
   charts and the Recent days table follow the data by themselves.

8. Reply with the newest day's headline, the KPIs against their targets, one
   line per change, and where the days were stored or why they were not. For
   each earlier day filled in, add one line: the day, its headline and its
   autonomous and wasted share. The page and the
   records may be shared: keep credentials, local paths and hostnames out of
   the notes.
