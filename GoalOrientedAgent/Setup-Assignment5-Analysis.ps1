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
13. Enforce dependency ownership: "can be created" does NOT mean "belongs in
    this goal." CREATED-IN-GOAL is only for small, tightly coupled supporting
    work. Missing substantial or independently testable dependencies remain
    prerequisites or become their own candidate goals.
14. Enforce current-state evidence: builder/factory/setup/editor code proves
    capability to create state, not that the resulting state currently exists.
    Verify actual usable scene/prefab/resource/configuration state before
    calling such a dependency PRE-EXISTING and ready.
15. Enforce FOUNDATION COMPATIBILITY. Existing state is not automatically a
    valid foundation. If the GDD/current gap analysis shows that a controller,
    camera, world representation, navigation layer, scene structure, or other
    foundation is a temporary prototype or materially contradicts the desired
    architecture, treat it as PRESENT-INCOMPATIBLE when a candidate materially
    depends on that behavior/state.
16. Promote blocked prerequisites. When a candidate is blocked by substantial
    missing or incompatible required work that is independently testable, that
    prerequisite must itself be considered in the candidate pool rather than
    merely being reported as a reason another candidate is blocked.
17. Enforce candidate self-decomposition. If the agent's own scope/risk
    reasoning reveals that a candidate contains multiple independently
    testable systems or milestones, it must split that candidate BEFORE the
    comparison. It may not knowingly retain a non-focused candidate.
18. Distinguish HARD prerequisites from SUPPORTING dependencies and
    SHARED/FUTURE relationships. Only a genuine hard prerequisite can block
    readiness. A future interaction or shared interface must not be called a
    hard dependency merely to inflate unlock value.
19. Evaluate architecture-compatible implementation and EXPECTED REWORK RISK.
    Do not reward a fast prototype that materially depends on foundations
    already known to require replacement unless the candidate is sufficiently
    decoupled that the replacement will not cause meaningful rework.
20. Represent winner tradeoffs structurally and have goal_agent.py validate
    them against candidate values before goal_analysis.json is saved.

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

Keep prerequisites, current-state evidence, goal decomposition, and
implementation scope logically consistent.

A prerequisite is something that must ALREADY EXIST in usable project state
before the candidate goal can begin.

CRITICAL RULE — CAN BE CREATED != BELONGS IN THIS GOAL:

A missing dependency may be classified CREATED-IN-GOAL only when it is tightly
scoped supporting work necessary to make the candidate's ONE behavior
testable, and is NOT itself a meaningful independently testable goal.

The fact that the agent is technically capable of creating, configuring,
generating, or baking something does NOT automatically permit that work to be
absorbed into the candidate.

Before classifying missing work as CREATED-IN-GOAL, ask:

1. Could this missing work reasonably be implemented, tested, reviewed, and
   committed as its own focused goal?
2. Is it a substantial reusable system, infrastructure layer, world/content
   milestone, or separately required GDD feature?
3. Is it needed by multiple future systems rather than only as tiny local
   plumbing for this candidate?
4. Would building it materially expand the candidate beyond its single
   independently testable behavior?

If YES to any of these in a meaningful way, do NOT silently absorb the work
into CREATED-IN-GOAL. Treat it as a prerequisite/dependency that is not yet
ready, and consider that missing work as its own candidate goal when
appropriate.

Only small, tightly coupled supporting plumbing may be CREATED-IN-GOAL.

CURRENT-STATE EVIDENCE RULE:

Code that CAN create a resource is not proof that the resource CURRENTLY
EXISTS.

Examples of capability-only evidence include:

- a scene-builder method such as BuildFloor() or BuildWalls()
- a factory method
- a setup/editor script
- a prefab-generation script
- a bake/configuration method
- code that would create a Tilemap, NavMesh, room, prefab, or other object if
  executed

Such code proves construction capability, not current usable state.

To call something PRE-EXISTING and ready, verify the usable project state
itself under Assets/ whenever that state should be serialized/present there:
for example an actual scene object, prefab, Tile asset, imported sprite,
serialized component/configuration, or other concrete artifact/state.

A builder/setup script alone must never satisfy a prerequisite that depends on
the built result.

Therefore:

- If a true prerequisite is not verified as currently usable project state,
  prerequisites_ready must be false.
- If missing work passes the supporting-plumbing test above, it may be
  CREATED-IN-GOAL and belongs in implementation_scope.
- If missing work is independently meaningful/substantial, it remains a
  not-ready prerequisite or becomes its own candidate goal even if the agent
  knows how to build it.
- If the candidate is expected to ACQUIRE a missing external resource during
  implementation using an approved capability such as PixelLab, that resource
  may be ACQUIRED-IN-GOAL only when the acquisition itself is supporting work
  for this focused candidate rather than a separate substantial content
  milestone.
- prerequisites_ready evaluates only dependencies that must already exist
  before this candidate begins.
- Do not list a genuinely required-before-goal dependency as missing and then
  mark prerequisites_ready true merely because it could be built.

Before finalizing every candidate, perform this consistency check:

1. Read every item in dependencies.
2. First ask whether the dependency is VERIFIED CURRENT STATE or merely
   CAPABILITY-TO-CREATE evidence.
3. If missing, perform the GOAL OWNERSHIP TEST:
   - Is this small supporting plumbing for the candidate's one behavior?
   - Or is it substantial/independently testable work that should be separate?
