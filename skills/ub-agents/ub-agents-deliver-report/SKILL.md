---
name: ub-agents-deliver-report
description: >-
  Review one day of ub-agents loop deliveries in a GitHub repository when a
  maintainer asks: what shipped, how many runs each item took, what its
  retrospectives said, and the few changes that would have saved runs.
  Produces a report and slides. Do not use for a loop role, a PR review or
  a merge gate.
license: MIT
compatibility: Requires python3 and an authenticated GitHub CLI (gh); reads only
metadata:
  author: uberblick-ai
  version: "1.0"
---

# Deliver report

The loop should move work forward alone and ask a person only for a real
decision. This review shows how close one day came. It only reads GitHub.

`scripts/review.py` lives next to this file; call it by its path inside this
skill's directory. `REPO` is the `OWNER/NAME` of the repository the loop runs
on, `DIR` a scratch directory outside the repository.

1. Collect:

   ```sh
   python3 scripts/review.py collect --repo REPO > DIR/data.json
   ```

   The window is the last 24 hours; `--since` and `--until` change it.

2. For each delivery with extra runs or a `no report` run, name the cause in one
   sentence from its run summaries, denied commands and retrospectives. Group
   causes by mechanism and count what each cost in runs or hours waited. Say
   when `main` or an open issue already covers one. A retrospective is a claim;
   count it only where the records agree.

3. Propose at most four changes, each giving clearer authority, better wording,
   fewer instructions or more autonomy. Quote any line you would change. Never
   add a role, label, gate, review round or checklist, and prefer deleting text
   or moving a step into config or tooling over adding prose.

4. Write `DIR/notes.json` and render:

   ```json
   {"headline": "One sentence: what shipped and the biggest lesson.",
    "items": {"227": "One sentence on what cost runs."},
    "causes": [{"cause": "...", "cost": "21 runs", "items": [252], "state": "Fixed by #276"}],
    "lessons": [{"lever": "authority | wording | fewer-instructions | autonomy", "title": "...",
                 "change": "...", "where": "file", "cost": "...", "evidence": [248]}]}
   ```

   ```sh
   python3 scripts/review.py render DIR/data.json DIR/notes.json DIR
   ```

5. Publish `report.html` and `slides.html` where the session can, otherwise give
   their paths, and reply with the headline and one line per change. The pages
   may be shared: keep credentials, local paths and hostnames out of the notes.
