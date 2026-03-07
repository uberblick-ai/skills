# docs-integrity-checker

Use this role when `workflow_hints.active_role == "docs-integrity-checker"`.

## Mission

Finalize documentation integrity checks before completion transitions.

## Checklist

- perform `page_sync_handoff` for impacted pages
- perform `docs_drift_audit` over the declared scope
- choose `acknowledged` or `deferred` for each check
- include `note` when status is `deferred`

## Output Contract

Return:

- `completion_gate_update` payload
- `handoff_summary`
- `deferred_items` (if any)

`completion_gate_update` must include one or both:

- `page_sync_handoff`
- `docs_drift_audit`

## Handoff

- submit payload via `update_prd_tool` or `update_rfc_tool`.
- retry final status transition only after payload submission.
