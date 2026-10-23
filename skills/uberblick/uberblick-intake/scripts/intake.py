#!/usr/bin/env python3
"""Facts and corpus writes for the uberblick-intake skill. Standard library, `git`, and `ub` for the writes.

    intake.py scan CHECKOUT [--max-commits N] > scan.json      # Markdown, docs site, git churn, tests, labels
    intake.py hot scan.json [--limit 15]                       # the churn and direction changes, readable
    intake.py tests scan.json [--titles 80]                    # the test focus per area and the e2e journeys
    intake.py blocks DOC.md                                    # one Uberblick Markdown file as create_doc arguments
    intake.py check PLAN [--scan scan.json] [--checkout PATH] [--tags tags.json]  # the plan against the scan and the corpus rules
    intake.py review PLAN --scan scan.json --out review.html [--open]  # the page a person approves before writes
    intake.py calls PLAN --tags tags.json > calls.json         # the ordered corpus writes, with $ref placeholders
    intake.py ub --calls calls.json --checkout PATH [--out applied.json]  # run them through one `ub mcp serve`
    intake.py resolve --calls calls.json --uuids uuids.json    # for the MCP tools: the rest, UUIDs filled in
    intake.py corpus --checkout PATH --dir DIR                 # the workspace's tags, sidebar and documents

`scan` and `check` only read. `ub` writes to the Uberblick workspace the checkout is bound to. See
references/plan.md for the plan and references/analysis.md for how to read the scan.
"""

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import signal
import subprocess
import sys
import time
import webbrowser
from collections import Counter, defaultdict
from pathlib import Path

# --------------------------------------------------------------------------------------------------- scan helpers

SCHEMA_VERSION = 2
MD_EXT = (".md", ".mdx", ".markdown")
NOISE_DIRS = re.compile(r"(^|/)(node_modules|vendor|third[_-]party|dist|build|out|\.venv|venv|target|"
                        r"__snapshots__|fixtures?|testdata|test-data|snapshots)(/|$)", re.I)
VENDORED = re.compile(r"(^|/)(node_modules|vendor|third[_-]party)/", re.I)
LOCKFILES = re.compile(r"(^|/)(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|Cargo\.lock|go\.sum|poetry\.lock|"
                       r"uv\.lock|Gemfile\.lock|composer\.lock|bun\.lockb?|mix\.lock|gradle\.lockfile|"
                       r"\.yarn/.*|versions\.lock)$")
CHURN_NOISE = re.compile(r"(^|/)(CHANGELOG[^/]*|HISTORY[^/]*|NEWS[^/]*|RELEASES?[^/]*)$|"
                         r"(^|/)(changelogs?|upcoming-release-notes|\.changeset|release-notes|locales?|i18n|"
                         r"translations?|l10n|po)/|(^|/)values-[a-z]{2}(-r?[A-Z]{2})?/|\.(snap|po|pot|min\.js|svg|png|"
                         r"jpe?g|gif|webp|ico|lock)$|(^|/)\.github/workflows/.*\.lock\.yml$", re.I)
ROUTINE = re.compile(r"^(fix|docs?|test|tests|style|ci|typo|lint|chore\(deps|build\(deps|bump)\b", re.I)
BOT = re.compile(r"\[bot\]|dependabot|renovate|github-actions|crowdin|weblate|transifex|semantic-release|"
                 r"allcontributors|pre-commit-ci|mergify", re.I)
DIRECTION = re.compile(
    r"\b(revert(s|ed)?|switch(es|ed)? (to|from|over)|replac(e|es|ed|ing)\b|migrat(e|es|ed|ing|ion)\b|"
    r"rewr(ite|ites|ote|itten)\b|mov(e|es|ed|ing) (to|from|away|off)\b|deprecat|in favou?r of|instead of|"
    r"back to|drop(s|ped)? (support|the|our)|redesign|re-?architect|overhaul|adopt(s|ed)?\b|"
    r"remov(e|es|ed|ing) (the )?(legacy|old)|introduc(e|es|ed|ing) (a |an |the )?new|use [\w.-]+ instead|"
    r"no longer|reintroduc|bring back|undo)", re.I)
HARNESS = re.compile(r"(^|/)(AGENTS|CLAUDE|GEMINI|COPILOT|CONVENTIONS)\.md$|(^|/)\.(agents|claude|codex|cursor|"
                     r"opencode|windsurf|github/copilot-instructions|gemini|aider|continue|roo|clinerules)(/|\.md$)|"
                     r"(^|/)(skills|prompts|agents)/.*\.md$|(^|/)SKILL\.md$|copilot-instructions\.md$|"
                     r"(^|/)\.github/(ISSUE_TEMPLATE|PULL_REQUEST_TEMPLATE|pull_request_template)", re.I)
COMMUNITY = re.compile(r"(^|/)(CODE[_-]OF[_-]CONDUCT|SECURITY|SUPPORT|GOVERNANCE|MAINTAINERS|LICEN[CS]E|COPYING|"
                       r"CLA|FUNDING|AUTHORS|CONTRIBUTORS|NOTICE|TRADEMARKS?)[^/]*$", re.I)
CHANGELOG = re.compile(r"(^|/)(CHANGELOG|HISTORY|NEWS|RELEASES?|UPGRADING|MIGRATING)[^/]*$|(^|/)(changelogs?|"
                       r"upcoming-release-notes|\.changeset|release-notes|releases|blog|posts|_posts)/", re.I)
DECISION = re.compile(r"(^|/)(adrs?|decisions?|architecture[-_]decisions?|decision[-_]records?)(/|$)|"
                      r"(^|/)adr[-_]?\d+[^/]*$", re.I)
RFC = re.compile(r"(^|/)(rfcs?|proposals?|design[-_]docs?|specs?|plans?)/", re.I)
TECH_NAME = re.compile(r"(^|/)(CONTRIBUTING|DEVELOP(MENT|ING)?|HACKING|BUILD(ING)?|INSTALL(ATION|ING)?|ARCHITECTURE|INTERNALS|"
                       r"RELEASING|RELEASE|DEPLOY(MENT|ING)?|TESTING|STYLE|CODE[_-]STYLE|CODE[_-]REVIEW[^/]*|"
                       r"WRITING[_-]STYLE|DESIGN|MANIFEST|SIGNING|PORTING|BENCHMARKS?|PERFORMANCE|DEBUGGING|"
                       r"TROUBLESHOOTING|SYNC(ING)?|UPSTREAM|VENDOR(ING)?|MAINTAIN(ING|ERS?))[^/]*$|(^|/)(contributing|development|developers?|internals|architecture|"
                       r"dev[-_]?docs|reference|api|self-hosting|hosting|deploy(ment)?|operations|ops|infra|docker|playwright|"
                       r"cypress|e2e|tests?|scripts|ci|packaging|helm|k8s|kubernetes|\.devcontainer|dev|"
                       r"benchmarks?|maintainers?)/", re.I)
TECH_HEADINGS = re.compile(r"^(install(ation|ing)?|build(ing)?|dependencies|(binary )?packages|from (release )?(tarball|source|version control)|compil(e|ing)|development|setup|set up|local development|"
                           r"testing|running tests|architecture|internals|api( reference)?|configuration|"
                           r"environment variables|deploy(ment|ing)?|docker|self[- ]host(ing)?|contributing|"
                           r"debugging|release|requirements|prerequisites|options|flags|cli reference)\b", re.I)
# getting the product running (followed step by step, changes with the build) and community sections: stay Markdown
SETUP_HEADING = re.compile(r"^(install(ation|ing)?|(binary )?packages|dependencies|requirements|prerequisites|"
                           r"build(ing)?|from (release )?(tarball|source|version control)|compil(e|ing)|"
                           r"deploy(ment|ing)?|docker|self[- ]host(ing)?|upgrad(e|ing)|"
                           r"contribut(e|ing|ors?)|sponsors?|donat(e|ions?)|backers|support|licen[cs]e|"
                           r"code of conduct|community|credits|acknowledge?ments?)\b", re.I)

DOC_SITES = [
    ("mkdocs", ["mkdocs.yml", "mkdocs.yaml", "docs/mkdocs.yml"]),
    ("docusaurus", ["docusaurus.config.js", "docusaurus.config.ts", "*/docusaurus.config.js",
                    "*/docusaurus.config.ts", "*/*/docusaurus.config.js", "*/*/docusaurus.config.ts"]),
    ("mdbook", ["book.toml", "docs/book.toml", "*/book.toml"]),
    ("vitepress", [".vitepress/config.*", "docs/.vitepress/config.*", "*/*/.vitepress/config.*"]),
    ("sphinx", ["docs/conf.py", "doc/conf.py", "docs/source/conf.py"]),
    ("mintlify", ["mint.json", "docs/mint.json", "docs.json", "docs/docs.json"]),
    ("fumadocs/nextra", ["*/*/source.config.ts", "*/*/theme.config.tsx", "*/source.config.ts"]),
    ("starlight", ["astro.config.mjs", "*/astro.config.mjs", "*/*/astro.config.mjs"]),
    ("gitbook", [".gitbook.yaml", "SUMMARY.md", "docs/SUMMARY.md"]),
    ("jekyll", ["_config.yml", "docs/_config.yml"]),
]

MANIFESTS = {"package.json": "node", "pyproject.toml": "python", "setup.py": "python", "Cargo.toml": "rust",
             "go.mod": "go", "Gemfile": "ruby", "build.gradle": "jvm", "build.gradle.kts": "jvm",
             "settings.gradle.kts": "jvm", "pom.xml": "jvm", "mix.exs": "elixir", "composer.json": "php",
             "Package.swift": "swift", "pubspec.yaml": "dart", "deno.json": "deno", "CMakeLists.txt": "c/c++"}
CODE_EXT = {".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
            ".cjs": "JavaScript", ".py": "Python", ".go": "Go", ".rs": "Rust", ".kt": "Kotlin", ".kts": "Kotlin",
            ".java": "Java", ".rb": "Ruby", ".ex": "Elixir", ".exs": "Elixir", ".php": "PHP", ".swift": "Swift",
            ".dart": "Dart", ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".cs": "C#", ".vue": "Vue",
            ".svelte": "Svelte", ".scala": "Scala", ".clj": "Clojure", ".cljs": "Clojure", ".zig": "Zig"}
AREA_ROOTS = ("packages", "apps", "crates", "libs", "lib", "modules", "services", "plugins", "extensions",
              "feature", "features", "core", "components", "internal", "pkg", "cmd", "app", "src")

E2E_CONFIGS = re.compile(r"(^|/)(playwright\.config\.[cm]?[jt]s|cypress\.config\.[cm]?[jt]s|cypress\.json|"
                         r"wdio\.conf\.[jt]s|detox\.config\.js|\.detoxrc[^/]*|nightwatch\.conf\.[jt]s|"
                         r"testcafe[^/]*\.json|codecept\.conf\.[jt]s|\.maestro/[^/]*\.ya?ml|"
                         r"behat\.yml|cucumber\.[jt]s|features/[^/]*\.feature)$", re.I)
TEST_FILE = re.compile(
    r"(\.(test|spec|e2e|cy|it)\.[cm]?[jt]sx?$)|(__tests__/.*\.[cm]?[jt]sx?$)|((^|/)test_[^/]*\.py$)|(_test\.py$)|"
    r"(_test\.go$)|((^|/)tests?/.*\.rs$)|((^|/)src/(test|androidTest|androidInstrumentedTest|commonTest|jvmTest|"
    r"integrationTest|testDebug|testRelease)/.*\.(kt|java)$)|((Test|Tests|Spec|IT)\.(kt|java|swift|cs|php)$)|"
    r"(_spec\.rb$)|((^|/)test/.*_test\.rb$)|(_test\.exs$)|(\.feature$)|((^|/)(Tests?|UITests?)/.*\.swift$)",
    re.I)
SHELL_TEST = re.compile(r"(^|/)(regress|regressions?|tests?|t)/[^/]+\.sh$|(^|/)test[-_][^/]*\.sh$|_test\.sh$", re.I)
E2E_PATH = re.compile(r"(^|/)(e2e|e2e-tests?|end-to-end|playwright|cypress|acceptance|androidTest|"
                      r"androidInstrumentedTest|ui-?tests?|browser-tests?|system-tests?|smoke|"
                      r"maestro|detox|journeys?)(/|$)|\.(e2e|cy)\.[cm]?[jt]sx?$|\.feature$|UITests?/", re.I)
INTEGRATION_PATH = re.compile(r"(^|/)(integration|integration-tests?|it|api-tests?|functional)(/|$)|"
                              r"\.(it|integration)\.[cm]?[jt]sx?$|(^|/)crates/[^/]+/tests/|(^|/)tests/.*\.rs$", re.I)
VISUAL_PATH = re.compile(r"(^|/)(vrt|visual|screenshots?)(/|$)|visual|\.vrt\.", re.I)

