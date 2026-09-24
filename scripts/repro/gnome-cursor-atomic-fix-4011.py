#!/usr/bin/env python3
"""Fork-only red/green experiment for PR #4011, not desktop certification.

Apply a guarded two-file candidate in the CI worktree, export its ordinary git
patch, then compile actual production excerpts using the earlier fixture.
The original five test assertions are unchanged between baseline and candidate.
No product source is committed or pushed by this runner.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("baseline", HERE / "gnome-cursor-admission-4011.py")
assert spec and spec.loader
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)
OUT = Path("atomic-evidence")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"Expected one patch anchor, found {text.count(old)}: {old[:100]!r}")
    return text.replace(old, new, 1)


QUEUE_OLD = '''    fn enqueue(&self, request: VisualRequest) -> Result<(), VisualQueueError> {
        let (lock, ready) = &*self.shared;'''
QUEUE_NEW = '''    fn enqueue(&self, request: VisualRequest) -> Result<(), VisualQueueError> {
        self.enqueue_batch(vec![request])
    }

    // Capacity counts helper calls, not batches. Only a singleton hide may
    // use the reserved terminal slot; ordinary batches fit completely or fail.
    fn enqueue_batch(&self, requests: Vec<VisualRequest>) -> Result<(), VisualQueueError> {
        let (lock, ready) = &*self.shared;'''

HELPER_OLD = '''fn enqueue_visual(method: &'static str, args: Vec<String>) {
    let result = with_visual_dispatcher(|dispatcher| {
        dispatcher
            .ok_or(VisualQueueError::Closed)
            .and_then(|dispatcher| dispatcher.enqueue(VisualRequest { method, args }))
    });
    if let Err(error) = result {
        tracing::warn!(method, ?error, "GNOME visual queue rejected command");
    }
}'''
HELPER_NEW = '''fn enqueue_visual(method: &'static str, args: Vec<String>) {
    enqueue_visual_with_color(None, method, args);
}

/// Admit a semantic update and its session color under one queue lock.
/// This is atomic admission, not atomic execution of separate helper calls.
pub(crate) fn enqueue_visual_with_color(
    color: Option<String>,
    method: &'static str,
    args: Vec<String>,
) {
    let result = with_visual_dispatcher(|dispatcher| {
        let dispatcher = dispatcher.ok_or(VisualQueueError::Closed)?;
        let request = VisualRequest { method, args };
        match color {
            Some(color) => dispatcher.enqueue_batch(vec![
                VisualRequest {
                    method: "SetCursorColor",
                    args: vec![color],
                },
                request,
            ]),
            None => dispatcher.enqueue(request),
        }
    });
    if let Err(error) = result {
        tracing::warn!(method, ?error, "GNOME visual queue rejected command");
    }
}'''

FORWARD_NEW = '''#[cfg(target_os = "linux")]
fn dispatch_shell_helper_command(key: &str, cmd: &OverlayCommand, semantic: bool) {
    let (method, args) = match cmd {
        OverlayCommand::ClickPulse { x, y } if semantic => (
            "ClickPulse",
            vec![(*x as i32).to_string(), (*y as i32).to_string()],
        ),
        OverlayCommand::MoveTo { x, y, .. }
        | OverlayCommand::SnapTo { x, y, .. }
        | OverlayCommand::ClickPulse { x, y } => (
            "MoveCursor",
            vec![(*x as i32).to_string(), (*y as i32).to_string()],
        ),
        OverlayCommand::BeginAction {
            action,
            delivery,
            target,
        } if semantic => (
            "SetCursorState",
            vec![
                action.as_str().to_owned(),
                delivery.as_ref().map_or("", |value| value.as_str()).to_owned(),
                target.as_ref().map_or("", |value| value.as_str()).to_owned(),
                true.to_string(),
            ],
        ),
        OverlayCommand::EndAction(action) if semantic => (
            "SetCursorState",
            vec![action.as_str().to_owned(), String::new(), String::new(), false.to_string()],
        ),
        OverlayCommand::SetSessionLabel(label) if semantic => (
            "SetSessionLabel",
            vec![cursor_overlay::sanitize_session_label(label).unwrap_or_default()],
        ),
        _ => {
            // Preserve the existing color-only behavior for unrelated commands.
            // Hide stays on its singleton path so saturation cannot reject it.
            if semantic {
                crate::wayland::shell_helper::set_cursor_color(&cursor_overlay::session_fill_hex(key));
            }
            if matches!(cmd, OverlayCommand::SetEnabled(false)) {
                crate::wayland::shell_helper::hide_cursor();
            }
            return;
        }
    };
    crate::wayland::shell_helper::enqueue_visual_with_color(
        semantic.then(|| cursor_overlay::session_fill_hex(key)),
        method,
        args,
    );
}
'''

EXTRA_TESTS = r'''
    #[test]
    fn all_semantic_command_pairs_survive_or_reject_together() {
        use crate::cursor_overlay::Name;
        let cases = vec![
            (OverlayCommand::SnapTo { x: 40.0, y: 50.0 }, moved()),
            (OverlayCommand::ClickPulse { x: 40.0, y: 50.0 }, request("ClickPulse", &["40", "50"])),
            (OverlayCommand::BeginAction { action: Name::Test, delivery: Some(Name::Test), target: Some(Name::Test) }, request("SetCursorState", &["test", "test", "test", "true"])),
            (OverlayCommand::EndAction(Name::Test), request("SetCursorState", &["test", "", "", "false"])),
            (OverlayCommand::SetSessionLabel("session-B".into()), request("SetSessionLabel", &["session-B"])),
        ];
        for (command, expected) in cases {
            assert_eq!(run_case(62, true, command), vec![color(), expected]);
        }
        for command in [
            OverlayCommand::SnapTo { x: 40.0, y: 50.0 },
            OverlayCommand::ClickPulse { x: 40.0, y: 50.0 },
            OverlayCommand::BeginAction { action: Name::Test, delivery: None, target: None },
            OverlayCommand::EndAction(Name::Test),
            OverlayCommand::SetSessionLabel("session-B".into()),
        ] {
            assert!(run_case(63, true, command).is_empty());
        }
    }

    #[test]
    fn legacy_pulse_remains_a_single_movement() {
        assert_eq!(run_case(63, false, OverlayCommand::ClickPulse { x: 40.0, y: 50.0 }), vec![moved()]);
    }

    #[test]
    fn hide_keeps_reserved_slot_even_after_a_rejected_pair() {
        // Construct an owned queue directly: no worker can drain it during admission.
        let dispatcher = VisualDispatcher { shared: Arc::new((Mutex::new(VisualQueue::default()), Condvar::new())) };
        for _ in 0..63 { dispatcher.enqueue(request("MoveCursor", &["old"])).unwrap(); }
        assert_eq!(dispatcher.enqueue_batch(vec![color(), moved()]), Err(VisualQueueError::Full));
        assert_eq!(dispatcher.shared.0.lock().unwrap().pending.len(), 63);
        dispatcher.enqueue(request("MoveCursor", &["single"])).unwrap();
        dispatcher.enqueue(VisualRequest::hide()).unwrap();
        dispatcher.enqueue(VisualRequest::hide()).unwrap();
        assert_eq!(dispatcher.shared.0.lock().unwrap().pending.len(), 65);
        assert_eq!(dispatcher.enqueue_batch(vec![color(), moved()]), Err(VisualQueueError::Full));
        let guard = dispatcher.shared.0.lock().unwrap();
        assert_eq!(guard.pending.back(), Some(&VisualRequest::hide()));
    }

    #[test]
    fn batches_do_not_expand_the_helper_call_capacity() {
        let dispatcher = VisualDispatcher { shared: Arc::new((Mutex::new(VisualQueue::default()), Condvar::new())) };
        for _ in 0..32 { dispatcher.enqueue_batch(vec![color(), moved()]).unwrap(); }
        assert_eq!(dispatcher.shared.0.lock().unwrap().pending.len(), 64);
        assert_eq!(dispatcher.enqueue_batch(vec![color(), moved()]), Err(VisualQueueError::Full));
        assert_eq!(dispatcher.enqueue(request("MoveCursor", &["extra"])), Err(VisualQueueError::Full));
    }

    #[test]
    fn closed_queue_rejects_the_whole_batch() {
        let dispatcher = VisualDispatcher { shared: Arc::new((Mutex::new(VisualQueue { pending: Default::default(), closed: true }), Condvar::new())) };
        assert_eq!(dispatcher.enqueue_batch(vec![color(), moved()]), Err(VisualQueueError::Closed));
        assert!(dispatcher.shared.0.lock().unwrap().pending.is_empty());
    }

    #[test]
    fn concurrent_producers_cannot_split_or_interleave_the_last_pair() {
        let (entered_tx, entered_rx) = mpsc::channel();
        let (release_tx, release_rx) = mpsc::channel();
        let (seen_tx, seen_rx) = mpsc::channel();
        let mut first = true;
        let (dispatcher, worker) = VisualDispatcher::spawn(move |item| {
            if first {
                first = false;
                entered_tx.send(()).unwrap();
                release_rx.recv_timeout(Duration::from_secs(5)).unwrap();
            }
            seen_tx.send(item).unwrap();
        }).unwrap();
        let dispatcher = Arc::new(dispatcher);
        dispatcher.enqueue(request("MoveCursor", &["priming"])).unwrap();
        entered_rx.recv_timeout(Duration::from_secs(5)).unwrap();
        for _ in 0..62 { dispatcher.enqueue(request("MoveCursor", &["old"])).unwrap(); }
        let start = Arc::new(std::sync::Barrier::new(3));
        let mut producers = Vec::new();
        for key in ["B", "C"] {
            let queue = dispatcher.clone();
            let start = start.clone();
            producers.push(std::thread::spawn(move || {
                VISUAL_OVERRIDE.with(|slot| { *slot.borrow_mut() = Some(queue); });
                start.wait();
                crate::forwarding::forward(key, &movement(), true);
                VISUAL_OVERRIDE.with(|slot| { slot.borrow_mut().take(); });
            }));
        }
        start.wait();
        for producer in producers { producer.join().unwrap(); }
        assert_eq!(dispatcher.shared.0.lock().unwrap().pending.len(), 64);
        release_tx.send(()).unwrap();
        let mut seen = Vec::new();
        for _ in 0..65 { seen.push(seen_rx.recv_timeout(Duration::from_secs(5)).unwrap()); }
        let tail = &seen[63..];
        assert_eq!(tail.len(), 2);
        assert_eq!(tail[0].method, "SetCursorColor");
        assert!(tail[0].args == vec!["test-color:B"] || tail[0].args == vec!["test-color:C"]);
        assert_eq!(tail[1], moved());
        drop(dispatcher);
        worker.join().unwrap();
        assert_eq!(seen_rx.into_iter().collect::<Vec<_>>(), vec![VisualRequest::hide()]);
    }
'''


def run(command: list[str], *, timeout: int = 90) -> subprocess.CompletedProcess:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout)


def compile_and_test(label: str, shell: str, overlay: str, extra: bool = False) -> dict:
    visual = baseline.span(shell, "// One process-wide dispatcher matches", "#[cfg(test)]\nmod tests {")
    forwarding = baseline.span(overlay, '#[cfg(target_os = "linux")]\nfn dispatch_shell_helper_command', "\npub fn is_enabled()")
    tests = baseline.TESTS
    if extra:
        tests = replace_once(tests, "    fn movement() -> OverlayCommand", EXTRA_TESTS + "\n    fn movement() -> OverlayCommand")
    code = baseline.PRELUDE + visual + tests + '\nmod forwarding {\nuse crate::cursor_overlay::{self, OverlayCommand};\n' + forwarding + '\npub fn forward(key: &str, cmd: &OverlayCommand, semantic: bool) { dispatch_shell_helper_command(key, cmd, semantic); }\n}\n'
    source = OUT / f"{label}.rs"
    executable = OUT / label
    source.write_text(code)
    built = run(["rustc", "--edition=2021", "--test", str(source), "-o", str(executable)])
    (OUT / f"{label}-build.log").write_text(built.stdout + built.stderr)
    if built.returncode:
        raise RuntimeError(built.stdout + built.stderr)
    tested = run([str(executable), "--test-threads=1", "--nocapture"], timeout=60)
    log = tested.stdout + tested.stderr
    (OUT / f"{label}-tests.log").write_text(log)
    print(f"\n=== {label} ===\n{log}")
    match = re.search(r"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed", log)
    if not match:
        raise RuntimeError("Missing native test summary")
    return {"passed": int(match[1]), "failed": int(match[2]), "exit_code": tested.returncode, "generated_sha256": hashlib.sha256(code.encode()).hexdigest()}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    original = {}
    provenance = {"source_commit": baseline.PIN, "runner_commit": baseline.git("rev-parse", "HEAD"), "files": {}}
    for path in (baseline.SHELL, baseline.OVERLAY):
        data = subprocess.check_output(["git", "show", f"{baseline.PIN}:{path}"])
        if Path(path).read_bytes() != data:
            raise RuntimeError(f"Worktree is not pinned source: {path}")
        original[path] = data.decode()
        provenance["files"][path] = {"before_sha256": hashlib.sha256(data).hexdigest()}
    red = compile_and_test("baseline", original[baseline.SHELL], original[baseline.OVERLAY])
    if (red["passed"], red["failed"], red["exit_code"]) != (4, 1, 101):
        raise RuntimeError(f"Baseline did not reproduce the known failure: {red}")
    shell = replace_once(original[baseline.SHELL], QUEUE_OLD, QUEUE_NEW)
    shell = replace_once(shell, "        if request.is_hide() {", "        if requests.len() == 1 && requests[0].is_hide() {")
    shell = replace_once(shell, "        } else if queue.pending.len() >= VISUAL_QUEUE_CAPACITY {", "        } else if requests.len() > VISUAL_QUEUE_CAPACITY.saturating_sub(queue.pending.len()) {")
    shell = replace_once(shell, "        queue.pending.push_back(request);", "        queue.pending.extend(requests);")
    shell = replace_once(shell, HELPER_OLD, HELPER_NEW)
    old_forward = baseline.span(original[baseline.OVERLAY], '#[cfg(target_os = "linux")]\nfn dispatch_shell_helper_command', "\npub fn is_enabled()")
    overlay = replace_once(original[baseline.OVERLAY], old_forward, FORWARD_NEW)
    for path, text in ((baseline.SHELL, shell), (baseline.OVERLAY, overlay)):
        Path(path).write_text(text)
        formatted = run(["rustfmt", "--edition", "2021", path])
        if formatted.returncode:
            raise RuntimeError(formatted.stdout + formatted.stderr)
        provenance["files"][path]["after_sha256"] = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    diff = subprocess.check_output(["git", "diff", "--", baseline.SHELL, baseline.OVERLAY], text=True)
    (OUT / "candidate.patch").write_text(diff)
    checked = run(["git", "diff", "--check", "--", baseline.SHELL, baseline.OVERLAY])
    if checked.returncode:
        raise RuntimeError(checked.stdout + checked.stderr)
    # Compile exact candidate worktree excerpts, not the unformatted input strings.
    shell, overlay = Path(baseline.SHELL).read_text(), Path(baseline.OVERLAY).read_text()
    green = compile_and_test("candidate", shell, overlay, extra=True)
    if (green["passed"], green["failed"], green["exit_code"]) != (11, 0, 0):
        raise RuntimeError(f"Candidate failed: {green}")
    repetitions = []
    for index in range(20):
        tested = run([str(OUT / "candidate"), "--test-threads=4"], timeout=60)
        (OUT / f"repeat-{index + 1:02d}.log").write_text(tested.stdout + tested.stderr)
        if tested.returncode or "11 passed; 0 failed" not in tested.stdout:
            raise RuntimeError(f"Parallel repetition {index + 1} failed")
        repetitions.append({"iteration": index + 1, "passed": 11, "failed": 0})
    provenance["rustc"] = subprocess.check_output(["rustc", "--version", "--verbose"], text=True).strip()
    provenance["patch_sha256"] = hashlib.sha256(diff.encode()).hexdigest()
    (OUT / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    result = {"baseline": red, "candidate": green, "parallel_repetitions": len(repetitions), "parallel_test_executions": len(repetitions) * 11, "product_files_changed": 2, "queue_capacity": "64 helper calls plus one reserved hide; unchanged", "ordering": "FIFO helper call order; no coalescing", "atomicity": "Queue admission only; NOT atomic D-Bus execution", "full_workspace_check": "NOT_RUN", "live_desktop_validation": "NOT_RUN", "upstream_changes": "NONE"}
    (OUT / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print("\n=== RED/GREEN RESULT ===\n" + json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
