$ErrorActionPreference = "Stop"

# Assignment 5 bootstrap:
# Regenerates the ANALYSIS-ONLY goal-oriented agent from scratch.
#
# Intended location:
#   NoSafeCircle\GoalOrientedAgent\Setup-Assignment5-Analysis.ps1
#
# PixelLab policy:
# - PixelLab MCP must be connected in the Claude Code environment.
# - The analysis agent KNOWS PixelLab is an approved development-time
#   resource-acquisition capability.
# - The analysis agent DOES NOT call PixelLab or spend generations.
# - PixelLab may be used later by an implementation/action phase if the
#   selected goal requires compatible art assets.

$GoalAgentDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $GoalAgentDir

Write-Host ""
Write-Host "Assignment 5 - Regenerate PixelLab-aware analysis agent" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host ""

Set-Location $RepoRoot

# Make sure the Assignment 5 folders exist.
New-Item -ItemType Directory -Force -Path "GoalOrientedAgent\prompts" | Out-Null
New-Item -ItemType Directory -Force -Path "GoalOrientedAgent\outputs" | Out-Null

# ---------------------------------------------------------------------------
# Verify PixelLab is actually connected before teaching the generated agent
# that PixelLab is an available development capability.
#
# The API token remains in Claude's external configuration. This script does
# not read it, copy it, print it, or place it in the repository.
# ---------------------------------------------------------------------------

Write-Host "Checking PixelLab MCP connection..." -ForegroundColor Yellow
$McpOutput = cmd.exe /c "docker compose run --rm claude claude mcp list 2>&1" | Out-String
$McpExitCode = $LASTEXITCODE

Write-Host $McpOutput.Trim()

if ($McpExitCode -ne 0) {
    throw "Unable to query Claude MCP connections. 'claude mcp list' failed with exit code $McpExitCode."
}

if ($McpOutput -notmatch "(?is)pixellab:.*Connected") {
    throw @"
PixelLab MCP is not reported as connected.

Before running this setup script, add PixelLab to the Claude Code environment
and verify that:

    docker compose run --rm claude claude mcp list

shows:

    pixellab: https://api.pixellab.ai/mcp (HTTP) - Connected

The analysis agent must not assume an external capability is available unless
the bootstrap process verifies it first.
"@
}

Write-Host "PixelLab MCP connection verified." -ForegroundColor Green
Write-Host ""

# Regenerate the two generated artifacts from scratch rather than patching
# earlier generated versions.
Remove-Item -Force -ErrorAction SilentlyContinue "GoalOrientedAgent\goal_agent.py"
Remove-Item -Force -ErrorAction SilentlyContinue "GoalOrientedAgent\prompts\analyze.md"

$Prompt = @'
Create the ANALYSIS-ONLY implementation for Assignment 5 in /workspace/GoalOrientedAgent.

You are generating these two files FROM SCRATCH:

- /workspace/GoalOrientedAgent/goal_agent.py
- /workspace/GoalOrientedAgent/prompts/analyze.md

Do not modify:

- /workspace/AgentCrew
- /workspace/DynamicContentPipeline
- /workspace/Docs/GDD/No_Safe_Circle_GDD.md
- any Unity file under /workspace/Assets

PixelLab MCP availability was verified by the bootstrap PowerShell script before
this Claude run started. You may therefore treat PixelLab as an AVAILABLE,
APPROVED DEVELOPMENT-TIME CAPABILITY for resource-acquisition reasoning.

IMPORTANT:
The analysis agent you generate must NOT call PixelLab or any MCP tool.
PixelLab is capability context during analysis, not an action tool during goal
selection.

============================================================
READ EXISTING INFRASTRUCTURE FIRST
============================================================

Read /workspace/AgentCrew/orchestrator.py first to understand this repository's
existing subprocess/Claude invocation pattern.

Reuse appropriate structural ideas such as:

- Python subprocess invocation
- cwd handling
- prompt loading
- JSON parsing
- structured output
- timeout/error handling

However, Assignment 5 has DIFFERENT permission, repository-boundary, and
reasoning requirements.

Do not blindly copy AgentCrew's Claude command.

The exact Assignment 5 rules below override any conflicting pattern found in
AgentCrew.

IMPORTANT DISTINCTION:

The BOOTSTRAP Claude that is currently generating goal_agent.py and analyze.md
MAY read AgentCrew/orchestrator.py for implementation-pattern reference.

The ANALYSIS Claude that goal_agent.py launches later must NEVER inspect
AgentCrew/ or DynamicContentPipeline/.

============================================================
ASSIGNMENT 5 PURPOSE
============================================================

The generated goal-oriented agent must perform this reasoning:

Desired State - Current State = Gaps

Then:

Gaps
-> Evaluate
-> Prioritize
-> Choose exactly one next implementation goal

In this project:

Desired State:
Docs/GDD/No_Safe_Circle_GDD.md

Current State:
actual gameplay implementation under Assets/

Available approved development capability relevant to missing visual resources:
PixelLab

The ANALYSIS phase must:

1. Read the GDD.
2. Extract REQUIRED gameplay features and systems.
3. Scan the actual Unity implementation under Assets/.
4. Classify each required gameplay feature as:
   - implemented
   - partial
   - missing
5. Build a set of candidate next implementation goals from missing or
   meaningfully partial required gameplay features.
6. Evaluate candidate goals using:
   - dependencies
   - prerequisite readiness
   - resource acquisition readiness
   - prototype readiness
   - integration readiness
   - unlock value
   - implementation risk and size
   - required-vs-stretch scope
7. Select exactly ONE next implementation goal.
8. Explain why it won.
9. Explain why at least one other serious high-priority candidate lost.
10. Report non-code requirements separately when their status cannot be
    established from Assets/.
11. Keep every candidate goal to the smallest coherent implementation slice
    that produces independently testable behavior. Do not bundle multiple
    distinct missing required features into one candidate merely to increase
    unlock value or make that candidate appear strategically dominant.
