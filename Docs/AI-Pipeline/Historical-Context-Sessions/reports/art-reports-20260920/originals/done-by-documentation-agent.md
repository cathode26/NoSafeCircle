# Art Director: done (documentation agent, 2026-09-16)

This answers `brief-for-documentation-agent.md`.

**Created**
- `C:\Users\VincentLiguori\.claude\agents\art-director.md`: the custom agent `art-director` (Claude Opus 5, effort high, inherits all tools including the PixelLab MCP). Its prompt is the art bible:
  - the vision (Ultima Online plus Diablo, dark-but-cute);
  - camera and facing (your Euler 30/-45/0 facts and the flip lesson);
  - a palette with swatches sampled from the approved sprites;
  - light, outline and shading rules;
  - scale and canvas conventions;
  - readability checks;
  - identity rules;
  - an identity bible for wizards, both enemies, doors, the architecture kit (not approved), props and UI, with reference image paths;
  - PixelLab pitfalls;
  - hard rules;
  - a fixed report format.
- `C:\NSC\nsc-art-director-guide.md`: the operating guide. It covers routing, authority, setup, per-class PixelLab settings, provenance, review packages, `.meta` rules, open art questions for Vincent (section 11) and the art queue (section 12).
- `C:\NSC\CLAUDE.md`: loaded by every Claude session under `C:\NSC`. It tells sessions to route all 2D art to `art-director`.

**Changed**
- `C:\NSC\nsc-art-producer-guide.md` is now a redirect. **Its art queue moved to `nsc-art-director-guide.md` section 12**, with your 9/16 Wizard, Enemies and Doors updates copied verbatim. Please update the queue there from now on.
- The Art Director replaces the Art Producer in:
  - `nsc-agent-launch-prompts.md`: an Art Director section with a delegation brief, plus routing rules added to the Main, Task and GER prompts;
  - `nsc-pipeline-runbook.md`: the doc index, roles table and new rule 12;
  - `nsc-main-orchestrator-guide.md`;
  - `nsc-task-orchestrator-guide.md` (section 3, item 6);
  - `nsc-ger-orchestrator-guide.md` (section 9);
  - `nsc-integration-steward-guide.md`;
  - `nsc-delivery-evidence-guide.md`.

**To use it now**
- Sessions started before the agent file existed may not list `art-director`. Start a new session, or run `/agents`.
- Call the Agent tool with `subagent_type: "art-director"` and the brief from the launch-prompts file.

**Flagged for Vincent** (guide section 11): texel density (wizard 180 PPU vs room sprites 64 PPU vs 32 px tiles), and the teal-lantern wraith art vs the "fire caster" enemy's color story.
