"""B-07 equivalence checks over one packaged chunk (raw/browser/<chunk>.tar.gz), run after the chunk.

Per trial, from the captured frames (harness/b07_browser.py write_frames):
* requests (PREP_FAST): every tools/call request line must equal the library serialisation of the
  same (name, arguments, id): ClientRequest(CallToolRequest(CallToolRequestParams)) -> model_dump(
  by_alias, mode=json, exclude_none) -> JSONRPCMessage(JSONRPCRequest) -> model_dump_json(by_alias,
  exclude_none). Arguments are read back with json.loads (key order kept), so a fast-path text that
  differs from the library's in any byte fails.
* responses (ROUTE_FAST): the sequence of sha256(canonical JSON) of the result objects handed to
  CallToolResult.model_validate must equal the sequence over the tools/call response lines (by
  request id) of sha256(canonical(json.loads(line)['result'])).
* structure (POST_FAST): per paired round, the sequence of tools/call response structures (keys and
  value types; enumerated fields route/effect/status/input_route/code/type/isError kept by value) must
  be identical between the control and the candidate trial.
* validation: every in-T call returned ok in both arms (same compiled validators on identical objects
  give identical verdicts).

usage: b07_equivalence.py <chunk.tar.gz> <out.json>   (jev-use venv python, under hostless)
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import sys
import tarfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from mcp import types

ENUM_KEYS = {"route", "effect", "status", "input_route", "code", "type", "isError", "mode", "kind"}


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def library_line(name: str, arguments: Any, rid: Any) -> str:
    req = types.ClientRequest(types.CallToolRequest(params=types.CallToolRequestParams(name=name, arguments=arguments)))
    data = req.model_dump(by_alias=True, mode="json", exclude_none=True)
    return types.JSONRPCMessage(types.JSONRPCRequest(jsonrpc="2.0", id=rid, **data)).model_dump_json(
        by_alias=True, exclude_none=True)


def structure(v: Any, key: str | None = None) -> Any:
    if isinstance(v, dict):
        return {k: structure(x, k) for k, x in sorted(v.items())}
    if isinstance(v, list):
        return [structure(x) for x in v]
    if key in ENUM_KEYS or isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return "n"
    if isinstance(v, str):
        return "s"
    return type(v).__name__


def read_tar(path: Path) -> dict[str, bytes]:
    out = {}
    with tarfile.open(path, "r:gz") as tar:
        for m in tar.getmembers():
            if m.isfile():
                out[m.name[2:] if m.name.startswith("./") else m.name] = tar.extractfile(m).read()
    return out


def check_trial(frames: list[dict[str, Any]]) -> dict[str, Any]:
    reqs = [json.loads(f["line"]) | {"_line": f["line"]} for f in frames if f["k"] == "req"]
    call_ids = {r["id"]: r for r in reqs if r.get("method") == "tools/call" and "id" in r}
    req_ok = req_bad = 0
    bad_examples = []
    for r in call_ids.values():
        p = r["params"]
        lib = library_line(p["name"], p.get("arguments"), r["id"])
        if lib == r["_line"]:
            req_ok += 1
        else:
            req_bad += 1
            if len(bad_examples) < 3:
                bad_examples.append({"id": r["id"], "tool": p["name"]})
    resp_sha, structs = [], []
    for f in frames:
        if f["k"] != "resp":
            continue
        try:
            m = json.loads(f["line"])
        except ValueError:
            continue
        if isinstance(m, dict) and m.get("id") in call_ids and "result" in m:
            resp_sha.append(hashlib.sha256(canonical(m["result"]).encode()).hexdigest())
            structs.append([call_ids[m["id"]]["params"]["name"], structure(m["result"])])
    obj_sha = [f["sha"] for f in frames if f["k"] == "resobj"]
    return {"requests": len(call_ids), "requests_identical": req_ok, "requests_different": req_bad,
            "request_examples": bad_examples, "responses": len(resp_sha),
            "responses_decoded_identical": resp_sha == obj_sha, "n_resobj": len(obj_sha),
            "structure_sha": hashlib.sha256(canonical(structs).encode()).hexdigest()}


def main() -> None:
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    files = read_tar(src)
    per: dict[str, Any] = {}
    meta: dict[str, Any] = {}
    for name, data in sorted(files.items()):
        if name.startswith("frames/") and name.endswith(".frames.jsonl.gz"):
            trial = name.split("/")[-1].replace(".frames.jsonl.gz", "")
            frames = [json.loads(x) for x in gzip.decompress(data).decode().splitlines() if x.strip()]
            per[trial] = check_trial(frames)
        elif name.startswith("trials/") and name.endswith(".jsonl") and not name.endswith(".driver-trace.jsonl"):
            lines = [json.loads(x) for x in data.decode().splitlines() if x.strip()]
            if lines and lines[-1].get("event") == "summary":
                s = lines[-1]
                calls_ok = all(e.get("ok") for e in lines[:-1] if e.get("event") == "call_return"
                               and str(e.get("label", "")).startswith(("snapshot", "action")))
                meta[s["trial"]] = {"cls": s.get("cls"), "arm": s.get("arm"), "round": s.get("round"),
                                    "kind": s.get("kind"), "calls_ok": calls_ok}
    # structure pairing per (cls, round) for measured trials
    pairs: dict[tuple, dict[str, str]] = defaultdict(dict)
    for t, m in meta.items():
        if m["kind"] == "measured" and t in per and not t.endswith("-admission"):
            pairs[(m["cls"], m["round"])][m["arm"]] = per[t]["structure_sha"]
    struct_rows = [{"cls": k[0], "round": k[1], "arms": v, "identical": len(set(v.values())) == 1}
                   for k, v in sorted(pairs.items(), key=lambda kv: (kv[0][0], kv[0][1])) if len(v) == 2]
    summary = {
        "chunk": src.name, "trials": len(per),
        "requests": sum(x["requests"] for x in per.values()),
        "requests_identical": sum(x["requests_identical"] for x in per.values()),
        "requests_different": sum(x["requests_different"] for x in per.values()),
        "responses": sum(x["responses"] for x in per.values()),
        "trials_responses_decoded_identical": sum(1 for x in per.values() if x["responses_decoded_identical"]),
        "structure_pairs": len(struct_rows), "structure_pairs_identical": sum(1 for x in struct_rows if x["identical"]),
        "measured_trials_all_calls_ok": sum(1 for t, m in meta.items() if m["kind"] == "measured" and m["calls_ok"]),
        "measured_trials": sum(1 for m in meta.values() if m["kind"] == "measured"),
    }
    summary["all_equal"] = (summary["requests_different"] == 0 and summary["requests"] > 0
                            and summary["trials_responses_decoded_identical"] == summary["trials"]
                            and summary["structure_pairs_identical"] == summary["structure_pairs"])
    out.write_text(json.dumps({"summary": summary, "per_trial": per, "structure_pairs": struct_rows}, indent=1) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
