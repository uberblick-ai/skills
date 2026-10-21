#!/usr/bin/env python3
"""Run agent trials: give a fresh headless agent a task with only this MCP
server loaded, and record what it did, in order.

Each trial answers one behavioural question the static report leaves open,
such as "is the syntax help read before the first table is written?". The
agent is Claude Code in print mode (`claude -p`) with stream-json output, so
the transcript shows every tool call, its size and whether it failed.

  trial.py run --mcp-config CFG --server NAME --plan DIR/trials.json --out DIR

Write tools are blocked by permissions unless --allow-writes is given (use it
only against a sandbox). A blocked call still shows what the agent would have
sent, which is what most trials need. Results go into DIR/probe.json under
"trials", transcripts into DIR/trials/. Secrets are redacted before anything
is written, as in probe.py.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402  (scrub, write_record)

CLIENT_TOOLS = ["ListMcpResourcesTool", "ReadMcpResourceTool", "ToolSearch"]
# The child must be a fresh session, not a copy of the one running the review.
SESSION_ENV = ["CLAUDECODE", "CLAUDE_PID", "CLAUDE_CODE_SESSION_ID", "CLAUDE_CODE_REMOTE_SESSION_ID",
               "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_CODE_MESSAGING_TOKEN", "CLAUDE_CODE_MAX_MCP_DESCRIPTION_LENGTH",
               "CLAUDE_AFTER_LAST_COMPACT", "CLAUDE_CODE_TEE_SDK_STDOUT", "CLAUDE_CODE_DIAGNOSTICS_FILE"]
NOTE_BLOCKED = ("Tools that change data may be blocked in this session. If a call is denied, do not look for a "
                "workaround: finish with the exact call you would have made and why.")
DEFAULT_HELP_TOOLS = ["*help*", "*guide*", "*docs*", "*manual*"]


def result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return ""


def is_help(name: str, inp: dict, help_spec: dict) -> bool:
    if name == "ReadMcpResourceTool":
        return any(fnmatch.fnmatch(str(inp.get("uri", "")), p) for p in help_spec.get("resources", ["*"]))
    return any(fnmatch.fnmatch(name, p) for p in help_spec.get("tools", DEFAULT_HELP_TOOLS))


def summarize(lines: list[dict], server: str, trial: dict, help_spec: dict) -> dict:
    lines = [m for m in lines if isinstance(m, dict)]
    prefix = f"mcp__{server}__"
    init = next((m for m in lines if m.get("type") == "system" and m.get("subtype") == "init"), {})
    final = next((m for m in reversed(lines) if m.get("type") == "result"), {})
    denied = {d.get("tool_use_id") for d in final.get("permission_denials") or []}
    events, by_id, text = [], {}, []
    for m in lines:
        msg = m.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            if m.get("type") == "assistant" and c.get("type") == "tool_use":
                name = c.get("name", "")
                short = name[len(prefix):] if name.startswith(prefix) else name
                inp = c.get("input") or {}
                kind = ("help" if is_help(short, inp, help_spec) else "client" if short in CLIENT_TOOLS
                        else "tool" if name.startswith(prefix) else "other")
                ev = {"i": len(events), "tool": short, "kind": kind, "input": json.dumps(inp, ensure_ascii=False)[:600],
                      "denied": c.get("id") in denied}
                if short == "ReadMcpResourceTool":
                    ev["uri"] = inp.get("uri")
                events.append(ev)
                by_id[c.get("id")] = ev
            elif m.get("type") == "assistant" and c.get("type") == "text":
                text.append(c.get("text", ""))
            elif m.get("type") == "user" and c.get("type") == "tool_result":
                ev = by_id.get(c.get("tool_use_id"))
                if ev is not None:
                    body = result_text(c.get("content"))
                    ev["bytes"] = len(body.encode("utf-8"))
                    ev["tokens"] = probe.estimate_tokens(body)
                    ev["is_error"] = bool(c.get("is_error")) and not ev["denied"]
                    if ev["is_error"]:
                        ev["error"] = body[:400]
    needs = set(trial.get("needs") or [])
    first_use = next((e["i"] for e in events if e["tool"] in needs), None)
    help_events = [e for e in events if e["kind"] == "help"]
    errors = [e for e in events if e.get("is_error") and e["kind"] in ("tool", "help")]
    # Recovered: the agent retried the same tool with changed input and it worked, with at most
    # one or two other server calls (a help read, a lookup) in between. A later unrelated success does not count.
    recovered = 0
    server = [x for x in events if x["kind"] in ("tool", "help")]
    for e in errors:
        after = [x for x in server if x["i"] > e["i"]]
        nxt = next((k for k, x in enumerate(after) if x["tool"] == e["tool"]), None)
        recovered += bool(nxt is not None and nxt <= 2 and after[nxt]["input"] != e["input"]
                          and not after[nxt].get("is_error") and not after[nxt]["denied"])
    seen, repeats = set(), 0
    for e in events:
        key = (e["tool"], e["input"])
        repeats += key in seen
        seen.add(key)
    def matches(e, spec):
        if spec == "help":
            return e["kind"] == "help"
        name, _, pattern = spec.partition(":")
        if e["tool"] != name:
            return False
        return not pattern or fnmatch.fnmatch(str(e.get("uri") or ""), pattern) or pattern in e.get("input", "")

    rules = []
    for rule in trial.get("rules") or []:
        first = next((e["i"] for e in events if any(matches(e, f) for f in rule.get("first", []))), None)
        before = [e for e in events if any(matches(e, b) for b in rule.get("before", []))]
        rules.append({"label": rule.get("label", ""), "applies": first is not None,
                      "followed": None if first is None else any(e["i"] < first for e in before)})
    usage = final.get("usage") or {}
    # Context per API call: what the model holds at that step, cached or not.
    context = [sum(int((m["message"].get("usage") or {}).get(k) or 0)
                   for k in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
               for m in lines if m.get("type") == "assistant" and isinstance(m.get("message"), dict)]
    context = [c for c in context if c]
    return {
        "id": trial["id"], "question": trial.get("question", ""), "task": trial["task"],
        "expects_help": trial.get("expects_help"), "needs": sorted(needs),
        "model": init.get("model") or max((final.get("modelUsage") or {}).items(),
                                          key=lambda kv: kv[1].get("outputTokens", 0), default=(None, {}))[0],
        "events": events,
        "calls": sum(1 for e in events if e["kind"] in ("tool", "help")),
        "help_reads": len(help_events), "help_bytes": sum(e.get("bytes", 0) for e in help_events),
        "help_tokens": sum(e.get("tokens", 0) for e in help_events),
        "first_use": first_use,
        "help_before_use": None if first_use is None or not needs else any(e["i"] < first_use for e in help_events),
        "rules": rules,
        "errors": len(errors), "recovered": recovered, "repeats": repeats,
        "drafts": [e for e in events if e["denied"]],
        "tokens": sum(int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                                         "cache_creation_input_tokens")),
        "context_start": context[0] if context else None,
        "context_peak": max(context) if context else None,
        "server_tokens": sum(e.get("tokens", 0) for e in events if e["kind"] in ("tool", "help")),
        "cost_usd": final.get("total_cost_usd") or sum(float(v.get("costUSD") or 0) for v in (final.get("modelUsage") or {}).values()
                                                       if isinstance(v, dict)) or None,
        "turns": final.get("num_turns"), "ms": final.get("duration_ms"),
        "status": final.get("subtype") or "no result",
        "answer": (final.get("result") or "\n".join(text))[-3000:],
        "mcp_status": [s.get("status") for s in init.get("mcp_servers") or []],
        "client": f"claude-code {init.get('claude_code_version', '')}".strip(),
    }


def safe_summary(lines, server, trial, help_spec) -> dict:
    """One odd transcript must not lose the other trials' results."""
    try:
        return summarize(lines, server, trial, help_spec)
    except Exception as exc:  # noqa: BLE001
        return {"id": trial["id"], "question": trial.get("question", ""), "task": trial["task"], "events": [],
                "calls": 0, "help_reads": 0, "help_bytes": 0, "help_before_use": None, "rules": [], "errors": 0,
                "recovered": 0, "repeats": 0, "drafts": [], "tokens": 0, "cost_usd": None, "answer": "",
                "mcp_status": [], "status": f"could not read the transcript: {exc!r}", "invalid": True}


