import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intake  # noqa: E402

SCRIPT = Path(__file__).resolve().parent / "intake.py"


# A stand-in for `ub mcp serve`: answers the tools intake.py calls and logs each call. The workspace already has
# a page titled Alpha, and the first unpin_doc fails as it does when the page is unpinned already.
FAKE_UB = r"""
import json, sys
log = open(sys.argv[1], "a")
unpins = 0
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m:
        continue
    result = {}
    if m["method"] == "tools/call":
        name, args = m["params"]["name"], m["params"]["arguments"]
        log.write(json.dumps({"name": name, "arguments": args}) + "\n"); log.flush()
        error, text = False, "{}"
        if name == "list_docs":
            docs = [] if args.get("kind") else [{"title": "Alpha", "uuid": "uuid-existing"}]
            text = json.dumps({"workspace": "w", "docs": docs})
        elif name == "create_doc":
            text = json.dumps({"uuid": "uuid-" + args["title"]})
        elif name == "get_sidebar":
            text = json.dumps({"groups": []})
        elif name == "unpin_doc":
            unpins += 1
            error, text = unpins == 1, "not pinned"
        result = {"content": [{"type": "text", "text": text}], "isError": error}
    print(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": result}), flush=True)
"""


def doc(title, body, **meta):
    lines = ["---", f"title: {title}", f"description: {meta.pop('description', 'About ' + title)}"]
    for k, v in meta.items():
        lines.append(f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}")
    return "\n".join(lines + ["---", "", body])


class Blocks(unittest.TestCase):
    def test_blocks_and_inline_runs(self):
        meta, blocks, refs = intake.parse_doc(doc("Send", (
            "Upload a **PDF** and see [Roles](ref:roles).\n\n"
            "## Recipients\n\n"
            "- one `-p`\n  - nested\n1. first\n\n"
            "| a | b |\n| --- | --- |\n| [x](ref:other) | 2 |\n\n"
            "```ablauf\nflow v0\n```\n\n"
            "```terminal\n$ glow\n```\n\n"
            ":::card\ntitle: Hi\n\nBody\n:::\n\n> quoted\n> more\n"), tags=["signing"], tldr="Short."))
        self.assertEqual(meta["tags"], ["signing"])
        self.assertEqual(refs, {"roles", "other"})
        types = [b["type"] for b in blocks]
        self.assertEqual(types, ["paragraph", "heading", "list-item", "list-item", "list-item", "table", "code",
                                 "terminal", "card", "quote"])
        para = blocks[0]
        self.assertEqual(para["text"], "Upload a PDF and see Roles.")
        self.assertIn({"text": "PDF", "marks": {"bold": True}}, para["inline"])
        self.assertIn({"text": "Roles", "marks": {"docLink": {"$doc": "roles"}}}, para["inline"])
        self.assertEqual(blocks[3]["indent"], 1)
        self.assertEqual(blocks[4]["list"], "ordered")
        self.assertEqual(blocks[6]["language"], "ablauf")
        self.assertEqual(blocks[9]["text"], "quoted more")

    def test_refusals(self):
        with self.assertRaisesRegex(ValueError, "mermaid"):
            intake.parse_doc(doc("A", "```mermaid\ngraph TD\n```\n"))
        with self.assertRaisesRegex(ValueError, "neither https"):
            intake.parse_doc(doc("A", "See [the code](src/main.go).\n"))
        with self.assertRaisesRegex(ValueError, "frontmatter"):
            intake.parse_doc("# No frontmatter\n")


