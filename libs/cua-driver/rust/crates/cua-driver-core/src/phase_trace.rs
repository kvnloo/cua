//! Measurement-only phase marks (research experiment R2-04, AT-SPI phase profile).
//!
//! Off unless `CUA_DRIVER_PHASE_TRACE_FILE` names a writable file when the
//! first mark is taken. When off, [`mark`] is one `OnceLock` read and returns;
//! no file is opened and no behaviour changes. When on, each mark appends one
//! JSON line `{"scope","mark","wall_ns","mono_ns"}` so a profiler can align
//! Driver-internal phases with D-Bus monitor and caller timestamps
//! (`wall_ns` = CLOCK_REALTIME, `mono_ns` = monotonic offset from the first
//! mark in this process). Marks are hints for a timing profile only: nothing
//! reads them back, and they never gate, verify, or authorize anything.

use std::io::Write;
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

fn line(scope: &str, mark: &str, wall_ns: u128, mono_ns: u128) -> String {
    // scope/mark are static identifiers chosen in source (no quoting needed),
    // but escape defensively so a line is always valid JSON.
    let esc = |s: &str| s.replace('\\', "\\\\").replace('"', "\\\"");
    format!(
        "{{\"scope\":\"{}\",\"mark\":\"{}\",\"wall_ns\":{wall_ns},\"mono_ns\":{mono_ns}}}\n",
        esc(scope),
        esc(mark)
    )
}

/// Record one phase mark. No-op unless [`ENV`] is set.
pub fn mark(scope: &str, mark: &str) {
    let Some(sink) = sink() else {
        return;
    };
    let wall_ns = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_nanos())
        .unwrap_or(0);
    let mono_ns = sink.base.elapsed().as_nanos();
    if let Ok(mut file) = sink.file.lock() {
        let _ = file.write_all(line(scope, mark, wall_ns, mono_ns).as_bytes());
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
        let text = line("click", "reveal_done", 12, 34);
        assert!(text.ends_with('\n'));
        let value: serde_json::Value = serde_json::from_str(text.trim_end()).unwrap();
        assert_eq!(value["scope"], "click");
        assert_eq!(value["mark"], "reveal_done");
        assert_eq!(value["wall_ns"], 12);
        assert_eq!(value["mono_ns"], 34);
        let quoted = line("a\"b", "c\\d", 1, 2);
        let value: serde_json::Value = serde_json::from_str(quoted.trim_end()).unwrap();
        assert_eq!(value["scope"], "a\"b");
        assert_eq!(value["mark"], "c\\d");
    }
}
