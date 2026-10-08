# Uberblick skills

Agent skills for working with [Uberblick](https://github.com/uberblick-ai/uberblick-2)
and [ub-agents](https://agents.uberblick.ai). Each skill is a folder with a
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

## Skills

Skills are grouped by what they work on. Each group has its own README with
the full list.

### [UB Agents](skills/ub-agents/README.md)

Skills for repositories that run the [ub-agents](https://agents.uberblick.ai) loop.

- **[ub-agents-deliver-report](skills/ub-agents/ub-agents-deliver-report/SKILL.md)**: Report one calendar day of loop deliveries: what shipped, what cost extra runs, and the few changes that would have saved them. Opens the report in your browser. Needs `python3` and an authenticated `gh`.

## Contributing

Read [AGENTS.md](AGENTS.md) for the layout and the checks a change must pass.

## License

[MIT](LICENSE)
