"""Checks for the flow documents: validation, warnings, the Uberblick Markdown, the page and the command line."""
import copy
import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "assets"
spec = importlib.util.spec_from_file_location("flow_page", HERE / "page.py")
page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(page)
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


class PageTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ASSETS / "example.json").read_text(encoding="utf-8"))
        names = [self.data["overview"]["flow"]] + [p["flow"] for p in self.data["phases"]]
        self.flows = {name: (ASSETS / name).read_text(encoding="utf-8") for name in names}
        self.svgs = {name: SVG for name in self.flows}

    def test_example_is_clean(self):
        self.assertEqual(page.validate(self.data, self.flows), [])

    def test_outcome_label_that_starts_nothing_warns(self):
        self.data["roles"][0]["outcomes"]["prepared"] = ["redy"]
        self.assertIn("issue-preparer: outcome prepared adds redy, which starts no agent",
                      page.validate(self.data, self.flows))

    def test_gate_numbers_must_match_their_phase_flow(self):
        self.flows["pr.flow"] = self.flows["pr.flow"].replace("G4 Green", "Green").replace("G3 Criteria", "G9 Criteria")
        warnings = page.validate(self.data, self.flows)
        self.assertIn("Implementation and PR phase: G4 is not in pr.flow", warnings)
        self.assertIn("Implementation and PR phase: G3 is not in pr.flow", warnings)
        self.assertIn("Implementation and PR phase: pr.flow shows G9, which is not one of its gates", warnings)

    def test_a_gate_only_in_an_edge_label_is_not_drawn(self):
        self.flows["issue.flow"] = self.flows["issue.flow"].replace(
            '"G2 Clear and in scope?"', '"Clear and in scope?"').replace(
            "g2 --> ready : prepared", "g2 --> ready : G2 prepared")
        self.assertIn("Issue phase: G2 is not in issue.flow", page.validate(self.data, self.flows))

    def test_every_role_sits_in_one_phase_and_gates_count_from_one(self):
        for change in (lambda d: d["phases"][1]["roles"].remove("reviewer"),
                       lambda d: d["phases"][0]["roles"].append("reviewer"),
                       lambda d: d["phases"][0].update(roles=[]),
                       lambda d: d["phases"][1]["gates"].pop(0),
                       lambda d: d["phases"][0]["gates"].reverse(),
                       lambda d: d["phases"][0].update(flow="issue.txt"),
                       lambda d: d["phases"][1].update(flow="issue.flow"),
                       lambda d: d["phases"][1].update(flow="overview.flow"),
                       lambda d: d["phases"][0].pop("starts")):
            data = copy.deepcopy(self.data)
            change(data)
            with self.assertRaises(ValueError):
                page.validate(data)

    def test_budgets_warn(self):
        self.data["overview"]["summary"] = "word " * 61
        self.data["phases"][0]["gates"][0]["rule"] = "word " * 31
        warnings = page.validate(self.data)
        self.assertIn("overview: summary is over 60 words", warnings)
        self.assertIn("Issue phase G1: rule is over 30 words", warnings)

    def test_malformed_reports_fail(self):
        cases = [
            lambda d: d.update(schema_version=1),
            lambda d: d.update(repository="ub-agents"),
            lambda d: d["phases"][0]["gates"][0].update(decides="robot"),
            lambda d: d["phases"][0]["gates"][0].update(sources=[]),
            lambda d: d["phases"][0]["gates"][0].pop("rule"),
            lambda d: d.update(settings=[]),
            lambda d: d.update(gates=[]),
            lambda d: d.pop("overview"),
            lambda d: d["overview"].pop("flow"),
            lambda d: d["roles"][0].update(outcomes={}),
            lambda d: d["roles"].append(copy.deepcopy(d["roles"][0])),
            lambda d: d.pop("phases"),
        ]
        for change in cases:
            data = copy.deepcopy(self.data)
            change(data)
            with self.assertRaises(ValueError):
                page.validate(data)

    def test_an_overview_and_a_document_per_phase(self):
        docs = page.documents(self.data)
        self.assertEqual([name for name, _, _ in docs], ["overview", "issue", "pr"])
        overview, issue, pr = (page.markdown(title, blocks, self.flows) for _, title, blocks in docs)
        self.assertTrue(overview.startswith("# How the loop runs in uberblick-ai/ub-agents\n"))
        self.assertIn("| **Issue phase** | `needs-preparation` | `ready` | issue-preparer | 3 |", overview)
        self.assertIn("## Notes\n\n- `queue.milestones: order` Priority always wins", overview)
        self.assertEqual(overview.count(":::card"), 0)
        self.assertTrue(issue.startswith("# The loop in uberblick-ai/ub-agents: issue phase\n"))
        self.assertEqual(issue.count(":::card\n"), 3)
        self.assertEqual(pr.count(":::card\n"), 5)
        self.assertIn(":::card\nlabel: G3 · reviewer · agent decides\ntitle: Review\n\nAnother model", pr)
        self.assertIn("| **reviewer** pr | `needs-review` | Reviews the exact head", pr)
        for md in (overview, issue, pr):
            self.assertEqual(md.count("```ablauf\nflow v0\n"), 1)
            self.assertNotIn("footer:", md)

    def test_combined_is_one_document(self):
        [(name, title, blocks)] = page.combined(self.data)
        md = page.markdown(title, blocks, self.flows)
        self.assertEqual(name, "flow")
        self.assertTrue(md.startswith("# How the loop runs"))
        self.assertNotIn("# The loop in", md)
        self.assertEqual(md.count("```ablauf\nflow v0\n"), 3)
        self.assertEqual(md.count(":::card\n"), 8)
        self.assertIn("## Implementation and PR phase", md)
        self.assertIn("### Notes", md)

    def test_table_cells_escape_pipes(self):
        self.data["roles"][0]["does"] = "Reads a | b"
        _, title, blocks = page.documents(self.data)[1]
        self.assertIn("Reads a \\| b", page.markdown(title, blocks, self.flows))

    def test_page_draws_each_document_and_escapes_text(self):
        self.data["overview"]["notes"] = ["<script>alert(1)</script> and `code`"]
        html = page.render(page.documents(self.data), self.svgs, self.data["repository"])
        self.assertEqual(html.count("<article>"), 3)
        self.assertEqual(html.count('<figure class="ablauf"><svg'), 3)
        self.assertEqual(html.count('<div class="card">'), 8)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; and <code>code</code>", html)
        self.assertIn("article+article{break-before:page", html)

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            shutil.copy(ASSETS / "example.json", tmp / "flow.json")
            for name in self.flows:
                shutil.copy(ASSETS / name, tmp / name)
            args = [str(tmp / "flow.json"), "--out", str(tmp / "flow.html")]
            self.assertEqual(page.main(args), 1)  # no SVGs rendered yet
            for name in self.flows:
                (tmp / name).with_suffix(".svg").write_text(SVG, encoding="utf-8")
            self.assertEqual(page.main(args), 0)
            self.assertIn("How the loop runs in uberblick-ai/ub-agents", (tmp / "flow.html").read_text(encoding="utf-8"))
            for name in ("overview", "issue", "pr"):
                self.assertIn("```ablauf", (tmp / f"{name}.md").read_text(encoding="utf-8"))
            self.assertFalse((tmp / "flow.md").exists())
            self.assertEqual(page.main(args[:1] + ["--out", str(tmp / "one" / "flow.html"), "--combine"]), 0)
            self.assertEqual((tmp / "one" / "flow.md").read_text(encoding="utf-8").count("```ablauf"), 3)
            self.assertFalse((tmp / "one" / "overview.md").exists())


if __name__ == "__main__":
    unittest.main()
