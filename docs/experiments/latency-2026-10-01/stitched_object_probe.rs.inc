    // EXPERIMENT ONLY. Insert inside browser/store.rs's existing tests module.
    // Reuses store_with_ref() and BrowserStore; creates no second authority store.
    // This is uncompiled in the captured environment (rustc unavailable).
    // Native DOM/AX equality and real actions remain unexecuted.
    struct StitchedObservation {
        session: String,
        target: String,
        tab: String,
        page_ref: String,
        dom_backend_id: i64,
        ax_backend_id: i64,
        ax_node_id: String,
        runtime_object_id: String,
    }

    impl StitchedObservation {
        fn resolved_handles<'a>(
            &'a self,
            store: &BrowserStore,
            current_session: &str,
        ) -> Result<(&'a str, &'a str), &'static str> {
            // Never regard the attachment's cached fields as mutation authority.
            if current_session != self.session {
                return Err("session_mismatch");
            }
            let live = store
                .resolve_ref(current_session, &self.target, &self.tab, &self.page_ref)
                .map_err(|_| "authority_refused")?;
            if live.backend_node_id != self.dom_backend_id
                || self.dom_backend_id != self.ax_backend_id
            {
                return Err("object_identity_mismatch");
            }
            Ok((&self.ax_node_id, &self.runtime_object_id))
        }
    }

    #[test]
    fn experimental_stitched_metadata_retires_with_existing_authority() {
        let (store, target, tab, page_ref) = store_with_ref();
        let observation = StitchedObservation {
            session: "sess-a".into(), target: target.clone(), tab,
            page_ref, dom_backend_id: 555, ax_backend_id: 555,
            ax_node_id: "fixture-ax-id".into(),
            runtime_object_id: "fixture-runtime-id".into(),
        };
        assert!(observation.resolved_handles(&store, "sess-a").is_ok());
        assert_eq!(observation.resolved_handles(&store, "sess-b"), Err("session_mismatch"));
        store.update_target("sess-a", &target, |record| record.generation += 1);
        assert_eq!(observation.resolved_handles(&store, "sess-a"), Err("authority_refused"));
        // Neither AX nor runtime handle is returned after generation invalidation.
        // All mutations still go through existing Driver actions and frame reproof.
    }
