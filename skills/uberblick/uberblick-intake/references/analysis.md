# Deciding the intake

The corpus holds product intent: what a person can do and what they see,
written as the product is today. Technical, implementation and agent
material stays in the repository as Markdown, next to the code it describes,
where it changes with that code. When unsure, keep the file in the
repository: a missing page is cheaper than a page that is wrong.

## Markdown files

Sort by what the file is for, not where it sits.

| The file | Action | Examples |
| --- | --- | --- |
| What a user can do, see or decide | `convert` | README feature sections, user guides, concepts, how-tos, FAQ, product docs on a docs site |
| How to get it, build it, run it or change it | `keep` | installation, binary packages, dependencies, building from source, CONTRIBUTING, ARCHITECTURE, development setup, release, deployment and self-hosting recipes, internals, code style, package READMEs, welcome docs for new contributors |
| Exhaustive reference generated from or mirroring code | `keep` | CLI reference, API reference, config option lists, environment variable tables, changelogs of settings |
| Instructions for agents or GitHub | `keep` | AGENTS.md, CLAUDE.md, `.agents/`, `.claude/`, `.cursor/`, skills, prompts, issue and PR templates |
| Records of past decisions | `convert` into decision records | ADRs, `decisions/`, accepted RFCs |
| Open proposals and plans | `keep` | RFC drafts, agent plans, scratch notes |
| Generated, fixture, vendored, fragments | `skip` | release-note fragments, changelogs, blog posts, test fixtures, `node_modules`, translated copies |
| Community and legal | `skip` | CODE_OF_CONDUCT, SECURITY, LICENSE, CLA |

- One file may feed several pages, and several files one page. A file that
  is part product, part technical takes `sections`: one entry per heading
  with its own action. A README usually splits this way: the pitch and
  features become the overview; dependencies, installation, packages,
  building, contributing and support stay.
- A generated file (a `cog` block, "do not edit", a file a script writes) is
  never the source: read what generates it, and `keep` or `skip` the output.
- A docs site is product intent but rarely belongs in the corpus page for
  page. Take its top-level navigation as the shape, convert the concepts and
  guides a person needs to act, and keep the reference sections as Markdown,
  linked from the pages. When the site is the product's published
  documentation, the pages and the site overlap: say so on the review page
  and let the person choose whether the corpus states intent at a coarser
  grain beside the site (the usual answer) or replaces it.
- Getting the product running stays Markdown, even when the product is
  something people install or operate (a server, a CLI): installation,
  binary packages, building from source, deployment and proxy recipes are
  documentation people follow step by step, and they change with the build.
  What a person can configure and do once it runs is product intent and gets
  pages; those pages link to the install docs instead of repeating them.
- `convert` never moves a file out of the repository. The corpus states the
  intent; the file stays until a person accepts a proposed change for it.
- A changelog is history; the corpus has none.
- Keep a file the team edits as Markdown on purpose (a style guide agents
  read, a contributing guide), even if it reads like intent.

## Capabilities, then pages

Before writing pages, list what a person can do with the product in
`capabilities`: one line each, the evidence (docs, code, tests), and the page
that covers it or why none does (internal, too small, reference only). The
pages follow from that list, never from a quota: a one-README tool may need
three pages, a large docs site thirty. A page per docs-site page is a sign of
copying; a capability with heavy tests or many docs and no page is a gap.

## Writing pages

Unless the repository has its own rules for corpus pages, which win:

- A page states what a person can do and what they see. Leave out stack,
  architecture, file paths, data structures and implementation mechanics.
- Write the product as it is, in the present tense. No history, plans or
  provenance: no "planned", "will", "coming soon", "since", "added in",
  version or release, date, issue or PR number. Work the maintainers have
  decided (an accepted RFC or ADR) counts as in place; an experiment behind
  a flag does not, unless a person can turn it on, and then it is a
  setting the page names.
- Describe what the default release build does. One code base shipped as
  several apps or editions is one corpus: name a difference on the page
  where it matters.
- When the docs and the code disagree, the code wins. Write what the code
  does and list the drift in the plan's `notes`, so the maintainers can fix
  the docs.
- Start small: a one-line usage or example first, a short section per
  command, screen or setting with a snippet, then scenarios as H3 headings
  with a short paragraph each. Related links last, as the closing section.
  Tables only for real reference data.
- Scenarios are what a person tries to get done, picked by how much it
  matters to them; the tests are evidence that a scenario works and how,
  not the list of scenarios. Never write a scenario from a test title alone.
- For a command-line product, show usage in a `terminal` fence (`$ glow
  README.md`, then the output) and syntax in a `sh` code fence.
- An overview links the area pages; it does not repeat them.
- Intros are one or two sentences, no TL;DR in the body. Plain words, full
  sentences. Cut what an example already shows.
- Commands, syntax and UI labels appear in code formatting exactly as the
  product shows them; read them from the code, not the old docs.
- When another page owns a fact, link it (`ref:slug`) instead of repeating it.
- The `description` is for agents searching the corpus: what the page covers,
  how it differs from its neighbours, the words someone would search for.

## Tags

Tags are how people filter the corpus and how agents narrow a search.

- Reuse the catalog first: names in `list_tags` (case ignored), such as
  `workflow` for process and lifecycle pages and `report` for recurring
  reports. Never rename or duplicate one with another spelling.
