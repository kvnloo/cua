//! Measurement-only CDP session and frame counters (experiment BUG-01).
//!
//! Env-gated and default-off. With `CUA_DRIVER_EXP_CDP_COUNTER_FILE` unset
//! (or empty) every hook returns after one `OnceLock` read: no counter is
//! touched, no allocation is made and no file is created. When it is set,
//! the Driver appends one JSON line per completed tool call with cumulative
//! counters and per-call deltas:
//!
//! - `Target.attachToTarget` / `Target.detachFromTarget` commands sent and
//!   acknowledged;
//! - `Target.attachedToTarget` / `Target.detachedFromTarget` events received;
//! - the size of the live CDP session set (sessions acknowledged by an
//!   attach reply or an `attachedToTarget` event, minus those acknowledged
//!   by a detach reply or a `detachedFromTarget` event);
//! - frames received per session id since the previous line.
//!
//! Counters are process-wide (every pooled connection), which is one
//! connection in the BUG-01 design. Nothing here changes CDP traffic,
//! dispatch, authorization or tool results.

use std::collections::{HashMap, HashSet};
use std::ffi::OsString;
use std::io::Write;
use std::path::PathBuf;
use std::sync::{Mutex, OnceLock};

use serde_json::{json, Value};

/// Environment variable naming the JSONL output file.
pub const ENV: &str = "CUA_DRIVER_EXP_CDP_COUNTER_FILE";

const BROWSER_LEVEL: &str = "-";

#[derive(Default)]
struct Inner {
    seq: u64,
    attach_sent: u64,
    detach_sent: u64,
    attach_ok: u64,
    detach_ok: u64,
    attached_events: u64,
    detached_events: u64,
    replies_total: u64,
    events_total: u64,
    live: HashSet<String>,
    sessions_seen: HashSet<String>,
    // Per-line deltas, reset by `line`.
    replies_delta: u64,
    events_delta: u64,
    frames_by_session: HashMap<String, u64>,
    events_by_session: HashMap<String, u64>,
}

pub(crate) struct CdpCounters {
    path: PathBuf,
    inner: Mutex<Inner>,
}

impl CdpCounters {
    pub(crate) fn from_env_value(value: Option<OsString>) -> Option<Self> {
        value
            .filter(|value| !value.is_empty())
            .map(|path| Self::new(PathBuf::from(path)))
    }

    pub(crate) fn new(path: PathBuf) -> Self {
        Self {
            path,
            inner: Mutex::new(Inner::default()),
        }
    }

    pub(crate) fn command_sent(&self, method: &str) {
        let mut inner = self.inner.lock().unwrap();
        match method {
            "Target.attachToTarget" => inner.attach_sent += 1,
            "Target.detachFromTarget" => inner.detach_sent += 1,
            _ => {}
        }
    }

    pub(crate) fn command_ok(&self, method: &str, detach_session: Option<&str>, result: &Value) {
        let mut inner = self.inner.lock().unwrap();
        match method {
            "Target.attachToTarget" => {
                inner.attach_ok += 1;
                if let Some(session) = result.get("sessionId").and_then(Value::as_str) {
                    inner.live.insert(session.to_owned());
                    inner.sessions_seen.insert(session.to_owned());
                }
            }
            "Target.detachFromTarget" => {
                inner.detach_ok += 1;
                if let Some(session) = detach_session {
                    inner.live.remove(session);
                }
            }
            _ => {}
        }
    }

