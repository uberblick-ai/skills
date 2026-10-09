# Changelog

## Unreleased

- Add `ub-agents-deliver-report` under `skills/ub-agents/`, the `delivery-review` skill moved out of uberblick-2 and ub-agents; one script now serves both role setups. Compared with the source copies: the window is a calendar day in local time instead of the last 24 hours, the page is defined in `references/report.md`, `render` opens the report in the default browser, and the slides are gone. It measures the KPIs the loop is steered by (autonomous deliveries, wasted runs, human stops and the wait for them, cycle without that wait, run time, runs with permission denials), classifies runs from each role's outcomes and triggers in `ub-agents.yaml`, names findings from a cause registry with a fixed class list so recurrence is visible, groups the day's retrospectives by cause, and `records` turns a day into an `update_data` batch for an Uberblick document's `days`, `items`, `findings`, `causes`, `lessons` and `changes`. Recent days is a data-backed table block in that document, and `document` renders its top five open actions and a short changelog of the latest changes; a lesson leaves the actions once an issue or PR addresses it. The document is optional: the skill updates it when it exists, offers to create it (`create` writes the `create_doc` arguments) when Uberblick is available but no document holds the data, and skips it when Uberblick is not available. Skills under `skills/` install with `npx skills@latest add uberblick-ai/skills`.
- Remove the `/uberblick` plugin and its marketplace manifest; the last version that carried it is the commit before this change.

## v1.0.0 — 2026-03-07

Initial public release.

- `/uberblick` skill for Claude Code with marketplace registration
- Role-agent files: `prd-critic`, `rfc-architect`, `implementation-reviewer`, `docs-integrity-checker`
- Codex skill (`SKILL.md` + `openai.yaml`) for manual install