12. Before choosing a winner, cross-check all selection/rejection prose against
    the final candidate_goals values. Never make an "only/all/every/highest/
    same/equal" claim that the structured candidates do not support. If the
    winner is weaker than a serious alternative on a readiness/risk dimension,
    acknowledge that tradeoff explicitly instead of erasing it.

Do NOT hard-code Mana, spells, enemies, doors, death/restart, world building,
the dungeon floor, PixelLab usage, or any other feature as the winner.

The model must independently select the goal from the GDD, the actual state of
Assets/, the real dependency graph, and the explicitly supplied approved
development-capability context.

============================================================
PIXELLAB DEVELOPMENT-CAPABILITY CONTEXT
============================================================

PixelLab is connected to the Claude Code development environment through MCP.

For the ANALYSIS phase, PixelLab must be treated as an approved
DEVELOPMENT-TIME RESOURCE-ACQUISITION OPTION.

The analysis agent does NOT get PixelLab MCP tools and does NOT generate art.
It is only allowed to reason about what PixelLab could make available to a
later implementation/action phase.

PixelLab capabilities relevant to No Safe Circle include:

- isometric pixel-art tiles
- connectable isometric terrain/path tiles
- isometric building kits
- isometric floor pieces
- connectable wall pieces
- doorway art
- pillars
- staircase art
- transparent map objects / props
- 4-directional or 8-directional pixel-art characters
- character animation
- supporting 2D/pixel-art images

The current game direction is a 2.5D isometric presentation inspired by early
isometric action/RPG games. Therefore PixelLab's isometric environment and
directional sprite capabilities may materially affect the feasibility of goals
that otherwise appear blocked by missing art.

However, PixelLab availability does NOT mean that:

- an asset already exists locally
- an asset is already imported into Unity
- a prefab already exists
- a Tilemap or room layout already exists
- sprite sorting is configured
- collision is configured
- navigation/pathfinding is configured
- doorway traversal works
- the five-space dungeon already exists
- integration has been completed
- generated art automatically satisfies every GDD requirement

The agent must distinguish:

LOCAL RESOURCE READINESS:
Does the required resource already exist in Assets/?

RESOURCE ACQUISITION READINESS:
If the resource does not exist locally, can an approved development-time tool
such as PixelLab realistically produce the needed resource?

INTEGRATION READINESS:
Even if the resource can be acquired, can it be integrated and meaningfully
validated in the actual game context now?

Example:

A missing isometric floor-art dependency may have:

local resource readiness:
missing

resource acquisition readiness:
high

because PixelLab can generate compatible isometric tiles/building pieces.

But integration readiness may still be medium or low if Unity-side room
construction, sorting, collisions, prefabs, navigation, encounters, or doorway
systems are not ready.

Do not treat "PixelLab can generate the art" as equivalent to "the feature is
implemented."

Do not automatically favor goals that can use PixelLab.
PixelLab is one available capability to consider, not a priority instruction.

============================================================
RESOURCE ACQUISITION READINESS
============================================================

Every candidate goal must include:

resource_acquisition_readiness

Allowed values:

- high
- medium
- low

Also include:

resource_acquisition_reasoning

This is a required explanatory string.

Definition:

HIGH:
- Missing external resources can realistically be acquired using approved
  development capabilities such as PixelLab, OR
- the candidate requires no meaningful missing external resources.

MEDIUM:
- An approved tool can acquire only PART of the genuinely required external
  resource set, OR
- there is meaningful uncertainty that the approved tool can produce the
  required resource type/quality at all.

LOW:
- No approved capability currently resolves the important missing external
  resource dependency, OR
- the required external resource type is outside the capability of the
  approved tool.

CRITICAL SCORING RULE:

resource_acquisition_readiness measures ACQUISITION ONLY.

Do NOT lower resource_acquisition_readiness because Unity-side implementation
or integration work remains after the resource is acquired.

The following are NOT reasons to lower resource_acquisition_readiness:

- creating Unity Tile assets
- creating or configuring Tilemaps
- creating prefabs
- importing/configuring sprites
- sprite sorting
- collision setup
- navigation/pathfinding setup
- room layout authoring
- doorway integration
- encounter placement
- code integration
- Play Mode validation

Those belong in implementation_scope, integration_readiness, risk_and_size,
dependencies, or reasoning as appropriate.

Example:

If required isometric floor/wall/prop art is missing locally, and PixelLab can
realistically generate those exact external art resources, then
resource_acquisition_readiness should normally be HIGH even if Tilemap
construction, collision, sorting, navigation, and room integration are still
substantial work.

For art-dependent candidates, resource_acquisition_reasoning must say
specifically whether PixelLab is relevant and why.

For code-only candidates that do not require missing external art/resources,
say that explicitly instead of inventing a PixelLab dependency.

============================================================
PREREQUISITE SEMANTICS
============================================================

Keep prerequisites and implementation scope logically consistent.

A prerequisite is something that must ALREADY EXIST before the candidate goal
can begin.

Therefore:

- If a true pre-existing prerequisite does not currently exist in Assets/,
  prerequisites_ready must be false.
- If the candidate itself will create/configure/build something as part of the
  work, that thing is NOT a pre-existing prerequisite. Put it in
  implementation_scope.
- This rule applies to infrastructure and engine setup too. If a candidate will
  create/configure/bake a NavMesh, create a Tilemap/Grid, configure a camera,
  create a prefab, add navigation components, or create other required
  infrastructure as part of its own implementation, the current absence of
  that thing must NOT by itself make prerequisites_ready false.
- If the candidate is expected to ACQUIRE a missing external resource during
  implementation using an approved capability such as PixelLab, that resource
  is also NOT a pre-existing prerequisite. Put the acquisition step in
  implementation_scope and evaluate its feasibility under
  resource_acquisition_readiness.
- Do not mark prerequisites_ready false merely because PixelLab-generated art
  or another approved-acquisition resource is not already present in Assets/
  when acquiring that resource is part of the candidate's own implementation.
- The dependencies list may contain both true pre-existing dependencies and
  relationships/work the candidate itself will create or acquire.
  prerequisites_ready evaluates ONLY the true pre-existing dependencies.