4. Classify each item mentally as:
   - PRE-EXISTING: must already exist before the candidate can start and is
     verified as usable current state.
   - MISSING-PREREQUISITE: must exist first, is not currently verified, and is
     too substantial/independent to absorb into this candidate.
   - CREATED-IN-GOAL: small tightly coupled supporting work created as part of
     this candidate.
   - ACQUIRED-IN-GOAL: a missing external resource acquired as supporting work
     for this candidate.
5. prerequisites_ready = false if any MISSING-PREREQUISITE exists.
6. CREATED-IN-GOAL and ACQUIRED-IN-GOAL do not reduce prerequisites_ready only
   after they pass the goal-ownership test above.

PIXELLAB EXAMPLE:

Missing art that PixelLab can generate may be ACQUIRED-IN-GOAL when acquiring
that art is supporting resource work for the focused candidate. The current
absence of that art then affects local resource state but does not by itself
make prerequisites_ready false.

However, "PixelLab can generate it" does not authorize bundling an entire
independent environment/content milestone into an unrelated candidate. If the
resource-generation effort is itself substantial and independently meaningful,
keep it as separate work/candidate scope.

NAVMESH / WORLD-STATE EXAMPLE:

Candidate: "Melee Enemy Chase-and-Attack Prototype"

Do NOT assume NavMesh or walkable geometry automatically belongs inside the
enemy goal merely because the agent could create it.

First verify current state.

WRONG evidence:
- "DoorPrototypeSceneBuilder.BuildFloor() and BuildWalls() exist, therefore
  usable Floor/Walls are PRE-EXISTING."

A builder method proves only that geometry CAN be constructed.

RIGHT evidence:
- inspect the actual serialized scene/prefab/project state and verify that
  usable walkable Floor/Walls already exist in current project state.

Then perform the goal-ownership test:

- Adding a NavMeshAgent component to the new enemy, a detection radius, and an
  attack cooldown are normally tightly coupled CREATED-IN-GOAL work.
- Baking/configuring navigation over an already-existing usable test room MAY
  be supporting CREATED-IN-GOAL work if it is small/local and not a meaningful
  independent milestone.
- Creating the walkable room itself, building a reusable navigation
  infrastructure layer, authoring the dungeon floor, or doing other substantial
  world/navigation work is NOT automatically CREATED-IN-GOAL. If that work is
  independently testable/substantial, it is a separate prerequisite/candidate.

Therefore a Melee Enemy candidate may legitimately have
prerequisites_ready=false if the usable world/navigation prerequisite it needs
does not actually exist yet and creating it would be a separate goal.


============================================================
FOUNDATION COMPATIBILITY / GOAL-GRAPH RULES
============================================================

"EXISTS" IS NOT THE SAME AS "READY FOUNDATION."

After verifying that a scene object/component/resource actually exists, ask a
second question:

"Is this implementation sufficiently compatible with the GDD's desired
architecture that another feature can safely be built on top of it?"

Examples of potentially incompatible foundations include:

- a WASD-only controller when the GDD requires mouse-directed movement
- a temporary perspective/test camera when the GDD requires a fixed isometric
  camera/projection
- a disposable primitive Plane/Cube test room when the GDD requires an
  isometric Tilemap-based dungeon/world representation
- prototype scene-reload behavior standing in for a future persistent run/floor
  state architecture
- temporary navigation/world geometry expected to be substantially replaced

Do not mark such state READY-COMPATIBLE merely because it is serialized and
usable today.

For candidate dependency reasoning, use these dependency STATES:

- READY-COMPATIBLE
  The required usable state exists AND is sufficiently compatible with the
  desired architecture for this candidate to build on safely.

- PRESENT-INCOMPATIBLE
  Something exists, but the GDD/current gap analysis shows it is a temporary,
  placeholder, wrong-paradigm, or materially replaceable foundation for the
  behavior this candidate would rely on.

- MISSING-PREREQUISITE
  Required-before-goal work is absent and too substantial/independent to absorb
  into the candidate.

- CREATED-IN-GOAL
  Small, tightly coupled supporting work that legitimately belongs to this one
  focused candidate.

- ACQUIRED-IN-GOAL
  Supporting external-resource acquisition that legitimately belongs to this
  focused candidate.

Dependency STRENGTH is separate from dependency state:

- HARD-PREREQUISITE
  The candidate genuinely cannot be implemented or meaningfully tested without
  this dependency in a suitable form.

- SUPPORTING-DEPENDENCY
  Needed local plumbing/supporting work for this candidate, but not a separate
  prerequisite that must already exist before the goal starts.

- SHARED-FUTURE-DEPENDENCY
  A shared interface, future interaction, or downstream relationship. It may
  increase strategic relevance, but it is NOT a hard prerequisite.

HARD DEPENDENCY TEST:

Before calling something a HARD-PREREQUISITE, ask:

"If this dependency did not exist, could the candidate's ONE behavior still be
implemented and meaningfully tested?"

If YES, it is not a hard prerequisite.

Do not call a future interaction a hard prerequisite merely because two systems
will eventually use the same data or interact.

Example:
The GDD may use the cursor as both movement steering and spell aiming. That
does not automatically prove that the ENTIRE mouse-movement feature is a hard
prerequisite for every spell. A narrower cursor-world-target provider may be
the true shared dependency. Analyze the actual architectural dependency instead
of inflating unlock value.

