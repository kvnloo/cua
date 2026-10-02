"""Copy lane AB run outputs into raw/ (sanitized), bundling trials per run.

    python3 collect_raw.py <runs-dir> <quiet-lane-ledger.jsonl> <run-name>...

For each run directory: run-manifest-*.json and session-env-*.txt are copied, trials/ is bundled
as raw/trials-<run>.tar.gz, and session.out is copied with local paths replaced. The quiet-lane
receipts whose label starts with "i107-ab" are copied to raw/lock-receipts.jsonl.
"""

from __future__ import annotations

import io
import json
import re
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PATH_RE = re.compile(r"/(?:mnt|home|tmp)/[^\s\"']*")


def sanitize(text: str) -> str:
    return PATH_RE.sub("<path>", text)


def main() -> None:
    runs, ledger, names = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    raw = HERE / "raw"
    raw.mkdir(exist_ok=True)
    for name in names:
        src = runs / name
        for f in sorted(src.glob("run-manifest-*.json")):
            (raw / f.name).write_text(f.read_text())
        for f in sorted(src.glob("session-env-*.txt")):
            (raw / f"{name}-{f.name}").write_text(sanitize(f.read_text()))
        if (src / "session.out").exists():
            (raw / f"{name}-session.out.txt").write_text(sanitize((src / "session.out").read_text()))
        trials = sorted((src / "trials").glob("*.jsonl")) if (src / "trials").is_dir() else []
        if trials:
            with tarfile.open(raw / f"trials-{name}.tar.gz", "w:gz") as tar:
                for f in trials:
                    data = f.read_bytes()
                    info = tarfile.TarInfo(f"trials/{f.name}")
                    info.size, info.mtime, info.mode = len(data), 0, 0o644
                    tar.addfile(info, io.BytesIO(data))
    rows = [json.loads(x) for x in ledger.read_text().splitlines() if x.strip()]
    mine = [r for r in rows if str(r.get("label", "")).startswith("i107-ab")]
    (raw / "lock-receipts.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in mine))
    print(f"collected {names}; {len(mine)} lock receipts")


if __name__ == "__main__":
    main()