- Never use the absence of candidate-created or candidate-acquired work to set
  prerequisites_ready false.
- Do not list a genuinely pre-existing prerequisite as missing and then also
  mark prerequisites_ready true.

Before finalizing every candidate, perform this consistency check:

1. Read every item in dependencies.
2. Classify each item mentally as one of:
   - PRE-EXISTING: must already exist before the candidate can start.
   - CREATED-IN-GOAL: the candidate itself will create/configure/build it.
   - ACQUIRED-IN-GOAL: the candidate itself will obtain it through an approved
     resource capability such as PixelLab.
3. For PRE-EXISTING items only, verify they exist now. If any required
   pre-existing item is absent, prerequisites_ready = false.
4. CREATED-IN-GOAL items belong in implementation_scope and do not reduce
   prerequisites_ready merely because they are absent today.
5. ACQUIRED-IN-GOAL items belong in implementation_scope and are scored under
   resource_acquisition_readiness; they do not reduce prerequisites_ready
   merely because they are absent today.

PIXELLAB EXAMPLE — WRONG:

- dependency/prerequisite: "PixelLab-generated isometric floor tiles"
- local state: tiles do not exist yet
- prerequisites_ready: false

when the candidate itself is supposed to generate/acquire those tiles.

PIXELLAB EXAMPLE — RIGHT:

- implementation_scope includes: generate/acquire isometric floor/wall tiles
  using PixelLab, import them, create Unity Tile assets, and configure the
  Tilemap
- resource_acquisition_readiness: high if PixelLab can realistically provide
  the required art
- prerequisites_ready is determined only from resources/systems that must
  already exist before that work can start

NAVMESH EXAMPLE — WRONG:

Candidate: "Melee Enemy Chase-and-Attack Prototype"

- implementation_scope says the candidate will configure/bake the NavMesh
- dependencies also mention "a baked NavMesh"
- analysis observes no baked NavMesh currently exists
- prerequisites_ready: false

This is contradictory because the candidate itself is responsible for creating
the NavMesh.

NAVMESH EXAMPLE — RIGHT:

Candidate: "Melee Enemy Chase-and-Attack Prototype"

- PRE-EXISTING dependencies might include:
  - existing walkable floor geometry
  - existing Player GameObject / target transform
  - existing PlayerHealth.TakeDamage entry point
- implementation_scope includes:
  - add/configure navigation components
  - configure/bake the NavMesh
  - implement NavMeshAgent chase behavior
  - implement close-range attack behavior
- prerequisites_ready may be true if those true pre-existing dependencies are
  already present
- the candidate may still score lower because its implementation is larger,
  riskier, or has lower prototype/integration readiness

============================================================
GDD TIMELINE / ORDERING FLEXIBILITY
============================================================

The GDD may contain dates, week numbers, development phases, milestone
ordering, or an example implementation schedule.

Treat those timeline references as planning context, NOT as hard priority
rules.

The goal-selection agent must NOT choose a feature merely because the GDD says
it was planned for an earlier week, phase, or date.

Likewise, it must NOT reject or delay a feature merely because the GDD places
it in a later week, phase, or date.

Current repository state is the source of truth for implementation ordering.

Goal ordering must be driven primarily by:

- actual dependencies
- prerequisite readiness
- resource acquisition readiness
- prototype readiness
- integration readiness
- unlock value
- implementation risk and size
- required-vs-stretch scope

A GDD timeline may be mentioned as historical/planning context, but it must not
override evidence from the current codebase.

Only treat GDD ordering as a real dependency when the GDD explicitly states a
mechanical, technical, or content dependency such as "A requires B to exist"
or equivalent language.

Week numbers, dates, phases, milestone labels, and development-plan ordering by
themselves are NOT dependencies.

The same rule applies to AI Architecture / workflow descriptions:

- Agent ownership boundaries may establish WHO owns work.
- Agent workflow descriptions may establish that two tasks can be separated or
  performed independently.
- But an agent-role sequence, example workflow sequence, or statement that one
  agent commonly works before another is NOT priority evidence by itself.
- Do not select or reject a candidate because "the GDD workflow does this
  first" unless the text also establishes a real mechanical, technical, or
  content prerequisite.

Architectural separability may support prototype readiness.
Workflow ordering must not be converted into implementation priority.

============================================================
NON-NEGOTIABLE PERMISSION REQUIREMENTS
============================================================

The generated goal_agent.py must invoke the ANALYSIS Claude agent with these
permission concepts:

--permission-mode dontAsk
--tools "Read,Glob,Grep"
--allowedTools "Read,Glob,Grep"
--disallowedTools "Edit,Write,mcp__*"

Do NOT omit --allowedTools.

The ANALYSIS agent itself must remain read-only.

It must never receive:

- Write
- Edit
- Bash
- PixelLab MCP tools
- any MCP tool

It must not change any file and must not spend PixelLab generations.

============================================================
GOAL_AGENT.PY REQUIREMENTS
============================================================

Create /workspace/GoalOrientedAgent/goal_agent.py.

Keep it straightforward and runnable using the same Docker/Claude environment
already used by this repository.

The Python program must:

1. Enforce the analysis-boundary concept in the generated prompt/schema
   design. The later ANALYSIS Claude must NEVER Read, Glob, or Grep:
   - AgentCrew/
   - DynamicContentPipeline/

   Those directories are completely excluded from Assignment 5 gameplay
   analysis, not merely excluded as gameplay evidence.

2. Include a defensive post-output boundary check in goal_agent.py.

   After Claude returns structured_output but BEFORE saving
   goal_analysis.json, serialize the structured output and fail the run if it
   references:
   - AgentCrew/
   - DynamicContentPipeline/

   This check is defense-in-depth. The analysis prompt is still the primary
   boundary instruction.

3. In the structured output schema, candidate_goals.scope must be constrained
   to exactly one of:
   - required
   - stretch

   Implement candidate_goals.scope as a JSON Schema enum.