FOUNDATION READINESS:

A HARD-PREREQUISITE in PRESENT-INCOMPATIBLE or MISSING-PREREQUISITE state makes
prerequisites_ready = false.

A candidate may use temporary/incompatible state only as a disposable test
harness when its CORE implementation is demonstrably decoupled from that
foundation. In that case:

- do not call the incompatible state READY-COMPATIBLE
- classify the relationship honestly
- explain the decoupling
- score foundation_compatibility and expected_rework_risk accordingly

FOUNDATION COMPATIBILITY score for each candidate:

- compatible
  Core implementation is built on compatible foundations, OR the candidate
  itself is the focused correction/replacement of the incompatible foundation.

- mixed
  Some surrounding prototype/test state will be replaced, but the candidate's
  core implementation is sufficiently decoupled/reusable that expected rework
  is limited.

- incompatible
  The candidate materially depends on foundations already known to require
  substantial replacement, so significant rework or revalidation is expected.

EXPECTED REWORK RISK for each candidate:

- low
- medium
- high

A quick prototype is not automatically a strong next goal. Penalize work that
is likely to be thrown away or materially rewritten after known foundational
deviations are corrected.

============================================================
BLOCKED-PREREQUISITE PROMOTION
============================================================

When a candidate contains a HARD-PREREQUISITE whose state is
PRESENT-INCOMPATIBLE or MISSING-PREREQUISITE, ask whether correcting/building
that prerequisite is itself:

- required by the GDD (directly or as necessary architecture for a required
  behavior)
- substantial enough not to be local plumbing
- independently implementable/testable/reviewable/committable

If YES, PROMOTE that prerequisite into the candidate-goal pool.

Do not merely say:

"Candidate X cannot be built because Foundation Y is missing."

and then omit Foundation Y from consideration.

The selector's job is to find the next actionable node in the dependency graph.
A blocked leaf should cause the agent to move upstream to a buildable
foundation when that foundation is itself a coherent goal.

Examples of potentially promotable foundations in this project include, based
on evidence rather than hard-coding:

- correcting the player control/input paradigm
- establishing a fixed isometric camera/projection
- establishing the world/Tilemap foundation
- establishing reusable navigation/world infrastructure

Whether these are separate goals or can be combined must be decided by the
focused-slice test, not assumed in advance.

============================================================
CANDIDATE SELF-DECOMPOSITION
============================================================

Before a candidate is allowed into the final candidate_goals array, perform a
SELF-DECOMPOSITION CHECK.

Ask:

1. Does implementation_scope contain more than one independently testable
   behavior/system?
2. Does risk_and_size or reasoning itself admit that this is really a new
   subsystem plus content plus integration?
3. Could major pieces reasonably be separate commits/goals?
4. Is the candidate's title narrower than the work actually listed in
   implementation_scope?

If any answer reveals multiple coherent goals, SPLIT the candidate and
re-evaluate the smaller slices.

Do not knowingly return a candidate while simultaneously saying it is "closer
to several systems" or "larger than a focused testable slice."

Every returned candidate must set is_focused_slice = true and provide
decomposition_reasoning explaining why.

============================================================
ARCHITECTURE-COMPATIBLE IMPLEMENTATION
============================================================

Prototype readiness asks whether something can be tested today.

Architecture compatibility asks whether the implementation is likely to remain
valid as the project moves toward the GDD.

These are different.

Do not select a feature merely because primitives/current prototype state make
it easy to demo if that feature materially depends on foundations already known
to be wrong.

Conversely, do not automatically block a foundational correction merely because
it must be tested against temporary surrounding content. A correction can still
be a strong goal if its core interface/behavior is compatible with the final
architecture and expected rework is low.

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

   IMPORTANT: this check must verify what Claude CLAIMS IT INSPECTED, not scan
   every prose field for forbidden words.

   After Claude returns structured_output but BEFORE saving
   goal_analysis.json:

   - read only `structured_output["current_state"]["files_reviewed"]`
   - reject the run if any files_reviewed entry contains an excluded repository
     path using either slash style:
       - AgentCrew/
       - AgentCrew\
       - DynamicContentPipeline/
       - DynamicContentPipeline\

   Do NOT serialize/search the entire structured_output for the bare words
   "AgentCrew" or "DynamicContentPipeline". A harmless explanatory sentence
   that merely mentions an excluded directory name must not discard an
   otherwise successful analysis.

   The analysis prompt remains the primary access-control instruction. This
   Python check is defense-in-depth/audit validation that the agent did not
   report excluded files as reviewed.

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

18. Run the defensive files_reviewed boundary check before saving the output.
    The check must inspect only current_state.files_reviewed for actual excluded
    path tokens; it must not reject the analysis merely because explanatory
    prose elsewhere contains an excluded directory name.

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
    - its foundation compatibility
    - its expected rework risk
    - its implementation risk
    - its unlock value
    - promoted foundational prerequisites/candidates
    - structured winner advantages/disadvantages
    - confirmation that semantic validation passed
    - rejected high-priority alternatives

21. Handle:
    - nonzero Claude exit codes
    - invalid JSON
    - missing structured_output
    - timeouts
    - excluded repository paths reported in current_state.files_reviewed