def resummarize(args) -> int:
    """Rebuild the trial summaries from transcripts already in DIR/trials/, without running anything."""
    out = Path(args.out)
    record = json.loads((out / "probe.json").read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    runs = []
    before = {r["id"]: r for r in (record.get("trials") or {}).get("runs") or []}
    found = []
    for trial in plan.get("trials") or []:
        paths = [out / "trials" / f"{trial['id']}.jsonl"] + sorted((out / "trials").glob(f"{trial['id']}#*.jsonl"))
        found += [(dict(trial, id=p.stem, base_id=trial["id"]), p) for p in paths if p.exists()]
    for trial, path in found:
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict):
                lines.append(msg)
        summary = safe_summary(lines, args.server, trial, plan.get("help") or {})
        if summary.get("mcp_status") and summary["mcp_status"] != ["connected"]:
            summary["invalid"] = True
        summary["base_id"] = trial["base_id"]
        for key in ("verify", "wall_ms", "attempt"):
            if key in (before.get(trial["id"]) or {}):
                summary[key] = before[trial["id"]][key]
        runs.append(summary)
    old = (record.get("trials") or {})
    record["trials"] = {"server": args.server, "writes": old.get("writes", "blocked"), "runs": sorted(runs, key=lambda r: r["id"])}
    probe.write_record(out, record)
    print(f"{len(runs)} trial transcripts summarized", file=sys.stderr)
    return 0


