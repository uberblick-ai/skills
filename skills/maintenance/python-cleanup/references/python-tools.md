# Python tools and graph checks

Use existing tools where possible and record their versions. The examples
below were exercised with Vulture 2.16 and Pyan3 2.9.0. Check installed
`--help` before relying on flags in another version. These are analysis tools,
not runtime dependencies of the repository being reviewed.

## Candidate scans

Adapt `src` and `tests` to the repository's actual inputs, including production
scripts and plugins. Set `DEAD_CODE_OUT` to a scratch directory outside the
checkout. Inspect existing exclusions and configuration first.

```sh
ruff --version
ruff check src --select F401,F841 --no-fix --no-cache > "$DEAD_CODE_OUT/ruff.txt"
vulture --version
vulture src --min-confidence 60 --sort-by-size > "$DEAD_CODE_OUT/source.txt"
vulture src tests --min-confidence 60 --sort-by-size > "$DEAD_CODE_OUT/with-tests.txt"
```

These Vulture examples assume tests are outside `src`. For nested test trees,
inventory tracked Python paths and classify production, test/support,
migration and tooling inputs first. Supply the intended files or inspect
`--exclude` patterns against that inventory. Test helpers may also have tooling
consumers; classify by use as well as directory name. Keep omitted migration
and tooling consumers in a supplementary scan or qualified search. Record
the exact inputs of each pass so the comparison measures what tests add.

Compare the advisory rule selection with the repository's normal check.
In the Ruff 0.17.2 trial, explicit `--select F401,F841` enabled F841 despite
its global configuration ignore; no configuration edit was needed. Per-file
ignores and inline suppressions still apply. Inspect and report those limits
rather than treating no findings as proof of non-use or the advisory scan as
the repository's normal check.

Run the scans independently and retain each exit status. Vulture exits 3 for
findings; 1 or 2 indicates an invalid invocation or analysis error. Ruff exits
1 for violations, so neither is a reason to skip the next scan. Do not turn an
analysis failure into an empty findings list.

If tools are missing, an optional isolated setup is:

```sh
python3 -m venv "$DEAD_CODE_OUT/tools"
"$DEAD_CODE_OUT/tools/bin/python" -m pip install 'vulture==2.16' 'pyan3==2.9.0'
```

Then invoke that environment's executables by absolute path. Use an interpreter
that supports the target's syntax; no edits to project manifests or lockfiles.
If installation is unavailable, continue with qualified source searches and
report the omitted tool evidence.

[Vulture](https://github.com/jendrikseipp/vulture) compares defined and used
names without full scope resolution. A same-name method elsewhere can hide a
candidate. Its confidence values are categories of findings, not measured
probabilities that deletion is safe. Functions often appear at 60%, so an
80% or 100% scan alone misses the main subject of this audit. Tests can mask
obsolete production functions. A private helper used only by a dead function
may not be reported until the caller is removed; inspect that chain now.

[Ruff F401](https://docs.astral.sh/ruff/rules/unused-import/) flags imports
unused inside a file. Other modules can consume those imports as re-exports.
An apparently unused import can also register plugins through import side
effects. F841 covers local assignments, not all write-only object state.

## Static graphs with Pyan3

[Pyan3](https://github.com/Technologicat/pyan) builds an approximate graph of
definitions and uses across the supplied Python files. Uses include more than
function calls. It also supports a separate module import graph. Neither mode
is a complete inventory of possible runtime callers.

For a conventional `src/pkg` layout, use `--root src`, so names match imports
such as `pkg.mod.func`. Include all relevant production input directories.
For a flat layout use its import root. Check the resulting qualified names.

```sh
pyan3 --version
pyan3 src --root src --no-defines --uses --annotated --dot \
  --file "$DEAD_CODE_OUT/uses.dot"
pyan3 --module-level src --root src --text \
  --file "$DEAD_CODE_OUT/modules.txt"

# All statically found callers, including other top-level packages.
pyan3 src --root src --function pkg.mod.func --namespace '' \
  --direction up --no-defines --annotated --text \
  --file "$DEAD_CODE_OUT/callers.txt"

# Dependencies of the same symbol.
pyan3 src --root src --function pkg.mod.func --namespace '' \
  --direction down --no-defines --annotated --dot \
  --file "$DEAD_CODE_OUT/callees.dot"

# A specific path, within the analyzed graph.
pyan3 src --root src --paths-from pkg.cli.main --paths-to pkg.mod.func
```

Replace the example symbols with definitions in the repository. Repeat the
caller query with test inputs to inspect test consumers. When tests live
outside `--root`, Pyan3 2.9.0 can give them filesystem-derived namespaces;
classify them by source path and verify resolution across the boundary. For
several independent source roots, do not silently choose a common ancestor
that changes import names. The Python API's `from_sources` accepts explicit
`(source, module_name)` pairs if correct names cannot be represented by one
root. Record any portion of the project the graph cannot resolve.

Three traps observed in 2.9.0:

1. **Default namespace filtering:** `--function ... --direction up` normally
   confines traversal to the target's top-level namespace. `--namespace ''`
   allows cross-namespace callers, including separately located tests. Check
   a known cross-package caller before accepting an empty result.
2. **Text output omits isolated nodes:** it prints outgoing edges. Empty text
   does not show whether the requested target exists, has no uses, or was
   filtered away. Verify the target in the full DOT graph or analyzer first.
3. **A drawing is not an execution model:** containment edges (`defines`) do
   not establish invocation. Graph filtering may traverse those edges even
   when `--no-defines` hides them. Rendering can omit redundant import edges;
   use `--keep-subsumed-edges` when investigating imports. Manually inspect
   the exact incoming relationships before claiming a caller.

Use fully qualified nodes and preserve source locations. Treat unresolved
attribute dispatch and external nodes as unknown. Verify re-exports, callback
registration, subprocess targets and framework hooks outside the graph. A
disconnected component or mutually recursive group is a candidate only after
checking execution roots and public contracts.

DOT and text output do not require Graphviz. If `dot` is already available,
render a focused graph with:

```sh
dot -Tsvg "$DEAD_CODE_OUT/callees.dot" -o "$DEAD_CODE_OUT/callees.svg"
```

If a whole-project graph is useful and practical, keep it as an artifact and
use focused views for decisions. A large graph is optional, not a prerequisite
for a bounded finding. Record analyzed files, exclusions and elapsed time.
When filtering a view, retain the raw incoming relationships for the selected
symbols so omitted imports or comprehension scopes remain inspectable.

Label a graph collapsed from symbol uses as **module uses**, not module
imports: references between functions are not import statements. Unknown or
external nodes remain analysis limits. Graph size does not establish coverage.
For Python API exports, plain node/edge records with qualified names and source
locations are enough; the whole analyzer object need not be serializable.

## Other available tools

- [pydeps](https://github.com/thebjorn/pydeps) is useful for module import
  dependencies and cycles when already in use. It does not answer which
  functions call a particular method.
- [code2flow](https://github.com/scottrogowski/code2flow) makes approximate
  call graphs, but documents skipped ambiguous same-name functions and
  generated functions. Account for those omissions before interpreting it.
- [PyCG](https://github.com/vitsalis/PyCG) is archived. Do not make its original
  package a new default without checking compatibility with the target Python.
- [TLDR](https://github.com/parcadei/llm-tldr) offers calls, impact and dead-code
  queries as part of a broader indexing workflow. Use it if the repository
  already has it, and check roots, exclusions and resolution as above. This
  skill does not need its daemon or semantic index.

Existing runtime traces and coverage add observed calls, not a proof of
non-use. Keep test execution evidence separate from production observations.
