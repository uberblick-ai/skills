#!/usr/bin/env python3
"""Render an evidence-backed grooming input; no network or issue mutations."""
import argparse
import html
import json
import re
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

TREATMENTS = {'keep', 'narrow', 'combine', 'defer', 'close delivered', 'close unnecessary', 'track only'}

def esc(value):
    return html.escape(str(value), quote=True)

def url(value):
    if not isinstance(value, str) or urlsplit(value).scheme not in {'https', 'http'} or not urlsplit(value).netloc:
        raise ValueError(f'Expected an absolute HTTP(S) evidence URL: {value!r}')
    return esc(value)

def link(text, target):
    return f'<a href="{url(target)}" rel="noreferrer">{esc(text)}</a>' if target else esc(text)

def text(obj, key):
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{key} must be nonempty text')
    return value

def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamps must include a timezone")

def validate(data):
    if data.get('schema_version') != 1:
        raise ValueError('schema_version must be 1')
    timestamp(text(data, 'reviewed_at'))
    scope = data['scope']
    if scope['kind'] not in {'repository', 'milestone', 'project'}:
        raise ValueError('scope.kind must be repository, milestone or project')
    for k in ('label', 'goal'):
        text(scope, k)
    if not isinstance(data['items'], list):
        raise ValueError('items must be an array')
    seen = set()
    for item in data['items']:
        ident = text(item, 'id')
        if ident in seen:
            raise ValueError(f'Duplicate item identity: {ident}')
        seen.add(ident)
        for k in ('title', 'summary'):
            text(item, k)
        url(item['url'])
        if item['state'] not in {'open', 'closed', 'draft'}:
            raise ValueError(f'{ident}: invalid state')
        if item['treatment'] not in TREATMENTS:
            raise ValueError(f'{ident}: invalid treatment')
        for k in ('estimate', 'basis'):
            text(item['effort'], k)
        if not item.get('evidence'):
            raise ValueError(f'{ident}: evidence is required')
        for evidence in item['evidence']:
            text(evidence, 'text')
            if evidence.get('url'):
                url(evidence['url'])
        for pr in item.get('open_prs', []):
            text(pr, 'id')
            url(pr['url'])
        challenge = item['challenge']
        if challenge['status'] not in {'completed', 'not-needed', 'pending', 'unavailable'}:
            raise ValueError(f'{ident}: invalid challenge status')
        if challenge['status'] != 'not-needed':
            text(challenge, 'summary')
        loop = item.get('loop')
        if loop is not None:
            if loop['state'] not in {'yes', 'no', 'blocked', 'unknown'}:
                raise ValueError(f'{ident}: invalid loop state')
            for k in ('reason', 'checked_at', 'config_source'):
                text(loop, k)
            timestamp(loop['checked_at'])
            if loop['state'] in {'no', 'blocked', 'unknown'}:
                text(loop, 'short_reason')
        priority = item.get('priority')
        if priority:
            text(priority, 'name')
            if not isinstance(priority.get('rank'), (float, int)):
                raise ValueError(f'{ident}: priority.rank must be numeric (lower first)')
            if priority.get('color') and not re.fullmatch('[0-9a-fA-F]{6}', priority['color']):
                raise ValueError(f'{ident}: priority.color must be six hex digits from the tracker')
        for blocker in item.get('blockers', []):
            for k in ('id', 'state', 'source'):
                text(blocker, k)
            if blocker.get('url'):
                url(blocker['url'])
    return data

def visible(item):
    return item['state'] != 'closed' or bool(item.get('open_prs') or item.get('highlight_reason'))

def priority_badge(priority):
    if not priority or priority.get('is_default') or priority['name'].lower() in {'medium', 'priority:medium'}:
        return ''
    color = priority.get('color')
    style = ''
    if color:
        rgb = [int(color[i:i+2], 16)/255 for i in (0, 2, 4)]
        lin = [c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb]
        lum = sum(c*w for c, w in zip(lin, (.2126, .7152, .0722)))
        foreground = '#000' if (lum+.05)/.05 >= 1.05/(lum+.05) else '#fff'
        style = f' style="background:#{color};color:{foreground}"'
    return f'<span class="priority"{style}>{esc(priority["name"])}</span>'

