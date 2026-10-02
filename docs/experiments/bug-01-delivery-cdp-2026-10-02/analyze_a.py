"""BUG-01 part A analysis: recompute every part A number from raw/part-a/.

usage: analyze_a.py [packet_dir]  -> prints the part A summary JSON
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

FIELDS = ("effect", "route", "delivery_mode", "delivered_count", "evidence", "escalation", "error", "summary_template")


def receipt(structured: dict[str, Any] | None) -> dict[str, Any] | None:
    if not structured:
        return None
    delivery = structured.get("delivery") or {}
    summary = structured.get("summary")
    return {
        "effect": structured.get("effect"),
        "route": structured.get("route"),
        "delivery_mode": delivery.get("mode") if structured.get("delivery") is not None else None,
        "delivered_count": delivery.get("delivered_count"),
        "evidence": json.dumps(structured.get("evidence"), sort_keys=True),
        "escalation": json.dumps(structured.get("escalation"), sort_keys=True),
        "error": json.dumps(structured.get("error"), sort_keys=True),
        "summary_template": re.sub(r"\d+(\.\d+)?", "#", re.sub(r"tab-[0-9a-f-]+", "tab-<id>", summary)) if isinstance(summary, str) else None,
    }


def is_submit(target: str | None) -> bool:
    return bool(target) and target.startswith("button[type=submit]")


def window_id_from(focus: dict[str, Any] | None) -> int | None:
    if not focus:
        return None
    raw = focus.get("active_window")
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


def trial_row(rec: dict[str, Any]) -> dict[str, Any]:
    journal = rec.get("journal") or []
    page = [j for j in journal if j.get("source") == "page"]
    pdown = [j for j in page if j.get("kind") == "pointerdown" and is_submit(j.get("target"))]
    clicks = [j for j in page if j.get("kind") == "click" and is_submit(j.get("target"))]
    posts = [j for j in journal if j.get("source") == "target" and j.get("kind") == "submit_post"]
    token = rec.get("token") or ""
    inputs = [j for j in page if j.get("kind") == "input"]
    win = rec.get("browser_window_id")
    pre, post = window_id_from(rec.get("focus_pre")), window_id_from(rec.get("focus_post"))
    click = rec.get("click") or {}
    typed = rec.get("type") or {}
    oracle = rec.get("oracle") or {}
    trusted_fg = bool(pdown) and all(p.get("is_trusted") is True and p.get("has_focus") is True and p.get("visibility") == "visible" for p in pdown[:1]) and bool(clicks) and clicks[0].get("is_trusted") is True and pre == win and post == win
    return {
        "trial": rec["trial"],
        "arm": rec["arm"],
        "block": rec["block"],
        "click_accepted": click.get("accepted"),
        "click_receipt": receipt(click.get("structured")),
        "type_accepted": typed.get("accepted"),
        "type_receipt": receipt(typed.get("structured")),
        "page_pointerdown_submit": len(pdown),
        "page_pointerdown_trusted": bool(pdown) and pdown[0].get("is_trusted") is True,
        "page_has_focus_at_pointerdown": bool(pdown) and pdown[0].get("has_focus") is True,
        "page_visible_at_pointerdown": bool(pdown) and pdown[0].get("visibility") == "visible",
        "page_click_submit": len(clicks),
        "page_click_trusted": bool(clicks) and clicks[0].get("is_trusted") is True,
        "x11_active_is_browser_pre": pre == win,
        "x11_active_is_browser_post": post == win,
        "page_trusted_foreground": trusted_fg,
        "type_effect_observed": any(j.get("value_len") == len(token) for j in inputs),
        "type_input_trusted": bool(inputs) and all(j.get("is_trusted") is True for j in inputs),
        "posts": len(posts),
        "verified": oracle.get("first_verified_after_tool_ms") is not None,
        "final_state_null": (oracle.get("final") or {}).get("submitted") is None,
    }


def load(raw: Path, label: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows, errors = [], []
    for path in sorted(raw.glob(f"{label}-*.jsonl")):
        for line in path.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("event") == "trial":
                rows.append(trial_row(rec))
            else:
                errors.append(rec)
    return rows, errors


def tally(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    return dict(Counter(str(r[key]) for r in rows))


def arm_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    by_arm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)
    for arm, rs in sorted(by_arm.items()):
        out[arm] = {
            "n": len(rs),
            "click_accepted": sum(1 for r in rs if r["click_accepted"]),
            "click_delivery_mode": dict(Counter(str((r["click_receipt"] or {}).get("delivery_mode")) for r in rs if arm != "Y")),
            "click_route": dict(Counter(str((r["click_receipt"] or {}).get("route")) for r in rs if arm != "Y")),
            "click_effect": dict(Counter(str((r["click_receipt"] or {}).get("effect")) for r in rs if arm != "Y")),
            "type_accepted": sum(1 for r in rs if r["type_accepted"]),
            "type_delivery_mode": dict(Counter(str((r["type_receipt"] or {}).get("delivery_mode")) for r in rs)),
            "type_route": dict(Counter(str((r["type_receipt"] or {}).get("route")) for r in rs)),
            "page_trusted_foreground": sum(1 for r in rs if r["page_trusted_foreground"]),
            "page_pointerdown_trusted": sum(1 for r in rs if r["page_pointerdown_trusted"]),
            "page_click_submit": sum(1 for r in rs if r["page_click_submit"]),
            "page_click_trusted": sum(1 for r in rs if r["page_click_trusted"]),
            "x11_active_is_browser_pre_and_post": sum(1 for r in rs if r["x11_active_is_browser_pre"] and r["x11_active_is_browser_post"]),
            "type_effect_observed": sum(1 for r in rs if r["type_effect_observed"]),
            "type_input_trusted": sum(1 for r in rs if r["type_input_trusted"]),
            "verified": sum(1 for r in rs if r["verified"]),
            "final_state_null": sum(1 for r in rs if r["final_state_null"]),
            "posts_total": sum(r["posts"] for r in rs),
            "mislabel_trusted_fg_as_background": sum(1 for r in rs if r["click_accepted"] and r["page_trusted_foreground"] and (r["click_receipt"] or {}).get("delivery_mode") == "background"),
        }
    return out


def field_dist(rows: list[dict[str, Any]], which: str) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = defaultdict(dict)
    for arm in sorted({r["arm"] for r in rows}):
        rs = [r for r in rows if r["arm"] == arm and r[which]]
        if not rs:
            continue
        for f in FIELDS:
            out[arm][f] = dict(Counter(str(r[which][f]) for r in rs))
    return dict(out)


def main(packet: Path) -> dict[str, Any]:
    raw = packet / "raw" / "part-a"
    summary: dict[str, Any] = {"schema": "cua.bug01.part_a.summary.v1"}
    dists = {}
    for label in ("baseline", "fix"):
        rows, errors = load(raw, label)
        if not rows and not errors:
            continue
        env_path = raw / f"{label}-session-env.json"
        env = json.loads(env_path.read_text()) if env_path.exists() else {}
        summary[label] = {
            "driver_sha256": env.get("driver_sha256"),
            "driver_version_in_session": env.get("driver_version_in_session"),
            "chrome_version_in_session": env.get("chrome_version_in_session"),
            "trials": len(rows),
            "harness_errors": len(errors),
            "arms": arm_summary(rows),
        }
        dists[label] = {"click": field_dist(rows, "click_receipt"), "type": field_dist(rows, "type_receipt")}
    if "baseline" in dists and "fix" in dists:
        changed: list[dict[str, Any]] = []
        for which in ("click", "type"):
            for arm, fields in dists["baseline"][which].items():
                for f, dist in fields.items():
                    other = dists["fix"][which].get(arm, {}).get(f)
                    if other != dist:
                        changed.append({"receipt": which, "arm": arm, "field": f, "baseline": dist, "fix": other})
        summary["receipt_field_changes_baseline_to_fix"] = changed
        summary["only_delivery_mode_changed"] = all(c["field"] == "delivery_mode" for c in changed)
    summary["field_distributions"] = dists
    return summary


if __name__ == "__main__":
    packet = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    print(json.dumps(main(packet), indent=1, sort_keys=True))
