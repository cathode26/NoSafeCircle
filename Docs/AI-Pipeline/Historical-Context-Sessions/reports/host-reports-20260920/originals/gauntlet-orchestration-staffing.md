# Gauntlet orchestration staffing — three tiers, one authority

Written 2026-09-12 for the fresh NSC-1130 replay gauntlet. This is operating
guidance for the agent sessions that operate the gauntlet, not for the crews
inside it (the crews keep `worker-haiku.example.json`).

## 1. The three tiers

| Tier | Model | Session lifetime | Owns | Never |
|---|---|---|---|---|
| OPERATOR | Haiku 4.5 (use Sonnet 5 if it cannot follow the fixed loop) | one fresh session per gauntlet run | runs the fixed runner block (4.1), reads one status field, escalates | diagnoses, edits files, retries, clears or stops jobs, changes flags |
| IMPLEMENTER | Sonnet 5 | one fresh session per ticket | executes one bounded ticket (section 6) in its own clone, commits, reports | touches the live run, the operator's clone, Tasks/, Assets/, GitHub, Docker, Unity |
| REVIEWER / INTEGRATOR | Opus 5 at effort `xhigh` (Fable 5.1 when the change touches process identity, locks, or provider spend) | one session for the whole gauntlet | diagnosis, design, tickets, verification of everything the other two produce, integration into the controller clone, reports to Vincent and Issue #36 | trusts authorship, mutates the live run without Vincent's explicit word, pushes or merges |

