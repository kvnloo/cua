#!/usr/bin/env python3
"""Write headline-numbers.json: every number the README headlines cite, with its source path in
n03-summary.json / hc-control.json and the exact text the README prints for it (checked by
verify_artifacts.py). usage: make_headlines.py"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = json.loads((HERE / "n03-summary.json").read_text(encoding="utf-8"))
H = json.loads((HERE / "hc-control.json").read_text(encoding="utf-8"))


def get(src, path):  # noqa: ANN001
    obj = src
    for part in path.split("|"):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def ms(v):  # noqa: ANN001
    return f"{v:.2f} ms"


def pct(v):  # noqa: ANN001
    return f"{100 * v:.2f}%"


def plain(v):  # noqa: ANN001
    return str(v)


ITEMS = []
for t in ("checkbox", "text"):
    for c, tag in (("X-vs-X+HCL", "hcl"), ("X-vs-X+V", "v"), ("X+V-vs-X+HCL+V", "hcl2"), ("X+HCL-vs-X+HCL+V", "v2")):
        base = f"part_a_k1|contrasts_k1|{t}/{c}|wall_clock_T_ms"
        ITEMS += [(f"{tag}_k1_{t}_median", base + "|median", ms), (f"{tag}_k1_{t}_lo", base + "|ci95|0", ms),
                  (f"{tag}_k1_{t}_hi", base + "|ci95|1", ms)]
        k5 = f"part_a_k5|contrasts_k5|{t}/{c}|sum_T_ms"
        ITEMS += [(f"{tag}_k5_{t}_median", k5 + "|median", ms), (f"{tag}_k5_{t}_lo", k5 + "|ci95|0", ms),
                  (f"{tag}_k5_{t}_hi", k5 + "|ci95|1", ms)]
    w = f"part_a_k1|contrasts_k1|{t}/X-vs-X+V|work_admission_v_ms"
    ITEMS += [(f"v_work_{t}_median", w + "|median", ms), (f"v_work_{t}_lo", w + "|ci95|0", ms), (f"v_work_{t}_hi", w + "|ci95|1", ms)]
    for g in ("HCL", "V"):
        ITEMS.append((f"verdict_{g}_{t}", f"gates|{g}/{t}|verdict", plain))
    ITEMS += [(f"best_arm_{t}", f"e2|{t}|best_arm", plain),
              (f"untested_primary_{t}", f"e2|{t}|primary_R2-10_reading|untested_share", pct),
              (f"untested_conservative_{t}", f"e2|{t}|conservative_N-02_reading|untested_share", pct),
              (f"meanT_best_{t}", f"e2|{t}|primary_R2-10_reading|mean_T_ms", ms),
              (f"untested_ms_{t}", f"e2|{t}|primary_R2-10_reading|untested_ms", ms)]
    for a in ("X", "X+HCL", "X+V", "X+HCL+V"):
        ITEMS.append((f"median_T_{t}_{a}", f"part_a_k1|arms|{t}|{a}|T_oracle_ms|median", ms))
        ITEMS.append((f"k5_validate_task1_{t}_{a}", f"part_a_k5|sessions|{t}/{a}|validate_by_task_i_median|1", ms))
        ITEMS.append((f"k5_validate_task0_{t}_{a}", f"part_a_k5|sessions|{t}/{a}|validate_by_task_i_median|0", ms))
for fam in ("D", "U"):
    ITEMS.append((f"axfg_verdict_{fam}", f"gates|axfg_S0/{fam}|verdict", plain))
    for el in ("checkbox", "button"):
        b = f"part_b|{fam}/{el}"
        ITEMS += [(f"axfg_{fam}_{el}_visible", b + "|s0_visible_at_return", plain),
                  (f"axfg_{fam}_{el}_minmargin", b + "|s0_min_margin_ms", ms),
                  (f"axfg_{fam}_{el}_saved", b + "|wall_clock_saved_T_ms|median", ms),
                  (f"axfg_{fam}_{el}_saved_lo", b + "|wall_clock_saved_T_ms|ci95|0", ms),
                  (f"axfg_{fam}_{el}_saved_hi", b + "|wall_clock_saved_T_ms|ci95|1", ms)]
ITEMS += [("pc_s0u_not_visible", "part_b|positive_control|S0U|not_visible", plain),
          ("hcl_online_calls", "hcl_equivalence_online|calls", plain),
          ("hcl_online_agree", "hcl_equivalence_online|agree", plain),
          ("vctl_pass", "v_control|x_v_pass", plain)]


def main() -> None:
    out = []
    for hid, path, fmt in ITEMS:
        v = get(S, path)
        out.append({"id": hid, "source": "n03-summary.json", "path": path, "value": v,
                    "text": fmt(v) if v is not None else None})
    for tool, v in H["summary"]["per_tool"].items():
        out.append({"id": f"hc_offline_{tool}", "source": "hc-control.json", "path": f"summary|per_tool|{tool}|invalid_rejected_by_both",
                    "value": v["invalid_rejected_by_both"], "text": None})
    readme = (HERE / "README.md").read_text(encoding="utf-8") if (HERE / "README.md").exists() else ""
    for x in out:
        x["cited_in_readme"] = bool(x["text"] and x["text"] in readme)
        print(x["id"], "=", x["text"] if x["text"] is not None else x["value"])
    (HERE / "headline-numbers.json").write_text(json.dumps({"schema": "n03.headlines.v1", "numbers": out}, indent=1,
                                                           sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
