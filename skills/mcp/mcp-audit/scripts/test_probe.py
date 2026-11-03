"""Tests for probe.py against two tiny stdio servers: a legacy one (initialize handshake) and a 2026-07-28 one
(server/discover, version in every request's _meta, no handshake).

  python -m unittest discover -s skills/mcp/mcp-audit/scripts -p "test_*.py"
"""

from __future__ import annotations

import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402

SERVER = r'''
import json, sys
ERA = sys.argv[1]
BIG = "x" * 300000
TOOLS = [
    {"name": "get_note", "description": "Read one note by id.", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "delete_note", "description": "Delete a note.", "annotations": {"readOnlyHint": True},
     "inputSchema": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
]
RESOURCES = [{"uri": "notes://help", "name": "help"}, {"uri": "notes://big", "name": "big"},
             {"uri": "db://customers/1", "name": "customer"}, {"uri": "notes://huge", "name": "huge", "size": 10**9}]
calls = []
def answer(req):
    m, p = req.get("method"), req.get("params") or {}
    if ERA == "modern":
        if m == "initialize":
            return {"error": {"code": -32601, "message": "initialize is not supported; use 2026-07-28"}}
        if (p.get("_meta") or {}).get("io.modelcontextprotocol/protocolVersion") != "2026-07-28":
            return {"error": {"code": -32022, "message": "Unsupported protocol version",
                              "data": {"supported": ["2026-07-28"]}}}
    if m == "server/discover":
        if ERA == "legacy":
            return {"error": {"code": -32601, "message": "Method not found"}}
        return {"result": {"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}, "resources": {}},
                           "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "notes", "version": "1.2.0"}}}}
    if m == "initialize":
        return {"result": {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}, "resources": {}},
                           "serverInfo": {"name": "notes", "version": "1.2.0"}}}
    if m == "ping":
        return {"result": {}}
    if m == "tools/list":
        return {"result": {"tools": TOOLS}}
    if m == "resources/list":
        return {"result": {"resources": RESOURCES}}
    if m in ("resources/templates/list", "prompts/list"):
        return {"result": {"resourceTemplates": [], "prompts": []}}
    if m == "resources/read":
        text = {"notes://help": "How to read notes.", "notes://big": BIG, "db://customers/1": "Jane, +1 555 0100"}.get(p.get("uri"))
        if text is None:
            return {"error": {"code": -32002, "message": "Resource not found"}}
        return {"result": {"contents": [{"uri": p["uri"], "mimeType": "text/plain", "text": text}]}}
    if m == "tools/call":
        calls.append(p.get("name"))
        sys.stderr.write("CALLED " + p.get("name") + "\n")
        args = p.get("arguments") or {}
        if not isinstance(args.get("id"), str):
            return {"result": {"isError": True, "content": [{"type": "text", "text": "id must be a string"}]}}
        return {"result": {"content": [{"type": "text", "text": "note " + args["id"]}]}}
    return {"error": {"code": -32601, "message": "Method not found"}}
for line in sys.stdin:
    try:
        req = json.loads(line)
    except ValueError:
        print(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}), flush=True)
        continue
    if "id" not in req:
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": req["id"], **answer(req)}), flush=True)
'''


class ProbeEras(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "server.py").write_text(SERVER, encoding="utf-8")
        probe.set_retention(64 * 1024, True)

    def command(self, era: str) -> str:
        return f"{shlex.quote(sys.executable)} {shlex.quote(str(self.tmp / 'server.py'))} {era}"

    def collect(self, era: str, *extra: str) -> dict:
        out = self.tmp / era
        rc = probe.main(["collect", "--command", self.command(era), "--out", str(out), "--start-timeout", "10",
                         "--label", "notes", "--package", "notes@1.2.0", "--max-keep-bytes", str(64 * 1024), *extra])
        self.assertEqual(rc, 0)
        return json.loads((out / "probe.json").read_text(encoding="utf-8"))

    def call(self, era: str, calls: list[dict]) -> dict:
        out = self.tmp / era
        plan = self.tmp / f"{era}-calls.json"
        plan.write_text(json.dumps({"calls": calls}), encoding="utf-8")
        rc = probe.main(["call", "--command", self.command(era), "--out", str(out), "--calls", str(plan),
                         "--start-timeout", "10"])
        self.assertEqual(rc, 0)
        return json.loads((out / "probe.json").read_text(encoding="utf-8"))

    def test_modern_only_server_is_collected_and_called_without_a_handshake(self):
        rec = self.collect("modern")
        self.assertEqual(rec["lifecycle"], "modern")
        self.assertEqual(rec["initialize"]["serverInfo"], {"name": "notes", "version": "1.2.0"})
        rec = self.call("modern", [{"tool": "get_note", "arguments": {"id": "a"}, "confirmed_read_only": True}])
        self.assertEqual(rec["calls"][0]["text_head"], "note a")
        self.assertEqual(len(rec["probes"]["invalid_arguments"]), 1)

    def test_legacy_server_still_works(self):
        rec = self.collect("legacy")
        self.assertEqual(rec["lifecycle"], "legacy")
        rec = self.call("legacy", [{"tool": "get_note", "arguments": {"id": "a"}, "confirmed_read_only": True}])
        self.assertEqual(rec["calls"][0]["text_head"], "note a")

    def test_collect_calls_no_tool_and_call_needs_confirmation(self):
        rec = self.collect("legacy")
        # delete_note claims readOnlyHint; collect must not call it, nor get_note.
        self.assertEqual(rec["probes"]["invalid_arguments"], [])
        tail = "\n".join(rec.get("stderr_tail") or [])
        self.assertNotIn("CALLED get_note", tail)
        self.assertNotIn("CALLED delete_note", tail)
        rec = self.call("legacy", [{"tool": "delete_note", "arguments": {"id": "a"}}])
        self.assertIn("not confirmed as a read", rec["calls"][0]["skipped"])
        self.assertEqual(rec["probes"]["invalid_arguments"], [])

    def test_reads_are_capped_and_skippable(self):
        rec = self.collect("legacy", "--skip", "db://customers/*")
        reads = {r["uri"]: r for r in rec["resource_reads"]}
        self.assertEqual(reads["notes://help"]["text"], "How to read notes.")
        self.assertTrue(reads["notes://big"]["truncated"])
        self.assertEqual(reads["notes://big"]["text_bytes"], 300000)
        self.assertEqual(len(reads["notes://big"]["text"]), 64 * 1024)
        self.assertIn("--skip", reads["db://customers/1"]["skipped"])
        self.assertNotIn("text", reads["db://customers/1"])
        self.assertIn("declares", reads["notes://huge"]["skipped"])
        transcript = (self.tmp / "legacy" / "transcript.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("Jane", transcript)
        self.assertLess(max(len(line) for line in transcript.splitlines()), 64 * 1024 + 200)

    def test_no_transcripts(self):
        self.collect("legacy", "--no-transcripts")
        self.assertEqual(list((self.tmp / "legacy").glob("transcript*.jsonl")), [])
        self.assertTrue((self.tmp / "legacy" / "probe.json").exists())


if __name__ == "__main__":
    unittest.main()
