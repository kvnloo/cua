//! Measurement-only phase trace for the R2-01 browser feedback A/B.
//!
//! EXPERIMENT ONLY, not for promotion and not a public contract.
//!
//! Default off. It is enabled only when `CUA_DRIVER_PHASE_TRACE_FILE` names a
//! file when the first mark is attempted. Each [`mark`] then appends one JSON
//! line carrying the host `CLOCK_MONOTONIC` time in nanoseconds, so a caller
//! and a fixture on the same host can align these marks with their own
//! `time.monotonic_ns()` readings. A mark never changes control flow, a tool
//! result or an authorization decision; when disabled it costs one
//! initialized-`OnceLock` read.

use std::io::Write;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};

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

/// Host monotonic time in nanoseconds (`CLOCK_MONOTONIC` on Unix, which is
/// the clock behind Python's `time.monotonic_ns()` on Linux).
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
/// with another process; the R2-01 experiment runs on Linux only).
#[cfg(not(unix))]
pub fn monotonic_ns() -> u64 {
    static START: OnceLock<std::time::Instant> = OnceLock::new();
    START
        .get_or_init(std::time::Instant::now)
        .elapsed()
        .as_nanos() as u64
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
    let seq = SEQ.fetch_add(1, Ordering::Relaxed);
    let line = serde_json::json!({
        "t_mono_ns": t_mono_ns,
        "seq": seq,
        "phase": phase,
        "session": session,
        "detail": detail(),
    });
    if let Ok(mut file) = sink.lock() {
        let _ = writeln!(file, "{line}");
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
    fn monotonic_clock_does_not_go_backwards() {
        let a = monotonic_ns();
        let b = monotonic_ns();
        assert!(b >= a);
    }
}