def run(args) -> int:
    out = Path(args.out)
    record_path = out / "probe.json"
    if not record_path.exists():
        raise probe.ProbeError(f"{record_path} is missing; run probe.py collect first")
    record = json.loads(record_path.read_text(encoding="utf-8"))
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    claude = shutil.which(args.claude)
    if not claude:
        raise probe.ProbeError(f"{args.claude} not found; agent trials need Claude Code on PATH")
    server = args.server
    reads = [t["name"] for t in record.get("tools") or [] if (t.get("annotations") or {}).get("readOnlyHint") is True]
    reads += [t for t in plan.get("confirmed_read_only") or []]
    allowed = [f"mcp__{server}__{n}" for n in reads] + CLIENT_TOOLS
    if args.allow_writes:
        allowed = [f"mcp__{server}"] + CLIENT_TOOLS
    help_spec = plan.get("help") or {}
    env = {k: v for k, v in os.environ.items() if k not in SESSION_ENV}
    # The user's own CLAUDE.md, AGENTS.md and memories must not steer the trial agent.
    env.update({"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})
    tdir = out / "trials"
    tdir.mkdir(parents=True, exist_ok=True)
    # Outside the home tree, so no parent directory contributes instruction files.
    work = Path(tempfile.mkdtemp(prefix="mcp-trial-", dir="/tmp" if os.path.isdir("/tmp") else None))
    runs = [r for r in (record.get("trials") or {}).get("runs") or []
            if args.only and r["id"].split("#")[0] not in args.only]
    # One run shows a behaviour, not a rate: repeat each trial to report "k of n".
    planned = []
    for trial in plan.get("trials") or []:
        if args.only and trial["id"] not in args.only:
            continue
        n = max(1, int(trial.get("repeat") or args.repeat))
        planned += [dict(trial, id=f"{trial['id']}#{k}" if n > 1 else trial["id"], base_id=trial["id"], attempt=k)
                    for k in range(1, n + 1)]
    for trial in planned:
        model = trial.get("model") or args.model
        cmd = [claude, "-p", trial["task"], "--output-format", "stream-json", "--verbose", "--model", model,
               "--no-session-persistence", "--strict-mcp-config", "--mcp-config", str(Path(args.mcp_config).resolve()),
               "--setting-sources", "", "--tools", ",".join(CLIENT_TOOLS),
               "--allowedTools", ",".join(allowed), "--max-budget-usd", str(args.max_budget)]
        if not args.allow_writes:
            cmd += ["--append-system-prompt", NOTE_BLOCKED]
        if args.before_each:
            # Every trial starts from the same sandbox state, or later trials see earlier trials' writes.
            subprocess.run(args.before_each, shell=True, check=True)
        print(f"{trial['id']}: running with {model} ...", file=sys.stderr)
        t0 = time.monotonic()
        try:
            proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=args.timeout)
            raw = proc.stdout
        except subprocess.TimeoutExpired as exc:
            raw = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        lines = []
        for line in raw.splitlines():
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict):  # stream-json can carry bare strings too
                lines.append(msg)
        with (tdir / f"{trial['id']}.jsonl").open("w", encoding="utf-8") as fh:
            for m in lines:
                fh.write(json.dumps(probe.scrub(m), ensure_ascii=False) + "\n")
        summary = safe_summary(lines, server, trial, help_spec)
        summary["wall_ms"] = int((time.monotonic() - t0) * 1000)
        summary["base_id"], summary["attempt"] = trial["base_id"], trial["attempt"]
        if trial.get("verify"):
            # Graded by the server's own parser or reads, not judged from the transcript.
            try:
                v = subprocess.run(trial["verify"], shell=True, capture_output=True, text=True, timeout=120)
                summary["verify"] = {"command": trial["verify"], "ok": v.returncode == 0,
                                     "output": probe.scrub_text((v.stdout + v.stderr).strip())[-600:]}
            except subprocess.TimeoutExpired:
                summary["verify"] = {"command": trial["verify"], "ok": False, "output": "timed out after 120 s"}
        if summary["mcp_status"] != ["connected"]:
            summary["status"] = f"server did not connect ({', '.join(map(str, summary['mcp_status'])) or 'no init'})"
            summary["invalid"] = True
            print(f"{trial['id']}: {summary['status']}; not scored", file=sys.stderr)
        runs.append(summary)
        record["trials"] = {"server": server, "writes": "allowed (sandbox)" if args.allow_writes else "blocked",
                            "runs": sorted(runs, key=lambda r: r["id"])}
        probe.write_record(out, record)
        hb = "-" if summary["help_before_use"] is None else "yes" if summary["help_before_use"] else "NO"
        print(f"{trial['id']}: {summary['calls']} calls, {summary['help_reads']} help reads "
              f"({summary['help_tokens']:,} tokens), help before use: {hb}, errors {summary['errors']}, "
              f"context {summary.get('context_start') or 0:,} -> {summary.get('context_peak') or 0:,} tokens, "
              f"${summary['cost_usd'] or 0:.3f}", file=sys.stderr)
    record["trials"] = {"server": server, "writes": "allowed (sandbox)" if args.allow_writes else "blocked",
                        "runs": sorted(runs, key=lambda r: r["id"])}
    probe.write_record(out, record)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("run", help="run the trials in a plan file")
    p.add_argument("--mcp-config", required=True, help="Claude Code MCP config JSON with this one server")
    p.add_argument("--server", required=True, help="the server's key in the MCP config")
    p.add_argument("--plan", required=True, help="trials.json")
    p.add_argument("--out", required=True, help="the run directory with probe.json")
    p.add_argument("--model", default="haiku", help="default model for trials (default: haiku)")
    p.add_argument("--only", nargs="*", help="run only these trial ids")
    p.add_argument("--repeat", type=int, default=1, help="runs per trial unless the trial sets repeat (default 1)")
    p.add_argument("--allow-writes", action="store_true", help="let write tools run (sandbox only)")
    p.add_argument("--before-each", help="shell command run before each trial, e.g. to restore the sandbox")
    p.add_argument("--max-budget", type=float, default=1.0, help="USD cap per trial (default 1.0)")
    p.add_argument("--timeout", type=int, default=600, help="seconds per trial (default 600)")
    p.add_argument("--claude", default="claude", help="Claude Code executable")
    r = sub.add_parser("summarize", help="rebuild summaries from DIR/trials/*.jsonl without running")
    r.add_argument("--server", required=True)
    r.add_argument("--plan", required=True)
    r.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    try:
        return run(args) if args.cmd == "run" else resummarize(args)
    except probe.ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
