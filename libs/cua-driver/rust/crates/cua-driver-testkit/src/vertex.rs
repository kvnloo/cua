//! Shape lint for the legacy Vertex/Gemini Schema-shaped input path (#4798).
//!
//! Derived from #4871's contract lint and injaneity's testkit extraction in
//! #4888. RitikaxG identified the missing runtime-only tools/list coverage.
//! Keep #4871's nullable and reference handling: this is not a wire migration.
//! This lint is not a live provider acceptance test or a parametersJsonSchema
//! validator. It walks schema positions, not arbitrary JSON payloads.

use serde_json::Value;

const VERTEX_SCHEMA_FIELDS: &[&str] = &[
    "type",
    "format",
    "title",
    "description",
    "nullable",
    "default",
    "items",
    "minItems",
    "maxItems",
    "enum",
    "properties",
    "propertyOrdering",
    "required",
    "minProperties",
    "maxProperties",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "pattern",
    "example",
    "anyOf",
    "additionalProperties",
    "$ref",
    "$defs",
];

const VERTEX_SCHEMA_TYPES: &[&str] = &[
    "string", "number", "integer", "boolean", "array", "object", "null",
];

/// Report nodes outside the schema-shape policy used by the #4871 tests.
/// Property names and default/example/enum payloads are not schema keywords.
pub fn input_schema_violations(schema: &Value) -> Vec<String> {
    let mut out = Vec::new();
    walk(schema, "$", &mut out);
    out
}

