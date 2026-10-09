"""Behavioral checks for report filtering, evidence safety and portability."""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('grooming_render', HERE/'render.py')
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((HERE.parent/'assets/example.json').read_text())

    def test_timestamp_requires_timezone(self):
        for value in ["yesterday", "2026-10-09", "2026-10-09T12:00:00"]:
            self.data["reviewed_at"] = value
            with self.assertRaises(ValueError): render.render(self.data)

    def test_closed_items_require_an_actionable_reason(self):
        closed = self.data['items'][1]
        self.assertIn(closed['title'], render.render(self.data))
        closed['open_prs'] = []
        self.assertNotIn(closed['title'], render.render(self.data))
        closed['highlight_reason'] = 'Closure conflicts with an undelivered guarantee.'
        self.assertIn(closed['highlight_reason'], render.render(self.data))

    def test_priority_sort_color_and_default_suppression(self):
        self.data['items'].reverse()
        self.data['items'][0]['priority'] = {'name':'priority:medium','rank':2,'color':'FBCA04'}
        page = render.render(self.data)
        self.assertLess(page.index('Install at the project root'), page.index('Improve the sync summary'))
        self.assertIn('background:#D93F0B', page)
        self.assertNotIn('priority:medium', page)

    def test_loop_is_optional_and_negative_status_needs_evidence(self):
        self.data['items'][0]['loop'].pop('short_reason')
        with self.assertRaises(ValueError): render.render(self.data)
        for item in self.data['items']: item['loop'] = None
        page = render.render(self.data)
        self.assertNotIn('Loop / blockers', page)
        self.assertIn('Blocked by', page)

    def test_untrusted_text_and_urls_do_not_execute(self):
        self.data['items'][0]['title'] = '<script>alert(1)</script> @@ROWS@@'
        page = render.render(self.data)
        self.assertIn('&lt;script&gt;', page)
        self.assertIn('@@ROWS@@', page)
        self.assertNotIn('<script>', page)
        self.data['items'][0]['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError): render.render(self.data)

    def test_challenge_status_does_not_claim_completion(self):
        c = self.data['items'][2]['challenge']
        c['status'] = 'unavailable'
        page = render.render(self.data)
        self.assertIn('Challenge unavailable', page)
        self.assertNotIn('Independently challenged', page)

    def test_round_trip_preserves_human_decisions_and_action_results(self):
        self.data['decisions'] = [{'question':'Goal?', 'answer':'Reduce scope', 'source':'chat'}]
        self.data['actions'] = [{'item':'example/app#1','action':'label','outcome':'failed','source':'API refusal'}]
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'input.json'; source.write_text(json.dumps(self.data))
            self.assertEqual(render.main([str(source),d,'--no-open']),0)
            self.assertEqual(json.loads((Path(d)/'report.json').read_text()),self.data)
            self.assertTrue((Path(d)/'report.html').exists())

    def test_cross_repository_identity_and_duplicate_detection(self):
        extra=copy.deepcopy(self.data['items'][0]);extra['id']='example/other#1';self.data['items'].append(extra)
        render.render(self.data)
        extra['id']='example/app#1'
        with self.assertRaises(ValueError):render.render(self.data)

if __name__ == '__main__': unittest.main()
