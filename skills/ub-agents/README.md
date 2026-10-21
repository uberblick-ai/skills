# UB Agents

Skills for repositories that run the [ub-agents](https://agents.uberblick.ai)
loop: reading its records on GitHub, judging how the loop did, answering what
it stops to ask, and tuning the instructions it runs on.

- **[ub-agents-deliver-report](./ub-agents-deliver-report/SKILL.md)**: Report one calendar day of loop deliveries: how many the loop delivered on its own, which runs were wasted, where a person stepped in, the causes and the few changes that would have saved runs. Opens an HTML report in your browser and leaves a JSON record of the day. Needs only `python3` and an authenticated `gh`; with the Uberblick MCP server it also stores the day in an Uberblick document's data.
- **[ub-agents-flow](./ub-agents-flow/SKILL.md)**: Explain how the loop runs in your repository in two phases, issue and implementation/PR: each drawn with [ablauf](https://ablauf.uberblick.ai), every gate that holds work back numbered and highlighted, with the rule it enforces in one sentence and the line of the config or agent instructions it comes from, plus the roles and the queue rules. Writes the report as Uberblick Markdown and a matching page to read or print. Reads only; needs `python3` and Node.js 22.18+.
- **[ub-agents-unblock](./ub-agents-unblock/SKILL.md)**: Go through the issues and pull requests the loop stopped with `needs-human`, one at a time: the skill recommends a decision from the item and your repository's agent guidance, asks you with an interactive prompt, then posts your answer and resumes, merges or closes the item. Needs only an authenticated `gh`.
