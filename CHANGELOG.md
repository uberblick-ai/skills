# Changelog

## Unreleased

- Add the website at skills.uberblick.ai: `site/build.py` builds an overview and one page per skill from the `SKILL.md` files, group READMEs and marketplace, plus `skills.md`, `llms.txt`, a sitemap and a 404 page. Optional `site/content/skills/<name>.json` adds example asks, steps and report screenshots. CI builds the site on every change.
- Add `backlog-grooming` 1.1 in the new `maintenance` group: repository, milestone and project review, bounded independent challenges, chat decisions, optional ub-agents eligibility, and a reusable HTML/JSON decision report. Independent portability review removed the medium-as-default assumption and added visibly identified drafts without required permalinks.

- Add `ub-agents-deliver-report` under `skills/ub-agents/`, the `delivery-review` skill moved out of uberblick-2 and ub-agents; one script now serves both role setups. Compared with the source copies: the window is a calendar day in local time instead of the last 24 hours, the page is defined in `references/report.md`, `render` opens the report in the default browser, and the slides are gone. It measures the KPIs the loop is steered by (autonomous deliveries, wasted runs, human stops and the wait for them, cycle without that wait, run time, runs with permission denials), classifies runs from each role's outcomes and triggers in `ub-agents.yaml`, names findings from a cause registry with a fixed class list so recurrence is visible, groups the day's retrospectives by cause, and `records` turns a day into an `update_data` batch for an Uberblick document's `days`, `items`, `findings`, `causes`, `lessons` and `changes`. Recent days is a data-backed table block in that document, and `document` renders its top five open actions and a short changelog of the latest changes; a lesson leaves the actions once an issue or PR addresses it, or after 14 days without new evidence. Item detail is kept compact, one record per day, for 14 days; daily figures and findings stay for long-term trends. The document is optional: the skill updates it when it exists, offers to create it (`create` writes the `create_doc` arguments) when Uberblick is available but no document holds the data, and skips it when Uberblick is not available. Collection reads comments only for items opened before the day ended that have any, and PR sizes only for PRs merged that day, so a day costs about 140 GitHub API calls and backfilling an older day no longer pays for everything touched since. Skills under `skills/` install with `npx skills@latest add uberblick-ai/skills`.
- Remove the `/uberblick` plugin; the last version that carried it is the commit before this change. The `uberblick-ai` marketplace stays and now lists one plugin per skill group, `ub-agents` first, pointing at the skills in place; `scripts/check_marketplace.py` keeps it in step with `skills/`.

## v1.0.0 — 2026-03-07

Initial public release.

- `/uberblick` skill for Claude Code with marketplace registration
- Role-agent files: `prd-critic`, `rfc-architect`, `implementation-reviewer`, `docs-integrity-checker`
- Codex skill (`SKILL.md` + `openai.yaml`) for manual install
