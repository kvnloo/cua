//! Native element tokens are owned by the session that published their
//! snapshot (kvnloo/cua#36 native token ownership rows I2 and I2d).

use cua_driver_core::element_token::{format_snapshot_id, token_for, ResolvedElement};
use cua_driver_core::snapshot_store::{SnapshotPayload, SnapshotStore};
use serde_json::{json, Value};

struct Payload(Vec<u32>);

impl SnapshotPayload for Payload {
    type Element = u32;
    fn len(&self) -> usize {
        self.0.len()
    }
    fn retain(&self, index: usize) -> Option<u32> {
        self.0.get(index).copied()
    }
}

const PID: i32 = 42;

fn publish(cache: &SnapshotStore<Payload>, window: u64, session: Option<&str>) -> u32 {
    cache
        .publish_for_session(PID, window, Payload(vec![10, 20, 30]), session, None)
        .expect("live session publishes")
        .0
}

fn args(token: &str, session: Option<&str>) -> Value {
    let mut args = json!({ "element_token": token });
    if let Some(session) = session {
        args["_session_id"] = json!(session);
    }
    args
}

fn refusal(cache: &SnapshotStore<Payload>, token: &str, session: Option<&str>) -> Value {
    cache
        .resolve(PID, &args(token, session))
        .expect_err("token must be refused")
        .structured_content
        .unwrap()
}

#[test]
fn another_sessions_token_is_refused_and_stays_live_for_its_owner() {
    let cache = SnapshotStore::new();
    let token = token_for(publish(&cache, 7, Some("session-a")), 2);

    let refused = refusal(&cache, &token, Some("session-b"));
    assert_eq!(refused["refusal"]["code"], "stale_element_token");

    assert!(matches!(
        cache.resolve(PID, &args(&token, Some("session-a"))).unwrap(),
        ResolvedElement::Element {
            window_id: 7,
            element: 30,
            ..
        }
    ));
}

#[test]
fn a_token_minted_from_another_sessions_handle_is_refused() {
    let cache = SnapshotStore::new();
    let handle = format_snapshot_id(publish(&cache, 7, Some("session-a")));
    publish(&cache, 8, Some("session-b"));
    // B builds `<A's handle>:<index>` itself without ever receiving A's token.
    let minted = format!("{handle}:1");
    assert_eq!(
        refusal(&cache, &minted, Some("session-b"))["refusal"]["code"],
        "stale_element_token"
    );
}

#[test]
fn stale_refusal_names_only_the_callers_own_snapshots() {
    let cache = SnapshotStore::new();
    let theirs = format_snapshot_id(publish(&cache, 7, Some("session-a")));
    let mine = format_snapshot_id(publish(&cache, 8, Some("session-b")));

    let refused = refusal(&cache, "sffffffff:0", Some("session-b"));
    assert_eq!(refused["refusal"]["code"], "stale_element_token");
    assert_eq!(
        refused["current_snapshots"],
        json!([{ "snapshot_id": mine, "window_id": 8 }])
    );
    assert!(!refused.to_string().contains(&theirs));

    let outsider = refusal(&cache, "sffffffff:0", Some("session-c"));
    assert_eq!(outsider["current_snapshots"], json!([]));
    assert!(!outsider.to_string().contains(&theirs));
    assert!(!outsider.to_string().contains(&mine));
}

#[test]
fn anonymous_and_named_snapshots_do_not_resolve_for_each_other() {
    let cache = SnapshotStore::new();
    let anonymous = token_for(publish(&cache, 7, None), 0);
    let named = token_for(publish(&cache, 8, Some("session-a")), 0);

    assert_eq!(
        refusal(&cache, &anonymous, Some("session-a"))["refusal"]["code"],
        "stale_element_token"
    );
    assert_eq!(
        refusal(&cache, &named, None)["refusal"]["code"],
        "stale_element_token"
    );
    assert!(cache.resolve(PID, &args(&anonymous, None)).is_ok());
    assert!(cache.resolve(PID, &args(&named, Some("session-a"))).is_ok());
}

// trycua/cua PR 4375 added a capture-only publication path
// (`publish_capture_for_session`, used by screenshot-only observations). Its
// snapshots carry a token-bearing id like any other, so F1 must bind them to
// their session too.
#[test]
fn a_capture_only_publication_resolves_only_for_its_session() {
    let cache = SnapshotStore::new();
    let id = cache
        .publish_capture_for_session(PID, 7, Payload(vec![10, 20]), Some("session-a"), Some(1.0))
        .expect("live session publishes")
        .0;
    let token = token_for(id, 1);

    let refused = refusal(&cache, &token, Some("session-b"));
    assert_eq!(refused["refusal"]["code"], "stale_element_token");
    assert_eq!(refused["current_snapshots"], json!([]));
    assert!(matches!(
        cache.resolve(PID, &args(&token, Some("session-a"))).unwrap(),
        ResolvedElement::Element {
            window_id: 7,
            element: 20,
            ..
        }
    ));
    // The capture-only flag still does not claim a semantic walk.
    assert!(!cache.contains_semantic_window(PID, 7));
}

// Two windows of one process (kvnloo/cua#36 same-process two-window row):
// tokens are per session and retirement is per window.
#[test]
fn two_windows_of_one_process_keep_tokens_per_window_and_per_session() {
    let cache = SnapshotStore::new();
    let a_window1 = token_for(publish(&cache, 7, Some("session-a")), 0);
    publish(&cache, 8, Some("session-b"));

    // B cannot act through A's window-1 token on the same pid.
    assert_eq!(
        refusal(&cache, &a_window1, Some("session-b"))["refusal"]["code"],
        "stale_element_token"
    );
    // One session observing window 1 then window 2 keeps its window-1 token.
    let own_window2 = token_for(publish(&cache, 8, Some("session-a")), 0);
    assert!(cache.resolve(PID, &args(&a_window1, Some("session-a"))).is_ok());
    assert!(cache.resolve(PID, &args(&own_window2, Some("session-a"))).is_ok());
    // Removing window 1's snapshot retires only window 1.
    cache.remove(PID, 7);
    assert_eq!(
        refusal(&cache, &a_window1, Some("session-a"))["refusal"]["code"],
        "stale_element_token"
    );
    assert!(cache.resolve(PID, &args(&own_window2, Some("session-a"))).is_ok());
    // A window-1 token presented with window 2's id conflicts instead of
    // resolving inside window 2.
    let again = token_for(publish(&cache, 7, Some("session-a")), 0);
    let mut cross = args(&again, Some("session-a"));
    cross["window_id"] = json!(8);
    let conflict = cache
        .resolve(PID, &cross)
        .expect_err("window mismatch must be refused")
        .structured_content
        .unwrap();
    assert_eq!(conflict["refusal"]["code"], "conflicting_element_target");
}
