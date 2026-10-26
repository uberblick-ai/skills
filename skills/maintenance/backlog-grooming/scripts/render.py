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
# Defaults only: a repository's own scale and cap, passed as `capacity`, replace them.
DEFAULT_WEIGHTS = {'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 5}
DEFAULT_CAP = 25

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
    return parsed

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
        if item.get('url'):
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
        if 'created_at' in item:
            timestamp(text(item, 'created_at'))
        if item.get('no_change'):
            placement = item.get('placement') or {}
            if item['treatment'] != 'keep' or item['state'] == 'closed' or challenge['status'] == 'pending':
                raise ValueError(f'{ident}: no_change is only for an open item kept as it is')
            if 'proposed' in placement and placement['proposed'] != placement.get('current'):
                raise ValueError(f'{ident}: no_change cannot move the item to another milestone')
    validate_milestones(data)
    return data

def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f'{name} must be a number of at least 0')
    return value

def capacity(data):
    c = data.get('capacity') or {}
    weights = {str(k).upper(): number(v, f'capacity.weights.{k}') for k, v in (c.get('weights') or DEFAULT_WEIGHTS).items()}
    cap = number(c.get('cap', DEFAULT_CAP), 'capacity.cap')
    ceiling = number(c.get('ceiling', 2*cap), 'capacity.ceiling')
    if not cap or ceiling < cap:
        raise ValueError('capacity.cap must be above 0 and capacity.ceiling at least the cap')
    return weights, cap, ceiling

def validate_milestones(data):
    capacity(data)
    ids = set()
    for m in data.get('milestones', []):
        ident = str(m.get('id', ''))
        if not ident or ident in ids:
            raise ValueError(f'Milestone ids must be present and unique: {ident!r}')
        ids.add(ident)
        text(m, 'title')
        if m.get('url'):
            url(m['url'])
        for k in ('delivered_weight', 'other_open_weight'):
            number(m.get(k, 0), f'{ident}: {k}')
        if 'bounded' in m:
            text(m, 'bounded')
    for item in data['items']:
        for k, v in (item.get('placement') or {}).items():
            if k not in {'current', 'proposed'}:
                raise ValueError(f'{item["id"]}: placement takes current and proposed')
            if v is not None and str(v) not in ids:
                raise ValueError(f'{item["id"]}: placement.{k} names no milestone in milestones: {v!r}')

def weight(estimate, weights):
    """Weight of one estimate, or None when the scale does not know it."""
    key = str(estimate).strip().upper()
    if key == 'NONE':
        return 0
    if key in weights:
        return weights[key]
    try:
        return number(float(key), 'estimate')
    except ValueError:
        return None

def milestone_load(data):
    """Weigh each listed milestone before and after the proposed placements."""
    weights, cap, ceiling = capacity(data)
    loads = []
    for m in data.get('milestones', []):
        ident = str(m['id'])
        base = m.get('delivered_weight', 0) + m.get('other_open_weight', 0)
        before = after = base
        added = unknown = 0
        for item in data['items']:
            placement = item.get('placement') or {}
            if item['state'] == 'closed':
                continue
            current = placement.get('current')
            target = placement['proposed'] if 'proposed' in placement else current
            w = weight(item['effort']['estimate'], weights)
            if str(current) == ident and current is not None:
                before += w or 0
            if str(target) == ident and target is not None and not item['treatment'].startswith('close'):
                after += w or 0
                unknown += w is None
                added += str(current) != ident or current is None
        if after <= cap:
            status, note = 'Within cap', ''
        elif m.get('bounded') and after <= ceiling:
            status, note = 'Bounded exception', m['bounded']
        else:
            status = 'Overloaded'
            note = 'Above the ceiling even for one bounded step: split it into phases.' if after > ceiling else 'Move issues into a new milestone instead of adding more.'
        loads.append({'milestone': m, 'before': before, 'after': after, 'added': added, 'unknown': unknown, 'status': status, 'note': note})
    return loads, cap, ceiling

def fmt(value):
    return f'{value:g}'

def load_section(data):
    loads, cap, ceiling = milestone_load(data)
    if not loads:
        return '', 0
    rows = []
    for load in loads:
        m = load['milestone']
        name = link(m['title'], m.get('url')) + ('<small>New milestone, proposed</small>' if m.get('new') else '')
        change = fmt(load['before']) if load['before'] == load['after'] else f'{fmt(load["before"])} → {fmt(load["after"])}'
        details = []
        if load['added']:
            details.append(f'{load["added"]} issue{"s" if load["added"] != 1 else ""} proposed in')
        if load['unknown']:
            details.append(f'{load["unknown"]} without a known estimate, not counted')
        basis = f'<small>{esc(m["basis"])}</small>' if m.get('basis') else ''
        rows.append(f'<tr><td>{name}</td><td>{change}<small>{esc("; ".join(details))}</small>{basis}</td><td><span class="treatment">{load["status"]}</span><small>{esc(load["note"])}</small></td></tr>')
    weights, _, _ = capacity(data)
    scale = ', '.join(f'{k} {fmt(v)}' for k, v in weights.items())
    source = (data.get('capacity') or {}).get('source') or 'skill defaults'
    over = sum(load['status'] == 'Overloaded' for load in loads)
    section = f'''<section><h2>Milestone load</h2><p>Weight is the sum of estimates ({esc(scale)}) of delivered, open and proposed issues. Cap {fmt(cap)}; a milestone that is one bounded heavy step may reach {fmt(ceiling)}. Source: {esc(source)}.</p><div class="table-wrap"><table class="load" aria-label="Milestone load"><colgroup><col style="width:40%"><col style="width:25%"><col style="width:35%"></colgroup><thead><tr><th>Milestone</th><th>Weight now → proposed</th><th>Status</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></section>'''
    return section, over

