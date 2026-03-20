---
name: uberblick
description: Run $uberblick as a guided MCP workflow using workflow_hints and role-agent playbooks for PRDs, RFCs, and implementation review
---

You are starting an Uberblick working session. Follow these steps exactly:

## Step 0 — Check for a direct page ID
If `$ARGUMENTS` looks like a UUID (e.g. `019c93b0-72eb-71a1-8cdf-c8c6803a9056`), skip Steps 1–3 and go directly to Step 4, using that UUID as the page `id`.

## Step 0.5 — Route bug intake directly when appropriate
If the user's request, or a newly discovered issue during the session, is primarily about broken behavior now, a regression, or triage intake rather than planning/execution work:

1. Fetch `uberblick://docs/bug-guide`.
2. Use `list_bugs` to check for existing similar bugs.
3. Use `create_bug_tool` when a new bug is the right artifact.
4. If bug filing fully resolves the request, stop. Otherwise continue and link the bug from the related PRD/RFC instead of turning the planning record into a bug report.

## Step 1 — List workspaces
Call the `list_workspaces` MCP tool to get all workspaces.

## Step 2 — Fetch active planning records
For each workspace returned:

1. Call `list_prds` with that `workspace_id`.
2. Call `list_rfcs` with that `workspace_id`.

Collect all records where `parent_status` is `"to_do"` or `"in_progress"` (exclude `"complete"`).

If `$ARGUMENTS` was provided (and is not a UUID), filter further to records whose title contains the argument (case-insensitive).

If no active records exist, tell the user and stop.

## Step 3 — Let the user pick
Present the records as options.
Format each option as: `[type][status_name] Title` (e.g. `[PRD][Draft] Auth Revamp`).
Group by workspace name if there are multiple workspaces.
Limit to 4 options per question; if more exist, ask the user to provide a keyword to narrow down.

## Step 4 — Load context and workflow contracts
Once the user picks a PRD or RFC:

1. Call `get_page` with the selected record `id`.
2. Call `get_resource` for:
   - `uberblick://docs/workflow`
   - `uberblick://docs/workflow-roles`
3. Call `get_linked_pages` with `id: "prd:<uuid>"` or `id: "rfc:<uuid>"` depending on record type.
4. For each linked PRD/RFC, call `get_page` to load context.
5. Read `workflow_hints` from the selected record response and store:
   - `stage`
   - `role_sequence`
   - `active_role` (present for RFCs and in-progress PRDs)
   - `active_role_instruction` (present when `active_role` is set)
   - `next_role` (present for Draft PRDs in `to_do` status — offer-only, do not auto-run)
   - `confirmation_required`
   - `pending_completion_checks`

## Step 5 — Brief the user
Present a concise briefing:
- **Selected record title/type/status**
- **Current stage** from `workflow_hints.stage`
- **Active role** from `workflow_hints.active_role` (or available role from `workflow_hints.next_role.role` if `active_role` is absent)
- **Linked records** (titles + status)
- **Pending completion checks** from `workflow_hints.pending_completion_checks`

## Step 6 — Run the active role
If `workflow_hints.next_role` is present and `workflow_hints.active_role` is absent (Draft PRD):
- Inform the user that `next_role.role` is available (e.g. "prd-critic is available — want me to run a critique pass?").
- Do not auto-run the role. Wait for user confirmation.
- If the user confirms, run the role using `next_role.role` and `next_role.description` as the instruction.

Otherwise, map `workflow_hints.active_role` to a local role definition file:

- `prd-critic` -> `./agents/prd-critic.md`
- `rfc-architect` -> `./agents/rfc-architect.md`
- `implementation-reviewer` -> `./agents/implementation-reviewer.md`
- `docs-integrity-checker` -> `./agents/docs-integrity-checker.md`

Path resolution rule: resolve `./agents/...` relative to this `SKILL.md` file's directory (the skill folder), not the repository root.

Execute the active role using:

1. the selected record content,
2. linked PRD/RFC context,
3. `workflow_hints.active_role_instruction`,
4. the role file's output contract.
5. Enforce artifact boundary:
   - PRD findings must stay at product-requirement level.
   - Technical/design specifics must be output only as `RFC Remarks` (brief reminders). Keep this high-level only: technical and implementation details do not belong in the PRD.
6. Enforce decision-source boundary:
   - Keep unresolved product decisions in `gaps_and_ambiguities` only (single source of truth).
   - In persisted PRD content, render this section header as `Gaps and ambiguities` (human-readable). The underscore form is identifier-only.
   - Do not create a second action list that repeats the same items with different wording.
   - PM/owner decisions should be captured as comments/discussion on those gaps.
7. If active role is `rfc-architect` and unresolved PRD decisions remain:
   - present option paths directly in the live LLM session for PM selection,
   - do not write those option menus into PRD body content.

If the role file is missing, continue using `workflow_hints.active_role_instruction` plus `uberblick://docs/workflow-roles`.

## Step 7 — Write outputs through MCP tools
Never treat local role output as final state until it is written through MCP.