fn walk(schema: &Value, path: &str, out: &mut Vec<String>) {
    let Some(node) = schema.as_object() else {
        out.push(format!("{path}: schema must be an object, got {schema}"));
        return;
    };
    for key in node.keys() {
        if !VERTEX_SCHEMA_FIELDS.contains(&key.as_str()) {
            out.push(format!(
                "{path}: `{key}` is not a field of the Vertex AI Schema object"
            ));
        }
    }
    match node.get("type") {
        Some(Value::String(name)) if VERTEX_SCHEMA_TYPES.contains(&name.as_str()) => {}
        Some(other) => out.push(format!(
            "{path}: type must be one of {VERTEX_SCHEMA_TYPES:?} as a single string, got {other}"
        )),
        None if !node.contains_key("$ref") => {
            out.push(format!("{path}: schema node has no type"))
        }
        None => {}
    }
    if let Some(values) = node.get("enum") {
        match values.as_array() {
            Some(values) if values.iter().all(Value::is_string) => {}
            _ => out.push(format!(
                "{path}: enum must be a list of strings, got {values}"
            )),
        }
    }
    for keyword in ["properties", "$defs"] {
        if let Some(children) = node.get(keyword) {
            if let Some(children) = children.as_object() {
                for (name, child) in children {
                    walk(child, &format!("{path}.{keyword}.{name}"), out);
                }
            } else {
                out.push(format!("{path}.{keyword}: expected an object, got {children}"));
            }
        }
    }
    if let Some(items) = node.get("items") {
        walk(items, &format!("{path}.items"), out);
    }
    if let Some(additional) = node.get("additionalProperties") {
        if !additional.is_boolean() {
            walk(additional, &format!("{path}.additionalProperties"), out);
        }
    }
    if let Some(variants) = node.get("anyOf") {
        if let Some(variants) = variants.as_array().filter(|values| !values.is_empty()) {
            for (index, variant) in variants.iter().enumerate() {
                walk(variant, &format!("{path}.anyOf[{index}]"), out);
            }
        } else {
            out.push(format!("{path}.anyOf: expected a nonempty array, got {variants}"));
        }
    }
    if let Some(required) = node.get("required") {
        if !required
            .as_array()
            .is_some_and(|fields| fields.iter().all(Value::is_string))
        {
            out.push(format!("{path}.required: expected an array of strings, got {required}"));
        }
    }
    if let Some(nullable) = node.get("nullable") {
        if !nullable.is_boolean() {
            out.push(format!("{path}.nullable: expected a boolean, got {nullable}"));
        }
    }
    if let Some(reference) = node.get("$ref") {
        if !reference.is_string() {
            out.push(format!("{path}.$ref: expected a string, got {reference}"));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn nullable_references_and_literal_payloads_keep_existing_policy() {
        let schema = json!({
            "type": "object",
            "additionalProperties": false,
            "$defs": {"label": {"type": "string"}},
            "properties": {
                "ref": {"$ref": "#/$defs/label"},
                "glow": {"type": "boolean", "nullable": true},
                "const": {
                    "type": "string",
                    "default": {"oneOf": "payload, not a schema"},
                    "example": {"type": ["object", "null"]}
                }
            }
        });
        let violations = input_schema_violations(&schema);
        assert!(violations.is_empty(), "{violations:#?}");
    }

    #[test]
    fn catches_all_four_reported_run_actions_violations() {
        let schema = json!({
            "type": "object",
            "properties": {
                "observe": {"type": ["object", "boolean"]},
                "steps": {"type": "array", "items": {"anyOf": [
                    {"type": "object", "properties": {
                        "expect": {"type": ["object", "array"]}
                    }},
                    {"type": "object", "properties": {
                        "expect": {"type": ["object", "array"]}
                    }}
                ]}}
            }
        });
        let violations = input_schema_violations(&schema);
        assert_eq!(violations.len(), 4, "{violations:#?}");
        for path in [
            "$.properties.observe:",
            "$.properties.steps.items:",
            "$.properties.steps.items.anyOf[0].properties.expect:",
            "$.properties.steps.items.anyOf[1].properties.expect:",
        ] {
            assert!(
                violations.iter().any(|message| message.starts_with(path)),
                "missing {path} in {violations:#?}"
            );
        }
    }

    #[test]
    fn rejects_malformed_schema_container_fields_instead_of_skipping_them() {
        let schema = json!({
            "type": "object",
            "properties": {
                "bad_properties": {"type": "object", "properties": ["not an object"]},
                "bad_anyof": {"type": "object", "anyOf": []},
                "bad_required": {"type": "object", "required": [true]},
                "bad_nullable": {"type": "string", "nullable": "yes"},
                "bad_ref": {"$ref": 7},
                "bad_defs": {"type": "object", "$defs": false}
            }
        });
        let violations = input_schema_violations(&schema);
        for expected in [
            "$.properties.bad_properties.properties: expected an object",
            "$.properties.bad_anyof.anyOf: expected a nonempty array",
            "$.properties.bad_required.required: expected an array of strings",
            "$.properties.bad_nullable.nullable: expected a boolean",
            "$.properties.bad_ref.$ref: expected a string",
            "$.properties.bad_defs.$defs: expected an object",
        ] {
            assert!(
                violations.iter().any(|violation| violation.starts_with(expected)),
                "missing {expected} in {violations:#?}"
            );
        }
    }

    #[test]
    fn recursively_checks_schema_positions() {
        let schema = json!({
            "type": "object",
            "properties": {
                "target": {"oneOf": [{"type": "object"}]},
                "kind": {"type": "string", "const": "window"},
                "kinds": {"type": "array", "uniqueItems": true,
                    "items": {"enum": ["text"]}},
                "flag": {"type": "boolean", "enum": [true]}
            },
            "$defs": {"bad": {"type": ["string", "null"]}},
            "additionalProperties": {"type": ["number", "null"]}
        });
        let violations = input_schema_violations(&schema);
        for expected in [
            "$.properties.target: `oneOf`",
            "$.properties.target: schema node has no type",
            "$.properties.kind: `const`",
            "$.properties.kinds: `uniqueItems`",
            "$.properties.kinds.items: schema node has no type",
            "$.properties.flag: enum must be a list of strings",
            "$.$defs.bad: type must be one of",
            "$.additionalProperties: type must be one of",
        ] {
            assert!(
                violations.iter().any(|message| message.starts_with(expected)),
                "missing {expected} in {violations:#?}"
            );
        }
    }
}
