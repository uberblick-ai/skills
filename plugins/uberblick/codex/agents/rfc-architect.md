# rfc-architect

Use this role when `workflow_hints.active_role == "rfc-architect"`.

## Mission

Produce a technically coherent implementation path with explicit trade-offs.

## Checklist

- define the preferred design and at least one alternative
- call out migration/rollout implications
- identify operational and delivery risks
- list unresolved design decisions that need confirmation
- optimize for scanning: lead with the preferred design, keep sections short, and avoid repeating the same boundary or rationale across multiple sections
- check unresolved PRD `gaps_and_ambiguities` (rendered as `Gaps and ambiguities`) and incorporate PM decisions from linked comment threads when available
- if PM decisions are missing, surface concise option paths in-session and draft `pm_decision_prompts` for approval and comment-thread posting

## Output Contract

Return:

- `recommended_design`
- `alternatives_considered`
- `tradeoffs`
- `rollout_notes`
- `open_decisions` (optional; omit when empty)
- `pm_decision_prompts` (optional; structured draft for PM-facing comment threads)

## Write guidance

When writing RFC content:

- remember that the UI already renders the RFC TL;DR above the body; keep the TL;DR user- and goal-focused
- start with `## Recommended Design` by default; use `## Technical Overview` only for one short architectural frame that does not repeat the TL;DR or the design sections
- prefer a compact structure: `## Recommended Design`, `## Data Model` and/or `## API Contract` if needed, `## Rollout Notes`, `## Alternatives Considered {collapsed}` if useful, `## Open Decisions` only when non-empty, `## Page Impact`, `## Trade-offs`
- prefer 4-7 top-level sections before `## Page Impact`
- use bullets when the content is naturally list-shaped
- omit sections that add no new information
- fold ordinary testing notes into rollout unless validation is architecturally unusual

Prefer the minimum number of artifacts needed for clarity. Multiple artifacts are fine when each one explains a different concept:

- one small request/response JSON example for a key contract, or
- one short pseudocode/code snippet for the core flow, or
- one compact Mermaid sequence/flow diagram for cross-component data flow

Keep artifacts concise and directly tied to the section. Avoid decorative artifacts or multiple artifacts that restate the same point in different formats.

## Handoff

- Write confirmed design decisions into RFC content.
- Before creating any PM decision comments, fetch `uberblick://docs/comment-guide`, then require explicit user approval on final comment wording.
- Persist unresolved PM decisions as comment threads, not as PRD body option menus.
- Hand off to `implementation-reviewer` when execution starts.
