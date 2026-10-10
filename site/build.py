"""Build skills.uberblick.ai from the skills in this repository into site/out.

Links use Pages' extensionless URLs (/skills/<name>, not /skills/<name>.html,
which Pages redirects), so the pages are meant to be served, not opened as files.

Standard library only:

    python3 site/build.py

Every skill under skills/<group>/<name>/ gets a page from its SKILL.md. The
optional site/content/skills/<name>.json adds the question it answers, example
asks, steps, screenshots and requirements; without it the page still builds
from the frontmatter. Group names and descriptions come from each group's
README.md, plugins from .claude-plugin/marketplace.json, the overview's text
from site/content/home.json.
"""
import html, json, re, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_DIR = ROOT.parent
CONTENT, OUT = ROOT / 'content', ROOT / 'out'
SITE = 'https://skills.uberblick.ai'
REPO = 'https://github.com/uberblick-ai/skills'
RAW = 'https://raw.githubusercontent.com/uberblick-ai/skills/main'
AGENTS = 'https://agents.uberblick.ai'
INSTALL = 'npx skills@latest add uberblick-ai/skills'
TAGLINE = 'Agent skills for Uberblick and the ub-agents loop. One command, any agent.'

# ---------- Reading the repository ----------

def frontmatter(text):
    """The subset of YAML that SKILL.md frontmatter uses: scalars, folded `>-` blocks and one level of nesting."""
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        raise ValueError('SKILL.md has no frontmatter')
    data, parent, key, folded = {}, None, None, None
    for line in m.group(1).split('\n'):
        indent = len(line) - len(line.lstrip())
        if folded is not None and (indent > folded or not line.strip()):
            target = data[parent] if parent and folded > 2 else data
            target[key] = (target[key] + ' ' + line.strip()).strip()
            continue
        folded = None
        kv = re.match(r'^(\s*)([A-Za-z0-9_-]+):\s*(.*)$', line)
        if not kv:
            continue
        lead, k, v = len(kv.group(1)), kv.group(2), kv.group(3).strip()
        if lead == 0:
            parent = None
        target = data[parent] if parent and lead > 0 else data
        if v in ('>-', '>', '|', '|-'):
            target[k], key, folded = '', k, lead
        elif v == '':
            data[k], parent = {}, k
        else:
            target[k] = v.strip('"\'')
    return data


def plain(md):
    md = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', md)
    return re.sub(r'[*`]', '', md).strip()


def group_info(gdir):
    text = (gdir / 'README.md').read_text()
    name = re.search(r'^# (.+)$', text, re.M).group(1).strip()
    body = text.split('\n', 1)[1].strip()
    para = plain(body.split('\n\n')[0].replace('\n', ' '))
    para = re.sub(r'\s*Plugin: \S+\s*$', '', para)
    return name, para


def plugins():
    market = json.loads((REPO_DIR / '.claude-plugin' / 'marketplace.json').read_text())
    return {path.rstrip('/').split('/')[-1]: p['name'] for p in market['plugins'] for path in p.get('skills', [])}


def collect():
    home = json.loads((CONTENT / 'home.json').read_text())
    plugin_of = plugins()
    gdirs = sorted(d for d in (REPO_DIR / 'skills').iterdir() if d.is_dir())
    order = {g: i for i, g in enumerate(home['groups'])}
    gdirs.sort(key=lambda d: (order.get(d.name, len(order)), d.name))
    groups, skills = [], []
    for gdir in gdirs:
        name, desc = group_info(gdir)
        members = []
        for sdir in sorted(d for d in gdir.iterdir() if (d / 'SKILL.md').is_file()):
            fm = frontmatter((sdir / 'SKILL.md').read_text())
            extra_path = CONTENT / 'skills' / f'{sdir.name}.json'
            extra = json.loads(extra_path.read_text()) if extra_path.is_file() else {}
            s = {
                'slug': fm['name'], 'group': gdir.name, 'group_name': name,
                'version': (fm.get('metadata') or {}).get('version', ''),
                'description': fm['description'], 'compatibility': fm.get('compatibility', ''),
                'plugin': plugin_of.get(sdir.name, gdir.name),
                'path': f'skills/{gdir.name}/{sdir.name}',
                'files': [p.relative_to(sdir).as_posix() for p in sorted(sdir.rglob('*.md')) if p.name != 'SKILL.md'],
                **extra,
            }
            s.setdefault('short', s['description'])
            members.append(s)
        if members:
            groups.append({'id': gdir.name, 'name': name, 'description': desc, 'plugin': members[0]['plugin'], 'skills': members})
            skills += members
    return home, groups, skills

