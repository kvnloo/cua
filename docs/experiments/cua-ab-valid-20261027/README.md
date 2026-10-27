# CUA vs opencli head-to-head, valid rerun (2026-10-27)

Tracks [#161](https://github.com/kvnloo/cua/issues/161). This rerun replaces the 2026-10-26 A/C
read-only run. That run is **invalid**: it used a stale, unpinned `cua-driver 0.23.2`, CUA started
cold on every attempt while opencli reused a warm Chrome, and it had only read-only tasks.

Status: **REAL, descriptive, synthetic fixture only.** Pomerado arm: **NOT_RUN** (see below).

## Design

| Item | Value |
|---|---|
| Tools | A = CUA Driver (`cua-driver mcp`, browser tools), B = opencli adapter over CDP |
| Cells | tool x {warm, cold} x {read, write} = 8 cells |
| Ordering | blocks of 4 attempts, ABBA or BAAB; per shard and per (mode, effect): 2 ABBA + 2 BAAB, seeded shuffle (`SEED=20261027`); read blocks before write blocks |
| n | 10 shards x 4 blocks x 2 attempts = **80 attempts per cell**, 640 timed attempts, plus 40 excluded warm-ups |
| Machines | Boat `small` Linux VMs (2 vCPU, 4 GB, Ubuntu 24.04), one shard per fresh VM; both tools run in every block on the same VM |
| Fixture | `libs/cua-driver/examples/jev-use/fixture_server.py` with the audited `/audit` wrapper, loopback only |
| Oracle | independent `POST /reset`, then `/state` + `/audit` after each attempt; read = page status read and zero commits; write = exactly one commit of the exact value |
| Rules | one attempt, no retry, no fallback, no model calls; teardown is outside the timer |

Warm and cold arms:

- **CUA warm**: one persistent MCP session and one driver-launched isolated Chromium, prepared before
  the timed blocks. Each attempt navigates, then reads (`get_browser_state` semantic_v2) or acts
  (`browser_type` + `browser_click` dom_event, then poll the page for the submitted status).
- **CUA cold**: the timer starts before `cua-driver mcp` spawns; it includes initialize,
  `browser_prepare` (isolated Chromium launch), window bind, navigate, and the read or write.
- **opencli warm**: one persistent Chromium with a CDP port. Each attempt runs the `opencli` CLI
  (`jev read-status` / `jev submit-value`), which is opencli's normal CDP route: one node process
  per call.
- **opencli cold**: the timer starts before Chromium spawns; it includes CDP readiness and the CLI call.

Write confirmation is the same for both tools: poll the page every 100 ms, for up to 5 s, until it
shows `status=submitted:<value>`. The 2026-10-26 opencli write adapter used a fixed `page.wait(1)`;
this rerun replaces it with the poll (digest below).

## Pins (recorded in every receipt)

| Pin | Value |
|---|---|
| cua-driver | `0.38.0`, release tag `cua-driver-rs-v0.38.0` -> trycua/cua commit `85e2b1318bd77ccf3cfa88ccdf875a4bb7eaed19` |
| cua-driver tarball | `cua-driver-rs-0.38.0-linux-x86_64-binary.tar.gz` sha256 `31ab9709dd91ce73677e49b9f3e75c6f0d3e4d9625c286c9e58262bfbea698dd` (release SHA256SUMS) |
| cua-driver binary | sha256 `bf57b2f3778a0a7daa9388e241f20ce948b32a7a2f4dd102e497f34e54137934`; `doctor --json` build.exe_sha256 matches; embedded git_sha is empty in release builds |
| image driver | the Boat image's preinstalled `cua-driver 0.23.2` is present and **not used** |
| opencli | npm `@jackwener/opencli@2.0.2`, tag v2.0.2 -> jackwener/opencli `deca0fee85016be2e58836eeca974825e09c9076`, integrity `sha512-+O+S+FQikiVunP/alMG//ww9D1lpgA24+C6ifyyzI4rZVT6GEJVqaiGZWbyI2i/Hcocs4l1K6gnNt+3Yaf2wtw==` |
| opencli adapters | read sha256 `d81450e46088fac3dde3baf492d42bd8fc2c7af4711d16f0700bd96e3d9d606d`, write sha256 `cf9ee61f98f3a18b7fa96c8f565712d75984ad4c0cd3578cb3fa38f0ab1e2540` |
| Browser | Google Chrome 151.0.7922.108 (`/opt/google/chrome/chrome` for both tools) |
| Runtime | node v24.22.1, Python 3.12.3 |
| Harness | `h2h_run.py` blob `54967be2a3c2795495297721e7d17f9f5db2e7c3` at every shard SHA (`e45acadb`, `8777278b`, `de61110f`; only `vm_bootstrap.sh` changed between them) |

## Results

Success rate is over all attempts. Latency is wall time of the one timed invocation, over verified
attempts, nearest-rank percentiles.

| Tool | Mode | Task | n | Verified | Success | Median ms | p90 ms | p95 ms |
|---|---|---|---:|---:|---:|---:|---:|---:|
| CUA 0.38.0 | warm | read | 80 | 80 | 100% | 50.5 | 68.7 | 79.3 |
| opencli 2.0.2 | warm | read | 80 | 80 | 100% | 778.0 | 866.3 | 883.2 |
| CUA 0.38.0 | warm | write | 80 | 80 | 100% | 261.5 | 304.5 | 316.0 |
| opencli 2.0.2 | warm | write | 80 | 80 | 100% | 918.4 | 1001.3 | 1018.0 |
| CUA 0.38.0 | cold | read | 80 | 80 | 100% | 731.8 | 1068.3 | 1321.2 |
| opencli 2.0.2 | cold | read | 80 | 80 | 100% | 1350.3 | 1733.3 | 1919.7 |
| CUA 0.38.0 | cold | write | 80 | 80 | 100% | 2216.6 | 2775.0 | 2989.4 |
| opencli 2.0.2 | cold | write | 80 | 80 | 100% | 1528.3 | 1910.6 | 2098.9 |

Paired by block (per block: mean CUA minus mean opencli; 40 complete blocks per row; seeded
bootstrap 95% interval of the median):

| Mode | Task | Median delta (CUA - opencli) | 95% CI | Blocks where CUA was faster |
|---|---|---:|---|---:|
| warm | read | -715.9 ms | [-738.1, -709.7] | 40/40 |
| warm | write | -663.1 ms | [-669.7, -648.1] | 40/40 |
| cold | read | -624.1 ms | [-646.3, -603.2] | 39/40 |
| cold | write | +660.5 ms | [+627.8, +712.6] | 0/40 |

Safety, all 680 attempts: 0 unauthorized effects, 0 duplicate commits, 0 wrong targets, 0 uncertain
effects, 0 fallbacks, 0 retries, 0 model calls.

Headline: on this fixture, CUA 0.38.0 is faster in 3 of 4 conditions (warm read, warm write, cold
read). opencli is faster for cold write. Both tools verified 640/640 timed attempts.

## Caveats (read before citing)

- One synthetic loopback page, one read task and one write task. This is not a real-site benchmark.
- The warm routes differ in shape: CUA keeps one MCP server process; opencli runs one CLI process per
  call (its normal CDP route). Process start alone is small (`opencli --version` 24-164 ms,
  `cua-driver --version` 2-46 ms, in `results/shards.jsonl`), so most of opencli's ~780 ms warm read
  is per-call CDP connect, adapter discovery and navigation. This rerun does not break it down.
- The read mechanics differ: CUA returns a full semantic_v2 page snapshot; the opencli adapter
  evaluates one selector.
- Cold CUA write is ~1.5 s slower than cold CUA read, but warm CUA write is only ~0.2 s slower than
  warm read, with the same tool-call count (8 vs 5 cold, 5 vs 2 warm). The extra cost seems to come
  from the first input or submit in a freshly launched isolated browser. Per-call timing was not
  recorded, so this is not proven.
- 5 VM starts refused `browser_prepare` (`browser_route_unavailable`) during warm-up, before any
  timed attempt. Boot-time image provisioning was still writing under `/opt` at that time. Those
  shards (1, 7, 8, 9; shard 8 twice) were rerun from the start on fresh VMs with the same plan. No
  timed attempt was discarded. `vm_bootstrap.sh` now waits for boot to finish and for stable `/opt`
  ownership.
- Boat VMs differ between shards. Both tools run interleaved on the same VM in every block.

## Pomerado arm: NOT_RUN

The subscription-transport work for minting (fork branch `feat/chatgpt-transport-apply-patch`
@ `f541fe5c`, draft PR kvnloo/pomerado#1) passed unit tests, plus one live smoke request (HTTP 200).
A full live mint has not completed, and no minted fixture integration exists. Minting also needs a
model credential, and that credential may not leave the trusted host. Boat runs public source only,
with no secrets. So Pomerado has no warm or cold cell here. It stays NOT_RUN until a mint has
completed and its artifact is published by digest.

## Files

- `h2h_run.py`: shard runner (plan, both tools, oracle, receipts). `python3 h2h_run.py --print-plan` prints `plan.json`.
- `vm_bootstrap.sh <harness-sha> <shard>`: fresh-VM setup. It fetches the files at an exact SHA, then
  verifies the driver and opencli digests before it runs one shard.
- `adapters/jev/`: the opencli adapters used.
- `analyze.py`: makes `results/summary.json` from `results/attempts.jsonl`.
- `results/attempts.jsonl`: raw per-attempt receipts (`cua.h2h.attempt.v1`, 680 lines; warm-ups are flagged `"warmup": true`).
- `results/shards.jsonl`: per-shard pins, plan, process-start baselines, done markers.
- `results/vm_ledger.json`: every Boat VM used (exec seconds, billed seconds, setup refusals).

Reproduce one shard on a fresh Ubuntu 24.04 VM with Chrome 151 and an X display:
`bash vm_bootstrap.sh <harness-sha> <shard 0-9>`.

Credit: opencli is [jackwener/opencli](https://github.com/jackwener/opencli). Pomerado is MIT,
Pomerado AI, Inc. CUA is [trycua/cua](https://github.com/trycua/cua).
