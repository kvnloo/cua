"""results.jsonl chain, schemas, plan, ar-submit, g1 rows."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AR))
sys.path.insert(0, str(AR / "runner"))

from areval import results  # noqa: E402
from areval.schema import load, validate  # noqa: E402
import g1_rows  # noqa: E402
import plan  # noqa: E402


def result_record(eval_id="ar-20261002-x", lord=None):
    return {"schema": "ar.result.v1", "eval_id": eval_id, "prereg_sha256": "a" * 64, "rows_sha256": "b" * 64,
            "verdict": "REJECT", "failed_gate": "G0", "gates": [{"gate": "G0", "pass": False, "reasons": ["x"],
                                                                 "metrics": {}}],
            "not_evaluated": ["G1"], "delta": None, "ci95": None, "p_value": None, "power": None, "n_pairs": None,
            "tau": 0.02, "lord": lord, "recorded_utc": "2026-10-02T00:00:00Z"}


class Results(unittest.TestCase):
    def test_append_chain_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "results.jsonl"
            results.append(path, result_record())
            results.append(path, result_record("ar-20261002-y", lord={"index": 1, "alpha_i": 0.00125,
                                                                      "p_value": 0.5, "rejected": False,
                                                                      "wealth_before": 0.025, "wealth_after": 0.02375}))
            self.assertEqual(results.verify_chain(path), [])
            self.assertEqual(results.prior_p_values(path), [0.5])
            lines = path.read_text().splitlines()
            lines[0] = lines[0].replace("REJECT", "KEEP")
            path.write_text("\n".join(lines) + "\n")
            self.assertTrue(results.verify_chain(path))
            with self.assertRaises(RuntimeError):
                results.append(path, result_record("ar-20261002-z"))

    def test_invalid_record_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = result_record()
            bad["verdict"] = "MAYBE"
            with self.assertRaises(ValueError):
                results.append(Path(tmp) / "r.jsonl", bad)


class Schemas(unittest.TestCase):
    def test_prereg_schema_accepts_valid_and_rejects_cheats(self):
        schema = load("prereg.schema.json")
        pre = json.loads((AR / "tests/data/prereg-example.json").read_text())
        self.assertEqual(validate(pre, schema), [])
        for path, value in ((("tau", "value"), 0.01), (("mechanism", "min_share"), 0.5),
                            (("design", "alpha_one_sided"), 0.05), (("design", "session_trials"), 60),
                            (("fdr", "procedure"), "BH")):
            bad = json.loads(json.dumps(pre))
            bad[path[0]][path[1]] = value
            self.assertTrue(validate(bad, schema), path)

    def test_trial_schema_on_a_synthetic_row(self):
        sys.path.insert(0, str(AR / "tests"))
        import synth
        self.assertEqual(validate(synth.trial(1, "champion", "task", 1500.0, 241.0), load("trial.schema.json")), [])


class Plan(unittest.TestCase):
    def test_sessions_pairs_and_trace_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a", Path(tmp) / "b"
            a.write_bytes(b"A")
            b.write_bytes(b"B")
            p = plan.build("ar-20261002-t", {"champion": str(a), "candidate": str(b)}, 50, seed=3,
                           spot_pairs=10, soak=100)
            sessions = p["sessions"]
            self.assertTrue(all(len(s["trials"]) <= 48 for s in sessions))
            task = [t for s in sessions for t in s["trials"] if t["kind"] == "task" and not t["warmup"]]
            pairs = {}
            for t in task:
                pairs.setdefault(t["pair_id"], []).append(t)
            self.assertEqual(len(pairs), 50)
            for pid, ts in pairs.items():
                self.assertEqual(len({t["session"] for t in ts}), 1, "pair split across sessions")
                self.assertEqual(ts[0]["trace"], ts[1]["trace"])
                first = sorted(ts, key=lambda t: t["position"])[0]["arm"]
                self.assertEqual(first, "champion" if ts[0]["order"] == "AB" else "candidate")
            self.assertEqual(sum(1 for ts in pairs.values() if not ts[0]["trace"]), 10)
            self.assertEqual(sum(1 for t in task if t["order"] == "AB"), sum(1 for t in task if t["order"] == "BA"))
            soak = [t for s in sessions for t in s["trials"] if t["kind"] == "soak"]
            self.assertEqual(len(soak), 100)
            for s in sessions:
                kinds = [t["kind"] for t in s["trials"]]
                if "task" in kinds and "soak" not in kinds:
                    self.assertEqual(kinds.count("stale_negative"), 2)
                    self.assertEqual(kinds.count("impossible_canary"), 2)
            ids = [t["trial_id"] for s in sessions for t in s["trials"]]
            self.assertEqual(ids, list(range(len(ids))))


class Submit(unittest.TestCase):
    def run_submit(self, *args, env_dir=True):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ)
            env.pop("AR_REQUEST_DIR", None)
            if env_dir:
                env["AR_REQUEST_DIR"] = tmp
            proc = subprocess.run([sys.executable, str(AR / "ar-submit"), *args], capture_output=True, text=True, env=env)
            files = list(Path(tmp).glob("*.json"))
            return proc, [json.loads(f.read_text()) for f in files]

    def test_writes_valid_request(self):
        proc, reqs = self.run_submit("--branch", "ar/s1/settle-watch-120", "--hypothesis", "Shorter settle watch.",
                                     "--mechanism-start", "focus_guard/body_done", "--mechanism-end", "focus_guard/restored")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(reqs), 1)
        self.assertEqual(validate(reqs[0], load("request.schema.json")), [])

    def test_rejects_bad_branch_and_missing_inbox(self):
        proc, reqs = self.run_submit("--branch", "main", "--hypothesis", "x")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(reqs, [])
        proc, _ = self.run_submit("--branch", "ar/s1/x", "--hypothesis", "x", env_dir=False)
        self.assertNotEqual(proc.returncode, 0)


class G1Rows(unittest.TestCase):
    def test_parse_logs(self):
        build = ("[t] build start label=ar-x head=" + "a" * 40 + " rustc=1\n  Fresh workspace units: 0\n"
                 "[t] build done label=ar-x seconds=200 sha256=" + "b" * 64 + "\n")
        self.assertTrue(g1_rows.build_rows(build)[0]["ok"])
        self.assertFalse(g1_rows.build_rows(build.replace("units: 0", "units: 3"))[0]["ok"])
        log = ("### cargo test -p platform-linux --lib\n"
               "test result: ok. 599 passed; 0 failed; 10 ignored; 0 measured; 0 filtered out; finished in 24.01s\nrc=0\n"
               "### cargo test -p cua-driver-core --lib\n"
               "test result: FAILED. 816 passed; 1 failed; 0 ignored; 0 measured\nrc=101\n")
        rows = g1_rows.test_rows(log)
        self.assertEqual([(r["suite"], r["ok"]) for r in rows],
                         [("platform-linux --lib", True), ("cua-driver-core --lib", False)])


if __name__ == "__main__":
    unittest.main()
