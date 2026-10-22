---
name: uberblick-intake
description: >-
  Move a repository's knowledge into Uberblick. Reads every Markdown file,
  the git history and the test suite, then proposes the corpus: which files
  become product pages and which stay in the repository as technical,
  implementation or agent Markdown, the tags for this repository, decision
  records for the questions the history keeps reopening, ablauf drawings
  and wireframes where a picture says it better, page scenarios that follow
  what the e2e tests cover, and a sidebar ready for the team. Shows the whole
  plan on one review page and writes it to the workspace once approved. Use
  when someone wants to set up Uberblick for an existing repository, migrate
  their docs into the corpus, or asks what an intake would create.
license: MIT
compatibility: >-
  Requires python3 and git, and Node.js 22.18 or newer with npm to check and
  draw ablauf and wireframe blocks. Writing to the corpus needs the Uberblick
  MCP tools or the `ub` command in a checkout bound to a workspace; without
  either it stops at the review page. Reads GitHub labels with an
  authenticated gh when there is one.
metadata:
  author: uberblick-ai
  version: "0.1"
---

# Intake

A new Uberblick workspace is only as useful as what it holds on day one. The
repository already knows a lot: what the product does (README, user docs),
how it is built (contributor and reference docs), what agents are told
(AGENTS.md and friends), which questions keep coming back (the history) and
what the team cares about enough to test end to end. This skill sorts that
into a corpus a person can trust: product intent as pages, the questions that
mattered as decision records, everything technical left as Markdown next to
the code, with a sidebar that opens on the right pages.

`scripts/intake.py` and `scripts/viz.mjs` live next to this file; call them by
their path inside this skill's directory. `CHECKOUT` is the repository's
checkout, `DIR` a scratch directory outside it. The plan's shape is in
[references/plan.md](references/plan.md), how to judge each part in
[references/analysis.md](references/analysis.md), drawings in
[references/visuals.md](references/visuals.md).

