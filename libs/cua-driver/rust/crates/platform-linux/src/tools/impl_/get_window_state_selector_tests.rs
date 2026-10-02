use super::*;

fn first_text(result: &ToolResult) -> String {
    result
        .content
        .iter()
        .find_map(|item| match item {
            cua_driver_core::protocol::Content::Text { text, .. } => Some(text.clone()),
            _ => None,
        })
        .unwrap_or_default()
}

#[tokio::test]
async fn non_boolean_modality_selectors_are_refused_as_invalid_arguments() {
    let tool = GetWindowStateTool {
        state: ToolState::new(),
    };
    for (field, value) in [
        ("include_screenshot", json!("false")),
        ("include_screenshot", json!("true")),
        ("include_screenshot", json!(0)),
        ("include_screenshot", Value::Null),
        ("include_accessibility_tree", json!("false")),
        ("include_accessibility_tree", json!({})),
    ] {
        let mut args = json!({ "pid": std::process::id(), "window_id": 1 });
        args[field] = value.clone();
        let result = tool.invoke(args).await;
        assert_eq!(
            result.is_error,
            Some(true),
            "{field}={value} must be refused"
        );
        assert_eq!(
            result
                .structured_content
                .as_ref()
                .map(|s| s["code"].clone()),
            Some(json!("invalid_arguments")),
            "{field}={value} must be refused with invalid_arguments"
        );
        assert!(
            first_text(&result).contains(field),
            "{field}={value}: the refusal must name the field"
        );
    }
}
