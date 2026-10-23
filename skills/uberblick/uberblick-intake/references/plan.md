# intake.json and the documents

`intake.py` reads `DIR/intake.json` and the Uberblick Markdown files it names
in `DIR/docs/`. `check` validates them, `review` shows them, `calls` turns them
into corpus writes.

```json
{
  "schema_version": 1,
  "repository": "OWNER/NAME",
  "ref": "8707e33c",
  "date": "2026-10-22",
  "summary": "At most 80 words: what the corpus holds, how it is grouped and what stays in the repository.",
  "tags": [
    {"name": "signing", "status": "new", "why": "The signing flow, the product's core; 9 pages."},
    {"name": "workflow", "status": "existing", "why": "Already in the catalog; the document lifecycle."}
  ],
  "sidebar": {
    "groups": [
      {"name": "Documents", "docs": ["overview", "document-lifecycle"]},
      {"name": "Signing", "docs": ["send-a-document"]}
    ],
    "starter": "unpin"
  },
  "documents": [
    {
      "slug": "send-a-document",
      "file": "docs/send-a-document.md",
      "kind": "page",
      "sources": ["README.md", "apps/docs/content/docs/users/documents/send.mdx"],
      "tests": ["packages/app-tests/e2e/document-flow"],
      "visuals": ["ablauf"]
    },
    {
      "slug": "pdf-library",
      "file": "docs/pdf-library.md",
      "kind": "decision",
      "related": "send-a-document",
      "sources": ["git:9035240b4d"],
      "status": "open"
    }
  ],
  "markdown": [
    {"path": "README.md", "action": "convert", "doc": ["overview"], "why": "Pitch and features; install and setup stay for GitHub readers.",
     "sections": [{"heading": "Developer quickstart", "action": "keep"}, {"heading": "Self hosting", "action": "keep"}]},
    {"path": "apps/docs/content/docs/developers/**", "action": "keep", "why": "API reference, generated from the code."},
    {"path": ".agents/**", "action": "keep", "why": "Agent plans and skills."},
    {"path": "CODE_OF_CONDUCT.md", "action": "skip", "why": "Community file; nothing for the corpus."}
  ],
  "capabilities": [
    {"name": "Send a document for signing", "evidence": ["apps/docs/content/docs/users/documents/send.mdx", "packages/app-tests/e2e/document-flow"], "doc": "send-a-document"},
    {"name": "Manage API tokens", "evidence": ["apps/web/src/app/(dashboard)/settings/tokens"], "doc": null, "why": "Developer setting; the API reference stays Markdown."}
  ],
  "candidates": [
    {"question": "Which library reads and signs PDFs?", "evidence": ["9035240b4d"], "create": "pdf-library",
     "why": "Replaced pdf-sign; constrains every signing change."},
    {"question": "Which linter?", "evidence": ["edbf65969b"], "create": null,
     "why": "Tooling, no product consequence; stays in CONTRIBUTING.md."}
  ],
  "tests": {
    "summary": "One or two sentences: where the suite's weight is and what that says about the product.",
    "focus": [
      {"topic": "document-flow", "cases": 46, "kind": "e2e", "doc": "send-a-document"},
      {"topic": "api", "cases": 521, "kind": "e2e", "doc": null, "why": "The public API; its reference stays Markdown."}
    ]
  },
  "repo_changes": [
    {"path": "README.md", "change": "Keep install and contributing; point to the corpus for what the product does."}
  ],
  "notes": ["Anything the person should know that fits nowhere else."]
}
```

- `ref` is the commit the scan read (`scan.json`'s `ref`; its full hash is
  `commit`, for links and code checks), `date` today.
- `capabilities`: what a person can do with the product, each with its
  `evidence` (docs, code, tests) and the `doc` that covers it, or `null`
  and a `why`. The pages follow from this list.
- `tags`: every tag a document uses, `status` `existing` when `list_tags`
  has it (case ignored) and `new` otherwise. Name the catalog's spelling. A
  tag is lowercase letters and digits joined by hyphens, at most 30
  characters. `"core": true` marks a tag that names a core area, which may
  sit on a single page.
