# Working in this repository

This repository publishes agent skills for Uberblick and ub-agents. People
install them with `npx skills@latest add uberblick-ai/skills`, which reads
`skills/<group>/<name>/SKILL.md`. Claude Code users can also install a group
as a plugin from the marketplace in `.claude-plugin/marketplace.json`, which
points at the same folders.

## Layout

```
skills/<group>/
├── README.md          # the group: one line per skill, name linked to its SKILL.md
└── <name>/
    ├── SKILL.md       # required: frontmatter (name, description) and the instructions
    ├── scripts/       # code the skill runs; standard library, no install step
    ├── references/    # documents the skill reads on demand
    └── assets/        # templates and data the skill copies or fills
```

Skills sit in groups named for what they work on: `ub-agents/` for
repositories that run the ub-agents loop, later `uberblick/` for the product.
One skill per folder; the folder name is the skill name, and the name carries
the group as a prefix (`ub-agents-deliver-report`) so it reads right once
installed, where the group folder is gone. Every skill appears in its group's
`README.md` and in the top-level `README.md`, name linked to its `SKILL.md`,
and in `.claude-plugin/marketplace.json` under the plugin named for its group
(`source: "./"`, `strict: false`, the skill folder in `skills`).
Keep `SKILL.md` under 500 lines and move detail into `references/`; reference
files by their path relative to the skill folder, one level deep.

## Writing a skill

- `description` says what the skill does and when to use it, with the words a
  user would say. It is the only text an agent sees before choosing the skill.
- The body is the procedure: numbered steps, the exact commands, the shape of
  any file the skill writes. Leave out what the agent already knows.
- Scripts are self-contained, print a clear error on bad input and read only
  unless the skill says otherwise. A skill that needs tools or network access
  says so in `compatibility`.
- No em-dashes in prose.

## Checks

Every change must pass, locally and in CI:

```sh
pip install skills-ref                     # once
for s in skills/*/*/; do agentskills validate "$s"; done
python3 -m compileall -q skills
python3 scripts/check_marketplace.py       # every skill in its group's plugin
npx skills@latest add . --list             # every skill listed, none missing
```

## Releasing

A skill is live for `npx skills add` as soon as it is on `main`. Bump
`metadata.version` in `SKILL.md` when a skill's behaviour changes and add a
line to `CHANGELOG.md`.
