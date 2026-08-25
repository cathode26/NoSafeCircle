# Repository Agent Guidance

This file is operating guidance, not GDD canon.

Any agent creating, modifying, reviewing, or running tests must first read `Docs/Engineering/UNITY_TESTING_POLICY.md`.

Before producing operational commands or human-facing handoff artifacts, read `Docs/AI-Pipeline/OPERATOR_FILE_HANDOFF_AND_DOWNLOADS.md`. Human-facing external files default to the Windows Downloads folder; repository-authoritative, pipeline-owned, and hash-bound files remain at their required locations.

Any work involving Unity build targets, platform-dependent APIs or plugins, WebGL/browser compatibility, deployment, or release packaging must also read `Design/Approved/Platform/Desktop_WebGL_Publishing_Target.md`. Desktop WebGL is a human-approved additional publication target; it does not remove the canonical Windows Standalone requirement.

Task meaning comes from the selected task contract and current approved canon. Deterministic tools, not agent claims, establish test results and clean-tree state.

Do not duplicate the complete testing, handoff, or approved-artifact policies here; use the canonical documents above.
