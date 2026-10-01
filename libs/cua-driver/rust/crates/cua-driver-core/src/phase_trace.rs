//! Measurement-only phase trace (research experiments R2-01 and R2-04; this
//! file is the union of both mark sets).
//!
//! EXPERIMENT ONLY, not for promotion and not a public contract.
//!
//! Default off. It is enabled only when `CUA_DRIVER_PHASE_TRACE_FILE` names a
//! writable file when the first mark is attempted. When off, [`mark`] and
//! [`mark_detail`] are one initialized-`OnceLock` read and return: no file is
//! opened, no detail is built and no behaviour changes. When on, each mark
//! appends one JSON line:
//!
//! `{"t_mono_ns", "wall_ns", "seq", "phase", "session", "detail"}`
//!
//! `t_mono_ns` is host `CLOCK_MONOTONIC` (the clock behind Python's
//! `time.monotonic_ns()` on Linux), so a caller and a fixture on the same host
//! can align marks with their own readings; `wall_ns` is `CLOCK_REALTIME`.
//! Both mark functions take two identifiers. The R2-01 call sites pass
//! `(phase, browser session)`; the R2-04 call sites pass `(scope, mark)` in
//! the same two slots, so for those a consumer keys a mark as
//! `phase + "/" + session` (for example `atspi_action/do_action_replied`).
//! Marks are hints for a timing profile only: nothing reads them back, and
//! they never gate, verify, or authorize anything.

use std::io::Write;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;

/// The environment variable that enables the trace. The `CUA_DRIVER_` prefix
/// is the one the jev-use example runners already forward to the Driver.
pub const PHASE_TRACE_ENV: &str = "CUA_DRIVER_PHASE_TRACE_FILE";

static SINK: OnceLock<Option<Mutex<std::fs::File>>> = OnceLock::new();
static SEQ: AtomicU64 = AtomicU64::new(0);

fn open_sink(path: Option<std::ffi::OsString>) -> Option<Mutex<std::fs::File>> {
    let path = path.filter(|p| !p.is_empty())?;
    std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .ok()
        .map(Mutex::new)
}

fn sink() -> Option<&'static Mutex<std::fs::File>> {
    SINK.get_or_init(|| open_sink(std::env::var_os(PHASE_TRACE_ENV)))
        .as_ref()
}

/// Whether the trace is enabled for this process.
pub fn enabled() -> bool {
    sink().is_some()
}

/// Host monotonic time in nanoseconds (`CLOCK_MONOTONIC` on Unix).
#[cfg(unix)]
pub fn monotonic_ns() -> u64 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: `ts` is a valid, writable timespec and CLOCK_MONOTONIC is a
    // clock id every supported Unix provides.
    unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    (ts.tv_sec as u64)
        .saturating_mul(1_000_000_000)
        .saturating_add(ts.tv_nsec as u64)
}

/// Non-Unix fallback: process-relative monotonic nanoseconds (not alignable
/// with another process; the experiments run on Linux only).
#[cfg(not(unix))]
pub fn monotonic_ns() -> u64 {
    static START: OnceLock<std::time::Instant> = OnceLock::new();
    START
        .get_or_init(std::time::Instant::now)
        .elapsed()
        .as_nanos() as u64
}

fn line(t_mono_ns: u64, wall_ns: u128, seq: u64, phase: &str, session: &str, detail: Value) -> Value {
    serde_json::json!({
        "t_mono_ns": t_mono_ns,
        "wall_ns": wall_ns,
        "seq": seq,
        "phase": phase,
        "session": session,
        "detail": detail,
    })
}

/// Record one phase boundary. No-op when the trace is disabled.
pub fn mark(phase: &str, session: &str) {
    mark_detail(phase, session, || Value::Null);
}

/// Record one phase boundary with a detail object built only when enabled.
pub fn mark_detail(phase: &str, session: &str, detail: impl FnOnce() -> Value) {
    let Some(sink) = sink() else {
        return;
    };
    let t_mono_ns = monotonic_ns();
    let wall_ns = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let value = line(t_mono_ns, wall_ns, seq, phase, session, detail());
    if let Ok(mut file) = sink.lock() {
        let _ = writeln!(file, "{value}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unset_or_empty_env_opens_no_sink() {
        assert!(open_sink(None).is_none());
        assert!(open_sink(Some(std::ffi::OsString::new())).is_none());
    }

    #[test]
    fn unwritable_path_opens_no_sink() {
        assert!(open_sink(Some("/nonexistent-dir-r2-04/phase.jsonl".into())).is_none());
    }

    #[test]
    fn default_process_has_trace_disabled() {
        // The test environment never sets the variable; the default Driver
        // behaviour must be "no trace".
        if std::env::var_os(PHASE_TRACE_ENV).is_none() {
            assert!(!enabled());
            // A disabled mark must not evaluate its detail closure.
            mark_detail("never", "s", || panic!("detail built while disabled"));
        }
    }

    #[test]
    fn named_file_receives_appended_lines() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("trace.jsonl");
        let sink = open_sink(Some(path.clone().into_os_string())).unwrap();
        writeln!(sink.lock().unwrap(), "{{}}").unwrap();
        assert_eq!(std::fs::read_to_string(path).unwrap(), "{}\n");
    }

    #[test]
    fn line_is_one_valid_json_object() {
        let text = line(34, 12, 7, "click", "reveal_done", Value::Null).to_string();
        assert!(!text.contains('\n'));
        let parsed: Value = serde_json::from_str(&text).unwrap();
        assert_eq!(parsed["phase"], "click");
        assert_eq!(parsed["session"], "reveal_done");
        assert_eq!(parsed["wall_ns"], 12);
        assert_eq!(parsed["t_mono_ns"], 34);
        assert_eq!(parsed["seq"], 7);
        let quoted = line(1, 2, 3, "a\"b", "c\\d", Value::Null).to_string();
        let parsed: Value = serde_json::from_str(&quoted).unwrap();
        assert_eq!(parsed["phase"], "a\"b");
        assert_eq!(parsed["session"], "c\\d");
    }

    #[test]
    fn monotonic_clock_does_not_go_backwards() {
        let a = monotonic_ns();
        let b = monotonic_ns();
        assert!(b >= a);
    }
}
