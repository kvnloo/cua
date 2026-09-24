#!/usr/bin/env python3
"""Characterize PR #4011's cursor admission using unchanged production excerpts.

No GNOME/D-Bus access. The real dispatcher, queue, six public helper methods,
and overlay forwarding function are compiled by rustc. Only display I/O,
logging, and the unrelated overlay type/color helpers are replaced by test
adapters. The worker is paused by channels, not by a guessed sleep duration.
This is a source-component test, not a full workspace or desktop test.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

PIN = "54802e70cc7fdcad5f8c5d3a992610d0ca0d777a"
SHELL = "libs/cua-driver/rust/crates/platform-linux/src/wayland/shell_helper.rs"
OVERLAY = "libs/cua-driver/rust/crates/platform-linux/src/overlay.rs"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def span(text: str, start: str, end: str) -> str:
    if text.count(start) != 1:
        raise ValueError(f"Non-unique start marker: {start!r}")
    left = text.index(start)
    right = text.index(end, left)
    return text[left:right]


PRELUDE = r'''
#![allow(dead_code)]
extern crate self as tracing;
#[macro_export] macro_rules! warn { ($($token:tt)*) => {{}}; }
#[macro_export] macro_rules! debug { ($($token:tt)*) => {{}}; }

// Value/type adapters only. No queue, worker, or forwarding behavior lives here.
mod cursor_overlay {
    pub enum Name { Test }
    impl Name { pub fn as_str(&self) -> &'static str { "test" } }
    pub enum OverlayCommand {
        MoveTo { x: f64, y: f64 },
        SnapTo { x: f64, y: f64 },
        ClickPulse { x: f64, y: f64 },
        BeginAction { action: Name, delivery: Option<Name>, target: Option<Name> },
        EndAction(Name), SetSessionLabel(String), SetEnabled(bool), Other,
    }
    pub fn session_fill_hex(key: &str) -> String { format!("test-color:{key}") }
    pub fn sanitize_session_label(label: &str) -> Option<String> { Some(label.to_owned()) }
}
mod wayland {
  pub mod shell_helper {
    use std::collections::VecDeque;
    use std::sync::{Arc, Condvar, Mutex, OnceLock};
    use std::time::Duration;
    // Fail immediately if a test ever escapes the existing dispatcher injection.
    fn gdbus_call(_: &str, _: &[String]) -> Option<String> {
        panic!("real helper I/O is forbidden in this fixture")
    }
'''

TESTS = r'''
#[cfg(test)]
mod tests {
    use super::*;
    use crate::cursor_overlay::OverlayCommand;
    use std::sync::mpsc;

    // Same thread-local injection seam used by the PR's own tests.
    thread_local! {
        pub(super) static VISUAL_OVERRIDE: std::cell::RefCell<Option<Arc<VisualDispatcher>>> =
            const { std::cell::RefCell::new(None) };
    }

    fn request(method: &'static str, args: &[&str]) -> VisualRequest {
        VisualRequest { method, args: args.iter().map(|x| x.to_string()).collect() }
    }

    fn run_case(prefill: usize, semantic: bool, command: OverlayCommand) -> Vec<VisualRequest> {
        let (entered_tx, entered_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let (seen_tx, seen_rx) = mpsc::channel();
        let mut first = true;
        let (dispatcher, worker) = VisualDispatcher::spawn(move |item| {
            if first {
                first = false;
                entered_tx.send(()).unwrap();
                release_rx.recv_timeout(Duration::from_secs(5)).expect("release worker");
            }
            seen_tx.send(item).unwrap();
        }).unwrap();
        let dispatcher = Arc::new(dispatcher);
        VISUAL_OVERRIDE.with(|slot| {
            assert!(slot.borrow_mut().replace(dispatcher.clone()).is_none());
        });
        dispatcher.enqueue(request("MoveCursor", &["priming", "0"])).unwrap();
        entered_rx.recv_timeout(Duration::from_secs(5)).expect("native worker entry");
        for _ in 0..prefill {
            dispatcher.enqueue(request("MoveCursor", &["producer-A", "0"])).unwrap();
        }
        assert_eq!(dispatcher.shared.0.lock().unwrap().pending.len(), prefill);

        // This calls the exact production overlay forwarding function below.
        crate::forwarding::forward("producer-B", &command, semantic);
        let admitted = dispatcher.shared.0.lock().unwrap().pending.len() - prefill;
        release_tx.send(()).unwrap();

        // Read exactly the admitted set; do not infer dropping from a timeout.
        let mut seen = Vec::new();
        for _ in 0..(1 + prefill + admitted) {
            seen.push(seen_rx.recv_timeout(Duration::from_secs(5)).expect("drain admitted item"));
        }
        VISUAL_OVERRIDE.with(|slot| { slot.borrow_mut().take(); });
        drop(dispatcher);
        worker.join().expect("worker shutdown");
        let cleanup: Vec<_> = seen_rx.into_iter().collect();
        assert_eq!(cleanup, vec![VisualRequest::hide()], "exactly one shutdown hide");

        let mut actual: Vec<_> = seen.into_iter().skip(1 + prefill).collect();
        println!("CASE prefill={prefill} semantic={semantic} admitted={admitted} observed={actual:?}");
        actual.shrink_to_fit();
        actual
    }

    fn movement() -> OverlayCommand { OverlayCommand::MoveTo { x: 40.0, y: 50.0 } }
    fn color() -> VisualRequest { request("SetCursorColor", &["test-color:producer-B"]) }
    fn moved() -> VisualRequest { request("MoveCursor", &["40", "50"]) }

    #[test]
    fn control_two_free_slots_delivers_both_parts() {
        assert_eq!(run_case(62, true, movement()), vec![color(), moved()]);
    }
    #[test]
    fn control_full_queue_rejects_both_parts() {
        assert_eq!(run_case(64, true, movement()), vec![]);
    }
    #[test]
    fn control_one_free_slot_handles_single_nonsemantic_move() {
        assert_eq!(run_case(63, false, movement()), vec![moved()]);
    }
    #[test]
    fn control_terminal_hide_survives_full_queue() {
        assert_eq!(run_case(64, true, OverlayCommand::SetEnabled(false)), vec![VisualRequest::hide()]);
    }
    #[test]
    fn regression_one_free_slot_never_delivers_color_without_movement() {
        let seen = run_case(63, true, movement());
        assert!(seen.is_empty() || seen == vec![color(), moved()],
            "logical update was split: expected both parts or neither, got {seen:?}");
    }
}
  }
}
'''


def main() -> None:
    output = Path("queue-evidence")
    output.mkdir(exist_ok=True)
    provenance = {"repository": "trycua/cua", "source_commit": PIN, "runner_commit": git("rev-parse", "HEAD"), "sources": {}}
    sources = {}
    for path in (SHELL, OVERLAY):
        original = subprocess.check_output(["git", "show", f"{PIN}:{path}"])
        current = Path(path).read_bytes()
        if current != original:
            raise ValueError(f"Source differs from pinned PR: {path}")
        sources[path] = original.decode()
        provenance["sources"][path] = {"git_blob": git("rev-parse", f"{PIN}:{path}"), "sha256": hashlib.sha256(original).hexdigest()}
    visual = span(sources[SHELL], "// One process-wide dispatcher matches", "#[cfg(test)]\nmod tests {")
    forwarding = span(sources[OVERLAY], '#[cfg(target_os = "linux")]\nfn dispatch_shell_helper_command', "\npub fn is_enabled()")
    provenance["excerpts_sha256"] = {"visual": hashlib.sha256(visual.encode()).hexdigest(), "forwarding": hashlib.sha256(forwarding.encode()).hexdigest()}
    code = PRELUDE + visual + TESTS + '\nmod forwarding {\nuse crate::cursor_overlay::{self, OverlayCommand};\n' + forwarding + '\npub fn forward(key: &str, cmd: &OverlayCommand, semantic: bool) { dispatch_shell_helper_command(key, cmd, semantic); }\n}\n'
    generated = output / "source_component_test.rs"
    generated.write_text(code)
    provenance["rustc"] = subprocess.check_output(["rustc", "--version", "--verbose"], text=True).strip()
    provenance["generated_test_sha256"] = hashlib.sha256(code.encode()).hexdigest()
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    build = subprocess.run(["rustc", "--edition=2021", "--test", str(generated), "-o", str(output / "queue-test")], text=True, capture_output=True, timeout=90)
    (output / "build.log").write_text(build.stdout + build.stderr)
    if build.returncode:
        print(build.stdout + build.stderr)
        raise SystemExit(build.returncode)
    tested = subprocess.run([str(output / "queue-test"), "--test-threads=1", "--nocapture"], text=True, capture_output=True, timeout=45)
    log = tested.stdout + tested.stderr
    (output / "tests.log").write_text(log)
    print(log)
    expected = tested.returncode != 0 and "4 passed; 1 failed" in log and "regression_one_free_slot_never_delivers_color_without_movement" in log and "logical update was split" in log
    summary = {"source_commit": PIN, "controls_passed": 4 if expected else None, "desired_behavior_regression": "FAIL_REPRODUCED" if expected else "UNEXPECTED_RESULT", "native_test_exit_code": tested.returncode, "desktop_validation": "NOT_RUN", "test_scope": "Unchanged extracted production queue, worker, helper methods and forwarding; test display sink and value/type adapters", "interpretation": "Expected-red characterization is not product acceptance and not evidence of desktop rendering."}
    (output / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not expected:
        raise SystemExit("Expected-red test did not produce the specified failure and passing controls")


if __name__ == "__main__":
    main()
