//! Optional Omarchy semantic desktop revision.
//!
//! CUA keeps direct Hyprland IPC/capture as the authority for targeting and
//! dispatch. This adapter consumes Omarchy's read-only desktop-state contract
//! only as an observation freshness receipt. It never grants action authority,
//! changes routing, or replaces compositor attestation.

use anyhow::{ensure, Context, Result};
use serde::Deserialize;
use serde_json::{json, Value};
use std::path::Path;
use std::process::Command;

const OMARCHY_STATE: &str = "/usr/bin/omarchy-desktop-state";
const TIMEOUT: &str = "/usr/bin/timeout";
const MAX_SNAPSHOT_BYTES: usize = 1024 * 1024;

#[derive(Debug, Deserialize)]
struct Snapshot {
    schema: String,
    compositor: Compositor,
    revision: String,
}

#[derive(Debug, Deserialize)]
struct Compositor {
    kind: String,
    instance: Option<String>,
}

fn valid_revision(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn parse_snapshot(bytes: &[u8], expected_instance: &str) -> Result<Snapshot> {
    ensure!(
        !bytes.is_empty() && bytes.len() <= MAX_SNAPSHOT_BYTES,
        "Omarchy desktop snapshot has invalid size"
    );
    let snapshot: Snapshot =
        serde_json::from_slice(bytes).context("invalid Omarchy desktop snapshot JSON")?;
    ensure!(
        snapshot.schema == "omarchy.desktop-state.v1",
        "unsupported Omarchy desktop snapshot schema"
    );
    ensure!(
        snapshot.compositor.kind == "hyprland",
        "Omarchy desktop snapshot is not Hyprland"
    );
    ensure!(
        snapshot.compositor.instance.as_deref() == Some(expected_instance),
        "Omarchy desktop snapshot belongs to a different Hyprland instance"
    );
    ensure!(
        valid_revision(&snapshot.revision),
        "invalid Omarchy desktop revision"
    );
    Ok(snapshot)
}

fn read_snapshot(expected_instance: &str) -> Result<Snapshot> {
    ensure!(
        Path::new(OMARCHY_STATE).is_file() && Path::new(TIMEOUT).is_file(),
        "Omarchy desktop-state provider is unavailable"
    );
    // The provider is optional and must not be able to strand get_desktop_state.
    // Coreutils timeout is package-owned on Omarchy and kills the read after a
    // short bound. No shell is involved.
    let output = Command::new(TIMEOUT)
        .args(["--signal=KILL", "0.25s", OMARCHY_STATE])
        .output()
        .context("failed to start Omarchy desktop-state provider")?;
    ensure!(
        output.status.success(),
        "Omarchy desktop-state provider failed or timed out"
    );
    parse_snapshot(&output.stdout, expected_instance)
}

/// Best-effort provider receipt for one desktop observation.
///
/// Failure means "no Omarchy receipt", never "desktop unavailable": CUA's
/// direct native observation remains authoritative and unchanged.
pub(crate) fn desktop_revision_receipt() -> Option<Value> {
    if !crate::wayland::hyprland::is_session() {
        return None;
    }
    let instance = std::env::var("HYPRLAND_INSTANCE_SIGNATURE").ok()?;
    match read_snapshot(&instance) {
        Ok(snapshot) => Some(json!({
            "provider": "omarchy",
            "schema": snapshot.schema,
            "revision": snapshot.revision,
            "compositor": {
                "kind": snapshot.compositor.kind,
                "instance": snapshot.compositor.instance,
            },
            "authority": "observation_freshness_only",
        })),
        Err(error) => {
            tracing::debug!("Omarchy desktop revision unavailable: {error:#}");
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn snapshot(instance: Option<&str>, revision: &str) -> Vec<u8> {
        serde_json::to_vec(&json!({
            "schema": "omarchy.desktop-state.v1",
            "compositor": {"kind": "hyprland", "instance": instance},
            "monitors": [],
            "workspaces": [],
            "windows": [],
            "active": {"workspace": null, "window": null, "pid": null},
            "revision": revision,
        }))
        .unwrap()
    }

    #[test]
    fn snapshot_is_bound_to_exact_hyprland_instance() {
        let revision = "a".repeat(64);
        let parsed = parse_snapshot(&snapshot(Some("instance-a"), &revision), "instance-a").unwrap();
        assert_eq!(parsed.schema, "omarchy.desktop-state.v1");
        assert_eq!(parsed.revision, revision);

        for instance in [None, Some("instance-b")] {
            assert!(parse_snapshot(&snapshot(instance, &"b".repeat(64)), "instance-a").is_err());
        }
    }

    #[test]
    fn snapshot_rejects_noncanonical_revision_and_provider_identity() {
        let invalid = [
            String::new(),
            "ABCDEF".to_owned(),
            "g".repeat(64),
            "a".repeat(63),
        ];
        for revision in invalid {
            assert!(
                parse_snapshot(&snapshot(Some("instance-a"), &revision), "instance-a").is_err()
            );
        }

        let mut value: Value =
            serde_json::from_slice(&snapshot(Some("instance-a"), &"c".repeat(64))).unwrap();
        value["schema"] = json!("omarchy.desktop-state.v2");
        assert!(parse_snapshot(&serde_json::to_vec(&value).unwrap(), "instance-a").is_err());

        value["schema"] = json!("omarchy.desktop-state.v1");
        value["compositor"]["kind"] = json!("other");
        assert!(parse_snapshot(&serde_json::to_vec(&value).unwrap(), "instance-a").is_err());
    }

    #[test]
    fn snapshot_size_is_bounded_before_parse() {
        assert!(parse_snapshot(&[], "instance-a").is_err());
        assert!(
            parse_snapshot(&vec![b' '; MAX_SNAPSHOT_BYTES + 1], "instance-a").is_err()
        );
    }
}
