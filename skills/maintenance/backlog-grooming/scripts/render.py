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
from urllib.parse import quote, urlsplit

TREATMENTS = {'keep', 'narrow', 'combine', 'defer', 'close delivered', 'close unnecessary', 'track only'}
# Treatments that end an issue, so it needs no milestone recommendation.
UNPLACED = {'combine', 'close delivered', 'close unnecessary'}
# Defaults only: a repository's own scale and cap, passed as `capacity`, replace them.
DEFAULT_WEIGHTS = {'XS': 0, 'S': 1, 'M': 2, 'L': 3, 'XL': 5}
DEFAULT_CAP = 25
# The table groups by milestone once this share of open items has one.
GROUPING_SHARE = 0.4
CLAUDE_CODE = 'claude://code/new?q='
# Keeps the discuss link a size browsers and the desktop app accept; the rest stays in report.json.
PROMPT_LIMIT = 6000

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
        for k in ('bounded', 'goal'):
            if k in m:
                text(m, k)
        if m.get('due_on'):
            due_date(m['due_on'])
        if m.get('state', 'open') not in {'open', 'closed'}:
            raise ValueError(f'{ident}: milestone state must be open or closed')
    for item in data['items']:
        placement = item.get('placement') or {}
        for k, v in placement.items():
            if k == 'reason':
                text(placement, 'reason')
                continue
            if k not in {'current', 'proposed'}:
                raise ValueError(f'{item["id"]}: placement takes current, proposed and reason')
            if v is not None and str(v) not in ids:
                raise ValueError(f'{item["id"]}: placement.{k} names no milestone in milestones: {v!r}')
    usage = data.get('milestone_usage')
    if usage is not None:
        text(usage, 'summary')
    if grouping(data)['grouped']:
        for item in data['items']:
            placement = item.get('placement') or {}
            needs = item['state'] == 'open' and placement.get('current') is None and item['treatment'] not in UNPLACED
            if needs and ('proposed' not in placement or not placement.get('reason')):
                raise ValueError(f'{item["id"]}: the report groups by milestone, so an open issue without one needs '
                                 'placement.proposed (a milestone id, or null to keep it without) and placement.reason')

def due_date(value):
    """A due date as YYYY-MM-DD or a timestamp with timezone."""
    if not isinstance(value, str):
        raise ValueError(f'due_on must be a date: {value!r}')
    return datetime.fromisoformat(value.replace('Z', '+00:00')).date()

def grouping(data):
    """How many open items have a milestone now, and whether the table groups by it."""
    open_items = [i for i in data['items'] if i['state'] != 'closed']
    placed = sum((i.get('placement') or {}).get('current') is not None for i in open_items)
    share = placed / len(open_items) if open_items else 0
    return {'placed': placed, 'open': len(open_items), 'share': share, 'grouped': bool(placed) and share >= GROUPING_SHARE}

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

def placement_label(item, titles):
    """What the row recommends for its milestone, or '' when it stays put."""
    placement = item.get('placement') or {}
    current = placement.get('current')
    if 'proposed' not in placement or item['treatment'] in UNPLACED:
        return ''
    target = placement['proposed']
    if target is None:
        return 'Keep without milestone' if current is None else 'Take out of its milestone'
    if current is None:
        return f'Add to {titles[str(target)]}'
    return '' if str(target) == str(current) else f'Move to {titles[str(target)]}'

def pretty_date(value):
    d = due_date(value)
    return f'{d.day} {d:%b %Y}'

