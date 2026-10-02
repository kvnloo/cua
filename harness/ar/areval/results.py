"""Append-only, hash-chained results.jsonl (one line per evaluation).

Each line carries ``prev_sha256`` = sha256 of the previous line's bytes ("genesis" for the
first), so an edited or deleted line breaks the chain and :func:`verify_chain` reports it.
Lines are only ever appended (O_APPEND); nothing rewrites the file.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .schema import load, validate


def _lines(path: Path) -> list[bytes]:
    if not path.exists():
        return []
    return [x for x in path.read_bytes().split(b"\n") if x.strip()]


def verify_chain(path: Path) -> list[str]:
    errors = []
    prev = "genesis"
    for i, line in enumerate(_lines(path)):
        rec = json.loads(line)
        if rec.get("prev_sha256") != prev:
            errors.append(f"line {i + 1}: chain broken")
        prev = hashlib.sha256(line).hexdigest()
    return errors


def prior_p_values(path: Path) -> list[float]:
    """p-values of every earlier G5 test, in order (the whole LORD++ state)."""
    out = []
    for line in _lines(path):
        lord = json.loads(line).get("lord")
        if lord:
            out.append(float(lord["p_value"]))
    return out


def append(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    errors = verify_chain(path)
    if errors:
        raise RuntimeError(f"results chain broken, refusing to append: {errors}")
    lines = _lines(path)
    record = {**record, "prev_sha256": hashlib.sha256(lines[-1]).hexdigest() if lines else "genesis"}
    problems = validate(record, load("result.schema.json"))
    if problems:
        raise ValueError(f"result record invalid: {problems}")
    data = (json.dumps(record, sort_keys=True) + "\n").encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    return record
