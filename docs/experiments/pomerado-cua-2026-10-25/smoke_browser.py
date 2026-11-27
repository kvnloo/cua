#!/usr/bin/env python3
"""Browser/fixture contract probe. DOES NOT exercise CUA Driver or Pomerado.

Runs real isolated Chromium against the existing jev-use fixture and checks
its independent HTTP oracle. Intended as a cheap prerequisite for remote
Avrea/Boat A/B runs; results are NEVER labelled as CUA or Pomerado trials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from threading import Thread
from time import perf_counter
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "libs/cua-driver/examples/jev-use/fixture_server.py"
CASES = ("read_only", "submit", "duplicate_target", "renamed_target",
         "visual_only", "origin_escape", "wrong_input", "uncertain_commit")


def fixture_server(*, visual: bool):
    spec = importlib.util.spec_from_file_location("cua_jev_fixture", FIXTURE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load original CUA fixture")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    server = module.FixtureServer(("127.0.0.1", 0), visual=visual)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return server, worker


def oracle(base: str) -> dict:
    with urlopen(base + "/state", timeout=3) as response:
        return json.load(response)


def reset(base: str) -> None:
    with urlopen(Request(base + "/reset", data=b"", method="POST"), timeout=3) as response:
        if response.status != 204:
            raise AssertionError(f"Unexpected reset status: {response.status}")
    if oracle(base) != {"submitted": None}:
        raise AssertionError("Reset not verified by independent oracle")


def chrome_path() -> str | None:
    return next((path for name in ("chromium", "google-chrome", "google-chrome-stable")
                 if (path := shutil.which(name))), None)


def one_case(browser, case: str, iteration: int) -> dict:
    visual = case == "visual_only"
    server, thread = fixture_server(visual=visual)
    base = f"http://127.0.0.1:{server.server_port}"
    context = browser.new_context()
    started = perf_counter()
    status = "FAILED"
    oracle_result = "unknown"
    error = None
    try:
        reset(base)
        page = context.new_page()
        page.goto(base + "/", wait_until="load", timeout=15000)
        if not page.url.startswith(base + "/"):
            raise AssertionError("Page exited approved origin")
        field = page.get_by_role("textbox", name="verification value")
        submit = page.get_by_role("button", name="Submit", exact=True)
        token = f"fixture_{iteration}_{case}"  # synthetic, never a secret
        if case == "read_only":
            assert field.count() == 1 and submit.count() == 1
            assert oracle(base) == {"submitted": None}
            oracle_result = "unchanged"
        elif case == "submit":
            assert field.count() == 1 and submit.count() == 1
            field.fill(token)
            submit.click(timeout=5000)
            assert oracle(base) == {"submitted": token}
            oracle_result = "verified"
        elif case == "duplicate_target":
            page.evaluate("""() => {
              const original = document.querySelector('button[type=submit]');
              original.after(original.cloneNode(true));
            }""")
            assert submit.count() == 2  # ambiguous; refuse, do not dispatch
            assert oracle(base) == {"submitted": None}
            oracle_result = "refused_ambiguous"
        elif case == "renamed_target":
            page.locator("button[type=submit]").evaluate("(button) => button.textContent = 'Confirm'")
            assert submit.count() == 0  # invalidated prior learned locator
            assert oracle(base) == {"submitted": None}
            oracle_result = "refused_changed"
        elif case == "visual_only":
            assert field.count() == 1 and submit.count() == 0
            assert page.get_by_text("Submit", exact=True).count() == 1
            assert oracle(base) == {"submitted": None}
            oracle_result = "refused_semantic_route"
        elif case == "origin_escape":
            page.goto("about:blank")
            assert not page.url.startswith(base + "/")
            assert oracle(base) == {"submitted": None}
            oracle_result = "refused_origin"
        elif case == "wrong_input":
            field.fill("wrong_" + token)
            submit.click(timeout=5000)
            assert oracle(base) == {"submitted": "wrong_" + token}
            oracle_result = "refuted_wrong_value"
        elif case == "uncertain_commit":
            field.fill(token)
            submit.click(timeout=5000)
            # Simulate lost acknowledgement *after* the one synthetic submit.
            # Independent /state read proves the write; a safe caller must not replay.
            assert oracle(base) == {"submitted": token}
            assert page.get_by_role("button", name="Submit", exact=True).count() == 0
            oracle_result = "reconciled_no_repeat"
        else:
            raise AssertionError(f"Unknown case: {case}")
        status = "PASSED"
    except Exception as exc:
        error = f"{type(exc).__name__}: {str(exc)[:220]}"
    finally:
        context.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    return {
        "schema": "cua.pomerado.fixture_browser_smoke.v1",
        "evidence_class": "FIXTURE_BROWSER_ONLY",
        "executor": "playwright_chromium_not_CUA_not_Pomerado",
        "case": case, "iteration": iteration,
        "status": status, "oracle_result": oracle_result,
        "elapsed_ms": round((perf_counter() - started) * 1000, 2),
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output", type=Path, help="Write redacted JSONL; never commit as CUA/Pomerado A/B evidence")
    args = parser.parse_args()
    if args.repeat < 1 or args.repeat > 100:
        parser.error("repeat must be 1..100")
    if not FIXTURE.is_file():
        raise SystemExit("BLOCKED: original jev-use fixture missing")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("BLOCKED: pip install playwright==1.57.0")
    records = []
    with sync_playwright() as playwright:
        kwargs = {"headless": True, "args": ["--no-sandbox", "--disable-dev-shm-usage"]}
        if (binary := chrome_path()):
            kwargs["executable_path"] = binary
        browser = playwright.chromium.launch(**kwargs)
        browser_version = browser.version
        try:
            for i in range(args.repeat):
                for case in CASES:
                    records.append(one_case(browser, case, i))
        finally:
            browser.close()
    for item in records:
        item["chromium_version"] = browser_version
    summary = {
        "schema": "cua.pomerado.fixture_browser_smoke_summary.v1",
        "evidence_class": "FIXTURE_BROWSER_ONLY",
        "measured_utc": datetime.now(timezone.utc).isoformat(),
        "fixture_path": str(FIXTURE.relative_to(ROOT)),
        "total": len(records),
        "passed": sum(r["status"] == "PASSED" for r in records),
        "failed": sum(r["status"] != "PASSED" for r in records),
        "chromium_version": browser_version,
        "driver_trials": 0, "pomerado_trials": 0,
        "claim": "No CUA/Pomerado benchmark or production correctness claim",
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))
    print(json.dumps(summary, sort_keys=True))
    for item in records:
        if item["status"] != "PASSED":
            print(json.dumps(item, sort_keys=True), file=sys.stderr)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