4. Add a separate candidate_goals.implementation_scope string field.

   Use implementation_scope to describe what code/files/systems would likely
   be involved in implementing the candidate.

5. Add candidate_goals.resource_acquisition_readiness.

   It must be a JSON Schema enum containing exactly:
   - high
   - medium
   - low

6. Add candidate_goals.resource_acquisition_reasoning.

   It must be a required string field explaining whether missing resources can
   be obtained and whether PixelLab is relevant.

7. Add candidate_goals.prototype_readiness.

   It must be a JSON Schema enum containing exactly:
   - high
   - medium
   - low

8. Add candidate_goals.integration_readiness.

   It must be a JSON Schema enum containing exactly:
   - high
   - medium
   - low

9. The generated analyze.md must enforce focused candidate-goal sizing:
   - each candidate is one coherent, independently testable implementation slice
   - supporting plumbing may be included only when necessary for that slice
   - multiple independently testable missing features must not be bundled merely
     to inflate unlock value or make a candidate look stronger

10. Handle non-code required deliverables separately from gameplay-code gaps.

   The schema must include a top-level field:

   non_code_requirements

   Each entry must contain:
   - feature
   - status
   - evidence

   non_code_requirements.status must be constrained to:
   - confirmed
   - not_assessable_from_assets

   Do NOT classify "not assessable from Assets/" as "missing".

   Non-code requirements that cannot be assessed from gameplay-code evidence
   must NOT become candidate coding goals.

10. Locate the repo root based on __file__.

11. Load GoalOrientedAgent/prompts/analyze.md.

12. Invoke Claude Code non-interactively.

13. Run from the repository root so relative paths in the prompt resolve
    correctly.

14. Use the exact read-only permission rules specified above:

    --permission-mode dontAsk
    --tools "Read,Glob,Grep"
    --allowedTools "Read,Glob,Grep"
    --disallowedTools "Edit,Write,mcp__*"

    The analysis Claude must not receive Bash or any MCP tool.

15. Request structured JSON output with --json-schema.

16. Parse Claude's JSON response.

17. Extract structured_output.

18. Run the defensive excluded-path check before saving the output.

19. Save structured_output itself to:

    GoalOrientedAgent/outputs/goal_analysis.json

20. Print a readable terminal summary including:
    - how many gameplay-code required features were evaluated
    - which gameplay features are missing or partial
    - any non-code requirements reported separately
    - how many candidate goals were considered
    - the selected goal
    - why it was selected
    - its dependencies
    - its resource acquisition readiness
    - its prototype readiness
    - its integration readiness
    - rejected high-priority alternatives

21. Handle:
    - nonzero Claude exit codes
    - invalid JSON
    - missing structured_output
    - timeouts
    - excluded-path references in returned analysis

22. Allow model, timeout, and max-turn overrides through environment variables.

    The generated goal_agent.py must include an environment-variable-backed
    max-turn setting, for example:

    MAX_TURNS = int(os.environ.get("GOAL_AGENT_MAX_TURNS", "40"))

    and must pass that value to Claude using:

    --max-turns

    Do not rely on timeout alone; preserve both a wall-clock timeout and an
    agent-turn ceiling.

The structured output schema must contain at least:

- desired_state
- current_state
- gaps
- non_code_requirements
- candidate_goals
- selected_goal
- selection_reason
- dependencies
- evidence (an ARRAY of concrete supporting evidence strings)
- rejected_high_priority_alternatives

Use strict JSON Schema definitions where appropriate.

Do not regress previously established schema structure or reasoning semantics while adding new fields.
In particular:
- Do not treat a resource the candidate will acquire itself (including
  PixelLab-generated art) as a pre-existing prerequisite.
- Do not treat infrastructure the candidate will create/configure itself
  (including a NavMesh bake, Tilemap/Grid setup, camera configuration, prefab
  creation, or navigation component setup) as a pre-existing prerequisite.
- prerequisites_ready must be determined only from dependencies that truly
  must exist before implementation begins.
- selection_reason and rejected_high_priority_alternatives must agree with the
  final candidate_goals prerequisite/readiness/risk values.
- Comparative claims such as "only", "all", "every", "highest", "lowest",
  "same", or "equal" must never contradict the structured candidate values.
- `evidence` is a top-level ARRAY of strings, not a string.
- `candidate_goals` keeps minItems: 3.
- `rejected_high_priority_alternatives` keeps minItems: 1.

Required schema behavior:

desired_state:
- source
- required_features

current_state:
- source
- implemented_summary
- files_reviewed

gaps entries:
- feature
- status
- evidence

gaps.status must be constrained to:
- implemented
- partial
- missing

non_code_requirements entries:
- feature
- status
- evidence

non_code_requirements.status must be constrained to:
- confirmed
- not_assessable_from_assets

candidate_goals entries:
- name
- description
- scope
- implementation_scope
- dependencies
- prerequisites_ready
- resource_acquisition_readiness
- resource_acquisition_reasoning
- prototype_readiness
- integration_readiness
- systems_unlocked
- risk_and_size
- reasoning

Dependency/prerequisite semantics for generated analyze.md:

- dependencies may describe PRE-EXISTING, CREATED-IN-GOAL, and
  ACQUIRED-IN-GOAL relationships.
- prerequisites_ready must be determined ONLY from PRE-EXISTING dependencies.
- Missing CREATED-IN-GOAL infrastructure (including a NavMesh the candidate
  itself will bake/configure) must not make prerequisites_ready false.
- Missing ACQUIRED-IN-GOAL resources must be evaluated under
  resource_acquisition_readiness rather than prerequisite readiness.

candidate_goals.scope must be constrained with an enum to:
- required
- stretch

candidate_goals.resource_acquisition_readiness must be constrained with an
enum to:
- high
- medium
- low

candidate_goals.prototype_readiness must be constrained with an enum to:
- high
- medium
- low

candidate_goals.integration_readiness must be constrained with an enum to:
- high
- medium
- low

JSON SCHEMA CARDINALITY REQUIREMENTS:

Do not rely only on prompt wording for minimum collection sizes.

