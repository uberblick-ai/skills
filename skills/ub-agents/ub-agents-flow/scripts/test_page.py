"""Checks for the flow report: validation, warnings, the Uberblick Markdown, the page and the command line."""
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
        self.flows = {p["name"]: (ASSETS / p["flow"]).read_text(encoding="utf-8") for p in self.data["phases"]}
        self.svgs = {name: SVG for name in self.flows}

    def test_example_is_clean(self):
        self.assertEqual(page.validate(self.data, self.flows), [])

    def test_outcome_label_that_starts_nothing_warns(self):
        self.data["roles"][0]["outcomes"]["prepared"] = ["redy"]
        self.assertIn("issue-preparer: outcome prepared adds redy, which starts no agent",
                      page.validate(self.data, self.flows))

    def test_gate_numbers_must_match_the_flows(self):
        self.flows["Implementation and PR phase"] = self.flows["Implementation and PR phase"].replace(
            "G5 Green", "Green").replace("G3", "G9")
        warnings = page.validate(self.data, self.flows)
        self.assertIn("G5 is in no flow", warnings)
        self.assertIn("G3 is in no flow", warnings)
        self.assertIn("the Implementation and PR phase flow shows G9, which is not a gate", warnings)
        self.flows["Issue phase"] = self.flows["Issue phase"].replace("G2 Clear", "Clear")
        self.data["phases"][0]["gates"] = ["G1"]
        self.data["phases"][1]["gates"].insert(0, "G2")
        self.assertIn("G2 is in no flow", page.validate(self.data, self.flows))

    def test_every_role_and_gate_sits_in_one_phase(self):
        for change in (lambda d: d["phases"][1]["roles"].remove("reviewer"),
                       lambda d: d["phases"][0]["roles"].append("reviewer"),
                       lambda d: d["phases"][1]["gates"].remove("G6"),
                       lambda d: d["phases"][0]["gates"].append("G7"),
                       lambda d: d["phases"][0].update(roles=[]),
                       lambda d: d["phases"][0].update(flow="issue.txt")):
            data = copy.deepcopy(self.data)
            change(data)
            with self.assertRaises(ValueError):
                page.validate(data)

    def test_budgets_warn(self):
        self.data["summary"] = "word " * 61
        self.data["gates"] += [dict(self.data["gates"][0], id=f"G{n}") for n in range(7, 10)]
        self.data["phases"][1]["gates"] += ["G7", "G8", "G9"]
        warnings = page.validate(self.data)
        self.assertIn("summary is over 60 words", warnings)
        self.assertIn("9 gates; merge related ones to stay within 8", warnings)

    def test_malformed_reports_fail(self):
        cases = [
            lambda d: d.update(schema_version=2),
            lambda d: d.update(repository="ub-agents"),
            lambda d: d["gates"][0].update(decides="robot"),
            lambda d: d["gates"][1].update(id="G1"),
            lambda d: d["gates"][0].update(sources=[]),
            lambda d: d["roles"][0].update(outcomes={}),
            lambda d: d["roles"].append(copy.deepcopy(d["roles"][0])),
            lambda d: d.pop("phases"),
        ]
        for change in cases:
            data = copy.deepcopy(self.data)
            change(data)
            with self.assertRaises(ValueError):
                page.validate(data)

    def test_markdown_uses_uberblick_blocks(self):
        md = page.markdown(self.data, self.flows)
        self.assertTrue(md.startswith("# How the loop runs in uberblick-ai/ub-agents\n"))
        self.assertEqual(md.count("```ablauf\nflow v0\n"), 2)
        self.assertEqual(md.count(":::card\n"), 6)
        self.assertIn("## Implementation and PR phase", md)
        self.assertIn("label: G4 · reviewer · agent decides\ntitle: Review\nfooter: "
                      "[.agents/reviewer.md:3-17](https://github.com/uberblick-ai/ub-agents/blob/a021eaa/.agents/reviewer.md#L3-L17)", md)
        self.assertIn("| `max-attempts` | 5 | Failed runs in a row before the item is marked failed. |", md)

    def test_table_cells_escape_pipes(self):
        self.data["roles"][0]["does"] = "Reads a | b"
        self.assertIn("Reads a \\| b", page.markdown(self.data, self.flows))

    def test_page_draws_each_phase_and_escapes_text(self):
        self.data["notes"] = ["<script>alert(1)</script> and `code`"]
        html = page.render(self.data, self.svgs)
        self.assertEqual(html.count('<figure class="ablauf"><svg'), 2)
        self.assertEqual(html.count('<div class="card">'), 6)
        self.assertIn('<a href="https://github.com/uberblick-ai/ub-agents/blob/a021eaa/ub-agents.yaml#L100-L107"', html)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; and <code>code</code>", html)
        self.assertIn(".phase~.phase{break-before:page", html)

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            shutil.copy(ASSETS / "example.json", tmp / "flow.json")
            for phase in self.data["phases"]:
                shutil.copy(ASSETS / phase["flow"], tmp / phase["flow"])
            args = [str(tmp / "flow.json"), "--out", str(tmp / "flow.html")]
            self.assertEqual(page.main(args), 1)  # no SVGs rendered yet
            for phase in self.data["phases"]:
                (tmp / phase["flow"]).with_suffix(".svg").write_text(SVG, encoding="utf-8")
            self.assertEqual(page.main(args), 0)
            self.assertIn("How the loop runs in uberblick-ai/ub-agents", (tmp / "flow.html").read_text(encoding="utf-8"))
            self.assertIn("```ablauf", (tmp / "flow.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