22. Allow model, timeout, and max-turn overrides through environment variables.

    The generated goal_agent.py must include an environment-variable-backed
    max-turn setting, for example:

    MAX_TURNS = int(os.environ.get("GOAL_AGENT_MAX_TURNS", "40"))

    and must pass that value to Claude using:

    --max-turns

    Do not rely on timeout alone; preserve both a wall-clock timeout and an
    agent-turn ceiling.

DEFENSIVE REPOSITORY-BOUNDARY VALIDATION (goal_agent.py):

Implement the excluded-directory defense using the audited file list only.

Required behavior:

```python
def check_excluded_paths(structured_output: dict[str, Any]) -> None:
    files_reviewed = (
        structured_output.get("current_state", {}).get("files_reviewed", [])
    )

    forbidden_tokens = (
        "AgentCrew/",
        "AgentCrew\\",
        "DynamicContentPipeline/",
        "DynamicContentPipeline\\",
    )

    violations = [
        str(item)
        for item in files_reviewed
        if any(token in str(item) for token in forbidden_tokens)
    ]

    if violations:
        raise RuntimeError(
            "Analysis reports inspecting excluded repository paths in "
            f"current_state.files_reviewed: {violations}"
        )
```

Equivalent implementation is fine, but preserve the semantics exactly:
validate actual reported inspection paths, not arbitrary prose.

POST-OUTPUT SEMANTIC VALIDATION (goal_agent.py):

In addition to JSON Schema validation and excluded-path validation, implement a
Python semantic validator that runs BEFORE save_json().

It must reject the run with a clear RuntimeError if any of these are violated:

1. Candidate names are unique.
2. selected_goal.name exactly matches one candidate_goals.name.
3. Every candidate has is_focused_slice == true.
4. For every dependency:
   - hard_prerequisite + (present_incompatible OR missing_prerequisite)
     contributes a blocker.
   - created_in_goal/acquired_in_goal may not use strength=hard_prerequisite.
   - shared_future_dependency never determines readiness.
5. candidate.prerequisites_ready must equal:
   NOT(any hard prerequisite is present_incompatible or missing_prerequisite).
6. Promotion:
   - If a dependency is hard, blocking, required_gdd_work=true, and
     independently_testable=true, should_promote_to_candidate must be true.
   - Every true promoted_candidate_name must exactly match an existing
     candidate name.
   - False promotion flags require promoted_candidate_name == "".
7. Foundation promotion:
   - candidate_worthy=true requires promoted_candidate_name matching a candidate.
   - candidate_worthy=false requires promoted_candidate_name == "".
8. winner_tradeoffs:
   - every alternative must match a candidate other than the winner
   - every winner_value/alternative_value must match actual candidate fields
   - every advantage must truly favor the winner by the ranking table
   - every disadvantage must truly favor the alternative
   - for every rejected high-priority alternative, every scalar dimension on
     which that alternative beats the winner must appear as a disadvantage
9. Top-level selected-goal dependencies must exactly equal the selected
   candidate's dependency objects, or goal_agent.py should derive/validate the
   same content before saving.
10. If any candidate's foundation_compatibility is "incompatible" while
    prerequisites_ready=true, require reasoning to explain why the incompatible
    foundation is only a disposable test harness and why core implementation
    remains decoupled; otherwise reject as inconsistent. Prefer prompt-side
    correction before output.

Print semantic-validation success in the terminal summary.

The structured output schema must contain at least:

- desired_state
- current_state
- gaps
- non_code_requirements
- foundation_gaps
- candidate_goals
- selected_goal
- selection_reason
- dependencies
- winner_tradeoffs
- evidence (an ARRAY of concrete supporting evidence strings)
- rejected_high_priority_alternatives

Use strict JSON Schema definitions where appropriate.

Do not regress previously established schema structure or reasoning semantics while adding new fields.
In particular:
- Do not assume "the agent can create it" means the work belongs inside the
  current candidate.
- CREATED-IN-GOAL is limited to tightly scoped supporting work that is not
  itself a meaningful independently testable goal.
- Substantial world, navigation, Tilemap, camera, prefab, infrastructure, or
  other reusable work must remain a prerequisite/separate candidate when it
  constitutes its own coherent task.
- A builder/factory/setup method proves capability to create state, not that the
  resulting state currently exists.
- PRE-EXISTING readiness requires evidence of the usable project state itself,
  not merely code capable of constructing it.
- PixelLab acquisition may be ACQUIRED-IN-GOAL when it is supporting resource
  acquisition for the focused candidate; substantial content-generation
  milestones should not be silently bundled.
- prerequisites_ready must be determined only after both current-state
  verification and the goal-ownership/decomposition test.
- selection_reason and rejected_high_priority_alternatives must agree with the
  final candidate_goals prerequisite/readiness/risk values.
- Comparative claims such as "only", "all", "every", "highest", "lowest",
  "same", or "equal" must never contradict the structured candidate values.
- Existing serialized state must not be treated as a ready foundation when it
  materially conflicts with the desired GDD architecture.
- Candidate selection must account for expected rework from known-to-be-replaced
  foundations.
- Blocking substantial prerequisites must be promoted into candidate_goals when
  they are required and independently testable.
- Candidate goals that fail their own focused-slice decomposition check must be
  split before output.
- Dependency strength must distinguish hard prerequisites from supporting and
  shared/future relationships.
- Winner comparison must be structurally represented in winner_tradeoffs and
  mechanically validated by goal_agent.py.
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