Only the reviewer has judgment authority. The operator relays; the implementer
executes. Vincent relays messages between the windows (or, if you prefer a
board, the reviewer and operator can post them as comments on Issue #36).

## 2. Fixed facts for this gauntlet

- Controller code: `C:\nscrev\throughput`, branch `throughput/background-decomposition`, commit `e90670da5b5fc19567e1efe1cb655c43de292f4e` (background jobs `6f32664`, plan() cache `c70a2d9`, containment and operator stop `24273b6`, stop-graph `0c42f0d`, exact container cleanup and restart reconciliation `67614e7`, window/stop-retry/lock repairs `14cd051`, unfinished-tombstone/reauthentication/ownership/stop-graph repairs `62245a1`, durable partial cleanup/full identity authentication/concurrency outcomes/unreadable-index repairs `91a0b0d`, checkout-exact container identity with ticket labels and refusal-safe cleanup progress `ca56dc7`, ownership-verified cooperative stop `e90670d`). Astra's re-review of this exact commit is pending; the trial does not start before it passes.
- Live Source: `C:\NSC\GauntletFresh1140-20260912-1`, branch `gauntlet-replay/fresh-1140-20260912`, commit `bdaaa2d153a0504c471fbd66afd70f1984b171d9` (a disposable clone with no remote). The controller runs from the clone against this Source; the Source's own copy of the pipeline is not modified. The old 1130 project and its live run are not used for anything.
- Checkout root: `C:\NSC\GauntletFresh1140-20260912-1-Checkouts`; records in `.assistant-control`; journal `graph-controller-events.jsonl`; state `graph-controller.json`; background job indexes `NSC-*.background-job.json`; job run roots `background-jobs\<task>\<job_id>\`.
- Targets: NSC-1140 … NSC-1147, a fresh family generated on 2026-09-12 with the same graph as NSC-1130 … NSC-1137: 1140, 1145 and 1146 need decomposition (each proposal is a paid two-provider job; each yields two children crews), 1141–1144 are independent single-agent tasks, 1145 depends on 1141, 1146 on 1145, 1147 on 1146. Five of the eight need work that has not started; the run is long. Worker config: `Pipeline\AssistantControl\worker-haiku.example.json` in the Source (the same bytes the 1130 run used).
- State at the time of writing: no task has a record and the checkout root holds no `.assistant-control` yet (the first 4.1 run creates it); the 1130 family was removed from this copy, so nothing outside the eight targets exists in the graph. Decomposition children are allocated by the decomposer at the next free ids (expect NSC-1148 upward).
- Ticket identity is checkout-exact since `ca56dc7`: a background-job ticket id (and so its provider container name) is derived from the Source path and the checkout root as well as the task, and the container carries `com.nosafecircle.assistant.job` / `com.nosafecircle.assistant.checkout` labels that a stop verifies before removing anything. Tickets written by an older controller commit do not authenticate under this one and cannot be cleared by the tool; if `$ExpectedControlHead` is ever moved under a checkout root that already holds `.assistant-control\NSC-*.background-job.json` files from an older commit, the reviewer archives those files by hand (and removes any leftover `nsc-decompose-*` container by hand) before the operator runs 4.1 again. The 1140 checkout root starts empty, so nothing needs migrating for this trial.
- Issue for reports: https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36

## 3. Rules that bind every tier

1. While the operator loop is running, nobody edits `C:\nscrev\throughput`. New child processes (background jobs, worker launches) import code from that clone at launch time; a half-edited file would run. The implementer works in its own clone; the reviewer integrates only when the operator loop has ended and `stop-background-jobs` reports no jobs.
2. The live run is read-only for the reviewer and implementer. Only the operator's runner block mutates it, and only through `run-graph`. No resets, no wipes, no moving the Source branch by hand.
3. No paid provider is launched outside `run-graph --authorize-provider-spend`. No push, no merge, no GitHub state change other than comments on Issue #36 when Vincent asks.
4. A failed, died, cancelled or quarantined background job blocks only its task and is never relaunched automatically. Only the reviewer decides to run `clear-background-job`, after reading the job's `stderr.log`, receipt and (for a decomposition) its `provider_container_cleanup`; the command refuses until that container is verified absent, waits out a one-minute tombstone after a killed tree, and rechecks the name once before the index moves aside.
5. Every hand-off is a complete message in the formats of sections 5 and 6. No splicing, no "as before".

## 4. Commands

All blocks are Windows PowerShell 5.1. Paste each block whole. They contain no placeholders.

### 4.1 Operator runner (mutating: launches crews and background jobs)

```powershell
& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    # ============================================================
    # IDENTITY
    # ============================================================
    $ControlSource = "C:\nscrev\throughput"
    $ExpectedControlHead = "e90670da5b5fc19567e1efe1cb655c43de292f4e"
    $Source = "C:\NSC\GauntletFresh1140-20260912-1"
    $ExpectedBranch = "gauntlet-replay/fresh-1140-20260912"
    $CheckoutRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts"
    $Records = Join-Path $CheckoutRoot ".assistant-control"
    $WorkerConfig = Join-Path $Source "Pipeline\AssistantControl\worker-haiku.example.json"
    $Targets = @("NSC-1140", "NSC-1141", "NSC-1142", "NSC-1143", "NSC-1144", "NSC-1145", "NSC-1146", "NSC-1147")
    $LogDir = Join-Path $CheckoutRoot "operator-logs"
    $MaxInvocations = 40
    $ContinueStatuses = @("worker_still_running", "background_jobs_running", "action_limit_reached", "capacity_full")
    $CurrentPhase = "identity"
    $LastStatus = "not-run"
    $LastOut = ""
    $IdleCycles = 0

    function Get-NativeText {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @()
        )

        $StdOutPath = [System.IO.Path]::GetTempFileName()
        $StdErrPath = [System.IO.Path]::GetTempFileName()
        $Previous = $ErrorActionPreference
        $Code = 1

        try {
            try {
                $ErrorActionPreference = "Continue"
                & $FilePath @ArgumentList 1> $StdOutPath 2> $StdErrPath
                $Code = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $Previous
            }

            if ($Code -ne 0) {
                Get-Content -LiteralPath $StdErrPath | ForEach-Object {
                    Write-Host ("[STDERR] " + $_)
                }
                throw ($FilePath + " failed with exit code " + $Code + ".")
            }

            return ((@(Get-Content -LiteralPath $StdOutPath) -join "`n").Trim())
        }
        finally {
            Remove-Item -LiteralPath $StdOutPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $StdErrPath -Force -ErrorAction SilentlyContinue
        }
    }

    try {
        # ========================================================
        # PREFLIGHT
        # ========================================================
        $CurrentPhase = "preflight"
        foreach ($Path in @($ControlSource, $Source, $CheckoutRoot, $WorkerConfig)) {
            if (-not (Test-Path -LiteralPath $Path)) {
                throw "Missing path: $Path"
            }
        }

        $ControlHead = Get-NativeText -FilePath "git" -ArgumentList @("-C", $ControlSource, "rev-parse", "HEAD")
        if ($ControlHead -ne $ExpectedControlHead) {
            throw "Controller clone is at $ControlHead, expected $ExpectedControlHead. Escalate."
        }

        $ControlEdits = Get-NativeText -FilePath "git" -ArgumentList @("-C", $ControlSource, "status", "--porcelain=v1", "--untracked-files=no")
        if (-not [string]::IsNullOrWhiteSpace($ControlEdits)) {
            throw ("Controller clone has local edits; someone is editing it. Escalate.`n" + $ControlEdits)
        }

        $SourceBranch = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "branch", "--show-current")
        if ($SourceBranch -ne $ExpectedBranch) {
            throw "Source is on $SourceBranch, expected $ExpectedBranch. Escalate."
        }

        $SourceHead = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "rev-parse", "HEAD")
        Write-Host "[PASS] Controller $ControlHead"
        Write-Host "[PASS] Source $SourceBranch at $SourceHead"

        # ========================================================
        # OBSERVE CURRENT STATE
        # ========================================================
        $CurrentPhase = "observe-current-state"
        $OwnerPath = Join-Path $Records "graph-controller-owner.json"
        if (Test-Path -LiteralPath $OwnerPath) {
            $Owner = Get-Content -LiteralPath $OwnerPath -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-Host ("[STATE] Previous controller: " + $Owner.status + " (invocation " + $Owner.invocation_id + ")")
            if ($Owner.status -ne "controller_released") {
                throw ("A graph controller may still own the graph (owner status " + $Owner.status + "). Escalate; do not start a second controller.")
            }
        }

        $StatePath = Join-Path $Records "graph-controller.json"
        if (Test-Path -LiteralPath $StatePath) {
            $State = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-Host ("[STATE] Graph status before this run: " + $State.status + "; last error: " + $State.last_error)
        }

        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

        # ========================================================
        # WORK: bounded run-graph loop
        # ========================================================
        $CurrentPhase = "work"
        Set-Location $ControlSource
        $TargetArguments = @()
        foreach ($Task in $Targets) {
            $TargetArguments += @("--task", $Task)
        }

        for ($Invocation = 1; $Invocation -le $MaxInvocations; $Invocation++) {
            $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
            $OutPath = Join-Path $LogDir ("run-graph-" + $Stamp + ".json")
            $ErrPath = Join-Path $LogDir ("run-graph-" + $Stamp + ".stderr.log")
            $Arguments = @(
                "-m", "Pipeline.AssistantControl",
                "--source", $Source,
                "--checkout-root", $CheckoutRoot,
                "run-graph"
            ) + $TargetArguments + @(
                "--worker-config", $WorkerConfig,
                "--human-review-task", "NSC-042",
                "--auto-approve-gauntlet",
                "--authorize-provider-spend",
                "--capacity", "20",
                "--target-branch", $ExpectedBranch,
                "--max-actions", "240",
                "--background-jobs", "2"
            )

            Write-Host ""
            Write-Host ("[RUN " + $Invocation + "] " + (Get-Date -Format "HH:mm:ss") + " run-graph starting; output " + $OutPath)

            $Previous = $ErrorActionPreference
            $Code = 1
            try {
                $ErrorActionPreference = "Continue"
                & python @Arguments 1> $OutPath 2> $ErrPath
                $Code = $LASTEXITCODE
            }
            finally {
                $ErrorActionPreference = $Previous
            }

            $LastOut = $OutPath
            $Result = $null
            $Raw = ""
            if (Test-Path -LiteralPath $OutPath) {
                $Raw = Get-Content -LiteralPath $OutPath -Raw -Encoding UTF8
            }
            if (-not [string]::IsNullOrWhiteSpace($Raw)) {
                try {
                    $Result = $Raw | ConvertFrom-Json
                }
                catch {
                    $Result = $null
                }
            }
            if ($null -eq $Result) {
                $LastStatus = "no_json_output"
                Write-Host ("[STOP] No JSON result (exit " + $Code + "). Read " + $ErrPath)
                break
            }

            $LastStatus = [string]$Result.status
            $ActionCount = 0
            if ($Result.completed_actions) {
                $ActionCount = @($Result.completed_actions).Count
            }
            $HarvestCount = 0
            if ($Result.harvested_jobs) {
                $HarvestCount = @($Result.harvested_jobs).Count
            }
            Write-Host ("[RUN " + $Invocation + "] exit " + $Code + "; status " + $LastStatus + "; actions " + $ActionCount + "; harvested " + $HarvestCount + "; source " + $Result.source_commit)
            if ($Result.completed_actions) {
                foreach ($Item in @($Result.completed_actions)) {
                    Write-Host ("    " + $Item.action.kind + " " + $Item.action.task_id + " -> " + $Item.result.status)
                }
            }
            if ($Result.background_jobs) {
                foreach ($Job in @($Result.background_jobs)) {
                    Write-Host ("    job " + $Job.kind + " " + $Job.task_id + ": " + $Job.status)
                }
            }
            if ($Result.blocked) {
                foreach ($Blocked in @($Result.blocked)) {
                    Write-Host ("    blocked " + $Blocked.task_id + ": " + $Blocked.reason)
                }
            }
            if ($Result.error) {
                Write-Host ("    error: " + $Result.error)
            }

            if ($Code -ne 0) {
                Write-Host "[STOP] Non-zero exit. Escalate."
                break
            }
            if ($ContinueStatuses -notcontains $LastStatus) {
                Write-Host ("[STOP] Terminal status " + $LastStatus + ".")
                break
            }
            if (($ActionCount -eq 0) -and ($HarvestCount -eq 0)) {
                $IdleCycles++
            }
            else {
                $IdleCycles = 0
            }
            if ($IdleCycles -ge 3) {
                $LastStatus = "idle_loop:" + $LastStatus
                Write-Host "[STOP] Three cycles without progress. Escalate."
                break
            }
            if ($LastStatus -eq "capacity_full") {
                Start-Sleep -Seconds 30
            }
        }

        # ========================================================
        # FINAL REPORT
        # ========================================================
        $CurrentPhase = "final-report"
        Write-Host ""
        Write-Host "============================================================"
        Write-Host ("[DONE] Operator loop ended with status: " + $LastStatus)
        Write-Host "============================================================"
        Write-Host ("[STATE] Last result JSON: " + $LastOut)
        Write-Host ("[STATE] Records: " + $Records)
        Write-Host ("[STATE] Journal: " + (Join-Path $Records "graph-controller-events.jsonl"))
        Write-Host "[NEXT] complete -> tell Vincent. awaiting_human -> tell Vincent the waiting_human list. Anything else -> send the section 5 escalation to the reviewer and stop."
    }
    catch {
        Write-Host ""
        Write-Host ("[BLOCKED] Operator loop did not reach DONE (phase " + $CurrentPhase + ")")
        Write-Host ("[ERROR] " + $_.Exception.Message)
        Write-Host ("[RECOVERY] Last status: " + $LastStatus + "; last result: " + $LastOut)
        Write-Host "[RECOVERY] Do not rerun. Send this output to the reviewer."
        throw
    }
}
```

Ctrl+C in the operator window stops the controller, which stops its background
jobs (bounded grace, then the exact Job Object trees) and marks them
`cancelled`; the block itself also stops, so run 4.2 afterwards to read state.

### 4.2 Read-only status (no mutation; safe for any tier)

```powershell
& {
    $env:PYTHONUTF8 = "1"
    Set-Location "C:\nscrev\throughput"
    python -m Pipeline.AssistantControl --source "C:\NSC\GauntletFresh1140-20260912-1" --checkout-root "C:\NSC\GauntletFresh1140-20260912-1-Checkouts" graph-plan --task NSC-1140 --task NSC-1141 --task NSC-1142 --task NSC-1143 --task NSC-1144 --task NSC-1145 --task NSC-1146 --task NSC-1147 --auto-approve-gauntlet --capacity 20 --target-branch gauntlet-replay/fresh-1140-20260912 --background-jobs 2
    Write-Host ("[EXIT] " + $LASTEXITCODE)
}
```

Journal tail (read-only):

```powershell
Get-Content -LiteralPath "C:\NSC\GauntletFresh1140-20260912-1-Checkouts\.assistant-control\graph-controller-events.jsonl" -Tail 40
```

### 4.3 Stopping the controller (reviewer only; mutating)

Stopping a running controller, including a detached one started by 4.5: the
request binds to the running invocation, PID and process identity; the
controller cancels its jobs exactly like Ctrl+C (bounded grace, exact Job
Object trees, exact provider containers watched for the whole window) and
releases with status `stopped`. Repeating it is harmless (`already_released`).
It refuses only when no controller ever owned the graph or the owner record
is stale. Exit 1 with status `stopped_cleanup_pending` (or, once the owner
has released, `already_released_cleanup_pending`) means the controller stopped
but a decomposition's container cleanup is not final yet (its one-minute
tombstone is unfinished, Docker was unreachable, or a name kept reappearing):
run the second block until it prints `stopped`.

```powershell
& {
    $env:PYTHONUTF8 = "1"
    Set-Location "C:\nscrev\throughput"
    python -m Pipeline.AssistantControl --source "C:\NSC\GauntletFresh1140-20260912-1" --checkout-root "C:\NSC\GauntletFresh1140-20260912-1-Checkouts" stop-graph --reason "reviewer stop" --grace-seconds 15 --wait-seconds 120
    Write-Host ("[EXIT] " + $LASTEXITCODE)
}
```

Finishing a stop, or recovering after a lost controller process (the owner
record says started but the process is gone; `stop-graph` reports it stale).
Refuses while a graph controller owns the graph. It waits each container's
one-minute tombstone out and records the final recheck, so it can take about
a minute per killed decomposition. Exit 0 with `stopped` means every job is
terminal and every provider container is finally verified absent; exit 1
with `cleanup_pending` names the tasks whose container is not (with
`retry_after_utc` when a bound is still running), and the block is simply run
again once Docker Desktop answers or the time has passed. A cleanup marked
`authentication_failed` (the job index no longer matches its immutable
ticket, or its recorded PID / process identity / Job Object name no longer
match the run's own `launcher.identity.json`, `child.identity.json` and
`job.opened.json`) is never retried automatically: the reviewer inspects the
index and `launch.request.json` under `background-jobs\<task>\<job_id>\`,
repairs or removes by hand, and only then clears. A job index that cannot be
read at all (empty, truncated, malformed, or naming another Source) is
reported by both blocks as `unreadable_indexes` with the path and error and
keeps the exit code at 1 for the whole graph; nothing repairs or deletes it
automatically, and the next 4.1 run refuses to start (`startup_refused`)
until the reviewer has moved the file aside or restored it by hand. A
cleanup `refused` with `carries other identity (job label ..., checkout
label ...)` in its error means a container under the ticket's name does not
carry this ticket's labels: it belongs to another checkout or was created
by hand, it is never removed by the tool, and the reviewer decides by hand.
The child's own cooperative stop (the first thing a stop request triggers)
holds to the same rule: it inspects the exact name, stops only a container
carrying its ticket's labels and only by exact id, and writes what it saw and
decided to `background-jobs\<task>\<job_id>\cooperative-stop.json`; a
refusal there stops nothing and the bounded Job Object termination that
follows the grace period still ends the child's own tree.

```powershell
& {
    $env:PYTHONUTF8 = "1"
    Set-Location "C:\nscrev\throughput"
    python -m Pipeline.AssistantControl --source "C:\NSC\GauntletFresh1140-20260912-1" --checkout-root "C:\NSC\GauntletFresh1140-20260912-1-Checkouts" stop-background-jobs --grace-seconds 15
    Write-Host ("[EXIT] " + $LASTEXITCODE)
}
```

Either way the next 4.1 run reconciles every retained ticket before it plans:
`job_adopted` (a live job carried over, normal after a restart), `job_completed`
/ `job_failed` / `job_died` (harvested, container reconciled), `job_quarantined`
(a live job whose ticket no longer authenticated: stopped exactly, its task
blocked), `job_container_verified` (a pending cleanup proven finally absent;
startup waits a killed decomposition's one-minute bound out first, so a
restart right after a kill can take about a minute before its first plan).
A `startup_refused` event with state `blocked` means the controller would not
plan beside an ambiguous ticket or an unverified container; the reviewer
reads the event's `error` and decides, nothing was killed or removed.

### 4.4 Clearing an ended job (reviewer only; mutating; shape, not paste-ready)

After reading `background-jobs\<task>\<job_id>\stderr.log` and `receipt.json`,
the reviewer runs, with the exact task id and the `job_id` from that task's
`NSC-<n>.background-job.json`:

```text
python -m Pipeline.AssistantControl --source C:\NSC\GauntletFresh1140-20260912-1 --checkout-root C:\NSC\GauntletFresh1140-20260912-1-Checkouts clear-background-job NSC-<n> --job-id <job_id>
```

### 4.5 Agent-session mode (tool calls limited to ten minutes)

An agent session whose tool calls time out after ten minutes cannot run 4.1 in
the foreground. Use the extracted copy of 4.1 at
`C:\nscrev\reports\operator-runner-4-1.ps1` (identical content, regenerated
whenever 4.1 changes, parser-checked) and run it detached:

```powershell
& {
    $LogDir = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts\operator-logs"
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
    $Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $Transcript = Join-Path $LogDir ("runner-" + $Stamp + ".transcript.txt")
    $Errors = Join-Path $LogDir ("runner-" + $Stamp + ".errors.txt")
    $Pointer = Join-Path $LogDir "runner-current.txt"
    if (Test-Path -LiteralPath $Pointer) {
        $Previous = (Get-Content -LiteralPath $Pointer -Raw).Trim()
        $PreviousText = [string](Get-Content -LiteralPath $Previous -Raw -ErrorAction SilentlyContinue)
        if ($PreviousText -notmatch "\[(DONE|BLOCKED)\]") {
            throw "The previous runner transcript has not finished: $Previous. Poll it, or escalate; do not start a second runner."
        }
    }
    $Process = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\nscrev\reports\operator-runner-4-1.ps1") -RedirectStandardOutput $Transcript -RedirectStandardError $Errors -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $Pointer -Value $Transcript -Encoding ascii
    Write-Host ("[RUNNER] started pid " + $Process.Id)
    Write-Host ("[RUNNER] transcript " + $Transcript)
}
```

The start block refuses to start a second runner while the transcript it
recorded in `operator-logs\runner-current.txt` has not finished. Then poll
with this block, repeatedly, until it prints `[POLL] finished` (each call
waits at most four minutes). It reads exactly the transcript the start block
recorded, never "the newest file", so a RESUME that starts a new runner is
polled and an old transcript is never mistaken for the current one:

```powershell
& {
    $LogDir = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts\operator-logs"
    $Pointer = Join-Path $LogDir "runner-current.txt"
    if (-not (Test-Path -LiteralPath $Pointer)) { throw "No runner has been started from this block: $Pointer is missing." }
    $TranscriptPath = (Get-Content -LiteralPath $Pointer -Raw).Trim()
    if (-not (Test-Path -LiteralPath $TranscriptPath)) { throw "Recorded transcript is missing: $TranscriptPath" }
    $Deadline = (Get-Date).AddSeconds(240)
    $Text = ""
    do {
        $Text = [string](Get-Content -LiteralPath $TranscriptPath -Raw -ErrorAction SilentlyContinue)
        if ($Text -match "\[(DONE|BLOCKED)\]") { break }
        Start-Sleep -Seconds 15
    } while ((Get-Date) -lt $Deadline)
    Write-Host ("[TRANSCRIPT] " + $TranscriptPath)
    Get-Content -LiteralPath $TranscriptPath -Tail 30
    if ($Text -match "\[(DONE|BLOCKED)\]") {
        Write-Host "[POLL] finished"
    }
    else {
        Write-Host "[POLL] still running; run this block again"
    }
}
```

The final `[DONE] Operator loop ended with status: X` line is in the
transcript; act on X exactly as in section 7.1. Ctrl+C is not available to a
detached runner; a stop is the reviewer's decision and goes through the
`stop-graph` block in section 4.3 while the controller is running (the
transcript then ends with status `stopped`), or the `stop-background-jobs`
block after the controller process has been lost.

### 4.6 Reading the run

Viewer for this checkout root: http://127.0.0.1:8817/ (read-only; started by Vincent's session with `python -m Pipeline.AssistantControl --source C:\NSC\GauntletFresh1140-20260912-1 --checkout-root C:\NSC\GauntletFresh1140-20260912-1-Checkouts viewer --port 8817` from `C:\nscrev\throughput`; "run scope only" shows the controller's targets). The viewers on 8815 and 8816 belonged to the old 1130 project and are gone.

Journal events of the job mechanism and who acts on them:

- `job_launched`, `job_completed`, `job_stopped`, `job_adopted` (a live job carried across a controller restart), `job_container_verified`, `job_cleanup_pending` (the loop retried a decomposition's container cleanup and it is not final yet, usually because its one-minute bound is still running), `job_cleanup_superseded` (a ticket was cleared or replaced while its cleanup ran; whatever replaced it owes its own cleanup): nobody acts; they are the normal record.
- `job_harvest_deferred`: the loop could not harvest an ended job this cycle (its record could not be read or authenticated) and moved on; the reviewer reads the event's `detail` if it repeats.
- `job_failed`, `job_died`, `job_spawn_failed`, `job_quarantined`: the operator never acts on them; they surface as `blocked` tasks in the loop's final status, which the operator escalates (section 5). The reviewer reads the job's `stderr.log`, `receipt.json` and `provider_container_cleanup`, then decides RESUME (other tasks continue), TICKET, or `clear-background-job` (section 4.4) to allow a fresh attempt; `clear` refuses while the container's one-minute tombstone is active and says when to retry.
- `startup_refused` (with state `blocked`): the reviewer reads the event's `error`; a `refused` container cleanup usually means Docker Desktop was not reachable or another container holds the ticket's name; nothing was killed or removed, and the next 4.1 run re-verifies.
- `stop_request_ignored`: a stale `stop-graph` request was archived; nobody acts.
- A `controller_stopped` event or a `stop-graph` result with a non-empty `cleanup_pending` list: the reviewer runs the `stop-background-jobs` block of 4.3 until it prints `stopped`.

Task ids outside `$Targets` are expected in the operator's `[RUN n]` lines: the decomposer allocates children (NSC-1148 and up) that join the run scope automatically.

## 5. Escalation message (operator → reviewer)

```text
ESCALATION from OPERATOR — <date time>
Loop ended with: <status line from [DONE] or [BLOCKED]>
Exit code of last run-graph: <code>
Last result JSON: <path>
Last 10 lines of the stderr log: 
<paste>
Blocked tasks (task: reason): 
<paste the "blocked" lines>
Background jobs (kind task: status): 
<paste the "job" lines>
Owner status line: <paste [STATE] Previous controller ...>
I have not rerun anything. Waiting for RESUME, STOP or TICKET.
```

Reviewer reply is one word first — `RESUME`, `STOP` or `TICKET` — then the reasoning in a few sentences.

## 6. Ticket (reviewer → implementer)

```text
TICKET <short id> for IMPLEMENTER (Sonnet 5, fresh session)
Goal: <one sentence>
Clone: git clone C:\nscrev\throughput C:\nscrev\impl-<short id>  (branch throughput/background-decomposition; work only there)
Files you may change: <exact list>
Change: <precise description, including function names and the exact behavior>
Tests you must add or update: <exact test names and what they prove>
Tests you must run and paste: python -m unittest <modules>
Commit message: <exact first line>; end with "Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
Forbidden: the live run, C:\nscrev\throughput itself, Tasks/, Assets/, GitHub, Docker, Unity, paid providers, any other file
Report back: commit SHA, changed files, full test output, anything you could not do as written
```

The reviewer integrates with `git -C C:\nscrev\throughput fetch C:\nscrev\impl-<short id> throughput/background-decomposition` and a fast-forward, only while the operator loop is stopped, then reruns the affected tests in `C:\nscrev\throughput` before telling the operator `RESUME` (and updates `$ExpectedControlHead` in 4.1 to the new commit).

## 7. Prompts (complete; paste whole)

### 7.1 OPERATOR — Haiku 4.5, fresh session, working directory C:\nscrev\throughput

```text
You are the gauntlet OPERATOR. Your whole job is to run one fixed PowerShell block and report its result. You do not diagnose, fix, edit files, retry, clear or stop jobs, or change any command or flag.

