#!/usr/bin/env python3
"""Build accounting.json and the generated tables in README.md for kvnloo/cua#10.

Stdlib only; run under the lane's hostless wrapper. Every number is read from an accepted packet's
summary JSON at an exact commit (`git show <sha>:<path>`) and stored as a pointer
{"value", "from": {packet, file, path, round}} that verify_artifacts.py re-resolves.

Rules carried from the loop: one row per SOURCE (binary); never add or ratio numbers across rows;
work deleted is reported separately from wall-clock saved; cross-lane readings combine verdicts only.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rfc_common as C  # noqa: E402

OUT_JSON = os.path.join(C.HERE, "accounting.json")
README = os.path.join(C.HERE, "README.md")
BEGIN = "<!-- BEGIN GENERATED: make_accounting.py -->"
END = "<!-- END GENERATED: make_accounting.py -->"

PACKETS = {
    "R2-10": dict(branch="exp/r2-10-composition-20261002", sha="030f6bdbf811e124e11daa2de0569bffb993b66d",
                  dir="docs/experiments/r2-10-composition-2026-10-02",
                  files={"summary": "r2-10-summary.json", "provenance": "provenance.json"},
                  source="R", accepted_wave=3, binary_path=["binaries", "R", "sha256"],
                  tested_source="989cc76ce + R2-10 steps 1-8 (head 8f3a646b4)",
                  note="Published fork branch carries an encoded private-name list (owner ruling pending); "
                       "PUB-02 clean candidate r1c eaca68df9 is held, not pushed. The summary blob is "
                       "checked identical at both commits."),
    "R2-10R": dict(branch="exp/r2-10r-recert-a3-20261003", sha="d22eeb2ecf8a679d1425c21120a599775aa0817d",
                   dir="docs/experiments/r2-10r-recert-2026-10-03",
                   files={"summary": "r2-10r-summary.json", "recert": "recert-summary.json",
                          "provenance": "provenance.json"},
                   source="R'", accepted_wave=4, binary_path=["binaries", "R_prime", "sha256"],
                   tested_source="0f1955d2f + R2-10 steps 1-8 (45dff8f32)",
                   note="a3 is the PUB-02 privacy rewrite of the accepted a2 (c183b95e3), verified 189/189 both ways."),
    "B-04": dict(branch="exp/b-04-observation-reconcile-a2-20261003", sha="8620ebfa23a77c0f94403a619b7684a65c3cd63c",
                 dir="docs/experiments/b-04-observation-reconcile-2026-10-03",
                 files={"summary": "b04-summary.json", "provenance": "provenance.json"},
                 source="R", accepted_wave=4, binary_path=["driver_binary", "sha256"],
                 tested_source="R (12b9045a) + re-analysis of R2-10 raw at 030f6bdbf"),
    "R2-07d": dict(branch="exp/r2-07d-quiet-timing-phase-l-20261003", sha="79f6dd29958b2a73b477544ca9e777efade8a6c3",
                   dir="docs/experiments/r2-07d-quiet-timing-phase-l-2026-10-03",
                   files={"summary": "r2-07d-summary.json", "provenance": "provenance.json"},
                   source="R", accepted_wave=5, binary_path=["driver", "sha256"],
                   tested_source="R (12b9045a), no Driver change"),
    "B-06": dict(branch="exp/b-06-per-process-cold-snapshot-20261003", sha="31bc98a95b746080d1b74b895fe575071d4a94e9",
                 dir="docs/experiments/b-06-per-process-cold-snapshot-2026-10-03",
                 files={"summary": "b06-summary.json", "provenance": "provenance.json"},
                 source="R'", accepted_wave=5, binary_path=["driver_binary", "sha256"],
                 tested_source="R' (45dff8f32), not rebuilt"),
    "B-07": dict(branch="exp/b-07-transport-residual-rprime-20261003", sha="eab1e87a3fb35a300a5d434cd10f2cddbf9a3bb1",
                 dir="docs/experiments/b-07-transport-residual-rprime-2026-10-03",
                 files={"summary": "b07-summary.json", "provenance": "provenance.json"},
                 source="B7", accepted_wave=5, binary_path=["binaries", "B7", "sha256"],
                 tested_source="R' 45dff8f32 + B-07 marks + POST_FAST knob (ac319cbe9)"),
    "B-05": dict(branch="exp/b-05-browser-mcp-transport-a3-20261003", sha="7052382820687e5bf55e2925e09a3fbe70cce500",
                 dir="docs/experiments/b-05-browser-mcp-transport-2026-10-03",
                 files={"summary": "b05-summary.json", "provenance": "provenance.json"},
                 source="B5", accepted_wave=5, binary_path=["binaries", "B5", "sha256"],
                 tested_source="R2-10 source + B-05 marks (b376f1ff3)"),
    "N-04": dict(branch="exp/n-04-native-composition-rprime-20261003", sha="9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2",
                 dir="docs/experiments/n-04-native-composition-rprime-2026-10-03",
                 files={"summary": "n04-summary.json", "provenance": "provenance.json"},
                 source="R'n", accepted_wave=5, binary_path=["binaries", "Rn", "sha256"],
                 tested_source="R' 45dff8f32 + N-02 marks + focus-guard clamp knob (11a03bf51)"),
    "N-03": dict(branch="exp/n-03-native-closure-axfg-a3-20261003", sha="6b70ec9024cc3921f7637bba2ffabcc93e29fc77",
                 dir="docs/experiments/n-03-native-closure-axfg-2026-10-03",
                 files={"summary": "n03-summary.json", "provenance": "provenance.json"},
                 source="N3", accepted_wave=5, binary_path=["binaries", "N3", "sha256"],
                 tested_source="R2-10 source + N-03 marks/knobs (85a73c2c7)"),
}

# Rows that can still move in wave 6 (refresh in wave 7).
PENDING_W6 = {
    "B-08": "per-process cold first snapshot on B7 (exp/b-08-per-process-cold-b7-20261003); decides the "
            "browser cold-excess verdict on the B7 source",
    "R2-07e": "new pre-registered modal gate + Phase L (exp/r2-07e-modal-gate-phase-l-20261003)",
    "PUB-03": "privacy rewrites of published N-03 / N-04 / OWN-20G heads (r1c branches); numbers unchanged by design",
}


def P(pkt, fkey, path, nd=None):
    meta = PACKETS[pkt]
    data = C.show_json(meta["sha"], meta["dir"] + "/" + meta["files"][fkey])
    raw = C.resolve(data, path)
    return {"value": C.rnd(raw, nd), "from": {"packet": pkt, "file": fkey, "path": list(path), "round": nd}}


def D(num, den, nd):
    """A within-row derived ratio of two pointers (same packet, same source); verify recomputes it."""
    val = None
    if num["value"] not in (None, 0) and den["value"] not in (None, 0):
        val = C.rnd(float(num["value"]) / float(den["value"]), nd)
    return {"value": val, "derived": {"op": "div", "num": num, "den": den, "round": nd}}


def T(text):
    """A literal (non-number) statement; never a measured value."""
    return {"text": text}


def NA(reason, status="NOT_MEASURED"):
    return {"status": status, "reason": reason}


# ----------------------------------------------------------------------------------------- rows

def comp_list_r210(pkt, layer, key, verdict_lane):
    """All components of a R2-10-style decomposition (R2-10 / R2-10R), values and verdicts from the packet."""
    base = [layer, "decomposition", key] if layer else ["decomposition", key]
    if layer in ("live", "scripted"):
        base = ["browser", layer, "decomposition", key]
    elif layer == "native":
        base = ["native", "decomposition", key]
    meta = PACKETS[pkt]
    data = C.show_json(meta["sha"], meta["dir"] + "/" + meta["files"]["summary"])
    comps = C.resolve(data, base + ["components"])
    out = []
    for name in sorted(comps, key=lambda n: -comps[n]["mean_ms"]):
        out.append({
            "component": name,
            "mean_ms": P(pkt, "summary", base + ["components", name, "mean_ms"], 2),
            "share": P(pkt, "summary", base + ["components", name, "share"], 4),
            "material": P(pkt, "summary", base + ["components", name, "above_threshold"]),
            "verdict": P(pkt, "summary", base + ["components", name, "verdict"]),
            "verdict_lane": verdict_lane,
        })
    return out


def floor_r210(pkt, base):
    return {
        "T_composed_mean_ms": P(pkt, "summary", base + ["mean_T_ms"], 2),
        "T_irreducible_ms": P(pkt, "summary", base + ["T_irreducible_ms"], 2),
        "floor_ratio": P(pkt, "summary", base + ["floor_ratio_mean"], 2),
        "untested_ms": P(pkt, "summary", base + ["untested_ms"], 2),
    }


# Components the composed browser configuration deliberately removes (BASE - COMP mean, per trial).
BROWSER_REMOVED = [
    ("visualization", "feedback glide off (B-01 glide: OWNER_DECISION)"),
    ("settles", "insert_text focus settle (B-01 H_T: OWNER_DECISION)"),
    ("client_validation", "caller-compiled output validators (B-01 H_C: DELETED)"),
    ("mcp_admission", "admission tools-list cache (B-02 H_V: DELETED)"),
]


def browser_work(pkt, layer, cls):
    base = ["browser", layer, "work_deleted_vs_wall_clock", cls]
    items = [{"component": c, "why": why, "ms": P(pkt, "summary", base + ["component_mean_ms_deleted", c], 1)}
             for c, why in BROWSER_REMOVED]
    if cls == "fill":
        items.append({"component": "provider_decision",
                      "why": "fill compiled replay (R2-07b via FIX-01) removes the provider decisions on warm replay",
                      "ms": P(pkt, "summary", base + ["component_mean_ms_deleted", "provider_decision"], 1)})
    return {
        "components_ms": items,
        "provider_requests_per_trial": {
            "BASE": P(pkt, "summary", base + ["provider_decisions_per_trial", "BASE"], 3),
            "COMP": P(pkt, "summary", base + ["provider_decisions_per_trial", "COMP"], 3),
        },
        "rule": "BASE minus COMP component mean for the components the composed arm removes; other "
                "component differences are noise or moved work and are not counted",
    }


def browser_wall(pkt, layer, cls):
    base = ["browser", layer, "work_deleted_vs_wall_clock", cls]
    return {"median_paired_ms": P(pkt, "summary", base + ["wall_clock_saved_median_paired_ms"], 1),
            "ci95": P(pkt, "summary", base + ["wall_clock_saved_ci95"], 1)}


def row_r210_browser(cls, layer):
    pkt = "R2-10"
    lay = "live" if layer == "live" else "scripted"
    s = ["browser", lay, "S", "COMP", cls]
    dkey = cls + "/COMP"
    row = {
        "row_id": "%s/R/R2-10-%s" % (cls, lay),
        "lane": "R2-10", "source": "R", "status": "ACCEPTED",
        "layer": "L-live (TypeSafe provider)" if lay == "live" else "L-scripted (scripted chooser, no provider)",
        "evidence_class": (["LIVE_PROVIDER", "REAL", "BENCHMARK (FIXTURE)"] if lay == "live"
                           else ["REAL", "BENCHMARK (FIXTURE)"]),
        "best_arm": "COMP",
        "T_base_ms": P(pkt, "summary", s + ["all", "median_base_ms"], 1),
        "T_best_ms": P(pkt, "summary", s + ["all", "median_arm_ms"], 1),
        "S": P(pkt, "summary", s + ["all", "S"], 2),
        "S_ci95": P(pkt, "summary", s + ["all", "ci95"], 2),
        "n_pairs": P(pkt, "summary", s + ["all", "n"]),
        "validity": {
            "BASE": P(pkt, "summary", ["gates", "validity", "shares", "browser/%s/%s/BASE" % (lay, cls)], 3),
            "COMP": P(pkt, "summary", ["gates", "validity", "shares", "browser/%s/%s/COMP" % (lay, cls)], 3),
            "e4": P(pkt, "summary", ["browser", lay, "e4"]),
        },
        "floor": floor_r210(pkt, ["browser", lay, "decomposition", dkey]),
        "components": comp_list_r210(pkt, lay, dkey, "R2-10 mapping (this packet)"),
        "work_deleted": browser_work(pkt, lay, cls),
        "wall_clock_saved": browser_wall(pkt, lay, cls),
        "untested": {
            "A": P(pkt, "summary", ["browser", lay, "decomposition", dkey, "untested_share"], 4),
            "B": P("B-04", "summary", ["r2_10_rows", "%s/%s" % (lay, cls), "updated_untested_share"], 4),
            "B_lane": "B-04 (same source R; re-analysis of R2-10 raw)",
        },
    }
    if cls == "fill":
        row["S_amortized"] = P(pkt, "summary", s + ["amortized_mean_ratio", "S"], 2)
        row["S_amortized_ci95"] = P(pkt, "summary", s + ["amortized_mean_ratio", "ci95"], 2)
    if lay == "scripted":
        row["S_keep_only"] = P(pkt, "summary", ["browser", "scripted", "S", "COMP_K", cls, "all", "S"], 2)
        row["S_keep_only_ci95"] = P(pkt, "summary", ["browser", "scripted", "S", "COMP_K", cls, "all", "ci95"], 2)
        if cls == "fill":
            row["S_keep_only_amortized"] = P(pkt, "summary",
                                             ["browser", "scripted", "S", "COMP_K", "fill", "amortized_mean_ratio", "S"], 2)
            row["S_keep_only_amortized_ci95"] = P(pkt, "summary",
                                                  ["browser", "scripted", "S", "COMP_K", "fill", "amortized_mean_ratio", "ci95"], 2)
    else:
        row["S_keep_only"] = NA("no KEEP-only (COMP_K) arm on the live layer")
        row["provider"] = {
            "BASE_requests": P(pkt, "summary", ["provider", "by_class_arm", "%s/BASE" % cls]),
            "COMP_requests": P(pkt, "summary", ["provider", "by_class_arm", "%s/COMP" % cls]),
        }
    if cls == "modal":
        row["untested"]["B_note"] = "B-04 did not remap the modal cold excess (B-02 H_W IRREDUCIBLE); B equals A"
    return row


def row_r210r_browser(cls):
    pkt = "R2-10R"
    s = ["browser", "scripted", "S", "COMP", cls]
    dkey = cls + "/COMP"
    row = {
        "row_id": "%s/R'/R2-10R" % cls,
        "lane": "R2-10R", "source": "R'", "status": "ACCEPTED",
        "layer": "L-scripted (recertification of R2-10 on 0f1955d2f; live layer not re-run)",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE)"],
        "best_arm": "COMP",
        "T_base_ms": P(pkt, "summary", s + ["all", "median_base_ms"], 1),
        "T_best_ms": P(pkt, "summary", s + ["all", "median_arm_ms"], 1),
        "S": P(pkt, "summary", s + ["all", "S"], 2),
        "S_ci95": P(pkt, "summary", s + ["all", "ci95"], 2),
        "n_pairs": P(pkt, "summary", s + ["all", "n"]),
        "S_keep_only": P(pkt, "summary", ["browser", "scripted", "S", "COMP_K", cls, "all", "S"], 2),
        "S_keep_only_ci95": P(pkt, "summary", ["browser", "scripted", "S", "COMP_K", cls, "all", "ci95"], 2),
        "validity": {
            "BASE": P(pkt, "recert", ["validity_100", "shares", "browser/scripted/%s/BASE" % cls], 3),
            "COMP": P(pkt, "recert", ["validity_100", "shares", "browser/scripted/%s/COMP" % cls], 3),
            "e4": P(pkt, "summary", ["browser", "scripted", "e4"]),
        },
        "floor": floor_r210(pkt, ["browser", "scripted", "decomposition", dkey]),
        "components": comp_list_r210(pkt, "scripted", dkey, "R2-10 mapping (this packet)"),
        "work_deleted": browser_work(pkt, "scripted", cls),
        "wall_clock_saved": browser_wall(pkt, "scripted", cls),
        "untested": {"A": P(pkt, "summary", ["browser", "scripted", "decomposition", dkey, "untested_share"], 4)},
    }
    if cls in ("fill", "toggle"):
        row["untested"]["B"] = P("B-06", "summary", ["e2", "classes", cls, "share_post_B06"], 4)
        row["untested"]["B_lane"] = "B-06 primary (same source R'; per-process cold excess UNDECIDED, share is a lower bound)"
    else:
        row["untested"]["B"] = P("B-06", "summary", ["e2", "classes", "modal", "share_post_B06"], 4)
        row["untested"]["B_lane"] = "B-06 (modal descriptive; not remapped)"
    if cls == "fill":
        row["S_amortized"] = P(pkt, "summary", s + ["amortized_mean_ratio", "S"], 2)
        row["S_amortized_ci95"] = P(pkt, "summary", s + ["amortized_mean_ratio", "ci95"], 2)
        row["S_keep_only_amortized"] = P(pkt, "summary",
                                         ["browser", "scripted", "S", "COMP_K", "fill", "amortized_mean_ratio", "S"], 2)
        row["S_keep_only_amortized_ci95"] = P(pkt, "summary",
                                              ["browser", "scripted", "S", "COMP_K", "fill", "amortized_mean_ratio", "ci95"], 2)
    return row


def row_b06(cls):
    pkt = "B-06"
    c = ["classes", cls]
    row = {
        "row_id": "%s/R'/B-06" % cls, "lane": "B-06", "source": "R'", "status": "ACCEPTED",
        "layer": "L-scripted, COMP only (per-process cold first snapshot; no BASE arm)",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE)", "SOURCE (per-document part carried from B-04)"],
        "best_arm": "C (cold COMP)",
        "T_base_ms": NA("B-06 has no BASE arm; its arms are COMP variants (C cold, Wa/Wb warm, P control)"),
        "T_arms_ms": {a: P(pkt, "summary", c + ["arms", a, "T_oracle_median"], 1) for a in ("C", "Wa", "Wb", "P")},
        "S": NA("no BASE arm in this lane"),
        "S_keep_only": NA("no KEEP-only arm in this lane"),
        "validity": {a: P(pkt, "summary", ["validity", "%s/%s" % (cls, a), "validity"], 3) for a in ("C", "Wa", "Wb", "P")},
        "n_per_arm": P(pkt, "summary", ["validity", "%s/C" % cls, "n"]),
        "cold_excess": {
            "E_R'_mean_ms": P(pkt, "summary", ["e2", "classes", cls, "E_R_prime_mean_ms"], 2),
            "D_C_minus_Wa_median_ms": P(pkt, "summary", c + ["D_C_minus_Wa", "median"], 2),
            "D_ci": P(pkt, "summary", c + ["D_C_minus_Wa", "ci"], 2),
            "PC_P_minus_Wa_median_ms": P(pkt, "summary", c + ["PC_P_minus_Wa", "median"], 2),
            "verdict_primary": P(pkt, "summary", c + ["verdict"]),
        },
        "components": [],
        "work_deleted": NA("nothing deleted; no product change", status="NONE"),
        "wall_clock_saved": NA("not a deletion experiment", status="NONE"),
    }
    if cls in ("fill", "toggle"):
        xa = ["block_x_amendment_1", "classes", cls]
        row["cold_excess"]["amended_D_median_ms"] = P(pkt, "summary", xa + ["D_C_minus_Wa", "median"], 2)
        row["cold_excess"]["amended_D_ci"] = P(pkt, "summary", xa + ["D_C_minus_Wa", "ci"], 2)
        row["cold_excess"]["verdict_amended_post_hoc"] = P(pkt, "summary", xa + ["verdict"])
        row["untested"] = {
            "A": P(pkt, "summary", ["e2_amended", "classes", cls, "share_post_B06"], 4),
            "A_label": "amended reading (owner's call): per-process part OWNER_DECISION; R2-10R mapping, transport still UNTESTED on R'",
            "B": P(pkt, "summary", ["e2", "classes", cls, "share_post_B06"], 4),
            "B_label": "primary PREREG reading: per-process UNDECIDED, counted UNTESTED (lower bound)",
        }
        row["amortized_ms"] = {
            "warmup_outside_T": P(pkt, "summary", c + ["amortized", "warmup_Wa_median"], 1),
            "k1_T_Wa_plus_warmup": P(pkt, "summary", c + ["amortized", "k1_T_Wa_plus_warmup"], 1),
            "k5_per_task": P(pkt, "summary", c + ["amortized", "k5_T_Wa_plus_warmup_over_5"], 1),
        }
    else:
        row["untested"] = {"A": P(pkt, "summary", ["e2", "classes", "modal", "share_post_B06"], 4),
                           "A_label": "modal descriptive only (not remapped)"}
    return row


def b07_components(cls):
    pkt = "B-07"
    rc = ["phase_A", "by_class", cls, "r210_components"]
    meta = PACKETS[pkt]
    data = C.show_json(meta["sha"], meta["dir"] + "/" + meta["files"]["summary"])
    comps = C.resolve(data, rc)
    out = []
    for name in sorted(comps, key=lambda n: -comps[n]["corr_mean_ms"]):
        ent = {"component": name,
               "mean_ms": P(pkt, "summary", rc + [name, "corr_mean_ms"], 2),
               "share": P(pkt, "summary", rc + [name, "share_corr"], 4)}
        if name == "mcp_transport":
            ent["verdict"] = T("terminal by sub-span (B-05 + B-07): route/adm BELOW_GATE, post/parse/validate "
                               "IRREDUCIBLE, prep %s" % ("DELETED-fragile (not carried)" if cls == "fill" else "IRREDUCIBLE"))
            ent["verdict_lane"] = "B-07 verdicts.units + B-05"
        elif name == "mcp_admission":
            ent["verdict"] = P(pkt, "summary", ["verdicts", "units", "adm.inner", cls])
            ent["verdict_lane"] = "B-07 (adm.inner)"
        else:
            ent["verdict"] = P("R2-10", "summary", ["browser", "scripted", "decomposition", cls + "/COMP",
                                                    "components", name, "verdict"])
            ent["verdict_lane"] = "R2-10 mapping (cross-lane verdict; number from B-07)"
        out.append(ent)
    return out


def row_b07(cls):
    pkt = "B-07"
    pa = ["phase_A", "by_class", cls]
    e2 = ["e2", cls]
    return {
        "row_id": "%s/B7/B-07" % cls, "lane": "B-07", "source": "B7", "status": "ACCEPTED",
        "layer": "L-scripted, COMP only (transport residual on R' + marks; mark-corrected at c_m)",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE)", "UNIT (weak)", "SOURCE"],
        "best_arm": "COMP",
        "T_base_ms": NA("B-07 has no BASE arm"),
        "T_best_ms": P(pkt, "summary", pa + ["T_oracle_ms", "median"], 1),
        "T_runner_corr_mean_ms": P(pkt, "summary", pa + ["T_runner_corr_ms", "mean"], 2),
        "S": NA("no BASE arm in this lane"),
        "S_keep_only": NA("no KEEP-only arm in this lane"),
        "n": P(pkt, "summary", pa + ["n"]),
        "validity": {"valid": P(pkt, "summary", ["phase_A", "valid"]), "n": P(pkt, "summary", ["phase_A", "n"]),
                     "verified": P(pkt, "summary", ["phase_A", "verified"]),
                     "e4": P(pkt, "summary", ["e4", "phase_A"])},
        "floor": NA("not computed by B-07 (E2 shares only)"),
        "cold_excess_mean_ms": P(pkt, "summary", pa + ["cold_excess_ms", "mean"], 2),
        "transport_corr_mean_ms": P(pkt, "summary", pa + ["groups", "transport_in_out", "corr", "mean"], 2),
        "components": b07_components(cls),
        "work_deleted": {
            "PREP_FAST_caller_work_ms": P(pkt, "summary", ["phase_B", "PREP_FAST", "by_class", cls, "prep_ms", "mean_diff"], 2),
            "carried": False,
            "note": ("fill DELETED is fragile (the first round is a training invocation; every alternative reading is "
                     "KILL); the knob is not carried, so no carried work is deleted" if cls == "fill"
                     else "PREP_FAST KILL; nothing carried"),
        },
        "wall_clock_saved": {"PREP_FAST_T_oracle_mean_diff_ms": P(pkt, "summary", ["phase_B", "PREP_FAST", "by_class", cls,
                                                                                   "T_oracle_ms", "mean_diff"], 2),
                             "ci95": P(pkt, "summary", ["phase_B", "PREP_FAST", "by_class", cls, "T_oracle_ms", "ci95"], 2),
                             "carried": False},
        "untested": {
            "A": P(pkt, "summary", e2 + ["corr:below_gate_as_irreducible", "a_r2_10_carry_over", "untested_share"], 4),
            "A_label": "R2-10 mapping, cold excess not untested, BELOW_GATE as IRREDUCIBLE",
            "A2": P(pkt, "summary", e2 + ["corr:below_gate_as_untested", "a_r2_10_carry_over", "untested_share"], 4),
            "A2_label": "R2-10 mapping, BELOW_GATE as UNTESTED",
            "B": (P(pkt, "summary", e2 + ["corr:below_gate_as_irreducible", "b_b04_cold_excess_untested", "untested_share"], 4)
                  if cls != "modal" else NA("modal cold excess is outside the B-04/B-06 gates")),
            "B_label": "B-04 mapping: cold excess UNTESTED",
        },
    }


def row_b05(cls):
    pkt = "B-05"
    pa = ["phase_A", "by_class", cls]
    e2 = ["e2", cls]
    return {
        "row_id": "%s/B5/B-05" % cls, "lane": "B-05", "source": "B5", "status": "ACCEPTED",
        "layer": "L-scripted, COMP only (MCP transport sub-spans on R2-10 source + marks)",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE)", "UNIT"],
        "best_arm": "COMP",
        "T_base_ms": NA("B-05 has no BASE arm"),
        "T_best_ms": P(pkt, "summary", pa + ["T_oracle_ms", "median"], 1),
        "T_runner_corr_mean_ms": P(pkt, "summary", pa + ["T_runner_corr_ms", "mean"], 2),
        "S": NA("no BASE arm in this lane"),
        "S_keep_only": NA("no KEEP-only arm in this lane"),
        "n": P(pkt, "summary", pa + ["n"]),
        "validity": {"valid": P(pkt, "summary", ["phase_A", "valid"]), "n": P(pkt, "summary", ["phase_A", "n"]),
                     "e4": P(pkt, "summary", ["e4"])},
        "floor": NA("not computed by B-05"),
        "transport_corr_mean_ms": P(pkt, "summary", pa + ["groups", "transport_in_out", "corr", "mean"], 2),
        "components": [
            {"component": "c_out.parse", "verdict": P(pkt, "summary", ["verdicts", "f.c_out.parse", cls]),
             "verdict_lane": "B-05", "PARSE_FAST_caller_ms_ci95": P(pkt, "summary", ["phase_B", "PARSE_FAST", "by_class", cls,
                                                                                    "caller_ms", "ci95"], 2)},
            {"component": "c_out.validate", "verdict": P(pkt, "summary", ["verdicts", "f.c_out.validate", cls]),
             "verdict_lane": "B-05", "VALIDATE_FAST_caller_ms_ci95": P(pkt, "summary", ["phase_B", "VALIDATE_FAST", "by_class",
                                                                                        cls, "caller_ms", "ci95"], 2)},
        ],
        "work_deleted": NA("PARSE_FAST and VALIDATE_FAST are KILL (below B-05's pre-registered gate); nothing carried", status="NONE"),
        "wall_clock_saved": NA("nothing carried", status="NONE"),
        "untested": {
            "A": P(pkt, "summary", e2 + ["corr:below_gate_as_irreducible", "untested_share"], 4),
            "A_label": "B-05 own mapping, BELOW_GATE as IRREDUCIBLE (before B-07 closed route/prep/post)",
            "A2": P(pkt, "summary", e2 + ["corr:below_gate_as_untested", "untested_share"], 4),
            "A2_label": "BELOW_GATE as UNTESTED",
        },
    }


def row_r207d(cls):
    pkt = "R2-07d"
    ps = ["phase_S", cls]
    return {
        "row_id": "%s/R/R2-07d" % cls, "lane": "R2-07d", "source": "R", "status": "ACCEPTED",
        "layer": "L-scripted quiet window (COMP vs COMP+CR compiled routine); live Phase L NOT_RUN",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE)", "UNIT", "LIVE_PROVIDER NOT_RUN"],
        "best_arm": "COMP (compiled routine excluded from the composed configuration)",
        "T_base_ms": NA("R2-07d compares COMP with COMP+CR, not BASE"),
        "T_COMP_ms": P(pkt, "summary", ps + ["timing", "median_T_COMP_ms"], 1),
        "T_COMP_CR_ms": P(pkt, "summary", ps + ["timing", "median_T_COMP_CR_ms"], 1),
        "CR_minus_COMP_median_ms": P(pkt, "summary", ps + ["timing", "diff_COMP_CR_minus_COMP_ms", "median"], 1),
        "CR_minus_COMP_ci95": P(pkt, "summary", ps + ["timing", "diff_COMP_CR_minus_COMP_ms", "ci95"], 1),
        "gate_ci_upper_le_2ms": P(pkt, "summary", ps + ["timing", "gate_ci_upper_le_2ms"]),
        "n_pairs": P(pkt, "summary", ps + ["timing", "valid_pairs"]),
        "S": NA("non-regression gate, not a speedup row"),
        "S_keep_only": NA("not applicable"),
        "validity": {"G3_pass": P(pkt, "summary", ps + ["G3", "pass"]), "E4_clean": P(pkt, "summary", ps + ["E4_clean"])},
        "floor": {"T_composed_mean_ms": P(pkt, "summary", ps + ["decomposition", "COMP", "mean_T_oracle_ms"], 2),
                  "T_irreducible_ms": P(pkt, "summary", ps + ["decomposition", "COMP", "irreducible_ms"], 2),
                  "floor_ratio": D(P(pkt, "summary", ps + ["decomposition", "COMP", "mean_T_oracle_ms"]),
                                   P(pkt, "summary", ps + ["decomposition", "COMP", "irreducible_ms"]), 2)},
        "components": [],
        "work_deleted": NA("compiled routine not carried for toggle/modal (Phase L NOT_RUN; modal gate FAIL)", status="NONE"),
        "wall_clock_saved": NA("nothing carried", status="NONE"),
        "untested": {"A": P(pkt, "summary", ps + ["decomposition", "COMP", "untested_share"], 4),
                     "A_label": "R2-07d's own COMP decomposition (R2-10 mapping, transport UNTESTED)"},
        "provider": {"attempts": P(pkt, "summary", ["provider", "attempts"]),
                     "reached": P(pkt, "summary", ["provider", "reached"])},
        "disposition": P(pkt, "summary", ["disposition", "disposition"]),
    }


# --------------------------------------------------------------------------------- native rows

def native_comp_r210(pkt, task, arm="X"):
    return comp_list_r210(pkt, "native", "%s/%s" % (task, arm), "R2-10 mapping (this packet)")


def native_work(pkt, task, arm="X"):
    base = ["native", "work_deleted_vs_wall_clock", "%s/%s" % (task, arm)]
    items = [{"component": "post_action_sleep", "why": "fixed post-DoAction sleep (N-01R H_S: DELETED, scoped)",
              "ms": P(pkt, "summary", base + ["component_mean_ms_deleted", "post_action_sleep"], 1)},
             {"component": "reveal", "why": "cursor reveal glide (N-01R H_C: OWNER_DECISION)",
              "ms": P(pkt, "summary", base + ["component_mean_ms_deleted", "reveal"], 1)}]
    return {"components_ms": items, "provider_requests_per_trial": NA("scripted chooser (no provider)", status="NONE"),
            "rule": "BASE minus X component mean for the components X removes"}


def row_r210_native(task, pkt="R2-10"):
    src = "R" if pkt == "R2-10" else "R'"
    s = ["native", "S", "X", task, "all"]
    s0 = ["native", "S", "S0", task, "all"]
    dk = ["native", "decomposition", "%s/X" % task]
    row = {
        "row_id": "%s/%s/%s" % (task, src, pkt), "lane": pkt, "source": src, "status": "ACCEPTED",
        "layer": "L-scripted (scripted chooser; native T excludes provider decisions)",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE, GTK3, private Xvfb + AT-SPI)"],
        "best_arm": "X (fast reveal + no post-DoAction sleep)",
        "T_base_ms": P(pkt, "summary", s + ["median_base_ms"], 1),
        "T_best_ms": P(pkt, "summary", s + ["median_arm_ms"], 1),
        "S": P(pkt, "summary", s + ["S"], 2),
        "S_ci95": P(pkt, "summary", s + ["ci95"], 2),
        "n_pairs": P(pkt, "summary", s + ["n"]),
        "S_keep_only": P(pkt, "summary", s0 + ["S"], 2),
        "S_keep_only_ci95": P(pkt, "summary", s0 + ["ci95"], 2),
        "floor": floor_r210(pkt, dk),
        "components": native_comp_r210(pkt, task),
        "work_deleted": native_work(pkt, task),
        "wall_clock_saved": {"median_paired_ms": P(pkt, "summary", ["native", "work_deleted_vs_wall_clock", "%s/X" % task,
                                                                    "wall_clock_saved_median_paired_ms"], 1),
                             "ci95": P(pkt, "summary", ["native", "work_deleted_vs_wall_clock", "%s/X" % task,
                                                        "wall_clock_saved_ci95"], 1)},
        "untested": {"A": P(pkt, "summary", dk + ["untested_share"], 4),
                     "A_label": "R2-10 mapping (observation transport IRREDUCIBLE)",
                     "B": NA("the conservative (N-02) reading was not computed on this source")},
        "T_land": {
            "BASE_median_ms": P(pkt, "summary", ["native", "arms", task, "BASE", "T_land_ms_median"], 1),
            "X_median_ms": P(pkt, "summary", ["native", "arms", task, "X", "T_land_ms_median"], 1),
            "BASE_T_oracle_median_ms": P(pkt, "summary", ["native", "arms", task, "BASE", "T_oracle_ms", "median"], 1),
            "X_T_oracle_median_ms": P(pkt, "summary", ["native", "arms", task, "X", "T_oracle_ms", "median"], 1),
        },
    }
    if pkt == "R2-10":
        row["validity"] = {a: P(pkt, "summary", ["gates", "validity", "shares", "native/%s/%s" % (task, a)], 3)
                           for a in ("BASE", "S0", "X")}
        row["validity"]["e4"] = P(pkt, "summary", ["native", "e4"])
        row["T_land"]["S_land"] = NA("paired S at T_land is not in R2-10's summary; the R2-10 verifier note "
                                     "on S_land is not recomputed here")
    else:
        row["validity"] = {a: P(pkt, "recert", ["validity_100", "shares", "native/%s/%s" % (task, a)], 3)
                           for a in ("BASE", "S0", "X")}
        row["validity"]["e4"] = P(pkt, "summary", ["native", "e4"])
        row["T_land"]["S_land_X"] = P(pkt, "summary", ["native", "S_land", "X", task, "all", "S"], 2)
        row["T_land"]["S_land_X_ci95"] = P(pkt, "summary", ["native", "S_land", "X", task, "all", "ci95"], 2)
        row["T_land"]["S_land_S0"] = P(pkt, "summary", ["native", "S_land", "S0", task, "all", "S"], 2)
    return row


def row_n04(task):
    pkt = "N-04"
    e3 = ["e3", task]
    e2p = ["e2", task, "primary_R2-10_reading"]
    e2c = ["e2", task, "conservative_N-02_reading"]
    meta = PACKETS[pkt]
    data = C.show_json(meta["sha"], meta["dir"] + "/" + meta["files"]["summary"])
    comps = C.resolve(data, e2p + ["components"])
    comp_rows = []
    for name in sorted(comps, key=lambda n: -comps[n]["mean_ms"]):
        if abs(comps[name]["mean_ms"]) < 0.5 and comps[name]["verdict"] != "OWNER_DECISION":
            continue
        comp_rows.append({"component": name,
                          "mean_ms": P(pkt, "summary", e2p + ["components", name, "mean_ms"], 2),
                          "share": P(pkt, "summary", e2p + ["components", name, "share"], 4),
                          "material": P(pkt, "summary", e2p + ["components", name, "above_threshold"]),
                          "verdict": P(pkt, "summary", e2p + ["components", name, "verdict"]),
                          "verdict_lane": "N-04 primary (R2-10 labels + V/HCL verdicts)"})
    work = data["e2"][task]["work_deleted_BASE_minus_best_ms"]
    wd = []
    for name, why in (("post_action_sleep", "post-DoAction sleep (DELETED, scoped)"),
                      ("reveal", "cursor reveal glide (OWNER_DECISION)"),
                      ("action_transport.admission_v", "admission tools-list cache V on the action call (DELETED)"),
                      ("observation_transport.admission_v", "admission tools-list cache V on the observation call (DELETED)")):
        if name in work:
            wd.append({"component": name, "why": why,
                       "ms": P(pkt, "summary", ["e2", task, "work_deleted_BASE_minus_best_ms", name], 2)})
    k1 = ["k1", "contrasts"]
    return {
        "row_id": "%s/R'n/N-04" % task, "lane": "N-04", "source": "R'n", "status": "ACCEPTED",
        "layer": "L-scripted (scripted chooser; native T excludes provider decisions)",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE, GTK3)", "UNIT"],
        "best_arm": P(pkt, "summary", e3 + ["best_composed"]),
        "T_base_ms": P(pkt, "summary", e3 + ["S_best", "median_base_ms"], 1),
        "T_best_ms": P(pkt, "summary", e3 + ["S_best", "median_arm_ms"], 1),
        "S": P(pkt, "summary", e3 + ["S_best", "S"], 3),
        "S_ci95": P(pkt, "summary", e3 + ["S_best", "ci95"], 3),
        "n_pairs": P(pkt, "summary", e3 + ["S_best", "n"]),
        "S_keep_only": P(pkt, "summary", e3 + ["S0_keep_only", "S"], 3),
        "S_keep_only_ci95": P(pkt, "summary", e3 + ["S0_keep_only", "ci95"], 3),
        "validity": {"k1_tasks": P(pkt, "summary", ["counts", "k1_tasks"]),
                     "k5_tasks": P(pkt, "summary", ["counts", "k5_tasks"]),
                     "best_arm_valid_share": P(pkt, "summary", ["k1", "cells", "%s/X+V+HCL" % task, "valid_share"], 3),
                     "e4_best_arm": P(pkt, "summary", ["e4", "X+V+HCL"])},
        "floor": {"T_composed_mean_ms": P(pkt, "summary", e2p + ["mean_T_ms"], 2),
                  "T_irreducible_ms": P(pkt, "summary", e2p + ["T_irreducible_ms"], 2),
                  "floor_ratio": P(pkt, "summary", e2p + ["floor_ratio"], 3),
                  "untested_ms": P(pkt, "summary", e2p + ["untested_ms"], 2)},
        "components": comp_rows,
        "work_deleted": {"components_ms": wd,
                         "V_admission_work_ms": P(pkt, "summary", k1 + ["%s/X-vs-X+V" % task, "work_admission_v_ms", "median"], 2),
                         "provider_requests_per_trial": NA("scripted chooser (no provider)", status="NONE"),
                         "rule": "BASE minus best-arm component mean, from the packet's own work_deleted table"},
        "wall_clock_saved": {"median_paired_ms": P(pkt, "summary", ["e2", task, "wall_clock_saved_BASE_minus_best_ms", "median"], 2),
                             "ci95": P(pkt, "summary", ["e2", task, "wall_clock_saved_BASE_minus_best_ms", "ci95"], 2),
                             "V_T_saved_k1_median_ms": P(pkt, "summary", k1 + ["%s/X-vs-X+V" % task, "wall_clock_T_ms", "median"], 2),
                             "V_T_saved_k1_ci95": P(pkt, "summary", k1 + ["%s/X-vs-X+V" % task, "wall_clock_T_ms", "ci95"], 2),
                             "HCL_k1_median_ms": P(pkt, "summary", k1 + ["%s/X+V-vs-X+V+HCL" % task, "wall_clock_T_ms", "median"], 2),
                             "HCL_k5_per_session_median_ms": P(pkt, "summary", ["k5", "contrasts", "%s/X+V-vs-X+V+HCL" % task,
                                                                                "sum_T_ms", "median"], 2)},
        "untested": {"A": P(pkt, "summary", e2p + ["untested_share"], 4),
                     "A_label": "primary R2-10 reading",
                     "B": P(pkt, "summary", e2c + ["untested_share"], 4),
                     "B_label": "conservative N-02 reading (observation-transport client validation counted)"},
        "T_land": {"S_land_best": P(pkt, "summary", e3 + ["S_land_best", "S"], 3),
                   "S_land_best_ci95": P(pkt, "summary", e3 + ["S_land_best", "ci95"], 3),
                   "best_T_land_median_ms": P(pkt, "summary", e3 + ["S_land_best", "median_arm_ms"], 2),
                   "BASE_T_land_median_ms": P(pkt, "summary", e3 + ["S_land_best", "median_base_ms"], 2),
                   "S0_land": P(pkt, "summary", e3 + ["S0_keep_only_land", "S"], 3)},
        "verdicts": {"V": P(pkt, "summary", ["gates", "V", "verdict"]),
                     "HCL": P(pkt, "summary", ["gates", "HCL/%s" % task, "verdict"])},
    }


def row_n03(task):
    pkt = "N-03"
    e2p = ["e2", task, "primary_R2-10_reading"]
    e2c = ["e2", task, "conservative_N-02_reading"]
    g = ["gates"]
    row = {
        "row_id": "%s/N3/N-03" % task, "lane": "N-03", "source": "N3", "status": "ACCEPTED",
        "layer": "L-scripted (superseded for E2/E3 by N-04 on R'n)",
        "evidence_class": ["REAL", "BENCHMARK (FIXTURE, GTK3)", "UNIT"],
        "best_arm": P(pkt, "summary", ["e2", task, "best_arm"]),
        "T_base_ms": NA("N-03 Part A has no BASE arm"),
        "T_best_mean_ms": P(pkt, "summary", e2p + ["mean_T_ms"], 2),
        "S": NA("no BASE arm in Part A"),
        "S_keep_only": NA("not measured in N-03"),
        "floor": {"T_composed_mean_ms": P(pkt, "summary", e2p + ["mean_T_ms"], 2),
                  "T_irreducible_ms": P(pkt, "summary", e2p + ["T_irreducible_ms"], 2),
                  "floor_ratio": P(pkt, "summary", e2p + ["floor_ratio"], 3)},
        "components": [],
        "work_deleted": {"V_admission_work_ms": P(pkt, "summary", g + ["V/%s" % task, "work_admission_v_ms", "median"], 2),
                         "provider_requests_per_trial": NA("scripted chooser (no provider)", status="NONE")},
        "wall_clock_saved": {"V_T_saved_median_ms": P(pkt, "summary", g + ["V/%s" % task, "wall_clock_T_ms", "median"], 2),
                             "V_T_saved_ci95": P(pkt, "summary", g + ["V/%s" % task, "wall_clock_T_ms", "ci95"], 2),
                             "HCL_k5_per_session_median_ms": P(pkt, "summary", g + ["HCL/%s" % task, "k5_session_saving_ms",
                                                                                    "median"], 2)},
        "untested": {"A": P(pkt, "summary", e2p + ["untested_share"], 4), "A_label": "primary R2-10 reading",
                     "B": P(pkt, "summary", e2c + ["untested_share"], 4), "B_label": "conservative N-02 reading"},
        "verdicts": {"V": P(pkt, "summary", g + ["V/%s" % task, "verdict"]),
                     "HCL": P(pkt, "summary", g + ["HCL/%s" % task, "verdict"])},
        "validity": {"hcl_rows_valid_verified": P(pkt, "summary", g + ["HCL/%s" % task, "hcl_rows_valid_verified"]),
                     "hcl_rows": P(pkt, "summary", g + ["HCL/%s" % task, "hcl_rows"])},
    }
    if task == "checkbox":
        row["ax_fg_S0"] = {
            "verdict": P(pkt, "summary", ["gates", "axfg_S0/D", "verdict"]),
            "click_wrapper_saved_median_ms": P(pkt, "summary", ["part_b", "D/checkbox", "click_wrapper_saved_ms", "median"], 2),
            "ci95": P(pkt, "summary", ["part_b", "D/checkbox", "click_wrapper_saved_ms", "ci95"], 2),
            "n": P(pkt, "summary", ["part_b", "D/checkbox", "click_wrapper_saved_ms", "n"]),
            "post_action_wait_median_ms": P(pkt, "summary", ["part_b", "D/checkbox", "post_action_wait_median_ms"], 2),
            "note": "X11 ax_fg route at the default config; Part B is not order-counterbalanced (bound disclosed in the N-03 packet)",
        }
    return row


def pending(row_id, lane, source, why):
    return {"row_id": row_id, "lane": lane, "source": source, "status": "PENDING",
            "pending_reason": why, "refresh": "wave 7"}


# ------------------------------------------------------------------------------------ assemble

def build():
    blocks = []
    for cls, title in (("fill", "Browser fill -> submit (jev-use, kvnloo/cua#24 class)"),
                       ("toggle", "Browser toggle -> confirm (jev-use, kvnloo/cua#24 class)"),
                       ("modal", "Browser modal -> act (jev-use, kvnloo/cua#24 class)")):
        rows = [row_r210_browser(cls, "live"), row_r210_browser(cls, "scripted")]
        if cls == "fill":
            rows.append({"row_id": "fill/R/R2-07d", "lane": "R2-07d", "source": "R", "status": "NOT_APPLICABLE",
                         "reason": "R2-07d covers toggle/modal only; the fill compiled replay (R2-07b, re-qualified by "
                                   "FIX-01) is already inside R2-10's fill COMP arm"})
        else:
            rows.append(row_r207d(cls))
        rows.append(row_r210r_browser(cls))
        rows.append(row_b06(cls))
        rows.append(row_b07(cls))
        rows.append(pending("%s/B7/B-08" % cls, "B-08", "B7", PENDING_W6["B-08"]))
        rows.append(row_b05(cls))
        if cls != "fill":
            rows.append(pending("%s/R/R2-07e" % cls, "R2-07e", "R", PENDING_W6["R2-07e"]))
        blocks.append({"task": "browser_" + cls, "title": title, "rows": rows})
    for task, title in (("checkbox", "Native GTK3 checkbox toggle (canonical fixture)"),
                        ("text", "Native GTK3 text entry (canonical fixture)")):
        rows = [row_r210_native(task, "R2-10"), row_r210_native(task, "R2-10R"), row_n04(task), row_n03(task)]
        blocks.append({"task": "native_" + task, "title": title, "rows": rows})

    packets = {}
    for k, m in PACKETS.items():
        packets[k] = {kk: vv for kk, vv in m.items() if kk not in ("binary_path",)}
        packets[k]["binary_sha256"] = P(k, "provenance", m["binary_path"])
    doc = {
        "schema": "cua-rfc-10-final-accounting/v1",
        "lane": "DOC-10-74 (wave 6)",
        "owners": ["kvnloo/cua#10", "kvnloo/cua#73", "kvnloo/cua#74"],
        "rules": [
            "One row per SOURCE (binary). Never add or ratio numbers across rows or sources.",
            "Cross-lane readings combine verdicts, never numbers.",
            "T is the median T_oracle unless a field says mean; components are mean ms.",
            "Work deleted (ms of removed work; provider requests removed) is reported separately from wall-clock saved.",
            "Every number is a pointer {value, from} into an accepted packet at an exact commit.",
            "PENDING rows can still move in wave 6 and are refreshed in wave 7.",
        ],
        "sources": {
            "R": "989cc76ce + R2-10 steps 1-8, binary 12b9045a (R2-10 L-live, R2-10 L-scripted, R2-07d, B-04)",
            "R'": "0f1955d2f + R2-10 steps 1-8 (45dff8f32), binary 922111c5 (R2-10R, B-06)",
            "B7": "R' + B-07 marks + POST_FAST knob, binary 6f95aef5 (B-07; B-08 PENDING)",
            "R'n": "R' + N-02 marks + focus-guard clamp knob (11a03bf51), binary 78a1137d (N-04)",
            "B5": "R2-10 source + B-05 marks (b376f1ff3), binary f4149bdd (B-05)",
            "N3": "R2-10 source + N-03 marks/knobs (85a73c2c7), binary b1843871 (N-03)",
        },
        "untested_mappings": {
            "browser": {
                "A": "R2-10 mapping: cold first-snapshot excess counted inside IRREDUCIBLE observation; on B7, "
                     "BELOW_GATE sub-spans counted IRREDUCIBLE (A2 counts them UNTESTED)",
                "B": "B-04 mapping: cold excess counted UNTESTED (per-process part UNDECIDED under B-06's PREREG; "
                     "B-06's post-hoc amended reading would make it OWNER_DECISION - owner's call)",
            },
            "native": {"A": "primary R2-10 reading (observation transport IRREDUCIBLE)",
                       "B": "conservative N-02 reading (observation-transport client validation and buckets counted)"},
        },
        "packets": packets,
        "blocks": blocks,
        "owner_decision_dependency": {
            "statement_template": "The large browser speedups depend on owner decisions. With KEEP-only deletions "
                                  "(feedback glide, H_T settle and endpoint re-proof left at their defaults), browser S "
                                  "is about {R2-10_fill} (fill amortized ratio of means {R2-10_fill_amortized}); native "
                                  "KEEP-only S is about {N-04_checkbox} checkbox and {N-04_text} text (cursor reveal "
                                  "left at its default).",
            "browser_keep_only": {
                "R2-10_fill": P("R2-10", "summary", ["browser", "scripted", "S", "COMP_K", "fill", "all", "S"], 2),
                "R2-10_fill_amortized": P("R2-10", "summary", ["browser", "scripted", "S", "COMP_K", "fill",
                                                               "amortized_mean_ratio", "S"], 2),
                "R2-10_toggle": P("R2-10", "summary", ["browser", "scripted", "S", "COMP_K", "toggle", "all", "S"], 2),
                "R2-10_modal": P("R2-10", "summary", ["browser", "scripted", "S", "COMP_K", "modal", "all", "S"], 2),
                "R2-10R_fill": P("R2-10R", "summary", ["browser", "scripted", "S", "COMP_K", "fill", "all", "S"], 2),
                "R2-10R_fill_amortized": P("R2-10R", "summary", ["browser", "scripted", "S", "COMP_K", "fill",
                                                                 "amortized_mean_ratio", "S"], 2),
            },
            "native_keep_only": {
                "N-04_checkbox": P("N-04", "summary", ["e3", "checkbox", "S0_keep_only", "S"], 3),
                "N-04_text": P("N-04", "summary", ["e3", "text", "S0_keep_only", "S"], 3),
                "R2-10_checkbox": P("R2-10", "summary", ["native", "S", "S0", "checkbox", "all", "S"], 2),
                "R2-10_text": P("R2-10", "summary", ["native", "S", "S0", "text", "all", "S"], 2),
            },
            "owner_items": [
                "browser feedback glide off/fast (B-01; the single largest component of default BASE T, see the "
                "visualization entry under work deleted)",
                "B-01 H_T insert_text focus settle",
                "B-02 H_E endpoint re-proof bound check (security policy)",
                "native cursor reveal (N-01R H_C; the native text speedup over KEEP-only S comes from it)",
                "HCL lazy validators (session shape)",
                "B-06 amended reading of the per-process cold excess",
                "R2-08 API route per task",
            ],
        },
        "references_only": [
            {"name": "PreAct", "reported": "8.5-13x warm replay acceleration",
             "differences": [
                 "benchmark: PreAct's own small benchmark subsets, not the jev-use fixture classes or the GTK3 fixture",
                 "scope: warm replay of compiled programs only; this table's S is whole-task verified time (first "
                 "observation to independent oracle) over every invocation, including first-run/compile/admission and fallback",
                 "baseline: PreAct's baseline is its own agent loop; this table's BASE is the default Driver path "
                 "with feedback glide on, so most of our S comes from owner-decision deletions, not replay",
                 "verification: PreAct checks compiled programs before storage; our compiled routine (R2-07b) also needs "
                 "fresh authority per replayed mutation; out-of-domain reuse degrades in PreAct and is not claimed here",
                 "provider: our live rows use TypeSafe; scripted rows use no provider",
             ], "use": "reference only, never a gate or a target"},
            {"name": "SkillDroid", "reported": "about 2.4x, pure replay only",
             "differences": [
                 "35 pure replay rounds were zero-LLM, not all 79 Layer-2 rounds (SkillDroid section 5.1, Tables 2-3, "
                 "as recorded on kvnloo/cua#93); the other Layer-2 paths include model-assisted matching or step fallback",
                 "benchmark: Android app tasks, not jev-use browser classes or GTK3",
                 "scope: pure replay subset, not a whole-workload or CUA speedup; this table measures all attempted invocations",
             ], "use": "reference only, never a gate or a target"},
        ],
        "live_layer_gaps": [
            {"gap": "R' live layer (R2-10 recertification with TypeSafe on 0f1955d2f)", "status": "BLOCKED",
             "blocker": "paid budget: the loop's remaining TypeSafe budget does not cover a live recertification "
                        "(kvnloo/cua#74 OR-11; figures in the queue's state extract)",
             "consequence": "live rows exist only on R (989cc76ce); R' rows are scripted"},
            {"gap": "live toggle/modal provider decisions (the largest live COMP component in R2-10)", "status": "UNTESTED",
             "blocker": "BLOCKED by budget; modal also needs a passing non-regression gate (R2-07d modal FAIL)",
             "refs": {"toggle_provider_ms": P("R2-10", "summary", ["browser", "live", "decomposition", "toggle/COMP",
                                                                   "components", "provider_decision", "mean_ms"], 1),
                      "toggle_provider_share": P("R2-10", "summary", ["browser", "live", "decomposition", "toggle/COMP",
                                                                      "components", "provider_decision", "share"], 4),
                      "modal_provider_ms": P("R2-10", "summary", ["browser", "live", "decomposition", "modal/COMP",
                                                                  "components", "provider_decision", "mean_ms"], 1),
                      "modal_provider_share": P("R2-10", "summary", ["browser", "live", "decomposition", "modal/COMP",
                                                                     "components", "provider_decision", "share"], 4)}},
            {"gap": "R2-07e (new pre-registered modal gate + Phase L)", "status": "PENDING",
             "blocker": "wave-6 lane running; refresh in wave 7"},
            {"gap": "native live arms (native T including provider decisions)", "status": "BLOCKED",
             "blocker": "owner decision (may native T exclude provider decisions?) or paid budget"},
        ],
        "pending_w6": PENDING_W6,
    }
    doc["owner_decision_dependency"]["statement"] = statement(doc["owner_decision_dependency"])
    return doc


def statement(odd):
    vals = {}
    for grp in ("browser_keep_only", "native_keep_only"):
        for k, x in odd[grp].items():
            vals[k] = C.fmt(x["value"], x["from"]["round"])
    return odd["statement_template"].format(**vals)


# ----------------------------------------------------------------------------------- rendering

def v(x, nd=None, pct=False):
    if isinstance(x, dict):
        if "value" in x:
            val = x["value"]
            meta = x.get("from") or x.get("derived") or {}
            if pct:
                return C.fmt(val, (meta.get("round") or 4), pct=True)
            out = C.fmt(val, meta.get("round") if nd is None else nd)
            return out + (" (derived)" if "derived" in x else "")
        if "status" in x:
            return x["status"]
        if "text" in x:
            return x["text"]
    if x is None:
        return "n/a"
    return C.fmt(x, nd, pct)


def ci(x):
    if isinstance(x, dict) and "value" in x:
        return C.fmt(x["value"], (x.get("from") or x.get("derived"))["round"])
    return ""


def s_cell(row, key="S"):
    s = row.get(key)
    if isinstance(s, dict) and "value" in s:
        c = row.get(key + "_ci95")
        return v(s) + (" " + ci(c) if c else "")
    return v(s)


def untested_cell(row):
    u = row.get("untested") or {}
    parts = []
    for k in ("A", "A2", "B"):
        if k in u:
            parts.append("%s %s" % (k, v(u[k], pct=True) if isinstance(u[k], dict) and "value" in u[k] else v(u[k])))
    return "; ".join(parts) if parts else "n/a"


def floor_cell(row):
    f = row.get("floor")
    if isinstance(f, dict) and "T_irreducible_ms" in f:
        r = f.get("floor_ratio")
        return "%s / %s = %s" % (v(f["T_composed_mean_ms"]), v(f["T_irreducible_ms"]), v(r) if r else "n/a")
    return v(f)


def t_cell(row):
    if "T_best_ms" in row:
        return v(row["T_best_ms"])
    if "T_COMP_ms" in row:
        return "COMP %s / CR %s" % (v(row["T_COMP_ms"]), v(row["T_COMP_CR_ms"]))
    if "T_arms_ms" in row:
        a = row["T_arms_ms"]
        return "C %s / Wa %s" % (v(a["C"]), v(a["Wa"]))
    if "T_best_mean_ms" in row:
        return "mean %s" % v(row["T_best_mean_ms"])
    return "n/a"


def n_cell(row):
    for k in ("n_pairs", "n", "n_per_arm"):
        if k in row:
            return v(row[k])
    if "validity" in row and "k1_tasks" in row["validity"]:
        return "k1 %s" % v(row["validity"]["k1_tasks"])
    return "n/a"


def validity_cell(row):
    val = row.get("validity") or {}
    bits = []
    for k, x in val.items():
        if isinstance(x, dict) and "value" in x and not isinstance(x["value"], dict):
            bits.append("%s %s" % (k, C.fmt(x["value"], x["from"].get("round"))))
        elif isinstance(x, dict) and "value" in x and isinstance(x["value"], dict):
            bad = sum(int(vv) for kk, vv in x["value"].items()
                      if isinstance(vv, (int, float)) and not isinstance(vv, bool) and kk not in ("rows", "n", "cells", "tasks"))
            bits.append("%s %d violations" % (k, bad))
    return "; ".join(bits) if bits else "n/a"


def work_cell(row):
    w = row.get("work_deleted")
    if not isinstance(w, dict):
        return "n/a"
    if "status" in w:
        return "%s (%s)" % (w["status"], w["reason"])
    bits = []
    for it in w.get("components_ms", []):
        val = it["ms"]["value"]
        if isinstance(val, (int, float)) and val >= 1.0:
            bits.append("%s %s" % (it["component"], v(it["ms"])))
    if "V_admission_work_ms" in w:
        bits.append("V admission work %s" % v(w["V_admission_work_ms"]))
    if "PREP_FAST_caller_work_ms" in w:
        bits.append("PREP_FAST %s (not carried)" % v(w["PREP_FAST_caller_work_ms"]))
    pr = w.get("provider_requests_per_trial")
    if isinstance(pr, dict) and "BASE" in pr:
        bits.append("provider requests/trial %s -> %s" % (v(pr["BASE"]), v(pr["COMP"])))
    return "; ".join(bits) if bits else "none"


def wall_cell(row):
    w = row.get("wall_clock_saved")
    if not isinstance(w, dict):
        return "n/a"
    if "status" in w:
        return w["status"]
    if "median_paired_ms" in w:
        return "%s %s" % (v(w["median_paired_ms"]), ci(w["ci95"]))
    if "PREP_FAST_T_oracle_mean_diff_ms" in w:
        return "PREP_FAST %s %s (not carried)" % (v(w["PREP_FAST_T_oracle_mean_diff_ms"]), ci(w["ci95"]))
    if "V_T_saved_median_ms" in w:
        return "V %s %s" % (v(w["V_T_saved_median_ms"]), ci(w["V_T_saved_ci95"]))
    return "n/a"


def comp_lines(row):
    out = []
    for cpt in row.get("components", []):
        if "mean_ms" in cpt:
            val = cpt["mean_ms"]["value"]
            if not (cpt.get("material", {}).get("value") or (isinstance(val, (int, float)) and abs(val) >= 1.0)):
                continue
            share = cpt.get("share")
            out.append("%s %s ms%s: %s (%s)" % (
                cpt["component"], v(cpt["mean_ms"]),
                (" (" + v(share, pct=True) + ")") if share else "",
                v(cpt["verdict"]), cpt["verdict_lane"]))
        else:
            extra = [k for k in cpt if k.endswith("_ci95")]
            out.append("%s: %s (%s)%s" % (cpt["component"], v(cpt["verdict"]), cpt["verdict_lane"],
                                          "".join("; %s %s" % (k, ci(cpt[k])) for k in extra)))
    return out


def render(doc):
    L = [BEGIN, ""]
    L.append("Sources: " + "; ".join("**%s** = %s" % (k, s) for k, s in doc["sources"].items()) + ".")
    L.append("")
    for b in doc["blocks"]:
        L.append("### %s" % b["title"])
        L.append("")
        L.append("| Row (lane, source) | Evidence | n | Validity / E4 | BASE T | Best T | S [CI] | KEEP-only S | "
                 "Floor T_comp / T_irr | Untested (A; A2; B) | Work deleted | Wall-clock saved |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in b["rows"]:
            if r["status"] in ("PENDING", "NOT_APPLICABLE"):
                L.append("| %s (%s) **%s** | - | - | - | - | - | - | - | - | - | - | %s |" % (
                    r["lane"], r["source"], r["status"], r.get("pending_reason") or r.get("reason")))
                continue
            keep = s_cell(r, "S_keep_only")
            if "S_keep_only_amortized" in r:
                keep += "; amortized %s %s" % (v(r["S_keep_only_amortized"]), ci(r["S_keep_only_amortized_ci95"]))
            sc = s_cell(r)
            if "S_amortized" in r:
                sc += "; amortized %s %s" % (v(r["S_amortized"]), ci(r["S_amortized_ci95"]))
            L.append("| %s (%s), %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                r["lane"], r["source"], r["layer"], ", ".join(r["evidence_class"]), n_cell(r), validity_cell(r),
                v(r.get("T_base_ms")), t_cell(r), sc, keep, floor_cell(r), untested_cell(r), work_cell(r), wall_cell(r)))
        L.append("")
        for r in b["rows"]:
            if r["status"] != "ACCEPTED":
                continue
            lines = comp_lines(r)
            extra = []
            if "cold_excess" in r:
                ce = r["cold_excess"]
                extra.append("cold excess E_R' %s ms; D (C-Wa) %s %s; PC %s; primary verdict %s" % (
                    v(ce["E_R'_mean_ms"]), v(ce["D_C_minus_Wa_median_ms"]), ci(ce["D_ci"]),
                    v(ce["PC_P_minus_Wa_median_ms"]), v(ce["verdict_primary"])))
                if "amended_D_median_ms" in ce:
                    extra.append("post-hoc amendment: D %s %s -> %s (owner's call)" % (
                        v(ce["amended_D_median_ms"]), ci(ce["amended_D_ci"]), v(ce["verdict_amended_post_hoc"])))
            if "cold_excess_mean_ms" in r:
                extra.append("cold excess mean %s ms (per-process part UNDECIDED, B-06); transport in/out corrected %s ms"
                             % (v(r["cold_excess_mean_ms"]), v(r["transport_corr_mean_ms"])))
            if "CR_minus_COMP_median_ms" in r:
                extra.append("CR - COMP %s %s ms; gate (CI upper <= +2.0) %s; disposition %s" % (
                    v(r["CR_minus_COMP_median_ms"]), ci(r["CR_minus_COMP_ci95"]), v(r["gate_ci_upper_le_2ms"]),
                    v(r["disposition"])))
            if "T_land" in r:
                tl = r["T_land"]
                if "BASE_median_ms" in tl:
                    extra.append("T_land vs T_oracle (medians): BASE %s vs %s ms; X %s vs %s ms" % (
                        v(tl["BASE_median_ms"]), v(tl["BASE_T_oracle_median_ms"]), v(tl["X_median_ms"]),
                        v(tl["X_T_oracle_median_ms"])))
                if "S_land_X" in tl:
                    extra.append("S at T_land: X %s %s, S0 %s" % (v(tl["S_land_X"]), ci(tl["S_land_X_ci95"]), v(tl["S_land_S0"])))
                if "S_land" in tl:
                    extra.append("S at T_land: %s" % tl["S_land"]["reason"])
                if "S_land_best" in tl:
                    extra.append("T_land (medians) BASE %s / best %s ms; S at T_land best %s %s, KEEP-only %s" % (
                        v(tl["BASE_T_land_median_ms"]), v(tl["best_T_land_median_ms"]), v(tl["S_land_best"]),
                        ci(tl["S_land_best_ci95"]), v(tl["S0_land"])))
            if "verdicts" in r:
                extra.append("verdicts: " + ", ".join("%s %s" % (k, v(x)) for k, x in r["verdicts"].items()))
            if "ax_fg_S0" in r:
                a = r["ax_fg_S0"]
                extra.append("ax_fg S0: %s; click wrapper saved %s %s ms (n=%s); %s" % (
                    v(a["verdict"]), v(a["click_wrapper_saved_median_ms"]), ci(a["ci95"]), v(a["n"]), a["note"]))
            ws = r.get("wall_clock_saved") or {}
            if "HCL_k5_per_session_median_ms" in ws:
                extra.append("HCL per 5-task session %s ms%s" % (
                    v(ws["HCL_k5_per_session_median_ms"]),
                    ("; HCL at k=1 %s ms" % v(ws["HCL_k1_median_ms"])) if "HCL_k1_median_ms" in ws else ""))
            if "V_T_saved_k1_median_ms" in ws:
                extra.append("V T saved (k=1) %s %s ms" % (v(ws["V_T_saved_k1_median_ms"]), ci(ws["V_T_saved_k1_ci95"])))
            if "amortized_ms" in r:
                am = r["amortized_ms"]
                extra.append("warm-up outside T %s ms; k=1 %s ms; k=5 %s ms per task" % (
                    v(am["warmup_outside_T"]), v(am["k1_T_Wa_plus_warmup"]), v(am["k5_per_task"])))
            if lines or extra:
                tag = r["row_id"].split("/")[-1]
                L.append("- **%s (%s)** components (mean ms, material or >= 1 ms): %s" % (
                    tag, r["source"], "; ".join(lines) if lines else "none decomposed in this lane"))
                ul = r.get("untested") or {}
                labs = ["%s = %s" % (k[0:-6], ul[k]) for k in ("A_label", "A2_label", "B_label") if k in ul]
                if "B_lane" in ul:
                    labs.append("B from %s" % ul["B_lane"])
                if "B_note" in ul:
                    labs.append(ul["B_note"])
                if labs:
                    extra.insert(0, "untested mappings: " + "; ".join(labs))
                for e in extra:
                    L.append("  - %s" % e)
        L.append("")
    odd = doc["owner_decision_dependency"]
    L.append("### Owner-decision dependency")
    L.append("")
    L.append(odd["statement"])
    L.append("")
    L.append("- Browser KEEP-only S: " + ", ".join("%s %s" % (k, v(x)) for k, x in odd["browser_keep_only"].items()) + ".")
    L.append("- Native KEEP-only S: " + ", ".join("%s %s" % (k, v(x)) for k, x in odd["native_keep_only"].items()) + ".")
    L.append("- Owner items behind the difference: " + "; ".join(odd["owner_items"]) + ".")
    L.append("")
    L.append("### Live-layer gaps")
    L.append("")
    for g in doc["live_layer_gaps"]:
        refs = g.get("refs")
        rs = (" (" + ", ".join("%s %s" % (k, v(x, pct=k.endswith("share"))) for k, x in refs.items()) + ")") if refs else ""
        L.append("- **%s: %s.** %s%s" % (g["gap"], g["status"], g["blocker"], rs))
    L.append("")
    L.append("### References only (never gates or targets)")
    L.append("")
    for ref in doc["references_only"]:
        L.append("- **%s** reports %s. Differences from this table:" % (ref["name"], ref["reported"]))
        for d in ref["differences"]:
            L.append("  - %s" % d)
    L.append("")
    L.append(END)
    return "\n".join(L)


def main():
    doc = build()
    with open(OUT_JSON, "w") as f:
        json.dump(doc, f, indent=1, sort_keys=False)
        f.write("\n")
    gen = render(doc)
    if os.path.exists(README):
        txt = open(README).read()
        if BEGIN in txt and END in txt:
            pre = txt.split(BEGIN)[0]
            post = txt.split(END)[1]
            txt = pre + gen + post
        else:
            txt = txt + "\n" + gen + "\n"
    else:
        txt = gen + "\n"
    with open(README, "w") as f:
        f.write(txt)
    n = sum(1 for _ in C.walk_pointers(doc))
    print("accounting.json written: %d pointers, %d blocks" % (n, len(doc["blocks"])))


if __name__ == "__main__":
    main()