candidate_goals:
- type must be "array"
- minItems must be 3

rejected_high_priority_alternatives:
- type must be "array"
- minItems must be 1

These minItems constraints are NON-NEGOTIABLE.

The prompt and JSON Schema must both enforce these minimum counts.

selected_goal:
- name
- description

evidence:
- type must be "array"
- items must be strings
- this is a top-level list of concrete supporting evidence used for the selected goal

The generated JSON Schema must contain the equivalent of:

"evidence": {
    "type": "array",
    "items": {"type": "string"}
}

Do not collapse evidence into one long string.

rejected_high_priority_alternatives entries:
- name
- reason_rejected

============================================================
ANALYZE.MD REQUIREMENTS
============================================================

Create /workspace/GoalOrientedAgent/prompts/analyze.md.

It must clearly tell the analysis model:

- It is an ANALYSIS-ONLY goal-selection agent.
- It may use only Read, Glob, and Grep.
- It must not write, edit, create, delete, or otherwise modify anything.
- It must not call PixelLab or any MCP tool.
- PixelLab availability is supplied as approved development-capability context
  only.
- The GDD is the desired state.
- Assets/ is the current gameplay implementation.
- Claims about implementation must be grounded in actual
  files/classes/methods observed under Assets/.
- A filename alone is not enough evidence; the model should read relevant
  files.
- Required scope must be distinguished from stretch goals and explicitly
  excluded systems.
- Every REQUIRED gameplay-code feature must be classified implemented,
  partial, or missing.
- Missing evidence must be reported as missing rather than guessed.
- Before selecting a winner, it must compare the FINAL candidate_goals values
  against one another and ensure selection_reason and
  rejected_high_priority_alternatives agree with those structured values.
- It must not make unsupported comparative/exclusivity claims such as
  "only candidate", "all candidates", "every candidate", "none of the other
  candidates", "highest", "lowest", "same", "equal", or equivalent wording.
- If the winner has a worse readiness score or higher implementation risk than
  a serious alternative, selection_reason must explicitly acknowledge that
  disadvantage and explain why the winner's other advantages outweigh it.
- It must not dismiss a readiness dimension as non-discriminating if the
  candidate_goals values on that dimension actually differ.

REPOSITORY INSPECTION BOUNDARY:

The analysis model may inspect only these repository areas for Assignment 5
reasoning:

1. Docs/GDD/No_Safe_Circle_GDD.md
2. Assets/

It must NEVER Read, Glob, or Grep:

- AgentCrew/
- DynamicContentPipeline/

The Assignment 5 implementation-state analysis must be derivable from:

GDD + Assets/

alone.

APPROVED DEVELOPMENT CAPABILITY CONTEXT:

The prompt must explicitly provide the PixelLab capability summary given in
this bootstrap prompt.

The prompt must explain that PixelLab:

- is connected and approved for development-time asset generation
- is relevant to 2.5D isometric environment art and directional sprite art
- can affect resource acquisition readiness
- does not make local assets already exist
- does not make Unity integration complete
- must not be called during the analysis phase

The model may use this supplied capability context only when evaluating
resource_acquisition_readiness.

GAMEPLAY VS. NON-CODE REQUIREMENTS:

The GDD may contain required deliverables that cannot be reliably assessed by
scanning gameplay files under Assets/.

For example:

- a Windows build
- packaging/build-target requirements

These requirements must still be acknowledged because they are part of the
desired state.

However:

- Do not classify a requirement as missing merely because its status cannot be
  established from Assets/.
- Report such requirements separately through non_code_requirements.
- Use status "not_assessable_from_assets" when appropriate.
- Do not make an unassessable packaging/build requirement a candidate coding
  goal.

CANDIDATE GOAL REQUIREMENT:

Do NOT create three candidate goals for every gap.

From all gameplay features classified as missing or meaningfully partial,
propose at least THREE strong candidate next goals TOTAL.

CANDIDATE COHERENCE / SIZE RULE:

Each candidate must be the smallest coherent implementation slice that
produces independently testable behavior.

Do NOT bundle multiple independently testable missing features into one large
candidate merely because:

- they belong to the same GDD system
- they share an agent owner
- they would eventually interact
- bundling them increases systems_unlocked
- bundling them makes the candidate appear more strategically important

A candidate may include supporting plumbing that is genuinely necessary to
make its ONE behavior testable. Supporting plumbing is not permission to absorb
a second independent feature.

When deciding whether a candidate is too broad, ask:

"Could a developer reasonably implement, test, review, and commit this as one
focused Assignment 5 feature slice?"

If the answer is no, split the candidate into smaller goals before comparing
candidates.

Do not reward a candidate for unlock value that comes primarily from bundling
several otherwise-separate missing features together.

For every candidate:

- scope must mean ONLY:
  - required
  - stretch

- implementation_scope must separately describe the likely files, components,
  or systems involved.

- resource_acquisition_readiness must be:
  - high
  - medium
  - low

- resource_acquisition_reasoning must explain:
  - whether an important resource is missing locally
  - whether an approved capability can acquire it
  - whether PixelLab is relevant
  - what remains to be integrated even if the resource can be acquired

- prototype_readiness must be:
  - high
  - medium
  - low

- integration_readiness must be:
  - high
  - medium
  - low

PREREQUISITE CONSISTENCY RULE:

A prerequisite must be something that ALREADY EXISTS before work on the
candidate starts.

Before scoring prerequisites_ready, classify every item in dependencies as:

1. PRE-EXISTING — must already exist before this candidate can begin.
2. CREATED-IN-GOAL — this candidate will create/configure/build it.
3. ACQUIRED-IN-GOAL — this candidate will obtain it through an approved
   capability such as PixelLab.

Then apply these rules:

- Only PRE-EXISTING items are allowed to make prerequisites_ready false.
- If a required PRE-EXISTING item is absent in Assets/, prerequisites_ready
  must be false.
- CREATED-IN-GOAL work belongs in implementation_scope. Its current absence is
  expected and must NOT lower prerequisites_ready.