Facts (never change them):
- Runbook: C:\nscrev\reports\gauntlet-orchestration-staffing.md
- Controller code: C:\nscrev\throughput at commit e90670da5b5fc19567e1efe1cb655c43de292f4e
- Live Source: C:\NSC\GauntletFresh1140-20260912-1 on branch gauntlet-replay/fresh-1140-20260912
- Checkout root: C:\NSC\GauntletFresh1140-20260912-1-Checkouts (records in .assistant-control, your logs in operator-logs)

Your loop:
1. Open the runbook and paste section 4.1 ("Operator runner") into a Windows PowerShell 5.1 window exactly as written.
2. Wait until it prints [DONE] or [BLOCKED]. It may run for a long time. Do not interrupt it and never press Ctrl+C unless Vincent tells you to.
3. Read the line "[DONE] Operator loop ended with status: X" and act on X:
   - complete: tell Vincent "gauntlet complete" and paste the [STATE] lines.
   - awaiting_human: tell Vincent which tasks are waiting (the waiting_human list inside the last result JSON).
   - anything else, [BLOCKED], or no JSON output: write the escalation message from section 5 of the runbook, hand it to Vincent for the REVIEWER session, and stop.
4. Do not run the block again after an escalation until the reviewer answers RESUME.

Allowed: section 4.1, section 4.2 (read-only status and journal tail), reading files under the checkout root's .assistant-control and operator-logs directories, reading the runbook.
Forbidden: editing any file; any git command that changes anything; clear-background-job; stop-background-jobs; Docker; Unity; GitHub; any python command other than sections 4.1 and 4.2; retrying a failed command; changing any flag or path.