# ---------- Page parts ----------

e = html.escape


def head(title, description, canonical, pre):
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(description)}">
<link rel="canonical" href="{canonical}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="{pre}assets/site.css">
</head>
<body>
'''


def header(pre, skills):
    return f'''<header class="top">
  <a class="mark" href="{pre or "./"}">uberblick<span>/</span>skills</a>
  <span class="count">{len(skills)} skills</span>
  <nav>
    <a href="{AGENTS}">ub-agents</a>
    <a href="{REPO}/blob/main/CHANGELOG.md">Changelog</a>
    <a href="{REPO}">GitHub</a>
  </nav>
</header>'''


FOOTER = f'''<footer class="foot">
  <span>MIT license</span>
  <a href="{REPO}">Source</a>
  <a href="{REPO}/blob/main/AGENTS.md">Add a skill</a>
  <a href="{REPO}/blob/main/.claude-plugin/marketplace.json">Marketplace</a>
  <a href="{AGENTS}">ub-agents</a>
</footer>'''

JS = r'''<script>
document.querySelectorAll('.copy').forEach(function (btn) {
  btn.addEventListener('click', function () {
    var code = btn.parentNode.querySelector('code');
    function done(l) { btn.textContent = l; setTimeout(function () { btn.textContent = 'Copy'; }, 1600); }
    function select() { var r = document.createRange(); r.selectNodeContents(code); var s = getSelection(); s.removeAllRanges(); s.addRange(r); done('Selected'); }
    try { navigator.clipboard.writeText(code.textContent).then(function () { done('Copied'); }, select); } catch (e) { select(); }
  });
});
document.querySelectorAll('.tabs').forEach(function (box) {
  var tabs = box.querySelectorAll('[role="tab"]');
  tabs.forEach(function (tab) { tab.addEventListener('click', function () {
    tabs.forEach(function (t) { var on = t === tab; t.setAttribute('aria-selected', on); document.getElementById(t.getAttribute('aria-controls')).hidden = !on; });
  }); });
});
(function () {
  var f = document.getElementById('filter'); if (!f) return;
  f.addEventListener('input', function () {
    var q = f.value.trim().toLowerCase();
    document.querySelectorAll('[data-skill]').forEach(function (e) { e.hidden = q && e.dataset.find.indexOf(q) < 0; });
    document.querySelectorAll('[data-group]').forEach(function (g) { g.hidden = !g.querySelector('[data-skill]:not([hidden])'); });
  });
})();
(function () { var d = document.querySelector('details.side'); if (!d) return; var mq = window.matchMedia('(min-width: 900px)');
  function sync() { if (mq.matches) d.open = true; } sync(); if (mq.addEventListener) mq.addEventListener('change', sync); })();
