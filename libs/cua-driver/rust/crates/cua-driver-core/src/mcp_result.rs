// SPDX-License-Identifier: MIT
// Copyright (c) 2026 Cua AI, Inc.

//! The one place a `tools/call` result is held to the contract the driver
//! advertises.
//!
//! MCP validates every `structuredContent` a tool emits against that tool's
//! advertised `outputSchema` — payloads sent with `isError: true` included —
//! and rejects a response whose payload matches neither arm (`-32602`), or a
//! successful response that declares a schema and carries no structured
//! payload at all (`-32600`). Either way the client discards the whole
//! response, so the message the driver placed in `content` never reaches the
//! agent.
//!
//! Individual result constructors cannot enforce that: `ToolResult::error`
//! leaves `structuredContent` unset, the transport paths invent diagnostics
//! like `{"exit_code": 1}`, and the proxy synthesises an empty success when the
//! daemon answers `ok` with no result. So the rule lives here instead, on the
//! single path every direct and daemon-backed `tools/call` result passes
//! through.

use serde_json::{json, Value};
use std::{
    collections::HashMap,
    sync::{Arc, LazyLock, Mutex},
};
use tracing::warn;

use cua_driver_contract::{
    advertised_tool_output_schema, advertises_output_schema, conforming_error_envelope,
    is_refusal_envelope, validate_success_output,
};

/// Marker code for a result the driver replaced because the tool's own payload
/// could not be advertised under its `outputSchema`.
pub const TOOL_OUTPUT_INVALID_CODE: &str = "tool_output_invalid";

type CachedValidator = Result<Arc<jsonschema::Validator>, String>;
static OUTPUT_VALIDATORS: LazyLock<Mutex<HashMap<String, CachedValidator>>> =
    LazyLock::new(|| Mutex::new(HashMap::new()));

fn validate_wire_output(tool: &str, structured: &Value) -> Result<(), String> {
    // Only published tools reach this cache, so arbitrary client names cannot grow it.
    let validator = OUTPUT_VALIDATORS
        .lock()
        .map_err(|_| "output schema cache unavailable".to_owned())?
        .entry(tool.to_owned())
        .or_insert_with(|| {
            let schema = advertised_tool_output_schema(tool)
                .ok_or_else(|| "advertised output schema unavailable".to_owned())?;
            jsonschema::validator_for(&schema)
                .map(Arc::new)
                .map_err(|error| format!("invalid advertised output schema: {error}"))
        })
        .clone()?;
    if validator.is_valid(structured) {
        Ok(())
    } else {
        Err("structured content does not match the advertised output schema".to_owned())
    }
}

/// B-07 EXPERIMENT ONLY (measurement knob, default off, not for promotion).
/// `CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM=1` makes the direct stdio
/// transport call [`exp_prewarm_action_output_validators`] once, before it
/// reads the first request. Any other value, or unset, leaves the validator
/// cache to fill lazily on each tool's first call, as shipped.
pub const EXP_OUTPUT_VALIDATOR_PREWARM_ENV: &str = "CUA_DRIVER_EXP_OUTPUT_VALIDATOR_PREWARM";

pub fn exp_output_validator_prewarm_from(value: Option<&str>) -> bool {
    value == Some("1")
}

/// B-07 EXPERIMENT ONLY. Compile the action-result output validator once and
/// enter it in the validator cache under every action-result tool name whose
/// advertised schema is that same schema. Returns the number of names entered.
///
/// Verdicts are unchanged: each cached entry is the validator the lazy path
/// would compile from the identical advertised schema. Only the time it is
/// built moves (transport start instead of each tool's first call), and the
/// action-result tools share one compile instead of one per tool name.
pub fn exp_prewarm_action_output_validators() -> usize {
    let tools = cua_driver_contract::ACTION_RESULT_TOOLS;
    let Some(schema) = tools.first().and_then(|tool| advertised_tool_output_schema(tool)) else {
        return 0;
    };
    let Ok(validator) = jsonschema::validator_for(&schema) else {
        return 0;
    };
    let validator = Arc::new(validator);
    let Ok(mut cache) = OUTPUT_VALIDATORS.lock() else {
        return 0;
    };
    let mut entered = 0;
    for tool in tools {
        if advertised_tool_output_schema(tool).as_ref() == Some(&schema) {
            cache
                .entry((*tool).to_owned())
                .or_insert_with(|| Ok(validator.clone()));
            entered += 1;
        }
    }
    entered
}

