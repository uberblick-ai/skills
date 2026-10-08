# Changelog

## Unreleased

- Add `ub-agents-deliver-report` under `skills/ub-agents/`, the `delivery-review` skill moved out of uberblick-2 and ub-agents; one script now serves both role setups. Compared with the source copies: the window is a calendar day in local time instead of the last 24 hours, the page is defined in `references/report.md`, `render` opens the report in the default browser and writes a `report.json` record shaped for a document-owned dataset, and the slides are gone. Skills under `skills/` install with `npx skills@latest add uberblick-ai/skills`.
- Remove the `/uberblick` plugin and its marketplace manifest; the last version that carried it is the commit before this change.

## v1.0.0 — 2026-03-07

Initial public release.

- `/uberblick` skill for Claude Code with marketplace registration
- Role-agent files: `prd-critic`, `rfc-architect`, `implementation-reviewer`, `docs-integrity-checker`
- Codex skill (`SKILL.md` + `openai.yaml`) for manual install
