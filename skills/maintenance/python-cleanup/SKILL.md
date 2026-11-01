---
name: python-cleanup
description: >-
  Identify dead Python code and, when asked, remove it in bounded areas after
  reporting the evidence and test impact.
  Use for "find dead Python code", "which functions are only used by tests?",
  "plan a bounded cleanup" or "clean up this area after reporting test impact".
  Writes a pre-execution report and optional graphs; changes source and tests
  only for authorized cleanup, with confirmation for meaningful test removals.
  Not for general refactoring, formatting, dependency upgrades or automatically
  deleting everything a scanner flags.
license: MIT
compatibility: >-
  Requires a local Python checkout, git and a text search tool such as rg.
  Optional tools: Ruff for unused imports and locals, Vulture for unused-name
  candidates, Pyan3 for static uses and module graphs, Graphviz for rendering.
  Installing analysis tools needs package-index access; reading issue and PR
  context needs the repository host's authenticated connector or CLI.
  Cleanup uses the repository's existing test runner and development checks.
metadata:
  author: uberblick-ai
  version: "0.4"
---

# Python cleanup

Find small, defensible removals. A scanner finding, zero coverage or an empty
caller graph is a lead, not proof. Keep production reachability separate from
test usage, and preserve uncertainty about dynamic and external consumers.

An audit request ends with a report. An explicit cleanup request can continue
through execution after the report, subject to the decisions below. Always
recommend working on one coherent area at a time and explain the choice.

1. **Fix the scope and snapshot.** Read repository guidance, record the commit
   and working-tree changes, and identify production roots, tests, scripts,
   plugins and generated or vendored code. Inspect packaging and tool settings
   before choosing inputs. Record exclusions and existing suppressions. For a
   symbol request, investigate that symbol but search for callers throughout
   the repository. Keep the audit read only; put reports and tool environments
   outside the checkout. Do not run application entry points merely to discover
   them. Preserve user edits; ask about overlapping changes only when their
   ownership or intended treatment cannot be resolved safely.

2. **Map execution roots.** Read console-script declarations, `__main__.py`,
   executable scripts, subprocess commands, plugin registrations and framework
   discovery. Include module import side effects and documented library APIs.
   Classify roots as production, test, tooling or external/unknown. A file
   launched by pathname or `python -m` needs no ordinary import caller.
   Migrations, callbacks and hooks may be live without a lexical call site.
   For Django, Django Ninja or Celery, read
   [references/django-celery.md](references/django-celery.md) to check route,
   schema, signal and task registration against actual consumers.

3. **Collect candidates in two passes.** Use the commands and limitations in
   [references/python-tools.md](references/python-tools.md). Prefer available
   tools; install optional tools only in an isolated scratch environment.
   Run unused-name analysis on production inputs, then on production plus
   tests. Compare findings at production locations: disappearing findings are
   *possibly test-only*, not automatically live or dead. Check qualified uses
   because unrelated symbols with the same name can suppress a finding.
   When tests live under source, build separate input sets; scanning `src`
   already includes them. Keep migrations and tooling in consumer searches
   even when they are outside the candidate scan or graph, and report that
   difference in scope.

   Include unused functions, private helper chains, constants, write-only
   state, imports and unreachable statements. Ruff's F401 is local to the
   importing file; check consumers of that module's exports. Keep the initial
   broad results, then investigate coherent groups with the clearest evidence.
   Do not hide uncertain functions with a high confidence threshold or generate
   blanket whitelists to make the results disappear.

4. **Trace callers and dependencies.** For each promising group, locate exact
   definitions and inspect imports, aliases, attribute references and strings
   across source, tests, configuration, scripts and docs. Use Pyan3 when a
   graph makes this easier. Verify the graph contains the target and a known
   caller, including a caller in another package, before interpreting absence.
   Record inputs, tool version, filters, missing modules and analysis errors.
   If broad analysis fails, retain the failure and attempted inputs, then use
   a focused graph or qualified source inspection with explicit coverage limits.
   A failed build or a missing target node is not evidence of zero callers.

   Trace backwards to an execution root and forwards through private helpers.
   A caller can itself be dead. Mutually recursive functions can form a dead
   group even though each has a caller; judge reachability from the identified
   roots, not just incoming-edge counts. Keep import, definition, reference and
   call relationships distinct. A module defining a function does not call it.
   Show small caller/callee views alongside any whole-project graph.
   For a proposed group, check each member for callers outside that group.
   Keep shared schemas and helpers even when the old root imports them.

