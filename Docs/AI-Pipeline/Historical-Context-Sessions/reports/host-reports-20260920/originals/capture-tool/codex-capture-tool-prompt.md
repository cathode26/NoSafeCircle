You are building a small art-review tool for No Safe Circle, a Unity 6000.1.8f1 game. The current directory, /workspace, is a standalone clone made for this job, on branch tools/gameplay-capture-20260917 at local main <BASE>. You are running inside a Linux Docker container, so use `python3` where these instructions say `python`. The clone's git config already has core.autocrlf=true and core.filemode=false; keep them.

WHY
The Art Director reviews character art at real gameplay scale, but nobody can take a Game-view screenshot without Vincent. The Game Agent will run this tool headless (Unity batchmode on Windows) whenever art lands or the Art Director asks. The first real request is board row H-20260917-07: the current wizard, "masculine-light", standing idle, facing south-east, beside a wall, captured at exactly 1920x1080 and 2560x1440. It is evidence that the wizard's current Visual (localScale (1, 2, 1), identity rotation, 180 pixels per unit) looks thin and leans in the real game.

READ FIRST
1. AGENTS.md, CLAUDE.md, Docs/Engineering/ENGINEERING_STANDARDS.md and Docs/Engineering/UNITY_TESTING_POLICY.md.
2. How the game is assembled and run:
   - Assets/NoSafeCircle/DoorPrototype/Editor/World/DoorPrototypeGlobalSceneBuilder.cs: BuildCamera (orthographic size 8, Euler (30, -45, 0), follow offset), BuildPlayer, the wizard identity table ("masculine-light" and the others), the player spawn, and walls.
   - Assets/NoSafeCircle/DoorPrototype/Scripts/IsometricCameraFollow.cs, WizardSelection.cs, WizardSelectionController.cs and WizardAnimationController.cs (8 facings, idle and walk states).
   - Existing Play Mode tests that load Assets/Scenes/DoorPrototype.unity, for example WizardSelectionPlayModeTests and WizardAnimationPlayModeTests, and the four .asmdef files under Assets/NoSafeCircle/DoorPrototype.
   - Pipeline/Testing/run_unity_tests_clean.ps1, which is how the Game Agent runs Unity tests. It requires a clean git tree and does not pass -nographics.

WHAT TO BUILD
A gameplay capture tool with three parts.

1. Capture runner (Unity, Play Mode).
   - Load Assets/Scenes/DoorPrototype.unity the way the existing Play Mode tests do, in Play Mode, so Awake, Start, the wizard selection and IsometricCameraFollow run exactly as in the game.
   - Read a shot spec JSON. Each shot has:
     - a name;
     - a wizard identity key, validated against the game's identity table;
     - a facing, one of south, south-east, east, north-east, north, north-west, west, south-west (screen facings, as in WizardAnimationController);
     - a state, idle or walk, plus a walk frame index when the state is walk;
     - the wizard's world position (x, z) on the floor;
     - whether scene enemies are disabled for the shot (default true, so nothing wanders into frame or attacks);
     - a list of resolutions (default 1920x1080 and 2560x1440).
   - For each shot:
     - apply the identity through the game's own selection path;
     - place the wizard;
     - set the facing and state deterministically through the Animator or public APIs, with no input simulation, and make sure the sprite really shows that state's frame;
     - let the camera follow settle (LateUpdate);
     - render the scene's gameplay camera into a RenderTexture of exactly each resolution, with camera.aspect matching and orthographic size unchanged, and restore the camera afterwards;
     - read the pixels and write `<output>/<shot name>_<height>p.png`, for example `gameview_1080p.png`.
   - Screen-space UI is not part of the render. Say so in the manifest.
   - Write `<output>/capture-manifest.json` with:
     - the git commit and whether the tree was dirty (the wrapper can supply both);
     - Unity version, scene path and UTC time;
     - camera position, rotation, orthographic size and aspect per render;
     - per shot:
       - identity, facing, state, and the frame's sprite name;
       - the sprite's pixels per unit and its texture's filter mode;
       - the wizard Visual's world position, localScale and world rotation;
       - per render, the wizard pivot's screen position in pixels, unrounded, with the origin and y direction stated;
       - the output file with its size and SHA-256.
   - The tool must not change any import setting. The first shot documents the current state before the Visual fix.
   - Pick the mechanism that works reliably headless: a Play Mode UnityTest marked [Explicit] with a dedicated category, run by an exact test filter, reading its spec and output paths from environment variables, is a good fit. It must never run as part of normal test filters. It must fail loudly on a missing spec, an unknown identity or facing, a render or write failure, or an image that is a single flat color.
   - Never save the scene or any asset, and leave the git tree clean after a run.
