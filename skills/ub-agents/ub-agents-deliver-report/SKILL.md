---
name: ub-agents-deliver-report
description: >-
  Report one calendar day of ub-agents loop deliveries in a GitHub repository
  when a maintainer asks: what shipped, how many runs each item took, what
  its retrospectives said, and the few changes that would have saved runs.
  Writes an HTML report, opens it in the browser, and leaves a JSON record
  of the day. Do not use for a loop role, a PR review or a merge gate.
license: MIT
compatibility: Requires python3 and an authenticated GitHub CLI (gh); reads only
metadata:
  author: uberblick-ai
  version: "1.0"
---

# Deliver report

The loop should move work forward alone and ask a person only for a real
decision. This report shows how close one day came. It only reads GitHub.

`scripts/review.py` lives next to this file; call it by its path inside this
skill's directory. `REPO` is the `OWNER/NAME` of the repository the loop runs
on, `DIR` a scratch directory outside the repository. The page and the
records it produces are defined in [references/report.md](references/report.md).

1. Collect:

   ```sh
   python3 scripts/review.py collect --repo REPO > DIR/data.json
   ```

   The day is a calendar day in local time, midnight to midnight; the default
   is yesterday, `--day 2026-10-07` picks another.

2. For each delivery with extra runs or a `no report` run, name the cause in one
   sentence from its run summaries, denied commands and retrospectives. Group
   causes by mechanism and count what each cost in runs or hours waited. Say
   when `main` or an open issue already covers one. A retrospective is a claim;
   count it only where the records agree.

3. Propose at most four changes, each giving clearer authority, better wording,
   fewer instructions or more autonomy. Quote any line you would change. Never
   add a role, label, gate, review round or checklist, and prefer deleting text
   or moving a step into config or tooling over adding prose.

4. Write `DIR/notes.json` in the shape `references/report.md` gives (headline,
   one note per item, causes, lessons) and render:

   ```sh
   python3 scripts/review.py render DIR/data.json DIR/notes.json DIR
   ```

   This writes `DIR/report.html` and `DIR/report.json` and opens the page in
   the default browser. Pass `--no-open` where there is no browser, such as
   a remote session, and give the path or publish the page instead.

5. Reply with the headline and one line per change. The page may be shared:
   keep credentials, local paths and hostnames out of the notes.