/// Hold one `tools/call` result to the tool's advertised `outputSchema`.
///
/// - An error result keeps its diagnostic, normalized into the refusal arm so
///   a strict client accepts it and reads the `content` message.
/// - A successful result for a tool that advertises a schema must carry a
///   structured payload that the schema accepts. A missing or rejected payload
///   becomes a conforming internal-error result, because the alternative is a
///   response the client drops entirely.
/// - A successful result for a tool that advertises no schema is returned
///   unchanged: there is nothing for a client to validate it against.
pub fn conforming_tool_result(tool: &str, result: Value) -> Value {
    conforming_tool_result_inner(tool, result, advertises_output_schema(tool))
}

/// Reject contracts this proxy cannot safely normalize errors against. An older
/// daemon may omit its schema; that does not promise the local success contract.
pub fn validate_proxy_output_schema(tool: &str, schema: Option<&Value>) -> Result<(), String> {
    if let Some(schema) = schema {
        if advertised_tool_output_schema(tool).as_ref() != Some(schema) {
            return Err(format!(
                "incompatible daemon output schema for {tool}; use matching proxy and daemon versions"
            ));
        }
    }
    Ok(())
}

/// Apply the result boundary using the executing daemon's advertised contract.
/// Only matching canonical schemas enter the bounded validator cache.
pub fn conforming_proxy_tool_result(
    tool: &str,
    result: Value,
    schema: Option<&Value>,
) -> Result<Value, String> {
    validate_proxy_output_schema(tool, schema)?;
    Ok(conforming_tool_result_inner(tool, result, schema.is_some()))
}

fn conforming_tool_result_inner(tool: &str, result: Value, has_schema: bool) -> Value {
    let Value::Object(mut result) = result else {
        return internal_error_result(format!(
            "internal result mismatch for {tool}: tool result is not an object"
        ));
    };

    if result.get("isError").and_then(Value::as_bool) == Some(true) {
        let structured = result.remove("structuredContent").unwrap_or(Value::Null);
        result.insert(
            "structuredContent".to_owned(),
            conforming_error_envelope(structured),
        );
        return Value::Object(result);
    }

    if !has_schema {
        return Value::Object(result);
    }

    match result.get("structuredContent") {
        None | Some(Value::Null) => {
            warn!(
                tool,
                "successful tool result declared an output schema but carried no structured content"
            );
            invalid_output_result(result, format!(
                "internal output mismatch for {tool}: tool advertises an output schema but returned no structured content"
            ))
        }
        // A refusal payload satisfies the advertised schema's other arm. The
        // typed success validator would reject it, so ask the arm it belongs
        // to rather than replacing a payload a client accepts.
        Some(structured) if is_refusal_envelope(structured) => Value::Object(result),
        Some(structured) => match validate_wire_output(tool, structured)
            .and_then(|()| validate_success_output(tool, structured.clone()))
        {
            Ok(_) => Value::Object(result),
            Err(error) => {
                warn!(
                    tool,
                    "successful tool result carried structured content its output schema rejects"
                );
                invalid_output_result(
                    result,
                    format!("internal output mismatch for {tool}: {error}"),
                )
            }
        },
    }
}

fn invalid_output_result(original: serde_json::Map<String, Value>, message: String) -> Value {
    let mut result = internal_error_result(message);
    if let Some(Value::Array(content)) = original.get("content") {
        result["content"]
            .as_array_mut()
            .unwrap()
            .extend(content.clone());
    }
    if let Some(structured) = original.get("structuredContent") {
        // Preserve evidence as an explicitly invalid diagnostic, never as success.
        result["structuredContent"]["invalid_output"] = structured.clone();
    }
    result
}

