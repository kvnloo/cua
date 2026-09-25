# CUA wave 1 — completed HTTP/browser evidence

Date: 2026-09-25. Completes packet W14 in the [20-packet execution ledger](cua-wave1-20260925.md). This report supersedes that ledger's initial in-progress status for W14; other design and performance gates are unchanged.

## Result

[Run 36099230247](https://github.com/kvnloo/cua/actions/runs/36099230247), [job 107957962336](https://github.com/kvnloo/cua/actions/runs/36099230247/job/107957962336), completed successfully. Eight controller checks and six real-runner HTTP/MCP/Chromium integration cases passed. The product candidate's tracked source remained unchanged.

| Runner | Selected backend | Owned HTTP reply | HTTP requests | Candidate input calls at MCP ingress | Independent fixture result |
|---|---|---|---:|---|---|
| Python | `local` | Valid supplied choices | 2 | `browser_type`, `browser_click` | Exact expected token submitted |
| Python | `openjev` | Valid supplied choices | 2 | `browser_type`, `browser_click` | Exact expected token submitted |
| Python | `local` | Choice outside supplied candidates | 1 | None | No submission; `invalid_response` abstention |
| TypeScript | `local` | Valid supplied choices | 2 | `browser_type`, `browser_click` | Exact expected token submitted |
| TypeScript | `openjev` | Valid supplied choices | 2 | `browser_type`, `browser_click` | Exact expected token submitted |
| TypeScript | `local` | Choice outside supplied candidates | 1 | None | No submission; `invalid_response` abstention |

Every positive case executed the existing `type-verification-value` then `submit-form` candidates; dry-run output was disallowed. Each negative case still performed browser setup/observation, but dispatched no candidate input. Zero input calls is not zero Driver calls.

The negative-control response retained a valid normalized probability distribution while returning an unknown chosen ID. This tests rejection before input, not arbitrary model failures. The byte-forwarding MCP audit records tool names, not action arguments. Independent fixture state and audit records are both required: no submission alone would not prove that no typing happened.

## Exact identities

- Product PR: [trycua/cua#3961](https://github.com/trycua/cua/pull/3961).
- Product candidate: `737cda114ae711713a3dbfa9c9ba76863dfd46b9`.
- Fork-only controller/workflow commit: `4187a6b5c35b934f31c9b77f0376e9bc0a0ebf51`.
- Controller SHA-256: `f227962131c0e042447954dbdf16549c5b813ac6db9462631301df6aeeb17d2d`.
- Canonical bootstrap workflow blob: `7ea76b00fc0ffdb5141062e594af12709a40f49c`.
- Driver binary SHA-256 recorded by the runner: `b3534809adb61540f3a5a9bc0be01d1546750568b993baeb7e02264cc250c282`.

The first four canonical bootstrap bodies were retained unchanged; the final integration stage is explicitly adapted for these six cases. This is not a claim that the entire canonical workflow or full desktop matrix was rerun unchanged.

## Artifact verification

[Artifact 10848314560](https://github.com/kvnloo/cua/actions/runs/36099230247/artifacts/10848314560), `cua-wave1-http-browser`, is 49,676 bytes. Its downloaded ZIP SHA-256 matches the re-fetched GitHub artifact metadata:

```
a581b89f7e333248fd66c8c83bc76f74d4516afa1841df44674f9b1bec3be58c
```

All **43 entries** in `wave1-evidence/SHA256SUMS` were independently recomputed and matched. The downloaded result/controller identities were checked, and all six case receipts were rechecked against the controller's acceptance rules. That recheck is evidence validation, not another live run. The recorded binary hash was not independently recomputed because the binary is not in this artifact.

An initial metadata response reported a different size/digest (`48,736`, `9b4f756a482c1e938d802a1b18645f035a76129ec28a4c1e50446d6a791338742`). Acceptance was held until native artifact listing and the REST run-artifact listing were re-fetched; both then matched the downloaded bytes and workflow identity above. The cause of that initial discrepancy is unknown. It is retained in the local verification receipt, not treated as a product finding or silently discarded.

## Scope and remaining gates

Both `local` and `openjev` point at an owned loopback responder producing synthetic decisions. This qualifies the selected HTTP backend path through the actual language runners and Driver/browser fixture. It does **not** qualify external OpenJev/TypeSafe services, model quality, all error/cancellation cases, native macOS/Windows behavior, or a latency speedup.

No product PR branch, public Driver contract, or contributor assignment changed. The test campaign does not replace upstream CI, maintainer review, or a recorded RFC decision. Whole-task accounting and interleaved before/after latency remain separate work under #3963/#4052. Completion gates remain outside the narrowed #3961 provider-only scope.

AI-assisted test preparation, source review, and artifact verification.
