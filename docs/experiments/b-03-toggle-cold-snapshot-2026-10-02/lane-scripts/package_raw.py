# Sanitized copy (placeholders replace local paths); the lane ran the original in artifacts/r2/B-03/bin/.
"""Copy B-03 lane artifacts into the packet raw/ with absolute paths and host name removed."""
import io
import json
import re
import tarfile
from pathlib import Path

A = Path("<lanes>/artifacts/r2/B-03")
P = Path("<lanes>/w3-b03-cold-snapshot/docs/experiments/b-03-toggle-cold-snapshot-2026-10-02/raw")
HOST = Path("/etc/hostname").read_text().strip()
SUBS = [("<lanes>", "<lanes>"), ("<lane-tmp>", "<lane-tmp>"),
        ("<mnt-root>", "<mnt>"), ("<home-dir>", "<home>")]


def clean(text: str) -> str:
    for a, b in SUBS:
        text = text.replace(a, b)
    text = re.sub(r"/tmp/dbus-[A-Za-z0-9]+", "<session-tmp>/dbus-X", text)
    text = re.sub(r"/tmp/[A-Za-z0-9._/-]+", "<session-tmp>/...", text)
    if HOST:
        text = re.sub(re.escape(HOST), "<host>", text, flags=re.IGNORECASE)
    return text


def copy_text(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(clean(src.read_text(errors="replace")))


def tar_trials(src_dir: Path, dst: Path) -> int:
    n = 0
    with tarfile.open(dst, "w:gz") as tar:
        for p in sorted(src_dir.glob("*.jsonl")):
            data = clean(p.read_text()).encode()
            info = tarfile.TarInfo(f"trials/{p.name}")
            info.size, info.mtime = len(data), 0
            tar.addfile(info, io.BytesIO(data))
            n += 1
    return n


P.mkdir(parents=True, exist_ok=True)
summary = {}
for block in ("shake", "measured"):
    src = A / block
    if not src.exists():
        continue
    for f in sorted(src.glob("*.json*")):
        copy_text(f, P / block / f.name)
    for log in sorted(A.glob(f"{block}*.session.log")) + sorted(A.glob(f"{block}*.stdout.log")):
        copy_text(log, P / block / log.name)
    summary[block] = tar_trials(src / "trials", P / f"{block}-trials.tar.gz")
rows = []
for line in Path("<lane-tmp>/locks/quiet-lane-ledger.jsonl").read_text().splitlines():
    try:
        r = json.loads(line)
    except json.JSONDecodeError:
        continue
    if str(r.get("label", "")).startswith("b03-"):
        r["source"] = "quiet-timed (EXCLUSIVE) shared ledger line, copied verbatim"
        rows.append(r)
for block in ("shake",):
    f = A / block / "lock-receipts.jsonl"
    if f.exists():
        for line in f.read_text().splitlines():
            r = json.loads(line)
            r["source"] = f"run_b03.py SHARED acquisition ({block})"
            rows.append(r)
(P / "lock-ledger.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
print(json.dumps({"trial_files": summary, "lock_rows": len(rows)}))