2. Wrapper script for the Game Agent (Windows PowerShell or Python, next to the other Pipeline tools).
   - Inputs: checkout path, spec file and output folder. The output folder must be outside the repository.
   - Refuse if a Unity process already has that checkout open.
   - Record the commit and dirty state.
   - Run Unity batchmode Play Mode with only the capture test, by exact filter, preferably through Pipeline/Testing/run_unity_tests_clean.ps1, and without -nographics.
   - Afterwards, verify every expected PNG exists with its exact dimensions and print the output paths. Exit non-zero on any failure.
3. Example spec and short README.
   - The example spec is the first request:
     - shot name "gameview";
     - identity "masculine-light";
     - facing south-east, state idle;
     - both resolutions;
     - enemies disabled;
     - a floor position in the Ruined Entry, near the player spawn, about 1 world unit in front of a far, full-height (2.5 unit) north (+Z) or west (-X) wall. The wall sits directly BEHIND the wizard as seen from the camera, which looks toward world -X, +Z, and nothing (wall, door, prop, other character) overlaps the wizard in the frame. The Art Director uses that wall's height as the scale reference. Compute the position from the builder's layout data, and explain the choice in the README.
   - The README says how the Art Director words a request, how the Game Agent runs the wrapper, and what the manifest contains.
   - Add focused tests for the pure logic you add, such as spec parsing, facing names and resolution parsing: Edit Mode tests if the logic lives in C#, Python unittest if it lives in the wrapper.

HARD RULES
- Work only on this branch. NEVER push. NEVER commit to main or move it. Never delete branches, tags or worktrees. Never touch any directory outside this clone.
- Commit as user.name "No Safe Circle Codex Worker", user.email "codex-worker@nosafecircle.invalid"; the clone's local config already has both. Stage exact paths with `git add -- <path>`; never `git add .` or `-A`. Make small, logical commits with clear messages.
- New files only. Do not edit any existing gameplay script, builder, scene, asset, ProjectSettings or .asmdef.
  - If the tool truly cannot work without changing an existing file, stop and report exactly which change and why.
  - A brand-new C# file gets a new .meta with `fileFormatVersion: 2` and a fresh 32-hex guid.
  - New folders under Assets need a folder .meta with a fresh guid.
- Unity is NOT available to you. Do not try to run it, and never claim anything compiled or passed. The Game Agent runs it. Re-read every C# file you add for compile errors and assembly-boundary problems, for example runtime versus Editor APIs in the test assembly.
- Put temp files under `codex-tmp/` (git-ignored for this clone) and do not commit them.
- If reality contradicts these instructions, stop and report. Do not guess.

FINAL MESSAGE (concise report)
1. Every commit SHA and what it adds.
2. How a capture runs end to end, which mechanism you chose, and why it works headless.
3. The exact wrapper command the Game Agent runs for the example spec, with output folder C:\nscrev\reports\art-director\density-trial-20260916\, and the Unity test filter it uses.
4. The example shot's position and why the wall is behind the wizard from the camera's side.
5. The exact commands for the tests you added.
6. Anything you could not verify, risks for headless rendering such as graphics device, color space or sRGB read-back, and anything you did not do.