</script>'''


def find(s):
    return e(' '.join([s['slug'], s['group_name'], s['short'], s.get('question', '')]).lower())


def sidebar(pre, groups, current=None, filt=True):
    out = []
    for g in groups:
        items = ''.join(
            f'<li data-skill="{s["slug"]}" data-find="{find(s)}"><a{" class=\"on\"" if s is current else ""} href="{pre}skills/{s["slug"]}">{s["slug"]}</a></li>'
            for s in g['skills'])
        out.append(f'<li data-group="{g["id"]}"><span class="grp">{e(g["name"])} <span>{len(g["skills"])}</span></span><ul>{items}</ul></li>')
    f = '<input class="filter" id="filter" type="search" placeholder="Filter skills" aria-label="Filter skills">' if filt else ''
    on = ' class="on"' if current is None else ''
    summary = 'Skills' + (f' · {current["slug"]}' if current else '')
    return f'''<details class="side" open>
    <summary>{summary}</summary>
    <div class="side-in">
      {f}
      <ul class="plain"><li><a{on} href="{pre or "./"}">Overview</a></li></ul>
      <ul id="nav">{"".join(out)}</ul>
      <ul class="plain">
        <li><a href="{REPO}/blob/main/AGENTS.md">Add a skill</a></li>
        <li><a href="https://agentskills.io/specification">Specification</a></li>
      </ul>
    </div>
  </details>'''


def tabs(cmds, idp):
    btns, panels = [], []
    for i, (tid, label, cmd, sh) in enumerate(cmds):
        sel = 'true' if i == 0 else 'false'
        btns.append(f'<button role="tab" id="t-{idp}-{tid}" aria-selected="{sel}" aria-controls="p-{idp}-{tid}" type="button">{label}</button>')
        panels.append(f'<div class="panel{" sh" if sh else ""}" role="tabpanel" id="p-{idp}-{tid}" aria-labelledby="t-{idp}-{tid}"{"" if i == 0 else " hidden"}><code>{e(cmd)}</code><button class="copy" type="button">Copy</button></div>')
    return f'<div class="tabs"><div class="tablist" role="tablist" aria-label="Install with">{"".join(btns)}</div>{"".join(panels)}</div>'


def install_cmds(groups, s=None):
    if s is None:
        return [('any', 'Any agent', INSTALL, True),
                ('cc', 'Claude Code plugin', f'/plugin install {groups[0]["plugin"]} --marketplace uberblick-ai/skills', False)]
    return [('one', 'This skill', f'{INSTALL} --skill {s["slug"]}', True),
            ('cc', 'Claude Code plugin', f'/plugin install {s["plugin"]} --marketplace uberblick-ai/skills', False),
            ('glob', 'Every project', f'{INSTALL} --skill {s["slug"]} -g', True),
            ('all', 'All skills', INSTALL, True)]


def shot(image, caption, pre, eager=False):
    lazy = '' if eager else ' loading="lazy"'
    return (f'<figure class="shot"><div class="bar"><span>report.html</span></div>'
            f'<img class="l" src="{pre}img/{image}-light.webp" alt="{e(caption)}" width="2400"{lazy}>'
            f'<img class="d" src="{pre}img/{image}-dark.webp" alt="" width="2400"{lazy}>'
            f'<figcaption>{e(caption)}</figcaption></figure>')

# ---------- Pages ----------

def overview(home, groups, skills):
    stats = [(len(skills), 'skills'), (len(groups), 'groups'), (1, 'command to install'), (0, 'services to run')]
    stats = ''.join(f'<div class="stat"><b>{n}</b><span>{l}</span></div>' for n, l in stats)
    problem = ''.join(f'<p>{e(p)}</p>' for p in home['problem']['paragraphs'])
    blocks = []
    for i, g in enumerate(groups, 1):
        rows = ''
        for s in g['skills']:
            ask = f'<span>Ask: "{e(s["question"])}"</span>' if s.get('question') else ''
            version = f'v{e(s["version"])}' if s['version'] else ''
            rows += (f'<li data-skill="{s["slug"]}" data-find="{find(s)}"><a href="skills/{s["slug"]}"><span class="n">{s["slug"]}</span>'
                     f'<span class="d">{e(s["short"])}{ask}</span><span class="v">{version}</span></a></li>')
        blocks.append(f'<div class="gblock" data-group="{g["id"]}"><div class="gblock-h"><span class="num">{i:02d}</span><h3>{e(g["name"])}</h3>'
                      f'<code>plugin {g["plugin"]}</code><p>{e(g["description"])}</p></div><ul class="sk-list">{rows}</ul></div>')
    cards = ''.join(
        f'<article class="qcard"><span class="lab">{e(q["label"])}</span><h3>{e(q["question"])}</h3><ul class="links">'
        + ''.join(f'<li><span class="tag">{e(t)}</span><a href="{e(h)}">{e(n)}</a></li>' for t, n, h in q['links'])
        + '</ul></article>' for q in home['questions'])
    changes = ''.join(f'<li><time>{d}</time><span class="tag">{e(t)}</span><span>{e(x)}</span></li>' for d, t, x in home['changes'])
    skill_links = ''.join(f'<li><a href="skills/{s["slug"]}">{s["slug"]}</a></li>' for s in skills)
    return head('uberblick skills', TAGLINE, f'{SITE}/', '') + header('', skills) + f'''
