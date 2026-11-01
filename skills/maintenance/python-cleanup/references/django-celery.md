# Django, Ninja and Celery roots

Read this when these frameworks occur in the reviewed scope. Use the main
workflow's dispositions and test-removal policy; framework registration is
additional evidence, not a blanket whitelist or a reason to abandon the audit.

## Resolve registration and consumers

| Surface | Inspect | What the evidence establishes |
| --- | --- | --- |
| Django apps and signals | `INSTALLED_APPS`, `AppConfig.ready()`, imported signal modules, `@receiver` and `.connect()` | A live app may invoke hooks and import modules for registration without ordinary calls to their functions. |
| Ninja routes | Mounted API instances in URL configuration, `add_router`, dynamic route imports and router decorators | Trace the mounted version to its actual handler. An old version suffix on a helper does not prove that supported routes stopped using it. |
| Schemas | Active response/schema consumers, `resolve_*`, validators, serializers and model hooks | A resolver or validator on a consumed schema is invoked by the framework. An unconsumed schema needs its own reachability check. |
| Django commands | Installed apps, `management/commands`, `call_command`, deployment scripts and operator docs | `Command.handle` can be an operational entry point with no Python caller. |
| Migrations | Migration graph, `RunPython`, serialized callable paths and imports | Migration loading and replay are consumers. Keep migrations in consumer searches even when excluded from candidate scans. |
| Celery tasks | `@shared_task` / `@app.task`, explicit task names, autodiscovery, custom discovery, `.delay`, `.apply_async`, signatures/chains and `send_task` | Registration makes a task addressable. It does not by itself establish an active producer or justify removal. |
| Celery schedules | Beat configuration, app startup registration, database-backed schedules and operational senders | A qualified string in a live schedule is a consumer even when static tools find no call. |

For tasks with no local producer, consider queued messages, stored schedules
and external senders. Use available configuration, docs and authorized
read-only records. If those consumers cannot be checked, mark the task
**unresolved** and name the missing evidence. Do not start workers, enqueue
tasks or load application entry points merely to discover registrations.

For a retired reader or service, follow its helpers beyond the scanner's
finding. A helper can appear used solely because the retired root calls it.
Check outside callers for every member, including imports and strings. Keep
shared cache builders, schemas and utilities consumed by supported paths.
An import becoming unused in the old module does not retire its definition.

## Tests and environment

Read the relevant `conftest.py` chain, plugins and fixture configuration.
Autouse fixtures may seed a database, reset a client or patch network effects
for every test, including ones whose body looks pure. A client reset helper
used only by such a fixture is intentional support, not an obsolete wrapper.

Before baseline execution, identify the repository's test settings and
required local services. Check their availability with the project's normal
tools. In a database-backed suite, a small representative run can expose a
setup failure before repeating it across many cases. Follow the repository's
test setup procedure within the user's scope; do not reset shared services or
substitute a development/production database to bypass unavailable test infra.

Successful collection establishes discovered case IDs, not passing behavior.
If the test service is unavailable, continue the static audit and report the
runtime limit. A dry run does not need infrastructure deployment to produce
its report. Preserve the distinction between a setup error and a failing
assertion; leave tests intact in either case.

## Migrate a useful assertion, not just its function name

Map the original inputs and every check to a supported execution path. For
example, an obsolete synchronous feed reader may have one assertion that a
new notification kind is absent. Move that scenario to the cached reader
actually used by a supported route, keeping the other compatibility checks.
Do not discard the assertion because the old endpoint was retired.

Inspect the concrete rewrite's sync/async boundary, return shape and imports.
A later function-local import binds that name throughout the function: an
earlier use introduced by the migration can raise `UnboundLocalError`, even
when the same name is imported at module scope. Remove a redundant local
import only after verifying that the surviving binding supplies the same
object and has no required effect.

Compilation and lint can catch mistakes in a proposed rewrite without editing
the checkout; they do not prove the behavioral mapping. Record whether the
migration was only proposed, checked statically or exercised at runtime.
Confirm any lost scenario or assertion under the main skill's policy.
