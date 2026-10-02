// kvnloo/cua#107 lane AB, experiment-local UNIT test (never committed into libs/cua-driver).
//
// run_unit_acquisition.sh appends this file to a TEMPORARY copy of
// libs/cua-driver/rust/crates/cua-driver-core/src/browser/v2_tests.rs and runs it there,
// so the branch's libs/cua-driver tree (and the i107 binary built from it) stays unchanged.
//
// Question (MAP.md section 4, point 1): does a semantic_v2 read with `query` or `scope_ref`
// issue fewer or different CDP calls than a full semantic_v2 read? Fixture: the existing
// deterministic mock CDP endpoint (v2_tests.rs), which records every incoming CDP call.
// A `continuation` read is recorded as the contrast case (MAP.md section 4, point 2).

fn i107ab_calls_len(f: &Fixture) -> usize {
    f.state.lock().unwrap().calls.len()
}

/// Strip values that legitimately change between two reads of the same page (the
/// per-attach CDP session ids the mock mints), so only acquisition shape remains.
fn i107ab_normalize(value: &Value) -> Value {
    match value {
        Value::Object(map) => Value::Object(
            map.iter()
                .filter(|(key, _)| key.as_str() != "sessionId")
                .map(|(key, item)| (key.clone(), i107ab_normalize(item)))
                .collect(),
        ),
        Value::Array(items) => Value::Array(items.iter().map(i107ab_normalize).collect()),
        other => other.clone(),
    }
}

/// The CDP calls recorded since `start`, as a sorted multiset of (method, normalized params).
fn i107ab_acquisition_since(f: &Fixture, start: usize) -> Vec<String> {
    let mut calls: Vec<String> = f.state.lock().unwrap().calls[start..]
        .iter()
        .map(|(_, method, params)| format!("{method} {}", i107ab_normalize(params)))
        .collect();
    calls.sort();
    calls
}

fn i107ab_methods(calls: &[String]) -> Vec<String> {
    calls
        .iter()
        .map(|call| call.split(' ').next().unwrap_or("").to_owned())
        .collect()
}

async fn i107ab_read(f: &Fixture, target: &str, tab: &str, extra: Value) -> (Value, Vec<String>) {
    let start = i107ab_calls_len(f);
    let snap = semantic_snapshot_with(f, target, tab, extra).await;
    (snap, i107ab_acquisition_since(f, start))
}

#[tokio::test]
async fn i107ab_query_and_scope_reads_acquire_exactly_what_a_full_read_acquires() {
    for large in [false, true] {
        let f = fixture_with(|st| st.semantic_large_page = large).await;
        let (target, tab) = bind(&f).await;
        let query = json!({ "query": "verification value submit" });
        // Interleaved full / query / full / query, so neither order nor warm-up explains a match.
        let (full1, full1_calls) = i107ab_read(&f, &target, &tab, json!({})).await;
        let (q1, q1_calls) = i107ab_read(&f, &target, &tab, query.clone()).await;
        let (full2, full2_calls) = i107ab_read(&f, &target, &tab, json!({})).await;
        let (q2, q2_calls) = i107ab_read(&f, &target, &tab, query.clone()).await;
        for snap in [&full1, &q1, &full2, &q2] {
            assert_eq!(snap["status"], "ok", "large={large}: {snap}");
        }
        assert_eq!(full1["snapshot"]["scope"], "viewport", "large={large}: {full1}");
        assert_eq!(q1["snapshot"]["scope"], "query", "large={large}: {q1}");
        assert!(
            i107ab_methods(&full1_calls).iter().any(|m| m == "DOM.getDocument")
                && i107ab_methods(&full1_calls).iter().any(|m| m == "DOMSnapshot.captureSnapshot")
                && i107ab_methods(&full1_calls).iter().any(|m| m == "Accessibility.getFullAXTree"),
            "large={large}: full read must acquire DOM, layout and AX: {full1_calls:?}"
        );
        assert_eq!(full1_calls, q1_calls, "large={large}: query read acquired differently");
        assert_eq!(full2_calls, q2_calls, "large={large}: query read acquired differently (2nd pair)");
        assert_eq!(full1_calls, full2_calls, "large={large}: two full reads differ");
        // Projection did happen: the query read returns no more nodes than the full read.
        assert!(
            q1["snapshot"]["selected_nodes"].as_u64() <= full1["snapshot"]["selected_nodes"].as_u64(),
            "large={large}: {q1}"
        );
        println!(
            "I107AB large={large} full_calls={} query_calls={} methods={:?} full_selected={} query_selected={} full_total={} query_total={}",
            full1_calls.len(),
            q1_calls.len(),
            i107ab_methods(&full1_calls),
            full1["snapshot"]["selected_nodes"],
            q1["snapshot"]["selected_nodes"],
            full1["snapshot"]["total_nodes"],
            q1["snapshot"]["total_nodes"],
        );

        if large {
            // scope_ref: same acquisition again (resolved against the current snapshot first).
            let (fresh, _) = i107ab_read(&f, &target, &tab, json!({})).await;
            let heading_ref = fresh["content_refs"]
                .as_array()
                .unwrap()
                .iter()
                .find(|entry| entry["name"] == "Visible message")
                .and_then(|entry| entry["ref"].as_str())
                .expect("heading content ref")
                .to_owned();
            let (scoped, scoped_calls) =
                i107ab_read(&f, &target, &tab, json!({ "scope_ref": heading_ref })).await;
            assert_eq!(scoped["snapshot"]["scope"], "subtree", "{scoped}");
            assert_eq!(scoped_calls, full1_calls, "scope_ref read acquired differently");
            println!("I107AB scope_ref_calls={} equal_to_full=true", scoped_calls.len());

            // continuation: pages through the stored document; not a fresh read.
            let (first, _) = i107ab_read(&f, &target, &tab, json!({})).await;
            let token = first["snapshot"]["continuation"]
                .as_str()
                .expect("large fixture continuation")
                .to_owned();
            let (continued, cont_calls) =
                i107ab_read(&f, &target, &tab, json!({ "continuation": token })).await;
            assert_eq!(continued["snapshot"]["scope"], "continuation", "{continued}");
            let cont_methods = i107ab_methods(&cont_calls);
            assert!(
                !cont_methods.iter().any(|m| m == "DOM.getDocument"
                    || m == "DOMSnapshot.captureSnapshot"
                    || m == "Accessibility.getFullAXTree"),
                "continuation must not re-acquire: {cont_methods:?}"
            );
            println!("I107AB continuation_methods={cont_methods:?}");
        }
    }
}