<div class="layout">
  {sidebar('', groups)}
  <main class="main">
    <div class="hero">
      <p class="kicker">{e(home["eyebrow"])}</p>
      <h1>{e(home["headline"])}</h1>
      <p class="lede">{e(home["lede"])}</p>
      <div class="cta">{tabs(install_cmds(groups), "home")}<a href="#skills">Browse the skills →</a></div>
      <div class="stats">{stats}</div>
    </div>
    <section class="blk"><h2>{e(home["problem"]["title"])}</h2>{problem}</section>
    <section class="blk" id="skills">
      <div class="blk-h"><h2>The skills, grouped by what they work on.</h2></div>
      <p class="blk-intro">Each group is a folder in the repository and a plugin in Claude Code. Open a skill for install steps and its report.</p>
      {"".join(blocks)}
    </section>
    <section class="blk">
      <div class="blk-h"><h2>What do you want to do?</h2></div>
      <p class="blk-intro">Find your question, then the skill or page that answers it.</p>
      <div class="qcards">{cards}</div>
    </section>
    <section class="blk">
      <div class="blk-h"><h2>Recent changes.</h2><a href="{REPO}/blob/main/CHANGELOG.md">See the changelog</a></div>
      <ul class="changes">{changes}</ul>
    </section>
    <section class="blk about">
      <h2>Who builds this.</h2>
      <p>{home["about"]}</p>
      <div class="cols">
        <div><h3>Learn</h3><ul><li><a href="{AGENTS}">ub-agents</a></li><li><a href="{AGENTS}/docs/installation.html">Installation</a></li><li><a href="{AGENTS}/docs/configuration/index.html">Configuration</a></li><li><a href="{AGENTS}/docs/best-practices/small-issues.html">Best practices</a></li></ul></div>
        <div><h3>Skills</h3><ul>{skill_links}<li><a href="{REPO}/blob/main/CHANGELOG.md">Changelog</a></li><li><a href="{REPO}/blob/main/AGENTS.md">Add a skill</a></li></ul></div>
        <div><h3>Agents</h3><ul><li><a href="skills.md">skills.md</a></li><li><a href="llms.txt">llms.txt</a></li><li><a href="{REPO}/blob/main/.claude-plugin/marketplace.json">marketplace.json</a></li></ul></div>
      </div>
    </section>
  </main>
</div>
{FOOTER}
{JS}
</body>
</html>
'''


def skill_page(s, groups, skills):
    pre = '../'
    i = skills.index(s)
    prev, nxt = (skills[i - 1] if i else None), (skills[i + 1] if i + 1 < len(skills) else None)
    pager = (f'<a class="prev" href="{prev["slug"]}"><span>Previous</span>{prev["slug"]}</a>' if prev
             else f'<a class="prev" href="{pre or "./"}"><span>Back to</span>All skills</a>')
    if nxt:
        pager += f'<a class="next" href="{nxt["slug"]}"><span>Next</span>{nxt["slug"]}</a>'
    shots = s.get('shots', [])
    first = shot(shots[0]['image'], shots[0]['caption'], pre, eager=True) if shots else ''
    more = ''.join(shot(x['image'], x['caption'], pre) for x in shots[1:])
    secs = []
    if s.get('asks') or s.get('steps'):
        asks = ''.join(f'<li>"{e(a)}"</li>' for a in s.get('asks', []))
        steps = ''.join(f'<li>{t}</li>' for t in s.get('steps', []))
        secs.append(f'<section class="sk-sec"><h2>Use it</h2><p>Ask your agent in plain words. Any of these will do:</p>'
                    f'<ul class="asks">{asks}</ul><ol class="steps">{steps}</ol></section>')
    if s.get('facts'):
        facts = ''.join(f'<div><dt>{e(a)}</dt><dd>{e(b)}</dd></div>' for a, b in s['facts'])
        secs.append(f'<section class="sk-sec"><h2>{e(s.get("facts_title", "Details"))}</h2><dl class="facts">{facts}</dl></section>')
    if more:
        secs.append(f'<section class="sk-sec"><h2>In the report</h2><div class="shots">{more}</div></section>')
    needs = s.get('needs') or ([['Needs', e(s['compatibility'])]] if s['compatibility'] else [])
    if needs:
        rows = ''.join(f'<tr><th>{e(a)}</th><td>{b}</td></tr>' for a, b in needs)
        secs.append(f'<section class="sk-sec"><h2>Requirements</h2><div class="table"><table class="kv">{rows}</table></div></section>')
    srcs = ''.join(f'<li><a href="{REPO}/blob/main/{s["path"]}/{p}">{p}</a></li>' for p in ['SKILL.md'] + s['files'])
    secs.append(f'<section class="sk-sec"><h2>Source</h2><ul class="srcs">{srcs}</ul></section>')
    version = f'<span class="chip">v{e(s["version"])}</span>' if s['version'] else ''
    return head(f'{s["slug"]} · uberblick skills', s['short'], f'{SITE}/skills/{s["slug"]}', pre) + header(pre, skills) + f'''
