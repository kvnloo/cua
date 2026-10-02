"""Gate G0: scope and tamper (pure function of the candidate diff and its derived reports).

Inputs (all plain data, collected by ``cli.collect_g0_inputs``):
  diff               unified diff champion..candidate (``git diff --no-renames``)
  itemcheck          the ``ar.itemcheck.v1`` report for the changed .rs files
  frozen_sha256      {path: sha256 or None} of the manifest's candidate_frozen files in the
                     candidate tree
  lineage_ok         the candidate branch descends from the champion commit
"""

from __future__ import annotations

from typing import Any

from .scanner import parse_diff, scan


def changed_paths(diff: str) -> list[str]:
    return sorted(parse_diff(diff).keys() | {
        line.split(" b/", 1)[1] for line in diff.splitlines()
        if line.startswith("diff --git ") and " b/" in line
    })


def g0(inputs: dict[str, Any], allowlist: dict[str, Any], manifest: dict[str, Any],
       rules: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    allowed_files = set(allowlist["items"])
    paths = changed_paths(inputs["diff"])
    if not paths:
        reasons.append("empty_diff")
    for path in paths:
        name = path.rsplit("/", 1)[-1]
        if name in ("Cargo.toml", "Cargo.lock") or name.endswith(".toml"):
            reasons.append(f"cargo_change:{path}")
        elif path.startswith("harness/"):
            reasons.append(f"harness_touched:{path}")
        elif path not in allowed_files:
            reasons.append(f"path_outside_allowlist:{path}")
    for path, lines in parse_diff(inputs["diff"]).items():
        if any("phase_trace" in x for x in lines["added"] + lines["removed"]):
            reasons.append(f"phase_trace_line_touched:{path}")

    report = inputs.get("itemcheck") or {}
    if report.get("schema") != "ar.itemcheck.v1":
        reasons.append("itemcheck_missing")
    else:
        for v in report.get("violations", []):
            reasons.append(f"itemcheck:{v['kind']}:{v['file']}:{v.get('item')}")
        for key, expected in manifest.get("test_items", {}).items():
            got = report.get("files", {}).get(key, {}).get("test_items_cand")
            if got is not None and got != expected:
                reasons.append(f"test_item_hash_mismatch:{key}")

    for path, sha in manifest.get("candidate_frozen", {}).items():
        got = inputs.get("frozen_sha256", {}).get(path, "<not checked>")
        if got != sha:
            reasons.append(f"frozen_file_changed:{path}")

    hits = scan(inputs["diff"], rules)
    reasons.extend(f"scanner:{h['rule']}:{h['file']}" for h in hits)
    if not inputs.get("lineage_ok", False):
        reasons.append("candidate_not_based_on_champion")
    edited = sorted({*report.get("files", {}).keys()}) if report else []
    return {"gate": "G0", "pass": not reasons, "reasons": reasons,
            "metrics": {"changed_paths": paths, "scanner_hits": hits, "itemcheck_files": edited,
                        "changed_items": sorted(i for f in report.get("files", {}).values()
                                                for i in f.get("changed_allowed", []))}}
