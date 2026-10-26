"""UNIT tests for arm B/C one-attempt runners against the real audited fixture.

opencli and pomerado-mcp are replaced by tiny fake executables, so these prove the
receipt/oracle/fail-closed logic only. They are not runtime evidence for either tool.
"""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from threading import Thread
import unittest
from urllib.request import urlopen

from analyze_receipts import summarize
import audit_fixture
import run_arm_b
import run_arm_c

PY = sys.executable
FAKE_OPENCLI = r'''
import json, sys, os, urllib.request, urllib.parse
a = sys.argv[1:]
mode = os.environ.get("FAKE_MODE", "ok")
assert os.environ.get("OPENCLI_CDP_ENDPOINT", "").startswith("http://127.0.0.1:")
if mode == "crash": sys.exit(3)
origin = a[a.index("--origin") + 1]
if a[1] == "read-status":
    if mode == "mutate":  # a misbehaving adapter that writes during a read task
        urllib.request.urlopen(urllib.request.Request(origin + "/submit", data=b"value=x", method="POST"))
    html = urllib.request.urlopen(origin + "/").read().decode()
    status = html.split("<output>")[1].split("</output>")[0]
    print(json.dumps([{"url": origin + "/", "status": status}]))
else:
    value = a[a.index("--value") + 1]
    n = 2 if mode == "double" else 1
    for _ in range(n):
        urllib.request.urlopen(urllib.request.Request(origin + "/submit",
            data=urllib.parse.urlencode({"value": value}).encode(), method="POST"))
    if mode == "late-fail": sys.exit(4)
    print(json.dumps([{"url": origin + "/submit", "status": "status=submitted:" + value}]))
'''
FAKE_MCP = r'''
import json, sys, os, urllib.request, urllib.parse
mode = os.environ.get("FAKE_MODE", "ok")
base = os.environ["FAKE_BASE"]
annotations = {"readOnlyHint": mode != "writable"}
for line in sys.stdin:
    m = json.loads(line)
    if "id" not in m: continue
    method = m["method"]
    if method == "initialize":
        r = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "1"}}
    elif method == "tools/list":
        r = {"tools": [{"name": "get_job", "inputSchema": {}, "annotations": {"readOnlyHint": True}},
                       {"name": "read_status", "inputSchema": {}, "annotations": annotations}]}
    elif method == "tools/call":
        p = m["params"]
        if p["name"] == "read_status":
            if mode == "job":
                r = {"structuredContent": {"status": "running", "job_id": "11111111-1111-4111-8111-111111111111"}, "content": []}
            elif mode == "stall":
                r = {"structuredContent": {"status": "needs_input", "job_id": "x"}, "content": []}
            else:
                html = urllib.request.urlopen(base + "/").read().decode()
                out = {"status": html.split("<output>")[1].split("</output>")[0]}
                r = {"structuredContent": out, "content": [{"type": "text", "text": json.dumps(out)}]}
        else:  # get_job
            out = {"status": "completed", "job_id": p["arguments"]["job_id"], "output": {"status": "status=waiting"}}
            r = {"structuredContent": out, "content": []}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": r}) + "\n"); sys.stdout.flush()
'''


