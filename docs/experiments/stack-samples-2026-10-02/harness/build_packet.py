"""Assemble the committed packet from local receipts (sanitized: no absolute local paths).

  python build_packet.py <packet_dir> <collect_dir> <runs_dir> <work_dir> <hermes_worktree> <ledger.jsonl> <label_prefix> <sanitize.json>

Copies the frozen dataset, oracle inputs per run (final reply, produced cwd files, GUI state), the
examples/audits, scored rows, evaluations, analyses and scoring logs, the quiet-lane ledger lines of
this lane, and vendors the exact Hermes lab scripts used, then refuses if any committed file still
contains a local path marker or an absolute path. sanitize.json is a local, untracked file:
{"subst": [[local_prefix, "$VAR"], ...], "markers": [...]} so this source names no local path.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ABS_PATH = re.compile(r"(?<![\w$}.~-])/(mnt|home|workspace|run/user|srv|opt)/[A-Za-z0-9]")
SUBST: list[list[str]] = []
MARKERS: list[str] = []


def sanitize(text: str) -> str:
    for a, b in SUBST:
        text = text.replace(a, b)
    return text


def copy_text(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(sanitize(src.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")


def main() -> None:
    packet, collect, runs_dir, work, hermes_wt, ledger, prefix = map(str, sys.argv[1:8])
    local = json.loads(Path(sys.argv[8]).read_text())
    SUBST[:] = local["subst"]
    MARKERS[:] = local["markers"]
    packet, collect, runs_dir, work, hermes_wt, ledger = map(Path, (packet, collect, runs_dir, work, hermes_wt, ledger))
    raw = packet / "raw"
    if raw.exists():
        shutil.rmtree(raw)
    shutil.rmtree(packet / "dataset", ignore_errors=True)
    shutil.copytree(work / "dataset", packet / "dataset")
    for name in ("index.jsonl", "verdicts.jsonl", "collect.log", "launched_at"):
        if (collect / name).exists():
            copy_text(collect / name, raw / "collect" / name)
    env_checks = {}
    for line in (packet / "dataset" / "runs.jsonl").read_text().splitlines():
        run = json.loads(line)
        if run.get("status") != "RUN":
            continue
        src = runs_dir / run["run_id"]
        dst = raw / "runs" / run["run_id"]
        for name in ("stdout", "exit_code", "started_at", "ended_at", "argv", "mask.inside", "worktree-head", "worktree-status"):
            if (src / "meta" / name).exists():
                copy_text(src / "meta" / name, dst / name)
        if (src / "cwd").exists():
            for f in sorted(p for p in (src / "cwd").rglob("*") if p.is_file()):
                copy_text(f, dst / "cwd" / f.relative_to(src / "cwd"))
        for name in ("state.before.json", "state.after.json"):
            if (src / "meta" / "gui-state" / name).exists():
                copy_text(src / "meta" / "gui-state" / name, dst / "gui-state" / name)
        env = (src / "meta" / "env.inside").read_text() if (src / "meta" / "env.inside").exists() else ""
        hits = [l.split("=", 1)[0] for l in env.splitlines() if any(m in l and m.startswith("/") and not m.startswith("/mnt") for m in MARKERS)
                or re.match(r"^(OPENAI|ANTHROPIC|OPENROUTER|GROQ|DEEPSEEK|CEREBRAS|XAI|GEMINI|HF)_[A-Z_]*=", l)]
        env_checks[run["run_id"]] = {"env_vars": len(env.splitlines()), "live_path_or_secret_var_hits": hits,
                                     "hermes_home_in_run_dir": any(l.startswith("HERMES_HOME=") and "/samples/runs/" in l for l in env.splitlines())}
    (raw / "env_checks.json").write_text(json.dumps(env_checks, indent=2, sort_keys=True) + "\n")
    for sub in ("examples", "scored", "eval", "analysis", "scoring-logs", "controls"):
        if (work / sub).exists():
            for f in sorted(p for p in (work / sub).rglob("*") if p.is_file()):
                copy_text(f, raw / sub / f.relative_to(work / sub))
    lines = [l for l in ledger.read_text().splitlines() if f'"label":"{prefix}' in l]
    (raw / "quiet-lane-ledger.samples.jsonl").write_text("\n".join(lines) + ("\n" if lines else ""))
    vendor = packet / "harness" / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    for name in ("shadow_api_failure.py", "evaluate_shadow.py", "ollama_logprob_backend.py"):
        shutil.copy2(hermes_wt / "lab" / "z0_hermes_observer" / name, vendor / name)
    bad = []
    for f in packet.rglob("*"):
        if f.is_file() and "__pycache__" not in f.parts and f.suffix not in (".png",):
            text = f.read_text(encoding="utf-8", errors="replace")
            bad += [f"{f.relative_to(packet)}:{m}" for m in MARKERS if m in text]
            bad += [f"{f.relative_to(packet)}:abs:{m.group(0)}" for m in ABS_PATH.finditer(text)][:3]
    if bad:
        raise SystemExit("local path markers remain:\n" + "\n".join(bad[:20]))
    print(json.dumps({"runs_copied": len(env_checks), "ledger_lines": len(lines), "scan": "clean"}))


if __name__ == "__main__":
    main()
