#!/usr/bin/env python3
"""Write headline-numbers.json: every number the README headlines cite, with its source path in
n04-summary.json / hc-control.json ("|"-separated) and the exact text the README prints for it
(checked by verify_artifacts.py). usage: make_headlines.py"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
S = json.loads((HERE / "n04-summary.json").read_text(encoding="utf-8"))
H = json.loads((HERE / "hc-control.json").read_text(encoding="utf-8"))
TASKS = ("checkbox", "text")


def get(src, path):  # noqa: ANN001
    obj = src
    for part in path.split("|"):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


def ms(v):  # noqa: ANN001
    return f"{v:.2f} ms"


def pct(v):  # noqa: ANN001
    return f"{100 * v:.2f}%"


def x2(v):  # noqa: ANN001
    return f"{v:.3f}"


def plain(v):  # noqa: ANN001
    return str(v)


ITEMS = []
for t in TASKS:
    for c, tag in (("X-vs-X+V", "v"), ("X+V-vs-X+V+HCL", "hcl"), ("X-vs-X+V+HCL", "vhcl")):
        base = f"k1|contrasts|{t}/{c}|wall_clock_T_ms"
        ITEMS += [(f"{tag}_k1_{t}_median", base + "|median", ms), (f"{tag}_k1_{t}_lo", base + "|ci95|0", ms),
                  (f"{tag}_k1_{t}_hi", base + "|ci95|1", ms)]
    w = f"k1|contrasts|{t}/X-vs-X+V|work_admission_v_ms"
    ITEMS += [(f"v_work_{t}_median", w + "|median", ms), (f"v_work_{t}_lo", w + "|ci95|0", ms), (f"v_work_{t}_hi", w + "|ci95|1", ms)]
    k5 = f"k5|contrasts|{t}/X+V-vs-X+V+HCL|sum_T_ms"
    ITEMS += [(f"hcl_k5_{t}_median", k5 + "|median", ms), (f"hcl_k5_{t}_lo", k5 + "|ci95|0", ms), (f"hcl_k5_{t}_hi", k5 + "|ci95|1", ms)]
    ITEMS += [(f"verdict_HCL_{t}", f"gates|HCL/{t}|verdict", plain)]
    ITEMS += [(f"best_{t}", f"e3|{t}|best_composed", plain),
              (f"S_best_{t}", f"e3|{t}|S_best|S", x2), (f"S_best_{t}_lo", f"e3|{t}|S_best|ci95|0", x2),
              (f"S_best_{t}_hi", f"e3|{t}|S_best|ci95|1", x2),
              (f"S_land_best_{t}", f"e3|{t}|S_land_best|S", x2), (f"S_land_best_{t}_lo", f"e3|{t}|S_land_best|ci95|0", x2),
              (f"S_land_best_{t}_hi", f"e3|{t}|S_land_best|ci95|1", x2),
              (f"S0_{t}", f"e3|{t}|S0_keep_only|S", x2), (f"S0_{t}_lo", f"e3|{t}|S0_keep_only|ci95|0", x2),
              (f"S0_{t}_hi", f"e3|{t}|S0_keep_only|ci95|1", x2),
              (f"untested_primary_{t}", f"e2|{t}|primary_R2-10_reading|untested_share", pct),
              (f"untested_conservative_{t}", f"e2|{t}|conservative_N-02_reading|untested_share", pct),
              (f"meanT_best_{t}", f"e2|{t}|primary_R2-10_reading|mean_T_ms", ms),
              (f"untested_ms_{t}", f"e2|{t}|primary_R2-10_reading|untested_ms", ms)]
    for a in ("BASE", "X", "X+V", "X+V+HCL"):
        ITEMS.append((f"median_T_{t}_{a}", f"k1|cells|{t}/{a}|T_oracle_ms|median", ms))
    for a in ("X+V", "X+V+HCL"):
        ITEMS.append((f"k5_sumT_{t}_{a}", f"k5|sessions|{t}/{a}|sum_T_ms_median", ms))
ITEMS += [("verdict_V", "gates|V|verdict", plain), ("verdict_HCL", "gates|HCL|verdict", plain)]


def main() -> None:
    out = []
    for hid, path, fmt in ITEMS:
        v = get(S, path)
        out.append({"id": hid, "source": "n04-summary.json", "path": path, "value": v,
                    "text": fmt(v) if v is not None else None})
    hp = "summary|pass"
    out.append({"id": "hc_offline_pass", "source": "hc-control.json", "path": hp, "value": get(H, hp), "text": None})
    (HERE / "headline-numbers.json").write_text(json.dumps({"schema": "n04.headlines.v1", "numbers": out}, indent=1,
                                                           sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(out)} headline numbers")


if __name__ == "__main__":
    main()
