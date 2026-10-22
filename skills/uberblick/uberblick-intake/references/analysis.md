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
| How it is built, run or changed | `keep` | CONTRIBUTING, ARCHITECTURE, development setup, build, release, deployment, internals, code style, package READMEs |
| Exhaustive reference generated from or mirroring code | `keep` | CLI reference, API reference, config option lists, environment variable tables, changelogs of settings |
| Instructions for agents or GitHub | `keep` | AGENTS.md, CLAUDE.md, `.agents/`, `.claude/`, `.cursor/`, skills, prompts, issue and PR templates |
| Records of past decisions | `convert` into decision records | ADRs, `decisions/`, accepted RFCs |
| Open proposals and plans | `keep` | RFC drafts, agent plans, scratch notes |
| Generated, fixture, vendored, fragments | `skip` | release-note fragments, changelogs, blog posts, test fixtures, `node_modules`, translated copies |
| Community and legal | `skip` | CODE_OF_CONDUCT, SECURITY, LICENSE, CLA |

- One file may feed several pages, and several files one page. A README
  usually splits: the pitch and features become the overview, install and
  contributing stay.
- A docs site is product intent but rarely belongs in the corpus page for
  page. Take its top-level navigation as the shape, convert the concepts and
  guides a person needs to act, and keep the reference sections as Markdown,
  linked from the pages. A first intake writes 8 to 25 pages; a page per
  docs-site page is a sign of copying.
- Self-hosting and operations docs are technical unless the product is
  something people operate (a server, a CLI they install); then installing
  and configuring it is the product, and one page on it belongs in the corpus.
- A changelog is history; the corpus has none.
- Keep a file the team edits as Markdown on purpose (a style guide agents
  read, a contributing guide), even if it reads like intent.

## Writing pages

Unless the repository has its own rules for corpus pages, which win:

- A page states what a person can do and what they see. Leave out stack,
  architecture, file paths, data structures and implementation mechanics.
- Write the product as it is, in the present tense. No history, plans or
  provenance: no "planned", "will", "coming soon", "since", "added in",
  version or release, date, issue or PR number. Work the maintainers have
  decided counts as in place.
- Start small: a one-line usage or example first, a short section per
  command, screen or setting with a snippet, then scenarios as H3 headings
  with a short paragraph each. Related links last. Tables only for real
  reference data.
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

- **Existing ADRs** that are accepted become decided records: the title is
  the question, the body the answer in at most 60 words, leading with the
  choice, with a link to the ADR file on GitHub at `ref` for the context and
  alternatives. With deciders and a date in the ADR, record them as `answer`.
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
- A history decision is recorded as decided without `answer` (an agent's
  stance from the evidence); its answer cites the commit or pull request as a
  GitHub link. A person confirms it in Uberblick.
- Each record's `related` names the page it constrains, so the page shows it.
- List every candidate considered in `candidates`, with why it was left out.

## Tests

The test suite shows what the team protects. Use it to set how much each
page says, not to describe the tests.

- `intake.py tests` gives cases per area and topic by kind, and the e2e
  journeys with their suite and test titles. `e2e` and `cli` tests run the
  product as a person does: their titles are the product's scenarios.
- An area with many journeys gets a page with scenarios that follow them,
  one H3 per journey family, in the product's words: "Sign in order" from
  `document-flow: signs in sequence`. Read the test to get the behaviour
  right, then state the behaviour, not the test.
- An area with only unit tests or none gets a short page: what a person can
  do, no scenarios beyond the obvious. Do not invent scenarios no test or code
  shows.
- A topic with heavy e2e weight and no page is a gap: add a page, or say in
  `tests.focus` why not (an internal API, admin tooling).
- Put the suite's shape in `tests.summary`: where the weight is (for example
  "83% of cases are Playwright journeys, half of them the public API") and
  what that says about the product's priorities.
- Name the test paths a page follows in its `tests`, so grounding can check
  the page against them.

## Sidebar

The sidebar is the first thing a person sees. Pin entry points, not
everything.

- 3 to 6 groups, at most 8 pins each, ordered as a newcomer would read them:
  a "Start here" group (the overview and the one or two concepts everything
  else uses), then one group per product area, in the order of the product's
  own navigation or its main journey, then a group for working on the
  product if pages for that exist.
- Pin the page a person opens first in each area, and the decision records
  that most constrain day-to-day work. Leave the rest unpinned; links and
  search reach them.
- Group names are the product's nouns, short, in sentence case.
- The starter pages of a new workspace ("Welcome to Uberblick", "How to Use
  It" in the "Uberblick" group) are unpinned only when the person agrees.

## Repository changes

Propose, do not make: for each converted file, whether to delete it, shorten
it to what stays technical, or leave it; and a line in AGENTS.md (or the
README) saying product intent lives in the Uberblick corpus and how agents
reach it. Keep the README's install and quick start: people read it on
GitHub.