- Add one tag per product area a person would filter by: the nouns of the
  product (`signing`, `budgets`, `accounts`, `python-versions`), taken from
  the sidebar groups, the workspace packages, the e2e topics and the
  repository's GitHub labels (`scan.json` lists them). Prefer the word the
  product's UI or CLI uses.
- Add cross-cutting tags only when several pages share them: `security`,
  `api`, `self-hosting`, `mobile`.
- 2 to 12 tags (fewer for a small product), each used by at least two
  documents unless it names a core area. No tags for kinds (`page`, `decision`), statuses or teams.
- New tags are created by a person under Workspace settings → Tags; the
  writes leave off any tag that does not exist yet.

## Decision records

A decision record holds the short answer to one lasting question. Create one
only when all four hold: the choice is significant (a product principle, an
architectural direction, a system-wide commitment, a major user-facing
behaviour); credible alternatives had materially different consequences; it
constrains work beyond one change; and future work needs the trade-off.

- **Existing ADRs** and accepted RFCs become decided records when they meet
  the four criteria and constrain a product page; engineering-only ones
  (a build tool, a code style, a module layout) stay Markdown. The title is
  the question, the body the answer in at most 60 words, leading with the
  choice, with a link to the ADR file on GitHub at `ref` for the context and
  alternatives. Record the deciders and date as `answer`; when the ADR names
  none, the author and date of the commit that accepted it.
  Superseded ADRs: record only the one in force, and say what it replaced
  in its answer if that helps. Rejected and proposed ADRs stay Markdown.
- **History candidates** come from `intake.py hot`: an area with many
  commits and authors, reverts, or commits that change direction ("switch
  to", "replace", "migrate", "drop … in favour of"), and direction changes in
  manifests and build files. Open the commits. Most are routine (a
  dependency bump, a refactor, a fix) and fail the four criteria. Keep the
  few that name a lasting choice: a framework or library the product is built
  on, a storage or sync model, a security or permission model, a public
  interface. Two to six records is typical; none is a fine answer for a
  young or small repository.
- A history decision is recorded `open`: the answer states the choice the
  code shows and why, citing the pull request (or the commit, as
  `https://github.com/OWNER/NAME/commit/<full sha>`) as a link whose text is
  `#123` or the short sha, and a person decides it in Uberblick. Only an accepted ADR or a person's
  answer on record (`answer: {who, when, where}`) is `decided`.
- Open the patch (`git show SHA`), not only its message, and confirm the
  current code still follows it. A choice that is a setting a person changes
  (a default model, a theme) is a page fact, not a decision.
- Each record's `related` names the page it constrains, so the page shows it.
- List every candidate considered in `candidates`, with why it was left out.

## Tests

The test suite shows what the team protects. Use it to set how much each
page says, not to describe the tests.

- `intake.py tests` gives cases per area and topic by kind, and the e2e
  journeys with their suite and test titles. `e2e` and `cli` tests run the
  product as a person does: in a command-line product the `cli` tests are
  its journeys. The kinds and counts are heuristics from file names and
  imports: read a few files per kind before relying on them, and write
  "about" in `tests.summary`.
- An area with many journeys gets the scenarios a person needs, one H3 per
  scenario, in the product's words: "Sign in order", backed by
  `document-flow: signs in sequence`. Read the test to get the behaviour
  right, then state the behaviour, not the test.
- An area with only unit tests or none gets a short page: what a person can
  do, no scenarios beyond the obvious. Do not invent scenarios no test or code
  shows.
- A topic with heavy e2e weight and no page is a gap: add a page, or give
  its `tests.focus` row a `why` (an internal API, admin tooling).
- Put the suite's shape in `tests.summary`: where the weight is (for example
  "83% of cases are Playwright journeys, half of them the public API") and
  what that says about the product's priorities.
- Name the test paths a page follows in its `tests`, so grounding can check
  the page against them.

## Sidebar

The sidebar is how a person, or an agent new to the project, finds their way
in. Its groups are the domains, topics or responsibilities people on the team
own or work in; its pins are each domain's entry points; everything else is
reached from them.

- 3 to 6 groups, named for a domain in the product's nouns, short and in
  sentence case: "Signing", "Sharing", "Billing". A group never names a
  kind of document ("Decisions", "Reference", "Guides"): records and
  references belong to the domain they constrain.
- Each group pins its entry points, usually one and at most three: the page
  a person working in that domain opens first. Order the groups as a
  newcomer would meet the product, with the overview first in the first
  group.
- An entry point fans out. It says what the domain covers and links to each
  of its sub-docs with a line on what each holds; a sub-doc may lead on to
  its own. Decision records hang off the page they name in `related`, which
  shows them there. Every document is reachable from a pin, and `check`
  names the ones that are not. The review page shows each pin with the
  documents it leads to.
- Pin a decision record only when it is itself the entry point a person in
  that domain needs.
- The starter pages of a new workspace ("Welcome to Uberblick", "How to Use
  It" in the "Uberblick" group, spelled "Überblick" in older versions; the
  UUIDs never change) are unpinned only when the person agrees.

## Repository changes

Propose, do not make: for each converted file, whether to delete it, shorten
it to what stays technical, or leave it; and a line in AGENTS.md (or the
README) saying product intent lives in the Uberblick corpus and how agents
reach it. Keep the README's install, build and quick start, and every file
new contributors or users follow to get started: people read them on
GitHub. Never propose deleting or shortening a file that is `keep`. Never propose removing the source of a published docs site; its
readers are not in the corpus.
