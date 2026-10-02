#!/usr/bin/env python3
"""Evidence for the fix round's metric and G7 decisions (diagnostic; reads recorded raw rows only).

Ran at harness 2615af74f + the A/A and calibration run dirs:
  evidence.py <harness/ar> <calibration run dir>/evals <A/A run dir> <out.json>
(no-op build deltas in T and T_act; A/A deltas; legacy G7 trace-off rules on the delete50 repeats)
"""
import glob, json, math, sys
from statistics import fmean
sys.path.insert(0, sys.argv[1])
from areval import gates, stats
from areval.aa import t_act_ns

C, A, OUT = sys.argv[2], sys.argv[3], sys.argv[4]


def jl(paths):
    out = []
    for p in paths:
        out += [json.loads(x) for x in open(p) if x.strip()]
    return out


def deltas(rows, metric, kind="task"):
    ps = gates.pairs(rows, kind)
    v = [(metric(a), metric(c)) for a, c in ps]
    v = [(x, y) for x, y in v if x and y]
    return stats.ln_ratios(v)


def summ(d, seed=1):
    lo, hi = stats.bootstrap_ci(d, seed=seed)
    return {"n": len(d), "delta": round(fmean(d), 4), "ci": [round(lo, 4), round(hi, 4)], "sd": round(stats.sd(d), 4)}


W = lambda r: r.get("T_ns")
out = {"noop_builds": {}, "aa": {}}
for k in range(1, 11):
    rows = jl(glob.glob(f"{C}/ar-20261002-cal-noop{k:02d}-r01/screen/raw/*.jsonl"))
    out["noop_builds"][f"noop{k:02d}"] = {"whole": summ(deltas(rows, W)), "t_act": summ(deltas(rows, t_act_ns))}
for name in ("aa1", "aa-same"):
    rows = jl(glob.glob(f"{A}/{name}/raw/*.jsonl"))
    out["aa"][name] = {"whole": summ(deltas(rows, W)), "t_act": summ(deltas(rows, t_act_ns))}
for m in ("whole", "t_act"):
    ds = [v[m]["delta"] for v in out["noop_builds"].values()]
    ses = [v[m]["sd"] / math.sqrt(v[m]["n"]) for v in out["noop_builds"].values()]
    # between-build variance = var(build deltas) - mean within-build SE^2
    vb = stats.sd(ds) ** 2 - fmean(s * s for s in ses)
    out[f"noop_{m}_across_builds"] = {"mean": round(fmean(ds), 4), "sd": round(stats.sd(ds), 4),
                                      "mean_within_se": round(fmean(ses), 4),
                                      "between_build_sd_est": round(math.sqrt(max(vb, 0)), 4),
                                      "abs_gt_2pct": sum(1 for d in ds if abs(d) > math.log1p(0.02))}

# G7 trace-off variants on delete50 repeats + A/A
g7 = {}
for r in range(1, 11):
    e = f"{C}/ar-20261002-cal-delete50-r{r:02d}"
    rows = jl(glob.glob(f"{e}/confirm/raw/*.jsonl"))
    tau = json.load(open(f"{e}/prereg.json"))["tau"]["value"]
    for m, f in (("whole", W), ("t_act", t_act_ns)):
        on = [(f(a), f(c)) for a, c in gates.pairs(rows, "task", trace=True)]
        off = [(f(a), f(c)) for a, c in gates.pairs(rows, "task", trace=False)]
        on = stats.ln_ratios([x for x in on if x[0] and x[1]])
        off = stats.ln_ratios([x for x in off if x[0] and x[1]])
        if len(on) < 2 or len(off) < 2:
            continue
        lim = math.log1p(tau if m == "whole" else 0.02)
        lo, hi = stats.bootstrap_ci(on, seed=5)
        mo, mf = stats.bootstrap_means(on, 4000, 6), stats.bootstrap_means(off, 4000, 7)
        diffs = sorted(b - a for a, b in zip(mo, mf))
        dlo, dhi = stats.quantile(diffs, 0.025), stats.quantile(diffs, 0.975)
        g7[f"r{r:02d}-{m}"] = {"on": len(on), "off": len(off), "d_on": round(fmean(on), 4), "d_off": round(fmean(off), 4),
                               "point_abs": round(abs(fmean(off) - fmean(on)), 4), "lim": round(lim, 4),
                               "spec_pass": lo - lim <= fmean(off) <= hi + lim,
                               "diffci": [round(dlo, 4), round(dhi, 4)],
                               "diffci_pass": not (dlo > lim or dhi < -lim),
                               "sd_on": round(stats.sd(on), 4), "sd_off": round(stats.sd(off), 4)}
out["g7"] = g7
json.dump(out, open(OUT, "w"), indent=1)
print(json.dumps(out, indent=1))
