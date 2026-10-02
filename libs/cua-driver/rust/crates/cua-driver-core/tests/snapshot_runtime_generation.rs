//! A Driver process restart is a new runtime generation: element tokens from
//! the previous process must not resolve in the new one (kvnloo/cua#36 I5p).
//!
//! Each Driver generation is a separate process, so the test runs itself as
//! child processes and compares the first snapshot each one mints.

use cua_driver_core::element_token::{format_snapshot_id, parse_token, token_for};
use cua_driver_core::snapshot_store::{SnapshotPayload, SnapshotStore};

struct Payload;

impl SnapshotPayload for Payload {
    type Element = ();
    fn len(&self) -> usize {
        1
    }
    fn retain(&self, index: usize) -> Option<()> {
        (index == 0).then_some(())
    }
}

const CHILD: &str = "CUA_SNAPSHOT_GENERATION_CHILD";
const TEST: &str = "a_restarted_process_does_not_reissue_its_predecessors_tokens";

#[test]
fn a_restarted_process_does_not_reissue_its_predecessors_tokens() {
    if std::env::var_os(CHILD).is_some() {
        // One Driver generation: the same pid, window and observation order.
        let store = SnapshotStore::new();
        let id = store.publish(4242, 7, Payload);
        println!("FIRST_TOKEN={}", token_for(id, 0));
        return;
    }
    let generation = || {
        let output = std::process::Command::new(std::env::current_exe().unwrap())
            .args(["--exact", TEST, "--nocapture", "--test-threads=1"])
            .env(CHILD, "1")
            .output()
            .expect("child generation runs");
        assert!(output.status.success(), "{output:?}");
        let stdout = String::from_utf8(output.stdout).unwrap();
        // libtest prints the test's status prefix on the same line.
        let token = stdout
            .split("FIRST_TOKEN=")
            .nth(1)
            .and_then(|rest| rest.split_whitespace().next())
            .expect("child printed its first token")
            .to_owned();
        let (id, index) = parse_token(&token).expect("wire shape s<8 hex>:<index>");
        assert_eq!(token, token_for(id, index));
        assert_eq!(format_snapshot_id(id).len(), 9);
        token
    };
    let first = generation();
    let second = generation();
    assert_ne!(
        first, second,
        "two Driver generations minted the same first token for the same observation"
    );
}
