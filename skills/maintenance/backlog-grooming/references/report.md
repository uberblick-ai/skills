# Decision report contract

The HTML uses the bundled ledger template. Keep the title “Less work. More
value.” and a short factual goal/scope line. Use a YAGNI framing when useful:
“Review current issues for superseded work, excess scope and engineering effort
without a clear user, technical or maintenance benefit.” Do not add introductory
opinion panels or chat-confirmation banners. Decisions are asked in chat, never
through report controls.

Rows run from the oldest issue to the newest, by `created_at`; items without
it follow in input order. Priority shows on the row but does not reorder it.
Items marked `no_change` that carry a workflow label leave the table for a "No
change required" list below the Milestone load table; without a label they
stay in the table, since they still need one. The list shows id, title,
estimate and milestone, with the summary.

The columns are Issue, Treatment, Est., Loop / blockers (or Blocked by without
a loop), and Finding & evidence. Evidence gets the widest right-hand column and
expands inline. Use words only for Yes / No / Blocked; put a short reason below
No or Blocked. Show explicit non-default priority using its tracker label color
below the issue, alongside workflow labels. Each independently challenged item
has a visible label. Summarize the independent challenge below the table.

Draft items carry a visible Draft label and remain ideas, not queue authorization.
Closed issues disappear unless an open linked PR or a named remaining concern
makes them actionable. Retained closed rows must explain why. All input rows
remain in JSON for traceability. Counts describe visible rows; do not invent
saved hours, tokens or implementation counts. A project spanning repositories
uses qualified issue identities to avoid collisions.

## Input v1

The renderer accepts one JSON object. `assets/example.json` is a runnable fictional
example. Required fields:

- `schema_version`: 1.
- `reviewed_at`: a timestamp including the timezone.
- `scope`: `{kind, label, goal}`. Kind is `repository`, `milestone` or `project`.
  Goal is the short factual scope/intent line. Record repository selectors and
  project/milestone IDs as additional keys when useful.
- `items`: array of issue or draft records as below.

Optional top-level fields:
- `baselines`: `[{repository, revision}]` for the actual code revisions reviewed.
- `challenge_summary`: concise description of independent challenges and changes
  to recommendations; disclose unavailable independence or reused prior results.
- `limitations`: text array including incomplete scope, unavailable corpus,
  unverified runtime behavior, unreadable effort fields or remote-host uncertainty.
- `decisions`: `[{question, answer, source}]`; answer null means pending, never
  approved. Preserve these across refreshes; the renderer does not ask questions.
- `actions`: `[{item, action, outcome, source}]` for authorized writes actually
  attempted, including failures. Keep recommendations separate from these facts.
- `capacity`: `{weights?, cap?, ceiling?, source?}` for milestone load. Weights
  map an estimate (case-insensitive) to a number; numeric estimates count as
  themselves and `none` as 0. Defaults: XS 0, S 1, M 2, L 3, XL 5, cap 25,
  ceiling twice the cap.
- `milestones`: `[{id, title, url?, delivered_weight?, other_open_weight?,
  bounded?, new?, basis?}]`. `delivered_weight` is the weight already shipped,
  `other_open_weight` that of open issues not among the items. `bounded` is the
  reason the milestone is one bounded heavy step; `new` marks a proposed
  milestone not yet created; `basis` says how the weights were measured.

With `milestones`, the report adds a Milestone load table below the decisions:
weight now and after the proposed placements, and a status. Within cap; Bounded
exception when `bounded` is set and the weight stays within the ceiling;
otherwise Overloaded, and the count line says how many. Open items in a
closing treatment leave their milestone. Estimates the scale does not know are
counted as unknown, never guessed.

Each item requires:

| Field | Meaning |
| --- | --- |
| `id`, `title` | Qualified identity and title; draft items may use a project-item ID |
| `state` | `open`, `closed`, or `draft` |
| `treatment` | `keep`, `narrow`, `combine`, `defer`, `close delivered`, `close unnecessary`, `track only` |
| `summary` | Actionable recommendation or pending scope choice, one short paragraph |
| `effort` | `{estimate, basis, previous?}`; use the repository scale or a disclosed XS/S/M/L/XL assessment; `unknown` and `none` are valid |
| `evidence` | Nonempty array of `{text, url?}` pointing to actual code, deliveries, corpus or decisions; distinguish claims from observations |
| `challenge` | `{status, summary?}`; status `completed`, `not-needed`, `pending`, or `unavailable`; summary required except for not-needed |

Optional per-item fields:
- `created_at`: when the issue was opened, a timestamp with timezone; sets
  the order.
- `no_change`: true for an open item kept as it is, in its current milestone,
  with nothing to decide. Only valid with treatment `keep`, without a move in
  `placement` and without a pending challenge. Listed apart only when the item
  has `workflow_labels`.
- `url`: absolute HTTP(S) tracker URL when one exists. Do not invent links for
  drafts, offline backlogs or tracker items without a permalink.
- `workflow_labels`: string array. Do not repeat priority here.
- `priority`: `{name, rank, color?, is_default?}`. Rank is numeric, lower
  is more urgent; use the repository's ranking, normalizing its default to 2. `color` is the tracker's six-digit hex color without `#`, never a
  guessed semantic color. Set `is_default` only from the repository policy or an
  explicit display preference. Medium is hidden where it is the established
  default, not because of its spelling; an unknown priority is not a default.
- `blockers`: `[{id, state, source, url?}]`; source identifies native or proposed
  dependency. Only open blockers display in the compact column; explain closed
  prerequisites and mere overlap in evidence if useful.
- `loop`: null when not applicable, otherwise
  `{state, reason, short_reason?, checked_at, config_source}`. States are `yes`,
  `no`, `blocked`, `unknown`. `short_reason` is required for no/blocked/unknown;
  examples: “No preparation label”, “Closed”, “Waiting for #42”. Config source
  should include the checkout/host and revision actually inspected. The reason
  gives the evidence and practical limitation of that assessment.
- `open_prs`: `[{id, url}]`, verified currently open. Keeps a closed issue visible.
- `highlight_reason`: another specific reason a closed issue warrants attention.
- `applied_action`: short verified outcome displayed in evidence, not a proposal.
- `placement`: `{current?, proposed?}` milestone ids from `milestones`. A
  missing `proposed` keeps the current milestone; `null` takes the item out.

All text is escaped, URLs must be HTTP(S), and priority colors are validated.
Unknown additional JSON fields are preserved so collection metadata and human
answers survive rerendering. The renderer does not fetch evidence or decide if
it is sufficient; the reviewing agent owns that assessment. No remote resources
are loaded by the page. Rendering replaces only `report.html` and `report.json`
in the specified output directory; keep distinct runs in separate directories
or deliberately refresh the same run.