def milestone_groups(items, data):
    """Table groups by current milestone, No milestone last; [] for a flat table."""
    if not grouping(data)['grouped']:
        return []
    order = [str(m['id']) for m in data.get('milestones', [])]
    by_id = {str(m['id']): m for m in data.get('milestones', [])}
    members = {}
    for item in items:
        current = (item.get('placement') or {}).get('current')
        members.setdefault(None if current is None else str(current), []).append(item)
    keys = [k for k in order if k in members] + ([None] if None in members else [])
    if len(keys) < 2:
        return []
    loads = {str(l['milestone']['id']): l for l in milestone_load(data)[0]}
    groups = []
    for key in keys:
        group = members[key]
        count = f'{len(group)} issue{"s" if len(group) != 1 else ""}'
        if key is None:
            labels = [placement_label(i, {k: '' for k in by_id}) for i in group]
            add = sum(l.startswith('Add to') for l in labels)
            keep = sum(l == 'Keep without milestone' for l in labels)
            meta = [count] + ([f'{add} to add to a milestone'] if add else []) + ([f'{keep} to keep without one'] if keep else [])
            title, goal = esc('No milestone'), ''
        else:
            m, load = by_id[key], loads[key]
            weight = fmt(load['before']) if load['before'] == load['after'] else f'{fmt(load["before"])} → {fmt(load["after"])}'
            is_open = m.get('state', 'open') == 'open'
            # "No due date" only says something when other milestones have one.
            due = 'No due date' if any(x.get('due_on') for x in by_id.values()) else ''
            if m.get('due_on'):
                late = is_open and due_date(m['due_on']) < timestamp(data['reviewed_at']).date()
                due = f'{"Overdue, due" if late else "Due"} {pretty_date(m["due_on"])}'
            meta = ([] if is_open else ['Closed']) + ([due] if due else []) + [count, f'weight {weight}, {load["status"].lower()}']
            title, goal = link(m['title'], m.get('url')), m.get('goal', '')
        goal_html = f'<small>{esc(goal)}</small>' if goal else ''
        header = f'<tr class="group"><th colspan="5" scope="rowgroup"><strong>{title}</strong> <span>{esc(" · ".join(meta))}</span>{goal_html}</th></tr>'
        groups.append((header, group))
    return groups

def grouping_note(data, grouped):
    g = grouping(data)
    if not g['placed']:
        return ''
    share = f'{g["placed"]} of {g["open"]} open items in a milestone ({g["share"]:.0%})'
    if grouped:
        return f' · grouped by milestone: {share}'
    if g['grouped']:
        return f' · {share}, all in one, so not grouped'
    return f' · {share}, under {GROUPING_SHARE:.0%}, so not grouped'

def one_line(value, limit=240):
    value = ' '.join(str(value).split())
    return value if len(value) <= limit else value[:limit - 1].rstrip() + '…'

def discuss_link(data, items, report=None):
    """Opens a new Claude Code session with a prompt to discuss the findings, numbered as in the table. The prompt is
    filled in, not sent, and asks for no change until the person says so."""
    scope = data['scope']
    titles = {str(m['id']): m['title'] for m in data.get('milestones', [])}
    head = (f"From the backlog grooming report for {one_line(scope['label'])}, reviewed {data['reviewed_at']}"
            + (f", in {report}" if report else '') + f".\nGoal: {one_line(scope['goal'])}\n")
    usage = data.get('milestone_usage')
    if usage:
        head += f"Milestone usage: {one_line(usage['summary'])}\n"
    over = [l['milestone']['title'] for l in milestone_load(data)[0] if l['status'] == 'Overloaded']
    if over:
        head += f"Over the cap: {', '.join(over)}\n"
    tail = ("\nLet's discuss these findings before changing anything. Ask me which numbers to start with, read the "
            "issues and the evidence in the report for those, and challenge any recommendation that looks wrong. "
            "Change no issues, labels or milestones until I say so.")
    lines, budget = [], PROMPT_LIMIT - len(head) - len(tail)
    for n, item in enumerate(items, 1):
        move = placement_label(item, titles)
        reason = (item.get('placement') or {}).get('reason')
        line = (f"{n}. {item['id']} {one_line(item['title'], 90)}: {item['treatment']}, {item['effort']['estimate']}. "
                f"{one_line(item['summary'])}" + (f" Milestone: {move}" + (f" ({one_line(reason, 160).rstrip('.')})" if reason else '') + '.' if move else ''))
        if len(line) + 1 > budget:
            lines.append(f"…and {len(items) - n + 1} more in the report.")
            break
        lines.append(line)
        budget -= len(line) + 1
    return CLAUDE_CODE + quote(head + '\nFindings, numbered as in the table:\n' + '\n'.join(lines) + '\n' + tail, safe='')