class Scan(unittest.TestCase):
    def test_guesses(self):
        facts = {"headings": ["Status", "Context", "Decision"], "fences": {}, "words": 300}
        self.assertEqual(intake.guess_class("docs/notes/0003-sync.md", facts)[0], "decision")
        plain = {"headings": ["What is it?"], "fences": {}, "words": 500}
        self.assertEqual(intake.guess_class("AGENTS.md", plain)[0], "harness")
        self.assertEqual(intake.guess_class(".github/ISSUE_TEMPLATE/bug.md", plain)[0], "harness")
        self.assertEqual(intake.guess_class("CONTRIBUTING.md", plain)[0], "technical")
        self.assertEqual(intake.guess_class("upcoming-release-notes/123.md", plain)[0], "changelog")
        self.assertEqual(intake.guess_class("docs/guide.md", plain)[0], "product")

    def test_test_kinds_and_topics(self):
        self.assertEqual(intake.test_kind("packages/app-tests/e2e/admin/search.spec.ts", ""), "e2e")
        self.assertEqual(intake.test_kind("tests/test_cli.py", "CliRunner()\nCliRunner()\n", 4), "cli")
        self.assertEqual(intake.test_kind("tests/test_models.py", "def test_a(): pass", 1), "unit")
        self.assertEqual(intake.topic_of("packages/app-tests/e2e/admin/search.spec.ts"), "admin")
        self.assertEqual(intake.topic_of("tests/test_cli.py"), "cli")
        self.assertEqual(intake.topic_of("crates/uv/tests/it/lock.rs"), "lock")
        self.assertEqual(intake.topic_of("mail/protocols/imap/src/test/java/com/fsck/k9/mail/store/imap/A.kt"), "imap")
        self.assertEqual(intake.topic_of("legacy/core/src/test/java/com/fsck/k9/B.kt"), "core")

    def test_generated_and_usage_fences(self):
        gen = intake.md_facts("docs/cli.md", "<!-- This file is generated by cog. Do not edit. -->\n# CLI\n")
        self.assertEqual(intake.guess_class("docs/cli.md", gen)[0], "generated")
        readme = intake.md_facts("README.md", "<!-- [[[cog\n# Not a title\n]]] -->\n# Tool\n\n" +
                                 "```bash\ntool run\n```\n" * 3 + "Run it.\n")
        self.assertEqual(readme["title"], "Tool")
        self.assertTrue(readme["partly_generated"])
        self.assertEqual(intake.guess_class("README.md", readme)[0], "product")

    def test_scan_a_repository(self):
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            run = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)  # noqa: E731
            run("init", "-q")
            run("config", "user.email", "a@example.com")
            run("config", "user.name", "A")
            (repo / "README.md").write_text("# Tool\n\n## Usage\n\nRun it.\n")
            (repo / "AGENTS.md").write_text("# Agents\n")
            (repo / "e2e").mkdir()
            (repo / "e2e" / "login.spec.ts").write_text("test('signs in', async () => {});\n"
                                                         "test('signs out', async () => {});\n")
            (repo / "app.ts").write_text("export const a = 1;\n")
            run("add", ".")
            run("commit", "-qm", "Switch to the new renderer")
            out = subprocess.run([sys.executable, str(SCRIPT), "scan", d], capture_output=True, text=True,
                                 check=True).stdout
            scan = json.loads(out)
        self.assertEqual({m["path"]: m["guess"] for m in scan["markdown"]},
                         {"README.md": "product", "AGENTS.md": "harness"})
        self.assertEqual(scan["tests"]["cases"], {"e2e": 2})
        self.assertEqual(scan["tests"]["e2e"][0]["titles"], ["signs in", "signs out"])
        self.assertTrue(scan["churn"]["hot_files"])
        self.assertEqual(scan["schema_version"], intake.SCHEMA_VERSION)
        self.assertEqual(scan["churn"]["milestones"], [])  # one small commit is no milestone