- Use `update_prd_tool` for PRD records.
- Use `update_rfc_tool` for RFC records.

When relevant, include:

- content updates,
- status updates,
- `completion_gate_update` for `page_sync_handoff` / `docs_drift_audit`.

Follow the active role's agent file output contract for content structure and decision-handling rules.

Page Impact rule for PRD writes:

- If touching `## Page Impact`, keep every entry in validator-compatible checklist form from `uberblick://docs/markdown-spec`.
- Actionable entries must contain `[Title](page:UUID)` or `uberblick://docs/...`; if none apply, use exactly one checked no-update line.
- Before setting completion checks to `acknowledged`, ensure every actionable entry is checked.

Active comment-anchor migration rule:

- When rewriting/removing text that contains active `{comment:thread_uuid}...{/comment:thread_uuid}` markers, reposition each marker onto the new decision/result sentence in the updated content.
- Never drop an active marker during `update_prd_tool` / `update_rfc_tool` writes.
- If no equivalent sentence exists, add a short `Decision:` (or `Resolution:`) line and attach the marker there before submitting.

After each write, do not auto-refetch with `get_page`. Re-fetch only when required:

- verifying final status / completion-gate outcomes,
- recovering from ambiguous update errors, or
- reading fields not returned by the update response.

## Step 8 — Handle blocked transitions
If a status move to complete is blocked:

1. parse `missing_checks` and `required_sequence` from the error payload,
2. run the missing role/workflow action directly,
3. retry with one `update_prd_tool` / `update_rfc_tool` call that includes:
   - target `status_id`,
   - `completion_gate_update` for all resolved checks,
4. fetch `guidance_resources` only if the payload is unclear/contradictory,
5. verify via `get_page` only for touched records involved in the retry.

Do not set `acknowledged` before the corresponding action is complete.
Do not move one linked PRD/RFC to `Done` while another linked record is still blocked.

## Step 9 — Start implementation work (developer session)
When coding is in scope:

1. ALWAYS work in a branch.
2. Follow repository instructions (`docs/instructions/`).
3. Before the first code edit, enforce execution-entry status:
   - if current `parent_status` is not `"in_progress"`:
     - call `list_statuses` with `parent: "in_progress"`,
     - choose the most appropriate in-progress status for execution start (prefer exact name `In Progress`; otherwise the closest equivalent),
     - call `update_prd_tool` or `update_rfc_tool` with that `status_id`.
4. If status transition fails, stop implementation work and report the blocker; do not write code changes until resolved.
5. Keep linked PRD/RFC records intentionally in sync.

## Step 10 — Open PR Early (Draft) and Push Incrementally

Do this shortly after the first meaningful implementation commit.

1. Push the branch and open a **draft** PR (title from PRD; body includes PRD UUID + short summary).
2. Keep pushing incremental commits throughout implementation.
3. Keep the PR in draft until implementation and validation are complete.
4. If draft PR creation fails, report the blocker and retry after the next push.

## Step 11 — Wrap up: status, review handoff, and docs

Do this when implementation is complete.

1. Determine intended handoff status:
   - if PR is open: use the highest `in_progress` status (typically `In Review`),
   - if PR is merged: use the default complete status (typically `Done`).
2. If PR is draft, mark it ready for review.
3. If PR is open, request Copilot review by adding reviewer `app/github-copilot`. If this fails, note the error and continue.
4. Audit only likely-drift docs:
   - target explicitly touched docs + PRD `Page Impact` targets,
   - fetch those pages in parallel,
   - update only pages with stale facts.
5. Status sync in one pass (parallel where safe):
   - list every touched PRD/RFC,
   - call one `update_prd_tool` / `update_rfc_tool` per record with final `status_id`,
   - when moving to complete, include `completion_gate_update` in that same call,
   - if any status update fails, stop and fix before continuing.
6. Verification gate (required):
   - call `get_page` once per touched PRD/RFC after status updates,
   - verify each record is in intended handoff status,
   - verify linked PRD/RFC statuses are intentionally aligned (no accidental mixed final states).
7. Report a final status summary in the handoff message:
   - `record_id`
   - `record_type` (`prd`/`rfc`)
   - `final_status_name`

## Step 12 — Monitor CI and PR comments

Run this step only while the PR is open. If the PR is already merged, skip to Step 13.

1. Periodically check PR status (`gh pr checks`) and comments (`gh pr view --comments`).
2. If CI is failing, inspect failed logs (`gh run view --log-failed`), fix issues, commit, and push.
3. For PR comments:
   - fix actionable correctness/standards issues and reply on the PR
   - leave purely stylistic/opinion comments for human judgment
4. Continue until CI is green and no actionable comments remain.

## Step 13 — Claude/Codex parity check
Before final signoff, ensure this session did not violate policy parity:

- gate behavior and `completion_gate_update` rules match MCP responses,
- `workflow_hints` stage/role sequence was respected,
- manual web UI status remains authoritative and is not auto-reverted.

Report the final PR URL to the user.