<div class="layout">
  {sidebar(pre, groups, s, filt=False)}
  <main class="main sk">
    <p class="crumb"><a href="{pre or "./"}">Skills</a> / {e(s["group_name"])}</p>
    <div class="sk-title"><h1>{s["slug"]}</h1>{version}<span class="chip acc">plugin {s["plugin"]}</span></div>
    <p class="sk-lede">{e(s.get("lede", s["description"]))}</p>
    {first}
    <section class="sk-sec" id="install">
      <h2>Install</h2>
      {tabs(install_cmds(groups, s), "sk")}
      <p class="note">Works in Claude Code, Codex, Cursor, OpenCode and the other agents the skills CLI supports. <code>npx skills update</code> keeps it current.</p>
    </section>
    {"".join(secs)}
    <nav class="pager">{pager}</nav>
  </main>
</div>
{FOOTER}
{JS}
</body>
</html>
'''


def not_found(groups, skills):
    body = head('Page not found · uberblick skills', TAGLINE, f'{SITE}/', '/') + header('/', skills) + f'''
<div class="layout">
  {sidebar('/', groups, filt=False)}
  <main class="main"><div class="hero"><h1>Page not found.</h1><p class="lede">Start at the <a href="/">overview</a>, or pick a skill on the left.</p></div></main>
</div>
{FOOTER}
{JS}
</body>
</html>
'''
    return re.sub(r'<link rel="canonical"[^>]*>\n', '', body)


def skills_md(groups):
    out = ['# Uberblick skills', '', TAGLINE, '', '```sh', INSTALL, '```', '']
    for g in groups:
        out += [f'## {g["name"]}', '', g['description'], f'Claude Code plugin: `/plugin install {g["plugin"]} --marketplace uberblick-ai/skills`', '']
        for s in g['skills']:
            out += [f'### {s["slug"]}', '', s['description'], '',
                    f'- Page: {SITE}/skills/{s["slug"]}', f'- SKILL.md: {RAW}/{s["path"]}/SKILL.md',
                    f'- Install: `{INSTALL} --skill {s["slug"]}`', '']
    return '\n'.join(out)


def llms_txt(home, groups):
    out = ['# Uberblick skills', '', f'> {TAGLINE} Install with `{INSTALL}`.', '', home['lede'], '']
    for g in groups:
        out += [f'## {g["name"]}', '']
        out += [f'- [{s["slug"]}]({RAW}/{s["path"]}/SKILL.md): {s["short"]}' for s in g['skills']]
        out.append('')
    out += ['## Optional', '', f'- [All skills in one file]({SITE}/skills.md)', f'- [ub-agents]({AGENTS}): the loop these skills report on', '']
    return '\n'.join(out)


def main():
    home, groups, skills = collect()
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / 'assets').mkdir(parents=True)
    (OUT / 'skills').mkdir()
    shutil.copy(ROOT / 'site.css', OUT / 'assets' / 'site.css')
    shutil.copytree(ROOT / 'img', OUT / 'img')
    missing = [x['image'] for s in skills for x in s.get('shots', [])
               for v in ('light', 'dark') if not (ROOT / 'img' / f'{x["image"]}-{v}.webp').is_file()]
    if missing:
        sys.exit('site/img is missing: ' + ', '.join(sorted(set(missing))))
    (OUT / 'index.html').write_text(overview(home, groups, skills))
    for s in skills:
        (OUT / 'skills' / f'{s["slug"]}.html').write_text(skill_page(s, groups, skills))
    (OUT / '404.html').write_text(not_found(groups, skills))
    (OUT / 'skills.md').write_text(skills_md(groups))
    (OUT / 'llms.txt').write_text(llms_txt(home, groups))
    urls = [f'{SITE}/'] + [f'{SITE}/skills/{s["slug"]}' for s in skills]
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + ''.join(f'  <url><loc>{u}</loc></url>\n' for u in urls) + '</urlset>\n')
    (OUT / 'robots.txt').write_text(f'User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n')
    print(f'{len(skills)} skills in {len(groups)} groups')


if __name__ == '__main__':
    main()
