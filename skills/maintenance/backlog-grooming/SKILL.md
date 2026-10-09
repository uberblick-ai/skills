---
name: backlog-grooming
description: >-
  Groom a repository backlog, milestone or project for an engineering manager
  or product owner: challenge unnecessary work, duplicates, superseded scope and
  unclear value, then produce an actionable evidence report with effort and
  blockers. Use for a daily backlog review or to identify what can be cut to
  deliver a specific outcome sooner. Not an implementation run or release gate.
license: MIT
compatibility: >-
  Requires python3 for the report. Issue, PR and code access are needed for
  evidence; GitHub repositories normally use authenticated gh and git.
  Product corpus and ub-agents integrations are optional. No runtime packages.
metadata:
  author: uberblick-ai
  version: "1.1"
---

# Backlog grooming

Reduce work while preserving clear user value, technical correctness and
maintainability. A small backlog is not itself the goal: keep necessary work,
including safety and data-preservation guarantees. This is an attended,
repeatable daily exercise, not authorization to schedule recurring runs.

Use the scripts by their absolute path inside this installed skill. `DIR` is
a durable task-owned output directory outside the source checkout. Repository
instructions govern authority, trusted inputs and issue mutations.

1. **Set the goal and scope in chat.** Support all repository issues, a
   milestone, or a project, including projects spanning repositories. No
   release or milestone is required. If no scope was supplied, ask what the
   grooming should achieve: general backlog reduction, or delivering a named
   outcome sooner. Resolve the repository/project selector from context or ask
   for it with that goal. With a supplied scope, reuse known intent; ask only
   if the purpose or cut boundary is unclear. Prefer one focused question
   about outcomes and boundaries over a questionnaire about individual issues.

2. **Collect current inputs.** Read [references/review.md](references/review.md)
   for collection, evidence, optional loop integration and application rules.
   Include every open issue in scope regardless of workflow label, priority
   or preparation state. Inspect closed items only for delivered overlap or
   reasons to retain them, such as an open linked PR. Follow pagination and
   disclose inaccessible scope. Fetch the relevant default branches and record
   their revisions. Read trusted discussions, linked deliveries and native
   blockers. When a product corpus exists, discover and read its relevant live
   documents and decisions; code proves implementation, not intended behavior.

3. **Challenge each issue.** Recommend keep, narrow, combine, defer, close
   delivered, close unnecessary, or track only. Ask what observable user,
   technical or maintenance benefit remains, what has already landed, and
   whether a smaller outcome would suffice. Do not repeat implementation
   already delivered or queue tracking parents as independent deliveries.
   Give each issue a tentative estimate for its remaining scope and distinguish
   recorded blockers from proposed prerequisites and mere file overlap.
   Read and use a repository's effort scale when available; disclose unavailable
   fields. Estimates are judgments, not commitments or invented time savings.

4. **Run a bounded independent challenge** on large or controversial items:
   uncertain closures, substantial rewrites, disputed value or boundary changes.
   Ask a separate agent to argue the strongest case against the recommendation
   using the issue, code and available corpus; request its smallest useful
   alternative, evidence and remaining uncertainty. Prefer another runtime
   when available, but do not claim cross-runtime review when it was not used.
   This is a quick adversarial pass, not a full delivery review. Do not repeat
   one on unchanged inputs. Label each challenged row and summarize what the
   challenge changed below the table. If independence is unavailable, mark it
   unavailable rather than presenting self-review as independent evidence.

5. **Resolve material choices in chat.** Present a concise recommendation,
   alternatives and consequences when a conflict changes the outcome or scope.
   Reuse prior decisions; silence is not agreement. Continue independent work
   while waiting, leaving the dependent recommendation explicitly pending.
   Questions belong in chat, not as report controls. Record answers separately
   from findings so a refresh preserves them. Do not weaken an agreed guarantee
   under YAGNI or treat missing evidence as proof of no value.

6. **Render the decision report.** Read
   [references/report.md](references/report.md) and write `DIR/input.json` in
   its format. Use [assets/example.json](assets/example.json) only as a fictional
   format example, never as findings. Then run:

   ```sh
   python3 /path/to/backlog-grooming/scripts/render.py DIR/input.json DIR
   ```

   This writes `report.html` and `report.json` and opens the report. Use
   `--no-open` when the host should open it or no browser is available. The
   renderer writes only these local report files and never mutates issues.
   The title is **Less work. More value.** Keep the opening factual and short;
   the table carries the decisions. No introductory opinion panels or
   “confirmed in chat” banner. Verify the rendered page and evidence expansion
   at desktop and tablet widths. Return its link and the few material findings.

7. **Apply only authorized actions.** A dry run changes no issues, labels,
   corpus or project fields. When the user requests particular changes,
   refresh those inputs and apply the concrete authorized scope without asking
   again. Transfer retained scope into a destination before closing combined
   issues as superseded; never call them delivered. Priority alone is not a
   preparation trigger. Refresh loop eligibility and the report after writes.
   Omit closed rows unless an open PR or a named remaining concern warrants
   highlighting them. Do not apply other report recommendations implicitly.

8. **Refresh incrementally.** Compare current scope, discussions, source
   revisions, blockers and deliveries with the previous report. Reuse unchanged
   evidence and human answers, refresh affected judgments and disclose reused
   challenge results. Keep recommendations, decisions and applied actions
   distinct. If the goal changes, reassess relevance, not just issue states.