If anything is unclear, stop and ask Vincent. Reply in short plain sentences and paste exact output lines rather than paraphrasing them.
```

### 7.2 REVIEWER / INTEGRATOR — Opus 5 at effort xhigh, one session for the whole gauntlet, working directory C:\nscrev\throughput

```text
You are the gauntlet REVIEWER and INTEGRATOR: the only session with judgment authority. An OPERATOR session (Haiku 4.5) runs the controller loop and escalates to you; IMPLEMENTER sessions (Sonnet 5) execute bounded tickets you write. You verify everything they produce and never trust authorship.

Facts:
- Runbook: C:\nscrev\reports\gauntlet-orchestration-staffing.md (read it first, all sections)
- Controller code: C:\nscrev\throughput, branch throughput/background-decomposition, commit e90670da5b5fc19567e1efe1cb655c43de292f4e (6f32664 background jobs, c70a2d9 plan() cache, 24273b6 containment and operator stop, 0c42f0d stop-graph, 67614e7 exact container cleanup and restart reconciliation, 14cd051 window/stop-retry/lock repairs, 62245a1 unfinished-tombstone/reauthentication/ownership/stop-graph repairs, 91a0b0d durable partial cleanup, full identity authentication, concurrency outcomes and unreadable-index repairs, ca56dc7 checkout-exact container identity with ticket labels and refusal-safe cleanup progress, e90670d ownership-verified cooperative stop). Read Pipeline/AssistantControl/README.md, Pipeline/AssistantControl/CURRENT.md and Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md there.
- Live Source: C:\NSC\GauntletFresh1140-20260912-1 on branch gauntlet-replay/fresh-1140-20260912. Checkout root: C:\NSC\GauntletFresh1140-20260912-1-Checkouts.
- Coordination issue: https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36

