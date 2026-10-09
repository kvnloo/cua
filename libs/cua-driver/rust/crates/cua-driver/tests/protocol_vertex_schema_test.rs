//! Check the actual platform tool inventory, including runtime-only tools.
//! RitikaxG's #4871 review demonstrated why manifest-only coverage is not enough.
//! This test only initializes MCP and lists schemas; it never invokes a tool.

#![cfg(any(target_os = "linux", target_os = "macos", target_os = "windows"))]

use cua_driver_contract::{manifest, Platform};
use cua_driver_testkit::{vertex::input_schema_violations, RawDriver};
use serde_json::json;
use std::collections::BTreeSet;

#[test]
fn live_tools_list_input_schemas_are_vertex_compatible() {
    // Missing binaries must fail, not silently turn this gate into a skip.
    let mut driver = RawDriver::spawn().expect("spawn source-built driver for live Vertex lint");
    driver.send(&json!({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}));
    let initialized = driver.recv();
    assert!(initialized["result"].is_object(), "{initialized}");

    driver.send(&json!({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}));
    let response = driver.recv();
    let tools = response["result"]["tools"]
        .as_array()
        .unwrap_or_else(|| panic!("tools/list has no tools array: {response}"));
    assert!(!tools.is_empty(), "tools/list must not be empty");
    assert!(
        response["result"]["nextCursor"].is_null(),
        "consume all tools/list pages before claiming full inventory coverage"
    );
    let names: BTreeSet<&str> = tools
        .iter()
        .map(|tool| tool["name"].as_str().expect("tool name"))
        .collect();
    assert_eq!(names.len(), tools.len(), "tools/list has duplicate tool names");
    assert!(
        names.contains("run_actions"),
        "the runtime-only run_actions tool must be covered"
    );

    // Do not certify a partial roster as Vertex-compatible. The contract
    // enumerates the cross-platform tools; the live check also covers every
    // runtime-only tool, which is how RitikaxG found the run_actions gap.
    let active_platform = if cfg!(target_os = "macos") {
        Platform::Macos
    } else if cfg!(target_os = "windows") {
        Platform::Windows
    } else {
        Platform::Linux
    };
    let missing: Vec<String> = manifest()
        .tools
        .into_iter()
        .filter(|tool| tool.platforms.contains(&active_platform))
        .map(|tool| tool.name)
        .filter(|name| !names.contains(name.as_str()))
        .collect();
    assert!(
        missing.is_empty(),
        "tools/list is missing {} portable tool(s): {}",
        missing.len(),
        missing.join(", ")
    );

    let mut violations = Vec::new();
    for tool in tools {
        let name = tool["name"].as_str().expect("tool name");
        // Output schemas are not function-declaration inputs. Linting them
        // would incorrectly impose this provider policy on result envelopes.
        for violation in input_schema_violations(&tool["inputSchema"]) {
            violations.push(format!("{name}.inputSchema {violation}"));
        }
    }
    assert!(
        violations.is_empty(),
        "live input schema violations (#4798 / #4717):\n{}",
        violations.join("\n")
    );
}
