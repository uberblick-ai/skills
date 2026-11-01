#!/usr/bin/env python3
"""Summarize how a tracker's milestones are used, open and closed.

Reads milestones as GitHub's REST API returns them (`number`, `title`,
`description`, `state`, `open_issues`, `closed_issues`, `created_at`,
`closed_at`, `due_on`, `html_url`); other trackers can map theirs to the same
fields. With --issues it also counts how many open issues carry a milestone.
Both files may hold one array or the pages `gh api --paginate` concatenates.

It counts and never judges intent: the reviewing agent reads the titles,
descriptions and `blind_spots` and decides what milestones mean here.
Read only; no network.
"""
import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

GROUPING_SHARE = 0.4  # the report groups by milestone from this share of open items
VERSION = re.compile(r'(^|[\s(\-_/])v?\d+\.\d+(\.\d+)?\b', re.I)
PERIOD = re.compile(
    r'\b((19|20)\d{2}[-/.](0?[1-9]|1[0-2])\b|q[1-4]\b|h[12]\b|'
    r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|'
    r'(sprint|iteration|cycle|week|wk)\s*#?\d+)', re.I)
BLIND_SPOTS = [
    'GitHub counts pull requests in a milestone\'s open_issues and closed_issues, so sizes mix issues and PRs.',
    'Size is a count, not effort; the report weighs effort in its Milestone load.',
    'Issues moved out of a milestone and deleted milestones leave no trace here; read issue timelines when history matters.',
    'Title kinds are guessed from version numbers, dates and English period words; anything else counts as other, so read the titles.',
    'Descriptions are cut to 160 characters; read the full text before relying on one.',
]

def pages(path):
    """One JSON array, or several concatenated as gh api --paginate prints them."""
    text = path.read_text(encoding='utf-8')
    decoder, at, out = json.JSONDecoder(), 0, []
    while True:
        while at < len(text) and text[at].isspace():
            at += 1
        if at == len(text):
            break
        value, at = decoder.raw_decode(text, at)
        if not isinstance(value, list):
            raise ValueError(f'{path}: expected a JSON array of records')
        out += value
    return out

def when(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

def kind(title):
    if VERSION.search(title):
        return 'version'
    if PERIOD.search(title):
        return 'period'
    return 'other'

def spread(values):
    if not values:
        return None
    return {'min': min(values), 'median': statistics.median(values), 'max': max(values)}

def record(m, now):
    due = when(m.get('due_on'))
    size = int(m.get('open_issues') or 0) + int(m.get('closed_issues') or 0)
    row = {
        'number': m.get('number'), 'title': m['title'], 'state': m.get('state', 'open'),
        'kind': kind(m['title']), 'size': size, 'open_issues': int(m.get('open_issues') or 0),
        'due_on': due.date().isoformat() if due else None,
        'description': (m.get('description') or '').strip()[:160] or None,
    }
    if m.get('html_url'):
        row['url'] = m['html_url']
    if row['state'] == 'open':
        row['overdue'] = bool(due and due < now)
        row['empty'] = size == 0
    else:
        closed = when(m.get('closed_at'))
        row['closed_at'] = closed.date().isoformat() if closed else None
        if due and closed:
            row['closed_days_after_due'] = (closed - due).days
    return row

def summarize(milestones, issues=None, now=None, recent=12):
    now = now or datetime.now(timezone.utc)
    for m in milestones:
        if not isinstance(m, dict) or not str(m.get('title', '')).strip():
            raise ValueError('every milestone needs a title')
    rows = [record(m, now) for m in milestones]
    open_rows = [r for r in rows if r['state'] == 'open']
    closed_rows = sorted((r for r in rows if r['state'] != 'open'), key=lambda r: r.get('closed_at') or '', reverse=True)
    dues = sorted(when(m['due_on']) for m in milestones if m.get('state') != 'open' and m.get('due_on'))
    gaps = [(b - a).days for a, b in zip(dues, dues[1:])]
    out = {
        'counts': {'open': len(open_rows), 'closed': len(closed_rows)},
        'title_kinds': {k: sum(r['kind'] == k for r in rows) for k in ('version', 'period', 'other')},
        'with_description': sum(bool(r['description']) for r in rows),
        'with_due_date': sum(bool(r['due_on']) for r in rows),
        'closed': {
            'size': spread([r['size'] for r in closed_rows]),
            'days_between_due_dates': spread(gaps),
            'days_closed_after_due': spread([r['closed_days_after_due'] for r in closed_rows if 'closed_days_after_due' in r]),
            'closed_with_open_issues': [r['title'] for r in closed_rows if r['open_issues']],
            'recent': closed_rows[:recent],
        },
        'open': sorted(open_rows, key=lambda r: (r['due_on'] is None, r['due_on'] or '', r['number'] if isinstance(r['number'], int) else -1)),
        'blind_spots': list(BLIND_SPOTS),
    }
    if issues is not None:
        real = [i for i in issues if isinstance(i, dict) and 'pull_request' not in i and i.get('state', 'open') == 'open']
        placed = [i for i in real if i.get('milestone')]
        share = len(placed) / len(real) if real else 0
        out['issues'] = {
            'open': len(real), 'in_milestone': len(placed), 'share': round(share, 3),
            'groups_by_milestone': share >= GROUPING_SHARE,
            'note': 'The report decides from the reviewed items; this share covers the issues file.',
        }
        out['blind_spots'].append('The issue share is only as complete as the issues file: pass every page of open issues.')
    else:
        out['blind_spots'].append('No --issues file: the share of open issues with a milestone is not counted.')
    if not rows:
        out['blind_spots'].append('No milestones at all: nothing to group by or learn from.')
    elif not out['with_due_date']:
        out['blind_spots'].append('No due dates: open milestones are listed in creation order, and cadence is unknown.')
    return out

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('milestones', type=Path, help='milestones of every state, e.g. milestones?state=all')
    p.add_argument('--issues', type=Path, help='open issues, to count the share with a milestone')
    p.add_argument('--now', help='reference time with timezone (default: now), for overdue')
    p.add_argument('--recent', type=int, default=12, help='closed milestones to list, newest first (default 12)')
    args = p.parse_args(argv)
    try:
        now = when(args.now) if args.now else None
        issues = pages(args.issues) if args.issues else None
        print(json.dumps(summarize(pages(args.milestones), issues, now, args.recent), indent=2, ensure_ascii=False))
    except (ValueError, TypeError, KeyError, OSError) as error:
        print(f'milestones: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
