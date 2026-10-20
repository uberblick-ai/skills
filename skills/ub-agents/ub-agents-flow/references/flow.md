# Drawing the loop with ablauf

[ablauf](https://ablauf.uberblick.ai) draws a flow from text. The author
places every node; the renderer sizes the grid, routes the edges and reports
every problem with its line number. It never moves anything, so the drawing is
what you wrote. The worked example is
[../assets/example.flow](../assets/example.flow).

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
  strong "G6 A maintainer decides"
  muted "removes needs-human, re-adds the trigger"

g2 --> ready : prepared
g4 --> needs-changes tone=rework : changes-requested
needs-changes --> implementer tone=rework from=top to=left label=end : revise the same PR

legend
  decision tone=system "gate, numbered as on page 2"
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

- Three columns: `rework` on the left for labels that send work back, `main`
  for the path an item takes when every gate passes, `stop` on the right for
  where a person steps in. Leave out a column the loop does not need.
- Main column, top to bottom: the entry label, then per agent its box, its
  gate as a `decision` and the label its passing outcome adds. Edges out of a
  gate carry the outcome name. Finish with an `end`.
- Every gate in `flow.json` appears in the drawing with its number as the
  first word of its text (`G2 ...`), as a `decision` with `tone=system`, or
  inside the stop panel for a gate a person decides. A launcher gate that
  applies to every run goes once, before the first agent, with an edge label
  that says so.
- Pills: the entry label `tone=muted`, labels that lead to the next agent
  `tone=agent` or `tone=done`, rework labels `tone=rework`, stop labels inside
  a `tone=stop` panel.
- Rework edges `tone=rework`, edges into the stop panel `tone=stop`. Route a
  loop back with `from=top to=left label=end` so it does not cross the main
  column.
- Keep captions to a few words; the detail belongs on page 2. A flow with more
  than about 20 nodes no longer fits a page: merge labels into edge text before
  dropping a gate.

`render.mjs` fails on any diagnostic, warnings included (`edge a → b crosses
c → d`, an unknown column or key). Fix the line it names, usually by moving a
node with `row=` or an edge end with `to=`, and render again.