class Plan(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        base = Path(self.dir.name)
        (base / "docs").mkdir()
        (base / "docs" / "a.md").write_text(doc("Alpha", "See [Beta](ref:b).\n", tags=["core"], tldr="Alpha."))
        (base / "docs" / "b.md").write_text(doc("Beta", "Back to [Alpha](ref:a).\n", tags=["core"], tldr="Beta."))
        (base / "docs" / "d.md").write_text(doc("Which store?", "We use SQLite because it is local.\n"))
        self.plan = {
            "schema_version": 1, "repository": "o/n", "ref": "abc", "summary": "S",
            "tags": [{"name": "core", "status": "new"}, {"name": "extra", "status": "new"}],
            "sidebar": {"groups": [{"name": "Start", "docs": ["a"]}, {"name": "More", "docs": ["b", "d"]}],
                        "starter": "unpin"},
            "documents": [
                {"slug": "a", "file": "docs/a.md", "sources": ["README.md"]},
                {"slug": "b", "file": "docs/b.md", "sources": ["README.md"]},
                {"slug": "d", "file": "docs/d.md", "kind": "decision", "related": "a", "sources": ["git:1"]},
            ],
            "markdown": [{"path": "README.md", "action": "convert", "doc": ["a", "b"], "why": "x"},
                         {"path": "docs/**", "action": "keep", "why": "y"}],
        }
        self.path = base / "intake.json"
        self.path.write_text(json.dumps(self.plan))
        self.scan = {"markdown": [{"path": "README.md"}, {"path": "docs/x/y.md"}, {"path": "NOTES.md"}]}

    def tearDown(self):
        self.dir.cleanup()

    def test_check(self):
        errors, warnings = intake.validate(self.plan, self.path.parent, self.scan)
        self.assertEqual(errors, ["markdown: NOTES.md is not accounted for (convert, keep or skip)"])
        self.plan["tags"][0]["name"] = "Core Tag"
        errors, _ = intake.validate(self.plan, self.path.parent)
        self.assertTrue(any("lowercase letters" in e for e in errors))

    def test_decision_answer_limits(self):
        (self.path.parent / "docs" / "d.md").write_text(doc("Which store?", "word " * 61 + "\n"))
        errors, _ = intake.validate(self.plan, self.path.parent)
        self.assertTrue(any("at most 60 words" in e for e in errors))

    def test_history_warning(self):
        (self.path.parent / "docs" / "a.md").write_text(doc("Alpha", "Search is planned for v2.\n", tldr="A."))
        _, warnings = intake.validate(self.plan, self.path.parent)
        self.assertTrue(any("'planned'" in w for w in warnings))

    def calls(self, *extra, tags=None):
        path = self.path.parent / "tags.json"
        path.write_text(json.dumps({"tags": tags if tags is not None else [{"id": "t1", "name": "core"}]}))
        run = subprocess.run([sys.executable, str(SCRIPT), "calls", str(self.path), "--tags", str(path), *extra],
                             capture_output=True, text=True, check=True)
        return json.loads(run.stdout), run.stderr

    def test_calls_in_two_passes(self):
        calls, _ = self.calls()
        tools = [(c["tool"], c.get("slug")) for c in calls]
        # every document exists before any block is written, so each link can name its target
        self.assertEqual(tools[:6], [("create_doc", "a"), ("create_doc", "b"), ("create_doc", "d"),
                                     ("insert_block", "a"), ("insert_block", "b"), ("insert_block", "d")])
        self.assertNotIn("blocks", calls[0]["arguments"])
        self.assertEqual(calls[0]["arguments"]["tags"], ["t1"])
        self.assertEqual(calls[2]["arguments"]["related"], {"$ref": "a"})
        self.assertEqual(calls[2]["arguments"]["kind"], "decision")
        self.assertEqual(calls[2]["arguments"]["status"], "open")
        self.assertEqual(calls[3]["arguments"]["uuid"], {"$ref": "a"})
        self.assertFalse([t for t, _ in tools if t in ("link_range", "edit_block", "starter_cleanup")])
        optional = [c for c in calls if c.get("optional")]
        self.assertEqual([c["tool"] for c in optional], ["unpin_doc", "unpin_doc", "sidebar_group"])
        self.assertEqual(calls[-1]["arguments"], {"group": "More", "action": "move", "index": 1})
        marks = calls[3]["arguments"]["blocks"][0]["inline"][1]["marks"]
        self.assertEqual(intake.resolve(marks, {"b": "uuid-b"}), {"docLink": "uuid-b"})
        with self.assertRaises(KeyError):
            intake.resolve(calls[3]["arguments"], {"a": "uuid-a"})

    def test_links_in_a_table(self):
        (self.path.parent / "docs" / "b.md").write_text(doc("Beta", "| x |\n| - |\n| [Alpha](ref:a) |\n",
                                                            tags=["core"], tldr="B."))
        calls, _ = self.calls()
        insert = next(c for c in calls if c["tool"] == "insert_block" and c["slug"] == "b")
        self.assertEqual(insert["arguments"]["blocks"][0]["text"], "| x |\n| - |\n| [Alpha]({{uuid:a}}) |")
        self.assertEqual(intake.resolve(insert["arguments"], {"a": "A", "b": "B"})["blocks"][0]["text"],
                         "| x |\n| - |\n| [Alpha](A) |")

    def test_resolve_for_the_mcp_route(self):
        calls, _ = self.calls()
        base = self.path.parent
        (base / "calls.json").write_text(json.dumps(calls))

        def resolve(uuids):
            if uuids is not None:
                (base / "uuids.json").write_text(json.dumps(uuids))
            run = subprocess.run([sys.executable, str(SCRIPT), "resolve", "--calls", str(base / "calls.json"),
                                  "--uuids", str(base / "uuids.json")], capture_output=True, text=True, check=True)
            return [json.loads(line) for line in run.stdout.splitlines()], run.stderr

        # nothing answered yet: the pages, then a stop at the record that names its page
        ready, err = resolve(None)
        self.assertEqual([(r["call"], r["tool"]) for r in ready], [(1, "create_doc"), (2, "create_doc")])
        self.assertIn("needs the UUID of 'a'", err)
        ready, _ = resolve({"a": "A", "b": "B"})
        self.assertEqual(ready[0], {"call": 3, "tool": "create_doc", "slug": "d", "arguments": {
            "title": "Which store?", "description": "About Which store?", "kind": "decision",
            "status": "open", "related": "A"}})
        self.assertEqual(ready[1]["call"], 4)  # stops before d's blocks, which wait for d
        self.assertEqual(len(ready), 3)
        ready, err = resolve({"a": "A", "b": "B", "d": "D"})
        self.assertEqual(ready[0]["call"], 4)
        self.assertEqual(ready[0]["arguments"]["uuid"], "A")
        self.assertNotIn("text", ready[0]["arguments"]["blocks"][0])  # the inline runs carry it
        self.assertEqual(ready[-1]["call"], len(calls))
        self.assertIn("all ready", err)

    def test_a_decided_record_is_created_with_its_answer(self):
        self.plan["documents"][2]["status"] = "decided"
        self.plan["documents"][2]["answer"] = {"who": "Ann", "when": "2026-01-02", "where": "https://x.test/adr"}
        self.path.write_text(json.dumps(self.plan))
        calls, _ = self.calls()
        create = next(c for c in calls if c.get("slug") == "d")
        self.assertEqual(create["arguments"]["blocks"][0]["text"], "We use SQLite because it is local.")
        self.assertFalse([c for c in calls if c["tool"] == "insert_block" and c["slug"] == "d"])
        (self.path.parent / "docs" / "d.md").write_text(doc("Which store?", "See [Beta](ref:b).\n"))
        self.plan["documents"].append({"slug": "e", "file": "docs/d.md", "kind": "decision", "status": "decided",
                                       "answer": self.plan["documents"][2]["answer"]})
        (self.path.parent / "docs" / "e.md").write_text(doc("Other?", "Yes.\n"))
        self.plan["documents"][3]["file"] = "docs/e.md"
        (self.path.parent / "docs" / "d.md").write_text(doc("Which store?", "Like [Other](ref:e).\n"))
        self.path.write_text(json.dumps(self.plan))
        run = subprocess.run([sys.executable, str(SCRIPT), "calls", str(self.path), "--tags",
                              str(self.path.parent / "tags.json")], capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn("links to e, created after it", run.stderr)

    def test_ub_skips_optional_failures_and_adopted_documents(self):
        calls, _ = self.calls()
        base = self.path.parent
        (base / "calls.json").write_text(json.dumps(calls))
        fake = base / "fake_ub.py"
        fake.write_text(FAKE_UB)
        log = base / "log.jsonl"
        run = subprocess.run([sys.executable, str(SCRIPT), "ub", "--calls", str(base / "calls.json"),
                              "--checkout", str(base), "--out", str(base / "applied.json"), "--adopt",
                              "--settle", "0", "--ub", f"{sys.executable} {fake} {log}"],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        sent = [json.loads(line) for line in log.read_text().splitlines()]
        tools = [m["name"] for m in sent]
        self.assertNotIn(("insert_block", "uuid-existing"),
                         [(m["name"], m["arguments"].get("uuid")) for m in sent])  # adopted: left as it is
        self.assertEqual(tools.count("unpin_doc"), 2)  # the first failed, which is fine
        applied = json.loads((base / "applied.json").read_text())
        self.assertEqual(applied["done"], len(calls))
        self.assertEqual(applied["adopted"], ["a"])

    def test_tags_the_catalog_lacks_are_left_off(self):
        calls, err = self.calls(tags=[])
        self.assertNotIn("tags", calls[0]["arguments"])
        self.assertIn("core", err)

    def test_calls_after_an_earlier_run(self):
        applied = self.path.parent / "applied.json"
        applied.write_text(json.dumps({"uuids": {"a": "uuid-a", "b": "uuid-b"}}))
        calls, _ = self.calls("--applied", str(applied))
        self.assertEqual([c["tool"] for c in calls[:5]],
                         ["existing", "set_metadata", "existing", "set_metadata", "create_doc"])
        self.assertEqual(calls[1]["arguments"], {"uuid": "uuid-a", "tags": ["t1"]})
        self.assertFalse([c for c in calls if c["tool"] == "insert_block" and c["slug"] in ("a", "b")])

    def test_globs_and_precedence(self):
        self.assertTrue(intake.covers("docs/*.md", "docs/a.md"))
        self.assertFalse(intake.covers("docs/*.md", "docs/x/a.md"))
        self.assertTrue(intake.covers("docs/**/*.md", "docs/x/y/a.md"))
        entries = [{"path": "docs/**", "action": "keep"}, {"path": "docs/guide/**", "action": "convert"}]
        self.assertEqual(intake.entry_for(entries, "docs/guide/a.md")["action"], "convert")

    def test_check_with_the_checkout_and_catalog(self):
        repo = self.path.parent / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("x")
        errors, warnings = intake.validate(self.plan, self.path.parent, None, repo, {"core", "extra"})
        self.assertFalse(errors)
        self.plan["documents"][0]["sources"] = ["src/gone.py:1-4"]
        errors, warnings = intake.validate(self.plan, self.path.parent, None, repo, {"core"})
        self.assertIn("source src/gone.py:1-4 does not exist", " ".join(errors))
        self.assertTrue(any("marked new, but the catalog has it" in w for w in warnings))
        self.assertTrue(any("extra is used by 0" in w for w in warnings))
        (repo / "README.md").write_text("# N\n\n### Install\n")
        self.plan["markdown"][0]["sections"] = [{"heading": "Install", "action": "keep"},
                                                {"heading": "Usage", "action": "keep"}]
        _, warnings = intake.validate(self.plan, self.path.parent, None, repo)
        self.assertEqual([w for w in warnings if "heading" in w],
                         ["markdown: README.md has no heading 'Usage'; a section names one exactly as the file has it"])

    def test_unknown_container(self):
        with self.assertRaisesRegex(ValueError, "no Uberblick container"):
            intake.parse_doc(doc("A", ":::note\nHi\n:::\n"))
        _, _, refs = intake.parse_doc(doc("A", ":::card\ntitle: Go\n\nSee [B](ref:b).\n:::\n"))
        self.assertEqual(refs, {"b"})

if __name__ == "__main__":
    unittest.main()
