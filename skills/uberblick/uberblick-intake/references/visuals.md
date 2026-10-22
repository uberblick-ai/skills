# Drawings

Uberblick draws two kinds of code fence in a document: `ablauf` for flows and
`wireframe` for screens. A drawing earns its place when it shows in one look
what the prose would take a paragraph of branches to say. Most pages need
none; an intake of 15 pages typically has 2 to 6 drawings.

## Ablauf: flows

Use one for a process with states, branches or phases a person moves
through: a document's lifecycle, a signing order, an import with its failure
paths, a sync conflict, a release a user sees. Not for a straight list of
steps (a numbered list says it) or for internal architecture (that stays
Markdown).

- Read the syntax first: the `ablauf` help topic (`get_help` with
  `{"topic": "ablauf"}`, or the resource `uberblick://help/ablauf`). `ub`
  before 0.4.9 has no such topic; then read
  [the primer](https://github.com/uberblick-ai/ablauf/blob/v0.2.0/spike/PRIMER.md)
  (`curl -sL` the raw file if a web fetch fails).
- Draw what the code does: states and transitions from the model or the
  state machine, branches from the e2e tests. The main path runs down one
  column, rework and failure branches beside it, stops in a panel.
- A flow with several phases gets an overview drawing with one box per
  phase, then one drawing per phase on its own page. Gates or checks along a
  phase are numbered from `G1` on each page.
- Keep box titles to two or three words and edge labels to one or two.
- Convert every Mermaid diagram worth keeping into ablauf: Uberblick deletes
  Mermaid blocks.

```ablauf
flow v0
columns main side
text start col=main "A sender uploads a PDF"
box draft title="Draft" "Recipients and fields"
box pending title="Pending" "Waiting for signatures"
decision all "All signed?"
end done "Completed"
box rejected col=side row=all title="Rejected" "A recipient declined"

start --> draft
draft --> pending : send
pending --> all
all --> done label=inline : yes
all --> rejected tone=stop label=inline : declined
```

## Wireframe: screens

Use one when the page describes a screen whose layout matters to the reader:
the main view of an area, a dialog with a consequential choice, a settings
panel with several options. Only for products with a UI, and only for screens
that exist: take the labels, buttons and order from the components and the e2e
tests' selectors (`getByRole('button', { name: 'Send' })`), never invent
controls.

- Read the format first: `AUTHORING.md` ships in the package, at
  `DIR/node/node_modules/@uberblick/wireframe/AUTHORING.md` after the install
  in step 6.
- One screen per block, its essential controls only: a wireframe is a sketch,
  not a screenshot.

```wireframe
dialog Send “Lease agreement”?
  text Two recipients sign in order. Each gets an email when it is their turn.
  row.end
    button Cancel
    button.primary Send
```

## Checking

`node scripts/viz.mjs DIR/node DIR/docs/*.md` parses every wireframe and
draws every ablauf into `DIR/docs/viz/<slug>-<n>.svg`, which the review page
shows, and a `.flat.svg` beside each with its light colours written in, for
an image viewer or rasterizer that ignores CSS variables. It fails on any
diagnostic with the file and line. Look at each drawing: a clean render can
still cross edges or crowd labels; fix those too.
