"""Checks for the flow report: validation, warnings, links and the command line."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("flow_page", HERE / "page.py")
page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(page)
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>'


class PageTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE.parent / "assets/example.json").read_text(encoding="utf-8"))
        self.flow = (HERE.parent / "assets/example.flow").read_text(encoding="utf-8")

    def test_example_is_clean(self):
        self.assertEqual(page.validate(self.data, self.flow), [])

    def test_outcome_label_that_starts_nothing_warns(self):
        self.data["roles"][0]["outcomes"]["prepared"] = ["redy"]
        self.assertIn("issue-preparer: outcome prepared adds redy, which starts no agent",
                      page.validate(self.data, self.flow))

    def test_gate_numbers_must_match_the_flow(self):
        warnings = page.validate(self.data, self.flow.replace("G5 Green", "Green").replace("G3", "G9"))
        self.assertIn("G5 is not in the flow", warnings)
        self.assertIn("the flow shows G9, which is not a gate", warnings)

    def test_budgets_warn(self):
        self.data["summary"] = "word " * 61
        self.data["gates"] += [dict(self.data["gates"][0], id=f"G{n}") for n in range(7, 10)]
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
        ]
        for change in cases:
            data = copy.deepcopy(self.data)
            change(data)
            with self.assertRaises(ValueError):
                page.validate(data)

    def test_sources_link_to_the_lines_at_the_ref(self):
        html = page.render(self.data, SVG, self.flow)
        self.assertIn('href="https://github.com/uberblick-ai/ub-agents/blob/a021eaa/ub-agents.yaml#L100-L107"', html)
        self.assertIn('href="https://github.com/uberblick-ai/ub-agents/blob/a021eaa/.agents/reviewer.md"', html)
        self.assertIn("break-before:page", html)

    def test_text_is_escaped(self):
        self.data["notes"] = ["<script>alert(1)</script>"]
        html = page.render(self.data, SVG)
        self.assertNotIn("<script>alert", html)
        self.assertIn("&lt;script&gt;", html)

    def test_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "flow.json").write_text(json.dumps(self.data), encoding="utf-8")
            (tmp / "flow.svg").write_text(SVG, encoding="utf-8")
            (tmp / "bad.svg").write_text("not an svg", encoding="utf-8")
            args = [str(tmp / "flow.json"), "--out", str(tmp / "flow.html")]
            self.assertEqual(page.main(args + ["--svg", str(tmp / "flow.svg")]), 0)
            self.assertIn("How the loop runs in uberblick-ai/ub-agents", (tmp / "flow.html").read_text(encoding="utf-8"))
            self.assertEqual(page.main(args + ["--svg", str(tmp / "bad.svg")]), 1)


if __name__ == "__main__":
    unittest.main()
