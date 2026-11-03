# Drawing the loop with ablauf

[ablauf](https://ablauf.uberblick.ai) draws a flow from text. The author
places every node; the renderer sizes the grid, routes the edges and reports
every problem with its line number. It never moves anything, so the drawing is
what you wrote. Each document has one flow: the overview's and one per
phase. A flow ends with `play` scenarios: in Uberblick the drawing stays whole
until a reader presses Play, then each scenario lights its steps one by one
with a caption under the drawing. The worked examples are
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

play "Clean run"
  step needs-preparation
  step issue-preparer actor="issue-preparer" "Writes the behavior and criteria"
  step g2 "Yes: prepared"
  step ready
```

- `columns` names the columns left to right, once. Comments are whole lines starting with `#`.
- Nodes: `pill` (a label), `box` (an agent; the id is its name, the quoted
  text its caption), `decision` (a gate), `end`, `panel` (indented lines
  `pill`, `strong`, `muted`, `text`, `rule`), `text`.
- A node without `col=` goes below the previous one in the same column. `row=`
  puts it beside another node, `span=` lets a panel cover several rows.
- Edges: `a --> b` or dashed `a -.-> b`, then `tone=`, `from=`/`to=` with
  `top`, `right`, `bottom` or `left` (plus a slot like `bottom.2`), and
  `label=start|end`, then `: label`. Avoid `label=inline`: it sets the label
  in capitals. Where neither `start` nor `end` fits beside a long route back,
  send the edge to a label pill of its own beside the gate and route that pill
  back instead.
- Tones: `ink`, `muted`, `neutral`, `agent`, `system`, `done`, `rework`,
  `stop`.
- `play "Name"` starts a scenario, after everything else. Its indented
  `step TARGET` lines name a node id each; a step lights the node and the
  edge from the step before it, so consecutive steps need an edge between
  them. Then optionally a duration (`2.4s`, from `100ms` to `60s`),
  `actor="..."` and a quoted caption. An optional `tempo 1.8s` line before
  the steps sets the default, 1.6s.

## Conventions for a loop flow

- One flow per document. `overview.flow` is the abstract loop: an `end tone=muted`
  node per way work enters, side by side in the top row (a person's issue, an
  agent's follow-up or sub-issue, a bot's pull request), a `box` per phase
  named after it, its caption saying in a few words what the phase checks and
  who does it (`"grounds the requirement in the current code, checks the intent
  is clear and the scope an MVP; an issue review when needed"`), and an
  `end tone=done "Merged"`. No labels, gates, rework or stop panel: the
  phase documents carry those. Leave edges unlabeled too, except where a
  person chooses when an item moves on, such as landing a release branch
  (`: when ready for release, a maintainer merges`): a reader cannot infer
  that timing. `issue.flow` starts at an
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
  gate carry the outcome name, phrased as what happened where a bare route
  name would read as a step (`self-check passed`, not `self-check`). Finish with an `end`. When an agent checks
  something before it does its work (a contract still valid, a PR it must not
  duplicate), draw that gate between two boxes: the agent's box, the gate, then
  a box for the work itself, such as `box implement "builds the one PR"`.
- Every gate of a phase appears in its drawing with its number as the
  first word of its text (`G2 ...`), as a `decision` with `tone=system`, or
  inside the stop panel for a gate a person decides, never only in an edge
  label, where it reads as a step rather than a check (`page.py` warns). A
  launcher gate that applies to every run goes once per phase, before the
  first agent, with an edge label that says so.
- A fork on a property of the item, not a check it can fail (is the issue in
  a milestone, did a bot open the pull request), is a route: an unnumbered
  `decision tone=neutral` with an edge per answer, and a legend entry
  `decision tone=neutral "route, not a gate"`. Do not hide the fork in two
  edge labels from one box.
- Every edge into the stop panel says why, in a few of the instructions'
  words, not only the label it adds: `: needs-human: unclear intent, scope
  creep or a team decision`. Where an agent can stop both with a stop label
  and by reporting blocked, name both on the edge (`: needs-human: a scope
  call; blocked: needs outside help`), since only the first adds a label.
- A notification the `events` hook sends is part of the flow. One sent when
  a role starts is a dashed edge from the role's box to a `box tone=neutral`
  naming where it posts (`: posts on start`); one sent on a stop is a `muted`
  line in the stop panel.
- A drawing that hands an item to another document ends in an `end` node
  saying what the item waits for (`"waiting for the integrator to pick it
  up"`), never where the next drawing is.
- Pills: the entry label `tone=muted`, labels that lead to the next agent
  `tone=agent` or `tone=done`, rework labels `tone=rework`, stop labels inside
  a `tone=stop` panel.
- Rework edges `tone=rework`, edges into the stop panel `tone=stop`. Route a
  loop back with `from=top to=left label=end` so it does not cross the main
  column.
- Where a side route rejoins the main column, such as a second reviewer's
  approval leading to the label the passing path reaches, put that label on
  the row of the gate that leads to it, so the edge runs straight across
  instead of turning back up.
- Keep captions to a few words; the detail belongs in the gate cards. A flow with more
  than about 20 nodes no longer fits a page: merge labels into edge text before
  dropping a gate.

## Play scenarios

Each flow plays the paths items take most often, from `scripts/paths.py`
(step 3 of the skill), so a reader sees a typical item move before reading
the gates.

- One `play` per common path, most common first, up to four per flow. Keep a
  path while it covers a real share of the items (about 5% or more), and
  drop one that would play the same steps as a scenario already there. A
  route no item took gets no scenario; its gate card explains it.
- Translate each `agent outcome` into the drawing's ids: the agent's box,
  its gate, then the node its outcome's edge leads to (the label the outcome
  adds, the stop panel, the `end`). A stop is a step into the panel; a
  person's answer is the panel's edge back. `merged` and `closed` end on the
  phase's `end` node. A path the drawing cannot play misses a route: add the
  route, never bend the scenario around it.
