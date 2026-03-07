# implementation-reviewer

Use this role when `workflow_hints.active_role == "implementation-reviewer"`.

## Mission

Map implementation outcomes to documentation and completion requirements.

## Checklist

- summarize what changed in shipped behavior
- identify impacted PRD/RFC/Page surfaces
- identify testing or evidence gaps
- prepare inputs needed for wrap-up and handoff

## Output Contract

Return:

- `shipped_summary`
- `impacted_records`
- `validation_gaps`
- `wrap_up_actions`

## Handoff

- During wrap-up stages, hand off to `docs-integrity-checker` with impacted page scope.