/// Build the `isError: true` result for a call that produced no usable tool
/// payload, already normalized into the refusal arm.
pub fn internal_error_result(message: impl Into<String>) -> Value {
    let message = format!(
        "{}; the tool may have executed. Verify state before retrying.",
        message.into()
    );
    json!({
        "content": [{"type": "text", "text": message}],
        "isError": true,
        "structuredContent": {"code": TOOL_OUTPUT_INVALID_CODE, "execution_state": "unknown"},
    })
}

/// Build a tool-level error result carrying a caller-supplied diagnostic.
///
/// The diagnostic is passed through untouched here; [`conforming_tool_result`]
/// is what normalizes it, so every error path gets the same treatment whether
/// or not it went through this constructor.
pub fn tool_error_result(message: impl Into<String>, structured: Value) -> Value {
    let message = message.into();
    json!({
        "content": [{"type": "text", "text": message}],
        "isError": true,
        "structuredContent": structured,
    })
}

#[cfg(test)]
mod tests {
    //! The boundary is asserted the way a strict MCP client sees it: every
    //! payload leaving it is validated against the schema the tool actually
    //! advertises.

    use super::*;
    use cua_driver_contract::{advertised_tool_output_schema, TOOL_INVOCATION_FAILED_CODE};

    /// An action tool, so the advertised schema is the shared `ActionResult`
    /// one plus the refusal arm.
    const ACTION_TOOL: &str = "click";
    /// Advertises no `outputSchema` at all.
    const UNSCHEMED_TOOL: &str = "no_such_tool";

    #[track_caller]
    fn assert_conforms(tool: &str, result: &Value) {
        let schema = advertised_tool_output_schema(tool).expect("tool advertises a schema");
        let compiled = jsonschema::validator_for(&schema).expect("schema compiles");
        let structured = &result["structuredContent"];

        assert!(
            compiled.is_valid(structured),
            "advertised schema rejected {structured}"
        );
    }

    /// The shape this boundary exists for: the bare diagnostic the transport
    /// paths invent satisfies neither arm, which is what produced the `-32602`
    /// reports.
    #[test]
    fn a_bare_exit_code_diagnostic_does_not_validate() {
        let schema = advertised_tool_output_schema(ACTION_TOOL).expect("schema");
        let compiled = jsonschema::validator_for(&schema).expect("schema compiles");

        assert!(!compiled.is_valid(&json!({"exit_code": 1})));
    }

    #[test]
    fn an_error_diagnostic_gains_a_refusal_marker() {
        let result = conforming_tool_result(
            ACTION_TOOL,
            tool_error_result("daemon transport closed", json!({"exit_code": 1})),
        );

        assert_conforms(ACTION_TOOL, &result);
        // The diagnostic survives; only the marker is added.
        assert_eq!(result["structuredContent"]["exit_code"], 1);
        assert_eq!(
            result["structuredContent"]["code"],
            TOOL_INVOCATION_FAILED_CODE
        );
        assert_eq!(result["content"][0]["text"], "daemon transport closed");
    }

    /// `ToolResult::error` leaves `structuredContent` unset, and every tool
    /// that refuses through it lands here.
    #[test]
    fn an_error_without_any_payload_gains_one() {
        let result = conforming_tool_result(
            ACTION_TOOL,
            json!({"content": [{"type": "text", "text": "Unknown tool: nope"}], "isError": true}),
        );

        assert_conforms(ACTION_TOOL, &result);
        assert_eq!(
            result["structuredContent"]["code"],
            TOOL_INVOCATION_FAILED_CODE
        );
    }

    /// The guard adds a marker; it does not relabel a payload that already
    /// names its own refusal.
    #[test]
    fn an_existing_refusal_code_is_preserved() {
        let result = conforming_tool_result(
            ACTION_TOOL,
            tool_error_result("denied", json!({"code": "permission_denied"})),
        );

        assert_conforms(ACTION_TOOL, &result);
        assert_eq!(result["structuredContent"]["code"], "permission_denied");
    }