1. **Find the corpus.** The corpus is reachable when Uberblick MCP tools are
   in your tool list (whatever the server is called; load tools listed by
   name only), or when `ub` is on the PATH and `ub status` in `CHECKOUT`
   names a workspace. Through `ub`, read with a calls file and `--print`:

   ```sh
   echo '[{"tool":"list_tags","arguments":{}},{"tool":"get_sidebar","arguments":{}},{"tool":"list_docs","arguments":{}}]' > DIR/read.json
   python3 scripts/intake.py ub --calls DIR/read.json --checkout CHECKOUT --out DIR/read-applied.json --print
   ```

   Note the tag catalog (save the `list_tags` answer as `DIR/tags.json`), the
   sidebar's groups and the documents already there. A fresh workspace holds
   two starter pages in an "Uberblick" group. With neither route, say so in
   one line: the run ends with the review page and the Markdown files. Read
   the repository's own rules for corpus pages if it has any (AGENTS.md and
   the files it points to); otherwise follow the rules in
   [references/analysis.md](references/analysis.md#writing-pages).

2. **Scan.**

   ```sh
   python3 scripts/intake.py scan CHECKOUT > DIR/scan.json
   python3 scripts/intake.py hot DIR/scan.json
   python3 scripts/intake.py tests DIR/scan.json
   ```

   `scan` lists every tracked Markdown file with its headings, size, history
   and a first guess at its class, finds a docs site (mkdocs, Docusaurus,
   mdBook and others), walks up to 5,000 commits for the files and areas that
   change most and the commits that changed direction, and counts the tests
   per area and topic, by kind: `e2e` (a browser or device), `cli` (the built
   command, end to end), `integration`, `unit`. `hot` and `tests` print the
   same facts to read. A large repository takes a few minutes.

3. **Read.** The guesses are a starting point, never the answer. Read the
   README, the docs site's navigation file, every file guessed `product`,
   `decision` or `rfc`, and enough of the rest to confirm its class. Read the
   e2e suites' titles: they name the journeys the team protects. Read the
   code an area's page would describe, enough to state what a person can do
   there. For each hot area and each direction change, open the commits
   (`git show --stat SHA`) before calling it a decision.

4. **Decide** each part as [references/analysis.md](references/analysis.md)
   describes:

   - every Markdown file: `convert` into a named page, `keep` as Markdown, or
     `skip` (generated, fixture, release note fragment, duplicate), with one
     line of why; a folder can be one entry (`docs/reference/**`);
   - the pages: one per product area or concept a person acts on, small,
     with scenarios from the e2e journeys where the tests cover the area;
   - the decision records: existing ADRs, and the few history candidates
     that meet all four criteria;
   - 2 to 12 tags, reusing the catalog's names first;
   - where a drawing helps: ablauf for a flow with branches or phases,
     wireframe for a screen the page describes;
   - the sidebar: 3 to 6 groups, entry points pinned, the rest reachable.

5. **Write** `DIR/docs/<slug>.md`, one Uberblick Markdown file per document,
   and `DIR/intake.json`, as [references/plan.md](references/plan.md)
   describes. Link pages to each other with `[text](ref:slug)`; the writer
   turns these into document links. Never copy a source file: rewrite it as
   the page it should be.

6. **Check** the drawings and the plan, installing the renderers once per
   scratch directory:

   ```sh
   npm install --prefix DIR/node @uberblick/ablauf@0.2.0 @uberblick/wireframe@0.3.0
   node scripts/viz.mjs DIR/node DIR/docs/*.md
   python3 scripts/intake.py check DIR/intake.json --scan DIR/scan.json
   ```

   `viz.mjs` draws each ablauf block into `DIR/docs/viz/` and fails on any
   diagnostic with the file and line; fix and run again until it prints no
   diagnostics. `check` stops on an error (a Markdown file nobody accounted
   for, a link to no document, a decision answer over 60 words, a tag not in
   the plan) and warns on what usually needs a fix (history or plans in a
   page, a page over 900 words, a group pinning more than 8). Fix every
   warning or keep it knowingly.

7. **Review.** Build the page and open it:

   ```sh
   python3 scripts/intake.py review DIR/intake.json --scan DIR/scan.json --out DIR/review.html --open
   ```

   It shows the sidebar beside every document as it will be written, the
   tags, every Markdown file's fate, the decision candidates with their
   commits, the test focus and the proposed repository changes. Tell the
   person in a few sentences what the corpus will hold, then ask once for
   approval to write it, and for any new tags to be created under
   Workspace settings → Tags (MCP cannot create tags). Writes go to a
   workspace the team shares: wait for the answer. Change the plan as they
   ask and build the page again.

8. **Write to the corpus.** Read the catalog again into `DIR/tags.json` so
   the writes use only tags that exist, then:

   ```sh
   python3 scripts/intake.py calls DIR/intake.json --tags DIR/tags.json > DIR/calls.json
   python3 scripts/intake.py ub --calls DIR/calls.json --checkout CHECKOUT --out DIR/applied.json
   ```

   `calls` orders the writes: pages, linked pages first; decision records,
   with `related` naming their page; the pins, group by group, then the
   groups' order; the links a cycle kept out of the text. `{"$ref": slug}`
   and `{"$doc": slug}` stand for the UUID that slug's `create_doc`
   returned. `ub` runs them through one `ub mcp serve`, waits for the hub to
   acknowledge, writes `DIR/applied.json` (slug to UUID) and stops at the
   first refusal; fix that document and re-run with `--resume`. With the MCP
   tools in your list instead, make the same calls in order yourself,
   substituting the UUIDs. With `starter: unpin`, `ub` unpins the starter
   pages and deletes the "Uberblick" group once it is empty (the
   `starter_cleanup` call); through the MCP tools, do that with `unpin_doc`
   and `sidebar_group`. Tags the catalog still lacks are left off and named;
   once a person creates them, or to run the intake again after changing the
   plan, pass `--applied DIR/applied.json` to `calls`: documents already
   written are not created again, only given their tags, pinned and linked.

9. **Ground.** When the `uberblick-corpus-sync` skill is installed, run it in
   apply mode on the pages just written (their UUIDs from `applied.json`) and
   in report mode on the Markdown kept in the repository, at the same commit.
   It checks each claim against the code and records the result on the page.
   Without it, say that the pages are not yet checked against the code.

10. **Report.** Tell the person what was created (pages, decision records,
    pins, tags), what stays in the repository as Markdown, what was skipped,
    the decision candidates left out and why, and the repository changes
    from the plan: converted files to remove or shorten to a pointer, and a
    line in AGENTS.md or the README naming the corpus as the home of product
    intent. Make those repository changes only when asked, on a branch.