GO_REGISTERED = re.compile(r"^var\s+\w+\s*=\s*New\w*Test\(", re.M)
GO_DESCRIPTION = re.compile(r"^\s*Description:\s*\"((?:[^\"\\]|\\.)+)\"", re.M)
GO_SKIP = re.compile(r"^\s*Skip:\s*true", re.M)
CASE_PATTERNS = {
    "js": re.compile(r"^\s*(?:it|test|scenario)(?:\.(?:only|skip|each\([^)]*\)|concurrent|fixme|fail|slow))*\s*\(\s*"
                     r"([`'\"])(.+?)\1", re.M),
    "py": re.compile(r"^\s*(?:async\s+)?def\s+(test_\w+)", re.M),
    "go": re.compile(r"^func\s+(Test\w+)\s*\(", re.M),
    "rs": re.compile(r"#\[(?:[\w:]+::)?test(?:\([^)]*\))?\]\s*(?:#\[[^\]]*\]\s*)*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)", re.M),
    "kt": re.compile(r"@Test\b[^\n]*\n(?:\s*@[^\n]*\n)*\s*(?:(?:public|internal|private)\s+)?fun\s+(`[^`]+`|\w+)", re.M),
    "java": re.compile(r"@Test\b[^\n]*\n(?:\s*@[^\n]*\n)*\s*(?:public\s+)?void\s+(\w+)", re.M),
    "rb": re.compile(r"^\s*(?:it|scenario|specify)\s+['\"](.+?)['\"]", re.M),
    "ex": re.compile(r"^\s*test\s+\"(.+?)\"", re.M),
    "feature": re.compile(r"^\s*Scenario(?: Outline)?:\s*(.+)$", re.M),
    "swift": re.compile(r"func\s+(test\w+)\s*\(", re.M),
    "php": re.compile(r"function\s+(test\w+)\s*\(", re.M),
}
SUITE_PATTERNS = {
    "js": re.compile(r"^\s*(?:describe|test\.describe|suite|context)(?:\.(?:only|skip|serial|parallel|each\([^)]*\)))*"
                     r"\s*\(\s*([`'\"])(.+?)\1", re.M),
    "rb": re.compile(r"^\s*(?:describe|context|feature)\s+['\"]?(.+?)['\"]?\s+do\b", re.M),
    "feature": re.compile(r"^\s*Feature:\s*(.+)$", re.M),
    "ex": re.compile(r"^\s*describe\s+\"(.+?)\"", re.M),
}


def git(checkout, *args, check=True):
    try:
        # gc.auto=0: reading the history must not start a repack in someone's checkout
        r = subprocess.run(["git", "-C", str(checkout), "-c", "gc.auto=0", *args], capture_output=True, text=True,
                           encoding="utf-8",
                           errors="replace")
    except OSError as e:
        sys.exit(f"git: {e}")
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def read(path, limit=400_000):
    try:
        with open(path, "rb") as f:
            return f.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def lang_of(path):
    p = path.lower()
    if p.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts", ".cts")):
        return "js"
    for ext, lang in ((".py", "py"), (".go", "go"), (".rs", "rs"), (".kt", "kt"), (".kts", "kt"), (".java", "java"),
                      (".rb", "rb"), (".exs", "ex"), (".feature", "feature"), (".swift", "swift"), (".php", "php")):
        if p.endswith(ext):
            return lang
    return None


def frontmatter(text):
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    meta = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip().strip("'\"")
    return meta, text[end + 4:].lstrip("\n")


GENERATED = re.compile(r"do not edit|auto-?generated|generated (by|from|with)|this file is generated", re.I)
USAGE_FENCES = {"sh", "bash", "shell", "console", "zsh", "terminal", "shell-session", "plain", "text", "powershell",
                "ps1", "cmd", "fish"}


def md_facts(path, text):
    meta, body = frontmatter(text)
    generated = bool(GENERATED.search(body[:600]))  # a whole file says so up top
    partly = "[[[cog" in body
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S)  # cog blocks and comments hold no visible headings
    lines = body.splitlines()
    headings, fences, in_fence = [], Counter(), False
    for line in lines:
        m = re.match(r"^\s*(```+|~~~+)\s*([\w+-]*)", line)
        if m:
            if not in_fence:
                fences[m.group(2).lower() or "plain"] += 1
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        h = re.match(r"^(#{1,3})\s+(.+?)\s*#*\s*$", line)
        if h:
            headings.append((len(h.group(1)), h.group(2)))
    words = len(re.findall(r"\w+", re.sub(r"```.*?```", " ", body, flags=re.S)))
    title = meta.get("title") or next((t for lvl, t in headings if lvl == 1), None) or Path(path).stem
    links = re.findall(r"\]\(([^)#\s]+\.mdx?)(?:#[^)]*)?\)", body)
    return {
        "title": title[:120],
        "words": words,
        "headings": [t[:80] for lvl, t in headings
                     if lvl == (2 if any(x == 2 for x, _ in headings) else 1) and t != title][:12],
        "fences": dict(fences),
        "images": len(re.findall(r"!\[[^\]]*\]\(", body)) + body.count("<img"),
        "links_md": len(links),
        "frontmatter": sorted(meta)[:10],
        "generated": generated,
        "partly_generated": partly,
    }


def guess_class(path, facts):
    """A first guess with its reason; the agent confirms or overrides every one in the plan."""
    p = path
    if NOISE_DIRS.search(p) or re.search(r"(^|/)(tests?|spec|__tests__|e2e)/", p, re.I):
        return "fixture", "under a test, fixture or vendored directory"
    if HARNESS.search(p):
        return "harness", "agent or GitHub instructions"
    if COMMUNITY.search(p):
        return "community", "community or legal file"
    if DECISION.search(p):
        return "decision", "decision record directory"
    heads = " ".join(facts["headings"]).lower()
    if re.search(r"\bstatus\b", heads) and re.search(r"\bcontext\b", heads) and re.search(r"\bdecision\b", heads):
        return "decision", "ADR headings (Status, Context, Decision)"
    if CHANGELOG.search(p):
        return "changelog", "changelog, release notes or blog"
    if RFC.search(p):
        return "rfc", "proposal, plan or spec directory"
    if TECH_NAME.search(p):
        return "technical", "contributor, reference or operations file"
    if facts.get("generated"):
        return "generated", "says it is generated; read what generates it"
    tech = sum(1 for h in facts["headings"] if TECH_HEADINGS.match(h))
    # shell sessions are how a command-line product is used, not code about it
    code = sum(v for k, v in facts["fences"].items() if k not in USAGE_FENCES and k != "mermaid")
    if Path(p).name.lower().startswith("readme") and p.count("/") >= 1 and facts["words"] < 400:
        return "technical", "a package or folder README"
    if facts["headings"] and tech / max(1, len(facts["headings"])) > 0.5:
        return "technical", "mostly setup, build or reference headings"
    if facts["words"] and code * 120 > facts["words"] and facts["words"] < 1500:
        return "technical", "code-heavy"
    return "product", "describes what a user can do"


def find_site(files):
    found = []
    for kind, patterns in DOC_SITES:
        for pat in patterns:
            rx = re.compile("^" + re.escape(pat).replace(r"\*", "[^/]+") + "$")
            for f in files:
                if rx.match(f) and not NOISE_DIRS.search(f):
                    found.append({"kind": kind, "config": f})
    seen, out = set(), []
    for s in found:
        if s["config"] not in seen:
            seen.add(s["config"])
            out.append(s)
    return out[:6]


def area_of(path, workspaces):
    for w in workspaces:
        if path == w or path.startswith(w + "/"):
            return w
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] in AREA_ROOTS:
        return "/".join(parts[:2])
    if len(parts) >= 2:
        if parts[0] in ("tests", "test", "spec", "e2e", "__tests__", "src") and len(parts) > 2:
            return f"{parts[0]}/{parts[1]}"
        return parts[0]
    return "(root)"


def workspaces_of(files):
    """Package directories: every folder holding a manifest below the root, under a known area root."""
    out = set()
    for f in files:
        name = f.rsplit("/", 1)[-1]
        if name in MANIFESTS and "/" in f and not NOISE_DIRS.search(f):
            d = f.rsplit("/", 1)[0]
            if d.split("/")[0] in AREA_ROOTS or d.count("/") == 0:
                out.add(d)
    # Only the deepest meaningful level: drop a folder that contains another one.
    return sorted((d for d in out if not any(o != d and o.startswith(d + "/") for o in out)), key=len, reverse=True)


def scan_markdown(checkout, files):
    docs, seen = [], {}
    for f in files:
        if not f.lower().endswith(MD_EXT) or VENDORED.search(f):
            continue
        text = read(checkout / f)
        facts = md_facts(f, text)
        cls, why = guess_class(f, facts)
        digest = hashlib.sha1(text.strip().encode()).hexdigest()
        if digest in seen and facts["words"] > 20:
            # a release copy or mirror of another tree: decide the original, then the copy follows it
            cls, why = "duplicate", f"same text as {seen[digest]}"
        seen.setdefault(digest, f)
        entry = {"path": f, "bytes": len(text.encode()), **facts, "guess": cls, "why": why}
        setup = [h for h in facts["headings"] if SETUP_HEADING.match(h)]
        if setup and cls == "product":
            entry["keep_sections"] = setup
        docs.append(entry)
    return docs


def md_history(checkout, paths, max_commits):
    """Commits and authors per Markdown path, from one log walk."""
    if not paths:
        return {}
    wanted = set(paths)
    out = git(checkout, "log", f"-n{max_commits}", "--no-merges", "--format=\x1e%an\x1f%aI", "--name-only",
              "--", "*.md", "*.mdx", "*.markdown", check=False)
    stats = defaultdict(lambda: {"commits": 0, "authors": set(), "last": None, "first": None})
    for chunk in out.split("\x1e")[1:]:
        head, _, names = chunk.partition("\n")
        author, _, date = head.partition("\x1f")
        for name in filter(None, (n.strip() for n in names.splitlines())):
            if name in wanted:
                s = stats[name]
                s["commits"] += 1
                s["authors"].add(author)
                s["last"] = s["last"] or date[:10]
                s["first"] = date[:10]
    return {k: {"commits": v["commits"], "authors": len(v["authors"]), "last": v["last"], "first": v["first"]}
            for k, v in stats.items()}


def milestones(checkout, limit=40):
    """The largest changes on the main line over the whole history, merges of big pull requests included: a
    feature landing ("add organisations") changes many files and names no direction verb."""
    out = git(checkout, "log", "--first-parent", "--diff-merges=first-parent", "--no-renames", "-n100000",
              "--format=\x1e%H\x1f%an\x1f%aI\x1f%s", "--name-only", check=False)
    found = []
    for chunk in out.split("\x1e")[1:]:
        head, _, names = chunk.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 4 or BOT.search(parts[1]) or BOT.search(parts[3][:40]) or ROUTINE.match(parts[3]):
            continue
        files = [n for n in (x.strip() for x in names.splitlines()) if n and not LOCKFILES.search(n)
                 and not CHURN_NOISE.search(n) and not NOISE_DIRS.search(n)]
        if 15 <= len(files) <= 3000:
            found.append({"sha": parts[0][:10], "date": parts[2][:10], "author": parts[1],
                          "subject": parts[3].strip()[:140], "files": len(files),
                          "direction": bool(DIRECTION.search(parts[3])),
                          "areas": [a for a, _ in Counter(f.split("/")[0] for f in files).most_common(3)]})
    return sorted(found, key=lambda c: -c["files"])[:limit]


def churn(checkout, max_commits, workspaces, remote):
    out = git(checkout, "log", f"-n{max_commits}", "--no-merges", "--format=\x1e%H\x1f%an\x1f%aI\x1f%s",
              "--name-only", check=False)
    commits = []
    for chunk in out.split("\x1e")[1:]:
        head, _, names = chunk.partition("\n")
        parts = head.split("\x1f")
        if len(parts) < 4:
            continue
        sha, author, date, subject = parts[0], parts[1], parts[2], "\x1f".join(parts[3:])
        files = [n.strip() for n in names.splitlines() if n.strip()]
        commits.append({"sha": sha, "author": author, "date": date[:10], "subject": subject.strip(), "files": files})
    human = [c for c in commits if not BOT.search(c["author"]) and not BOT.search(c["subject"][:40])]
    per_file = defaultdict(lambda: {"commits": 0, "authors": set(), "direction": [], "reverts": 0, "last": None})
    per_area = defaultdict(lambda: {"commits": 0, "authors": set(), "direction": [], "reverts": 0, "files": set()})
    for c in human:
        files = [f for f in c["files"] if not LOCKFILES.search(f) and not CHURN_NOISE.search(f)]
        if not files or len(c["files"]) > 200:  # mass renames and formatting sweeps say nothing about one file
            continue
        is_dir = bool(DIRECTION.search(c["subject"])) and not ROUTINE.match(c["subject"])
        is_revert = c["subject"].lower().startswith("revert")
        ref = {"sha": c["sha"][:10], "date": c["date"], "author": c["author"], "subject": c["subject"][:140]}
        areas = set()
        for f in files:
            s = per_file[f]
            s["commits"] += 1
            s["authors"].add(c["author"])
            s["last"] = s["last"] or c["date"]
            s["reverts"] += is_revert
            if is_dir and len(s["direction"]) < 8:
                s["direction"].append(ref)
            areas.add(area_of(f, workspaces))
        for a in areas:
            s = per_area[a]
            s["commits"] += 1
            s["authors"].add(c["author"])
            s["reverts"] += is_revert
            s["files"].update(f for f in files if area_of(f, workspaces) == a)
            if is_dir and len(s["direction"]) < 12:
                s["direction"].append(ref)
    hot_files = sorted(per_file.items(), key=lambda kv: (-kv[1]["commits"], kv[0]))[:40]
    hot_areas = sorted(per_area.items(), key=lambda kv: (-kv[1]["commits"], kv[0]))[:25]
    # Configuration and manifests that changed direction: dependency swaps, build and CI rework.
    config = re.compile(r"(^|/)(" + "|".join(re.escape(m) for m in MANIFESTS) +
                        r"|\.github/workflows/[^/]+|Dockerfile[^/]*|docker-compose[^/]*|[^/]*\.config\.[cm]?[jt]s|"
                        r"tsconfig[^/]*\.json|Makefile|Justfile|Taskfile\.ya?ml|turbo\.json|nx\.json|mise\.toml)$")
    swaps = [{"sha": c["sha"][:10], "date": c["date"], "author": c["author"], "subject": c["subject"][:140],
              "files": [f for f in c["files"] if config.search(f)][:5]}
             for c in human if DIRECTION.search(c["subject"]) and not ROUTINE.match(c["subject"]) and any(config.search(f) for f in c["files"])][:40]
    base = f"https://github.com/{remote}/commit/" if remote else None
    return {
        "commits_read": len(commits),
        "human_commits": len(human),
        "first": commits[-1]["date"] if commits else None,
        "last": commits[0]["date"] if commits else None,
        "commit_url": base,
        "hot_files": [{"path": k, "commits": v["commits"], "authors": len(v["authors"]), "reverts": v["reverts"],
                       "last": v["last"], "direction": v["direction"]} for k, v in hot_files],
        "hot_areas": [{"area": k, "commits": v["commits"], "authors": len(v["authors"]), "reverts": v["reverts"],
                       "files": len(v["files"]), "direction": v["direction"]} for k, v in hot_areas],
        "config_changes": swaps,
    }