    /// The proxy's empty-success fallback: a client that was promised a schema
    /// rejects this response outright rather than reading it as an error.
    #[test]
    fn a_success_missing_its_structured_payload_becomes_an_error() {
        let result = conforming_tool_result(ACTION_TOOL, json!({"content": [], "isError": false}));

        assert_conforms(ACTION_TOOL, &result);
        assert_eq!(result["isError"], true);
        assert_eq!(
            result["structuredContent"]["code"],
            TOOL_OUTPUT_INVALID_CODE
        );
    }

    #[test]
    fn b07_prewarm_knob_parses_only_one() {
        assert!(exp_output_validator_prewarm_from(Some("1")));
        for value in [None, Some(""), Some("0"), Some("true"), Some("yes"), Some(" 1")] {
            assert!(!exp_output_validator_prewarm_from(value), "{value:?}");
        }
    }

    /// The prewarm shares one compiled validator across the action-result
    /// tools and leaves every verdict and every result byte unchanged.
    #[test]
    fn b07_prewarm_shares_one_validator_and_keeps_results_identical() {
        let valid = json!({
            "content": [{"type": "text", "text": "clicked"}],
            "isError": false,
            "structuredContent": {
                "effect": "confirmed",
                "route": "accessibility",
                "delivery": {"mode": "background"},
                "evidence": [{"kind": "value_readback"}],
            },
        });
        let rejected = json!({
            "content": [],
            "isError": false,
            "structuredContent": {"clicked": true},
        });
        let tools = ["browser_click", "browser_type", "click"];
        let before: Vec<String> = tools
            .iter()
            .flat_map(|tool| {
                [valid.clone(), rejected.clone()]
                    .map(|r| serde_json::to_string(&conforming_tool_result(tool, r)).unwrap())
            })
            .collect();

        let entered = exp_prewarm_action_output_validators();
        assert_eq!(entered, cua_driver_contract::ACTION_RESULT_TOOLS.len());

        let after: Vec<String> = tools
            .iter()
            .flat_map(|tool| {
                [valid.clone(), rejected.clone()]
                    .map(|r| serde_json::to_string(&conforming_tool_result(tool, r)).unwrap())
            })
            .collect();
        assert_eq!(before, after, "result bytes changed");
        // Each action-result tool advertises the same schema, so prewarmed
        // names share one compiled validator.
        let cache = OUTPUT_VALIDATORS.lock().unwrap();
        let shared = |tool: &str| cache.get(tool).unwrap().as_ref().unwrap().clone();
        assert!(Arc::ptr_eq(&shared("mouse_button_up"), &shared("parallel_mouse_drag")));
        for tool in cua_driver_contract::ACTION_RESULT_TOOLS {
            assert_eq!(
                advertised_tool_output_schema(tool),
                advertised_tool_output_schema("browser_click"),
                "{tool}"
            );
        }
    }

    #[test]
    fn a_success_whose_payload_the_schema_rejects_becomes_an_error() {
        let result = conforming_tool_result(
            ACTION_TOOL,
            json!({
                "content": [],
                "isError": false,
                "structuredContent": {"clicked": true},
            }),
        );

        assert_conforms(ACTION_TOOL, &result);
        assert_eq!(result["isError"], true);
        assert_eq!(
            result["structuredContent"]["code"],
            TOOL_OUTPUT_INVALID_CODE
        );
    }

    #[test]
    fn a_conforming_success_is_returned_untouched() {
        let structured = json!({
            "effect": "confirmed",
            "route": "accessibility",
            "delivery": {"mode": "background"},
            "evidence": [{"kind": "value_readback"}],
        });
        let success = json!({
            "content": [{"type": "text", "text": "clicked"}],
            "isError": false,
            "structuredContent": structured,
        });

        let result = conforming_tool_result(ACTION_TOOL, success.clone());

        assert_conforms(ACTION_TOOL, &result);
        assert_eq!(result, success);
    }

