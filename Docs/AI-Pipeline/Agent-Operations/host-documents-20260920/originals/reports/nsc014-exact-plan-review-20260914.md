# NSC-014 exact graph-application review

- Canonical local main at review: `6ba9304730c8e2743e969554d2bf1b3452f98fab` (clean).
- Run 6 research source: `ccb933e434f078634daa993422740b6f127b070f`.
- Run ID: `run6-nsc-014-ccb933e-apply01`; result: `review_ready` after Claude author, Codex revision, Claude independent pass.
- Exact plan: `GDP-0041040e06fc4f69ff37c9ec03c9422b0e861f465f79260faa3e2be39516ee19`.
- Proposal file SHA-256: `1604cd4a804c63bba2fa94b57ff066ca367a9200e8813c7c08b815f9857ebb0e`.
- Plan file SHA-256: `8bb62dceed11a64e75dcfc202b3e2fd2bfcd07dd5538c87e260fe73c6d70377e`.
- Reviewed candidate semantic SHA-256: `3ac8e26b86fdae16d070c7cd2fac8ffd38a6447620f360743b487217c00f65df`.
- Independent canonical `plan_graph_apply`: `fresh` with exact deterministic plan equality.

The plan turns NSC-014 into a decomposed parent and allocates NSC-091 to target detection, target knowledge and search state, and NSC-092 to NavMesh pursuit, search movement, doorway traversal and reset coordination. NSC-092 alone receives `logical:enemy-locomotion-behavior-surface`; it depends on NSC-091, NSC-089 and NSC-090. Nine inbound dependency contracts are rewritten once each: NSC-013, NSC-015, NSC-016, NSC-017, NSC-033, NSC-053, NSC-054, NSC-071 and NSC-088. Unrelated dependencies and requirements remain unchanged.

Astra independently approved this exact plan with no blocking findings. NSC-054's rewrite provides its current-player-target prerequisite only; it does not add an active-target firing rule. NSC-088's rewrite does not decide the Spectral Decoy design. The new child contracts require later implementation and their local tests do not replace NSC-071's real Bone Archive proof.

Exact artifacts:

- `C:\nscrev\realdecomp-Checkouts-r6\.assistant-control\decomposition-runs\run6-nsc-014-ccb933e-apply01\decomposition_result.json`
- `C:\nscrev\realdecomp-Checkouts-r6\.assistant-control\decomposition-runs\run6-nsc-014-ccb933e-apply01\graph_delta.json`
- Read-only preview: `C:\NSC\nsc014_review_preview.json`

Nothing from this plan has been applied. The graph-application code requires independent review and authorization of the exact immutable plan; immediately before application, canonical main, artifact hashes and fresh-source status must be rechecked. NSC-015 and NSC-033 research runs are proceeding independently on the same pinned Run 6 source; any later application of those proposals needs a new freshness check against the changed canonical graph.
