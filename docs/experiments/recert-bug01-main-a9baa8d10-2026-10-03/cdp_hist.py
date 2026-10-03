"""Map CDP method names to Chrome's DevTools.CDPCommandFrom* sparse-histogram buckets.

Chrome records one sample per CDP command it receives in the sparse histograms
DevTools.CDPCommandFromRemoteDebugger (commands on the browser-level
connection, no sessionId) and DevTools.CDPCommandFromDevTools (commands routed
to a flattened target session, observed here). The bucket is the method-name
hash: the first 8 bytes of MD5(method) read as a big-endian uint64, truncated to
its low 32 bits and read as a signed int32. This was found in the plumbing
pilot by brute force against the observer's own commands and is RE-CALIBRATED
in every analysed sample: analyze_b_recert.py and verify_artifacts.py require
the Target.getTargets and Browser.getHistograms buckets to equal the observer's
own command counts before any other bucket is read.

usage: cdp_hist.py <method> [...]   -> prints method, signed bucket
"""

from __future__ import annotations

import hashlib
import struct
import sys


def bucket(method: str) -> int:
    u64 = struct.unpack(">Q", hashlib.md5(method.encode()).digest()[:8])[0]
    low = u64 & 0xFFFFFFFF
    return low - (1 << 32) if low >= (1 << 31) else low


def counts(hist: dict | None) -> dict[int, int]:
    """{bucket_low: count} from one Browser.getHistograms entry."""
    if not hist:
        return {}
    return {int(b["low"]): int(b["count"]) for b in hist.get("buckets") or []}


if __name__ == "__main__":
    for m in sys.argv[1:]:
        print(m, bucket(m))
