#!/usr/bin/env python3
"""Recompute every R2-02 headline number from raw/*.jsonl.

  python verify_artifacts.py           # recompute, compare with r2-02-summary.json, run packet checks
  python verify_artifacts.py --write   # recompute and (re)write r2-02-summary.json

Standard library only. Deterministic (seeded bootstrap).
"""

from __future__ import annotations

import json
import pathlib
import random
import re
import statistics
import sys

R = pathlib.Path(__file__).resolve().parent
RAW = R / "raw"
SUMMARY = R / "r2-02-summary.json"
SEED = 2026100102
RESAMPLES = 10000
PAIRS = 24
CONTROLS = 6


def load() -> list[dict]:
    rows = []
    for path in sorted(RAW.glob("[0-9][0-9][0-9]-*.jsonl")):
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        assert len(lines) == 1, path.name
        rows.append(json.loads(lines[0]))
    assert [r["seq"] for r in rows] == list(range(len(rows))), "missing or reordered trial receipts"
    return rows


def median(xs):
    return round(statistics.median(xs), 3) if xs else None


def p95(xs):
    if not xs:
        return None
    s = sorted(xs)
    return round(s[max(0, -(-95 * len(s) // 100) - 1)], 3)


def arm_stats(rows: list[dict]) -> dict:
    ver = [r for r in rows if r["outcome"] == "verified"]
    ctv = [r["click_to_verified_ms"] for r in ver]
    return {
        "n": len(rows),
        "verified": len(ver),
        "outcomes": {o: sum(r["outcome"] == o for r in rows) for o in sorted({r["outcome"] for r in rows})},
        "click_to_verified_ms": {"median": median(ctv), "p95_nearest_rank": p95(ctv),
                                 "min": min(ctv) if ctv else None, "max": max(ctv) if ctv else None},
        "tool_ms_median": median([r["tool_ms"] for r in ver]),
        "post_return_ms_median": median([r["post_return_ms"] for r in ver]),
        "effect_to_outcome_ms_median": median([r["effect_to_outcome_ms"] for r in ver]),
        "click_to_effect_ms_median": median([r["click_to_effect_ms"] for r in ver]),
        "oracle_reads_after_call": {"median": median([r["oracle_reads_after_call"] for r in ver]),
                                    "total": sum(r["oracle_reads_after_call"] for r in rows if "oracle_reads_after_call" in r)},
        "fixed_sleeps": {"median": median([r["fixed_sleeps"] for r in ver]),
                         "total": sum(r["fixed_sleeps"] for r in rows if "fixed_sleeps" in r)},
        "first_read_after_call_verified": sum(r.get("first_read_after_call") == "verified" for r in rows),
        "effect_before_tool_return": sum(bool(r.get("effect_before_tool_return")) for r in rows),
        "loadavg1_median": median([r["loadavg_before"][0] for r in rows]),
        "loadavg1_max": max(r["loadavg_before"][0] for r in rows) if rows else None,
    }


def bootstrap_ci(diffs: list[float]) -> list[float] | None:
    if not diffs:
        return None
    rng = random.Random(SEED)
    meds = sorted(statistics.median(rng.choices(diffs, k=len(diffs))) for _ in range(RESAMPLES))
    return [round(meds[int(0.025 * RESAMPLES)], 3), round(meds[int(0.975 * RESAMPLES) - 1], 3)]


def probe_phases(rows: list[dict]) -> dict:
    marks = [r["probe"]["marks"] for r in rows if r.get("probe")]
    def m(key):
        return median([x[key] for x in marks if key in x])
    dispatch = [x["dispatch_returned_ms"] - x["dispatch_sent_ms"] for x in marks]
    setup = [x["generation_read_ms"] for x in marks]
    overhead = [x["generation_read_ms"] + x["cleanup_ms"] for x in marks]
    return {
        "n": len(marks),
        "subscribed_ms_median": m("subscribed_ms"),
        "page_enable_ms_median": median([x["page_enabled_ms"] - x["subscribed_ms"] for x in marks]),
        "generation_read_ms_median": median([x["generation_read_ms"] - x["page_enabled_ms"] for x in marks]),
        "setup_total_ms_median": median(setup),
        "dispatch_ms_median": median(dispatch),
        "dispatch_return_to_wake_ms_median": m("wait_ms"),
        "cleanup_ms_median": m("cleanup_ms"),
        "setup_plus_cleanup_ms_median": median(overhead),
        "probe_total_ms_median": m("total_ms"),
    }


EXPECT = {
    "C1_lost": lambda r, p: p and p["end"] == "deadline" and p["counts"]["suppressed"] >= 1
    and p["wake_method"] is None and r["outcome"] == "verified",
    "C2_spurious": lambda r, p: p and p["end"] == "wake" and p["wake_injected"] is False
    and r["first_read_after_call"] != "verified" and r["outcome"] == "verified",
    "C3_early": lambda r, p: p and p["counts"]["early_rejected"] == 1 and p["end"] == "wake"
    and p["wake_injected"] is False and r["outcome"] == "verified",
    "C3u_early_unguarded": lambda r, p: p and p["wake_injected"] is True and r["outcome"] == "verified"
    and r["submit_posts"] == 1,
    "C4_unrelated": lambda r, p: p and p["counts"]["unrelated_frame"] >= 1 and p["end"] == "wake"
    and p["wake_injected"] is False and r["outcome"] == "verified",
    "C5_stale": lambda r, p: p and p["counts"]["stale_rejected"] == 1 and p["end"] == "wake"
    and p["wake_injected"] is False and r["outcome"] == "verified",
    "C5u_stale_unguarded": lambda r, p: p and p["wake_injected"] is True and r["outcome"] == "verified"
    and r["submit_posts"] == 1,
    "C6_timeout_event": lambda r, p: p and p["end"] == "deadline" and p["wake_method"] is None
    and r["outcome"] == "timeout" and r["submit_posts"] == 0,
    "C6p_timeout_poll": lambda r, p: p is None and r["outcome"] == "timeout" and r["submit_posts"] == 0,
    "C7_refuted": lambda r, p: p and p["end"] == "wake" and r["first_read_after_call"] == "refuted"
    and r["outcome"] == "refuted",
    "C0_default_off": lambda r, p: p is None and r["outcome"] == "verified",
}


def compute(rows: list[dict]) -> dict:
    pairs = {}
    for r in rows:
        if r["kind"] == "pair":
            pairs.setdefault(r["group"], {})[r["arm"]] = r
    assert len(pairs) == PAIRS and all(set(v) == {"poll", "event"} for v in pairs.values())
    poll = [v["poll"] for v in pairs.values()]
    event = [v["event"] for v in pairs.values()]
    diffs, both = [], 0
    for name in sorted(pairs):
        a, b = pairs[name]["poll"], pairs[name]["event"]
        if a["outcome"] == "verified" and b["outcome"] == "verified":
            both += 1
            diffs.append(round(b["click_to_verified_ms"] - a["click_to_verified_ms"], 3))
    order = {name: [r["arm"] for r in sorted(v.values(), key=lambda r: r["seq"])] for name, v in pairs.items()}
    ab = sum(o == ["poll", "event"] for o in order.values())

    controls = {}
    for group in EXPECT:
        g = [r for r in rows if r["group"] == group]
        passed = [r["seq"] for r in g if EXPECT[group](r, r.get("probe"))]
        controls[group] = {
            "n": len(g),
            "expectation_met": len(passed),
            "outcomes": {o: sum(r["outcome"] == o for r in g) for o in sorted({r["outcome"] for r in g})},
            "first_read_after_call": {o: sum(r.get("first_read_after_call") == o for r in g)
                                      for o in sorted({str(r.get("first_read_after_call")) for r in g})},
            "probe_end": {e: sum((r.get("probe") or {}).get("end") == e for r in g)
                          for e in sorted({str((r.get("probe") or {}).get("end")) for r in g})},
            "click_to_outcome_ms_median": median([r["click_to_outcome_ms"] for r in g if "click_to_outcome_ms" in r]),
            "failing_seqs": [r["seq"] for r in g if r["seq"] not in passed],
        }
        if group == "C4_unrelated":
            controls[group]["unrelated_frame_events_total"] = sum(r["probe"]["counts"]["unrelated_frame"] for r in g if r.get("probe"))

    # A verified record must rest on the oracle: last read verified and a journaled POST.
    false_success = [r["seq"] for r in rows if r["outcome"] == "verified"
                     and (r["reads"][-1]["outcome"] != "verified" or r["submit_posts"] < 1)]
    errors = [r["seq"] for r in rows if r["outcome"] == "error"]
    guarded_wrong_wake = [r["seq"] for r in rows if r["group"] in {"C3_early", "C4_unrelated", "C5_stale"}
                          and r.get("probe") and r["probe"]["wake_injected"] is True]

    med = median(diffs)
    ci = bootstrap_ci(diffs)
    favour = sum(d < 0 for d in diffs)
    ps, es = arm_stats(poll), arm_stats(event)
    correctness = (ps["verified"] >= 23 and es["verified"] >= 23 and not false_success and not guarded_wrong_wake
                   and all(c["n"] == (3 if g == "C0_default_off" else CONTROLS) and c["expectation_met"] == c["n"]
                           for g, c in controls.items()))
    timing_keep = med is not None and med <= -20 and ci[1] < 0
    if false_success or guarded_wrong_wake or (ci and ci[0] > 0):
        disposition = "KILL"
    elif correctness and timing_keep:
        disposition = "KEEP"
    else:
        disposition = "REVISE"
    return {
        "schema": "cua.r2_02.summary.v1",
        "trials_total": len(rows),
        "warmup": {r["arm"]: {"outcome": r["outcome"], "click_to_outcome_ms": r.get("click_to_outcome_ms")}
                   for r in rows if r["kind"] == "warmup"},
        "pairs": {
            "n": PAIRS, "order_ab": ab, "order_ba": PAIRS - ab, "both_verified": both,
            "poll": ps, "event": es,
            "paired_diff_event_minus_poll_ms": {
                "n": len(diffs), "median": med, "mean": round(statistics.fmean(diffs), 3) if diffs else None,
                "bootstrap95_ci_median": ci, "bootstrap": {"seed": SEED, "resamples": RESAMPLES},
                "pairs_favouring_event": favour, "pairs_favouring_poll": sum(d > 0 for d in diffs),
                "diffs": diffs,
            },
            "event_probe_phases": probe_phases(event),
            "event_probe_end": {e: sum(r["probe"]["end"] == e for r in event if r.get("probe"))
                                for e in sorted({r["probe"]["end"] for r in event if r.get("probe")})},
        },
        "controls": controls,
        "false_success_seqs": false_success,
        "guarded_wrong_wake_seqs": guarded_wrong_wake,
        "error_seqs": errors,
        "gates": {"correctness": correctness, "timing_keep": timing_keep, "disposition": disposition},
    }


PRIVATE = [re.compile(p) for p in (r"/home/", r"/mnt/", r"/tmp/", r"/root/", r"\bkvn\b", r"zer0models",
                                   r"cachyos", r"(?i)api[_-]?key\s*[:=]", r"(?i)bearer\s+[a-z0-9]")]


def packet_checks(summary: dict) -> None:
    prov = json.loads((R / "provenance.json").read_text())
    for key in ("tested_source_sha", "upstream_main_sha", "prereg_commit_sha"):
        assert re.fullmatch("[0-9a-f]{40}", prov[key]), key
    assert re.fullmatch("[0-9a-f]{64}", prov["driver_sha256"])
    assert re.fullmatch("[0-9a-f]{64}", prov["prereg_sha256"])
    head = (R / "source-head.txt").read_text().split()
    assert head[0] == prov["tested_source_sha"]
    import hashlib
    assert hashlib.sha256((R / "PREREG.json").read_bytes()).hexdigest() == prov["prereg_sha256"], "PREREG edited"
    readme = (R / "README.md").read_text()
    for needle in (summary["gates"]["disposition"], "Claim boundary", "Deviations", "Work deleted"):
        assert needle in readme, needle
    for path in R.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl", ".md", ".txt", ".py"} and path.name != "verify_artifacts.py":
            text = path.read_text()
            for pat in PRIVATE:
                assert not pat.search(text), f"privacy: {pat.pattern} in {path.relative_to(R)}"


def main() -> None:
    summary = compute(load())
    if "--write" in sys.argv:
        SUMMARY.write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
        print(f"wrote {SUMMARY.name}")
        return
    committed = json.loads(SUMMARY.read_text())
    assert committed == summary, "r2-02-summary.json does not match a recomputation from raw/"
    packet_checks(summary)
    p = summary["pairs"]
    d = p["paired_diff_event_minus_poll_ms"]
    print(f"pairs: poll {p['poll']['verified']}/{p['poll']['n']} verified, event {p['event']['verified']}/{p['event']['n']}")
    print(f"click_to_verified median poll {p['poll']['click_to_verified_ms']['median']} ms, "
          f"event {p['event']['click_to_verified_ms']['median']} ms")
    print(f"paired diff median {d['median']} ms, 95% CI {d['bootstrap95_ci_median']}, "
          f"{d['pairs_favouring_event']}/{d['n']} favour event")
    for g, c in summary["controls"].items():
        print(f"{g}: {c['expectation_met']}/{c['n']} expectation met, outcomes {c['outcomes']}")
    print(f"false success {len(summary['false_success_seqs'])}, errors {len(summary['error_seqs'])}, "
          f"disposition {summary['gates']['disposition']}")
    print("All R2-02 headline numbers recomputed from raw/ and match; packet checks passed")


if __name__ == "__main__":
    main()