5. **Challenge each proposed removal.** Resolve the relevant cases:

   - **Indirect use:** `getattr`/`setattr`, string registries, decorators,
     framework overrides, fixtures, dependency injection, serialization and
     monkey patches. Follow the dispatch or registration to the definition.
   - **Inherited and protocol use:** inspect relevant base classes and hook
     callers in the standard library and dependency sources matching the
     project's versions, not just the checkout. Record the caller and version.
     Removing even an empty override can expose different parent behavior;
     a private name or an "unused" comment does not make it dead. If this
     evidence is needed but unavailable, leave the candidate unresolved.
   - **Exports and compatibility:** check re-exports, `__all__`, documented
     imports, supported CLI options and consumers outside the scanned tree.
     Local absence cannot settle an externally supported API's retirement.
   - **Write-only state:** inspect reflection and serialization before dropping
     an attribute. Preserve the right-hand side's effects and any other used
     assignment target, as in `local = self.old_field = compute()`.
   - **History and intent:** use `git log -S 'symbol' -- path` and inspect the
     relevant diff to find the last caller's removal or replacement. Read
     linked or matching issues/PRs when available; a refactor may deliberately
     preserve an adapter. For overlapping work, read the current PR head/diff
     and relevant discussion: descriptions may retain abandoned scope, and
     review objections may already be resolved. Record existing work and what
     remains instead of recommending a duplicate. State when tracker context
     is unavailable. History supports the current-code check; it does not
     replace it.
   - **Tests:** distinguish retired behavior, current behavior tested through
     an old wrapper, and deliberate test support. Recommend moving useful
     assertions to the active entry point before retiring a wrapper. Never
     count every test mentioning the candidate as safely removable.
     Inspect the concrete rewrite for imports, local-name binding, async
     execution and fixture changes as well as its behavioral mapping. Mark
     compilation or lint-only feasibility checks as static, not runtime proof.

   Existing coverage or runtime traces can confirm use. Missing execution only
   describes the observed workload, especially for recovery and scheduled
   paths. Do not add production instrumentation as part of this audit.

6. **Choose one area and present the pre-execution report.** Group findings by
   a coherent feature or behavior, with its private helpers and affected tests.
   Recommend one bounded area to start with and explain why. A broad inventory
   can cover several areas; detail the next change for the selected area only.
   Queue unrelated findings for later. If the user authorizes several areas,
   process and verify them one at a time without re-asking for agreed work.

   Number findings and suggested actions. For each, give `path:line` and
   qualified symbol, production and test callers, indirect/export checks,
   history or issue evidence, remaining uncertainty and proposed scope. Use
   these dispositions:

   | Disposition | Evidence required |
   | --- | --- |
   | Removal candidate | No remaining production use or supported external contract found after checking relevant roots and indirection; account separately for tests and explain why the group is obsolete. |
   | Migrate first | Useful behavior or assertions still depend on the old boundary; name the replacement and preserved checks. |
   | Keep | A concrete consumer, supported contract, hook or intentional test utility remains. |
   | Unresolved | Missing consumers, dynamic dispatch or incomplete analysis prevents a decision; name the smallest check that would resolve it. |

   Read [references/report.md](references/report.md) and write `report.md` in
   the scratch directory. Present its actionable section in the conversation
   before any cleanup edits. Include exact changes, tests to retain/migrate/
   remove, old-to-new behavioral checks, numbered decisions, minor-leftover
   exceptions, validation and uncertainty. Link graph artifacts and name checks
   actually run separately from planned checks. Estimate source and test line
   changes separately, state the counting method and avoid double-counting
   shared helpers. Do not invent a savings target.

