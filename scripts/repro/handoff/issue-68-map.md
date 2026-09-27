# Issue 68

Fetched trycua/cua#3873 on 2026-09-25. It is OPEN. Title: `fix(cua-driver)!: resolve element tokens against a snapshot store invalidated on read`. The fetched body does not mention a snapshot quota. This branch did not merge that pull request.

On pinned main `c5ee191c02b11448ffefcc38b78b064a87d8ef23`, which this branch contains:

- `snapshot_id` pairs with `element_index` from the same response (`WORKFLOW.md` line 53). A later snapshot invalidates a pending action.
- `capture_id` is a different identity (`perception-extension.md` lines 99–100). A local PNG label cannot authorize a Driver action (lines 43–46).
- Windows skill text keys the element index map on `(pid, window_id)` (`WINDOWS.md` lines 519–522). A stale token fails with `stale_element_token` or `snapshot_id_required`.
- What survives into the next native action is a token from the current snapshot. `guarded_run.py` does not let the pre-type Submit ref authorize the second child.
- `browser_revision.bind` refuses the same label on a new generation. It does not mint a snapshot.
- `shadow_probe.record` stores `skip_capture=false`. It cannot extend action authority.

#3873, if it lands, keeps that single snapshot owner: a read replaces the window snapshot, a stale token is refused, and `element_token` is the only element input. It deletes `element_index` / `snapshot_id` action parameters. It does not leave a hole for a second authority.

Phase-2 concepts that are unnecessary because this owner already exists:

- a second snapshot authority
- a universal shadow store
- RevisionService
- a shadow layer that mints or extends action authority

Conditional observation stays unearned. macOS AX and Windows UIA were not re-censused here.