def visible(item):
    return item['state'] != 'closed' or bool(item.get('open_prs') or item.get('highlight_reason'))

def oldest_first(items):
    """Oldest created first; items without created_at follow in input order."""
    return sorted(items, key=lambda i: (0, timestamp(i['created_at']).timestamp()) if i.get('created_at') else (1, 0))

def no_change_section(items, data):
    if not items:
        return ''
    titles = {str(m['id']): m['title'] for m in data.get('milestones', [])}
    rows = []
    for item in items:
        current = (item.get('placement') or {}).get('current')
        where = f' · {esc(titles[str(current)])}' if current is not None else ''
        rows.append(f'<li>{link(item["id"], item.get("url"))} <strong>{esc(item["title"])}</strong> · {esc(item["effort"]["estimate"])}{where}<small>{esc(item["summary"])}</small></li>')
    return f'<section><h2>No change required</h2><p>Clear, kept as they are and in the right place. Nothing to decide.</p><ul class="fit">{"".join(rows)}</ul></section>'

def priority_badge(priority):
    if not priority or priority.get('is_default'):
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
    shown = oldest_first(i for i in data['items'] if visible(i))
    items = [i for i in shown if not i.get('no_change')]
    fits = [i for i in shown if i.get('no_change')]
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
        labels = ' · '.join(([item['state'].capitalize()] if item['state'] != 'open' else []) + item.get('workflow_labels', []))
        rows.append(f'''<tr><td>{link(item['id'], item.get('url'))}<strong class="issue-title">{esc(item['title'])}</strong><small>{esc(labels)}</small>{priority_badge(item.get('priority'))}{badge}</td><td><span class="treatment">{esc(item['treatment'].capitalize())}</span></td><td>{esc(item['effort']['estimate'])}{('<small>Was '+esc(previous)+'</small>') if previous else ''}</td><td>{status}</td><td><p>{esc(item['summary'])}</p><details><summary>Evidence and scope</summary>{''.join(evidence)}</details></td></tr>''')
    scope = data['scope']
    baselines = '; '.join(f'{b["repository"]}@{b["revision"]}' for b in data.get('baselines', []))
    limitations = ''.join(f'<li>{esc(x)}</li>' for x in data.get('limitations', []))
    challenge = data.get('challenge_summary')
    load, overloaded = load_section(data)
    tail = load + no_change_section(fits, data)
    tail += f'<section><h2>Independent challenge</h2><p>{esc(challenge)}</p></section>' if challenge else ''
    tail += f'<section><h2>Grounding &amp; limitations</h2><p>{esc(baselines)}</p><ul>{limitations}</ul></section>'
    if has_loop:
        tail += '<p class="note">Loop eligibility is a checked snapshot, not a guarantee of the next dispatch. Reasons and configuration sources are in the evidence.</p>'
    template = (Path(__file__).resolve().parent.parent/'assets'/'report.html').read_text(encoding='utf-8')
    values = {'SCOPE':esc(scope['label']), 'DATE':esc(data['reviewed_at']), 'GOAL':esc(scope['goal']), 'COUNT':str(len(items)), 'COUNT_NOTES':(f' · {len(fits)} with no change required' if fits else '') + (f' · {overloaded} milestone{"s" if overloaded != 1 else ""} over the cap' if overloaded else ''), 'LOOP_HEADER':'Loop / blockers' if has_loop else 'Blocked by', 'ROWS':''.join(rows), 'TAIL':tail}
    # One pass: text in source data must never become another template directive.
    return re.sub(r'@@([A-Z_]+)@@', lambda m: values[m.group(1)], template)

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--no-open', action='store_true')
    args = p.parse_args(argv)
    try:
        data = json.loads(args.input.read_text(encoding='utf-8'))
        page = render(data)
        args.output.mkdir(parents=True, exist_ok=True)
        target = args.output/'report.html'
        target.write_text(page, encoding='utf-8')
        (args.output/'report.json').write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
        print(target.resolve())
        if not args.no_open:
            webbrowser.open(target.resolve().as_uri())
    except (ValueError, TypeError, KeyError, AttributeError, OSError) as error:
        print(f'grooming report: {error}', file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    sys.exit(main())
