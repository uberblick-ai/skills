# uberblick skills

Guided `/uberblick` workflow for opinionated PRDs, RFCs, and implementation review using [uberblick.ai](https://uberblick.ai).

The `/uberblick` command gives Claude Code and Codex a structured planning workflow: load a PRD or RFC, run the right role (critic, architect, reviewer), write outputs back through MCP, and manage completion gates before marking work done.

The MCP-only baseline works without installing anything. This skill pack is an optional accelerator.

## Install for Claude Code

```
/plugin marketplace add uberblick-ai/skills
/plugin install uberblick@uberblick-ai
```

Then type `/uberblick` to start a session.

Claude Code will keep the plugin up to date automatically if marketplace auto-update is enabled.

### Manual install (fallback)

```bash
git clone https://github.com/uberblick-ai/skills.git
cp -r skills/plugins/uberblick/. .claude/plugins/uberblick/
```

Restart Claude Code, then type `/uberblick`.

To update, pull the latest repo and repeat the copy step.

## Install for Codex

```bash
git clone https://github.com/uberblick-ai/skills.git
cp -r skills/plugins/uberblick/codex/. .codex/skills/uberblick/
```

Restart Codex, then type `/uberblick`.

## Updating

For Claude Code marketplace installs, auto-update handles this. For manual installs, the skill notifies you at session start if a newer version is available — re-run the copy step with the latest repo contents to update.

## MCP-only baseline (no installation required)

You do not need to install this skill pack to use uberblick. Ask your AI assistant to follow `uberblick://docs/workflow` and `uberblick://docs/workflow-roles` directly. The skill pack adds the `/uberblick` command and guided stage flow — it is not a required control plane.

## Issues and feedback

[Open an issue](https://github.com/uberblick-ai/skills/issues) for bug reports, feature requests, or questions.