- ACQUIRED-IN-GOAL resources belong in implementation_scope and are evaluated
  under resource_acquisition_readiness. Their current absence must NOT lower
  prerequisites_ready.
- This rule applies to engine/infrastructure work too. If the candidate itself
  will configure/bake a NavMesh, create a Tilemap/Grid, configure a camera,
  create a prefab, add navigation components, or create comparable
  infrastructure, that missing infrastructure is CREATED-IN-GOAL, not a
  pre-existing prerequisite.

Never claim both:
- "this genuinely pre-existing prerequisite does not exist"
and
- "prerequisites_ready = true"

for the same candidate.

PIXELLAB / RESOURCE ACQUISITION EXAMPLE:

For a candidate such as "Isometric Tilemap Floor & Wall Base Layer for One
Room":

- Missing isometric floor/wall art may be acquired during the candidate using
  approved PixelLab capability.
- Therefore that art should normally be described in implementation_scope, not
  treated as a pre-existing prerequisite.
- If PixelLab can realistically generate the complete needed art resource set,
  resource_acquisition_readiness may be HIGH.
- prerequisites_ready should then be based only on things that truly must
  already exist before the candidate starts.
- The candidate may still have MEDIUM/LOW prototype or integration readiness,
  and higher risk/size, because importing sprites, creating Unity Tile assets,
  configuring Tilemaps, camera setup, sorting, collision, navigation, and room
  authoring are still substantial implementation/integration work.

NAVMESH / CREATED-INFRASTRUCTURE EXAMPLE:

For a candidate such as "Melee Enemy Chase-and-Attack Prototype":

- If implementation_scope includes configuring/baking the NavMesh, then the
  missing NavMesh is CREATED-IN-GOAL.
- Do NOT treat that missing NavMesh as a pre-existing prerequisite.
- True PRE-EXISTING prerequisites might instead be an existing walkable floor,
  an existing player target, and an existing damage entry point such as
  PlayerHealth.TakeDamage.
- If those true pre-existing requirements exist, prerequisites_ready may be
  true even though no NavMesh is currently baked.
- The candidate can still legitimately lose because it is larger, riskier, or
  has lower prototype/integration readiness.

Evaluate every candidate using:

- Dependencies
- Prerequisite readiness
- Resource acquisition readiness
- Prototype readiness
- Integration readiness
- Unlock value
- Implementation risk and size
- Required-vs-stretch scope

PROTOTYPE READINESS VS. INTEGRATION READINESS:

Treat these as separate concepts.

Prototype readiness asks:

"Can this feature be implemented and meaningfully tested at all using the
current project state, even in a limited prototype environment?"

Integration readiness asks:

"Can this feature be integrated and meaningfully validated in the actual game
context described by the GDD?"

For example, a feature may have HIGH prototype readiness because a primitive
test room is enough to exercise its basic behavior, while having LOW
integration readiness because the real multi-room dungeon, doorway traversal,
encounter context, or other final-game environment does not exist yet.

If a candidate with lower integration readiness than prototype readiness is
selected, selection_reason must explicitly explain why that tradeoff is
acceptable.

RESOURCE ACQUISITION VS. INTEGRATION:

Treat these as separate concepts too.

resource_acquisition_readiness answers ONLY:
"Can the missing external resource itself be obtained?"

integration_readiness answers:
"After the resource is obtained, can the candidate be integrated and
meaningfully validated in the actual game now?"

Therefore, do NOT lower resource_acquisition_readiness because Tilemap
authoring, prefab creation, sprite importing, sorting, collision, navigation,
room layout, encounters, doorway integration, code work, or validation remain.

A feature may have HIGH resource acquisition readiness because PixelLab can
generate compatible isometric art, while having MEDIUM or LOW integration
readiness because Unity-side room authoring, collision, navigation, sprite
sorting, prefabs, encounters, or doorway integration are not ready.

Do not collapse these into one score.

GDD TIMELINE / ORDERING RULE:

The GDD may mention weeks, dates, development phases, milestone order, or an
example implementation schedule.

Do NOT treat those timeline references as mandatory implementation order.

Do NOT give a candidate higher priority merely because it appears in an
earlier week or phase.

Do NOT give a candidate lower priority merely because it appears in a later
week or phase.

The current state of Assets/, actual dependency graph, resource acquisition
readiness, prototype readiness, and integration readiness determine what
should be built next.

Only treat GDD ordering as a dependency when the GDD explicitly describes a
real mechanical, technical, or content dependency.

Week/date/phase ordering alone is not dependency evidence.

Agent-role ownership and workflow examples in the GDD are also NOT
implementation-priority evidence by themselves.

You may use an agent ownership statement to understand architectural
boundaries or whether work is separable, but you must NOT reason:

"Agent/system A appears before Agent/system B in the workflow, therefore A
should be implemented first."

Likewise, example workflow sequences do not establish priority unless they
also describe a real mechanical, technical, or content prerequisite.

CROSS-CANDIDATE CONSISTENCY CHECK:

Before selecting the winner, treat the FINAL candidate_goals objects as the
source of truth for every comparative statement.

Build this mental comparison table:

candidate | prerequisites_ready | resource_acquisition_readiness |
prototype_readiness | integration_readiness | risk_and_size |
systems_unlocked | scope

Then cross-check every comparison you intend to make.

Rules:

- Never say "only candidate", "the only candidate", "all candidates",
  "every candidate", "none of the other candidates", "highest", "lowest",
  "same", "equal", "comparably high", or equivalent wording unless the final
  candidate_goals values actually support it.
- If you claim a candidate is the only one creating a wholly absent required
  system, check every other candidate first. Another candidate whose target
  feature is classified `missing` may also represent a wholly absent system.
- If you claim a readiness dimension does not differentiate the candidates,
  verify the exact readiness values for every candidate. If those values
  differ, that dimension IS a differentiator and must be discussed honestly.
- If the winner has lower integration/prototype/resource readiness than a
  serious alternative, state that disadvantage explicitly and explain why
  another factor such as unlock value, dependency position, or scope/risk
  still makes the winner preferable.