def exe(directory: Path, name: str, source: str) -> str:
    path = directory / name
    path.write_text(f"#!{PY}\n{source}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.dir = Path(self.tmp.name)
        self.server = audit_fixture.AuditedFixtureServer(("127.0.0.1", 0))
        Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.out = self.dir / "r.jsonl"
        self.pins = ["--fixture-sha", "a" * 40, "--caller-sha", "b" * 40, "--driver-sha", "c" * 40,
                     "--pomerado-sha", "d" * 40, "--browser-version", "Chromium-test"]
        self.common = ["--base", self.base, "--block-id", "blk", "--position", "1",
                       "--out", str(self.out), "--timeout", "20", "--mint-ms", "123", *self.pins]
        os.environ["FAKE_BASE"] = self.base
        os.environ.pop("FAKE_MODE", None)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()
        os.environ.pop("FAKE_MODE", None)

    def receipt(self):
        return json.loads(self.out.read_text().splitlines()[-1])

    def audit(self):
        return json.load(urlopen(self.base + "/audit"))["commit_count"]


class ArmC(Fixture):
    def run_c(self, *extra, mode="ok"):
        os.environ["FAKE_MODE"] = mode
        cli = exe(self.dir, "opencli", FAKE_OPENCLI)
        return run_arm_c.main([*self.common, "--cdp-endpoint", "http://127.0.0.1:9", "--opencli-cmd",
                               cli, "--opencli-sha", "e" * 40, *extra])

    def test_read_receipt_verified_and_fits_schema(self):
        self.assertEqual(self.run_c(), 0)
        r = self.receipt()
        self.assertEqual((r["arm"], r["route_observed"], r["oracle_outcome"]),
                         ("C", "opencli-adapter-cdp", "verified"))
        self.assertEqual((r["audit_before"], r["audit_after"], r["model_calls"]), (0, 0, 0))
        self.assertEqual(r["mint_ms"], 123.0)
        self.assertGreater(r["elapsed_ms"], 0)
        self.assertTrue(r["route_evidence"].startswith("opencli-adapter-cdp:read:exit=0"))

    def test_receipts_pass_the_analyzer_validator(self):
        rows = []
        for n, order in enumerate(("ACCA", "CAAC")):
            for pos, arm in enumerate(order, 1):
                self.out.unlink(missing_ok=True)
                self.common[self.common.index("--block-id") + 1] = f"b{n}"
                self.common[self.common.index("--position") + 1] = str(pos)
                self.run_c()
                r = self.receipt()
                if arm == "A":  # stand-in A row built from a real C receipt's shape
                    r.update(arm="A", route_observed="cua-driver", mint_ms=0.0,
                             run_id=r["run_id"] + "-as-A")
                    r.pop("opencli_sha")
                rows.append(r)
        cohort = summarize(rows, minimum_blocks=2)["cohorts"]["browser-fixture-form/default[AC]"]
        self.assertEqual(cohort["reasons"], ["non-real/unit evidence present"])
        self.assertEqual(cohort["blocks"], 2)

    def test_adapter_failure_is_recorded_not_retried(self):
        self.assertEqual(self.run_c(mode="crash"), 1)
        r = self.receipt()
        self.assertEqual((r["route_observed"], r["oracle_outcome"], r["fallback_count"]),
                         ("blocked", "abstained", 0))

    def test_read_that_mutates_is_refuted_and_unauthorized(self):
        self.assertEqual(self.run_c(mode="mutate"), 1)
        r = self.receipt()
        self.assertEqual(r["oracle_outcome"], "refuted")
        self.assertTrue(r["unauthorized_effect"])
        self.assertEqual(r["audit_after"], 1)

    def test_write_is_refused_without_authority(self):
        before = self.audit()
        self.assertEqual(self.run_c("--effect", "write", "--value", "v1"), 2)
        self.assertEqual(self.audit(), before)
        self.assertFalse(self.out.exists())

    def test_authorized_write_verified_by_audit(self):
        code = self.run_c("--effect", "write", "--value", "v1", "--allow-write",
                          "--read-only-proof-sha256", "f" * 64)
        self.assertEqual(code, 0)
        r = self.receipt()
        self.assertEqual((r["oracle_outcome"], r["audit_after"], r["duplicate_effect"]),
                         ("verified", 1, False))

    def test_double_write_is_flagged_duplicate(self):
        self.run_c("--effect", "write", "--value", "v1", "--allow-write",
                   "--read-only-proof-sha256", "f" * 64, mode="double")
        r = self.receipt()
        self.assertTrue(r["duplicate_effect"])
        self.assertEqual(r["oracle_outcome"], "refuted")

    def test_error_after_commit_is_uncertain_never_replayed(self):
        self.run_c("--effect", "write", "--value", "v1", "--allow-write",
                   "--read-only-proof-sha256", "f" * 64, mode="late-fail")
        r = self.receipt()
        self.assertTrue(r["uncertain_effect"])
        self.assertEqual((r["oracle_outcome"], r["audit_after"]), ("unknown", 1))

    def test_non_loopback_cdp_or_base_refused(self):
        os.environ["FAKE_MODE"] = "ok"
        cli = exe(self.dir, "opencli", FAKE_OPENCLI)
        argv = [*self.common, "--opencli-cmd", cli, "--opencli-sha", "e" * 40]
        self.assertEqual(run_arm_c.main([*argv, "--cdp-endpoint", "http://example.com:9222"]), 2)
        bad = list(argv)
        bad[bad.index("--base") + 1] = "http://example.com:80"
        self.assertEqual(run_arm_c.main([*bad, "--cdp-endpoint", "http://127.0.0.1:9"]), 2)

    def test_real_evidence_requires_exact_pins(self):
        self.assertEqual(self.run_c("--evidence-class", "REAL"), 0)
        self.assertEqual(self.receipt()["evidence_class"], "REAL")
        bad = [*self.common]
        bad[bad.index("--driver-sha") + 1] = "not-a-sha"
        os.environ["FAKE_MODE"] = "ok"
        cli = exe(self.dir, "opencli", FAKE_OPENCLI)
        self.assertEqual(run_arm_c.main([*bad, "--cdp-endpoint", "http://127.0.0.1:9", "--opencli-cmd",
                                         cli, "--opencli-sha", "e" * 40, "--evidence-class", "REAL"]), 2)


class ArmB(Fixture):
    def run_b(self, *extra, mode="ok"):
        os.environ["FAKE_MODE"] = mode
        cmd = exe(self.dir, "pomerado-mcp", FAKE_MCP)
        art = self.dir / "artifact"
        art.mkdir(exist_ok=True)
        return run_arm_b.main([*self.common, "--artifact", str(art), "--pomerado-cmd", cmd, *extra])

    def test_read_via_mcp_stdio_is_verified(self):
        self.assertEqual(self.run_b(), 0)
        r = self.receipt()
        self.assertEqual((r["arm"], r["route_observed"], r["oracle_outcome"]),
                         ("B", "pomerado-mcp", "verified"))
        self.assertIn("tool=read_status", r["route_evidence"])
        self.assertEqual((r["audit_before"], r["audit_after"]), (0, 0))

    def test_tool_without_read_only_hint_is_refused_for_read(self):
        self.assertEqual(self.run_b(mode="writable"), 1)
        r = self.receipt()
        self.assertEqual((r["route_observed"], r["oracle_outcome"]), ("blocked", "abstained"))

    def test_running_job_is_observed_with_get_job_only(self):
        self.assertEqual(self.run_b("--tool", "read_status", mode="job"), 0)
        self.assertIn("calls=tools/call,get_job", self.receipt()["route_evidence"])

    def test_stalled_job_never_gets_input(self):
        self.assertEqual(self.run_b("--tool", "read_status", mode="stall"), 1)
        # fake returns a non-completed job without answering provide_input
        self.assertEqual(self.receipt()["oracle_outcome"], "abstained")

    def test_missing_tool_fails_closed(self):
        self.assertEqual(self.run_b("--tool", "nonexistent"), 1)
        self.assertEqual(self.receipt()["route_observed"], "blocked")

    def test_missing_server_binary_is_recorded(self):
        art = self.dir / "a"
        art.mkdir()
        code = run_arm_b.main([*self.common, "--artifact", str(art),
                               "--pomerado-cmd", str(self.dir / "absent")])
        self.assertEqual(code, 1)
        self.assertEqual(self.receipt()["oracle_outcome"], "abstained")

    def test_write_requires_authority(self):
        self.assertEqual(self.run_b("--effect", "write", "--value", "v"), 2)


if __name__ == "__main__":
    unittest.main()
