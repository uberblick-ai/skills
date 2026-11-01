# Findings behind python-cleanup

Checked on 2026-11-01 against `uberblick-ai/ub-agents` at `6956308`.
The repository was read only. Tool trials used an exported snapshot and an
isolated Python 3.12.8 environment with Vulture 2.16 and Pyan3 2.9.0.

## Lessons from the code audit

| Observation | Consequence for the skill |
| --- | --- |
| `labels.provision_labels` has two test callers and no production caller; commit `e9387cf` replaced the production path. Its private `print_commands` helper remains referenced by that dead root. | Separate production from tests, use history as supporting evidence and follow private helper chains. |
| `view_data.outcomes_today`, `Session.freshness`, `item_context` and `outcome_text` remain exercised by tests after their production consumers changed. | Tests can conceal obsolete paths. Move useful assertions to active behavior before retiring wrappers. |
| Ruff F401 reported 12 imports. Four were consumed as re-exports, including `view_widgets.pane_line` by production `view_log_pane`. | A local unused-import finding does not establish that the export is unused. |
| `local = self._requests_before = ...` writes an unused field, but the local is read later. `_discovery_requests` is also write-only. | Inspect assignment targets separately and preserve computation and effects. |
| `_attach_tail` is read by `getattr`; Textual invokes overrides; `helper_command.py` is launched by pathname. | Bare identifier and import counts miss live dynamic and process entry points. |
| Closed refactor issues #701 and #705 deliberately retained delegation and import boundaries. | Check linked decisions before treating an adapter as accidental residue. |
| The `doctor.diagnose` test convenience and approval wrappers have different roles and migration costs. | Test-only does not mean disposable. Keep intentional helpers; migrate security assertions carefully. |

The first two rows describe six functions totaling 51 physical definition
lines, using AST start/end positions. That is an estimated source reduction,
not an implemented deletion or a count of safely removable tests. No dead-code
cleanup was applied.

## Tool trial

Commands were run from the snapshot, using the temporary environment's
executables:

```sh
vulture src --sort-by-size
vulture src tests --sort-by-size
pyan3 src/ub_agents --root src --no-defines --uses --text --file uses.txt
pyan3 --module-level src/ub_agents --root src --text --file modules.txt
pyan3 src/ub_agents/labels.py tests/test_labels.py --root src \
  --function ub_agents.labels.provision_labels --direction up \
  --no-defines --annotated --text --file callers-default.txt
pyan3 src/ub_agents/labels.py tests/test_labels.py --root src \
  --function ub_agents.labels.provision_labels --namespace '' --direction up \
  --no-defines --annotated --text --file callers-cross-namespace.txt
```

- Production-only Vulture: 112 findings. With tests: 68 findings, of which
  51 were in production files and 17 in tests. Both returned status 3,
  meaning findings, not a failed scan. Counts are leads, not confirmed removals.
- `provision_labels`, `outcomes_today`, `freshness`, `item_context` and
  `outcome_text` appeared in the first scan and disappeared in the second.
  `print_commands` did not appear because the obsolete wrapper still uses it.
- The module graph and whole-production uses graph completed successfully.
- The default filtered caller query printed nothing even with the two test
  callers supplied. The cross-namespace query printed both known tests.
  Inspecting the installed analyzer confirmed its default namespace filter;
  inspecting the text writer confirmed it only prints edges, not isolated nodes.
- An analyzer inspection also resolved the live `LogPane.render_line` use of
  `view_status.pane_line` through its re-export. Other dispatch still needs
  source inspection. This is a spot check, not a precision/recall benchmark.

## Existing skills and tool choice

Searched the skills.sh directory and ran `npx skills@latest find 'dead code'`.
Read the source instructions rather than judging names or install counts alone.