Rules:
- The live run is read-only unless Vincent explicitly authorizes a specific mutation in this conversation. Never move the Source branch, reset, delete records or run wipe commands. Diagnose from worker outcomes (run_result.json, progress logs), job receipts (background-jobs\<task>\<job_id>\receipt.json and stderr.log) and the journal before touching anything.
- No paid providers, no push, no merge, no GitHub state changes; comments on Issue #36 only when Vincent asks.
- Do not edit C:\nscrev\throughput while the operator loop is running. To stop a running controller (including the detached runner of section 4.5) use the stop-graph block in section 4.3; use stop-background-jobs after the controller process was lost, and again whenever a stop result lists cleanup_pending, until it prints stopped. Fixes go through implementer tickets (runbook section 6) in their own clones, or your own edits in C:\nscrev\throughput only after the loop has ended and stop-background-jobs reports stopped with no jobs. Every fix is a separate commit with tests; follow CLAUDE.md, the engineering standards and the operator command standards.
- Verify every implementer result by reading its diff and running its tests yourself in C:\nscrev\throughput after integrating. Then update $ExpectedControlHead in runbook section 4.1 to the new commit before telling the operator RESUME.
- Answer every escalation with one word first, RESUME, STOP or TICKET, then the reasoning in a few sentences. STOP means wait for Vincent.
- A failed, died, cancelled or quarantined background job blocks only its task and is never relaunched automatically; you decide whether clear-background-job is justified, after reading the receipt, stderr and provider_container_cleanup (the command refuses until the container is verified absent and its one-minute tombstone has passed; it tells you when to retry). A startup_refused event means the controller refused to plan beside an ambiguous ticket or an unverified container; read its error before anything else.

