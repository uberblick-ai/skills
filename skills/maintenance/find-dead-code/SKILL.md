---
name: find-dead-code
description: >-
  Find dead code in a Python repository and report bounded removal candidates
  with caller evidence, entry-point checks and a plan for preserving useful tests.
  Use for "find dead Python code", "which functions are only used by tests?",
  "show callers before removing this" or "plan a bounded cleanup".
  Writes an evidence report and optional graphs to a scratch directory;
  changes no source, configuration, issues or PRs. Not for general refactoring,
  dependency upgrades or automatically deleting everything a scanner flags.
license: MIT
compatibility: >-
  Requires a local Python checkout, git and a text search tool such as rg.
  Optional tools: Ruff for unused imports and locals, Vulture for unused-name
  candidates, Pyan3 for static uses and module graphs, Graphviz for rendering.
  Installing analysis tools needs package-index access; reading issue and PR
  context needs the repository host's authenticated connector or CLI.
metadata:
  author: uberblick-ai
  version: "0.1"
---

# Find dead code

Find small, defensible removals. A scanner finding, zero coverage or an empty
caller graph is a lead, not proof. Keep production reachability separate from
test usage, and preserve uncertainty about dynamic and external consumers.

1. **Fix the scope and snapshot.** Read repository guidance, record the commit
   and working-tree changes, and identify production roots, tests, scripts,
   plugins and generated or vendored code. Inspect packaging and tool settings
   before choosing inputs. Record exclusions and existing suppressions. For a
   symbol request, investigate that symbol and its callers rather than scanning
   unrelated areas. Work read only; put reports and tool environments outside
   the checkout. Do not run application entry points merely to discover them.

2. **Map execution roots.** Read console-script declarations, `__main__.py`,
   executable scripts, subprocess commands, plugin registrations and framework
   discovery. Include module import side effects and documented library APIs.
   Classify roots as production, test, tooling or external/unknown. A file
   launched by pathname or `python -m` needs no ordinary import caller.
   Migrations, callbacks and hooks may be live without a lexical call site.

3. **Collect candidates in two passes.** Use the commands and limitations in
   [references/python-tools.md](references/python-tools.md). Prefer available
   tools; install optional tools only in an isolated scratch environment.
   Run unused-name analysis on production inputs, then on production plus
   tests. Compare findings at production locations: disappearing findings are
   *possibly test-only*, not automatically live or dead. Check qualified uses
   because unrelated symbols with the same name can suppress a finding.

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

   Trace backwards to an execution root and forwards through private helpers.
   A caller can itself be dead. Mutually recursive functions can form a dead
   group even though each has a caller; judge reachability from the identified
   roots, not just incoming-edge counts. Keep import, definition, reference and
   call relationships distinct. A module defining a function does not call it.
   Show small caller/callee views alongside any whole-project graph.

5. **Challenge each proposed removal.** Resolve the relevant cases:

   - **Indirect use:** `getattr`/`setattr`, string registries, decorators,
     framework overrides, fixtures, dependency injection, serialization and
     monkey patches. Follow the dispatch or registration to the definition.
   - **Exports and compatibility:** check re-exports, `__all__`, documented
     imports, supported CLI options and consumers outside the scanned tree.
     Local absence cannot settle an externally supported API's retirement.
   - **Write-only state:** inspect reflection and serialization before dropping
     an attribute. Preserve the right-hand side's effects and any other used
     assignment target, as in `local = self.old_field = compute()`.
   - **History and intent:** use `git log -S 'symbol' -- path` and inspect the
     relevant diff to find the last caller's removal or replacement. Read
     linked or matching issues/PRs when available; a refactor may deliberately
     preserve an adapter. State when tracker context is unavailable. History
     supports the current-code check; it does not replace it.
   - **Tests:** distinguish retired behavior, current behavior tested through
     an old wrapper, and deliberate test support. Recommend moving useful
     assertions to the active entry point before retiring a wrapper. Never
     count every test mentioning the candidate as safely removable.

   Existing coverage or runtime traces can confirm use. Missing execution only
   describes the observed workload, especially for recovery and scheduled
   paths. Do not add production instrumentation as part of this audit.

6. **Classify and report.** Number findings and suggested actions. For each,
   give `path:line` and qualified symbol, current production and test callers,
   indirect/export checks, history or issue evidence, remaining uncertainty,
   proposed scope and validation. Use these dispositions:

   | Disposition | Evidence required |
   | --- | --- |
   | Removal candidate | No remaining use in the stated scope after checking relevant roots, indirection and contracts; explain why the group is obsolete. |
   | Migrate first | Useful behavior or assertions still depend on the old boundary; name the replacement and preserved checks. |
   | Keep | A concrete consumer, supported contract, hook or intentional test utility remains. |
   | Unresolved | Missing consumers, dynamic dispatch or incomplete analysis prevents a decision; name the smallest check that would resolve it. |

   Write `report.md` in the scratch directory, with the snapshot, scope and
   tool commands, a numbered findings table, evidence for each proposed action,
   rejected false positives and limitations. Link any graph artifacts. Say
   which checks were actually run and which would be needed after removal.
   Estimate source and test line savings separately, explain the counting
   method and do not double-count shared helpers. Measure the real diff only
   if cleanup is subsequently implemented. Do not invent a savings target.

   Example report excerpt (illustrative):

   ```text
   Reviewed example/app at abc123, clean tree. Source: src; tests: tests.
   1. Removal candidate: src/app/labels.py:111 provision_labels, plus its
      private formatter. No production callers; two tests use the old path.
      Commit def456 replaced the production call with Doctor.create_labels.
      Preserve confirmation and EOF checks at that active entry point.
      Could save about 23 source lines; test changes need review.
   2. Keep: src/app/widgets.py:11 pane_line re-export. log_pane imports it.
      F401 does not account for that consumer.
   Action 1: retire the old label path in one change after checking the active
   confirmation tests; run those tests and the repository's required checks.
   No source or tracker changes made. Static scans ran; tests were not run.
   ```

   If there are no supported removals, say: **"No supported dead-code removals
   found in the reviewed scope. No source or tracker changes made."** List
   unresolved candidates separately rather than calling the codebase clean.

The skill ends with the report. A request to find dead code does not authorize
deletions, new suppressions, CI gates or tracker writes. Follow an explicit
cleanup request as a separate implementation task using the report's evidence.
