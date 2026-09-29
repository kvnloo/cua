#!/usr/bin/env python3
"""Analyze captured Cua Driver ``tools/list`` payloads (kvnloo/cua#76). Stdlib only.

usage: analyze_tools_list.py RAW_DIR --base LABEL --head LABEL [--tokenizer-root DIR] [--json OUT] [--md OUT]
RAW_DIR holds <label>.tools-list.page*.response.json written by capture_tools_list.py.

Definitions (all byte counts are UTF-8 bytes of compact JSON, separators (",", ":"), ensure_ascii=False):
  wire_bytes            the raw JSON-RPC response line(s) as received from the Driver
  tool_bytes            compact JSON of one entry of result.tools[]
  description_bytes     UTF-8 length of a tool's top-level `description` string
  input_schema_bytes    compact JSON of `inputSchema`
  output_schema_bytes   compact JSON of `outputSchema`
  embedded_description_bytes  UTF-8 length of every `description` string nested inside a schema
  repeated bytes        for a group of byte-identical items that occurs n times, (n - 1) * item_bytes
No token estimate is derived from bytes; tokens are only reported when a real tokenizer runs.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import subprocess
from pathlib import Path


def compact(value) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False, sort_keys=False)


def size(value) -> int:
    return len(compact(value).encode("utf-8"))


def load(raw: Path, label: str):
    pages = sorted(glob.glob(str(raw / f"{label}.tools-list.page*.response.json")))
    wire = 0
    tools: list[dict] = []
    for page in pages:
        data = Path(page).read_bytes()
        wire += len(data)
        tools.extend(json.loads(data)["result"]["tools"])
    meta = json.loads((raw / f"{label}.meta.json").read_text())
    return tools, wire, meta


def embedded_descriptions(schema) -> list[str]:
    found: list[str] = []

    def walk(node, key=None):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "description" and isinstance(v, str) and key != "properties":
                    found.append(v)
                walk(v, k)
        elif isinstance(node, list):
            for item in node:
                walk(item, key)

    walk(schema)
    return found


def tool_row(tool: dict) -> dict:
    known = {"name", "description", "inputSchema", "outputSchema", "annotations", "title"}
    row = {
        "name": tool["name"],
        "tool_bytes": size(tool),
        "description_bytes": len(tool.get("description", "").encode()),
        "input_schema_bytes": size(tool["inputSchema"]) if "inputSchema" in tool else 0,
        "output_schema_bytes": size(tool["outputSchema"]) if "outputSchema" in tool else 0,
        "annotations_bytes": size(tool["annotations"]) if "annotations" in tool else 0,
        "other_keys": sorted(set(tool) - known),
        "properties": len((tool.get("inputSchema") or {}).get("properties", {})),
    }
    row["embedded_description_bytes_input"] = sum(len(d.encode()) for d in embedded_descriptions(tool.get("inputSchema", {})))
    row["embedded_description_bytes_output"] = sum(len(d.encode()) for d in embedded_descriptions(tool.get("outputSchema", {})))
    return row


def analyze(tools: list[dict], wire: int) -> dict:
    rows = [tool_row(t) for t in tools]
    tools_bytes = size(tools)
    result = {
        "wire_bytes": wire,
        "tools_array_compact_bytes": tools_bytes,
        "envelope_and_separators_bytes": wire - tools_bytes,
        "tool_count": len(tools),
        "sum_description_bytes": sum(r["description_bytes"] for r in rows),
        "sum_input_schema_bytes": sum(r["input_schema_bytes"] for r in rows),
        "sum_output_schema_bytes": sum(r["output_schema_bytes"] for r in rows),
        "sum_annotations_bytes": sum(r["annotations_bytes"] for r in rows),
        "sum_embedded_description_bytes_input": sum(r["embedded_description_bytes_input"] for r in rows),
        "sum_embedded_description_bytes_output": sum(r["embedded_description_bytes_output"] for r in rows),
        "tools_with_output_schema": sum(1 for r in rows if r["output_schema_bytes"]),
        "other_tool_keys": sorted({k for r in rows for k in r["other_keys"]}),
        "top15_tools_by_bytes": sorted(rows, key=lambda r: -r["tool_bytes"])[:15],
        "tools": rows,
    }

    # (a) byte-identical repeated input-schema property definitions (RFC #2969's method)
    prop_groups: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    prop_variants: dict[str, dict[str, list[str]]] = collections.defaultdict(lambda: collections.defaultdict(list))
    for tool in tools:
        for name, schema in ((tool.get("inputSchema") or {}).get("properties") or {}).items():
            text = compact(schema)
            prop_groups[(name, text)].append(tool["name"])
            prop_variants[name][text].append(tool["name"])
    repeated_props = [
        {"property": name, "definition_bytes": len(text.encode()), "occurrences": len(users),
         "repeated_bytes": (len(users) - 1) * len(text.encode()), "tools": users if len(users) <= 6 else users[:6] + ["…"]}
        for (name, text), users in prop_groups.items() if len(users) > 1
    ]
    repeated_props.sort(key=lambda r: -r["repeated_bytes"])
    result["repeated_input_property_definitions"] = {
        "total_repeated_bytes": sum(r["repeated_bytes"] for r in repeated_props),
        "groups": len(repeated_props),
        "top": repeated_props[:15],
    }
    drift = []
    for name, variants in prop_variants.items():
        if len(variants) > 1:
            drift.append({"property": name, "distinct_definitions": len(variants),
                          "variants": sorted(({"bytes": len(t.encode()), "tools": len(u)} for t, u in variants.items()),
                                             key=lambda v: -v["tools"] * v["bytes"])[:5]})
    drift.sort(key=lambda d: -sum(v["bytes"] * v["tools"] for v in d["variants"]))
    result["properties_with_divergent_definitions"] = drift[:15]

    # (b) identical outputSchema objects
    out_groups: dict[str, list[str]] = collections.defaultdict(list)
    for tool in tools:
        if "outputSchema" in tool:
            out_groups[compact(tool["outputSchema"])].append(tool["name"])
    result["repeated_output_schemas"] = sorted(
        ({"bytes": len(t.encode()), "occurrences": len(u), "repeated_bytes": (len(u) - 1) * len(t.encode()),
          "tools": u if len(u) <= 6 else u[:6] + ["…"]} for t, u in out_groups.items() if len(u) > 1),
        key=lambda r: -r["repeated_bytes"])

    # (c) identical description strings (top-level tool descriptions and schema-embedded ones)
    desc_groups: dict[str, int] = collections.Counter()
    for tool in tools:
        for d in [tool.get("description", "")] + embedded_descriptions(tool.get("inputSchema", {})) + embedded_descriptions(tool.get("outputSchema", {})):
            if d:
                desc_groups[d] += 1
    rep_desc = [{"bytes": len(d.encode()), "occurrences": n, "repeated_bytes": (n - 1) * len(d.encode()), "text": d[:120] + ("…" if len(d) > 120 else "")}
                for d, n in desc_groups.items() if n > 1]
    rep_desc.sort(key=lambda r: -r["repeated_bytes"])
    result["repeated_description_strings"] = {"total_repeated_bytes": sum(r["repeated_bytes"] for r in rep_desc), "groups": len(rep_desc), "top": rep_desc[:12]}

    # (d) element_token schema shapes
    shapes: dict[str, list[str]] = collections.defaultdict(list)
    for tool in tools:
        props = (tool.get("inputSchema") or {}).get("properties") or {}
        if "element_token" in props:
            shapes[compact(props["element_token"])].append(tool["name"])
    result["element_token_shapes"] = [{"schema": json.loads(t), "bytes": len(t.encode()), "tools": len(u), "tool_names": u} for t, u in shapes.items()]
    return result


def diff(base_tools: list[dict], head_tools: list[dict]) -> dict:
    b = {t["name"]: t for t in base_tools}
    h = {t["name"]: t for t in head_tools}
    changed = []
    for name in sorted(set(b) & set(h)):
        if b[name] != h[name]:
            changed.append({"tool": name, "before_bytes": size(b[name]), "after_bytes": size(h[name]),
                            "delta_bytes": size(h[name]) - size(b[name])})
    return {"added_tools": sorted(set(h) - set(b)), "removed_tools": sorted(set(b) - set(h)), "changed_tools": changed,
            "sum_delta_bytes_changed_tools": sum(c["delta_bytes"] for c in changed)}


def token_counts(root: str | None, tools: list[dict], helper: Path):
    if not root:
        return None
    texts = {
        "tools_array_compact_json": compact(tools),
        "descriptions_only": "\n".join(t.get("description", "") for t in tools),
        "input_schemas_only": "\n".join(compact(t.get("inputSchema", {})) for t in tools),
        "output_schemas_only": "\n".join(compact(t["outputSchema"]) for t in tools if "outputSchema" in t),
    }
    proc = subprocess.run(["node", str(helper), root], input=json.dumps(texts), capture_output=True, text=True)
    if proc.returncode != 0:
        return {"error": proc.stderr[-400:]}
    return json.loads(proc.stdout)


def to_markdown(res: dict) -> str:
    L = []
    w = L.append
    w("# tools/list payload census (kvnloo/cua#76)\n")
    w("| metric | " + " | ".join(res["labels"]) + " |")
    w("|---|" + "---|" * len(res["labels"]))
    for key in ("wire_bytes", "tools_array_compact_bytes", "tool_count", "sum_input_schema_bytes", "sum_output_schema_bytes",
                "sum_description_bytes", "sum_annotations_bytes", "sum_embedded_description_bytes_input",
                "sum_embedded_description_bytes_output", "tools_with_output_schema"):
        w(f"| {key} | " + " | ".join(str(res["payloads"][l][key]) for l in res["labels"]) + " |")
    for l in res["labels"]:
        p = res["payloads"][l]
        w(f"| repeated identical input property defs (bytes) [{l}] | {p['repeated_input_property_definitions']['total_repeated_bytes']} |")
    w("\n## Delta (head - base)\n```json\n" + json.dumps(res["delta"], indent=1) + "\n```\n")
    for l in res["labels"]:
        p = res["payloads"][l]
        w(f"## {l}: 15 largest tools\n")
        w("| tool | bytes | description | inputSchema | outputSchema | properties |")
        w("|---|---|---|---|---|---|")
        for r in p["top15_tools_by_bytes"]:
            w(f"| {r['name']} | {r['tool_bytes']} | {r['description_bytes']} | {r['input_schema_bytes']} | {r['output_schema_bytes']} | {r['properties']} |")
        w("\n### largest repeated input-property definitions\n")
        w("| property | def bytes | occurrences | repeated bytes |")
        w("|---|---|---|---|")
        for r in p["repeated_input_property_definitions"]["top"][:10]:
            w(f"| {r['property']} | {r['definition_bytes']} | {r['occurrences']} | {r['repeated_bytes']} |")
        w("\n### repeated outputSchema objects\n")
        for r in p["repeated_output_schemas"][:5]:
            w(f"- {r['bytes']} B x {r['occurrences']} tools -> {r['repeated_bytes']} B repeated ({', '.join(r['tools'])})")
        w("\n### repeated description strings (top)\n")
        for r in p["repeated_description_strings"]["top"][:8]:
            w(f"- {r['bytes']} B x {r['occurrences']} = {r['repeated_bytes']} B repeated: `{r['text']}`")
        w("\n### properties whose definition diverges across tools (top)\n")
        for d in p["properties_with_divergent_definitions"][:6]:
            w(f"- `{d['property']}`: {d['distinct_definitions']} distinct definitions; top variants (bytes x tools): "
              + ", ".join(f"{v['bytes']}x{v['tools']}" for v in d["variants"]))
        w("\n### element_token schema shapes\n```json\n" + json.dumps(p["element_token_shapes"], indent=1) + "\n```\n")
        if res["tokens"].get(l):
            w(f"### tokens ({l})\n```json\n{json.dumps(res['tokens'][l], indent=1)}\n```\n")
    return "\n".join(L) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--tokenizer-root", help="directory whose node_modules contains gpt-tokenizer")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--md", type=Path)
    args = parser.parse_args()
    labels = [args.base, args.head]
    payloads, metas, tools_by, tokens = {}, {}, {}, {}
    helper = Path(__file__).with_name("count_tokens.mjs")
    for label in labels:
        tools, wire, meta = load(args.raw, label)
        tools_by[label] = tools
        metas[label] = meta
        payloads[label] = analyze(tools, wire)
        tokens[label] = token_counts(args.tokenizer_root, tools, helper)
    res = {"labels": labels, "meta": metas, "payloads": payloads, "tokens": tokens,
           "delta": {"wire_bytes": payloads[args.head]["wire_bytes"] - payloads[args.base]["wire_bytes"],
                     **diff(tools_by[args.base], tools_by[args.head])}}
    if args.json:
        args.json.write_text(json.dumps(res, indent=1, sort_keys=True) + "\n")
    md = to_markdown(res)
    if args.md:
        args.md.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
