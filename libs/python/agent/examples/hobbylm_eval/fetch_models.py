"""Acquire pinned public artifacts, separately from offline inference.

Usage: python fetch_models.py [--models base adapter baseline]
Uses only the standard library. No credentials or model code are loaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from pathlib import Path

DEFAULT_CACHE = Path("/workspace/cache/hobbylm-cua/models")
MANIFEST = Path(__file__).with_name("artifact_manifest.json")


def _matches(path: Path, record: dict) -> bool:
    if not path.is_file() or path.stat().st_size != record["bytes"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest() == record["sha256"]


def fetch(cache: Path, roles: list[str]) -> None:
    manifest = json.loads(MANIFEST.read_text())
    cache = cache.expanduser().resolve()
    if not cache.is_relative_to(Path("/workspace/cache")):
        raise ValueError("Model downloads must remain under /workspace/cache")
    for role in roles:
        spec = manifest["models"][role]
        directory = cache / spec["directory"]
        directory.mkdir(parents=True, exist_ok=True)
        for filename, record in spec["files"].items():
            target = directory / filename
            if _matches(target, record):
                print(f"cached {role}/{filename} {record['sha256']}", flush=True)
                continue
            expected_url = f"https://huggingface.co/{spec['repository']}/resolve/{spec['revision']}/{filename}"
            if record["url"] != expected_url:
                raise ValueError(f"Artifact URL does not match its pin: {role}/{filename}")
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=directory, prefix=".download-", delete=False) as stream:
                    temporary = Path(stream.name)
                    with urllib.request.urlopen(expected_url, timeout=120) as response:
                        digest, size = hashlib.sha256(), 0
                        for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
                            size += len(block)
                            if size > record["bytes"]:
                                raise ValueError(f"Artifact exceeds pinned size: {role}/{filename}")
                            digest.update(block)
                            stream.write(block)
                if size != record["bytes"] or digest.hexdigest() != record["sha256"]:
                    raise ValueError(f"Artifact checksum or size mismatch: {role}/{filename}")
                os.replace(temporary, target)
                print(f"downloaded {role}/{filename} {record['sha256']}", flush=True)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
    (cache / "artifact_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--models", nargs="+", choices=("base", "adapter", "baseline"), default=["base", "adapter", "baseline"])
    args = parser.parse_args(argv)
    fetch(args.cache_dir, args.models)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
