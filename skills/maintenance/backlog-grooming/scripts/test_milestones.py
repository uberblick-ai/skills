"""Checks for the milestone usage summary: counts, not judgments, and named blind spots."""
import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('grooming_milestones', HERE/'milestones.py')
milestones = importlib.util.module_from_spec(spec)
spec.loader.exec_module(milestones)

def m(number, title, state='closed', due=None, closed=None, open_issues=0, closed_issues=5, description=''):
    return {'number': number, 'title': title, 'state': state, 'due_on': due, 'closed_at': closed,
            'open_issues': open_issues, 'closed_issues': closed_issues, 'description': description,
            'html_url': f'https://github.com/example/app/milestone/{number}'}

HISTORY = [
    m(1, 'v1.0', due='2026-06-01T07:00:00Z', closed='2026-06-03T10:00:00Z', closed_issues=8),
    m(2, '1.1: Offline', due='2026-07-13T07:00:00Z', closed='2026-07-10T10:00:00Z', closed_issues=12, description='Work without a network.'),
    m(3, 'Sprint 14', due='2026-08-24T07:00:00Z', closed='2026-09-01T10:00:00Z', open_issues=2, closed_issues=4),
    m(4, '1.4: Reliable sync', state='open', due='2026-10-31T07:00:00Z', open_issues=5, closed_issues=9),
    m(5, 'Someday', state='open', open_issues=0, closed_issues=0),
]
NOW = milestones.when('2026-11-01T12:00:00Z')

class MilestoneSummaryTests(unittest.TestCase):
    def test_counts_kinds_sizes_and_cadence(self):
        out = milestones.summarize(HISTORY, now=NOW)
        self.assertEqual(out['counts'], {'open': 2, 'closed': 3})
        self.assertEqual(out['title_kinds'], {'version': 3, 'period': 1, 'other': 1})
        self.assertEqual(out['with_due_date'], 4)
        self.assertEqual(out['with_description'], 1)
        self.assertEqual(out['closed']['size'], {'min': 6, 'median': 8, 'max': 12})
        self.assertEqual(out['closed']['days_between_due_dates'], {'min': 42, 'median': 42.0, 'max': 42})
        self.assertEqual(out['closed']['days_closed_after_due']['max'], 8)
        self.assertEqual(out['closed']['closed_with_open_issues'], ['Sprint 14'])
        self.assertEqual([r['title'] for r in out['closed']['recent']], ['Sprint 14', '1.1: Offline', 'v1.0'])

    def test_open_milestones_flag_overdue_and_empty(self):
        sync, someday = milestones.summarize(HISTORY, now=NOW)['open']
        self.assertEqual((sync['title'], sync['overdue'], sync['empty']), ('1.4: Reliable sync', True, False))
        self.assertEqual((someday['due_on'], someday['overdue'], someday['empty']), (None, False, True))

    def test_issue_share_excludes_pull_requests(self):
        issues = [{'state': 'open', 'milestone': {'number': 4}}, {'state': 'open', 'milestone': None},
                  {'state': 'open', 'milestone': {'number': 4}, 'pull_request': {}}]
        out = milestones.summarize(HISTORY, issues, now=NOW)
        self.assertEqual(out['issues']['open'], 2)
        self.assertEqual((out['issues']['share'], out['issues']['groups_by_milestone']), (0.5, True))
        out = milestones.summarize(HISTORY, issues[1:], now=NOW)
        self.assertFalse(out['issues']['groups_by_milestone'])

    def test_blind_spots_are_named(self):
        spots = ' '.join(milestones.summarize(HISTORY, now=NOW)['blind_spots'])
        self.assertIn('pull requests', spots)
        self.assertIn('No --issues file', spots)
        self.assertIn('No milestones at all', ' '.join(milestones.summarize([], now=NOW)['blind_spots']))

    def test_reads_paginated_output_and_rejects_bad_input(self):
        quiet = contextlib.ExitStack()
        quiet.enter_context(contextlib.redirect_stdout(io.StringIO()))
        quiet.enter_context(contextlib.redirect_stderr(io.StringIO()))
        with quiet, tempfile.TemporaryDirectory() as d:
            path = Path(d)/'milestones.json'
            path.write_text(json.dumps(HISTORY[:2]) + '\n' + json.dumps(HISTORY[2:]), encoding='utf-8')
            self.assertEqual(len(milestones.pages(path)), 5)
            self.assertEqual(milestones.main([str(path), '--now', '2026-11-01T12:00:00Z']), 0)
            path.write_text('{"title": "not a list"}', encoding='utf-8')
            self.assertEqual(milestones.main([str(path)]), 1)
            path.write_text('[{"number": 1}]', encoding='utf-8')
            self.assertEqual(milestones.main([str(path)]), 1)

if __name__ == '__main__': unittest.main()