foundation_gaps entries:
- name
- desired_architecture
- current_state
- status
- evidence
- downstream_systems_affected
- candidate_worthy
- promoted_candidate_name

foundation_gaps.status must be constrained with an enum to:
- compatible
- partial_mismatch
- incompatible
- missing

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
- foundation_compatibility
- foundation_reasoning
- expected_rework_risk
- implementation_risk
- unlock_value
- unlock_reasoning
- is_focused_slice
- decomposition_reasoning
- systems_unlocked
- risk_and_size
- reasoning

candidate_goals.foundation_compatibility must be constrained to:
- compatible
- mixed
- incompatible

candidate_goals.expected_rework_risk must be constrained to:
- high
- medium
- low

candidate_goals.implementation_risk must be constrained to:
- high
- medium
- low

candidate_goals.unlock_value must be constrained to:
- high
- medium
- low

candidate_goals.is_focused_slice must be boolean. The prompt must require it
to be true for every returned candidate. The Python orchestrator must reject
the analysis before saving if any candidate returns false.

DEPENDENCIES MUST BE STRUCTURED OBJECTS, not free-form strings.

Use one shared dependency schema for candidate_goals.dependencies and the
top-level selected-goal dependencies array.

Each dependency object must contain:

- name
- strength
- state
- evidence
- reasoning
- required_gdd_work
- independently_testable
- should_promote_to_candidate
- promoted_candidate_name

dependency.strength must be an enum:
- hard_prerequisite
- supporting_dependency
- shared_future_dependency

dependency.state must be an enum:
- ready_compatible
- present_incompatible
- missing_prerequisite
- created_in_goal
- acquired_in_goal

Rules encoded in prompt AND checked by goal_agent.py:

- A hard_prerequisite in present_incompatible or missing_prerequisite state
  means prerequisites_ready must be false.
- If prerequisites_ready is false, there must be at least one hard prerequisite
  in one of those blocking states.
- created_in_goal and acquired_in_goal are supporting work and must not be
  labeled hard_prerequisite.
- A shared_future_dependency must not determine prerequisites_ready.
- If a hard dependency is present_incompatible or missing_prerequisite AND
  required_gdd_work=true AND independently_testable=true, then
  should_promote_to_candidate must be true.
- Whenever should_promote_to_candidate=true, promoted_candidate_name must
  exactly match one of the names in candidate_goals.
- If should_promote_to_candidate=false, promoted_candidate_name must be an
  empty string.

FOUNDATION-GAP PROMOTION VALIDATION:

- If foundation_gaps.candidate_worthy=true, promoted_candidate_name must exactly
  match one candidate_goals.name.
- If candidate_worthy=false, promoted_candidate_name must be an empty string.

WINNER TRADEOFFS MUST BE STRUCTURED.

Add top-level winner_tradeoffs with:
- advantages
- disadvantages
- summary

advantages and disadvantages are arrays of comparison objects containing:
- alternative
- dimension
- winner_value
- alternative_value
- reasoning

comparison.dimension must be an enum containing:
- prerequisites_ready
- resource_acquisition_readiness
- prototype_readiness
- integration_readiness
- foundation_compatibility
- expected_rework_risk
- implementation_risk
- unlock_value

goal_agent.py must mechanically verify that winner_value and alternative_value
exactly match the corresponding fields in the final candidate_goals objects.

It must also verify direction using these rankings:

- prerequisites_ready: true > false
- resource/prototype/integration readiness: high > medium > low
- foundation_compatibility: compatible > mixed > incompatible
- expected_rework_risk: low > medium > high
- implementation_risk: low > medium > high
- unlock_value: high > medium > low

An entry in winner_tradeoffs.advantages must actually favor the winner by this
ranking. An entry in disadvantages must actually favor the alternative.

For every rejected_high_priority_alternatives candidate, if that alternative
beats the winner on ANY scalar comparison dimension above, every such
disadvantage must appear in winner_tradeoffs.disadvantages.

selection_reason must be written FROM the structured candidate fields and
winner_tradeoffs, not from an independent contradictory narrative.

Dependency/prerequisite semantics for generated analyze.md:

- It must distinguish READY-COMPATIBLE current state from
  PRESENT-INCOMPATIBLE, MISSING-PREREQUISITE, CREATED-IN-GOAL, and
  ACQUIRED-IN-GOAL.
- It must separately classify dependency strength as HARD-PREREQUISITE,
  SUPPORTING-DEPENDENCY, or SHARED-FUTURE-DEPENDENCY.
- Existing/serialized state is not automatically READY-COMPATIBLE. Compare the
  existing implementation against the desired GDD architecture.
- A prototype/placeholder/wrong-paradigm foundation that is expected to be
  substantially replaced is PRESENT-INCOMPATIBLE when the candidate materially
  relies on it.
- Only hard prerequisites determine prerequisites_ready.
- A hard prerequisite in PRESENT-INCOMPATIBLE or MISSING-PREREQUISITE state
  makes prerequisites_ready=false.
- A future/shared interaction is not a hard dependency merely because it
  increases unlock value.
- "Can be created by the agent" is NOT enough to classify something as
  CREATED-IN-GOAL.
- CREATED-IN-GOAL is allowed only for small, tightly coupled supporting work
  that is not itself a coherent independently testable goal.