- `sidebar.groups` in display order, one per domain, each with the entry
  points it pins in order; the other documents are linked from them. A document is pinned once at most; unpinned documents stay
  reachable through search, links and the decision log. `starter` is
  `unpin` or `keep`: what to do with the workspace's starter pages, decided
  with the person.
- `documents`: `slug` is kebab-case and unique; `file` is relative to
  `intake.json`. `kind` is `page` or `decision`. `sources` are the repository
  paths a page is written from (`path` or `path:start-end`, or `git:SHA` for a
  commit), `tests` the test folders or files its scenarios follow. A decision
  takes `related` (the slug of the page it belongs to), `status` (`open`
  or `decided`) and, only when a person's answer is on record, `answer:
  {who, when, where}`: an ADR's deciders, its date and its URL at `ref`.
  Without `status`, a record with `answer` is `decided` and one without is
  `open`. A decided record is written with its answer in one call, so its
  answer links only to pages or to records listed before it. A document already in the corpus takes `existing: UUID`: it
  is not created again, but can be pinned and linked.
- `markdown`: every Markdown file the scan found is covered by exactly one
  entry, an exact path or a glob (`dir/**`, `*.mdx`); an exact path wins over
  a glob. `action` is `convert` (with `doc`, one slug or a list), `keep` or
  `skip`. A file that is part product, part technical adds `sections`, one
  per heading with its own `action` (and `doc` when it converts). A
  section that is `keep` stays in the file; a heading with no entry
  follows the file's `action`, so list every setup heading the scan names
  in `keep_sections` (and the ones nested under them) as `keep`.
- `candidates`: every decision candidate considered, including the ones
  left out, with the commits (`sha`, short) and `create` naming the decision
  document or `null`.
- `tests.focus`: the topics that carry the suite's weight, from
  `intake.py tests`, each with the page that reflects it, or `null` and a
  `why` (internal, reference only). `check` warns about a topic with many
  journey cases and neither.
- `repo_changes`: proposals only; the skill makes none unless asked.

## A document file

Each document is one Markdown file with frontmatter, then its blocks:

```markdown
---
title: Send a document for signing
description: Preparing and sending a document: recipients, roles, fields, signing order, reminders. Envelope, distribute, signers.
tldr: Upload a PDF, add recipients and their fields, and send it; Documenso emails each recipient in order.
tags: [signing, workflow]
---

Upload a PDF, add who signs, place their fields and send.

## Recipients and roles

Each recipient is a **signer**, **approver**, **viewer** or gets a copy. See [Recipient roles](ref:recipient-roles).

### Signing in order

With *signing order* on, the second signer gets the email only after the first has signed.
```

- `title` and `description` are required; the description is for agents
  (at most 300 characters, search terms included), the `tldr` for people (at
  most 300). Both are plain text: backticks and asterisks show literally. `tags` lists tag names from the plan. Decisions have no `tldr`.
- The body is Uberblick Markdown: headings, paragraphs, flat lists (two
  spaces of indent per level, up to three), quotes, GFM tables, fenced code,
  `terminal` and `chart` fences, `ablauf` and `wireframe` fences, `:::card`
  containers. Inline: `**bold**`, `*italic*`, `` `code` ``, `~~strike~~`,
  `[text](https://…)` and `[text](ref:slug)` for another document of the plan
  (a whole document; `ref:slug#heading` is not supported).
- Scenarios are H3 headings under an H2 such as "Scenarios" or the area's
  own heading, each with a short paragraph.
- A `terminal` fence holds a session: `$ command` lines, each followed by
  its output. A `:::card` holds `label:` and `title:` lines, a blank line,
  the body, then optional `footer:` and `button: [Text](https://…)` lines.
- Not allowed: a leading H1 (the title shows already), `mermaid` (Uberblick
  deletes it; draw ablauf), relative links into the repository (link the file
  on GitHub at `ref`), images, HTML, nested block content.
- A decision's body is its answer: one to three blocks (paragraphs, code,
  tables, a list counts once), at most 60 words, leading with the choice.

`intake.py blocks FILE` prints the `create_doc` arguments a file becomes, to
check a conversion.
