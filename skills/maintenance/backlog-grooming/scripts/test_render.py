"""Behavioral checks for report filtering, evidence safety and portability."""
import copy
import importlib.util
import json
import os
import subprocess
import sys
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

    def test_priority_color_and_default_suppression(self):
        self.data['items'].reverse()
        self.data['items'][0]['priority'] = {'name':'priority:medium','rank':2,'color':'FBCA04','is_default':True}
        page = render.render(self.data)
        self.assertIn('background:#D93F0B', page)
        self.assertNotIn('priority:medium', page)

    def test_tracker_defines_default_not_priority_name(self):
        item=self.data["items"][0]
        item["priority"]={"name":"medium","rank":1,"is_default":False}
        self.assertIn(">medium<",render.render(self.data))
        item["priority"]={"name":"P3","rank":2,"is_default":True}
        self.assertNotIn(">P3<",render.render(self.data))

    def test_draft_without_permalink(self):
        item=self.data["items"][0]
        item["state"]="draft"
        item["id"]="planning-board:draft-17"
        item.pop("url")
        page=render.render(self.data)
        self.assertIn("planning-board:draft-17",page)
        self.assertIn("<small>Draft</small>",page)

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

    def test_report_is_utf8_whatever_the_locale(self):
        self.data['scope']['label']='Prüfung — schneller…'
        env=os.environ|{'LC_ALL':'C','PYTHONUTF8':'0','PYTHONCOERCECLOCALE':'0'}
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'in.json'; source.write_text(json.dumps(self.data), encoding='utf-8')
            subprocess.run([sys.executable, str(HERE/'render.py'), str(source), tmp, '--no-open'], env=env, check=True, capture_output=True)
            page=(Path(tmp)/'report.html').read_text(encoding='utf-8')
        self.assertIn('Prüfung — schneller…', page)
        self.assertLess(page.index('<meta charset="utf-8">'), page.index('<title>'))

    def test_milestone_load_counts_delivered_open_and_proposed(self):
        load, = render.milestone_load(self.data)[0]
        self.assertEqual((load['before'], load['after'], load['added'], load['status']), (24, 25, 1, 'Within cap'))
        page = render.render(self.data)
        self.assertIn('24 → 25', page)
        self.assertNotIn('over the cap', page)

    def test_milestone_over_cap_is_overloaded_unless_bounded(self):
        self.data['items'][2]['effort']['estimate'] = 'XL'
        load, = render.milestone_load(self.data)[0]
        self.assertEqual((load['after'], load['status']), (29, 'Overloaded'))
        self.assertIn('1 milestone over the cap', render.render(self.data))
        self.data['milestones'][0]['bounded'] = 'One storage refactor; not useful half done.'
        self.assertEqual(render.milestone_load(self.data)[0][0]['status'], 'Bounded exception')
        self.data['milestones'][0]['delivered_weight'] = 60
        self.assertEqual(render.milestone_load(self.data)[0][0]['status'], 'Overloaded')

    def test_capacity_is_configurable_and_closing_issues_leave(self):
        self.data['capacity'] = {'weights': {'1': 1, '3': 3, '8': 8}, 'cap': 10}
        for item in self.data['items']: item['effort']['estimate'] = '3'
        self.data['milestones'][0]['delivered_weight'] = 0
        load, = render.milestone_load(self.data)[0]
        self.assertEqual((load['before'], load['after']), (5, 8))
        self.data['items'][0]['treatment'] = 'close unnecessary'
        self.assertEqual(render.milestone_load(self.data)[0][0]['after'], 5)
        self.data['items'][0]['effort']['estimate'] = 'huge'
        self.data['items'][0]['treatment'] = 'keep'
        load, = render.milestone_load(self.data)[0]
        self.assertEqual((load['after'], load['unknown']), (5, 1))

    def test_milestone_load_is_optional_and_references_are_checked(self):
        del self.data['milestones']
        for item in self.data['items']: item.pop('placement', None)
        self.assertNotIn('Milestone load', render.render(self.data))
        self.data['items'][0]['placement'] = {'proposed': 'missing'}
        with self.assertRaises(ValueError): render.render(self.data)
        self.data['items'][0].pop('placement')
        self.data['capacity'] = {'cap': 10, 'ceiling': 5}
        with self.assertRaises(ValueError): render.render(self.data)

    def test_oldest_issue_first_whatever_the_priority(self):
        page = render.render(self.data)
        self.assertLess(page.index('Improve the sync summary'), page.index('Install at the project root'))
        self.data['items'][2]['created_at'] = '2026-10-01T00:00:00Z'
        page = render.render(self.data)
        self.assertLess(page.index('Install at the project root'), page.index('Improve the sync summary'))
        for item in self.data['items']: item.pop('created_at')
        page = render.render(self.data)
        self.assertLess(page.index('Install at the project root'), page.index('Improve the sync summary'))
        self.data['items'][0]['created_at'] = '2026-09-14'
        with self.assertRaises(ValueError): render.render(self.data)

    def test_no_change_items_leave_the_table_for_the_list(self):
        item = self.data['items'][0]
        item['no_change'] = True
        table = render.render(self.data).split('</table>', 1)[0]
        self.assertIn(item['title'], table)
        item['workflow_labels'] = ['ready']
        page = render.render(self.data)
        table, rest = page.split('</table>', 1)
        self.assertNotIn(item['title'], table)
        self.assertIn('No change required', rest)
        self.assertLess(rest.index(item['title']), rest.index('Grounding'))
        self.assertIn('1.4: Reliable sync', rest.split('No change required')[1])
        self.assertIn('2 items in the decision table · 1 with no change required', page)
        self.assertEqual(render.milestone_load(self.data)[0][0]['after'], 25)

    def test_no_change_only_for_items_kept_in_place(self):
        item = self.data['items'][0]
        item['no_change'] = True
        item['placement'] = {'current': '14', 'proposed': None}
        with self.assertRaises(ValueError): render.render(self.data)
        item['placement'] = {'current': '14'}
        item['treatment'] = 'narrow'
        with self.assertRaises(ValueError): render.render(self.data)

if __name__ == '__main__': unittest.main()