    #[test]
    fn a_success_missing_required_nullable_fields_becomes_a_conforming_error() {
        let structured = json!({
            "session": "schema-test",
            "capture_scope": "window",
            "effective_scope": "window",
            "desktop_capture_authorized": false,
            "desktop_unlocked": false,
        });
        let tool = "get_session_state";
        assert!(validate_success_output(tool, structured.clone()).is_ok());
        let result = conforming_tool_result(
            tool,
            json!({
                "content": [{"type": "text", "text": "action completed"}],
                "isError": false,
                "structuredContent": structured,
            }),
        );

        assert_conforms(tool, &result);
        assert_eq!(result["isError"], true);
        assert_eq!(
            result["structuredContent"]["code"],
            TOOL_OUTPUT_INVALID_CODE
        );
        assert_eq!(result["structuredContent"]["execution_state"], "unknown");
        assert_eq!(
            result["structuredContent"]["invalid_output"]["session"],
            "schema-test"
        );
        assert!(result["content"][0]["text"]
            .as_str()
            .unwrap()
            .contains("Verify state before retrying"));
        assert_eq!(result["content"][1]["text"], "action completed");
    }

    fn agent_cursor_state(position: Value) -> Value {
        json!({
            "session": "cursor-state-test",
            "enabled": true,
            "position": position,
            "theme": {
                "id": "cua-default",
                "version": "1",
                "profile": "default",
                "reduced_motion": "auto",
                "fallback": null,
            },
            "visual_state": {
                "requested_action": "idle",
                "resolved_action": "idle",
                "modifiers": [],
                "phase": "idle",
                "frame": 0,
                "preempted_count": 0,
            },
            "motion": {
                "start_handle": 0.3,
                "end_handle": 0.3,
                "arc_size": 0.25,
                "arc_flow": 0.0,
                "spring": 0.72,
                "glide_duration_ms": 750.0,
                "dwell_after_click_ms": 400.0,
                "idle_hide_ms": 3000.0,
                "turn_radius": 12.0,
            },
        })
    }

    /// A session cursor that has never moved has no position yet. Every
    /// platform reports that as `"position": null`, and the advertised schema
    /// must accept it rather than turning the read into `tool_output_invalid`.
    #[test]
    fn agent_cursor_state_accepts_a_cursor_that_has_not_moved() {
        const TOOL: &str = "get_agent_cursor_state";
        for position in [Value::Null, json!({"x": 10.0, "y": 20.0})] {
            let success = json!({
                "content": [{"type": "text", "text": "Agent cursor state."}],
                "isError": false,
                "structuredContent": agent_cursor_state(position),
            });

            let result = conforming_tool_result(TOOL, success.clone());

            assert_conforms(TOOL, &result);
            assert_eq!(result, success);
        }
    }

    /// `position` stays required: an unmoved cursor reports `null`, it does
    /// not drop the key.
    #[test]
    fn agent_cursor_state_without_a_position_key_is_rejected() {
        const TOOL: &str = "get_agent_cursor_state";
        let mut structured = agent_cursor_state(Value::Null);
        structured.as_object_mut().unwrap().remove("position");

        let result = conforming_tool_result(
            TOOL,
            json!({"content": [], "isError": false, "structuredContent": structured}),
        );

        assert_eq!(result["isError"], true);
        assert_eq!(
            result["structuredContent"]["code"],
            TOOL_OUTPUT_INVALID_CODE
        );
    }

    /// A tool with no advertised schema has no contract to violate, so its
    /// successful payload must not be second-guessed here.
    #[test]
    fn a_success_from_a_tool_without_a_schema_is_untouched() {
        let success = json!({
            "content": [{"type": "text", "text": "ok"}],
            "isError": false,
            "structuredContent": {"anything": "goes"},
        });

        assert_eq!(
            conforming_tool_result(UNSCHEMED_TOOL, success.clone()),
            success
        );
    }

    #[test]
    fn a_result_that_is_not_an_object_becomes_a_conforming_error() {
        let result = conforming_tool_result(ACTION_TOOL, json!("not a result"));

        assert_conforms(ACTION_TOOL, &result);
        assert_eq!(result["isError"], true);
    }
}