- The first scenario starts at the phase's entry and runs to its end. Later
  ones start one step before they leave the first scenario's path (the gate
  that sends work back, the integrator before a maintainer's merge), so a
  reader does not replay what they saw.
- Name a scenario for what happens, in a few words: "Clean run", "One review
  round", "A maintainer answers", "A bot's pull request". No counts, shares
  or dates in a name or a caption: the drawing describes the loop as it
  runs, and the shares go in the reply to the maintainer.
- Captions on agents and gates, a few words each in the instructions' terms.
  The controls show the node's own text above the caption, so the caption
  says what happens in this scenario, never the node's text again: what the
  agent does, or a gate's answer and why (`"No: a criterion is not met"`).
  A step on a label needs none, except the last step of a scenario that ends
  on a label handing the item to another agent or document: its caption says
  who picks it up (`"Names the failing job, back to the implementer"`). `actor=` names the agent
  as the config does, or "A maintainer" on a person's step. Give a person's
  step `2.4s`, since that is where a reader stops to read.
- The overview plays one scenario per way work enters that the paths show,
  most common first: the entry, each phase box it passes, `Merged`.
- Without observed paths, play the passing path and the most likely route
  back, and say in the reply that the scenarios come from the config.

## An issue-reviewer

When the config has an issue-reviewer, draw it in a second column beside the
preparer, with its own gate, and put `ready` on that gate's row (renders clean
with ablauf 0.3.0):

```
columns main review

end created col=main tone=muted "Issue created"
pill needs-preparation tone=muted
box issue-preparer "states behavior and acceptance criteria"
decision g2 tone=system "G2 Small and clear?"

pill needs-review col=review row=g2 tone=agent
box issue-reviewer "second opinion on scope and criteria"
decision g3 tone=system "G3 Scope and criteria hold?"

pill ready col=main row=g3 tone=done
end delivery "Implementation picks it up"

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

When one label starts both the issue-reviewer and the PR reviewer, say so in
the roles.