    /// One parsed frame from the browser endpoint (reply or event).
    pub(crate) fn frame(&self, frame: &Value) {
        let session = frame
            .get("sessionId")
            .and_then(Value::as_str)
            .unwrap_or(BROWSER_LEVEL)
            .to_owned();
        let method = frame.get("method").and_then(Value::as_str);
        let mut inner = self.inner.lock().unwrap();
        *inner.frames_by_session.entry(session.clone()).or_default() += 1;
        let Some(method) = method else {
            inner.replies_total += 1;
            inner.replies_delta += 1;
            return;
        };
        inner.events_total += 1;
        inner.events_delta += 1;
        *inner.events_by_session.entry(session).or_default() += 1;
        let child = frame
            .pointer("/params/sessionId")
            .and_then(Value::as_str)
            .map(str::to_owned);
        match (method, child) {
            ("Target.attachedToTarget", Some(child)) => {
                inner.attached_events += 1;
                inner.live.insert(child.clone());
                inner.sessions_seen.insert(child);
            }
            ("Target.detachedFromTarget", Some(child)) => {
                inner.detached_events += 1;
                inner.live.remove(&child);
            }
            _ => {}
        }
    }

    /// Build the line for one completed tool call and reset the deltas.
    pub(crate) fn line(&self, tool: &str, t_unix_ms: f64) -> Value {
        let mut inner = self.inner.lock().unwrap();
        inner.seq += 1;
        let short = |map: &HashMap<String, u64>| -> serde_json::Map<String, Value> {
            map.iter()
                .map(|(session, count)| (short_session(session), json!(count)))
                .collect()
        };
        let line = json!({
            "schema": "cua.bug01.cdp_counters.v1",
            "seq": inner.seq,
            "tool": tool,
            "t_unix_ms": t_unix_ms,
            "attach_sent": inner.attach_sent,
            "detach_sent": inner.detach_sent,
            "attach_ok": inner.attach_ok,
            "detach_ok": inner.detach_ok,
            "attached_events": inner.attached_events,
            "detached_events": inner.detached_events,
            "live_sessions": inner.live.len(),
            "sessions_seen": inner.sessions_seen.len(),
            "replies_total": inner.replies_total,
            "events_total": inner.events_total,
            "replies_delta": inner.replies_delta,
            "events_delta": inner.events_delta,
            "frames_by_session_delta": short(&inner.frames_by_session),
            "events_by_session_delta": short(&inner.events_by_session),
        });
        inner.replies_delta = 0;
        inner.events_delta = 0;
        inner.frames_by_session.clear();
        inner.events_by_session.clear();
        line
    }

    fn append(&self, line: &Value) {
        if let Ok(mut file) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
        {
            let _ = writeln!(file, "{line}");
        }
    }
}

/// Session ids are opaque browser tokens; 12 hex chars keep lines small and
/// remain unique within one browser instance.
fn short_session(session: &str) -> String {
    session.chars().take(12).collect()
}

fn global() -> Option<&'static CdpCounters> {
    static GLOBAL: OnceLock<Option<CdpCounters>> = OnceLock::new();
    GLOBAL
        .get_or_init(|| CdpCounters::from_env_value(std::env::var_os(ENV)))
        .as_ref()
}

pub(crate) fn enabled() -> bool {
    global().is_some()
}

pub(crate) fn on_command_sent(method: &str) {
    if let Some(counters) = global() {
        counters.command_sent(method);
    }
}

pub(crate) fn on_command_ok(method: &str, detach_session: Option<&str>, result: &Value) {
    if let Some(counters) = global() {
        counters.command_ok(method, detach_session, result);
    }
}

pub(crate) fn on_frame(frame: &Value) {
    if let Some(counters) = global() {
        counters.frame(frame);
    }
}

