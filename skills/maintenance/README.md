# Maintenance

Repository maintenance skills, independent of a delivery loop or release process. Plugin: `maintenance`.

- [find-dead-code](find-dead-code/SKILL.md): Find dead Python code with production and test callers kept separate, dynamic entry points and exports checked, and bounded removal recommendations in a report; optional Vulture and Pyan3 analysis, no source or tracker changes.
- [backlog-grooming](backlog-grooming/SKILL.md): Review repository, milestone or project issues for unnecessary work, duplication and scope reductions, grounded in current deliveries and available product intent; produce an actionable decision report, grouped by milestone when most issues have one.
- [ci-health](ci-health/SKILL.md): Track CI on main from GitHub Actions for any repository: median wall time with its spread and P95, the test count, optional coverage and the test-to-code ratio, the changes that made CI slower or faster, and the top three actions that would cut the wait; stores each day in the repository's own Uberblick document when the MCP tools or `ub` are there.
