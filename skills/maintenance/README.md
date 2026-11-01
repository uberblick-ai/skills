# Maintenance

Repository maintenance skills, independent of a delivery loop or release process. Plugin: `maintenance`.

- [python-cleanup](python-cleanup/SKILL.md): Identify dead Python code with caller evidence and a pre-execution report; recommend one area at a time, execute authorized cleanup and confirm meaningful test removals while allowing verified minor leftovers.
- [backlog-grooming](backlog-grooming/SKILL.md): Review repository, milestone or project issues for unnecessary work, duplication and scope reductions, grounded in current deliveries and available product intent; produce an actionable decision report, grouped by milestone when most issues have one.
- [ci-health](ci-health/SKILL.md): Track CI on main from GitHub Actions for any repository: median wall time with its spread and P95, the test count, optional coverage and the test-to-code ratio, the changes that made CI slower or faster, and the top three actions that would cut the wait; stores each day in the repository's own Uberblick document when the MCP tools or `ub` are there.
