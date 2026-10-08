# UB Agents

Skills for repositories that run the [ub-agents](https://agents.uberblick.ai)
loop: reading its records on GitHub, judging how the loop did, and tuning the
instructions it runs on.

- **[ub-agents-deliver-report](./ub-agents-deliver-report/SKILL.md)**: Review one day of loop deliveries: what shipped, how many runs each item took, what its retrospectives said, and the few changes that would have saved runs. Produces a report and slides. Needs `python3` and an authenticated `gh`.
