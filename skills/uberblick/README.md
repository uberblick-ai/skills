# Uberblick

Skills for setting up and keeping an [Uberblick](https://github.com/uberblick-ai/uberblick-2)
corpus: the product intent, decision records and sidebar a team and its agents
share. Plugin: `uberblick`.

- **[uberblick-intake](./uberblick-intake/SKILL.md)**: Move a repository's knowledge into Uberblick. Sorts every Markdown file into product pages, Markdown that stays next to the code, or skipped; suggests the repository's tags; finds decision records in the ADRs and the git history; draws flows and screens with ablauf and wireframes; follows the e2e tests in the pages' scenarios; and prepares the sidebar. Shows the plan on one review page and writes it once approved. Needs `python3`, `git` and Node.js; writing needs the Uberblick MCP tools or `ub`.
