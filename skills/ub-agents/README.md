# UB Agents

Skills for repositories that run the [ub-agents](https://agents.uberblick.ai)
loop: reading its records on GitHub, judging how the loop did, and tuning the
instructions it runs on.

- **[ub-agents-deliver-report](./ub-agents-deliver-report/SKILL.md)**: Report one calendar day of loop deliveries: how many the loop delivered on its own, which runs were wasted, where a person stepped in, the causes and the few changes that would have saved runs. Opens an HTML report in your browser and leaves a JSON record of the day. Needs only `python3` and an authenticated `gh`; with the Uberblick MCP server it also stores the day in an Uberblick document's data.