| Existing skill | Assessment for this task |
| --- | --- |
| [parcadei/continuous-claude-v3: dead-code](https://github.com/parcadei/continuous-claude-v3/blob/main/.claude/skills/dead-code/SKILL.md) | Closest integrated alternative: `tldr dead`, custom entry patterns and `tldr impact`. The short recipe does not cover the test-only, re-export and graph-validation decisions above. Directory search reported 734 installs; repository metadata reported 3,947 stars. |
| [laurigates/claude-plugins: vulture-dead-code](https://github.com/laurigates/claude-plugins/blob/main/python-plugin/skills/vulture-dead-code/SKILL.md) | Useful tool overview, but recommends high thresholds that omit many unused functions, broad decorator ignores and adding development dependencies. Directory search reported 327 installs; repository metadata reported 59 stars. |
| [skillmedev/skills: Dead Code Eliminator](https://www.skills.sh/skillmedev/skills/dead-code-eliminator) | Broad removal workflow, with mandatory production observation windows and a deletion PR as the deliverable. Its default removal workflow does not fit an audit request or the requested bounded, report-first cleanup. |

Install and star counts are observations on the check date, not quality
guarantees. No third-party skill was installed or copied into this skill.

The implementation uses established tools as optional evidence sources.
Vulture generates candidates; Pyan3 supplies function uses and module graphs;
the agent checks reachability, history and intent. It adds no custom Python
call-graph resolver. The tool reference records the version-specific pitfalls
observed here. pydeps covers imports; code2flow documents ambiguity omissions;
the original PyCG is archived. TLDR remains an option for repositories already
using it. None establishes every possible Python runtime caller.

## Review of the cleanup workflow

The maintainer requested the name `python-cleanup`, a pre-execution report,
a recommendation to work one area at a time, and confirmation of test removals
except minor or obvious leftovers. Claude reviewed the plan through Claude
Code with tools disabled and returned "approve with changes."

The resulting workflow addresses three gaps: pending decisions hold the
affected area before source edits; only removal candidates and explicit
migrations may be executed; and baseline checks plus failure handling prevent
deleting or weakening tests simply to get a passing result. The report format
makes the scope, test impact and decisions concrete.

The review also tightened exceptions for parameter cases, mock and existence
assertions, side-effecting setup and implicit fixtures. Approval carries across
unchanged scope; material new behavior needs preservation or a new decision.
Collected test cases can be compared when the existing runner supports it,
alongside inspection of assertion changes. Dirty files do not by themselves
require permission, and environmental failures do not establish a live caller.

The plan review was independent; it was not an execution test of the completed
skill. The following scenario checks apply the final rules to concrete cases:

| Case | Required disposition/action |
| --- | --- |
| `provision_labels` and its formatter, with two meaningful test callers | Removal/migration candidates in one area. Map confirmation and EOF behavior to the active path; any remaining test removal needs a numbered decision before editing that area. |
| `view_widgets.pane_line` consumed by `view_log_pane` | Keep the live re-export despite F401. |
| `_attach_tail` read by `getattr`, or `helper_command.py` launched by path | Keep the dynamic/process entry point; absence of ordinary calls or imports is insufficient. |
| An unread setup field assigned from a seeding call | Preserve the call's effects; only the binding may be a leftover. |
| An unused test import with no side effects, or a stub that exercises nothing | With cleanup authorized, report the exception and proceed without asking. |
| A one-line export assertion, a parameter case or an implicitly requested fixture | The assertion/case is meaningful coverage; confirm its removal. Keep the fixture with a consumer. |
| Generic cleanup permission given before any test-removal proposal | Show the report and batch the precise decisions; edit nothing in the affected area while pending. |
| A new consumer discovered after an approved removal starts | Stop that removal, restore the affected cleanup edits if necessary and reclassify. Do not delete the consumer's test. |
| An approved test gains an assertion about active behavior | Preserve or migrate that assertion; a proposal to drop it needs a new decision. Formatting-only changes do not require re-approval. |
| Existing user edits or an environmental test failure | Preserve the edits and distinguish baseline/environment failures from new regressions; do not manufacture approval gates or change tests to hide failures. |

These are manual scenario checks, not a measured guarantee of future agent
behavior. The actual tool trials above remain the evidence for graph and
unused-name behavior on ub-agents; no ub-agents code or tests were removed.

## Framework dry run and version 0.3

A second read-only dry run on 2026-11-01 exercised the skill on a Django,
Django Ninja and Celery backend. The backend-specific report, paths and raw
graphs remain outside this repository. These are the reusable observations:

| Observation | Change to the skill |
| --- | --- |
| Tests and factories were nested under the source root; migrations and operational scripts had separate execution roles. | Require distinct input sets, and retain omitted migration/tooling consumers in searches or a supplementary scan. |
| Many unused-name findings were mounted handlers, schema resolvers, signals or tasks invoked through strings. | Add a conditional framework reference that distinguishes registration from an identified consumer and leaves unchecked external task producers unresolved. |
| A 90-line retired reader had five exclusive helpers totaling another 219 definition-span lines. Shared schemas remained live through another builder. | Check outside callers for every group member and retain shared dependencies. |
| One compatibility assertion called the retired reader; a supported route used a different reader. | Map the scenario to the actual mounted path rather than deciding from a function's version suffix. Keep every meaningful assertion or request confirmation. |
| The proposed async test rewrite needed to remove a redundant local import; otherwise its earlier use would be locally unbound. | Inspect binding and sync/async details of the concrete rewrite; report static and runtime feasibility separately. |
| The configured Ruff rules ignored F841. | Verify explicit advisory rule selection and report remaining per-file/inline suppression limits without editing the configuration. |
| A graph of more than 2,000 source/test files completed in about 84 seconds, with roughly 200,000 uses edges. | Make whole-project graphs optional, retain focused raw edges, and label collapsed module uses separately from import graphs. |
| Test collection succeeded, but an autouse database fixture made every attempted test need unavailable PostgreSQL. Docker was also unavailable. | Check test-service prerequisites before execution, avoid multiplying the same setup error and continue audits with an explicit runtime limit. |

Tools were Python 3.13.11, Vulture 2.16, Pyan3 2.9.0 and Ruff 0.17.2.
Production-only Vulture produced 1,657 findings; 185 disappeared with tests.
Those counts are candidates, not verified removals. The graph contained the
selected definitions, their known test caller, active API callers and a
cross-package fixture-to-helper control edge.

The repository's format/lint check passed. A 93-case related set collected;
execution of the initial 31-case subset produced database setup errors, not
passing tests. The proposed three-assertion migration compiled and passed
Ruff in memory only. No cleanup or runtime verification of that migration
was performed. The dry run was conducted by the authoring agent, not an
independent behavioral evaluation of version 0.3.

Additional decision checks for the new reference:

| Case | Required disposition/action |
| --- | --- |
| Task named by a live beat schedule but no lexical caller | Keep; the schedule is a concrete consumer. |
| Registered task with no local producer and unchecked queued/external consumers | Unresolved; neither automatic deletion nor an assertion that registration proves active use. |
| Old-version helper still used by a mounted supported route | Keep regardless of its suffix. |
| Resolver on a schema with no established consumer | Trace the schema; framework naming alone does not prove that the schema is live. |
| Test-only client reset called by an autouse fixture | Keep intentional support. |
| Collection and lint succeed while the test database is unavailable | Continue the audit, state runtime verification is unavailable, and preserve the tests. |

These checks review decisions against observed cases. They do not claim an
independent agent trial or a post-removal test pass.

A separate scratch fixture exercised the revised scan guidance: a nested
test hid its source function only in the source-plus-tests pass, while a
migration consumer hid another function only when migration inputs were
included. With Ruff 0.17.2, explicit `--select F401,F841` reported a local that
the normal globally ignored F841 check omitted. This trial removed an
unnecessary ignore-list override from the proposed instructions. No fixture
code or analysis dependencies were added to the skill package.

## Public-library dry run and version 0.4

A third read-only dry run used `python-cleanup` 0.3 on
[`celery/celery` at `57cb15f`](https://github.com/celery/celery/tree/57cb15ff99ab47a6e72d5a70c5522b8fabb59a57)
on 2026-11-01. It scanned 161 package files, 242 test/support files and 48
supplemental Python files. Vulture 2.16 reported 258 package-only findings;
123 disappeared with tests. These are leads, not verified dead symbols.

| Observation | General guidance added in 0.4 |
| --- | --- |
| Seven apparently unused `AsynPool` methods were invoked by the installed Billiard 4.3.1 superclass, including an empty override. | Inspect standard-library and dependency hook callers at relevant versions; removing an override can expose different parent behavior. |
| Pyan3 2.9.0 on Python 3.12.8 failed on the 403-file package-plus-tests graph with a scope `KeyError`. A six-file graph resolved the selected target and known cross-package consumers. | Preserve failure evidence, use focused graphs or source inspection, and report their actual input coverage. Missing nodes and failed analysis do not establish non-use. |
| The strongest candidate was already proposed in an open PR. Its description still listed pool-method removals that its current diff had restored. | Read the checked PR head/diff and discussion; distinguish remaining scope from abandoned changes and resolved review concerns. |

The supported first area was the private `_start_worker_process` helper:
22 definition-span lines including its decorator, with no test removals.
Eight existing focused tests collected and passed on the unchanged snapshot
using an in-memory broker. No deletion or post-removal verification was run.

The current diff and discussion of
[PR #10201](https://github.com/celery/celery/pull/10201), checked at head
`1e128a82ad5b74390a8ee9634fa29de93ef9f0dc`, corroborated both the candidate and
the inherited-hook trap. The author had already restored those hooks. The
recommendation was to review or isolate the existing bounded change, not
create a duplicate PR or endorse all its other removals.

This is qualitative evidence from an author-run audit, not an independent
evaluation or a precision estimate over all findings. Repository names,
symbols and commits stay in this evidence document; the added workflow rules
apply to Python applications and libraries generally.
