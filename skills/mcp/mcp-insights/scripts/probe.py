#!/usr/bin/env python3
"""Probe one MCP server and record everything an agent would see.

Subcommands:
  collect  start or connect to the server, list everything, send safe error
           probes, write DIR/probe.json and DIR/transcript.jsonl
  call     run the read-only calls in a calls.json file and add the results
           to DIR/probe.json
  import   build DIR/probe.json from the tool definitions a client shows the
           model, for a hosted server the probe cannot reach itself (a
           connector behind the client's own sign-in); optionally add calls
           made through that client

Standard library only. Talks stdio (newline-delimited JSON-RPC) or
Streamable HTTP (JSON or SSE responses).
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PROBE_VERSION = "0.3"
TOKEN_ESTIMATOR = "chars-2026-10-21"  # see estimate_tokens
CLIENT_INFO = {"name": "mcp-insights", "version": PROBE_VERSION}
REQUESTED_VERSION = "2025-11-25"
MODERN_VERSION = "2026-07-28"
META_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CAPS = "io.modelcontextprotocol/clientCapabilities"
KNOWN_VERSIONS = ["2026-07-28", "2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
LIST_PAGE_LIMIT = 50
RESOURCE_READ_LIMIT = 200


class ProbeError(Exception):
    pass


# Secrets never reach disk. Every string is scrubbed before probe.json or a
# transcript is written; probe.json keeps only the name, place and length.
SECRET_FORMATS = [
    ("aws-access-key", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    ("github-token", r"\bgh[pousr]_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{40,}"),
    ("slack-token", r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    ("api-key", r"\bsk-(?:ant-|proj-|lf-)?[A-Za-z0-9_-]{20,}|\b[sr]k_live_[A-Za-z0-9]{20,}|\bNRAK-[A-Z0-9]{20,}"),
    ("google-api-key", r"\bAIza[0-9A-Za-z_-]{35}"),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    ("jwt", r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    ("bearer-token", r"(?<=Bearer )[A-Za-z0-9._~+/-]{20,}=*"),
    ("url-password", r"(?<=://)[^/\s:@]+:[^@\s/]{3,}(?=@)"),
]
SECRET_ASSIGN = re.compile(
    r"""(?ix)(["']?)\b([A-Z0-9_.-]*(?:SECRET|PASSWORD|PASSWD|PASSPHRASE|TOKEN|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIALS?|AUTH[_-]?KEY|DSN)[A-Z0-9_.-]*)\1
        (\s*[=:]\s*)(["']?)(?!\[REDACTED)([^\s"'`,;]{8,})\4""")
SECRET_KEY = re.compile(r"(?i)[A-Z0-9_.-]*(?:SECRET|PASSWORD|PASSWD|PASSPHRASE|TOKEN|API[_-]?KEY|ACCESS[_-]?KEY|PRIVATE[_-]?KEY|CREDENTIALS?|AUTH[_-]?KEY|DSN)[A-Z0-9_.-]*")
PLACEHOLDER = re.compile(r"(?i)^(?:x+|\*+|\.+|<[^>]*>|\$\{[^}]*\}|\$[A-Z_]+|\{\{[^}]*\}\}|(?:your|my|example|dummy|fake|test|sample)[-_].*"
                         r"|changeme|change_me|placeholder|redacted.*|null|none|true|false|string|number|integer|boolean)$")


def entropy(s: str) -> float:
    import math
    counts: dict = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    return -sum(n / len(s) * math.log2(n / len(s)) for n in counts.values()) if s else 0.0


def likely_real(value: str) -> bool:
    return len(value) >= 12 and entropy(value) >= 3.0 and bool(re.search(r"[A-Za-z]", value)) and bool(re.search(r"\d", value))


def scrub_text(text: str, found: list | None = None, where: str = "") -> str:
    def note(name, kind, value):
        if found is not None:
            found.append({"where": where, "name": name, "kind": kind, "length": len(value), "likely_real": likely_real(value)})

    for kind, pat in SECRET_FORMATS:
        def repl(mt, kind=kind):
            if PLACEHOLDER.match(mt.group(0)) or entropy(mt.group(0)) < 2.5:
                return mt.group(0)
            note(kind, kind, mt.group(0))
            return f"[REDACTED:{kind}]"
        text = re.sub(pat, repl, text)

    def assign(mt):
        quote, name, sep, vq, value = mt.groups()
        if PLACEHOLDER.match(value) or re.fullmatch(r"\d+", value) or re.search(r"(?i)page|cursor|next|max|count|limit|usage", name):
            return mt.group(0)
        note(name, "assignment", value)
        return f"{quote}{name}{quote}{sep}{vq}[REDACTED:{name} len={len(value)}]{vq}"
    return SECRET_ASSIGN.sub(assign, text)


# The probe's own fields, written by us rather than the server; "token_estimator" looks like a secret by name.
OWN_KEYS = {"probe_version", "token_estimator", "collected_at", "source"}


def scrub(obj, found: list | None = None, path: str = ""):
    if isinstance(obj, str):
        return scrub_text(obj, found, path)
    if isinstance(obj, list):
        return [scrub(v, found, f"{path}[{i}]") for i, v in enumerate(obj)]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            sub = f"{path}.{k}" if path else k
            if k == "secrets" or (not path and k in OWN_KEYS):
                out[k] = v
            elif isinstance(v, str) and SECRET_KEY.fullmatch(k) and not re.search(r"(?i)page|cursor|next|max|count|limit|usage", k) \
                    and len(v) >= 8 and not PLACEHOLDER.match(v) and not v.startswith("[REDACTED"):
                if found is not None:
                    found.append({"where": sub, "name": k, "kind": "field", "length": len(v), "likely_real": likely_real(v)})
                out[k] = f"[REDACTED:{k} len={len(v)}]"
            else:
                out[k] = scrub(v, found, sub)
        return out
    return obj


class Transcript:
    def __init__(self, path: Path | None):
        self.fh = path.open("a", encoding="utf-8") if path else None

    def write(self, direction: str, payload) -> None:
        if not self.fh:
            return
        self.fh.write(json.dumps(scrub({"t": round(time.time(), 3), "dir": direction, "msg": payload})) + "\n")
        self.fh.flush()


class StdioConnection:
    def __init__(self, command: str, cwd: str | None, env: dict, transcript: Transcript):
        self.transcript = transcript
        self.started = time.monotonic()
        self.proc = subprocess.Popen(
            command if os.name == "nt" else shlex.split(command),
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        self.messages: queue.Queue = queue.Queue()
        self.noise: list[str] = []
        self.stderr_lines: list[str] = []
        self.next_id = 1
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.proc.stdout
        for raw in iter(self.proc.stdout.readline, b""):
            line = raw.decode("utf-8", "replace").rstrip("\r\n")
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                self.noise.append(line[:500])
                self.transcript.write("noise", line[:500])
                continue
            self.transcript.write("in", msg)
            self.messages.put(msg)
        self.messages.put(None)

    def _read_stderr(self) -> None:
        assert self.proc.stderr
        for raw in iter(self.proc.stderr.readline, b""):
            if len(self.stderr_lines) < 400:
                self.stderr_lines.append(raw.decode("utf-8", "replace").rstrip()[:500])

    def alive(self) -> bool:
        return self.proc.poll() is None

    def send_raw(self, text: str) -> None:
        assert self.proc.stdin
        self.transcript.write("out-raw", text)
        self.proc.stdin.write((text + "\n").encode("utf-8"))
        self.proc.stdin.flush()

    def notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.transcript.write("out", msg)
        self.send_raw(json.dumps(msg))

    def request(self, method: str, params: dict | None = None, timeout: float = 30, raw_id=None):
        """Return (message, elapsed_ms). message is the response, or None on timeout."""
        req_id = raw_id if raw_id is not None else self.next_id
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if getattr(self, "meta", None):
            params = dict(params or {})
            params["_meta"] = {**self.meta, **(params.get("_meta") or {})}
        if params is not None:
            msg["params"] = params
        self.transcript.write("out", msg)
        start = time.monotonic()
        try:
            self.send_raw(json.dumps(msg))
        except (BrokenPipeError, OSError):
            return None, 0
        return self._wait(req_id, start, timeout)

    def wait_any_response(self, timeout: float):
        start = time.monotonic()
        return self._wait(None, start, timeout)

    def _wait(self, req_id, start: float, timeout: float):
        deadline = start + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, int((time.monotonic() - start) * 1000)
            try:
                msg = self.messages.get(timeout=remaining)
            except queue.Empty:
                return None, int((time.monotonic() - start) * 1000)
            if msg is None:
                return None, int((time.monotonic() - start) * 1000)
            if "method" in msg and "id" in msg:
                # A server-to-client request (sampling, roots, elicitation): decline it.
                self.send_raw(json.dumps({"jsonrpc": "2.0", "id": msg["id"],
                                          "error": {"code": -32601, "message": "not supported by mcp-insights"}}))
                continue
            if "method" in msg:
                continue  # notification
            if req_id is None or msg.get("id") == req_id:
                return msg, int((time.monotonic() - start) * 1000)

    def close(self) -> None:
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class HttpConnection:
    def __init__(self, url: str, headers: dict, transcript: Transcript):
        self.url = url
        self.headers = headers
        self.transcript = transcript
        self.session_id = None
        self.protocol_version = None
        self.next_id = 1
        self.noise: list[str] = []
        self.stderr_lines: list[str] = []
        self.started = time.monotonic()
        self.last_status = None

    def alive(self) -> bool:
        return True

    def _post(self, body: str, timeout: float, extra_headers: dict | None = None):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        headers.update(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(self.url, data=body.encode("utf-8"), headers=headers, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            status, rheaders, data = resp.status, resp.headers, resp.read()
        except urllib.error.HTTPError as exc:
            status, rheaders, data = exc.code, exc.headers, exc.read()
        self.last_status = status
        sid = rheaders.get("Mcp-Session-Id") if rheaders else None
        if sid:
            self.session_id = sid
        ctype = (rheaders.get("Content-Type") or "") if rheaders else ""
        text = data.decode("utf-8", "replace")
        messages = []
        if "text/event-stream" in ctype:
            for block in re.split(r"\r?\n\r?\n", text):
                payload = "\n".join(l[5:].lstrip() for l in block.splitlines() if l.startswith("data:"))
                if payload:
                    try:
                        messages.append(json.loads(payload))
                    except json.JSONDecodeError:
                        self.noise.append(payload[:500])
        elif text.strip():
            try:
                parsed = json.loads(text)
                messages.extend(parsed if isinstance(parsed, list) else [parsed])
            except json.JSONDecodeError:
                self.noise.append(text[:500])
        return status, messages

    def send_raw(self, text: str) -> None:
        self.transcript.write("out-raw", text)
        self._raw_result = self._post(text, 30)

    def notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self.transcript.write("out", msg)
        try:
            self._post(json.dumps(msg), 30)
        except (urllib.error.URLError, OSError):
            pass

    def request(self, method: str, params: dict | None = None, timeout: float = 30, raw_id=None):
        req_id = raw_id if raw_id is not None else self.next_id
        self.next_id += 1
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if getattr(self, "meta", None):
            params = dict(params or {})
            params["_meta"] = {**self.meta, **(params.get("_meta") or {})}
        if params is not None:
            msg["params"] = params
        self.transcript.write("out", msg)
        start = time.monotonic()
        try:
            status, messages = self._post(json.dumps(msg), timeout)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            self.transcript.write("error", str(exc))
            return None, int((time.monotonic() - start) * 1000)
        elapsed = int((time.monotonic() - start) * 1000)
        for m in messages:
            self.transcript.write("in", m)
        for m in messages:
            if isinstance(m, dict) and m.get("id") == req_id and "method" not in m:
                return m, elapsed
        return None, elapsed

    def wait_any_response(self, timeout: float):
        status, messages = getattr(self, "_raw_result", (None, []))
        for m in messages:
            if isinstance(m, dict) and ("result" in m or "error" in m):
                return m, 0
        return None, 0

    def close(self) -> None:
        if self.session_id:
            headers = dict(self.headers)
            headers["Mcp-Session-Id"] = self.session_id
            req = urllib.request.Request(self.url, headers=headers, method="DELETE")
            try:
                urllib.request.urlopen(req, timeout=5)
            except (urllib.error.URLError, OSError):
                pass


def open_connection(args, transcript: Transcript):
    if args.url:
        headers = {}
        for h in args.header or []:
            if ":" not in h:
                raise ProbeError(f"--header must look like 'Name: value', got {h!r}")
            name, value = h.split(":", 1)
            headers[name.strip()] = value.strip()
        return HttpConnection(args.url, headers, transcript)
    env = dict(os.environ)
    for e in args.env or []:
        if "=" not in e:
            raise ProbeError(f"--env must look like NAME=value, got {e!r}")
        k, v = e.split("=", 1)
        env[k] = v
    return StdioConnection(args.command, args.cwd, env, transcript)


def initialize(conn, version: str = REQUESTED_VERSION, timeout: float = 60):
    msg, ms = conn.request("initialize", {
        "protocolVersion": version,
        "capabilities": {},
        "clientInfo": CLIENT_INFO,
    }, timeout=timeout)
    return msg, ms


def error_of(msg):
    if msg is None:
        return {"kind": "timeout"}
    if "error" in msg:
        err = msg["error"] or {}
        return {"kind": "protocol", "code": err.get("code"), "message": str(err.get("message", ""))[:2000],
                "data": err.get("data")}
    res = msg.get("result") or {}
    if isinstance(res, dict) and res.get("isError"):
        return {"kind": "tool", "message": content_text(res)[:2000]}
    return None


def content_text(result) -> str:
    parts = []
    for c in (result or {}).get("content") or []:
        if isinstance(c, dict) and c.get("type") == "text":
            parts.append(str(c.get("text", "")))
    return "\n".join(parts)


def list_all(conn, method: str, key: str):
    items, pages, cursors_seen, error = [], 0, set(), None
    cursor = None
    cache = None
    repeated = False
    while pages < LIST_PAGE_LIMIT:
        params = {"cursor": cursor} if cursor else {}
        msg, ms = conn.request(method, params)
        pages += 1
        if msg is None or "error" in msg:
            error = error_of(msg)
            break
        res = msg.get("result") or {}
        if cache is None:
            cache = {"ttlMs": res.get("ttlMs"), "cacheScope": res.get("cacheScope")}
        items.extend(res.get(key) or [])
        cursor = res.get("nextCursor")
        if not cursor:
            break
        if cursor in cursors_seen:
            repeated = True  # the server would page forever
            break
        cursors_seen.add(cursor)
    # Hitting the page limit with a cursor still pending means the list was cut short here.
    return {"items": items, "pages": pages, "error": error, "cache": cache, "repeated_cursor": repeated,
            "page_limit_hit": bool(cursor) and not repeated and pages >= LIST_PAGE_LIMIT}


def size(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def estimate_tokens(text: str) -> int:
    """Claude input tokens for a text, from its character classes.

    Fitted 2026-10-21 on 33 texts (tool lists, descriptions, instructions, help
    topics; 360 to 31,000 tokens) counted by Claude Haiku and Sonnet, which
    share a tokenizer (Opus too): mean error 5%, worst 13%. Bytes alone miss by up to 30%,
    because JSON and indented text cost more tokens per byte than prose.
    """
    if not text:
        return 0
    letters = sum(1 for c in text if c.isascii() and c.isalpha())
    digits = sum(1 for c in text if c.isascii() and c.isdigit())
    other = sum(1 for c in text if not c.isascii())
    breaks = text.count("\n")
    punct = sum(1 for c in text if c.isascii() and not c.isalnum() and not c.isspace() and c != "_")
    return round(0.35 * letters + 0.57 * punct + 0.68 * digits + 1.8 * breaks + other)


def minimal_invalid_args(tool: dict):
    """Arguments that break the tool's schema: drop every required field."""
    schema = tool.get("inputSchema") or {}
    required = schema.get("required") or []
    if required:
        return {}, f"missing required {', '.join(required)}"
    props = schema.get("properties") or {}
    for name, prop in props.items():
        if isinstance(prop, dict) and isinstance(prop.get("enum"), list) and all(isinstance(v, str) for v in prop["enum"]):
            return {name: "mcp-insights-not-an-option"}, f"{name} is not one of its enum values"
    for name, prop in props.items():
        t = prop.get("type") if isinstance(prop, dict) else None
        if t is None and isinstance(prop, dict):
            # pydantic writes Optional[str] as anyOf: [{type: string}, {type: null}]
            alts = [a.get("type") for a in prop.get("anyOf") or prop.get("oneOf") or [] if isinstance(a, dict)]
            t = [a for a in alts if isinstance(a, str)] or None
        if isinstance(t, list):
            t = next((x for x in t if x != "null"), None) if len(t) <= 2 else None
        if t in ("string", "number", "integer", "boolean", "array", "object"):
            wrong = {"string": 12345, "number": "not-a-number", "integer": "not-an-integer",
                     "boolean": "not-a-boolean", "array": "not-an-array", "object": "not-an-object"}[t]
            return {name: wrong}, f"{name} has the wrong type"
    if schema.get("additionalProperties") is False:
        return {"mcp_insights_unknown": 1}, "an unknown field where additionalProperties is false"
    return None, None


def source_revision(cwd: str | None, given: str | None) -> dict | None:
    """The commit the server was built from, so a run can be reproduced: --commit, or the git checkout in --cwd."""
    if given:
        return {"commit": given, "from": "--commit"}
    if not cwd:
        return None
    try:
        head = subprocess.run(["git", "-C", cwd, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        dirty = subprocess.run(["git", "-C", cwd, "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if head.returncode != 0:
        return None
    return {"commit": head.stdout.strip(), "dirty": bool(dirty.stdout.strip()), "from": "git"}


def collect(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    transcript = Transcript(out / "transcript.jsonl")
    record: dict = {
        "probe_version": PROBE_VERSION,
        "token_estimator": TOKEN_ESTIMATOR,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": {"transport": "http" if args.url else "stdio",
                   "command": args.command, "url": args.url, "cwd": args.cwd,
                   "label": args.label},
        "source": source_revision(args.cwd, args.commit),
        "probes": {},
    }
    probes = record["probes"]

    # 2026-07-28 servers are stateless: no initialize, every request carries
    # its version in _meta, and server/discover MUST work. Ask that first on a
    # fresh connection, as the spec suggests, then try the legacy handshake.
    discover = discover_first(args, out)
    probes["discover_first"] = discover

    conn = open_connection(args, transcript)
    try:
        init, init_ms = initialize(conn, timeout=args.start_timeout)
        record["cold_start_ms"] = int((time.monotonic() - conn.started) * 1000)
        record["initialize_ms"] = init_ms
        legacy_ok = bool(init and "result" in init)
        modern_ok = bool(discover.get("ok"))
        record["lifecycle"] = "dual" if legacy_ok and modern_ok else "legacy" if legacy_ok else "modern" if modern_ok else "none"
        if not legacy_ok and modern_ok:
            conn.close()
            conn = open_connection(args, transcript)
            conn.meta = {META_VERSION: MODERN_VERSION, META_CAPS: {}}
            if isinstance(conn, HttpConnection):
                conn.protocol_version = MODERN_VERSION
            dres = discover.get("result") or {}
            init = {"result": {"protocolVersion": MODERN_VERSION, "capabilities": dres.get("capabilities") or {},
                               "serverInfo": dres.get("serverInfo") or {}, "instructions": dres.get("instructions")}}
        if init is None or "error" in init:
            failure = error_of(init)
            if init is None and not conn.alive():
                failure = {"kind": "exited", "code": conn.proc.returncode}
            record["initialize"] = {"ok": False, "error": failure}
            record["stderr_tail"] = conn.stderr_lines[-40:]
            record["stdout_noise"] = conn.noise[:20]
            write_record(out, record)
            print(f"initialize failed: {json.dumps(failure)}; see stderr_tail in probe.json", file=sys.stderr)
            return 2
        res = init.get("result") or {}
        record["initialize"] = {
            "ok": True,
            "protocolVersion": res.get("protocolVersion"),
            "capabilities": res.get("capabilities") or {},
            "serverInfo": res.get("serverInfo") or {},
            "instructions": res.get("instructions"),
            "raw_bytes": size(res),
        }
        if isinstance(conn, HttpConnection) and not getattr(conn, "meta", None):
            conn.protocol_version = res.get("protocolVersion")
        if not getattr(conn, "meta", None):
            conn.notify("notifications/initialized")
        caps = record["initialize"]["capabilities"]

        msg, ms = conn.request("ping", {})
        probes["ping"] = {"ok": bool(msg and "result" in msg), "ms": ms, "error": error_of(msg) if not (msg and "result" in msg) else None}

        tools = list_all(conn, "tools/list", "tools")
        t0 = time.monotonic()
        again = list_all(conn, "tools/list", "tools")
        record["tools_list_ms"] = int((time.monotonic() - t0) * 1000)
        record["tools"] = tools["items"]
        probes["tools_list"] = {"declared": "tools" in caps, "pages": tools["pages"], "error": tools["error"], "cache": tools["cache"],
                                "repeated_cursor": tools["repeated_cursor"], "page_limit_hit": tools["page_limit_hit"],
                                "stable_order": [t.get("name") for t in tools["items"]] == [t.get("name") for t in again["items"]]}

        for method, key, cap in (("resources/list", "resources", "resources"),
                                 ("resources/templates/list", "resourceTemplates", "resources"),
                                 ("prompts/list", "prompts", "prompts")):
            got = list_all(conn, method, key)
            record[key] = got["items"]
            probes[method] = {"declared": cap in caps, "pages": got["pages"], "error": got["error"], "count": len(got["items"]),
                              "cache": got["cache"], "repeated_cursor": got["repeated_cursor"], "page_limit_hit": got["page_limit_hit"]}

        reads = []
        for r in record["resources"][:RESOURCE_READ_LIMIT]:
            uri = r.get("uri")
            msg, ms = conn.request("resources/read", {"uri": uri})
            entry = {"uri": uri, "ms": ms, "error": error_of(msg) if (msg is None or "error" in msg) else None}
            if msg and "result" in msg:
                contents = (msg["result"] or {}).get("contents") or []
                text = "\n".join(str(c.get("text", "")) for c in contents if isinstance(c, dict) and "text" in c)
                entry["bytes"] = size(msg["result"])
                entry["text_bytes"] = len(text.encode("utf-8"))
                entry["text"] = text
                entry["mimeTypes"] = sorted({str(c.get("mimeType")) for c in contents if isinstance(c, dict)})
            reads.append(entry)
        record["resource_reads"] = reads

        prompt_gets = []
        for p in record["prompts"]:
            required = [a.get("name") for a in (p.get("arguments") or []) if a.get("required")]
            if required:
                continue
            msg, ms = conn.request("prompts/get", {"name": p.get("name"), "arguments": {}})
            entry = {"name": p.get("name"), "ms": ms, "error": error_of(msg) if (msg is None or "error" in msg) else None}
            if msg and "result" in msg:
                entry["bytes"] = size(msg["result"])
                texts = []
                for m in (msg["result"] or {}).get("messages") or []:
                    c = m.get("content") if isinstance(m, dict) else None
                    if isinstance(c, dict) and c.get("type") == "text":
                        texts.append(str(c.get("text", "")))
                entry["text"] = "\n".join(texts)
            prompt_gets.append(entry)
        record["prompt_gets"] = prompt_gets

        msg, ms = conn.request("mcp-insights/no-such-method", {})
        probes["unknown_method"] = {"response": error_of(msg) or {"kind": "success"}}

        msg, ms = conn.request("tools/call", {"name": "mcp_insights_no_such_tool", "arguments": {}})
        probes["unknown_tool"] = {"response": error_of(msg) or {"kind": "success"}}

        invalid = []
        for tool in record["tools"]:
            ann = tool.get("annotations") or {}
            if ann.get("readOnlyHint") is not True:
                continue
            bad_args, why = minimal_invalid_args(tool)
            if bad_args is None:
                continue
            msg, ms = conn.request("tools/call", {"name": tool.get("name"), "arguments": bad_args})
            invalid.append({"tool": tool.get("name"), "arguments": bad_args, "why": why, "ms": ms,
                            "response": error_of(msg) or {"kind": "success", "text": content_text((msg or {}).get("result"))[:1000]}})
        probes["invalid_arguments"] = invalid

        msg, ms = conn.request("resources/read", {"uri": "mcp-insights://no-such-resource"})
        probes["resource_not_found"] = {"response": error_of(msg) or {"kind": "success"}}
        # A URI no template matches is answered by most SDKs before the server's code runs; one that fits a
        # template but names nothing reaches the server's own handler.
        templates = [t.get("uriTemplate") for t in record.get("resourceTemplates") or [] if t.get("uriTemplate")]
        if templates:
            uri = re.sub(r"\{[^}]*\}", "mcp-insights-no-such-item", templates[0])
            msg, ms = conn.request("resources/read", {"uri": uri})
            probes["resource_not_found_template"] = {"uri": uri, "response": error_of(msg) or {"kind": "success"}}

        if isinstance(conn, StdioConnection):
            conn.send_raw('{"jsonrpc": "2.0", "id": "mcp-insights-parse", "method": ')
            msg, ms = conn.wait_any_response(5)
            after, _ = conn.request("ping", {}, timeout=10)
            probes["parse_error"] = {"response": error_of(msg) if msg else {"kind": "timeout"},
                                     "alive_after": bool(after and "result" in after)}
        record["stdout_noise"] = conn.noise[:20]
        record["stderr_tail"] = conn.stderr_lines[-40:]
    finally:
        conn.close()

    # A second start with a version nobody supports: the server should answer
    # with one it does support (stdio only; HTTP reuses the URL).
    if record.get("lifecycle") in ("legacy", "dual"):
        conn2 = open_connection(args, Transcript(out / "transcript-version.jsonl"))
        try:
            msg, ms = initialize(conn2, "1999-01-01", timeout=args.start_timeout)
            probes["unknown_version"] = {"response": error_of(msg) or {"kind": "success",
                                                                       "protocolVersion": (msg.get("result") or {}).get("protocolVersion")}}
        finally:
            conn2.close()

    if args.url:
        probes["origin"] = probe_origin(args)

    write_record(out, record)
    print(summary_line(record))
    return 0


def discover_first(args, out: Path) -> dict:
    conn = open_connection(args, Transcript(out / "transcript-discover.jsonl"))
    found: dict = {"ok": False}
    try:
        meta = {META_VERSION: MODERN_VERSION, META_CAPS: {}}
        if isinstance(conn, HttpConnection):
            conn.protocol_version = MODERN_VERSION
        msg, ms = conn.request("server/discover", {"_meta": meta}, timeout=args.start_timeout)
        res = (msg or {}).get("result")
        if isinstance(res, dict) and (res.get("supportedVersions") or res.get("capabilities") is not None):
            found = {"ok": True, "ms": ms, "result": res,
                     "supportedVersions": res.get("supportedVersions"),
                     "cache": {"ttlMs": res.get("ttlMs"), "cacheScope": res.get("cacheScope")}}
            bad, _ = conn.request("tools/list", {"_meta": {META_VERSION: "1999-01-01", META_CAPS: {}}})
            found["unknown_version"] = error_of(bad) or {"kind": "success"}
        else:
            found["response"] = error_of(msg) or {"kind": "success", "note": "result without supportedVersions"}
    except (OSError, ValueError) as exc:
        found["response"] = {"kind": "error", "message": str(exc)[:300]}
    finally:
        conn.close()
    return found


def probe_origin(args):
    """A request from a foreign Origin should be refused.

    The configured headers go along, so a server that wants credentials judges the
    Origin and not the missing key; without them a 401 says nothing about Origin checks.
    """
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    auth = {}
    for h in args.header or []:
        name, _, value = h.partition(":")
        auth[name.strip()] = value.strip()
    headers.update(auth)
    headers["Origin"] = "https://evil.example"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                       "params": {"protocolVersion": REQUESTED_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO}})
    req = urllib.request.Request(args.url, data=body.encode(), headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return {"status": resp.status, "with_auth": bool(auth)}
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "with_auth": bool(auth)}
    except (urllib.error.URLError, OSError) as exc:
        return {"status": None, "error": str(exc), "with_auth": bool(auth)}


def summary_line(record) -> str:
    init = record.get("initialize") or {}
    info = init.get("serverInfo") or {}
    return (f"{info.get('name', '?')} {info.get('version', '')}: protocol {init.get('protocolVersion')}, "
            f"{len(record.get('tools') or [])} tools, {len(record.get('resources') or [])} resources, "
            f"{len(record.get('prompts') or [])} prompts, tool list {size(record.get('tools') or []) / 1024:.1f} KB")


def surface_of(record: dict, path: str) -> str:
    """Turn a JSON path like resource_reads[3].text into 'resource mise://env'."""
    mt = re.match(r"(resource_reads|prompt_gets|calls|tools|resources|prompts)\[(\d+)\]", path)
    if not mt:
        return path.split(".")[0].split("[")[0]
    item = (record.get(mt.group(1)) or [{}])[int(mt.group(2))]
    label = {"resource_reads": "resource", "prompt_gets": "prompt", "calls": "response of",
             "tools": "tool", "resources": "resource list", "prompts": "prompt list"}[mt.group(1)]
    return f"{label} {item.get('uri') or item.get('name') or item.get('tool') or mt.group(2)}"


def write_record(out: Path, record: dict) -> None:
    found: list = []
    clean = scrub(record, found)
    known = {(s["where"], s["name"]) for s in record.get("secrets") or []}
    for s in found:
        s["where"] = surface_of(record, s["where"])
        if (s["where"], s["name"]) not in known:
            known.add((s["where"], s["name"]))
            clean.setdefault("secrets", []).append(s)
    record.clear()
    record.update(clean)
    (out / "probe.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    real = [s for s in record.get("secrets") or [] if s["likely_real"]]
    if real:
        print(f"warning: {len(real)} likely secrets redacted from what the server returned: "
              + ", ".join(sorted({f"{s['name']} ({s['where']})" for s in real})), file=sys.stderr)


def call(args) -> int:
    out = Path(args.out)
    probe_path = out / "probe.json"
    if not probe_path.exists():
        raise ProbeError(f"{probe_path} is missing; run collect first")
    record = json.loads(probe_path.read_text(encoding="utf-8"))
    plan = json.loads(Path(args.calls).read_text(encoding="utf-8"))
    tools = {t.get("name"): t for t in record.get("tools") or []}
    transcript = Transcript(out / "transcript-calls.jsonl")
    conn = open_connection(args, transcript)
    results, write_probes = [], []
    try:
        init, _ = initialize(conn, timeout=args.start_timeout)
        if init is None or "error" in init:
            raise ProbeError(f"initialize failed: {error_of(init)}")
        if isinstance(conn, HttpConnection):
            conn.protocol_version = (init.get("result") or {}).get("protocolVersion")
        conn.notify("notifications/initialized")
        for c in plan.get("calls") or []:
            name = c.get("tool")
            tool = tools.get(name)
            if tool is None:
                results.append({"tool": name, "skipped": "not in the tool list"})
                continue
            if c.get("write_probe"):
                if not args.allow_writes:
                    results.append({"tool": name, "skipped": "write probe; run with --allow-writes against a sandbox"})
                else:
                    write_probes.append(write_probe(conn, c, tools))
                continue
            if (tool.get("annotations") or {}).get("readOnlyHint") is not True and not c.get("confirmed_read_only"):
                results.append({"tool": name, "skipped": "not marked read-only; set confirmed_read_only after checking"})
                continue
            msg, ms = conn.request("tools/call", {"name": name, "arguments": c.get("arguments") or {}}, timeout=60)
            entry = {"tool": name, "arguments": c.get("arguments") or {}, "purpose": c.get("purpose"), "ms": ms}
            if msg is None:
                entry["error"] = {"kind": "timeout"}
            elif "error" in msg:
                entry["error"] = error_of(msg)
            else:
                res = msg.get("result") or {}
                entry["bytes"] = size(res)
                entry["isError"] = bool(res.get("isError"))
                entry["content_types"] = sorted({str(x.get("type")) for x in res.get("content") or [] if isinstance(x, dict)})
                entry["has_structured"] = "structuredContent" in res
                text = content_text(res)
                entry["text_head"] = text[:1500]
                # What the model receives is the content text; structuredContent mirrors it for programs.
                entry["text_bytes"] = len(text.encode("utf-8"))
                entry["tokens"] = estimate_tokens(text)
                if tool.get("outputSchema") and "structuredContent" in res:
                    entry["schema_problems"] = validate(res["structuredContent"], tool["outputSchema"])[:10]
            results.append(entry)
        # Servers without annotations get no invalid-argument probes in collect;
        # the tools confirmed as reads here can take them now.
        probed = {x.get("tool") for x in (record.get("probes") or {}).get("invalid_arguments") or []}
        extra = []
        for name in dict.fromkeys(r["tool"] for r in results if "bytes" in r):
            tool = tools[name]
            if name in probed:
                continue
            bad_args, why = minimal_invalid_args(tool)
            if bad_args is None:
                continue
            msg, ms = conn.request("tools/call", {"name": name, "arguments": bad_args})
            extra.append({"tool": name, "arguments": bad_args, "why": why, "ms": ms,
                          "response": error_of(msg) or {"kind": "success", "text": content_text((msg or {}).get("result"))[:1000]}})
        record.setdefault("probes", {}).setdefault("invalid_arguments", []).extend(extra)
    finally:
        conn.close()
    record["calls"] = results
    if write_probes:
        record["write_probes"] = write_probes
    write_record(out, record)
    if write_probes:
        silent = sum(1 for w in write_probes if w.get("accepted") and not w.get("diagnostic"))
        print(f"{len(write_probes)} write probes; {silent} accepted without a word: read them back and judge E12")
    done = sum(1 for r in results if "bytes" in r)
    print(f"{done} of {len(results)} calls answered; largest {max([r.get('bytes', 0) for r in results] or [0]) / 1024:.1f} KB")
    return 0


def write_probe(conn, c: dict, tools: dict) -> dict:
    """A deliberately malformed write to a sandbox, then the read that shows what was stored (E12)."""
    msg, ms = conn.request("tools/call", {"name": c["tool"], "arguments": c.get("arguments") or {}}, timeout=60)
    res = (msg or {}).get("result") or {}
    text = content_text(res) if res else ""
    entry = {"tool": c["tool"], "arguments": c.get("arguments") or {}, "purpose": c.get("purpose"), "expect": c.get("expect"),
             "ms": ms, "accepted": bool(msg) and "error" not in msg and not res.get("isError"),
             "response": error_of(msg) if msg and "error" in msg else {"isError": bool(res.get("isError")), "text": text[:2000]}}
    # A write that went through but says what it changed or dropped is not silent.
    entry["diagnostic"] = bool(re.search(r"(?i)warn|ignored|dropped|truncat|skipped|invalid|extra|unknown", text)) if entry["accepted"] else None
    back = c.get("read_back")
    if back:
        rb = tools.get(back.get("tool")) or {}
        if (rb.get("annotations") or {}).get("readOnlyHint") is not True and not back.get("confirmed_read_only"):
            entry["read_back"] = {"skipped": "read_back tool is not marked read-only"}
        else:
            m2, _ = conn.request("tools/call", {"name": back["tool"], "arguments": back.get("arguments") or {}}, timeout=60)
            r2 = (m2 or {}).get("result") or {}
            entry["read_back"] = {"tool": back["tool"], "arguments": back.get("arguments") or {},
                                  "text": content_text(r2)[:4000] if r2 else "", "error": error_of(m2) if m2 and "error" in m2 else None}
    return entry


def validate(value, schema, path="$"):
    """A small JSON Schema subset: type, required, properties, items, enum."""
    problems = []
    if not isinstance(schema, dict):
        return problems
    t = schema.get("type")
    types = t if isinstance(t, list) else [t] if t else []
    pytypes = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if types:
        ok = False
        for ty in types:
            if ty in ("number", "integer"):
                ok = ok or (isinstance(value, (int, float)) and not isinstance(value, bool))
            elif ty in pytypes:
                ok = ok or isinstance(value, pytypes[ty])
        if not ok:
            return [f"{path}: expected {'/'.join(types)}"]
    if "enum" in schema and value not in schema["enum"]:
        problems.append(f"{path}: not one of the enum values")
    if isinstance(value, dict):
        for req in schema.get("required") or []:
            if req not in value:
                problems.append(f"{path}.{req}: required but missing")
        for k, sub in (schema.get("properties") or {}).items():
            if k in value:
                problems.extend(validate(value[k], sub, f"{path}.{k}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for i, item in enumerate(value[:50]):
            problems.extend(validate(item, schema["items"], f"{path}[{i}]"))
    return problems


ERROR_HEAD = re.compile(r"(?i)(error\b|http \d{3}\b(?<!http 200)|failed\b|exception\b|unauthorized|forbidden|not found)")


def load_lines(path: Path) -> list:
    """A JSON array, an object with "tools" or "calls", or one JSON object per line."""
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("["):
        return json.loads(text)
    if text.startswith("{") and "\n" not in text:
        obj = json.loads(text)
        return obj.get("tools") or obj.get("calls") or [obj]
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def import_catalog(args) -> int:
    """Record what a client shows the model. Everything on the wire (handshake, versions,
    annotations, output schemas, error codes) stays unknown and the report says so."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tools = []
    for d in load_lines(Path(args.tools)):
        name = str(d.get("name", ""))
        if args.strip_prefix and name.startswith(args.strip_prefix):
            name = name[len(args.strip_prefix):]
        tool = {"name": name, "description": d.get("description") or "",
                "inputSchema": d.get("inputSchema") or d.get("parameters") or d.get("input_schema") or {}}
        for key in ("title", "annotations", "outputSchema"):
            if key in d:
                tool[key] = d[key]
        tools.append(tool)
    record: dict = {
        "probe_version": PROBE_VERSION, "token_estimator": TOKEN_ESTIMATOR,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target": {"transport": "client", "label": args.label, "via": args.via},
        "initialize": {"ok": True, "seen_through_client": True, "serverInfo": {"name": args.label},
                       "instructions": Path(args.instructions).read_text(encoding="utf-8").strip() if args.instructions else None},
        "tools": tools, "resources": [], "resourceTemplates": [], "prompts": [], "probes": {},
    }
    calls, invalid = [], []
    for c in load_lines(Path(args.calls)) if args.calls else []:
        text = str(c.get("text") or "")
        is_error = bool(c.get("is_error"))
        if c.get("why"):
            # An argument the schema forbids: did the server refuse it, and say which field?
            invalid.append({"tool": c["tool"], "arguments": c.get("arguments") or {}, "why": c["why"],
                            "response": {"kind": "client" if is_error else "success", "message": text[:600] if is_error else ""}})
            continue
        entry = {"tool": c["tool"], "arguments": c.get("arguments") or {}, "purpose": c.get("purpose"),
                 "bytes": len(text.encode("utf-8")), "text_bytes": len(text.encode("utf-8")),
                 "tokens": estimate_tokens(text), "isError": is_error, "via_client": True}
        # Keep the body only when it is an error: a read's content is the user's data, not the server's text.
        if is_error or ERROR_HEAD.match(text[:120]):
            entry["text_head"] = text[:600]
        calls.append(entry)
    if calls:
        record["calls"] = calls
    if invalid:
        record["probes"]["invalid_arguments"] = invalid
    write_record(out, record)
    print(f"{args.label}: {len(tools)} tools from the client, {len(calls)} calls, {len(invalid)} invalid-argument probes")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("collect", "call"):
        p = sub.add_parser(name)
        target = p.add_mutually_exclusive_group(required=True)
        target.add_argument("--command", help="stdio server command, e.g. 'npx -y @scope/server'")
        target.add_argument("--url", help="Streamable HTTP endpoint")
        p.add_argument("--cwd", help="working directory for a stdio server")
        p.add_argument("--env", action="append", help="NAME=value for a stdio server (repeatable)")
        p.add_argument("--header", action="append", help="'Name: value' for an HTTP server (repeatable)")
        p.add_argument("--out", required=True, help="directory for probe.json and transcripts")
        p.add_argument("--start-timeout", type=float, default=60, help="seconds to wait for initialize")
        if name == "collect":
            p.add_argument("--label", help="a short name for the server in the report")
            p.add_argument("--commit", help="the commit the server was built from, when --cwd is not its git checkout")
        else:
            p.add_argument("--calls", required=True, help="calls.json written by the agent")
            p.add_argument("--allow-writes", action="store_true",
                           help="run calls marked write_probe (sandbox only): malformed writes and the read that shows what was stored")
    p = sub.add_parser("import")
    p.add_argument("--tools", required=True, help="tool definitions as the client shows them (JSON array or JSON lines)")
    p.add_argument("--label", required=True, help="a short name for the server in the report")
    p.add_argument("--via", default="the client", help="how the tools were seen, e.g. 'Claude connector'")
    p.add_argument("--strip-prefix", help="client prefix to drop from tool names, e.g. mcp__Gmail__")
    p.add_argument("--instructions", help="file with the server instructions the client showed, if any")
    p.add_argument("--calls", help="calls made through the client: JSON lines with tool, arguments, text, is_error, "
                                   "and why for an invalid-argument probe")
    p.add_argument("--out", required=True, help="directory for probe.json")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "import":
            return import_catalog(args)
        return collect(args) if args.cmd == "collect" else call(args)
    except ProbeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"error: cannot start the server: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
