# Pre-execution report

Write `report.md` outside the checkout and show the actionable section in the
conversation before cleanup edits. A report for an audit can end with the
recommended area and its decisions. Cleanup uses that same report, updated
when evidence or scope changes. Keep a broad inventory brief and the selected
area concrete.

Use this shape, omitting empty optional sections:

```text
Python cleanup: OWNER/REPO at COMMIT
Mode: audit | cleanup requested
Snapshot: relevant working-tree changes; inputs, exclusions and tool versions

1. Recommended area: NAME
   Why this area first; feature boundary; files and exact symbols affected.
   Source changes proposed; estimated source/test line changes, counted how.

2. Findings
   ID | path:line / symbol | disposition | evidence | remaining uncertainty
   Distinguish production/test callers, dynamic roots and public contracts.
   Include relevant history/issue links and rejected false positives.

3. Test impact
   ID | test/case/assertion | retain/migrate/remove | behavior protected
   For migrations: old scenario/check -> new scenario/check and location.
   For removal: what guarantee disappears and what still covers active behavior.

4. Decisions before execution
   D1. Exact test removals or interface retirement, reason and consequences.
   D2. ...
   Status: pending | approved (scope of the user's answer) | declined.
   If none: No pending decisions for this area.

5. Minor leftovers
   Exact import/binding/helper/stub, no-use evidence and side-effect checks.
   State why each qualifies for the confirmation exception.

6. Validation
   Baseline checks run and their results, including pre-existing failures.
   Commands planned after edits; collected-case comparison if supported.
   Tool/coverage limitations and unavailable checks.

7. Other areas (optional)
   Numbered inventory for later. No unrelated changes in this area.

After execution:
   Actual changes, source/test diff counts and what those counts measure.
   Approved removals and minor exceptions applied; verification results.
   Any restored edits or unresolved findings; next recommended area.
```

Example actionable reply (illustrative):

```text
I recommend one area first: the retired label-provisioning path. Its wrapper
has only two test callers; one private formatter is used only by that wrapper.

1. Remove the wrapper and formatter. Could save about 23 source lines,
   measured from their definition spans; test changes are counted separately.
2. Move confirmation and EOF checks to the active Doctor entry point,
   preserving their inputs, expected writes and refusal behavior.
3. Decision D1: remove test_legacy_command_listing, which checks only the
   retired interface's output. Doctor label creation remains covered.

Cleanup was requested, but D1 needs confirmation before edits to this area.
Do you approve D1? The full evidence and planned checks are in report.md.
```

Ask about all pending decisions for the area together, with the precise test
names and consequences. If cleanup is authorized and only verified minor
leftovers are involved, state them and proceed after presenting the report.
Do not add a confirmation request just because a report was written.

Example result:

```text
Completed area 1: retired label provisioning. Removed the agreed wrapper,
formatter and approved legacy test; preserved confirmation and EOF checks
on the active path. Focused tests and required checks pass.
Actual change: 23 source lines removed; 8 test lines added, 14 removed.
Next recommendation: area 2, retired view helpers. No edits there yet.
```