# Drivers that run the built command whatever it is called, and generic process calls that count only when the
# line names the product (so `createdb` in a fixture is not a CLI journey).
CLI_STRONG = re.compile(r"\b(assert_cmd|cargo_bin|get_bin\(|CliRunner\b|\w+_snapshot!|testscript\.)")
CLI_WEAK = re.compile(r"(exec\.Command\(|subprocess\.(run|check_output|call|Popen)\(|execa\(|spawnSync\(|"
                      r"spawn\(|Open3\.|System\.cmd\(|Command::new\()([^\n]*)")
SKIPPED = re.compile(r"\b(?:it|test|describe|scenario)\.(?:skip|fixme|todo)\s*\(|\bx(?:it|describe)\s*\(|"
                     r"@pytest\.mark\.(?:skip|xfail)|#\[ignore\]|@Ignore\b|@Disabled\b|\bt\.Skip\(", re.M)


def test_kind(path, text, cases=0, products=()):
    """The test's scope from its path and what it drives. A guess: the plan can override it per topic."""
    browser = re.search(r"\bpage\.(goto|getBy\w+|locator|click|fill)\(|cy\.visit\(|browser\.url\(|"
                        r"\bdevice\.|onView\(|composeTestRule|XCUIApplication\(|"
                        r"\.\s*(Press(Key|Enter|Escape|Tab)?|SendKeys?)\(", text)
    api_only = re.search(r"from ['\"]@playwright/test['\"]", text) and not browser and "request." in text
    if VISUAL_PATH.search(path) and E2E_PATH.search(path):
        return "e2e-visual"
    if api_only:
        return "e2e-api"
    if E2E_PATH.search(path) or browser:
        return "e2e"
    drives = len(CLI_STRONG.findall(text))
    if products:
        names = re.compile(r"[\"'/\s(\[](" + "|".join(re.escape(p) for p in products) + r")[\"'\s,)\]]")
        drives += sum(1 for m in CLI_WEAK.finditer(text) if names.search(m.group(0)))
    if drives and drives >= max(1, cases // 4):
        return "cli"  # drives the built command end to end: a CLI's e2e layer
    if INTEGRATION_PATH.search(path):
        return "integration"
    return "unit"


GENERIC_DIRS = re.compile(r"(java|kotlin|scala|swift|src|main|test|tests|com|org|net|io|de|app|lib|internal|"
                          r"unit|integration|it|e2e|specs?|__tests__|androidTest|commonTest|jvmTest|flows?|scenarios|cases)", re.I)


def topic_of(path, prefix=""):
    """What a test is about: the first meaningful folder below an e2e or tests folder, else the file name without
    test affixes. `prefix` names the package in a monorepo, so two apps' `auth` tests stay apart."""
    parts = path.split("/")
    topic = None
    jvm = re.search(r"(?:^|/)src/[^/]*[Tt]est[^/]*/(?:java|kotlin|scala)/", path)
    if jvm:
        # A JVM test sits below its package (com/fsck/k9/...); the module folder names what it is about.
        module = path[:jvm.start()].split("/")
        named = [m for m in module if m and not MODULE_GENERIC.fullmatch(m)]
        return (named or module or [None])[-1]  # the module is the package already: no prefix
    for i, part in enumerate(parts[:-1] if topic is None else []):
        if re.fullmatch(r"e2e|e2e-tests?|end-to-end|playwright|cypress|acceptance|tests?|it|integration|spec|"
                        r"__tests__|androidTest|androidInstrumentedTest|ui-?tests?", part, re.I):
            rest = [p for p in parts[i + 1:-1] if not GENERIC_DIRS.fullmatch(p)]
            if rest:
                topic = rest[0]
                break
    if topic is None:
        stem = parts[-1].split(".")[0]
        topic = re.sub(r"(^test_|_test$|_spec$|Tests?$|Spec$|IT$)", "", stem) or stem
    return f"{prefix}/{topic}" if prefix else topic


MODULE_GENERIC = re.compile(r"impl|api|internal|common|core|legacy|library|feature|app|shared|domain|data|ui",
                            re.I)

JOURNEY_KINDS = ("e2e", "e2e-visual", "e2e-api", "cli")


def scan_tests(checkout, files, workspaces, products=()):
    multi = len(workspaces) > 1
    # A package that only holds tests (app-tests, e2e) names no product area of its own.
    def prefix(area):
        named = [x for x in area.split("/") if not MODULE_GENERIC.fullmatch(x) and x not in AREA_ROOTS]
        if not multi or area not in workspaces or not named or re.search(r"test|e2e|spec", named[-1], re.I):
            return ""
        return named[-1]
    tests, configs = [], [f for f in files if E2E_CONFIGS.search(f) and not NOISE_DIRS.search(f)]
    code_lines = Counter()
    test_lines = Counter()
    languages = Counter()
    for f in files:
        if VENDORED.search(f):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in (".yml", ".yaml") and E2E_PATH.search(f):
            flow = read(checkout / f, 200_000)
            if re.search(r"^appId:", flow, re.M) and re.search(r"^- (launchApp|tapOn|inputText|assertVisible)", flow,
                                                              re.M):
                # A Maestro flow: one journey on a device, named by its file
                name = re.search(r"^name:\s*(.+)$", flow, re.M)
                tests.append({"path": f, "area": area_of(f, workspaces), "topic": topic_of(f), "kind": "e2e",
                              "cases": 1, "skipped": 0, "lines": flow.count("\n"), "suites": [],
                              "titles": [(name.group(1) if name else Path(f).stem.replace("_", " "))[:120]]})
                test_lines[area_of(f, workspaces)] += flow.count("\n")
                continue
        if ext == ".sh" and SHELL_TEST.search(f):
            # a regression script that runs the built program, as C and Unix projects test: one journey per script
            script = read(checkout / f, 400_000)
            stem = re.sub(r"(^test[-_]|[-_]test$)", "", Path(f).stem)
            tests.append({"path": f, "area": area_of(f, workspaces), "topic": re.split(r"[-_]", stem)[0] or stem,
                          "kind": "cli", "cases": 1, "skipped": 0, "lines": script.count("\n"), "suites": [],
                          "titles": [stem.replace("-", " ").replace("_", " ")[:120]]})
            test_lines[area_of(f, workspaces)] += script.count("\n")
            continue
        is_test = bool(TEST_FILE.search(f)) and not re.search(r"(^|/)(fixtures?|testdata|__snapshots__|"
                                                            r"node_modules|vendor)/", f, re.I)
        if ext not in CODE_EXT and not f.endswith(".feature"):
            continue
        if NOISE_DIRS.search(f) and not is_test:
            continue
        text = read(checkout / f, 8_000_000 if is_test else 400_000)
        n = text.count("\n")
        area = area_of(f, workspaces)
        if not is_test and ext == ".rs" and "#[cfg(test)]" in text:
            # Rust keeps unit tests next to the code: count them, but the file is code.
            cases = CASE_PATTERNS["rs"].findall(text)
            if cases:
                tests.append({"path": f, "area": area, "topic": topic_of(f, prefix(area)), "kind": "unit",
                              "cases": len(cases), "skipped": len(SKIPPED.findall(text)), "lines": 0,
                              "suites": [], "titles": []})
        if not is_test and ext == ".go" and GO_REGISTERED.search(text):
            # tests declared as data and run by a harness (`var X = NewIntegrationTest(...)`): one case each
            titles = GO_DESCRIPTION.findall(text) or [Path(f).stem.replace("_", " ")]
            tests.append({"path": f, "area": area, "topic": topic_of(f, prefix(area)),
                          "kind": test_kind(f, text, len(GO_REGISTERED.findall(text)), products),
                          "cases": len(GO_REGISTERED.findall(text)), "skipped": len(GO_SKIP.findall(text)),
                          "lines": n, "suites": [], "titles": [t[:120] for t in titles[:30]]})
            test_lines[area] += n
            continue
        if not is_test:
            code_lines[area] += n
            languages[CODE_EXT.get(ext, "other")] += n
            continue
        lang = lang_of(f)
        test_lines[area] += n
        if lang is None:
            continue
        cases = CASE_PATTERNS[lang].findall(text)
        titles = [c[1] if isinstance(c, tuple) else c for c in cases]
        suite_rx = SUITE_PATTERNS.get(lang)
        suites = [s[1] if isinstance(s, tuple) and len(s) > 1 else s for s in suite_rx.findall(text)] if suite_rx else []
        kind = test_kind(f, text, len(titles), products)
        tests.append({"path": f, "area": area, "topic": topic_of(f, prefix(area)), "kind": kind, "cases": len(titles),
                      "skipped": len(SKIPPED.findall(text)), "lines": n,
                      "suites": [s[:100] for s in suites[:12]],
                      "titles": [t[:120] for t in titles[:30]] if kind in JOURNEY_KINDS else []})
    by_kind = Counter()
    by_area = defaultdict(lambda: Counter())
    by_topic = defaultdict(lambda: Counter())
    for t in tests:
        by_kind[t["kind"]] += t["cases"]
        by_area[t["area"]][t["kind"]] += t["cases"]
        by_topic[t["topic"]][t["kind"]] += t["cases"]
    topics = sorted(({"topic": k, "cases": sum(v.values()), **v} for k, v in by_topic.items()),
                    key=lambda x: (-sum(x.get(k, 0) for k in JOURNEY_KINDS), -x["cases"]))
    areas = []
    for a in sorted(set(by_area) | set(code_lines), key=lambda a: -(sum(by_area[a].values()) + code_lines[a] / 1000)):
        total = sum(by_area[a].values())
        areas.append({"area": a, "cases": total, **{k: v for k, v in by_area[a].items()},
                      "code_lines": code_lines[a], "test_lines": test_lines[a],
                      "test_ratio": round(test_lines[a] / code_lines[a], 2) if code_lines[a] else None})
    total_cases = sum(by_kind.values())
    for a in areas:
        a["share"] = round(a["cases"] / total_cases, 3) if total_cases else 0
    return {
        "method": "static: test declarations matched by pattern per language, not a runner's count; parameterised "
                  "and generated tests count once, skipped ones are included and counted in `skipped`; a shell "
                  "regression script counts as one case and skips inside it are not seen; Rust tests inside source "
                  "files count as cases but their lines stay code",
        "frameworks": configs[:12],
        "cases": dict(by_kind),
        "skipped": sum(t.get("skipped", 0) for t in tests),
        "total_cases": total_cases,
        "files": len({t["path"] for t in tests}),
        "areas": [a for a in areas if a["cases"] or a["code_lines"] > 200][:40],
        "topics": topics[:60],
        "e2e": journeys(tests),
        "languages": dict(languages.most_common(8)),
    }


def journeys(tests, detailed=150):
    """Every journey file, most cases first, then longest; past the first `detailed` only path and counts."""
    out = sorted((t for t in tests if t["kind"] in JOURNEY_KINDS), key=lambda t: (-t["cases"], -t["lines"], t["path"]))
    return out[:detailed] + [{**t, "suites": [], "titles": []} for t in out[detailed:]]


def brief(text):
    """A write's answer without the echoed content: its ids, revision and delivery state."""
    try:
        answer = json.loads(text)
    except ValueError:
        return text[:300]
    if not isinstance(answer, dict):
        return text[:300]
    keep = {k: v for k, v in answer.items() if k in ("uuid", "rev", "revision", "applied", "synced", "durable")}
    if isinstance(answer.get("block"), dict):
        keep["block"] = answer["block"].get("id")
    if isinstance(answer.get("blocks"), list):
        keep["blocks"] = len(answer["blocks"])
    if isinstance(answer.get("hub"), dict):
        keep["hub"] = answer["hub"].get("status")
    return keep


def remote_of(checkout):
    url = git(checkout, "remote", "get-url", "origin", check=False).strip()
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(\.git)?$", url)
    return m.group(1) if m else None


def cmd_scan(args):
    checkout = Path(args.checkout).resolve()
    if not (checkout / ".git").exists() and not git(checkout, "rev-parse", "--git-dir", check=False).strip():
        sys.exit(f"{checkout}: not a git checkout")
    files = [f for f in git(checkout, "ls-files", "-z").split("\0") if f]
    workspaces = workspaces_of(files)
    remote = remote_of(checkout)
    md = scan_markdown(checkout, files)
    hist = md_history(checkout, [d["path"] for d in md], args.max_commits)
    for d in md:
        d.update(hist.get(d["path"], {"commits": 0, "authors": 0, "last": None, "first": None}))
    dirs = defaultdict(Counter)
    for d in md:
        dirs[d["path"].rsplit("/", 1)[0] if "/" in d["path"] else "."][d["guess"]] += 1
    manifests = sorted({MANIFESTS[f.rsplit("/", 1)[-1]] for f in files
                        if f.rsplit("/", 1)[-1] in MANIFESTS and not NOISE_DIRS.search(f)})
    dirty = [line[3:] for line in git(checkout, "status", "--porcelain", "--untracked-files=no").splitlines()]
    if dirty:
        print(f"scan: {len(dirty)} tracked file(s) differ from HEAD; the scan reads them as they are on disk, "
              "so commit or stash first to tie every source to the commit", file=sys.stderr)
    products = products_of(checkout, files, remote)
    scan = {
        "schema_version": SCHEMA_VERSION,
        "repository": remote,
        "checkout": str(checkout),
        "ref": git(checkout, "rev-parse", "--short", "HEAD").strip(),
        "commit": git(checkout, "rev-parse", "HEAD").strip(),
        "dirty": dirty[:50],
        "products": products,
        "date": dt.date.today().isoformat(),
        "files": len(files),
        "stacks": manifests,
        "workspaces": sorted(workspaces),
        "doc_sites": find_site(files),
        "markdown": md,
        "markdown_dirs": [{"dir": k, "files": sum(v.values()), "guesses": dict(v)}
                          for k, v in sorted(dirs.items(), key=lambda kv: -sum(kv[1].values()))][:40],
        "markdown_classes": dict(Counter(d["guess"] for d in md)),
        "churn": {**churn(checkout, args.max_commits, workspaces, remote), "milestones": milestones(checkout)},
        "tests": scan_tests(checkout, files, workspaces, products),
        "labels": labels_of(checkout, files, remote),
    }
    json.dump(scan, sys.stdout, indent=1, ensure_ascii=False)
    print()


def products_of(checkout, files, remote):
    """The names a user types to run the product: the repository's name and every declared command."""
    names = set()
    if remote:
        names.add(remote.split("/")[-1].lower())
    for f in files:
        name = f.rsplit("/", 1)[-1]
        if NOISE_DIRS.search(f) or name not in ("package.json", "pyproject.toml", "Cargo.toml", "go.mod", "setup.py"):
            continue
        if re.search(r"(^|/)(tests?|scripts|examples?|docs?|benchmarks?|ecosystem|samples?|playground)/", f):
            continue
        text = read(checkout / f, 60_000)
        if name == "package.json":
            try:
                data = json.loads(text)
            except ValueError:
                continue
            b = data.get("bin")
            names.update(b.keys() if isinstance(b, dict) else [data.get("name", "").split("/")[-1]] if b else [])
        elif name == "pyproject.toml":
            m = re.search(r"^\[project\.scripts\]\n((?:[^\[\n][^\n]*\n?)*)", text, re.M)
            if m:
                names.update(re.findall(r"^\s*([\w.-]+)\s*=", m.group(1), re.M))
        elif name == "Cargo.toml":
            for block in re.findall(r"^\[\[bin\]\]\n((?:[^\[\n][^\n]*\n?)*)", text, re.M):
                names.update(re.findall(r'^\s*name\s*=\s*"([^"]+)"', block, re.M))
        elif name == "go.mod":
            m = re.search(r"^module\s+(\S+)", text, re.M)
            if m:
                names.add(re.sub(r"/v\d+$", "", m.group(1)).split("/")[-1])
        elif name == "setup.py":
            names.update(re.findall(r"['\"]([\w-]+)\s*=\s*[\w.]+:\w+['\"]", text))
    return sorted(n for n in names if n and len(n) > 1)[:20]


def labels_of(checkout, files, remote):
    """Vocabulary for tags: GitHub labels when gh can read them, and area names from the layout."""
    labels = []
    if remote:
        try:
            r = subprocess.run(["gh", "label", "list", "--repo", remote, "--limit", "200", "--json",
                                "name,description"], capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                labels = [l["name"] for l in json.loads(r.stdout)]
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return {"github": labels[:120]}


# --------------------------------------------------------------------------------------------------- readable views

def load_scan(path):
    scan = load(path)
    if scan.get("schema_version") != SCHEMA_VERSION:
        sys.exit(f"{path} was written by another version of intake.py; run `intake.py scan` again")
    return scan


def local_workspace(checkout):
    """True when the checkout is bound to a local-only workspace, whose catalog is whole although it reads
    `complete: false` while no hub runs."""
    try:
        return json.loads((Path(checkout) / ".uberblick.json").read_text(encoding="utf-8")).get("hubUrl") is None
    except (OSError, ValueError):
        return False


def cmd_hot(args):
    scan = load_scan(args.scan)
    c = scan["churn"]
    print(f"{scan['repository']} @ {scan['ref']}: {c['human_commits']} human commits of {c['commits_read']} non-merge commits read, "
          f"{c['first']} to {c['last']}")
    print("\nHot areas (commits, authors, reverts):")
    for a in c["hot_areas"][:args.limit]:
        print(f"  {a['area']}: {a['commits']} commits, {a['authors']} authors, {a['reverts']} reverts, "
              f"{a['files']} files")
        for d in a["direction"][:4]:
            print(f"      {d['date']} {d['sha']} {d['subject']}")
    print("\nHot files:")
    for f in c["hot_files"][:args.limit]:
        flag = f", {f['reverts']} reverts" if f["reverts"] else ""
        print(f"  {f['path']}: {f['commits']} commits, {f['authors']} authors{flag}")
        for d in f["direction"][:3]:
            print(f"      {d['date']} {d['sha']} {d['subject']}")
    print("\nDirection changes in configuration and manifests:")
    for s in c["config_changes"][:args.limit]:
        print(f"  {s['date']} {s['sha']} {s['subject']}  [{', '.join(s['files'])}]")
    print("\nLargest changes on the main line, whole history (features landing, rewrites, migrations):")
    for m in c.get("milestones", [])[:args.limit * 2]:
        print(f"  {m['date']} {m['sha']} {m['files']} files{' (direction)' if m['direction'] else ''}: "
              f"{m['subject']}  [{', '.join(m['areas'])}]")


KINDS = ("e2e", "e2e-visual", "e2e-api", "cli", "integration", "unit")


def cmd_tests(args):
    scan = load_scan(args.scan)
    t = scan["tests"]
    print(f"{t['total_cases']} test declarations (a static count) in {t['files']} files, {t.get('skipped', 0)} "
          f"marked skipped: " +
          ", ".join(f"{k} {v}" for k, v in sorted(t["cases"].items(), key=lambda kv: -kv[1])))
    print("Browser or device test configuration: " + (", ".join(t["frameworks"]) or "none found") +
          (f"; {t['cases'].get('cli', 0)} cases run the built command" if t["cases"].get("cli") else ""))
    print("\nArea, cases (share), by kind, test lines per code line:")
    for a in t["areas"][:30]:
        kinds = ", ".join(f"{k} {a[k]}" for k in KINDS if a.get(k))
        ratio = "" if a["test_ratio"] is None else f", ratio {a['test_ratio']}"
        print(f"  {a['area']}: {a['cases']} ({a['share']:.0%}){': ' + kinds if kinds else ''}; "
              f"{a['code_lines']} code lines{ratio}")
    print("\nTopics, journeys first (e2e, e2e-visual and cli cases count as journeys):")
    for x in t.get("topics", [])[:args.topics]:
        print(f"  {x['topic']}: {x['cases']} (" + ", ".join(f"{k} {x[k]}" for k in KINDS if x.get(k)) + ")")
    print(f"\nJourneys ({len(t['e2e'])} files, most cases first, then longest; suites, then test titles):")
    shown = printed = 0
    for e in t["e2e"]:
        if shown >= args.titles:
            break
        print(f"  {e['path']} ({e['cases']}, {e['kind']}): " + " | ".join(e["suites"][:3]))
        for title in e["titles"][:args.per_file]:
            print(f"      - {title}")
            shown += 1
        printed += 1
    if t["e2e"][printed:]:
        print("\nMore journey files (scan.json keeps titles for the first 150 under tests.e2e; open the rest):")
        for e in t["e2e"][printed:]:
            print(f"  {e['path']} ({e['cases']}, {e['kind']})")


# --------------------------------------------------------------------------------------------------- Markdown -> blocks

INLINE = re.compile(
    r"(?P<code>`+)(?P<codetext>.+?)(?P=code)"
    r"|\[(?P<label>(?:[^\[\]]|\[[^\]]*\])+)\]\((?P<href>[^)\s]+)\)"
    r"|(?P<b>\*\*|__)(?P<btext>.+?)(?P=b)"
    r"|(?P<s>~~)(?P<stext>.+?)~~"
    r"|(?<![\w*])(?P<i>[*_])(?P<itext>[^*_\s](?:.*?[^*_\s])?)(?P=i)(?![\w*])")
DELIMITER_ROW = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def runs(text, marks=None, refs=None):
    """Inline Markdown to Uberblick inline runs. `ref:slug` hrefs become {"$doc": slug} placeholders."""
    marks = marks or {}
    out, pos = [], 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            out.append({"text": text[pos:m.start()], "marks": dict(marks)})
        if m.group("code"):
            out.append({"text": m.group("codetext"), "marks": {**marks, "inlineCode": True}})
        elif m.group("label") is not None:
            href = m.group("href")
            if href.startswith("ref:"):
                if refs is not None:
                    refs.add(href[4:])
                out.extend(runs(m.group("label"), {**marks, "docLink": {"$doc": href[4:]}}, refs))
            elif UUID.match(href):
                out.extend(runs(m.group("label"), {**marks, "docLink": href}, refs))
            elif re.match(r"^https?://", href):
                out.extend(runs(m.group("label"), {**marks, "link": href}, refs))
            else:
                raise ValueError(f"link target {href!r} is neither https, ref:slug nor a document UUID")
        elif m.group("b"):
            out.extend(runs(m.group("btext"), {**marks, "bold": True}, refs))
        elif m.group("s"):
            out.extend(runs(m.group("stext"), {**marks, "strike": True}, refs))
        elif m.group("i"):
            out.extend(runs(m.group("itext"), {**marks, "italic": True}, refs))
        pos = m.end()
    if pos < len(text):
        out.append({"text": text[pos:], "marks": dict(marks)})
    merged = []
    for r in out:
        if merged and merged[-1]["marks"] == r["marks"]:
            merged[-1]["text"] += r["text"]
        elif r["text"]:
            merged.append(r)
    return merged


def prose(type_, text, refs, **extra):
    inline = runs(text, refs=refs)
    block = {"type": type_, "text": "".join(r["text"] for r in inline), **extra}
    if any(r["marks"] for r in inline):
        block["inline"] = inline
    return block


def parse_doc(text):
    """Uberblick Markdown (frontmatter, then blocks) to create_doc arguments, with `ref:` targets collected."""
    if not text.startswith("---\n"):
        raise ValueError("no frontmatter: every document starts with --- title, description, tags ---")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError("frontmatter is not closed with ---")
    meta = {}
    key = None
    for line in text[4:end].splitlines():
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m:
            key, value = m.group(1), m.group(2).strip()
            if value.startswith("[") and value.endswith("]"):
                meta[key] = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
            elif value in (">-", ">", "|"):
                meta[key] = ""
            else:
                meta[key] = value.strip("'\"")
        elif key and line.startswith("  - "):
            meta.setdefault(key, [])
            if not isinstance(meta[key], list):
                meta[key] = []
            meta[key].append(line[4:].strip().strip("'\""))
        elif key and line.startswith("  "):
            meta[key] = (meta.get(key) or "") + (" " if meta.get(key) else "") + line.strip()
    lines = text[end + 5:].splitlines()
    blocks, refs, i = [], set(), 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        fence = re.match(r"^(```+|~~~+)\s*([\w+-]*)\s*$", line)
        if fence:
            j = i + 1
            while j < len(lines) and not lines[j].startswith(fence.group(1)):
                j += 1
            if j >= len(lines):
                raise ValueError(f"line {i + 1}: unclosed code fence")
            lang = fence.group(2).lower()
            if lang == "mermaid":
                raise ValueError(f"line {i + 1}: Uberblick deletes mermaid blocks; draw it as ablauf")
            block = {"type": "code", "text": "\n".join(lines[i + 1:j])}
            if lang in ("terminal", "chart"):
                block["type"] = lang
            elif lang:
                block["language"] = lang
            blocks.append(block)
            i = j + 1
            continue
        if line.strip() in (":::card", ":::figma"):
            kind = line.strip()[3:]
            j = i + 1
            while j < len(lines) and lines[j].strip() != ":::":
                j += 1
            if j >= len(lines):
                raise ValueError(f"line {i + 1}: unclosed :::{kind}")
            blocks.append({"type": kind, "text": "\n".join(lines[i + 1:j])})
            refs.update(re.findall(r"\]\(ref:([a-z0-9-]+)\)", blocks[-1]["text"]))
            i = j + 1
            continue
        if line.startswith(":::"):
            raise ValueError(f"line {i + 1}: {line.strip()} is no Uberblick container; use :::card or :::figma")
        if line.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            blocks.append({"type": "table", "text": "\n".join(lines[i:j])})
            for row in lines[i:j]:
                for href in re.findall(r"\]\((ref:[^)\s]+)\)", row):
                    refs.add(href[4:])
            i = j
            continue
        h = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if h:
            blocks.append(prose("heading", h.group(2), refs, level=len(h.group(1))))
            i += 1
            continue
        li = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", line)
        if li:
            indent = min(3, len(li.group(1).replace("\t", "  ")) // 2)
            extra = {"indent": indent} if indent else {}
            if li.group(2)[0].isdigit():
                extra["list"] = "ordered"
            item = li.group(3)
            task = re.match(r"^\[( |x|X)\]\s+(.*)$", item)
            if task:
                item = ("☑ " if task.group(1).strip() else "☐ ") + task.group(2)
            blocks.append(prose("list-item", item, refs, **extra))
            i += 1
            continue
        if line.startswith(">"):
            j = i
            parts = []
            while j < len(lines) and lines[j].startswith(">"):
                parts.append(lines[j][1:].strip())
                j += 1
            blocks.append(prose("quote", " ".join(p for p in parts if p), refs))
            i = j
            continue
        j = i
        parts = []
        while j < len(lines) and lines[j].strip() and not re.match(r"^(#{1,6}\s|```|~~~|>|\s*([-*+]|\d+[.)])\s|\||:::)",
                                                                   lines[j]):
            parts.append(lines[j].strip())
            j += 1
        blocks.append(prose("paragraph", " ".join(parts), refs))
        i = j
    return meta, blocks, refs


def cmd_blocks(args):
    try:
        meta, blocks, refs = parse_doc(Path(args.doc).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"{args.doc}: {e}")
    json.dump({"meta": meta, "blocks": blocks, "refs": sorted(refs)}, sys.stdout, indent=1, ensure_ascii=False)
    print()


def load(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"{path}: {e}")


# --------------------------------------------------------------------------------------------------- the plan

MAX_DESCRIPTION = 300
MAX_TLDR = 300
HISTORY = re.compile(r"\b(planned|will (be|soon|eventually)|coming soon|roadmap|todo|tbd|not yet|"
                     r"since (v?\d|version|release|the (v?\d|version|release|last|first))|as of (v?\d|version|20\d\d)|in v\d+(\.\d+)*|deprecated in|"
                     r"(added|introduced|removed|changed) in (v?\d|version)|"
                     r"20\d\d-\d\d-\d\d|github\.com/[^\s)]+/(pull|issues)/\d+|(^|\s)#\d{2,}\b)", re.I)
DECISION_TYPES = ("paragraph", "code", "table", "list-item")


def plan_paths(plan, base):
    """The documents with their parsed files: (doc, meta, blocks, refs) or an error string."""
    out = []
    for d in plan.get("documents", []):
        path = (base / d.get("file", "")).resolve()
        try:
            meta, blocks, refs = parse_doc(path.read_text(encoding="utf-8"))
            out.append((d, meta, blocks, refs, None))
        except FileNotFoundError:
            out.append((d, {}, [], set(), f"{d.get('file')}: not found next to the plan ({base}); `file` is "
                                          f"relative to intake.json, as in docs/<slug>.md"))
        except (OSError, ValueError) as e:
            out.append((d, {}, [], set(), f"{d.get('file')}: {e}"))
    return out


def covers(pattern, path):
    """`**` spans folders, `*` and `?` stay within one."""
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/")
    if not any(ch in pattern for ch in "*?"):
        return path == pattern
    rx = ""
    for part in re.split(r"(\*\*/?|\*|\?)", pattern):
        rx += {"**/": "(?:.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}.get(part, re.escape(part))
    return re.fullmatch(rx, path) is not None


def entry_for(entries, path):
    """The entry that decides a file: an exact path, else the most specific (longest) pattern."""
    hits = [m for m in entries if covers(m.get("path", ""), path)]
    exact = [m for m in hits if m.get("path") == path]
    return (exact or sorted(hits, key=lambda m: -len(m.get("path", ""))) or [None])[0]


def words(blocks):
    return sum(len(re.findall(r"\w+", b.get("text", ""))) for b in blocks if b["type"] not in ("code",))


def validate(plan, base, scan=None, checkout=None, catalog=None):
    """Errors stop the writes; warnings are for the agent to fix or justify."""
    errors, warnings = [], []
    for key in ("repository", "ref", "summary", "documents", "markdown", "sidebar", "tags"):
        if key not in plan:
            errors.append(f"plan: missing `{key}`")
    if errors:
        return errors, warnings
    tags = {t["name"].lower(): t for t in plan["tags"]}
    for t in plan["tags"]:
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", t["name"]) or len(t["name"]) > 30:
            errors.append(f"tags: {t['name']!r}: a tag is lowercase letters and digits joined by hyphens, "
                          f"at most 30 characters")
    if not 2 <= len(tags) <= 12:
        warnings.append(f"tags: {len(tags)} tags; 2 to 12 keep the catalog useful")
    slugs = Counter(d.get("slug") for d in plan["documents"])
    for slug, n in slugs.items():
        if not slug or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            errors.append(f"documents: slug {slug!r} is not kebab-case")
        if n > 1:
            errors.append(f"documents: slug {slug} appears {n} times")
    titles = Counter()
    for d, meta, blocks, refs, err in plan_paths(plan, base):
        where = f"{d.get('slug')} ({d.get('file')})"
        if err:
            errors.append(err)
            continue
        kind = d.get("kind", "page")
        if kind not in ("page", "decision"):
            errors.append(f"{where}: kind {kind!r} is page or decision")
        title = meta.get("title", "").strip()
        titles[title.lower()] += 1
        if not title:
            errors.append(f"{where}: no title")
        for field in ("tldr", "description"):
            if re.search(r"`|\*\*|\]\(|(^|\s)_\w[^_]*_(?!\w)", meta.get(field, "") or ""):
                warnings.append(f"{where}: {field} is plain text; Markdown such as backticks shows literally")
        desc = meta.get("description", "")
        if not desc:
            errors.append(f"{where}: no description; agents find the page by it")
        elif len(desc) > MAX_DESCRIPTION:
            errors.append(f"{where}: description is {len(desc)} characters, at most {MAX_DESCRIPTION}")
        for t in meta.get("tags", []) or []:
            if t.lower() not in tags:
                errors.append(f"{where}: tag {t!r} is not in the plan's tags")
        for r in refs:
            if r not in slugs:
                errors.append(f"{where}: link ref:{r} names no document in the plan")
        for b in blocks:
            if b["type"] in ("code", "terminal", "chart"):
                continue
            if "![" in b.get("text", ""):
                errors.append(f"{where}: an image; Uberblick pages take no images, describe it or draw it")
            if re.search(r"<(/?[a-zA-Z][\w-]*)(\s[^>]*)?>", re.sub(r"`[^`]*`", "", "".join(
                    r["text"] for r in b.get("inline") or [{"text": b.get("text", ""), "marks": {}}]
                    if not r["marks"].get("inlineCode")))):
                warnings.append(f"{where}: HTML shows literally in Uberblick: {b.get('text', '')[:60]!r}")
        fences = {b.get("language") for b in blocks if b["type"] == "code"}
        for v in d.get("visuals", []):
            if v not in fences:
                warnings.append(f"{where}: `visuals` names {v}, but the document has no {v} block")
        if checkout:
            for src in d.get("sources", []) + d.get("tests", []):
                path = src.split(":")[0] if not src.startswith("git:") else None
                if path and not (checkout / path).exists():
                    errors.append(f"{where}: source {src} does not exist in the checkout")
        if blocks and blocks[0]["type"] == "heading" and blocks[0].get("level") == 1:
            warnings.append(f"{where}: starts with an H1; the title is shown already, drop it")
        if kind == "decision":
            if meta.get("tldr"):
                errors.append(f"{where}: decisions have no TL;DR")
            bad = [b["type"] for b in blocks if b["type"] not in DECISION_TYPES]
            groups = 0
            prev = None
            for b in blocks:
                if not (b["type"] == "list-item" and prev == "list-item"):
                    groups += 1
                prev = b["type"]
            if bad:
                errors.append(f"{where}: a decision answer takes paragraphs, code, tables or lists, not {bad}")
            if groups > 3:
                errors.append(f"{where}: a decision answer has at most three blocks (a list counts once), has {groups}")
            if words(blocks) > 60:
                errors.append(f"{where}: a decision answer has at most 60 words, has {words(blocks)}")
            if d.get("related") and d["related"] not in slugs:
                errors.append(f"{where}: related {d['related']} names no document in the plan")
            ans = d.get("answer")
            if ans and not all(ans.get(k) for k in ("who", "when", "where")):
                errors.append(f"{where}: answer needs who, when and where")
            if d.get("status") not in (None, "open", "decided"):
                errors.append(f"{where}: status is open or decided")
            if d.get("status") == "decided" and not ans:
                warnings.append(f"{where}: decided without a person's answer on record; a record read from history "
                                f"stays open until someone decides it")
        else:
            tldr = meta.get("tldr", "")
            if tldr and len(tldr) > MAX_TLDR:
                errors.append(f"{where}: tldr is {len(tldr)} characters, at most {MAX_TLDR}")
            if not tldr:
                warnings.append(f"{where}: no tldr; a person opening the page reads it first")
            n = words(blocks)
            if n > 900:
                warnings.append(f"{where}: {n} words; start small and split or cut")
            for b in blocks:
                if b["type"] in ("code", "terminal", "chart"):
                    continue
                # UI labels and examples in code formatting are the product's words, not history
                text = "".join(r["text"] for r in b["inline"] if not r["marks"].get("inlineCode")) \
                    if b.get("inline") else b.get("text", "")
                m = HISTORY.search(text)
                if m:
                    warnings.append(f"{where}: {m.group(0)!r} reads as history or plans; the corpus states the "
                                    f"product as it is: {text[:70]!r}")
        if not d.get("sources") and not d.get("tests"):
            warnings.append(f"{where}: no sources or tests; every page is grounded in the repository")
    for t, n in titles.items():
        if n > 1:
            errors.append(f"documents: title {t!r} is used {n} times")
    converted = defaultdict(list)
    for m in plan["markdown"]:
        if m.get("action") not in ("convert", "keep", "skip"):
            errors.append(f"markdown: {m.get('path')}: action is convert, keep or skip")
        if m.get("action") == "convert":
            for slug in ([m["doc"]] if isinstance(m.get("doc"), str) else m.get("doc") or []):
                if slug not in slugs:
                    errors.append(f"markdown: {m['path']} converts into {slug!r}, which is not a document")
                converted[slug].append(m["path"])
        if not m.get("why"):
            warnings.append(f"markdown: {m.get('path')}: no `why`")
        for sec in m.get("sections", []):
            if sec.get("action") not in ("convert", "keep", "skip"):
                errors.append(f"markdown: {m.get('path')} § {sec.get('heading')}: action is convert, keep or skip")
            if sec.get("action") == "convert" and SETUP_HEADING.match(sec.get("heading") or ""):
                warnings.append(f"markdown: {m.get('path')} § {sec.get('heading')} is setup or community material; "
                                f"keep it as Markdown and link it from the page")
            targets = sec.get("doc") if isinstance(sec.get("doc"), list) else [sec.get("doc")]
            for slug in targets if sec.get("action") == "convert" else []:
                if not isinstance(slug, str) or slug not in slugs:
                    errors.append(f"markdown: {m.get('path')} § {sec.get('heading')} converts into {slug!r}, "
                                  f"which is not a document")
    if checkout:
        for m in plan["markdown"]:
            if not m.get("sections") or not (checkout / m.get("path", "")).is_file():
                continue
            have = {h.strip() for h in re.findall(r"^#{1,6}\s+(.*?)\s*#*\s*$", read(checkout / m["path"]), re.M)}
            for sec in m["sections"]:
                if sec.get("heading") not in have:
                    warnings.append(f"markdown: {m['path']} has no heading {sec.get('heading')!r}; a section names "
                                    f"one exactly as the file has it")
    if scan:
        for doc in scan["markdown"]:
            if not entry_for(plan["markdown"], doc["path"]):
                errors.append(f"markdown: {doc['path']} is not accounted for (convert, keep or skip)")
        focus = {f.get("topic"): f for f in plan.get("tests", {}).get("focus", [])}
        journeys = sorted(((sum(t.get(k, 0) for k in ("e2e", "e2e-api", "cli")), t["topic"])
                           for t in scan.get("tests", {}).get("topics", [])), reverse=True)
        for n, topic in journeys[:8]:
            f = focus.get(topic)
            if n >= 10 and (not f or not (f.get("doc") or f.get("why"))):
                warnings.append(f"tests.focus: {topic} has about {n} journey cases and no page; cover it, or give "
                                f"the row a `why` (internal, reference only)")
    for c in plan.get("candidates", []):
        if c.get("create") and c["create"] not in slugs:
            errors.append(f"candidates: {c.get('question')!r} creates {c['create']!r}, which is not a document")
    for f in plan.get("tests", {}).get("focus", []):
        if f.get("doc") and f["doc"] not in slugs:
            errors.append(f"tests.focus: {f.get('topic')} points to {f['doc']!r}, which is not a document")
    if catalog is not None:
        for t in plan["tags"]:
            have = t["name"].lower() in catalog
            if have != (t.get("status") == "existing"):
                warnings.append(f"tags: {t['name']} is marked {t.get('status')}, but the catalog "
                                f"{'has' if have else 'lacks'} it")
    use = Counter(x.lower() for _d, meta, *_ in plan_paths(plan, base) for x in (meta.get("tags") or []))
    many = len(plan.get("documents", [])) > 8
    for t in plan["tags"]:
        n = use[t["name"].lower()]
        if n == 0 or (n == 1 and many and not t.get("core")):  # in a small corpus one page per area is normal
            warnings.append(f"tags: {t['name']} is used by {n} document(s); a tag earns its place with two or "
                            f"more, unless it names a core area")
    for c in plan.get("capabilities", []):
        if c.get("doc") and c["doc"] not in slugs:
            errors.append(f"capabilities: {c.get('name')!r} points to {c['doc']!r}, which is not a document")
        if not c.get("doc") and not c.get("why"):
            warnings.append(f"capabilities: {c.get('name')!r} has no page and no `why`")
    if not plan.get("capabilities"):
        warnings.append("capabilities: none listed; map what a person can do with the product to the pages first")
    groups = plan["sidebar"].get("groups", [])
    if not 3 <= len(groups) <= 6:
        warnings.append(f"sidebar: {len(groups)} groups; 3 to 6 read best")
    pinned = Counter()
    kinds = {d.get("slug"): d.get("kind", "page") for d in plan["documents"]}
    for g in groups:
        if DOC_TYPE_GROUP.fullmatch(g.get("name", "").strip()):
            warnings.append(f"sidebar: group {g.get('name')!r} names a kind of document; a group is a domain, "
                            f"topic or responsibility, and its records and references hang off its entry point")
        if len(g.get("docs", [])) > MAX_ENTRY_POINTS:
            warnings.append(f"sidebar: group {g.get('name')!r} pins {len(g['docs'])}; pin the domain's entry "
                            f"points (1 to {MAX_ENTRY_POINTS}) and link the rest from them")
        for slug in g.get("docs", []):
            pinned[slug] += 1
            if slug not in slugs:
                errors.append(f"sidebar: {g.get('name')!r} pins {slug!r}, which is not a document")
            elif kinds.get(slug) == "decision":
                warnings.append(f"sidebar: {slug} is a decision record; records are reached from their domain's "
                                f"page, pinned only when one is the entry point a person needs")
    for slug in sorted(set(slugs) - set(reachable(plan, base, pinned))):
        warnings.append(f"sidebar: {slug} is not reachable from any pinned entry point; link it from its "
                        f"domain's page")
    for slug, n in pinned.items():
        if n > 1:
            errors.append(f"sidebar: {slug} is pinned {n} times; a document has one pin")
    if plan["sidebar"].get("starter") not in (None, "keep", "unpin"):
        errors.append("sidebar: starter is keep or unpin")
    return errors, warnings


DOC_TYPE_GROUP = re.compile(r"(?i)(decisions?|decision records?|adrs?|rfcs?|reference|references|guides?|"
                            r"how-?tos?|docs|documentation|pages|misc|other|more|everything else)")
MAX_ENTRY_POINTS = 3


def fan_out(plan, base):
    """slug -> the documents it leads to: its links, and for a page the decision records that name it."""
    out = defaultdict(set)
    for d, _meta, _blocks, refs, _err in plan_paths(plan, base):
        out[d["slug"]] |= set(refs)
        if d.get("kind") == "decision" and d.get("related"):
            out[d["related"]].add(d["slug"])
    return out


def reachable(plan, base, start):
    edges, seen, todo = fan_out(plan, base), set(start), list(start)
    while todo:
        for nxt in edges.get(todo.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


def cmd_check(args):
    plan = load(args.plan)
    scan = load_scan(args.scan) if args.scan else None
    catalog = {t["name"].lower() for t in load(args.tags).get("tags", [])} if args.tags else None
    errors, warnings = validate(plan, Path(args.plan).resolve().parent, scan,
                                Path(args.checkout).resolve() if args.checkout else None, catalog)
    for w in warnings:
        print(f"warning: {w}")
    for e in errors:
        print(f"error: {e}")
    docs = plan.get("documents", [])
    kinds = Counter(d.get("kind", "page") for d in docs)
    actions = Counter(m.get("action") for m in plan.get("markdown", []))
    print(f"{len(docs)} documents ({kinds['page']} pages, {kinds['decision']} decisions); markdown entries: "
          + ", ".join(f"{k} {v}" for k, v in sorted(actions.items())) +
          f"; {len(errors)} errors, {len(warnings)} warnings")
    sys.exit(1 if errors else 0)


# --------------------------------------------------------------------------------------------------- corpus writes

def cmd_calls(args):
    """Ordered tool calls in two passes, so every link can name its target. First each document is created with
    its metadata only (pages, then decision records, which name their page); then each gets its blocks with
    insert_block, links included; then the sidebar. {"$ref": slug}, {"$doc": slug} and {{uuid:slug}} stand for
    the UUID that slug's create_doc returned."""
    plan = load(args.plan)
    base = Path(args.plan).resolve().parent
    errors, _ = validate(plan, base)
    if errors:
        sys.exit("the plan has errors; run `intake.py check` first")
    listing = load(args.tags)
    catalog = {t["name"].lower(): t["id"] for t in listing.get("tags", [])}
    if listing.get("complete") is False:
        print("the tag catalog reads complete: false. Tags missing from it are left off. On a team workspace, read "
              "it again once synced; on a local one (hubUrl null) it is already the whole catalog", file=sys.stderr)
    parsed = {d["slug"]: (d, meta, blocks, refs) for d, meta, blocks, refs, _ in plan_paths(plan, base)}
    done_before = load(args.applied) if args.applied else {}
    done_before = done_before.get("uuids", done_before)  # applied.json, or {slug: uuid} from the MCP route
    for slug, uuid in done_before.items():
        if slug in parsed and not parsed[slug][0].get("existing"):
            parsed[slug][0]["existing"] = uuid
            parsed[slug][0]["retag"] = True
    def decided(d):
        return d.get("kind") == "decision" and (d.get("status") or ("decided" if d.get("answer") else "open")) \
            == "decided"

    # pages, then open records, then decided ones: a decided record is created with its answer (Uberblick refuses
    # an empty one), so every document its answer links to must exist first
    order = sorted(parsed, key=lambda s: (parsed[s][0].get("kind", "page") == "decision", decided(parsed[s][0])))
    for i, slug in enumerate(order):
        d, _meta, _blocks, refs = parsed[slug]
        later = sorted(r for r in refs if r in order[i:] and not parsed[r][0].get("existing")) if decided(d) else []
        if later:
            sys.exit(f"{slug}: a decided record is created with its answer, which links to {', '.join(later)}, "
                     f"created after it; link a page instead, or leave the record open")
    calls, skipped_tags = [], set()

    def tag_list(meta):
        out = []
        for t in meta.get("tags", []) or []:
            if t.lower() not in catalog:
                skipped_tags.add(t)
                continue
            out.append(catalog[t.lower()])
        return out

    def linked(blocks):
        """`ref:slug` in a table's or card's text becomes the slug's UUID; prose carries {"$doc": slug} marks.
        A block with inline runs drops its `text`: the runs replace it, and the calls stay half the size."""
        out = []
        for b in blocks:
            b = dict(b)
            if b["type"] in ("table", "card", "figma"):
                b["text"] = re.sub(r"\]\(ref:([a-z0-9-]+)\)", lambda m: "](" + "{{uuid:" + m.group(1) + "}})",
                                   b["text"])
            elif b.get("inline"):
                del b["text"]
            out.append(b)
        return out

    for slug in order:
        d, meta, blocks, refs = parsed[slug]
        if d.get("existing"):
            calls.append({"tool": "existing", "slug": slug, "uuid": d["existing"]})
            if d.get("retag") and tag_list(meta):
                calls.append({"tool": "set_metadata", "arguments": {"uuid": d["existing"], "tags": tag_list(meta)}})
            continue
        a = {"title": meta["title"], "description": meta["description"]}
        tl = tag_list(meta)
        if tl:
            a["tags"] = tl
        if d.get("kind") == "decision":
            a["kind"] = "decision"
            a["status"] = d.get("status") or ("decided" if d.get("answer") else "open")
            if d.get("related"):
                a["related"] = {"$ref": d["related"]}
            if d.get("answer"):
                a["answer"] = d["answer"]
            if decided(d) and blocks:
                a["blocks"] = linked(blocks)
        elif meta.get("tldr"):
            a["tldr"] = meta["tldr"]
        calls.append({"tool": "create_doc", "slug": slug, "arguments": a})
    for slug in order:
        d, meta, blocks, refs = parsed[slug]
        if not d.get("existing") and blocks and not decided(d):
            calls.append({"tool": "insert_block", "slug": slug,
                          "arguments": {"uuid": {"$ref": slug}, "blocks": linked(blocks)}})
    for g in plan["sidebar"].get("groups", []):
        for slug in g.get("docs", []):
            calls.append({"tool": "pin_doc", "arguments": {"uuid": {"$ref": slug}, "group": g["name"]}})
    if plan["sidebar"].get("starter") == "unpin":
        # the starter pages and their group have fixed ids in every workspace; done already is fine
        calls += [{"tool": "unpin_doc", "optional": True, "arguments": {"uuid": u}} for u in STARTER_DOCS]
        calls.append({"tool": "sidebar_group", "optional": True,
                      "arguments": {"group": STARTER_GROUP, "action": "delete"}})
    for i, g in enumerate(plan["sidebar"].get("groups", [])):
        calls.append({"tool": "sidebar_group", "arguments": {"group": g["name"], "action": "move", "index": i}})
    if skipped_tags:
        print("tags not in the workspace's catalog, left off: " + ", ".join(sorted(skipped_tags)), file=sys.stderr)
        bare = sorted(c["slug"] for c in calls if c["tool"] == "create_doc" and not c["arguments"].get("tags"))
        if bare:
            print(f"{len(bare)} document(s) end up with no tag: " + ", ".join(bare), file=sys.stderr)
    json.dump(calls, sys.stdout, indent=1, ensure_ascii=False)
    print()


def cmd_resolve(args):
    """For the MCP tools: the next calls that can be sent, one per line, with every placeholder whose slug has a
    UUID filled in. It skips the create_doc calls already answered and stops before the first call that names a
    slug with no UUID yet: send what it printed, add the new UUIDs to the file, and run it again."""
    calls = load(args.calls)
    uuids = load(args.uuids) if Path(args.uuids).exists() else {}
    uuids = uuids.get("uuids", uuids)
    start = 0
    for i, c in enumerate(calls):  # everything up to the last answered create_doc was sent already
        if c["tool"] in ("create_doc", "existing") and c.get("slug") in uuids:
            start = i + 1
    printed = 0
    for i, c in enumerate(calls[start:], start):
        if c["tool"] == "existing":
            continue
        try:
            arguments = resolve(c.get("arguments", {}), uuids)
        except KeyError as e:
            print(f"stopped before call {i + 1} ({c['tool']}), which needs the UUID of {e}: send the calls above, "
                  f"add each create_doc's slug and uuid to {args.uuids}, and run resolve again", file=sys.stderr)
            break
        line = {"call": i + 1, "tool": c["tool"], "slug": c.get("slug") or target_slug(c), "arguments": arguments,
                "optional": c.get("optional")}
        for part in one_block(line) if args.one_block else [line]:
            print(json.dumps({k: v for k, v in part.items() if v is not None}, ensure_ascii=False))
        printed += 1
    else:
        print(f"calls {start + 1} to {len(calls)}: all ready", file=sys.stderr)
    if not printed and start < len(calls):
        sys.exit("nothing to send: a slug has no UUID in the file")


def one_block(line):
    """An insert_block with `blocks` as single inserts for a server that takes one block per call. Each goes in at
    the top, so they are sent last block first and need no block ids from earlier answers."""
    arguments = line["arguments"]
    if line["tool"] != "insert_block" or "blocks" not in arguments:
        return [line]
    blocks = arguments["blocks"]
    return [{**line, "part": f"{n}/{len(blocks)}", "arguments": {"uuid": arguments["uuid"], **blocks[n - 1]}}
            for n in range(len(blocks), 0, -1)]


def resolve(value, uuids):
    """Replace `{"$ref": slug}`, `{"$doc": slug}` and `{{uuid:slug}}` in text with the slug's UUID."""
    if isinstance(value, dict):
        if len(value) == 1 and next(iter(value)) in ("$ref", "$doc"):
            slug = next(iter(value.values()))
            if slug not in uuids:
                raise KeyError(slug)
            return uuids[slug]
        return {k: resolve(v, uuids) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, uuids) for v in value]
    if isinstance(value, str) and "{{uuid:" in value:
        def sub(m):
            if m.group(1) not in uuids:
                raise KeyError(m.group(1))
            return uuids[m.group(1)]
        return re.sub(r"\{\{uuid:([a-z0-9-]+)\}\}", sub, value)
    return value


def target_slug(call):
    where = (call.get("arguments") or {}).get("uuid")
    return where["$ref"] if isinstance(where, dict) and "$ref" in where else None


SETTLE_POLL = 2
# The pages and group `ub workspace create` seeds; fixed ids, so every workspace's starter is recognisable.
STARTER_DOCS = ("2d56b281-5614-43bd-b8d8-edd1c270a85a", "d7ddd0b1-fee9-4ef0-8f1e-42882f925c31")
STARTER_GROUP = "57a27e40-0000-4000-8000-000000000001"
# refusals of the starter cleanup that mean the page or group is already gone
ABSENT = re.compile(r"\b\w*not_found\b|not found|not pinned", re.I)


READ_TOOLS = {"list_tags", "get_sidebar", "list_docs", "search", "get_doc", "export_markdown", "get_help",
              "sync_status", "backlinks", "find_decisions", "get_data", "existing"}


class Stop(Exception):
    pass


def cmd_ub(args):
    """Run the calls through one `ub mcp serve` in the checkout: one agent in the workspace for the whole intake.
    Stops at the first error and writes what it applied so far, so a re-run with --resume skips the done calls."""
    calls = load(args.calls)
    checkout = Path(args.checkout).resolve()
    digests = [hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()[:16] for c in calls]
    before = load(args.out) if Path(args.out).exists() else None
    if before and before.get("workspace") and not args.resume:  # only a run that wrote records its workspace
        sys.exit(f"{args.out} records {before['done']} call(s) already applied: re-run with --resume to finish "
                 f"these calls, or plan the next writes with `calls --applied {args.out}` and a new --out")
    if args.resume and before and before.get("calls") != digests[:before.get("done", 0)]:
        sys.exit(f"the first {before.get('done')} calls in {args.calls} are not the ones {args.out} applied; "
                 f"--resume continues the same calls, changed only after where it stopped")
    applied = before if args.resume and before else {"uuids": {}, "adopted": [], "done": 0, "results": []}
    applied.setdefault("adopted", [])
    uuids = applied["uuids"]
    try:
        server = subprocess.Popen(args.ub.split() + ["mcp", "serve"], cwd=checkout, stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    except OSError as e:
        sys.exit(f"ub: {e}")
    ids = iter(range(1, 1_000_000))

    def ask(method, params):
        n = next(ids)
        server.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params}) + "\n")
        server.stdin.flush()
        for line in server.stdout:
            message = json.loads(line) if line.strip().startswith("{") else {}
            if message.get("id") == n:
                if "error" in message:
                    raise RuntimeError(message["error"].get("message"))
                return message["result"]
        raise RuntimeError(f"ub mcp serve stopped before answering {method}; run `ub doctor` in {checkout}")

    def call(tool, arguments):
        result = ask("tools/call", {"name": tool, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise RuntimeError(text)
        return text

    def save():
        applied["calls"] = digests[:applied["done"]]
        Path(args.out).write_text(json.dumps(applied, indent=1, ensure_ascii=False), encoding="utf-8")

    failed = None
    try:
        ask("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "uberblick-intake", "title": "Uberblick intake", "version": "1.0"}})
        server.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        tools = {t["name"]: t for t in ask("tools/list", {}).get("tools", [])}
        # older ub versions insert one block per call, after a block id they answered with
        one_at_a_time = "blocks" not in tools.get("insert_block", {}).get("inputSchema", {}).get("properties", {"blocks": 1})
        pending = [c for c in calls[applied["done"]:] if c["tool"] == "create_doc" and c["slug"] not in uuids]
        if pending or any(c["tool"] not in READ_TOOLS for c in calls):
            listing = json.loads(call("list_docs", {}))
            if applied.setdefault("workspace", listing["workspace"]) != listing["workspace"]:
                raise Stop(f"{args.out} was applied to workspace {applied['workspace']}, but {checkout} is bound to "
                           f"{listing['workspace']}")
            # list_docs leaves decision records out unless asked for them
            records = json.loads(call("list_docs", {"kind": "decision"}))["docs"]
            titles = {d["title"].strip().lower(): d["uuid"] for d in listing["docs"] + records}
            clash = {c["slug"]: titles[c["arguments"]["title"].strip().lower()] for c in pending
                     if c["arguments"]["title"].strip().lower() in titles}
            if clash and not args.adopt:
                raise Stop("the workspace already has a document titled like " + ", ".join(sorted(clash)) +
                           ": rename them in the plan, mark them `existing: UUID`, or pass --adopt to use the "
                           "document already there instead of creating one")
        else:
            clash = {}
        for i, c in enumerate(calls):
            if i < applied["done"]:
                continue
            if c["tool"] == "existing" or (c["tool"] == "create_doc" and c["slug"] in clash):
                uuids[c["slug"]] = c.get("uuid") or clash[c["slug"]]
                if c["tool"] == "create_doc":
                    applied["adopted"].append(c["slug"])
                applied["done"] = i + 1
                continue
            if target_slug(c) in applied["adopted"] and c["tool"] == "insert_block":
                applied["results"].append({"tool": c["tool"], "slug": target_slug(c),
                                           "text": "skipped: the document was adopted, not written by this run"})
                applied["done"] = i + 1
                continue
            try:
                arguments = resolve(c.get("arguments", {}), uuids)
                if c["tool"] == "insert_block" and one_at_a_time and "blocks" in arguments:
                    after = None
                    for block in arguments["blocks"]:
                        one = {"uuid": arguments["uuid"], **block, **({"after_block_id": after} if after else {})}
                        text = call("insert_block", one)
                        after = json.loads(text)["block"]["id"]
                else:
                    text = call(c["tool"], arguments)
            except (RuntimeError, KeyError, ValueError) as e:
                if c.get("optional"):
                    # starter cleanup: a page already unpinned or a group already gone is the state we want;
                    # any other refusal is kept as a warning, since the cleanup did not happen
                    absent = bool(ABSENT.search(str(e)))
                    applied["results"].append({"tool": c["tool"], "text": f"optional, not applied: {e}"})
                    if not absent:
                        applied.setdefault("warnings", []).append(f"{c['tool']} {json.dumps(c.get('arguments'))}: {e}")
                        print(f"ub: optional {c['tool']} refused for a reason other than an absent page or group, "
                              f"so the starter cleanup is incomplete: {e}", file=sys.stderr)
                    applied["done"] = i + 1
                    save()
                    continue
                failed = f"call {i + 1} ({c['tool']} {c.get('slug') or target_slug(c) or ''}): {e}"
                break
            if c["tool"] == "create_doc":
                try:
                    uuids[c["slug"]] = json.loads(text)["uuid"]
                except (ValueError, KeyError):
                    failed = f"call {i + 1}: create_doc answered without a uuid: {text[:200]}"
                    break
            applied["results"].append({"tool": c["tool"], "slug": c.get("slug"),
                                       **({"answer": brief(text)} if c["tool"] in ("create_doc", "insert_block",
                                                                                    "pin_doc") else {"text": text})})
            applied["done"] = i + 1
            save()
            print(f"{i + 1}/{len(calls)} {c['tool']} {c.get('slug') or ''}".rstrip(), file=sys.stderr)
        if not failed and any(c["tool"] in ("pin_doc", "unpin_doc", "sidebar_group") for c in calls):
            applied["sidebar"] = json.loads(call("get_sidebar", {}))
            for g in applied["sidebar"].get("groups", []):
                print(f"sidebar: {g.get('name')}: " + ", ".join(d.get("title", d["uuid"]) for d in g.get("docs", [])),
                      file=sys.stderr)
        deadline = time.monotonic() + args.settle
        wrote = any(c["tool"] not in READ_TOOLS for c in calls)
        while wrote and applied["done"]:
            try:
                status = json.loads(call("sync_status", {}))
            except (ValueError, RuntimeError):
                break
            applied["sync"] = status
            hub = (status.get("hub") or {}).get("status")
            if hub == "local":
                # newer servers: a local workspace without `ub open` has nothing pending
                print(f"ub: the writes are applied in this local workspace; `ub open` in {checkout} serves them to "
                      f"the web editor", file=sys.stderr)
                break
            if not status.get("unsyncedChanges") and not status.get("inFlightUpdates"):
                break
            if hub == "hub-down":
                if local_workspace(checkout):
                    print(f"ub: the writes are applied in this local workspace; `ub open` in {checkout} serves its "
                          f"hub, and they sync while it runs", file=sys.stderr)
                else:
                    print(f"ub: no hub is reachable ({(status.get('hub') or {}).get('reason')}); the writes are in "
                          f"this machine's replica and reach the hub when a server next runs in {checkout} with it up",
                          file=sys.stderr)
                break
            if time.monotonic() > deadline:
                print(f"ub: the hub has not acknowledged {status.get('unsyncedChanges')} change(s) after "
                      f"{args.settle}s; they are saved locally and sync when a server next runs in {checkout}",
                      file=sys.stderr)
                break
            time.sleep(SETTLE_POLL)
    except Stop as e:
        failed = str(e)
    finally:
        save()
        server.stdin.close()
        try:
            server.wait(timeout=60)
        except subprocess.TimeoutExpired:
            server.kill()
    if failed:
        sys.exit(f"{failed}\napplied {applied['done']} of {len(calls)}; fix the call and re-run with --resume")
    if args.print:
        for r in applied["results"]:
            if r.get("text"):
                print(f"== {r['tool']}\n{r['text']}")
    elif uuids and not getattr(args, "quiet", False):
        print(json.dumps(uuids, indent=1))


# --------------------------------------------------------------------------------------------------- review page

def esc(x):
    return html.escape(str(x), quote=True)


def inline_html(text):
    """Markdown text (a table cell, a card field, a plan note) as HTML."""
    return runs_html(runs(text))


def prose_html(block):
    """A prose block as parsed: its text is plain, its marks are in `inline`."""
    return runs_html(block.get("inline") or [{"text": block["text"], "marks": {}}])


def runs_html(rs):
    out = []
    for r in rs:
        t = esc(r["text"])
        m = r["marks"]
        if m.get("inlineCode"):
            t = f"<code>{t}</code>"
        if m.get("bold"):
            t = f"<strong>{t}</strong>"
        if m.get("italic"):
            t = f"<em>{t}</em>"
        if m.get("strike"):
            t = f"<s>{t}</s>"
        if m.get("link"):
            t = f'<a href="{esc(m["link"])}">{t}</a>'
        if m.get("docLink"):
            target = m["docLink"]["$doc"] if isinstance(m["docLink"], dict) else m["docLink"]
            t = f'<a href="#doc-{esc(target)}">{t}</a>'
        out.append(t)
    return "".join(out)


def doc_html(blocks, svgs):
    out, in_list = [], None
    for b in blocks:
        t = b["type"]
        if t != "list-item" and in_list:
            out.append(f"</{in_list}>")
            in_list = None
        if t == "heading":
            lvl = min(6, b.get("level", 2) + 1)
            out.append(f"<h{lvl}>{prose_html(b)}</h{lvl}>")
        elif t == "paragraph":
            out.append(f"<p>{prose_html(b)}</p>")
        elif t == "quote":
            out.append(f"<blockquote>{prose_html(b)}</blockquote>")
        elif t == "list-item":
            tag = "ol" if b.get("list") == "ordered" else "ul"
            if in_list != tag:
                if in_list:
                    out.append(f"</{in_list}>")
                out.append(f"<{tag}>")
                in_list = tag
            out.append(f'<li style="margin-left:{b.get("indent", 0) * 1.4}em">{prose_html(b)}</li>')
        elif t == "table":
            rows = [r.strip().strip("|").split("|") for r in b["text"].splitlines()
                    if not DELIMITER_ROW.match(r)]
            body = "".join("<tr>" + "".join(f"<{'th' if i == 0 else 'td'}>{inline_html(c.strip())}"
                                           f"</{'th' if i == 0 else 'td'}>" for c in row) + "</tr>"
                           for i, row in enumerate(rows))
            out.append(f"<table>{body}</table>")
        elif t == "card":
            head, _, body = b["text"].partition("\n\n")
            body = re.sub(r"^(footer|button):.*$", "", body, flags=re.M)
            fields = dict(re.findall(r"^(label|title):\s?(.*)$", head, re.M) +
                          re.findall(r"^(footer):\s?(.*)$", b["text"], re.M))
            out.append('<div class="card">' + (f'<div class="lbl">{inline_html(fields["label"])}</div>'
                                               if fields.get("label") else "") +
                       f'<div class="ttl">{inline_html(fields.get("title", ""))}</div>' +
                       (f"<p>{inline_html(body.strip())}</p>" if body.strip() else "") +
                       (f'<div class="ftr">{inline_html(fields["footer"])}</div>' if fields.get("footer") else "") +
                       "".join(f'<span class="btn">{inline_html(x)}</span>'
                               for x in re.findall(r"^button:\s?(.*)$", b["text"], re.M)) +
                       "</div>")
        elif t == "code" and b.get("language") == "ablauf" and svgs:
            svg = svgs.pop(0)
            out.append(f'<figure class="viz">{svg}</figure>' if svg else f"<pre>{esc(b['text'])}</pre>")
        elif t == "code" and b.get("language") == "wireframe":
            out.append(f'<figure class="viz wf" data-wireframe="{esc(b["text"])}"><pre>{esc(b["text"])}</pre>'
                       f"<figcaption>Wireframe</figcaption></figure>")
        else:
            out.append(f"<pre>{esc(b.get('text', ''))}</pre>")
    if in_list:
        out.append(f"</{in_list}>")
    return "\n".join(out)


def cmd_review(args):
    plan = load(args.plan)
    scan = load_scan(args.scan)
    base = Path(args.plan).resolve().parent
    errors, warnings = validate(plan, base, scan)
    template = (Path(__file__).resolve().parent.parent / "assets" / "review.html").read_text(encoding="utf-8")
    parsed = plan_paths(plan, base)
    by_slug = {d["slug"]: (d, meta, blocks) for d, meta, blocks, _r, _e in parsed}
    title_of = {s: v[1].get("title", s) for s, v in by_slug.items()}
    # Sidebar preview
    side = []
    edges = fan_out(plan, base)
    pins = [s for g in plan["sidebar"].get("groups", []) for s in g.get("docs", [])]

    def item(slug, sub=False):
        kind = by_slug.get(slug, ({}, {}, []))[0].get("kind", "page")
        icon = "◆" if kind == "decision" else "▤"
        return (f'<a class="si{" sub" if sub else ""}" href="#doc-{esc(slug)}"><span>{icon}</span>'
                f'{esc(title_of.get(slug, slug))}</a>')

    for g in plan["sidebar"].get("groups", []):
        side.append(f'<div class="sg">{esc(g["name"])}</div>')
        for slug in g.get("docs", []):
            side.append(item(slug))
            # what the entry point fans out to: the documents it links to that have no pin of their own
            for sub in sorted(edges.get(slug, ()) - set(pins), key=lambda s: title_of.get(s, s)):
                if sub in by_slug:
                    side.append(item(sub, sub=True))
    lost = [s for s in by_slug if s not in reachable(plan, base, pins)]
    if lost:
        side.append(f'<div class="sg muted">Not reachable from an entry point ({len(lost)})</div>')
        side += [f'<a class="si muted" href="#doc-{esc(s)}"><span>▤</span>{esc(title_of.get(s, s))}</a>'
                 for s in lost]
    # Tags
    tag_rows = []
    use = Counter(t.lower() for _d, meta, *_ in parsed for t in (meta.get("tags") or []))
    for t in plan["tags"]:
        tag_rows.append(f"<tr><td><span class='tag {'new' if t.get('status') == 'new' else ''}'>{esc(t['name'])}"
                        f"</span></td><td>{'new' if t.get('status') == 'new' else 'existing'}</td>"
                        f"<td class='num'>{use[t['name'].lower()]}</td><td>{inline_html(t.get('why', ''))}</td></tr>")
    # Markdown dispositions
    md_rows = []
    for m in plan["markdown"]:
        n = sum(1 for d in scan["markdown"] if covers(m["path"], d["path"]))
        target = m.get("doc")
        target = ", ".join(f'<a href="#doc-{esc(x)}">{esc(title_of.get(x, x))}</a>'
                           for x in ([target] if isinstance(target, str) else target or []))
        md_rows.append(f"<tr class='{esc(m['action'])}'><td><code>{esc(m['path'])}</code></td><td class='num'>{n}</td>"
                       f"<td><span class='act {esc(m['action'])}'>{esc(m['action'])}</span></td><td>{target}</td>"
                       f"<td>{inline_html(m.get('why', ''))}</td></tr>")
        for sec in m.get("sections", []):
            into = sec.get("doc")
            into = ", ".join(f'<a href="#doc-{esc(x)}">{esc(title_of.get(x, x))}</a>'
                             for x in ([into] if isinstance(into, str) else into or []))
            md_rows.append(f"<tr class='{esc(sec.get('action'))}'><td>§ {esc(sec.get('heading', ''))}</td><td></td>"
                           f"<td><span class='act {esc(sec.get('action'))}'>{esc(sec.get('action'))}</span></td><td>"
                           f"{into}</td><td>{inline_html(sec.get('why', ''))}</td></tr>")
    cap_rows = []
    for c in plan.get("capabilities", []):
        doc = c.get("doc")
        cap_rows.append(f"<tr><td>{inline_html(c.get('name', ''))}</td><td>"
                        f"{'<a href=#doc-' + esc(doc) + '>' + esc(title_of.get(doc, doc)) + '</a>' if doc else '—'}"
                        f"</td><td>{inline_html(c['why']) if c.get('why') else ''}"
                        f"{' '.join(f'<code>{esc(e)}</code>' for e in c.get('evidence', []))}</td></tr>")
    # Decision candidates
    cand_rows = []
    url = scan["churn"].get("commit_url")
    for c in plan.get("candidates", []):
        ev = " ".join(f'<a href="{esc(url + e)}"><code>{esc(e[:8])}</code></a>'
                      if url and re.fullmatch(r"[0-9a-f]{7,40}", e) else f"<code>{esc(e)}</code>"
                      for e in c.get("evidence", []))
        made = c.get("create")
        status = by_slug.get(made, ({}, {}, []))[0].get("status") or (
            "decided" if by_slug.get(made, ({}, {}, []))[0].get("answer") else "open")
        cand_rows.append(f"<tr><td>{inline_html(c['question'])}</td><td>{ev}</td><td>"
                         f"{'<a href=#doc-' + esc(made) + '>' + status + ' record</a>' if made else 'skip'}</td>"
                         f"<td>{inline_html(c.get('why', ''))}</td></tr>")
    # Test focus
    t = scan["tests"]
    focus = plan.get("tests", {}).get("focus", [])
    top = max([f.get("cases", 0) for f in focus] + [1])
    focus_rows = []
    for f in focus:
        width = 100 * f.get("cases", 0) / top
        doc = f.get("doc")
        focus_rows.append(f"<tr><td>{esc(f['topic'])}</td><td class='num'>{f.get('cases', 0)}</td>"
                          f"<td>{esc(f.get('kind', ''))}</td><td><div class='bar' style='width:{width:.0f}%'></div></td>"
                          f"<td>{'<a href=#doc-' + esc(doc) + '>' + esc(title_of.get(doc, doc)) + '</a>' if doc else '—'}"
                          f"</td></tr>")
    # Documents
    docs_html = []
    for d, meta, blocks in by_slug.values():
        svgs = []
        n = sum(1 for b in blocks if b["type"] == "code" and b.get("language") == "ablauf")
        for i in range(n):
            # viz.mjs draws next to the document file, named after it
            doc_file = base / d.get("file", "")
            p = doc_file.parent / "viz" / f"{doc_file.stem}-{i + 1}.svg"
            svgs.append(p.read_text(encoding="utf-8") if p.exists() else None)
        tags = "".join(f"<span class='tag'>{esc(x)}</span>" for x in meta.get("tags") or [])
        src = ", ".join(f"<code>{esc(x)}</code>" for x in d.get("sources", []) + d.get("tests", []))
        kind = d.get("kind", "page")
        docs_html.append(
            f'<article class="doc {esc(kind)}" id="doc-{esc(d["slug"])}"><header><div class="kind">'
            f'{"Decision record" if kind == "decision" else "Page"}</div><h3>{esc(meta.get("title", d["slug"]))}</h3>'
            f'<div class="tags">{tags}</div>'
            + (f'<p class="tldr">{inline_html(meta["tldr"])}</p>' if meta.get("tldr") else "")
            + f'<p class="desc">{esc(meta.get("description", ""))}</p><p class="src">From {src or "—"}</p>'
            f'</header>{doc_html(blocks, svgs)}</article>')
    issues = "".join(f"<li class='err'>{esc(e)}</li>" for e in errors) + \
        "".join(f"<li class='warn'>{esc(w)}</li>" for w in warnings)
    changes = "".join(f"<li><code>{esc(c['path'])}</code>: {inline_html(c['change'])}</li>"
                      for c in plan.get("repo_changes", []))
    kinds = Counter(d.get("kind", "page") for d in plan["documents"])
    md_actions = Counter()
    for doc in scan["markdown"]:
        hit = entry_for(plan["markdown"], doc["path"])
        if hit:
            md_actions[hit["action"]] += 1
    stats = [(len(scan["markdown"]), "Markdown files"), (md_actions["convert"], "converted"),
             (md_actions["keep"], "kept as Markdown"), (md_actions["skip"], "skipped"),
             (kinds["page"], "pages"), (kinds["decision"], "decision records"),
             (sum(1 for x in plan["tags"] if x.get("status") == "new"), "new tags")]
    page = template
    for key, value in {
        "TITLE": f"Intake: {plan['repository']}",
        "REPO": esc(plan["repository"]),
        "REF": esc(plan["ref"]),
        "DATE": esc(plan.get("date", "")),
        "SUMMARY": inline_html(plan["summary"]),
        "STATS": "".join(f"<div class='stat'><b>{n}</b><span>{esc(label)}</span></div>" for n, label in stats),
        "ISSUES": f"<ul class='issues'>{issues}</ul>" if issues else "<p class='ok'>The plan passes every check.</p>",
        "SIDEBAR": "\n".join(side),
        "TAGS": "".join(tag_rows),
        "MARKDOWN": "".join(md_rows),
        "CAPABILITIES": "".join(cap_rows) or "<tr><td colspan=3>None listed.</td></tr>",
        "CANDIDATES": "".join(cand_rows) or "<tr><td colspan=4>No candidates.</td></tr>",
        "TESTSUMMARY": inline_html(plan.get("tests", {}).get("summary", "")) + " " + esc(
            f"{t['total_cases']} cases: " + ", ".join(f"{k} {v}" for k, v in sorted(t['cases'].items(),
                                                                                 key=lambda kv: -kv[1])) + "."),
        "FOCUS": "".join(focus_rows),
        "CHANGES": (f"<ul>{changes}</ul>" if changes else "<p>None.</p>"),
        "STARTER": {"unpin": "The starter pages (Welcome to Uberblick, How to Use It) are unpinned and their group "
                             "removed.",
                    "keep": "The starter pages stay pinned."}.get(plan["sidebar"].get("starter"),
                                                                  "The starter pages are left as they are."),
        "NOTES": "".join(f"<li>{inline_html(n)}</li>" for n in plan.get("notes", [])) or "<li>None.</li>",
        "DOCS": "\n".join(docs_html),
    }.items():
        page = page.replace("{{" + key + "}}", value)
    Path(args.out).write_text(page, encoding="utf-8")
    print(f"{args.out}: {len(by_slug)} documents, {len(errors)} errors, {len(warnings)} warnings")
    if args.open and not webbrowser.open(Path(args.out).resolve().as_uri()):
        print(f"no browser here: open {Path(args.out).resolve()} yourself, or send it to the person")


# --------------------------------------------------------------------------------------------------- main

def cmd_corpus(args):
    """Read the workspace once: DIR/tags.json, DIR/sidebar.json and DIR/docs.json, for the plan and for `calls`."""
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)
    reads = [("list_tags", {}), ("get_sidebar", {}), ("list_docs", {}), ("list_docs", {"kind": "decision"})]
    (out / "read.json").write_text(json.dumps([{"tool": t, "arguments": a} for t, a in reads]), encoding="utf-8")
    applied = out / "read-applied.json"
    applied.unlink(missing_ok=True)
    cmd_ub(argparse.Namespace(calls=str(out / "read.json"), checkout=args.checkout, out=str(applied), resume=False,
                              adopt=False, settle=0, ub=args.ub, print=False, quiet=True))
    tags, sidebar, docs, records = (json.loads(r["text"]) for r in load(applied)["results"])
    docs["docs"] += records["docs"]
    for name, value in (("tags", tags), ("sidebar", sidebar), ("docs", docs)):
        (out / f"{name}.json").write_text(json.dumps(value, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"workspace {docs.get('workspace')}: {len(docs.get('docs', []))} documents; groups "
          + ", ".join(f"{g.get('name')} ({len(g.get('docs', []))})" for g in sidebar.get("groups", []))
          + "; tags " + (", ".join(t["name"] for t in tags.get("tags", [])) or "none")
          + ("" if tags.get("complete", True) or local_workspace(args.checkout)
             else " (catalog incomplete: not fully synced yet)"))


def main():
    if hasattr(signal, "SIGPIPE"):  # `intake.py hot … | head` ends quietly
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("scan", help="read the checkout: Markdown, docs site, git churn, tests")
    s.add_argument("checkout")
    s.add_argument("--max-commits", type=int, default=5000)
    h = sub.add_parser("hot", help="the churn and direction changes, readable")
    h.add_argument("scan")
    h.add_argument("--limit", type=int, default=15)
    t = sub.add_parser("tests", help="the test focus, readable")
    t.add_argument("scan")
    t.add_argument("--titles", type=int, default=80)
    t.add_argument("--topics", type=int, default=25)
    t.add_argument("--per-file", type=int, default=8, help="test titles per journey file")
    b = sub.add_parser("blocks", help="one Uberblick Markdown file as create_doc arguments")
    b.add_argument("doc")
    c = sub.add_parser("check", help="the plan against the scan and the corpus rules")
    c.add_argument("plan")
    c.add_argument("--scan")
    c.add_argument("--checkout", help="the repository, to check that every source and test path exists")
    c.add_argument("--tags", help="DIR/corpus/tags.json, to check which tags exist")
    r = sub.add_parser("review", help="the page a person approves before the writes")
    r.add_argument("plan")
    r.add_argument("--scan", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--open", action="store_true")
    k = sub.add_parser("calls", help="the ordered corpus writes")
    k.add_argument("plan")
    k.add_argument("--tags", required=True,
                   help="list_tags output, to pass tag ids and leave off tags the catalog lacks")
    k.add_argument("--applied", help="applied.json of an earlier run: those documents are not created again, "
                                     "only given the plan's tags that exist now")
    v = sub.add_parser("resolve", help="for the MCP tools: the calls with the UUIDs filled in, ready to send")
    v.add_argument("--calls", required=True)
    v.add_argument("--uuids", required=True, help="{slug: uuid} from the create_doc answers (or applied.json)")
    v.add_argument("--one-block", action="store_true",
                   help="the server's insert_block takes one block, no `blocks`: print one insert per block")
    w = sub.add_parser("corpus", help="read the workspace's tags, sidebar and documents into DIR")
    w.add_argument("--checkout", required=True)
    w.add_argument("--dir", required=True)
    w.add_argument("--ub", default="ub", help="the command that runs ub (default: ub)")
    u = sub.add_parser("ub", help="run the calls through one `ub mcp serve`")
    u.add_argument("--calls", required=True)
    u.add_argument("--checkout", required=True)
    u.add_argument("--out", default="applied.json")
    u.add_argument("--resume", action="store_true", help="continue the same calls file after a stop")
    u.add_argument("--adopt", action="store_true",
                   help="a page whose title the workspace already has is used as it is, not created again")
    u.add_argument("--settle", type=int, default=60)
    u.add_argument("--ub", default="ub", help="the command that runs ub (default: ub)")
    u.add_argument("--print", action="store_true", help="print each answer, for reads such as list_tags")
    args = parser.parse_args()
    {"scan": cmd_scan, "hot": cmd_hot, "tests": cmd_tests, "blocks": cmd_blocks, "check": cmd_check,
     "review": cmd_review, "calls": cmd_calls, "resolve": cmd_resolve, "corpus": cmd_corpus,
     "ub": cmd_ub}[args.command](args)


if __name__ == "__main__":
    main()