- If missing/incompatible work is a substantial reusable system,
  infrastructure layer, world/content milestone, separately required GDD
  feature, or focused task that could reasonably be implemented/tested/
  reviewed/committed on its own, it must remain blocking prerequisite work and
  be promoted into the candidate pool when required and independently testable.
- A builder/factory/setup/editor method is capability evidence only. It must
  not be used as proof that the built scene object/resource/configuration
  currently exists.
- NavMesh/Tilemap/world/camera/controller infrastructure must be classified by
  actual scope AND architectural compatibility; none is automatically
  CREATED-IN-GOAL or READY-COMPATIBLE.
- ACQUIRED-IN-GOAL resources are evaluated under
  resource_acquisition_readiness only after acquisition passes the same
  supporting-work/goal-ownership test.

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

candidate_goals.foundation_compatibility must be constrained with an enum to:
- compatible
- mixed
- incompatible

candidate_goals.expected_rework_risk must be constrained with an enum to:
- high
- medium
- low

candidate_goals.implementation_risk must be constrained with an enum to:
- high
- medium
- low

candidate_goals.unlock_value must be constrained with an enum to:
- high
- medium
- low

dependency.strength must be constrained with an enum to:
- hard_prerequisite
- supporting_dependency
- shared_future_dependency

dependency.state must be constrained with an enum to:
- ready_compatible
- present_incompatible
- missing_prerequisite
- created_in_goal
- acquired_in_goal

foundation_gaps.status must be constrained with an enum to:
- compatible
- partial_mismatch
- incompatible
- missing

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

CURRENT-STATE COMPATIBILITY NOTE:

When summarizing current_state, do not merely inventory what exists. Explicitly
identify implementations that exist but materially diverge from the GDD, such
as temporary prototype controls, camera/projection, world representation, or
other foundations. This compatibility information must feed foundation_gaps
and dependency states.

FOUNDATIONAL GAP ANALYSIS:

Before building candidate_goals, identify major foundational gaps that affect
multiple downstream systems.

A foundational gap is not merely "a big feature." It is a controller,
projection/camera assumption, world representation, navigation layer, run-state
architecture, or other base decision that downstream features materially build
on.

For each major foundation, compare:

- GDD desired architecture
- actual current project state
- whether current state is compatible, partially mismatched, incompatible, or
  missing
- downstream systems affected
- whether correcting/building it is itself a focused candidate-worthy goal

Return these in top-level foundation_gaps.

Do not hard-code which foundations are wrong. Derive them from the current GDD
and Assets/.

If foundation_gaps.candidate_worthy = true, that foundation must actually appear
in candidate_goals under the exact promoted_candidate_name.

This is how blocked leaf features move upstream in the goal graph.

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

HARD SELF-DECOMPOSITION RULE:

A candidate is NOT allowed to remain in candidate_goals if its own
implementation_scope/risk_and_size/reasoning admits that it is really multiple
independently testable systems, infrastructure milestones, content-generation
milestones, or commits.

Do not return a candidate and simultaneously say that it is "closer to a new
subsystem than a focused slice", "large because it includes several
foundations", or equivalent.

Split first, then compare the resulting smaller goals.

Every returned candidate must set:

- is_focused_slice = true
- decomposition_reasoning = a concrete explanation of why the candidate is one
  independently testable/committable slice

Do not reward a candidate for unlock value that comes primarily from bundling
several otherwise-separate missing features together.

The same anti-bundling rule applies to dependencies:

- A candidate must not hide a second coherent goal inside implementation_scope
  merely because that second goal is needed as a dependency.
- If a missing dependency could reasonably be implemented, tested, reviewed,
  and committed independently, or is a substantial reusable
  infrastructure/world task, keep it separate rather than absorbing it.
- "The agent can build it" is never sufficient justification for bundling it.

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

- foundation_compatibility must be:
  - compatible
  - mixed
  - incompatible

- foundation_reasoning must explain which current foundations the candidate
  materially depends on and whether those foundations match the GDD.

- expected_rework_risk must be:
  - high
  - medium
  - low

- implementation_risk must be:
  - high
  - medium
  - low

- unlock_value must be:
  - high
  - medium
  - low

- unlock_reasoning must distinguish HARD prerequisite unlocks from merely
  shared/future relationships. Do not inflate unlock value by calling future
  interactions hard dependencies.

- is_focused_slice must be true.

- decomposition_reasoning must explain why the candidate survives the
  self-decomposition check.

PREREQUISITE / GOAL-DECOMPOSITION CONSISTENCY RULE:

A prerequisite is something that must already exist in usable project state
before work on the candidate starts.

CRITICAL: "CAN BE CREATED" DOES NOT MEAN "BELONGS IN THIS GOAL."

STEP 1 — VERIFY CURRENT STATE

For every claimed PRE-EXISTING dependency, distinguish:

- ACTUAL USABLE STATE: a concrete scene object, prefab, Tile asset, imported
  resource, serialized configuration/component, or other current project state
  actually verified under Assets/.
- CAPABILITY TO CREATE STATE: a builder method, factory, setup/editor script,
  bake method, generation method, or other code that could create the state if
  run.

Capability-to-create evidence is NOT proof that the dependency currently
exists.

Example:
DoorPrototypeSceneBuilder.BuildFloor() proves a floor can be built. It does
not by itself prove a usable Floor is already present in current project state.

STEP 2 — IF MISSING, PERFORM THE GOAL-OWNERSHIP TEST

Ask whether the missing work is:

