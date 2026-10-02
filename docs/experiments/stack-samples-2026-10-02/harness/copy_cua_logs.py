"""Copy the private-home Hermes logs of the CUA runs into the packet (SAMPLESFIX, erratum E2).

  python copy_cua_logs.py <packet_dir> <runs_dir> <sanitize.json>

For every RUN task of kind "cua" in dataset/runs.jsonl, copies <runs_dir>/<run_id>/home/.hermes/logs/
{agent.log,errors.log} to raw/runs/<run_id>/ with the same local sanitizer as build_packet.py, then
refuses if a committed copy still holds a local marker or an absolute local path. No data are created:
these logs were written by the original SAMPLES runs and were mirrored locally but not committed.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_packet as bp  # noqa: E402  (reuses ABS_PATH, SUBST, MARKERS, copy_text)


def main() -> None:
    packet, runs_dir, cfg = Path(sys.argv[1]), Path(sys.argv[2]), json.loads(Path(sys.argv[3]).read_text())
    bp.SUBST[:] = cfg["subst"]
    bp.MARKERS[:] = cfg["markers"]
    runs = [json.loads(l) for l in (packet / "dataset" / "runs.jsonl").read_text().splitlines() if l.strip()]
    copied, bad = [], []
    for r in runs:
        if r["status"] != "RUN" or r["kind"] != "cua":
            continue
        for name in ("agent.log", "errors.log"):
            dst = packet / "raw" / "runs" / r["run_id"] / name
            bp.copy_text(runs_dir / r["run_id"] / "home" / ".hermes" / "logs" / name, dst)
            text = dst.read_text()
            if bp.ABS_PATH.search(text) or any(m in text for m in bp.MARKERS):
                bad.append(str(dst.relative_to(packet)))
            copied.append(str(dst.relative_to(packet)))
    print(json.dumps({"copied": len(copied), "refused": bad}))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