def render(data):
    validate(data)
    items = sorted((i for i in data['items'] if visible(i)), key=lambda i: (i.get('priority') or {}).get('rank', 2))
    has_loop = any(i.get('loop') is not None for i in items)
    rows = []
    for item in items:
        loop = item.get('loop')
        status = ''
        if has_loop:
            status = '<span>Not used</span>' if loop is None else f'<span>{esc(loop["state"].capitalize())}</span>'
            if loop and loop.get('short_reason'):
                status += f'<small>{esc(loop["short_reason"])}</small>'
        blockers = [b for b in item.get('blockers', []) if b['state'] == 'open']
        status += ''.join(f'<small>{link(b["id"], b.get("url"))} · {esc(b["source"])}</small>' for b in blockers)
        if not status:
            status = 'None identified'
        evidence = []
        if item['state'] == 'closed':
            reason = item.get('highlight_reason') or 'Retained because an open linked PR still needs attention.'
            evidence.append(f'<p><strong>Closed item retained:</strong> {esc(reason)}</p>')
        if loop:
            evidence.append(f'<p><strong>Loop:</strong> {esc(loop["reason"])}<small>{esc(loop["checked_at"])} · {esc(loop["config_source"])}</small></p>')
        evidence += [f'<p>{link(e["text"], e.get("url"))}</p>' for e in item['evidence']]
        evidence += [f'<p><strong>Open PR:</strong> {link(pr["id"], pr["url"])}</p>' for pr in item.get('open_prs', [])]
        evidence.append(f'<p><strong>Estimate:</strong> {esc(item["effort"]["basis"])}</p>')
        if item.get('applied_action'):
            evidence.append(f'<p><strong>Applied:</strong> {esc(item["applied_action"])}</p>')
        c = item['challenge']
        badge = ''
        if c['status'] != 'not-needed':
            label = {'completed':'Independently challenged', 'pending':'Challenge pending', 'unavailable':'Challenge unavailable'}[c['status']]
            badge = f'<small class="challenge">{label}</small>'
            evidence.append(f'<p><strong>Challenge:</strong> {esc(c["summary"])}</p>')
        previous = item['effort'].get('previous')
        labels = ' · '.join(item.get('workflow_labels', []))
        rows.append(f'''<tr><td>{link(item['id'], item['url'])}<strong class="issue-title">{esc(item['title'])}</strong><small>{esc(labels)}</small>{priority_badge(item.get('priority'))}{badge}</td><td><span class="treatment">{esc(item['treatment'].capitalize())}</span></td><td>{esc(item['effort']['estimate'])}{('<small>Was '+esc(previous)+'</small>') if previous else ''}</td><td>{status}</td><td><p>{esc(item['summary'])}</p><details><summary>Evidence and scope</summary>{''.join(evidence)}</details></td></tr>''')
    scope = data['scope']
    baselines = '; '.join(f'{b["repository"]}@{b["revision"]}' for b in data.get('baselines', []))
    limitations = ''.join(f'<li>{esc(x)}</li>' for x in data.get('limitations', []))
    challenge = data.get('challenge_summary')
    tail = f'<section><h2>Independent challenge</h2><p>{esc(challenge)}</p></section>' if challenge else ''
    tail += f'<section><h2>Grounding &amp; limitations</h2><p>{esc(baselines)}</p><ul>{limitations}</ul></section>'
    if has_loop:
        tail += '<p class="note">Loop eligibility is a checked snapshot, not a guarantee of the next dispatch. Reasons and configuration sources are in the evidence.</p>'
    template = (Path(__file__).resolve().parent.parent/'assets'/'report.html').read_text()
    values = {'SCOPE':esc(scope['label']), 'DATE':esc(data['reviewed_at']), 'GOAL':esc(scope['goal']), 'COUNT':str(len(items)), 'LOOP_HEADER':'Loop / blockers' if has_loop else 'Blocked by', 'ROWS':''.join(rows), 'TAIL':tail}
    # One pass: text in source data must never become another template directive.
    return re.sub(r'@@([A-Z_]+)@@', lambda m: values[m.group(1)], template)

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--no-open', action='store_true')
    args = p.parse_args(argv)
    try:
        data = json.loads(args.input.read_text())
        page = render(data)
        args.output.mkdir(parents=True, exist_ok=True)
        target = args.output/'report.html'
        target.write_text(page)
        (args.output/'report.json').write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n')
        print(target.resolve())
        if not args.no_open:
            webbrowser.open(target.resolve().as_uri())
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
        print(f'grooming report: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