A) small, tightly coupled supporting plumbing needed only to make this
candidate's ONE behavior testable, or

B) a meaningful independent task: a substantial/reusable system,
infrastructure layer, world/content milestone, separately required GDD
feature, or work that could reasonably be implemented, tested, reviewed, and
committed as its own focused goal.

Only category A may be CREATED-IN-GOAL.

Category B must remain a MISSING-PREREQUISITE (making
prerequisites_ready=false) and should be considered as its own candidate goal
when appropriate.

STEP 3 — CLASSIFY STATE AND STRENGTH SEPARATELY

STATE:

1. READY-COMPATIBLE — verified usable state AND sufficiently compatible with
   the desired GDD architecture for this candidate.
2. PRESENT-INCOMPATIBLE — usable state exists, but it is a prototype,
   placeholder, wrong-paradigm, or materially replaceable foundation for the
   behavior this candidate would rely on.
3. MISSING-PREREQUISITE — required-before-goal work is absent and too
   substantial/independent to absorb.
4. CREATED-IN-GOAL — small tightly coupled supporting work created inside this
   focused candidate.
5. ACQUIRED-IN-GOAL — external resource acquisition that is supporting work
   for this focused candidate rather than a separate content milestone.

STRENGTH:

1. HARD-PREREQUISITE — candidate cannot be implemented/meaningfully tested
   without this dependency in a suitable form.
2. SUPPORTING-DEPENDENCY — local plumbing/support needed within the candidate.
3. SHARED-FUTURE-DEPENDENCY — future interaction/shared interface, not a
   current blocker.

Then apply:

- A HARD-PREREQUISITE in PRESENT-INCOMPATIBLE or MISSING-PREREQUISITE state
  => prerequisites_ready = false.
- CREATED-IN-GOAL and ACQUIRED-IN-GOAL must be supporting work, not hard
  prerequisites.
- SHARED-FUTURE-DEPENDENCY never determines prerequisites_ready.
- Do not re-label a missing/incompatible hard prerequisite as CREATED-IN-GOAL
  simply to make a preferred candidate appear ready.
- NavMesh, Tilemap/Grid, camera setup, prefab creation, room construction,
  controller/input foundations, and other infrastructure are NOT automatically
  CREATED-IN-GOAL or READY-COMPATIBLE. Classify them by actual scope AND
  architectural compatibility.
- If a blocking hard dependency is required GDD work and independently
  testable, promote it into candidate_goals.

PIXELLAB / RESOURCE ACQUISITION EXAMPLE:

Missing external art can be ACQUIRED-IN-GOAL when PixelLab can realistically
supply it and acquisition is supporting work for the focused candidate.
resource_acquisition_readiness can still be HIGH while Unity-side import,
sorting, collision, Tilemap, or integration work remains.

But PixelLab capability does not justify absorbing an entire independently
meaningful content/world milestone into an unrelated candidate.

NAVMESH / WORLD-STATE / FOUNDATION-COMPATIBILITY EXAMPLE:

For a candidate such as "Melee Enemy Chase-and-Attack Prototype":

1. Verify actual world state; builder methods alone are insufficient.

2. Then compare that world state to the GDD.
   A serialized primitive test Plane/Cube room may be PRESENT-INCOMPATIBLE
   rather than READY-COMPATIBLE if enemy navigation/chase behavior would be
   materially tuned/validated against a world representation already known to
   be replaced by the required isometric dungeon.

3. Do not automatically absorb world/navigation work into the enemy goal.

   Likely CREATED-IN-GOAL / SUPPORTING:
   - MeleeEnemy behavior code
   - NavMeshAgent component on that enemy
   - detection radius
   - attack range/cooldown logic

   MAY be local supporting work:
   - a trivial navigation bake over an already READY-COMPATIBLE test surface

   Likely separate prerequisite/candidate when substantial or foundational:
   - correcting/building the walkable world representation
   - reusable navigation infrastructure
   - the isometric world/Tilemap foundation

If the enemy materially depends on PRESENT-INCOMPATIBLE or missing world
foundations, prerequisites_ready should be false and the blocking foundation
should be promoted when it is required and independently testable.

MOVEMENT / CAMERA / FLOOR EXAMPLE:

Do not automatically reason:

"Player exists + Camera exists + Floor exists => movement foundation ready."

Check whether each foundation is compatible with the GDD.

A mouse-movement correction may still be a strong candidate even while the
temporary camera/floor will later change IF its core cursor-world projection
and movement interface are designed to remain valid and the temporary scene is
used only as a disposable test harness. In that case foundation_compatibility
may be MIXED rather than INCOMPATIBLE, with explicit low/medium expected
rework reasoning.

HARD VS SHARED DEPENDENCY EXAMPLE:

The fact that the cursor will eventually aim spells does not automatically make
the entire mouse locomotion feature a HARD prerequisite for every spell.
Determine whether the true hard dependency is a narrower cursor-world-target
provider/shared interface. Shared future use may increase unlock value, but it
must be labeled SHARED-FUTURE-DEPENDENCY unless the downstream feature truly
cannot be implemented/tested without the whole candidate.

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
prototype_readiness | integration_readiness | foundation_compatibility |
expected_rework_risk | implementation_risk | unlock_value | scope

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

STRUCTURED WINNER TRADEOFFS:

Before writing selection_reason, populate winner_tradeoffs from the FINAL
candidate values.