- If the winner has higher implementation risk/size than a serious
  alternative, acknowledge that tradeoff rather than describing the winner as
  equally low-risk.
- rejected_high_priority_alternatives must use the same prerequisite,
  readiness, dependency, and risk facts already present in the corresponding
  candidate_goals entry.
- Do not change candidate scores merely to make a preferred winner easier to
  justify. If the final comparison favors another candidate, choose that
  candidate instead.

Concrete regression example:

If the final candidate values are:

- Movement integration_readiness = medium
- Enemy integration_readiness = low
- Door integration_readiness = medium
- Mana integration_readiness = low
- Death/Restart integration_readiness = medium

then it is FALSE to say "every candidate has low integration readiness" or
that integration readiness does not distinguish the candidates.

Likewise, if Mana is classified as fully `missing`, do not claim Enemy is
"the only candidate that stands up an entirely absent required system" unless
you establish a concrete distinction that makes that statement true.

A valid winner may still have a weaker score on one dimension. The correct
reasoning is to acknowledge the weaker dimension and explain the tradeoff.

SELECTING THE WINNER:

Compare the candidates against one another.

Select exactly ONE winner.

The selection must not be predetermined.

Do not default to:

- Mana
- spells
- enemies
- doors
- death/restart
- world building
- the dungeon floor
- PixelLab-related work
- or any other specific feature

The winner must follow from the actual GDD requirements, current Assets/
implementation, real dependencies, and approved resource capabilities.

A different project state should be able to produce a different selected goal.

Before writing selected_goal, selection_reason, and
rejected_high_priority_alternatives, perform the cross-candidate consistency
check above one final time.

selection_reason must be factually consistent with the final candidate_goals
objects. A comparative claim that contradicts those structured values is a
reasoning failure and must be corrected before returning the result.

All implementation evidence must come from the GDD and Assets/.

============================================================
OUTPUT RESPONSIBILITY
============================================================

The Claude analysis agent does NOT write goal_analysis.json itself.

TOP-LEVEL EVIDENCE FORMAT:

The structured output field `evidence` must be an ARRAY of strings, with each
string containing one concrete supporting fact/file/class/method/grep result
used to justify the selected goal.

Do not concatenate all evidence into one string.

The analysis agent:

1. Reads the GDD.
2. Reads/scans Assets/.
3. Reasons about gaps, resources, readiness, and priorities.
4. Returns structured JSON through --json-schema.

The Python orchestrator:

1. Receives Claude's structured_output.
2. Runs the defensive excluded-path check.
3. Saves that structured output to:
   GoalOrientedAgent/outputs/goal_analysis.json

Therefore analyze.md must NOT instruct the read-only Claude agent to save,
create, or write any file.

============================================================
MANDATORY SELF-VALIDATION
============================================================

After creating goal_agent.py and prompts/analyze.md, READ BOTH FILES AGAIN
before finishing.

Verify every item below:

[ ] goal_agent.py uses --permission-mode dontAsk for the analysis Claude invocation.
[ ] goal_agent.py restricts analysis tools to Read,Glob,Grep.
[ ] goal_agent.py explicitly pre-approves Read,Glob,Grep with --allowedTools.
[ ] goal_agent.py explicitly disallows Edit,Write,mcp__*.
[ ] The analysis Claude cannot modify files.
[ ] The analysis Claude is not given Bash.
[ ] The analysis Claude is not given PixelLab MCP or any MCP tool.
[ ] analyze.md never tells the read-only analysis Claude to save or create a file.
[ ] analyze.md requires at least three candidate goals TOTAL, not three per missing feature.
[ ] analyze.md does not hard-code any predetermined winner.
[ ] The GDD is treated as the desired state.
[ ] Assets/ is treated as the current state.
[ ] The analysis prompt explicitly forbids Read, Glob, and Grep access to AgentCrew/ and DynamicContentPipeline/.
[ ] goal_agent.py performs a defensive returned-output check for AgentCrew/ and DynamicContentPipeline/ before saving.
[ ] candidate_goals.scope is a JSON Schema enum containing only "required" and "stretch".
[ ] candidate_goals.implementation_scope is a separate string field.
[ ] candidate_goals.resource_acquisition_readiness exists and is constrained to "high", "medium", or "low".
[ ] candidate_goals.resource_acquisition_reasoning is a required string field.
[ ] candidate_goals.prototype_readiness exists and is constrained to "high", "medium", or "low".
[ ] candidate_goals.integration_readiness exists and is constrained to "high", "medium", or "low".
[ ] candidate_goals has JSON Schema minItems: 3.
[ ] rejected_high_priority_alternatives has JSON Schema minItems: 1.
[ ] analyze.md clearly distinguishes resource acquisition readiness from local resource existence.
[ ] analyze.md clearly distinguishes resource acquisition readiness from integration readiness.
[ ] analyze.md says Unity-side integration work must NOT lower resource_acquisition_readiness when the missing external resource itself is acquirable.
[ ] analyze.md clearly distinguishes prototype readiness from integration readiness.
[ ] analyze.md defines a prerequisite as something that must already exist before the candidate begins.
[ ] analyze.md requires prerequisites_ready=false when a required pre-existing prerequisite is missing.
[ ] analyze.md requires work created by the candidate itself to be placed in implementation_scope rather than treated as a missing prerequisite.
[ ] analyze.md says resources acquired DURING the candidate through approved tools such as PixelLab belong in implementation_scope, not as pre-existing prerequisites.
[ ] analyze.md says missing PixelLab-generated art alone must not force prerequisites_ready=false when the candidate itself is responsible for acquiring that art.
[ ] analyze.md includes an explicit Tilemap/PixelLab example showing high resource acquisition readiness can coexist with true prerequisites_ready while prototype/integration readiness remains lower.
[ ] analyze.md classifies dependencies as PRE-EXISTING, CREATED-IN-GOAL, or ACQUIRED-IN-GOAL before scoring prerequisites_ready.
[ ] analyze.md says only PRE-EXISTING dependencies may make prerequisites_ready=false.
[ ] analyze.md explicitly says a NavMesh the candidate itself will configure/bake is CREATED-IN-GOAL and must not make prerequisites_ready=false merely because it does not exist yet.
[ ] analyze.md includes an explicit Melee Enemy/NavMesh example showing that missing candidate-created navigation infrastructure affects implementation scope/risk/readiness, not pre-existing prerequisite readiness.
[ ] analyze.md requires a final cross-candidate comparison of the completed candidate_goals values before selecting a winner.
[ ] analyze.md prohibits unsupported exclusivity/ranking claims such as "only candidate", "all candidates", "every candidate", "highest", "lowest", "same", or "equal".
[ ] analyze.md explicitly forbids claiming a readiness dimension is non-discriminating when the final candidate values on that dimension differ.
[ ] analyze.md requires selection_reason to acknowledge a winner's worse readiness score or higher risk when a serious alternative scores better on that dimension.
[ ] analyze.md requires rejected_high_priority_alternatives to remain consistent with the corresponding candidate_goals prerequisite/readiness/risk facts.
[ ] analyze.md includes the concrete regression examples: mixed integration-readiness values cannot be described as all LOW, and a fully missing Mana system prevents unsupported claims that Enemy is the only wholly absent system.
[ ] analyze.md requires candidate goals to be focused, independently testable implementation slices rather than bundles of multiple missing features.
[ ] analyze.md explicitly identifies PixelLab as an approved development-time capability.
[ ] analyze.md explicitly says PixelLab is not called during analysis.
[ ] analyze.md explains PixelLab's relevant isometric-tile/building-kit/map-object/directional-sprite capabilities.
[ ] analyze.md does not claim PixelLab makes Unity prefabs, collision, navigation, sorting, or room integration automatically complete.
[ ] analyze.md explicitly says GDD week/date/phase ordering is planning context, not a hard priority rule.
[ ] analyze.md says current code state and actual dependencies outrank GDD timeline ordering.
[ ] analyze.md says GDD agent-role/workflow sequence is not priority evidence unless it expresses a real dependency.
[ ] analyze.md permits agent ownership to establish architectural boundaries/separability without converting workflow order into priority.
[ ] Non-code requirements that cannot be assessed from Assets/ are stored separately.
[ ] "not assessable from Assets/" is never incorrectly classified as a missing gameplay gap.
[ ] Non-code requirements that cannot be assessed from Assets/ are not candidate coding goals.
[ ] Exactly one next implementation goal must be selected.
[ ] At least one serious rejected alternative must be explained.
[ ] goal_agent.py defines an environment-variable-backed MAX_TURNS value.
[ ] goal_agent.py passes MAX_TURNS to Claude through --max-turns.
[ ] goal_agent.py keeps a separate wall-clock timeout as well as --max-turns.
[ ] The top-level evidence field is a JSON Schema array of strings, not a single string.
[ ] analyze.md explicitly requires evidence to be returned as an array of concrete supporting evidence strings.
[ ] The Python orchestrator saves structured_output to outputs/goal_analysis.json.
[ ] No Unity files were modified.
[ ] No AgentCrew files were modified.
[ ] No DynamicContentPipeline files were modified.
[ ] The GDD was not modified.

If ANY validation item fails:

1. Correct the generated file.
2. Read both generated files again.
3. Repeat the validation.
4. Do not declare success until every item passes.

When finished, print a short summary of:

- the two files created
- confirmation that the validation checklist passed
- confirmation that PixelLab is represented as capability context only
- confirmation that the analysis agent has no MCP access
- confirmation that no Unity/GDD/prior-assignment files were modified
'@

Write-Host "Launching Claude Code to regenerate the PixelLab-aware Assignment 5 analysis harness..." -ForegroundColor Yellow
Write-Host ""

# Windows has a relatively small process command-line limit. Passing the entire
# bootstrap prompt as the value of "-p" can exceed that limit before Docker even
# starts. Instead, write the long prompt to a short-lived repository file and
# give Claude a tiny command-line prompt telling it to Read that file.
#
# The temporary file is removed in a finally block whether Claude succeeds or
# fails, so it is not intended to become part of the repository.
$BootstrapPromptHostPath = Join-Path $GoalAgentDir ".assignment5-bootstrap-prompt.txt"
$BootstrapPromptContainerPath = "/workspace/GoalOrientedAgent/.assignment5-bootstrap-prompt.txt"

try {
    Set-Content -LiteralPath $BootstrapPromptHostPath -Value $Prompt -Encoding UTF8

    # This outer/bootstrap Claude needs Write because it creates the Assignment 5
    # harness. The generated analysis agent must remain read-only and receive no
    # MCP tools. PixelLab is capability context during analysis, not an action tool.
    #
    # Run through cmd.exe so harmless Docker status text written to stderr does not
    # become a terminating Windows PowerShell NativeCommandError while
    # $ErrorActionPreference is "Stop".
    $BootstrapCommand = 'docker compose run --rm claude claude -p "Read /workspace/GoalOrientedAgent/.assignment5-bootstrap-prompt.txt in full, follow every instruction in it exactly, perform its mandatory self-validation, and complete the requested file generation." --model sonnet --permission-mode dontAsk --tools "Read,Glob,Grep,Write" --allowedTools "Read,Glob,Grep,Write" --disallowedTools "Edit,mcp__*"'

    cmd.exe /c $BootstrapCommand
    $BootstrapExitCode = $LASTEXITCODE
}
finally {
    Remove-Item -Force -ErrorAction SilentlyContinue $BootstrapPromptHostPath
}

if ($BootstrapExitCode -ne 0) {
    throw "Claude setup command failed with exit code $BootstrapExitCode."
}

Write-Host ""
Write-Host "Regeneration completed." -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Run: git status"
Write-Host "  2. Inspect GoalOrientedAgent\goal_agent.py"
Write-Host "  3. Inspect GoalOrientedAgent\prompts\analyze.md"
Write-Host "  4. Do NOT run goal_agent.py until the generated harness has been reviewed."
Write-Host ""
