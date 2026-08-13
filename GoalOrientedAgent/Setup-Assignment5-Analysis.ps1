$ErrorActionPreference = "Stop"

# Assignment 5 bootstrap:
# Creates the initial ANALYSIS-ONLY goal-oriented agent.
# This script is intended to live in:
#   NoSafeCircle\GoalOrientedAgent\Setup-Assignment5-Analysis.ps1

$GoalAgentDir = $PSScriptRoot
$RepoRoot = Split-Path -Parent $GoalAgentDir

Write-Host ""
Write-Host "Assignment 5 - Build analysis-only goal agent" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host ""

Set-Location $RepoRoot

# Make sure the Assignment 5 folders exist.
New-Item -ItemType Directory -Force -Path "GoalOrientedAgent\prompts" | Out-Null
New-Item -ItemType Directory -Force -Path "GoalOrientedAgent\outputs" | Out-Null

$Prompt = @'
Create the initial ANALYSIS-ONLY implementation for Assignment 5 in /workspace/GoalOrientedAgent.

Read /workspace/AgentCrew/orchestrator.py first and reuse its proven Claude CLI invocation patterns where useful, but do not modify AgentCrew, DynamicContentPipeline, the GDD, or any Unity files.

Create:
- GoalOrientedAgent/goal_agent.py
- GoalOrientedAgent/prompts/analyze.md

The goal agent must invoke Claude Code as a goal-oriented reasoning agent with read-only tools Read, Glob, and Grep.

It must:
1. Read Docs/GDD/No_Safe_Circle_GDD.md as the desired state.
2. Scan the actual Unity codebase under Assets as the current state.
3. Identify which REQUIRED GDD features are implemented, partial, or missing.
4. Evaluate missing features using:
   - dependencies
   - prerequisite readiness
   - how many other required systems the feature unlocks
   - implementation risk/size
   - required-vs-stretch scope
5. Independently choose exactly one next implementation goal.

Do NOT hard-code Mana or any particular feature as the winner. The model must make the selection from evidence it finds.

Require structured JSON output containing:
- desired_state
- current_state
- gaps
- candidate_goals with reasoning
- selected_goal
- selection_reason
- dependencies
- evidence
- rejected_high_priority_alternatives

Save the structured result to:
GoalOrientedAgent/outputs/goal_analysis.json

The Python script must print a readable summary of the selected goal and why it was selected.

Analysis mode must have no Write or Edit permission and must not change gameplay code.

Keep the implementation straightforward and runnable using the same Docker/Claude setup already present in this repository.
'@

Write-Host "Launching Claude Code to create the Assignment 5 analysis harness..." -ForegroundColor Yellow
Write-Host ""

docker compose run --rm claude claude -p $Prompt --model sonnet --permission-mode dontAsk --tools "Read,Glob,Grep,Write" --disallowedTools "Edit,mcp__*"

if ($LASTEXITCODE -ne 0) {
    throw "Claude setup command failed with exit code $LASTEXITCODE."
}

Write-Host ""
Write-Host "Setup completed." -ForegroundColor Green
Write-Host ""
Write-Host "Next:"
Write-Host "  1. Run: git status"
Write-Host "  2. Inspect GoalOrientedAgent\goal_agent.py"
Write-Host "  3. Inspect GoalOrientedAgent\prompts\analyze.md"
Write-Host "  4. Do NOT run goal_agent.py until the generated harness has been reviewed."
Write-Host ""