First actions now: read the runbook; read graph-controller.json, graph-controller-owner.json, the last 40 journal events and every NSC-*.background-job.json in the checkout root's .assistant-control; summarize the gauntlet state to Vincent in under 15 lines; say whether the operator may start and which risk you will watch first (the first concurrent Unity validations under --background-jobs 2).
```

### 7.3 IMPLEMENTER — Sonnet 5, fresh session per ticket, working directory C:\nscrev

```text
You are the IMPLEMENTER for exactly one ticket, pasted below. Do what the ticket says and nothing more.

Rules:
- Work only in the clone the ticket names (create it with the git clone command in the ticket). Never edit C:\nscrev\throughput, the live run under C:\NSC, Tasks/, Assets/, GitHub, Docker or Unity, and never launch a paid provider.
- Change only the files the ticket lists. Add or update exactly the tests it names. Run the tests it names and paste the full output.
- Commit in your clone with the commit message the ticket gives. Do not push.
- If the ticket cannot be done as written, or you would need to change a file it does not list, stop and report why instead of improvising.
- Report back with: commit SHA, changed files, the full test output, and anything you could not do.

TICKET:
<paste the ticket here>
```

## 8. How to start the trial

1. Start the REVIEWER session (Opus 5, effort xhigh) with prompt 7.2. Wait for its state summary and its go/no-go.
2. Start the OPERATOR session (Haiku 4.5) with prompt 7.1. Its first act is pasting block 4.1.
3. Relay escalations and answers between the two windows. Start an IMPLEMENTER session (Sonnet 5, prompt 7.3) only when the reviewer hands you a ticket.
4. Judge the trial by three things: whether the operator ever had to think (it should not), whether every escalation was answered with a verifiable RESUME/STOP/TICKET, and whether the gauntlet finished without a human touching the records.

What to watch in the journal for the new mechanism: `job_launched`, `job_adopted` (after a restart), `job_completed`, `job_failed`, `job_died`, `job_stopped`, `job_quarantined`, `job_container_verified`, `startup_refused`; `provider_container_cleanup` on every decomposition job index (a kill-path cleanup watches the name for 15 s, so a died or stopped decomposition delays the next plan by about that much); and `background_jobs` in graph-controller.json. The first cycle after a Source move costs about 5 s; later cycles under a second.
