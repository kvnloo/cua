//! Measurement-only phase marks (research experiment R2-04, AT-SPI phase profile;
//! OWN-16 producer invocation counts).
//!
//! Off unless `CUA_DRIVER_PHASE_TRACE_FILE` names a writable file when the
//! first mark is taken. When off, [`mark`] is one `OnceLock` read and returns;
//! no file is opened and no behaviour changes. When on, each mark appends one
//! JSON line `{"scope","mark","wall_ns","mono_ns"}` so a profiler can align
//! Driver-internal phases with D-Bus monitor and caller timestamps
//! (`wall_ns` = CLOCK_REALTIME, `mono_ns` = monotonic offset from the first
//! mark in this process). Marks are hints for a timing profile only: nothing
//! reads them back, and they never gate, verify, or authorize anything.
//!
//! [`enter`] / [`exit`] bracket a producer boundary (the window capture, the
//! AT-SPI walk) and add `"n"`: that producer's 1-based invocation ordinal in
//! this process. Calls between two marks of one tool dispatch are that call's
//! invocation count, and a gap-free `n` shows no invocation went unmarked.
//! When off, nothing is counted.

use std::io::Write;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Mutex, OnceLock};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

/// Environment variable naming the JSONL sink. Unset (the default) = off.
pub const ENV: &str = "CUA_DRIVER_PHASE_TRACE_FILE";

struct Sink {
    file: Mutex<std::fs::File>,
    base: Instant,
}

fn sink() -> Option<&'static Sink> {
    static SINK: OnceLock<Option<Sink>> = OnceLock::new();
    SINK.get_or_init(|| open_sink(std::env::var_os(ENV)))
        .as_ref()
}

fn open_sink(path: Option<std::ffi::OsString>) -> Option<Sink> {
    let path = path.filter(|p| !p.is_empty())?;
    let file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .ok()?;
    Some(Sink {
        file: Mutex::new(file),
        base: Instant::now(),
    })
}

/// Whether phase marks are being recorded in this process.
pub fn enabled() -> bool {
    sink().is_some()
}

fn line(scope: &str, mark: &str, wall_ns: u128, mono_ns: u128, n: Option<u64>) -> String {
    // scope/mark are static identifiers chosen in source (no quoting needed),
    // but escape defensively so a line is always valid JSON.
    let esc = |s: &str| s.replace('\\', "\\\\").replace('"', "\\\"");
    let count = n.map(|n| format!(",\"n\":{n}")).unwrap_or_default();
    format!(
        "{{\"scope\":\"{}\",\"mark\":\"{}\",\"wall_ns\":{wall_ns},\"mono_ns\":{mono_ns}{count}}}\n",
        esc(scope),
        esc(mark)
    )
}

fn write(sink: &Sink, scope: &str, mark: &str, n: Option<u64>) {
    let wall_ns = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let mono_ns = sink.base.elapsed().as_nanos();
    if let Ok(mut file) = sink.file.lock() {
        let _ = file.write_all(line(scope, mark, wall_ns, mono_ns, n).as_bytes());
    }
}

/// Record one phase mark. No-op unless [`ENV`] is set.
pub fn mark(scope: &str, mark: &str) {
    if let Some(sink) = sink() {
        write(sink, scope, mark, None);
    }
}

/// Count and mark entry into a producer. Returns the invocation ordinal
/// (`0` when off: nothing is counted or written).
pub fn enter(scope: &str, calls: &AtomicU64) -> u64 {
    enter_into(sink(), scope, calls)
}

/// Mark the exit of the producer invocation `n` returned by [`enter`].
pub fn exit(scope: &str, mark: &str, n: u64) {
    exit_into(sink(), scope, mark, n);
}

fn enter_into(sink: Option<&Sink>, scope: &str, calls: &AtomicU64) -> u64 {
    let Some(sink) = sink else {
        return 0;
    };
    let n = calls.fetch_add(1, Ordering::Relaxed) + 1;
    write(sink, scope, "enter", Some(n));
    n
}

fn exit_into(sink: Option<&Sink>, scope: &str, mark: &str, n: u64) {
    match sink {
        Some(sink) if n > 0 => write(sink, scope, mark, Some(n)),
        _ => {}
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
    fn line_is_one_valid_json_object() {
        let text = line("click", "reveal_done", 12, 34, None);
        assert!(text.ends_with('\n'));
        let value: serde_json::Value = serde_json::from_str(text.trim_end()).unwrap();
        assert_eq!(value["scope"], "click");
        assert_eq!(value["mark"], "reveal_done");
        assert_eq!(value["wall_ns"], 12);
        assert_eq!(value["mono_ns"], 34);
        let quoted = line("a\"b", "c\\d", 1, 2, None);
        let value: serde_json::Value = serde_json::from_str(quoted.trim_end()).unwrap();
        assert_eq!(value["scope"], "a\"b");
        assert_eq!(value["mark"], "c\\d");
    }

    #[test]
    fn counted_line_carries_the_ordinal() {
        let value: serde_json::Value =
            serde_json::from_str(line("atspi_walk", "enter", 1, 2, Some(7)).trim_end()).unwrap();
        assert_eq!(value["n"], 7);
        let plain: serde_json::Value =
            serde_json::from_str(line("atspi_walk", "enter", 1, 2, None).trim_end()).unwrap();
        assert!(plain.get("n").is_none());
    }

    #[test]
    fn off_counts_nothing_and_writes_nothing() {
        let calls = AtomicU64::new(0);
        assert_eq!(enter_into(None, "capture_window", &calls), 0);
        exit_into(None, "capture_window", "exit_ok", 0);
        assert_eq!(calls.load(Ordering::Relaxed), 0);
    }

    #[test]
    fn on_counts_each_invocation_and_pairs_exit_with_enter() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("phase.jsonl");
        let sink = open_sink(Some(path.clone().into_os_string())).unwrap();
        let calls = AtomicU64::new(0);
        let first = enter_into(Some(&sink), "capture_window", &calls);
        exit_into(Some(&sink), "capture_window", "exit_ok", first);
        let second = enter_into(Some(&sink), "capture_window", &calls);
        exit_into(Some(&sink), "capture_window", "exit_err", second);
        // An `n` of 0 (taken while off) never writes an orphan exit.
        exit_into(Some(&sink), "capture_window", "exit_ok", 0);
        assert_eq!((first, second), (1, 2));
        let marks: Vec<serde_json::Value> = std::fs::read_to_string(&path)
            .unwrap()
            .lines()
            .map(|l| serde_json::from_str(l).unwrap())
            .collect();
        let got: Vec<(String, u64)> = marks
            .iter()
            .map(|m| {
                (
                    m["mark"].as_str().unwrap().to_owned(),
                    m["n"].as_u64().unwrap(),
                )
            })
            .collect();
        assert_eq!(
            got,
            [
                ("enter".to_owned(), 1),
                ("exit_ok".to_owned(), 1),
                ("enter".to_owned(), 2),
                ("exit_err".to_owned(), 2)
            ]
        );
    }
}
