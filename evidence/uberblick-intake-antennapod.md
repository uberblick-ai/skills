# Evidence: uberblick-intake on AntennaPod/AntennaPod

> Temporary. This folder collects evidence from trial runs of the skill for PR #46.
> Delete `evidence/` before merging. One file per run, named `<skill>-<repo>.md`.

## The run

| | |
| --- | --- |
| Repository | [AntennaPod/AntennaPod](https://github.com/AntennaPod/AntennaPod) at `047e35079` (2026-10-29) |
| Product | Android podcast app (Java), 37 Gradle modules, 9,535 commits since 2012 |
| Docs in the repository | 50 Markdown files: a short README, CONTRIBUTING, AGENTS.md, 45 module READMEs. The user docs live on antennapod.org, in another repository. The GitHub wiki is switched off and empty. |
| Skill | `uberblick-intake` 0.1 at `1168571`, run by Claude Opus 5.5 on 2026-11-01 |
| Corpus | A temporary local workspace (`ub workspace create`, ub 0.4.13), bound in a scratch folder. No shared workspace was touched. |
| Person | The skill author, standing in for the owner, but without knowing the product |

**Result.**

| Item | Result |
| --- | --- |
| Markdown files | 1 converted, 48 kept, 1 skipped |
| Documents | 15 pages and 5 decision records, all `open` |
| Tags | 6 new and 1 starter tag (`sync`) |
| Sidebar | 5 groups and 11 pins; the starter pages are unpinned |
| Drawings | 1 ablauf, no wireframes |
| `check` | 5 errors and 1 warning on the first run, 0 after fixes |
| Writes | 65 of 65 calls applied in under 1 s |

Reading the code for capabilities was the dominant cost. One delegated agent spent 96 minutes and 191k tokens, with 94 tool calls, inventorying 12 areas.

**The corpus.** It has 5 groups:
- **AntennaPod:** overview; home and navigation
- **Podcasts:** add podcasts; subscriptions → podcast settings, parental controls
- **Listening:** queue (with an ablauf drawing of how an episode ends); episode lists; player → sleep timer, controls outside the app
- **Automation:** downloads and refresh
- **Your data:** sync; backup and restore; statistics and Echo

The 5 records:
- Which builds ship
- Which navigation
- How devices sync
- Which states an episode goes through
- What AntennaPod promises its listeners

## Where a person had to step in

Each line is something the user had to say that the skill should have made unnecessary. The finding numbers refer to the next section.

1. "its ok to create a temp local workspace": there's no dry-run recipe (finding 2).
2. "assume that the person running the skill is the owner … asking for guidance is ok": the agent skipped the checkpoint (finding 8).
3. "I don't know the answers, I don't know the repo or the product - can you check their homepage": the checkpoint assumes product knowledge (findings 9 and 10).
4. "is there a github wiki?": wikis aren't scanned (finding 11).
5. "product intent is what we are looking for, right": the pages drifted toward settings reference (finding 13).
6. "the corpus should not be developer reference": the decision records named code symbols and an engine choice (finding 14).
7. "it can be, where it matters - but product intent and pages to allow an easy understanding of the product is the key": same as finding 14.
8. "the skill should also suggest to reduce markdown files if this isn't clear yet": finding 15.
9. "ensure the skill stays agnostic and nothing from the repo leaks into the skill": applies to every proposed fix below.
10. "coarser pages is fine - the corpus describes product intent - not the product itself. See guidance doc on uberblick-2. This should be respected by the skill" (said at the immich checkpoint; it applies to this run too): the skill never reads the workspace's writing guidance (finding 21).
11. "I feel the corpus of PodAntenna is too thin", after the run: the coverage came from the screens, not from the project's own map of the product (finding 22).
12. "the corpus felt thin - in width and depth .. some topics might have deserved to get sub-pages. Compare how the uberblick-2 corpus is structured": the skill produces one flat level of pages (finding 23).
13. "I would like to cover the product intent sufficiently and surface relevant technical aspects - uberblick-2 corpus is probably quite detailed": the target is sufficient intent plus the technical interfaces that matter. uberblick-2 is the reference for structure, not the size target (finding 24).
14. "the corpus is there to understand the technical structure too. Finding the balance to give a birds-eye view to understand the data flow and models - without going into details and have too much detail is the challenge": the skill gives no bird's-eye technical view and no test for its height (finding 25).

## Findings

Severity: **high** = wrong output, blocks the run, or makes a person step in; **medium** = slows the run or
misleads; **low** = polish. AntennaPod supplies the evidence; every fix is written so it holds for any repository.

### Finding the corpus (step 1)

1. **High: `intake.py corpus` crashes on an unbound checkout.** Without `.uberblick.json` it starts
   `ub mcp serve`, which exits, and the script dies with a 20-line traceback ending in
   `RuntimeError: ub mcp serve stopped before answering initialize`. Fix: check for a binding first,
   and say how to get one: bind the checkout, or `ub workspace create NAME` in a scratch folder
   passed as `--checkout`.
2. **Medium: no dry-run path.** The description offers "what would an intake of this repo create?",
   but the steps never say where a dry run stops or which corpus it checks tags against. What
   worked: `ub workspace create` in a separate scratch folder. The checkout stays clean, and the MCP
   server already connected (bound to another repository's workspace) is never touched. Fix: name
   this recipe, and say never to read or write a workspace bound to a different repository.
3. **Low: the starter tags are out of date.** SKILL.md lists six; ub 0.4.13 creates eight (it adds
   `guidance` and `technical-reference`). Fix: say "the starter tags `list_tags` shows" instead of
   listing them.

### Scan and tests (step 2)

4. **Medium: `tests` contradicts itself and miscounts journeys.** It prints "Browser or device test
   configuration: none found", then counts 106 on-device `e2e` cases. 37 of them never run: the
   largest file has a class-level `@Ignore`, and another a custom `@IgnoreOnCi`. Yet the header says
   "2 marked skipped". About 48 are service tests, not journeys, and 9 zero-case helper files are
   listed as journeys. Fixes, all generic:
   - count class-level and custom `@Ignore*` annotations;
   - drop zero-case files from the journey list;
   - recognise an instrumented-test source set and its runner as device test configuration;
   - count a file as a journey only when it drives the UI.
5. **Low: `hot` ranks areas that are gone at `ref`.** The two top areas are a module deleted two
   years earlier. Fix: mark an area "(gone at ref)".
6. **Low: `workspaces` misses nested modules.** It lists 5 of 37 Gradle modules (only top-level
   names). Tags draw on workspace names. Fix: read nested module paths.

### Reading (step 3)

7. **High (cost): a product whose intent lives only in code is expensive to read, and the skill has
   no recipe for it.** The README pitch was the only product prose in the repository. Fix:
   - ask at the checkpoint which areas matter before reading all of them (finding 9);
   - add a short "where capabilities live, by product kind" table to analysis.md: an app's
     settings definitions, menus, navigation and string resources; a web app's routes; a CLI's help;
   - consider letting `scan` dump the obvious UI facts, the way `tests` dumps test titles.

   The delegated inventory was accurate where spot-checked. Even so, my own drafts had 3 wrong
   labels before `check` (finding 17).
8. **High: a "dry run" was read as "unattended", so the checkpoint was skipped.** Step 4's only
   exception is "run unattended with leave to go on". I drafted 9 documents before asking anything.
   Fix:
   - say that a dry run still stops at the checkpoint when a person is in the session;
   - say that the person running the skill counts as the owner unless they say otherwise;
   - say that asking at the checkpoint is preferred to gathering everything alone.
9. **High: the checkpoint assumes the person knows the product.** Six open questions got "I don't
   know the repo or the product". Fix: state every outline item as a recommendation with its
   evidence, and ask "change anything?". "Don't know" keeps the recommendation and goes into
   `assumptions`.
10. **Medium: the project's homepage and published docs navigation aren't mentioned.** Two fetches
    gave the product's stated principles (absent from the repository) and the group names; the
    docs' sections matched the app's own settings words. Fix: in step 3, *when* the README, the
    host's `homepage` field or a package manifest links a homepage or published docs, read the
    homepage and the docs navigation; their words are good group and tag names. Many repositories
    have neither. Then fall back to what the repository says about itself: the README's opening, a
    manifest's `description`, store or package listing metadata kept in the repo, and the tracker's
    area labels. With none of these, ask at the checkpoint (finding 9). Outside sources show
    emphasis and words, never behaviour: the code still wins. Skip pages that need signing in, and
    for a private repository fetch nothing unless the person says so.
11. **Medium: GitHub wikis aren't scanned.** The repository reports `has_wiki: false`, yet
    `<repo>.wiki.git` clones with 309 commits. Its deleted pages held the episode state model, which
    became a decision record. Fix: `scan` tries the wiki remote, quietly skipping it when there is
    none (most repositories), and lists current and deleted pages.
    Deleted pages are evidence for decision candidates, never a source for pages.
12. **Medium: the history heuristics miss decisions made at the start.** Two of the five records
    (the episode state model and the listener promises) never had a "switch to" commit; the wiki and
    the homepage found them. A related point: a rewrite looked like an experiment until a build flag
    showed it was the only path. Fix:
    - say that early decisions come from the homepage, the wiki and the docs, not from `hot`;
    - for history candidates, check build flags that switch a new path on.

### What a page and a record are for (steps 5 and 6)

13. **Medium: pages drift toward settings reference in a settings-heavy product.** analysis.md keeps
    "config option lists" out of the corpus but doesn't say how to write a product whose behaviour
    *is* its settings. Fix, a rule of thumb: name a setting when it changes what a person
    experiences, and say what it does for them. Don't list every value; prefer a scenario.
14. **Medium: decision records slip into developer reference.** Drafts named code symbols and build
    flavor names, and one recorded which library plays audio. The criteria let "a framework or
    library the product is built on" through, which invites this. Fix:
    - write a record's answer in the product's words, for someone learning the product;
    - keep an engineering choice only where it changes what people get, and leave it out (as a
      candidate with its reason) when the repository already records it next to the code.
15. **Medium: the skill proposes reducing Markdown only for converted files.** analysis.md asks,
    per converted file, whether to delete or shorten it, and forbids touching `keep` files. It is
    silent on these cases:
    - Markdown that duplicates the published docs or the new pages;
    - stale or stub docs (here 45 module READMEs of 11–181 words, most under 50);
    - repositories whose intent was never in Markdown.

    Fix: make "fewer Markdown files" an explicit goal of `repo_changes`. Propose merging stubs,
    pointing duplicated prose to the corpus or the docs site, and say so even when the answer is
    "nothing to reduce". It stays a proposal, made only when asked.

21. **High: the skill never reads the workspace's writing guidance, and its own page rules
    contradict it.** The corpus's "Writing pages" page (tag `guidance`) says: "The product explains
    itself. A page does not teach how to use it: it shapes the product and sets its boundaries,
    stating what it must do, what it promises and what it refuses." It gives a feature page a
    shape (purpose, what it promises, what you can do, scenarios, notes). It bans option lists,
    defaults, internals and provenance, and says "Never fill unknown intent by describing what
    the code does today." analysis.md → Writing pages says the opposite in places:
    - "Write the product as it is";
    - "When the docs and the code disagree, the code wins. Write what the code does";
    - "a short section per command, screen or setting with a snippet".

    The skill only lets "the repository's own rules for corpus pages" win. A fresh workspace has
    the `guidance` tag, described as rules agents read before their first write, but no page
    carries it, and the skill reads neither the tag nor the "Welcome to Uberblick" page. This run's
    pages follow the skill and break the guidance: they state defaults ("every 12 hours by
    default", "25 by default"), list option values, and describe what the code does instead of
    what the product promises. Findings 13 and 14 were symptoms of this. Fix:
    - step 1 reads every `guidance`-tagged page (and the welcome page) and treats them as the
      rules for pages, above analysis.md;
    - analysis.md → Writing pages is rewritten to match the product's guidance: promises and
      boundaries first, the page shapes, the never-on-a-page list;
    - where intent can't be known from the repository, the agent lists the question at the
      checkpoint instead of writing what the code does.

22. **High: the corpus came out thin, because coverage followed the screens, not the project's own
    map of the product.** About 4,400 words over 20 documents; the five records are 34 to 48 words.
    Measured against what the project itself names:
    - **A whole audience is missing.** The published docs have a "For podcasters & hosters"
      section (listing a podcast, funding tags, moving a feed's URL, the subscribe link). The
      corpus says nothing to podcasters. The skill asks for "the product's kind and audience" but
      never asks whether there is more than one.
    - **Six tracker feature labels have no page:** Chapters, Local feeds, (External) storage,
      Podcast Index / Podcasting 2.0, Accessibility, Interacting devices. `scan` lists the labels;
      the skill uses them for tags only, not as a coverage checklist.
    - **The published docs were read by section title only.** They live in another repository of
      the same organization (36 English pages). Several hold refusals and promises a listener
      relies on: `ads`, `central-distributed`, `multiple-queues`, `other-platforms`,
      `app-permissions`, `episode-deletion`, `episodes-missing`. The skill only covers a docs site
      inside the repository.
    - **Refusals are nearly absent.** The pages describe what is there. They hardly say what the
      app won't do: one queue, not several; no central server; never deletes a favorite. The
      guidance asks pages for what the product "promises and refuses". The skill names no source
      for refusals.

    Fix: build coverage from the project's map before reading code. List every audience, every
    published docs page and every area or feature label, and give each a page or a reason
    (`capabilities` already has the shape). When the published docs live in another repository,
    clone and read it like the main one. Look for refusals in the docs, the FAQ and declined
    requests, and state them as promises on pages, or as records.

23. **High: the corpus is thin in depth as well as width: one flat level of pages, no sub-pages.**
    The skill's shape rules push toward it:
    - SKILL.md step 5 asks for "one per product area or concept a person acts on, small";
    - analysis.md asks for 3 to 6 groups, each pinning "usually one and at most three";
    - `check` warns about a group pinning more than 3 entry points.

    Nothing in the skill mentions sub-pages, page families, or splitting what a feature promises
    from how a surface presents it. The corpus the guidance comes from (uberblick-2, read
    2026-11-01) is built the other way:

    | | AntennaPod intake | uberblick-2 corpus |
    | --- | --- | --- |
    | Pages and records | 15 pages, 5 records | 64 pages, 11 records |
    | Sidebar | 5 groups, 11 pins, every page one level below a pin | 3 groups, 8 pins; the product sits in one group with 5 pins |
    | Structure | One page per area | Entry pages that fan out into families: Domain model → model pages; `CLI` → 12 command pages; `MCP` → 17 tool and help pages; `Web UI system` → 9 screen pages; Uberblick Markdown → 4 extension pages |
    | Promises versus surfaces | Mixed on each page | Feature pages own the promises (Comments, Notifications, Permissions, Archiving and deleting); surface pages (`Web UI: …`, `CLI: …`, `MCP: …`) show how one surface presents them and link back |
    | Records | 5, all `open`, 34 to 48 words | 11, all `decided`, each naming who decided |

    In AntennaPod, several areas deserved sub-pages:
    - **The player:** chapters, transcripts, video, Cast, speed and audio.
    - **Episode lists:** Inbox, Downloads, Playback history, Favorites, swipe actions.
    - **Downloads and refresh:** refresh, automatic download, automatic deletion, mobile data and storage.
    - **Controls outside the app:** notifications, widget, Android Auto, Wear OS.
    - **Add podcasts:** search and discovery, OPML, local folders.
    - **A domain model entry** (podcast, episode and its states, queue, tag) that the feature pages hang from.

    Fix: give the skill a page structure, not just a page list. That means an overview and
    a domain-model entry. Feature pages own the promises; surface pages present them, one per
    screen, command or tool where a surface has several; sub-pages appear when an area has
    capabilities with their own promises, tests or docs pages. Few groups and pins, each pin the
    entry to a family. Replace the "at most three pins" warning with a check that every family has
    one entry page. The plan could gain a `parent` per document so the review shows the tree.

24. **Medium: the skill shuts out every technical aspect, including the ones a corpus should
    surface.** analysis.md opens: "Technical, implementation and agent material stays in the
    repository as Markdown". Writing pages says "Leave out stack, architecture, file paths, data
    structures and implementation mechanics". The guidance draws the line elsewhere: a
    `technical-reference` page (a starter tag in every workspace) is for "readers who act on
    exact names, fields, codes or formats". There, "the interface belongs: names, fields,
    values, error codes, recovery steps, syntax. The mechanism behind it (storage, queues,
    logging, schema design) does not."

    AntennaPod has interfaces that others build against, and the intake left all of them out:
    - the feed elements podcasters can rely on (chapters, transcripts, funding, comments), and
      how a moved feed's redirect is followed;
    - the subscribe link a podcaster can publish;
    - the automation intents other apps (Tasker) send;
    - what sync exchanges with a gpodder or Nextcloud server;
    - the backup and OPML files.

    **Calibration.** The target is sufficient intent, not uberblick-2's size. uberblick-2 is a
    mature, hand-curated corpus (64 pages) and serves as the reference for structure and an upper
    bound for detail. "Sufficient" can be tested: every audience, docs page and feature label is
    covered (S21); every feature page states its promises and refusals (S20, S23); an area with
    several capabilities that carry their own promises gets sub-pages (S24); and every interface
    someone outside the team builds against gets a `technical-reference` page. For AntennaPod
    that is about 30 to 35 documents rather than 20, for example:
    - **Listening:** Player, with Chapters, Transcripts, Video, Cast, Sleep timer.
    - **The queue and lists:** Queue, Inbox, Episode lists.
    - **Podcasts:** Subscriptions, Add podcasts with Local folders, Podcast settings.
    - **Automation:** Automatic download, Automatic deletion, Refresh, Mobile data and storage.
    - **Outside the app:** Notifications, Widget, Android Auto, Wear OS.
    - **Your data:** Sync, Backup, Statistics and Echo.
    - **For podcasters:** Feeds AntennaPod reads, Moving a feed, the Subscribe link.
    - **Technical reference:** Automation intents, the sync exchange.
    - **A domain model entry:** podcast, episode and its states, queue, tag.
    - **Records:** at least the refusals the docs state (one queue, no central server, no ads).

    Fix: replace the blanket rule with the guidance's line. Internals stay in the repository.
    Interfaces that people or other programs act on become `technical-reference` pages: feed or
    file formats, links and intents, protocols with outside servers, a CLI's or API's contract
    where it is part of the product. And give the person a sufficiency test at the checkpoint.

25. **Medium: no bird's-eye view of the technical structure, and nothing that says how high to fly.**
    The corpus should also let someone understand how the product is built: its models and how
    data moves. The skill offers two extremes. It leaves out "stack, architecture … data
    structures", and its only technical outlet would be reference detail. The AntennaPod intake
    had neither a model page nor a data-flow view. The episode state model became a decision record
    because the corpus had no other place for it.

    uberblick-2's "Domain model" page shows the height. It is one table, `Model | Purpose`, each
    row one sentence linking to the model's own page (Workspaces, Regular documents, Decision
    records, Tags, Comments), then a short note on how special cases (RFCs, reports) use the
    models. It has no fields, schemas, classes or storage. Its flows work the same way: an overview
    drawing with one box per phase, each phase on its own page.

    For AntennaPod, the bird's-eye view would be two things:
    - a domain model: podcast (feed), episode and its media, the episode states, queue, tag,
      download, playback position and history, sync account;
    - one data-flow drawing: feeds refresh → new episodes → Inbox or queue → download → play →
      played → deleted, with where data leaves and enters (sync server, backup file, OPML, the
      watch).

    A test for the balance, to put in the skill:
    - **Enough:** someone new can say what each model is for, how the models relate, where a piece
      of data comes from and goes, and which page owns its rules.
    - **Too much:** the page would change if the code were refactored without changing behaviour
      (fields, tables, classes, modules, queues). That belongs in the repository.

    Fix: every intake proposes a domain-model entry page and, where data moves between stages,
    devices or services, one data-flow overview drawing. Both link to the feature pages and
    stay at the height above.

### Checking, review and writing (steps 7 to 10)

16. **Medium: step 7 says the corpus help names the renderer versions; it doesn't.** `get_help`
    `ablauf` names the version only through the primer link, and nothing names the wireframe
    version. Fix: make the help name both packages, or drop the sentence.
17. **Medium: `check` can't catch wrong labels.** Three wrong UI labels and one false claim got
    past it and were caught by hand. Fix: a check that extracts each backticked label from a page
    and finds it in the product's strings (string resources, help text) would catch most of them.
18. **Good: `check` caught invented source paths.** 5 of about 70 source paths I wrote from memory
    didn't exist. `check` named each one.
19. **Low: no `drawing` status on write.** ub 0.4.13 returned none for the ablauf block, so only
    `viz.mjs` checked it. As the skill says: say the drawings were looked at, here after
    rasterising with `qlmanage`.
20. **Low: `uberblick-corpus-sync` isn't installed, so step 10 can't run.** The pages were checked
    by hand at `047e35079` and carry no recorded check.

### What worked

- `scan` took 5.6 s on 9.5k commits; `markdown_dirs` gives the bulk fates at once.
- The four decision criteria quickly dismissed all 17 closed "Needs: Decision" issues as single
  features.
- "Open the patch and confirm the current code still follows it" turned a rewrite that looked
  experimental into a fact.
- The write step: one command, 65 calls, under a second; the sidebar is printed as written.
- The review page and `check` ran cleanly once the plan was fixed.

## Suggestions

Filed here for now, not made: more runs will show which ones recur. Each has a stable ID, so another
run can add itself to **Also seen in** (or "contradicts") instead of filing it again. Ranked by this run (S20 was added last but ranks first);
**F** is the finding above. Every suggestion is written to hold for any repository.

| ID | Suggestion | Details | Where | F | Also seen in |
| --- | --- | --- | --- | --- | --- |
| S20 | Follow the workspace's writing guidance (ranked first) | Step 1 reads every `guidance`-tagged page and the welcome page, and they rule over analysis.md. Rewrite analysis.md → Writing pages to match: pages state purpose, promises and boundaries ("the product explains itself"), in the feature and surface shapes; never option lists, defaults, internals or provenance; never fill unknown intent with what the code does today; ask instead. Absorbs S3. | `SKILL.md` step 1; `analysis.md` → Writing pages | 21 | immich (the person supplied the guidance at the checkpoint) |
| S1 | Always stop at the checkpoint | A dry run still stops at step 4 whenever a person is in the session. The person running it counts as the owner unless they say otherwise. Asking beats gathering everything alone. | `SKILL.md` step 4 ("Run unattended…") | 8 | ablauf §2 (checkpoint run by hand; related) |
| S2 | Recommend, don't quiz | Give every outline item as a recommendation with its evidence, then ask "change anything?". "Don't know" keeps the recommendation and goes into `checkpoint.assumptions`. | `SKILL.md` step 4; `analysis.md` → Confirm before recording | 9 | |
| S21 | Coverage from the project's own map | Before reading code, list every audience, every published docs page and every area or feature label (`scan` has the labels). Each gets a page or a reason in `capabilities`; `check` warns about a label or docs page with neither. | `SKILL.md` steps 3 and 5; `analysis.md` → Capabilities, then pages; `intake.py` `validate` | 22 | immich (heaviest suites did not set depth; related) |
| S22 | Read published docs in another repository | When the README or homepage links docs built from another repository of the same owner, clone it and read its pages, not just its navigation. They are the team's own statement of the product. | `SKILL.md` step 3; `analysis.md` → Markdown files (docs site) | 22 | |
| S23 | Capture refusals | Pages and records state what the product refuses as well as what it does. Look for refusals in the docs and FAQ, and in declined requests closed by a maintainer (`not planned`, `wontfix`, `by design`). | `analysis.md` → Writing pages, Decision records | 22 | fzf finding 6 (a principle found in declined requests); immich (FAQ refusals became records) |
| S24 | A page structure, not a page list | An overview and a domain-model entry; feature pages that own promises; surface pages (`<Surface>: …`) that present them and link back; sub-pages when an area has capabilities with their own promises, tests or docs pages. Few groups and pins, each pin the entry to a family; drop the "more than 3 pins" warning for a check that every family has an entry page. A `parent` per document lets the review show the tree. | `SKILL.md` step 5; `analysis.md` → Capabilities, then pages, and Sidebar; `plan.md`; `intake.py` `validate`, `review` | 23 | |
| S25 | Surface the technical interfaces that matter | Replace "technical material stays in the repository" with the guidance's line: internals stay, but interfaces that people or other programs act on (feed and file formats, links and intents, protocols with outside servers, a CLI's or API's contract) get `technical-reference` pages. Add a sufficiency test to the checkpoint: audiences, docs pages and labels covered; promises and refusals stated; sub-pages where capabilities carry their own promises; every outside interface referenced. uberblick-2 sets the structure, not the size. | `analysis.md` intro, Markdown files table, Writing pages; `SKILL.md` steps 4 and 5 | 24 | |
| S26 | A bird's-eye technical view, at the right height | Every intake proposes a domain-model entry page (a `Model / Purpose` table, one sentence per model, linking to its page, with how the models relate) and, where data moves between stages, devices or services, one data-flow overview drawing (ablauf, one box per stage, showing where data enters and leaves). Height test: enough when someone new can say what each model is for, where data comes from and goes, and which page owns its rules; too much when the page would change under a refactor that keeps behaviour (fields, tables, classes, modules). | `analysis.md` → Capabilities, then pages, and Writing pages; `references/visuals.md` (overview drawing); `SKILL.md` steps 4 and 5 | 25 | |
| S3 | Pages state intent, not reference | Absorbed by S20. Name a setting only where it carries a promise, and say what it promises; no lists of values. | `analysis.md` → Writing pages | 13 | ablauf §4.2 (intent is the point; related) |
| S4 | Records in the product's words | No code symbols or build names. An engineering choice qualifies only where it changes what people get; leave it out, as a candidate with its reason, when the repo records it next to the code. | `analysis.md` → Decision records (the "framework or library" line) | 14 | |
| S5 | Read what the team publishes, when there is any | When the README, the host's `homepage` field or a manifest links a homepage or docs site, read the homepage and the docs navigation for emphasis, group names and tags. Otherwise use the README's opening, a manifest's `description`, listing metadata in the repo and area labels; with none of these, ask (S2). Never a source for behaviour. Skip pages behind a sign-in, and fetch nothing for a private repository unasked. | `SKILL.md` step 3; `analysis.md` → Product, audience and scope | 10 | ablauf §5 "Product intent from the host" (related) |
| S6 | Scan the wiki, when there is one | `scan` tries `git ls-remote <repo>.wiki.git` even when the host reports no wiki, skips quietly when it fails, and lists current and deleted pages. Deleted pages are evidence for decisions, never page sources. | `intake.py` `cmd_scan` (beside `labels_of`); `analysis.md` → Decision records | 11 | |
| S7 | Founding decisions aren't in the history | Say so: they come from the homepage, wiki, docs, specs and agent instructions, not `hot`. Before calling a rewrite experimental, check for build flags that switch the new path on. | `analysis.md` → Decision records, history candidates | 12 | ablauf §1 (`hot` found nothing; the decisions were in docs and the tracker) |
| S8 | Clear error on an unbound checkout | Look for `.uberblick.json` in the checkout or a parent before starting `ub mcp serve`. Without one, print one line naming both fixes, with no traceback. | `intake.py` `cmd_corpus`, `cmd_ub` | 1 | |
| S9 | A dry-run recipe | Name it: a separate scratch folder and `ub workspace create`, writing only there. Never read or write a workspace bound to another repository, even when its MCP server is connected. | `SKILL.md` step 1 | 2 | ablauf (a workspace created per run; related) |
| S10 | Fewer Markdown files as a goal | `repo_changes` also proposes merging stub docs and pointing duplicated prose at the corpus or docs site. It says "nothing to reduce" when that's the answer. Proposals only. | `analysis.md` → Repository changes; `SKILL.md` step 11 | 15 | |
| S11 | Count skips right | A class-level `@Ignore` counts as one skip, not every case in the class. Count them all, and match custom `@IgnoreOn*` annotations. | `intake.py` `SKIPPED` regex, `scan_tests` | 4 | |
| S12 | Detect journeys right | Drop zero-case helper files. A file is a journey only when it drives the UI; otherwise it's an integration test. An instrumented-test source set and its runner count as device test configuration. | `intake.py` `test_kind`, `journeys`, `cmd_tests` | 4 | ablauf §5 "Depth without journey tests" (related) |
| S13 | Cheaper reading of products whose intent lives in code | A "where capabilities live, by product kind" table: settings definitions, menus, navigation and strings for an app; routes for web; help text for a CLI. At the checkpoint, ask which areas matter before reading them all. | `analysis.md` → Capabilities, then pages | 7 | ablauf §5 "the product's kind" (related) |
| S14 | Catch wrong labels and claims | `check` warns about each backticked label not found in the product's strings (string resources, help output). Claims still need reading against the code. | `intake.py` `validate` | 17 | ablauf §4.3 (a claim the host contradicts) |
| S15 | Mark areas gone at `ref` | `hot` marks areas with no files at `ref`. | `intake.py` `churn`, `cmd_hot` | 5 | |
| S16 | Nested workspaces | Read nested module paths, such as Gradle `:a:b`. | `intake.py` `workspaces_of` | 6 | |
| S17 | Don't list the starter tags | Say "the starter tags `list_tags` shows". | `SKILL.md` step 1 | 3 | |
| S18 | Renderer versions named in help | `get_help` `ablauf`/`wireframe` names the npm versions; otherwise drop the sentence in step 7. | Uberblick product (help); `SKILL.md` step 7 | 16 | ablauf §1 (renderer version lacked a kind) |
| S19 | Drawing status on write | The server answers each ablauf write with a `drawing` status. | Uberblick product (`ub mcp serve`) | 19 | |

S18 and S19 belong in the Uberblick product repository, not this skill.
