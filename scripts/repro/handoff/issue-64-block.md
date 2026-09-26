# Issue 64 — final disposition

Final disposition: **SUPERSEDED / closed duplicate**.

trycua/cua#4165 is closed. Its lazy-parse ordering and candidate-invariance test were explicitly salvaged into trycua/cua#4196.

#4196 merged as upstream commit:
`24aaf8d1965b3b7c1530cbb9d58758ec89472d92`.

A fork-only exact-head A/B artifact exists at:
- branch `muse/issue-64-exact-head-ab`
- commit `147158cf9caed69489607f7e6736dc9282bdd815`
- path `scripts/repro/handoff/issue-64/`

Controlled results:
- default fixture: auto verified in 2 steps with 0 visual tool calls; always verified with 4;
- visual fixture: auto verified with 2 visual tool calls; always verified with 4.

This controlled harness uses a fake async Driver and does not prove a real perception-enabled desktop visual action. That remaining gap belongs to downstream #2 against merged #4196.

Do not reopen #64 to qualify closed #4165.