/// Called once per completed tool call at the dispatch seam.
pub fn on_tool_call(tool: &str) {
    if let Some(counters) = global() {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|elapsed| elapsed.as_secs_f64() * 1000.0)
            .unwrap_or_default();
        let line = counters.line(tool, now);
        counters.append(&line);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_path(name: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "cua-bug01-{name}-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    #[test]
    fn unset_or_empty_env_value_disables_the_counters() {
        assert!(CdpCounters::from_env_value(None).is_none());
        assert!(CdpCounters::from_env_value(Some(OsString::new())).is_none());
        assert!(CdpCounters::from_env_value(Some(OsString::from("x.jsonl"))).is_some());
    }

    #[test]
    fn default_process_has_no_counter_file_and_hooks_are_inert() {
        // The test runner does not set the variable, so the global stays off
        // and the hooks neither count nor write.
        if std::env::var_os(ENV).is_some() {
            return;
        }
        assert!(!enabled());
        on_command_sent("Target.attachToTarget");
        on_frame(&json!({"id": 1, "result": {}}));
        on_tool_call("browser_click");
        assert!(global().is_none());
    }

    #[test]
    fn attach_without_detach_grows_the_live_session_set() {
        let counters = CdpCounters::new(temp_path("grow"));
        for index in 0..3 {
            counters.command_sent("Target.attachToTarget");
            counters.command_ok(
                "Target.attachToTarget",
                None,
                &json!({"sessionId": format!("SESSION{index:028}")}),
            );
            counters.frame(&json!({"id": index, "result": {"sessionId": "x"}}));
            let line = counters.line("get_browser_state", 1.0);
            assert_eq!(line["attach_sent"], index + 1);
            assert_eq!(line["live_sessions"], index + 1);
            assert_eq!(line["detach_sent"], 0);
            assert_eq!(line["replies_delta"], 1);
        }
    }

    #[test]
    fn detach_reply_and_detached_event_shrink_the_live_set() {
        let counters = CdpCounters::new(temp_path("shrink"));
        counters.command_ok("Target.attachToTarget", None, &json!({"sessionId": "AAA"}));
        counters.frame(&json!({
            "method": "Target.attachedToTarget",
            "sessionId": "AAA",
            "params": {"sessionId": "CHILD"}
        }));
        assert_eq!(counters.line("t", 1.0)["live_sessions"], 2);
        counters.command_sent("Target.detachFromTarget");
        counters.command_ok("Target.detachFromTarget", Some("CHILD"), &json!({}));
        counters.frame(&json!({
            "method": "Target.detachedFromTarget",
            "params": {"sessionId": "AAA"}
        }));
        let line = counters.line("t", 2.0);
        assert_eq!(line["live_sessions"], 0);
        assert_eq!(line["sessions_seen"], 2);
        assert_eq!(line["detach_sent"], 1);
        assert_eq!(line["detach_ok"], 1);
        assert_eq!(line["attached_events"], 1);
        assert_eq!(line["detached_events"], 1);
    }

    #[test]
    fn per_session_frame_deltas_reset_after_each_line() {
        let counters = CdpCounters::new(temp_path("delta"));
        counters.frame(&json!({"method": "DOM.documentUpdated", "sessionId": "S1", "params": {}}));
        counters.frame(&json!({"method": "DOM.documentUpdated", "sessionId": "S2", "params": {}}));
        counters.frame(&json!({"id": 3, "result": {}}));
        let first = counters.line("browser_navigate", 1.0);
        assert_eq!(first["events_delta"], 2);
        assert_eq!(first["events_by_session_delta"]["S1"], 1);
        assert_eq!(first["events_by_session_delta"]["S2"], 1);
        assert_eq!(first["frames_by_session_delta"]["-"], 1);
        let second = counters.line("browser_click", 2.0);
        assert_eq!(second["events_delta"], 0);
        assert_eq!(second["events_total"], 2);
        assert!(second["frames_by_session_delta"].as_object().unwrap().is_empty());
    }

    #[test]
    fn enabled_counters_append_one_line_per_tool_call() {
        let path = temp_path("append");
        let counters = CdpCounters::new(path.clone());
        let line = counters.line("browser_click", 1.0);
        counters.append(&line);
        let line = counters.line("get_browser_state", 2.0);
        counters.append(&line);
        let text = std::fs::read_to_string(&path).unwrap();
        let _ = std::fs::remove_file(&path);
        let lines: Vec<Value> = text
            .lines()
            .map(|line| serde_json::from_str(line).unwrap())
            .collect();
        assert_eq!(lines.len(), 2);
        assert_eq!(lines[0]["seq"], 1);
        assert_eq!(lines[1]["tool"], "get_browser_state");
    }
}