7. **Resolve decisions before editing the selected area.** An audit request
   stops after the report. Cleanup already authorized can proceed when there
   are no pending decisions. Otherwise, ask once for the grouped decisions and
   wait before editing that area; do not remove source and leave its tests
   broken while seeking confirmation.

   Explicit approval of the presented report covers its clearly listed
   decisions; partial approval covers only the named subset. Earlier generic
   cleanup permission does not confirm test removals not yet shown. Record
   what was approved and do not ask again for the same scope. If the relevant
   behavior changes after the report, preserve it or obtain a new decision
   before removing it; formatting and unrelated changes do not invalidate
   approval.

   Apply this test-removal policy:

   | Proposed change | Rule |
   | --- | --- |
   | Remove a meaningful test, parameter case or assertion, including mock and export/existence assertions | Confirm first, naming the behavior lost. Few lines do not make a removal minor. |
   | Retire tests for obsolete behavior, including skipped/xfail cases, or remove/relax snapshot or golden-file checks | Confirm first. Explain the guarantees lost and the coverage retained. |
   | Migrate checks from an obsolete wrapper to the active path | Proceed within authorized cleanup when the behavioral mapping preserves every assertion and scenario; confirm any loss. Case counts alone do not prove preservation. |
   | Remove minor or obvious leftovers: unused test imports, unused bindings, unreferenced support code or truly empty stubs | May proceed without confirmation; list each exception with evidence that it exercises/protects no behavior and has no implicit use or required effects. |

   Check fixture discovery, autouse, scope, `usefixtures`, `getfixturevalue`
   and plugins before calling a fixture unused. A test with no explicit
   assertion may still check successful execution or teardown. Preserve setup
   effects: an unread `self.db` does not justify deleting `seed_database()`
   from `self.db = seed_database()`. Check import side effects too.

   Fixtures, helpers and data used exclusively by confirmed test removals may
   go with them after verifying no remaining consumers; list them and do not
   extend that approval to other tests. Uncertain exceptions need confirmation.
   Retiring a supported public API or CLI contract also needs explicit
   authorization beyond generic dead-code cleanup; an internal re-export alone
   does not imply such a contract.

8. **Execute and verify the selected area.** Recheck the relevant snapshot and
   approval scope. Before running a baseline or migration trial, including in
   an audit, inspect the runner and autouse fixtures for required services.
   Check the repository's test-service configuration and availability first;
   fixtures can make apparently pure tests depend on a database. If setup is
   unavailable, record the missing prerequisite and continue the audit without
   claiming runtime verification. Do not repeat a known setup failure across
   larger suites unless its cause has changed.

   Run focused tests before cleanup edits to establish a baseline; record
   pre-existing failures or unavailable checks. Where the existing runner
   supports it, capture collected test cases before and after. Collection is
   not execution. Do not install a new test framework just to collect IDs.

   Execute only removal candidates and migrate-first items with a concrete
   preservation plan. Leave keep and unresolved items alone. Remove immediate
   private leftovers within the area only after checking their consumers and
   effects. New meaningful test removals still require confirmation.

   If an unexpected consumer appears, stop that removal and reassess it.
   Updating the report does not by itself authorize widening the change. Queue
   unrelated work or resolve the new decision before proceeding with it.

   Run focused tests and repository-required checks after editing. Investigate
   new failures and collection errors. Compare any collected cases and inspect
   test diffs for lost assertions or scenarios even when case counts match.
   Never delete, skip, weaken tests or regenerate expected outputs merely to
   make the cleanup pass. If a real consumer breaks, or a suspected regression
   cannot be resolved, restore only the affected edits from this cleanup and
   revise the finding. Do not overwrite user changes or treat an environmental
   or pre-existing failure as proof that the candidate is live. State any
   validation limit and do not claim success with unresolved regressions.

   Finish by updating the report with actual source/test changes, checks and
   results, remaining uncertainty and the next recommended area. Follow the
   user's existing authorization for commits or PRs; this skill itself grants
   no permission to publish changes, add suppressions or introduce CI gates.

If there are no supported removals, say: **"No supported dead-code removals
found in the reviewed scope. No source or tracker changes made."** List
unresolved candidates separately rather than calling the codebase clean.