winner_tradeoffs.advantages must contain only dimensions on which the winner
actually outranks the named alternative.

winner_tradeoffs.disadvantages must explicitly contain every scalar dimension
on which each rejected high-priority alternative outranks the winner.

Use these scalar rankings:

- prerequisites_ready: true > false
- readiness: high > medium > low
- foundation_compatibility: compatible > mixed > incompatible
- expected_rework_risk: low > medium > high
- implementation_risk: low > medium > high
- unlock_value: high > medium > low

Write selection_reason FROM these structured facts. Do not independently invent
comparisons in prose.

If a selected goal has higher prototype_readiness because it is easy to demo
on disposable prototype foundations but has worse foundation_compatibility or
expected_rework_risk, that disadvantage must be visible in winner_tradeoffs
and discussed.

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
[ ] A returned prose sentence containing the word "AgentCrew" outside current_state.files_reviewed would NOT fail the Python boundary validator.
[ ] The analysis Claude is not given Bash.
[ ] The analysis Claude is not given PixelLab MCP or any MCP tool.
[ ] analyze.md never tells the read-only analysis Claude to save or create a file.
[ ] analyze.md requires at least three candidate goals TOTAL, not three per missing feature.
[ ] analyze.md does not hard-code any predetermined winner.
[ ] The GDD is treated as the desired state.
[ ] Assets/ is treated as the current state.
[ ] The analysis prompt explicitly forbids Read, Glob, and Grep access to AgentCrew/ and DynamicContentPipeline/.
[ ] goal_agent.py checks current_state.files_reviewed for excluded AgentCrew/ and DynamicContentPipeline/ paths before saving.
[ ] goal_agent.py does NOT serialize/search the entire structured output for bare excluded-directory words; harmless prose mentions cannot cause a false boundary failure.
[ ] The excluded-path validator accepts both forward-slash and backslash path forms.
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
[ ] analyze.md defines a prerequisite as usable project state that must already exist before the candidate begins.
[ ] analyze.md distinguishes actual usable current state from code that is merely capable of constructing that state.
[ ] analyze.md explicitly says builder/factory/setup/editor methods such as BuildFloor()/BuildWalls() are not, by themselves, proof that the built result currently exists.
[ ] analyze.md requires inspection of concrete serialized/project state before calling a stateful dependency PRE-EXISTING and ready when such state should be present under Assets/.
[ ] analyze.md contains the rule "can be created != belongs in this goal".
[ ] analyze.md requires a goal-ownership/decomposition test before classifying missing work as CREATED-IN-GOAL.
[ ] analyze.md limits CREATED-IN-GOAL to small, tightly coupled supporting plumbing that is not itself a meaningful independently testable goal.
[ ] analyze.md says substantial reusable systems, infrastructure layers, world/content milestones, separately required GDD features, or independently testable missing tasks remain MISSING-PREREQUISITE / separate candidate work.
[ ] analyze.md requires prerequisites_ready=false when a required-before-goal dependency is missing and too substantial/independent to absorb.
[ ] analyze.md says an agent's technical ability to create a missing dependency is not sufficient reason to mark prerequisites_ready=true.
[ ] analyze.md does NOT hard-code NavMesh/Tilemap/camera/prefab/world infrastructure as CREATED-IN-GOAL; it classifies them according to actual scope.
[ ] analyze.md includes an explicit Melee Enemy example distinguishing enemy-local plumbing from potentially separate walkable-world/navigation prerequisites.
[ ] analyze.md preserves PixelLab acquisition semantics while preventing substantial content milestones from being silently bundled into unrelated candidates.
[ ] analyze.md distinguishes READY-COMPATIBLE from PRESENT-INCOMPATIBLE foundations; existence alone is not enough.
[ ] analyze.md requires foundation compatibility to be judged against the desired GDD architecture.
[ ] analyze.md requires a blocking hard dependency in PRESENT-INCOMPATIBLE state to make prerequisites_ready=false.
[ ] analyze.md distinguishes HARD-PREREQUISITE, SUPPORTING-DEPENDENCY, and SHARED-FUTURE-DEPENDENCY.
[ ] analyze.md requires a necessity test before labeling a dependency hard.
[ ] analyze.md forbids inflating unlock value by calling future/shared interactions hard prerequisites.
[ ] analyze.md promotes substantial required independently-testable blocking prerequisites into candidate_goals.
[ ] foundation_gaps exists in the schema and candidate_worthy foundations are mechanically required to map to candidate names.
[ ] analyze.md performs a hard self-decomposition check and never knowingly returns a multi-goal candidate.
[ ] every candidate has is_focused_slice and decomposition_reasoning.
[ ] every candidate has foundation_compatibility, foundation_reasoning, expected_rework_risk, implementation_risk, unlock_value, and unlock_reasoning.
[ ] analyze.md evaluates expected rework when prototype work depends on known-to-be-replaced foundations.
[ ] dependencies are structured objects with strength/state/evidence/reasoning/promotion fields.
[ ] goal_agent.py semantically validates prerequisites_ready from structured hard dependency states.
[ ] goal_agent.py semantically validates blocked-prerequisite promotion.
[ ] winner_tradeoffs is structured and goal_agent.py validates values/directions against candidate_goals.
[ ] for every rejected high-priority alternative, winner_tradeoffs.disadvantages contains every scalar dimension on which it beats the winner.
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
