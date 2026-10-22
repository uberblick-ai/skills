# Drawing the loop with ablauf

[ablauf](https://ablauf.uberblick.ai) draws a flow from text. The author
places every node; the renderer sizes the grid, routes the edges and reports
every problem with its line number. It never moves anything, so the drawing is
what you wrote. Each document has one flow: the overview's and one per
phase. The worked examples are
[../assets/overview.flow](../assets/overview.flow),
[../assets/issue.flow](../assets/issue.flow) and
[../assets/pr.flow](../assets/pr.flow). Uberblick draws the same source from
an `ablauf` fence.

## The lines you need

```
flow v0
# One comment line: the repository and what the flow covers.

columns rework main stop

pill needs-preparation col=main tone=muted
box issue-preparer "what it does, a few words"
decision g2 tone=system "G2 Clear and in scope?"
end merged "Squash-merged, issue closed"

pill needs-changes col=rework row=g4 tone=rework
panel human col=stop row=g2 span=7 tone=stop
  pill needs-human
  strong "G3 A maintainer answers"
  muted "removes needs-human, re-adds the trigger"

g2 --> ready : prepared
g4 --> needs-changes tone=rework : changes-requested
needs-changes --> implementer tone=rework from=top to=left label=end : revise the same PR

legend
  decision tone=system "gate, numbered as in the cards"
  pill tone=done "GitHub label"
  panel tone=stop "a person decides"
```

- `columns` names the columns left to right, once. Comments are whole lines starting with `#`.
- Nodes: `pill` (a label), `box` (an agent; the id is its name, the quoted
  text its caption), `decision` (a gate), `end`, `panel` (indented lines
  `pill`, `strong`, `muted`, `text`, `rule`), `text`.
- A node without `col=` goes below the previous one in the same column. `row=`
  puts it beside another node, `span=` lets a panel cover several rows.
- Edges: `a --> b` or dashed `a -.-> b`, then `tone=`, `from=`/`to=` with
  `top`, `right`, `bottom` or `left` (plus a slot like `bottom.2`), and
  `label=start|end|inline`, then `: label`.
- Tones: `ink`, `muted`, `neutral`, `agent`, `system`, `done`, `rework`,
  `stop`.

## Conventions for a loop flow

- Three flows. `overview.flow` is the abstract loop: an `end tone=muted`
  node per way work enters, side by side in the top row (a person's issue, an
  agent's follow-up or sub-issue, a bot's pull request), a `box` per phase
  named after it, its caption saying in a few words what the phase checks and
  who does it (`"grounds the requirement in the current code, checks the intent
  is clear and the scope an MVP; an issue review when needed"`), and an
  `end tone=done "Merged"`. No labels, gates, edge labels, rework or stop
  panel: the phase documents carry those. `issue.flow` starts at an
  `end created tone=muted "Issue created"` node with an edge to the entry
  label (`needs-preparation`) saying who adds it, and runs to the label the
  implementer starts on, ending in an `end` node such as "Implementation picks
  it up". `pr.flow` starts from that label and ends at the merge. Each phase
  flow draws the launcher's gate before its first agent, numbered `G1`.
- Work that enters without an issue, such as a bot's pull requests that
  `trusted-pr-authors` lets run or a label another tool adds that triggers an
  agent, gets its own input in the overview, with an edge straight to the
  phase it enters.

- Three columns: `rework` on the left for labels that send work back, `main`
  for the path an item takes when every gate passes, `stop` on the right for
  where a person steps in. Leave out a column the loop does not need.
- Main column, top to bottom: the entry label, then per agent its box, its
  gate as a `decision` and the label its passing outcome adds. Edges out of a
  gate carry the outcome name. Finish with an `end`. When an agent checks
  something before it does its work (a contract still valid, a PR it must not
  duplicate), draw that gate between two boxes: the agent's box, the gate, then
  a box for the work itself, such as `box implement "builds the one PR"`.
- Every gate of a phase appears in its drawing with its number as the
  first word of its text (`G2 ...`), as a `decision` with `tone=system`, or
  inside the stop panel for a gate a person decides, never only in an edge
  label, where it reads as a step rather than a check (`page.py` warns). A
  launcher gate that applies to every run goes once per phase, before the
  first agent, with an edge label that says so.
- Pills: the entry label `tone=muted`, labels that lead to the next agent
  `tone=agent` or `tone=done`, rework labels `tone=rework`, stop labels inside
  a `tone=stop` panel.
- Rework edges `tone=rework`, edges into the stop panel `tone=stop`. Route a
  loop back with `from=top to=left label=end` so it does not cross the main
  column.
- Keep captions to a few words; the detail belongs in the gate cards. A flow with more
  than about 20 nodes no longer fits a page: merge labels into edge text before
  dropping a gate.

## An issue-reviewer

`ub-agents init` writes an optional issue-reviewer: the preparer's `review`
outcome adds `needs-review`, and the issue-reviewer approves to `ready` or
sends it back with `needs-preparation`. When the config has it, draw it in a
second column of the issue flow, beside the preparer, with its own gate
(renders clean with ablauf 0.2.0):

```
columns main review

end created col=main tone=muted "Issue created"
pill needs-preparation tone=muted
box issue-preparer "states behavior and acceptance criteria"
decision g2 tone=system "G2 Small and clear?"
pill ready tone=done
end delivery "Implementation picks it up"

pill needs-review col=review row=g2 tone=agent
box issue-reviewer row=ready "second opinion on scope and criteria"
decision g3 row=delivery tone=system "G3 Scope and criteria hold?"

created --> needs-preparation : a maintainer adds the label
needs-preparation --> issue-preparer
issue-preparer --> g2
g2 --> ready : prepared
ready --> delivery
g2 --> needs-review : review
needs-review --> issue-reviewer
issue-reviewer --> g3
g3 --> ready from=left to=right : approved
g3 --> needs-preparation tone=rework from=right to=right label=end : changes-requested
```

`needs-review` then starts both the issue-reviewer (`kind: issue`) and the PR
reviewer (`kind: pr`); say so in the roles, since one label serves both.

`render.mjs` fails on any diagnostic, warnings included (`edge a → b crosses
c → d`, an unknown column or key). Fix the line it names, usually by moving a
node with `row=` or an edge end with `to=`, and render again.
