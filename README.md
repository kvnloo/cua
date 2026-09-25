# RFC #3963 dependency census

This scan-only research branch intentionally contains no product checkout or normal CI workflows. Its one-shot push workflow reads the public `trycua/cua` issue/PR corpus and source pinned to `a959b2a23f8099769d0d57e4b8c2c8e70bf7d036`. It performs no upstream writes and executes no target repository code. GitHub credentials are read-only and are never stored in the export.

Reference edges are mentions, not inferred prerequisites. The coverage manifest retains pagination failures, limits, and exclusions. The export is evidence for a separately reviewed RFC requirement/owner map, not a claim that every proposal is accepted or every implementation is shipped.

Run locally with `GH_TOKEN` containing a read-only GitHub token and `python scan.py`. Generated output is under `export/`. AI-assisted, under the repository owner's direction.
