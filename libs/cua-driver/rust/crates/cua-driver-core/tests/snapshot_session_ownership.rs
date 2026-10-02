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