def render(data, report=None):
    validate(data)
    shown = oldest_first(i for i in data['items'] if visible(i))
    # An issue without a workflow label still needs one, so it stays a decision.
    fits = [i for i in shown if i.get('no_change') and i.get('workflow_labels')]
    items = [i for i in shown if i not in fits]
    has_loop = any(i.get('loop') is not None for i in items)
    titles = {str(m['id']): m['title'] for m in data.get('milestones', [])}
    groups = milestone_groups(items, data)
    # Rows are numbered in table order, so "discuss 3" means the same row on the page and in the prompt.
    ordered = [i for _, members in groups for i in members] if groups else items
    number = {item['id']: n for n, item in enumerate(ordered, 1)}
    rows = {}
    for item in ordered:
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
        move = placement_label(item, titles)
        reason = (item.get('placement') or {}).get('reason')
        finding = f'<p>{esc(item["summary"])}</p>' + (f'<p class="placement"><strong>Milestone:</strong> {esc(reason)}</p>' if reason else '')
        rows[item['id']] = f'''<tr><td><span class="n">{number[item['id']]}</span>{link(item['id'], item.get('url'))}<strong class="issue-title">{esc(item['title'])}</strong><small>{esc(labels)}</small>{priority_badge(item.get('priority'))}{badge}</td><td><span class="treatment">{esc(item['treatment'].capitalize())}</span>{f'<small>{esc(move)}</small>' if move else ''}</td><td>{esc(item['effort']['estimate'])}{('<small>Was '+esc(previous)+'</small>') if previous else ''}</td><td>{status}</td><td>{finding}<details><summary>Evidence and scope</summary>{''.join(evidence)}</details></td></tr>'''
    if groups:
        body = ''.join(f'<tbody>{header}{"".join(rows[i["id"]] for i in members)}</tbody>' for header, members in groups)
    else:
        body = f'<tbody>{"".join(rows.values())}</tbody>'
    scope = data['scope']
    baselines = '; '.join(f'{b["repository"]}@{b["revision"]}' for b in data.get('baselines', []))
    limitations = ''.join(f'<li>{esc(x)}</li>' for x in data.get('limitations', []))
    challenge = data.get('challenge_summary')
    load, overloaded = load_section(data)
    usage = data.get('milestone_usage')
    if usage:
        basis = f'<small>{esc(usage["basis"])}</small>' if usage.get('basis') else ''
        load = f'<section><h2>Milestone usage</h2><p>{esc(usage["summary"])}</p>{basis}</section>' + load
    tail = load + no_change_section(fits, data)
    tail += f'<section><h2>Independent challenge</h2><p>{esc(challenge)}</p></section>' if challenge else ''
    tail += f'<section><h2>Grounding &amp; limitations</h2><p>{esc(baselines)}</p><ul>{limitations}</ul></section>'
    if has_loop:
        tail += '<p class="note">Loop eligibility is a checked snapshot, not a guarantee of the next dispatch. Reasons and configuration sources are in the evidence.</p>'
    template = (Path(__file__).resolve().parent.parent/'assets'/'report.html').read_text(encoding='utf-8')
    values = {'SCOPE':esc(scope['label']), 'DATE':esc(data['reviewed_at']), 'GOAL':esc(scope['goal']), 'COUNT':str(len(items)), 'COUNT_NOTES':(f' · {len(fits)} with no change required' if fits else '') + (f' · {overloaded} milestone{"s" if overloaded != 1 else ""} over the cap' if overloaded else '') + grouping_note(data, bool(groups)), 'DISCUSS':esc(discuss_link(data, ordered, report)) if ordered else '', 'LOOP_HEADER':'Loop / blockers' if has_loop else 'Blocked by', 'ROWS':body, 'TAIL':tail}
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
        page = render(data, (args.output/'report.json').resolve())
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
