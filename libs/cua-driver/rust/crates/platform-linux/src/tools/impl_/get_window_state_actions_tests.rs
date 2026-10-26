use super::*;
use crate::atspi::AtspiNode;
use atspi::{State, StateSet};

fn node(actions: Vec<String>) -> AtspiNode {
    AtspiNode {
        element_index: Some(1),
        role: "button".to_owned(),
        name: Some("ok".to_owned()),
        value: None,
        checked: None,
        expanded: None,
        enabled: Some(true),
        selected: None,
        description: None,
        actions,
        element_key: 1,
        identity: None,
        depth: 0,
        parent_element_index: None,
        in_web_content: false,
        object_ref: None,
    }
}

#[test]
fn element_entry_omits_actions_when_empty() {
    let n = node(Vec::new());
    let entry = build_element_entry(&n, None, None).unwrap();
    assert!(entry.get("actions").is_none());
}

#[test]
fn element_entry_filters_blank_action_names() {
    let n = node(vec![
        "Press".to_owned(),
        "".to_owned(),
        "   ".to_owned(),
        "Open".to_owned(),
    ]);
    let entry = build_element_entry(&n, None, None).unwrap();
    assert_eq!(entry["actions"], json!(["Press", "Open"]));
}

fn entry_for_state(role: &str, state: Option<&StateSet>) -> serde_json::Value {
    let states = crate::atspi::native::control_states(state);
    let mut n = node(vec!["toggle".into()]);
    n.role = role.into();
    n.checked = states.checked;
    n.expanded = states.expanded;
    n.selected = states.selected;
    build_element_entry(&n, Some(1), None).unwrap()
}

#[test]
fn element_entry_preserves_checked_false_true_and_mixed() {
    for role in [
        "check box",
        "radio button",
        "toggle button",
        "check menu item",
    ] {
        for (state, expected) in [
            (StateSet::new(State::Checkable), json!(false)),
            (
                StateSet::new(State::Checkable | State::Checked),
                json!(true),
            ),
            (
                StateSet::new(State::Checkable | State::Indeterminate),
                json!("mixed"),
            ),
            (
                StateSet::new(State::Checkable | State::Checked | State::Indeterminate),
                json!("mixed"),
            ),
        ] {
            let entry = entry_for_state(role, Some(&state));
            assert_eq!(entry["checked"], expected, "{role}: {state:?}");
            assert!(entry.get("selected").is_none(), "checked is not selected");
            assert!(entry.get("expanded").is_none());
        }
    }
}

#[test]
fn element_entry_keeps_expansion_and_selection_independent() {
    for (state, expanded, selected) in [
        (
            StateSet::new(State::Expandable | State::Selectable),
            false,
            false,
        ),
        (
            StateSet::new(State::Expandable | State::Expanded | State::Selectable),
            true,
            false,
        ),
        (
            StateSet::new(State::Expandable | State::Selectable | State::Selected),
            false,
            true,
        ),
        (
            StateSet::new(
                State::Expandable | State::Expanded | State::Selectable | State::Selected,
            ),
            true,
            true,
        ),
    ] {
        let entry = entry_for_state("tree item", Some(&state));
        assert_eq!(entry["expanded"], json!(expanded));
        assert_eq!(entry["selected"], json!(selected));
        assert!(entry.get("checked").is_none());
    }
    let state = StateSet::new(State::Checkable | State::Checked | State::Selectable);
    let entry = entry_for_state("check menu item", Some(&state));
    assert_eq!(entry["checked"], true);
    assert_eq!(entry["selected"], false);
}

#[test]
fn element_entry_omits_unknown_or_inapplicable_states_even_for_checkbox_role() {
    for state in [
        None,
        Some(StateSet::empty()),
        Some(StateSet::new(
            State::Checked | State::Indeterminate | State::Expanded | State::Selected,
        )),
    ] {
        let entry = entry_for_state("check box", state.as_ref());
        for key in ["checked", "expanded", "selected"] {
            assert!(entry.get(key).is_none(), "{key}: {state:?}");
        }
    }
}

#[test]
fn mixed_checkbox_cannot_prove_a_binary_setup_state() {
    use crate::atspi::CheckedState;
    assert_eq!(CheckedState::Boolean(false).as_bool(), Some(false));
    assert_eq!(CheckedState::Boolean(true).as_bool(), Some(true));
    assert_eq!(CheckedState::Mixed.as_bool(), None);
}
