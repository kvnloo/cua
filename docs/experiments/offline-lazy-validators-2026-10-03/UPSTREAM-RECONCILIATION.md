# Upstream reconciliation: lazy-validator mechanism already exists

**Decision: SUPERSEDED as a new implementation plan; qualify a supported SDK upgrade instead.** No SDK changes or upgrade have been made.

The original offline experiment remains valid for its measured versions and workloads: 3,131 checks plus 1,784 supplemental acceptance checks passed; the first-five-call outcome remained MODIFY, while repeated workloads benefited. Those measurements do not establish performance or integration readiness for another SDK version.

Official MCP main was resolved to [2118f14f8a19bc158d8a1cf90af58d85d187f849](https://github.com/modelcontextprotocol/python-sdk/commit/2118f14f8a19bc158d8a1cf90af58d85d187f849). Its [ClientSession implementation](https://github.com/modelcontextprotocol/python-sdk/blob/2118f14f8a19bc158d8a1cf90af58d85d187f849/src/mcp/client/session.py) already lazily caches validators per session and tool, reuses equal schemas, evicts changed schemas, and prunes tools after a complete uncursored single-page listing. The upstream mechanism originated in merged [PR #3134](https://github.com/modelcontextprotocol/python-sdk/pull/3134), by jlowin, co-authored by Max Isbey. The original PR described identity-based reuse; current main instead uses canonical JSON equality and listing-driven eviction.

A preregistered, offline extraction of five current-main functions passed **48/48 assertions** over tiny synthetic fixtures. These are assertions across scenarios, not 48 distinct scenarios. Coverage included same-name schema replacement, local reference changes, error-message selection, invalid/unresolved schemas, explicit null versus missing content, pagination, session isolation, cooperative concurrency and cancellation. No benchmark was rerun.

Important limits:
- This was an exact-function extraction with synthetic type/transport stubs and the legacy negotiated-version branch, not whole-SDK integration or the upstream test suite.
- Installed MCP 1.29.0 and N-02's MCP 1.30.0 both use one-shot validation. The latter additionally supplies an empty registry and wraps unresolved-reference failures. Current main has a different API/type surface; compatibility must be qualified before upgrading CUA.
- Current-main validation uses a fixed empty registry; custom registry replacement is not a supported seam. Failed schema checks are uncached; unresolved references may fail after a validator has been cached.
- Sixty-four concurrent known-schema validations compiled once. Sixteen concurrent misses issued sixteen listings and compiled once for equal schemas. Responses use last-absorbed ordering, which does not prove newest-server-revision ordering.
- Modern header filtering, full typed parsing, dispatcher/transport, notification-driven invalidation, shared-session multithreading and end-to-end performance were not qualified.

Credit: Kevin Rajan / KevinN-02 for the original CUA experiment and measurements; MCP Python SDK authors, including jlowin and Max Isbey, for the existing upstream mechanism; jsonschema/referencing authors for validation semantics. This reconciliation claims no new cache invention and includes no captured UI data.
