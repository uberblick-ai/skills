# Uberblick skills

Agent skills for working with [Uberblick](https://github.com/uberblick-ai/uberblick-2)
and [ub-agents](https://agents.uberblick.ai). Browse them at
[skills.uberblick.ai](https://skills.uberblick.ai). Each skill is a folder with a
`SKILL.md` that follows the
[Agent Skills specification](https://agentskills.io/specification), so it works
in Claude Code, Codex, Cursor, OpenCode and every other agent the
[`skills` CLI](https://github.com/vercel-labs/skills) supports.

## Install

```sh
npx skills@latest add uberblick-ai/skills
```

Pick the skills and agents in the prompt, or install one skill for one agent
without prompts:

```sh
npx skills@latest add uberblick-ai/skills --skill ub-agents-deliver-report -a claude-code -y
```

Add `-g` to install for every project on your machine instead of the current
one. `npx skills update` brings installed skills to the latest version.

In Claude Code, each group is also a plugin in this repository's marketplace:

```
/plugin install ub-agents --marketplace uberblick-ai/skills
```

Before Claude Code 2.1.275, add the marketplace first with
`/plugin marketplace add uberblick-ai/skills`, then
`/plugin install ub-agents@uberblick-ai`.

## Skills

Skills are grouped by what they work on. Each group has its own README with
the full list.

### [UB Agents](skills/ub-agents/README.md)

Skills for repositories that run the [ub-agents](https://agents.uberblick.ai) loop. Plugin: `ub-agents`.

- **[ub-agents-deliver-report](skills/ub-agents/ub-agents-deliver-report/SKILL.md)**: Report one calendar day of loop deliveries: how many the loop delivered on its own, which runs were wasted, where a person stepped in, the causes and the few changes that would have saved runs. Opens the report in your browser and leaves a JSON record of the day. Needs only `python3` and an authenticated `gh`; with the Uberblick MCP server it also stores each day in an Uberblick document to track KPIs over time.
- **[ub-agents-flow](skills/ub-agents/ub-agents-flow/SKILL.md)**: Explain how the loop runs in your repository in three documents: an overview with the whole loop in one drawing, then the issue phase and the implementation/PR phase, each drawn with [ablauf](https://ablauf.uberblick.ai), every gate that holds work back numbered and highlighted, with the rule it enforces in one sentence, plus the roles and the queue rules. Combines them into one document on request. Writes Uberblick Markdown and a matching page to read or print, stores the documents in your Uberblick corpus when one is connected, and tells you where the corpus said otherwise. Changes nothing on GitHub; needs `python3` and Node.js 22.18+.
- **[ub-agents-unblock](skills/ub-agents/ub-agents-unblock/SKILL.md)**: Go through the issues and pull requests the loop stopped with `needs-human`, one at a time: the skill recommends a decision from the item and your repository's agent guidance, asks you with an interactive prompt, then posts your answer and resumes, merges or closes the item. Needs only an authenticated `gh`.

### [Maintenance](skills/maintenance/README.md)

Repository maintenance, with no release or delivery-loop requirement. Plugin: `maintenance`.

- **[backlog-grooming](skills/maintenance/backlog-grooming/SKILL.md)**: Review all issues, a milestone or a project against current deliveries and available product intent. Challenge duplication and excess scope, resolve decisions in chat, and produce the “Less work. More value.” report with estimates, blockers and optional loop eligibility.
- **[ci-health](skills/maintenance/ci-health/SKILL.md)**: Track CI on main from GitHub Actions for any repository: the median wall time a push waits, with its spread and P95, the number of tests, optionally coverage and the test-to-code ratio, the changes that moved CI time up or down, and the top three actions that would cut the wait. Needs only `python3` and an authenticated `gh`; with the Uberblick MCP tools or the `ub` command it stores each day in the repository's own "CI Health Report" document with charts, recommended actions and an incident changelog.

## Contributing

Read [AGENTS.md](AGENTS.md) for the layout and the checks a change must pass.

## License

[MIT](LICENSE)
