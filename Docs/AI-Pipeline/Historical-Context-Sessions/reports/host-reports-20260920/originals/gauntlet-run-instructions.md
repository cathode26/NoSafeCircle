# Gauntlet NSC-1140..NSC-1147 — operator guide for the reviewed asynchronous AssistantControl graph controller

Written 2026-09-12. Every command in this file was written against code read in
`C:\NSC\GauntletFresh1140-20260912-1` on branch `gauntlet-test/throughput-e90670d`
(the reviewed anchor `3e5314d0511db15d98f386e5d31c8849a8d9c957`; the branch advanced
to `4f46117fff7504280b79ff30d762b0baa666d225` while this was being written — see
section 1.2). Claims are cited to the file they came from. Anything that could not be
proven from code or a durable record is marked **UNVERIFIED** inline. Section 12 is
the full verification ledger; section 13 lists what in the older runbook is wrong for
this project.

This supersedes `C:\nscrev\reports\gauntlet-orchestration-staffing.md` for **this**
run. That file still targets the same task family but runs the controller from the
`C:\nscrev\throughput` clone and uses the retired checkout root; do not paste its
blocks here.

---

## 1. Purpose and non-negotiable rules

### 1.1 Purpose

Run the eight-root synthetic gauntlet NSC-1140..NSC-1147 end to end under one
`run-graph` controller carrying the ten reviewed AssistantControl performance
commits, and measure whether asynchronous decomposition and post-crew validation
actually overlap with unrelated work (section 8). The gauntlet is a **test
gauntlet**: its tasks create trivial C# constant classes, nothing about the real
game.

### 1.2 Fixed identity

| Thing | Value |
|---|---|
| Controller project **and** Source | `C:\NSC\GauntletFresh1140-20260912-1` |
| Branch (also the `--target-branch`) | `gauntlet-test/throughput-e90670d` |
| Controller anchor (must be an ancestor of HEAD) | `3e5314d0511db15d98f386e5d31c8849a8d9c957` |
| Gauntlet family commit (must be an ancestor of HEAD) | `bdaaa2d153a0504c471fbd66afd70f1984b171d9` |
| Reviewed throughput head that was cherry-picked | `e90670da5b5fc19567e1efe1cb655c43de292f4e` in `C:\nscrev\throughput` |
| HEAD when this guide was finished | `4f46117fff7504280b79ff30d762b0baa666d225` |
| Checkout root for this run | `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2` |
| Records | `<checkout root>\.assistant-control` |
| Worker config | `C:\NSC\GauntletFresh1140-20260912-1\Pipeline\AssistantControl\worker-haiku.example.json` |
| Viewer | `http://127.0.0.1:8817/` |
| Report issue | https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36 |

**Branch identity is asserted by ancestry, not by equality.** At `3e5314d` the
project's `Pipeline/AssistantControl` tree was
`9195da84a09968e603222d71ff779261fcf9f1f8` — byte-identical to
`C:\nscrev\throughput` at `e90670da5b...`, verified in both repositories. While this
guide was being written the branch advanced by one commit,
`4f46117 AssistantControl viewer: serve only the explicit run roots and their
generated descendants`, which touches `Pipeline/AssistantControl/viewer.py`,
`__main__.py` and `test_viewer.py`, so the tree at HEAD is now
`f9cab0ff85087f7af9d89ad928001b38e57aa9e7`. Both `bdaaa2d` and `3e5314d` remain
ancestors of HEAD (verified), which is exactly what the preflight and the runner
check. The byte-identity claim therefore belongs to `3e5314d`; anything committed
above it is a local change on top of the reviewed head and must be reviewed on its
own merits before the run starts. Record the actual HEAD in the final report.

Unlike the older runbook, **the controller runs from the 1140 project itself**:

```text
cd C:\NSC\GauntletFresh1140-20260912-1
python -m Pipeline.AssistantControl ...
```

There is no separate controller clone in this run. That has one consequence worth
repeating: the Python the controller and every detached child imports is the
*working tree* of this project, not a commit. Editing `Pipeline/AssistantControl`
while the loop runs means a half-written module can be imported by the next child.

### 1.3 Rules that bind everyone

1. **Only this project and this branch.** Never `C:\NSC\NSC\NoSafeCircle`, never
   GitHub `main`, never the 1130 project, never a production Issue, never a real
   game task. NSC-042 and every real game task are out of scope and must never be
   run; `NSC-042` is additionally hard-reserved for human review by the code itself
   (`graph_controller.py:245`, `__main__.py:266`).
2. **No push, no merge, no GitHub state change** other than the final report comment
   on Issue #36 when Vincent asks. `integrate` is a local fast-forward only
   (`Pipeline/AssistantControl/README.md`, "Workflow").
3. **Fresh checkout root only.** Use
   `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2`. The older root
   `C:\NSC\GauntletFresh1140-20260912-1-Checkouts` holds the durable evidence of two
   failed `prepare NSC-1141` attempts (section 1.4). Do not reuse it, do not reset
   it, do not repair it, do not delete anything under it. The runner in section 4.2
   refuses to start if it is pointed at that path.
4. **Never edit the controller project while the loop runs.** No edits under
   `Pipeline/AssistantControl`, no branch moves, no `git reset`, no `git clean`.
   Fixes wait for the loop to end.
5. **One controller.** The controller holds an exclusive lock at
   `<records>\graph-controller.lock` (`graph_controller.py:304-310`); a second
   `run-graph` raises `ControllerOwnerActiveError`. Do not try to get around it.
6. **Stop with the reviewed stop command.** On any correctness or ownership problem
   — a task moving that should not, a worker or container that does not belong to
   this run, a record that disagrees with the viewer — run `stop-graph`
   (section 6.1) and preserve everything. Never kill by PID, never `docker rm` by
   hand, never edit a record.
7. **Provider spend is explicit.** Paid work happens only through
   `run-graph --authorize-provider-spend`. Nothing else may launch a provider
   (`graph_controller.py:968-970`, `__main__.py:438`).
8. **A failed, died, cancelled or quarantined background job blocks only its task
   and is never relaunched automatically** (`Pipeline/AssistantControl/README.md`,
   graph-controller section). Only the reviewer decides on `clear-background-job`,
   and only after section 7.2.

### 1.4 The evidence in the retired checkout root — leave it alone

`C:\NSC\GauntletFresh1140-20260912-1-Checkouts\.assistant-control` contains, read
read-only on 2026-09-12:

- `graph-controller-owner.json`: `controller_released`, `pid 50168`, outcome
  `exception`, `error_type RuntimeError`, released `2026-09-12T12:36:03.746127+00:00`.
- `graph-controller.json`: `status: blocked`, `last_error` beginning
  `RuntimeError: Cloning into 'C:\NSC\GauntletFresh1140-20260912-1-Checkouts\.NSC-1141-1f71147ac9c44d36a1b3e99dddf239af'... sh.exe: *** fatal error - couldn't create signal pipe, Win32 error 5`.
- `graph-controller-events.jsonl`: 8 events — two `controller_started` /
  `action_started prepare NSC-1141` / `action_failed` / `controller_released`
  cycles at `12:35:21Z` and `12:36:03Z`.
- `NSC-1141.json`, `project.json`, the two lock files. No `background-jobs`
  directory: no paid work ever started there.

Correction to the tasking brief: there were two failed attempts, but they were two
*different* controller invocations (`cad1ba10f7804ec5ad0882668191c54f` at 12:35:21Z
and `57490ad7f1dd4e5abda85d96c6139dde` at 12:36:03Z). The retained owner record
names only the second one's PID, 50168.

That MSYS `sh.exe` "couldn't create signal pipe, Win32 error 5" failure is a Windows
host condition inside `git clone` (`checkouts.py:121` clones `--no-local
--no-checkout` into a `.NSC-<task>-<hex>` staging directory). It is the single most
likely way this run fails early again. If it recurs in the fresh root, it is a host
problem, not a controller defect: escalate, do not retry in a loop.

---

## 2. Prerequisites and preflight

Windows PowerShell 5.1. No `&&`, no placeholders. Paste each block whole. Every
block in this section is **read-only**: `docker version` and `docker volume ls`
query the daemon and change nothing; `graph-plan` is documented as
"Show the next bounded graph actions without mutating or starting providers"
(`__main__.py:153-155`) and takes no lock and writes no state (`__main__.py:300`).

> **The checkout root is no longer fresh.** At 21:59–22:02 UTC on 2026-09-12, after
> this guide's read-only dry run and while it was being finished, another session
> ran a controller against
> `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2`. Observed read-only at 22:10 UTC:
> `graph-controller-owner.json` says `controller_released`, pid 9320, invocation
> `c03c130473324944843a7fc0fd861cab`, outcome `returned`; checkouts exist for
> NSC-1141..NSC-1144 and all four workers were started and settled; and
> `NSC-1140.background-job.json` plus `NSC-1140.decomposition.json` exist, with a
> `job_completed` event for the NSC-1140 `decompose` job carrying
> `result_status: failed`.
>
> Everything in this guide still applies — the preflight and the runner are written
> to *observe* the root rather than demand an empty one, and they proceed only while
> the owner record says `controller_released`. But before anything is started again:
> read the journal and `NSC-1140.decomposition.json`, decide with the reviewer
> whether the failed NSC-1140 decomposition needs `clear-background-job`
> (section 7.2), and treat the measurement in section 8 as covering *all*
> invocations in the journal, not just the next one. Do not delete the root to get a
> clean start; that would destroy the evidence of the failure.

### 2.1 Preflight block (read-only)

```powershell
& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    $Source = "C:\NSC\GauntletFresh1140-20260912-1"
    $ExpectedBranch = "gauntlet-test/throughput-e90670d"
    $GauntletCommit = "bdaaa2d153a0504c471fbd66afd70f1984b171d9"
    $ThroughputCommit = "3e5314d0511db15d98f386e5d31c8849a8d9c957"
    $CheckoutRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2"
    $ForbiddenRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts"
    $Records = Join-Path $CheckoutRoot ".assistant-control"
    $WorkerConfig = Join-Path $Source "Pipeline\AssistantControl\worker-haiku.example.json"
    $Targets = @("NSC-1140", "NSC-1141", "NSC-1142", "NSC-1143", "NSC-1144", "NSC-1145", "NSC-1146", "NSC-1147")
    $CurrentPhase = "identity"

    # Native processes decide success by exit code, and machine data comes from
    # stdout only, so a Git or Docker warning can never become a SHA or a name.
    function Invoke-Native {
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

            return [pscustomobject]@{
                ExitCode = [int]$Code
                StdOut = @(Get-Content -LiteralPath $StdOutPath)
                StdErr = @(Get-Content -LiteralPath $StdErrPath)
            }
        }
        finally {
            Remove-Item -LiteralPath $StdOutPath -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $StdErrPath -Force -ErrorAction SilentlyContinue
        }
    }

    function Get-NativeText {
        param(
            [Parameter(Mandatory = $true)]
            [string]$FilePath,

            [Parameter()]
            [string[]]$ArgumentList = @()
        )

        $Result = Invoke-Native -FilePath $FilePath -ArgumentList $ArgumentList
        if ($Result.ExitCode -ne 0) {
            $Result.StdErr | ForEach-Object { Write-Host ("[STDERR] " + $_) }
            throw ($FilePath + " " + ($ArgumentList -join " ") + " failed with exit code " + $Result.ExitCode + ".")
        }
        return (($Result.StdOut -join "`n").Trim())
    }

    try {
        # ========================================================
        # PHASE 1 - PATHS AND IDENTITY
        # ========================================================
        $CurrentPhase = "paths"
        Write-Host "[PHASE] paths and identity"
        if ([System.IO.Path]::GetFullPath($CheckoutRoot).TrimEnd("\") -eq [System.IO.Path]::GetFullPath($ForbiddenRoot).TrimEnd("\")) {
            throw "Refusing to preflight the retired checkout root."
        }
        foreach ($Path in @($Source, $WorkerConfig)) {
            if (-not (Test-Path -LiteralPath $Path)) { throw "Missing path: $Path" }
        }
        Write-Host ("[PASS] worker config " + $WorkerConfig)

        $Branch = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "branch", "--show-current")
        if ($Branch -ne $ExpectedBranch) { throw "Source is on '$Branch', expected '$ExpectedBranch'." }
        $Head = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "rev-parse", "HEAD")
        Write-Host ("[PASS] branch " + $Branch + " head " + $Head)

        foreach ($Anchor in @($GauntletCommit, $ThroughputCommit)) {
            $Ancestry = Invoke-Native -FilePath "git" -ArgumentList @("-C", $Source, "merge-base", "--is-ancestor", $Anchor, $Head)
            if ($Ancestry.ExitCode -ne 0) { throw ("HEAD does not contain the required commit " + $Anchor + ".") }
        }
        Write-Host "[PASS] both anchor commits are ancestors of HEAD"

        $AssistantControlTree = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "rev-parse", "HEAD:Pipeline/AssistantControl")
        Write-Host ("[STATE] Pipeline/AssistantControl tree " + $AssistantControlTree)
        Write-Host "[STATE] reviewed tree at e90670da5b5fc19567e1efe1cb655c43de292f4e is 9195da84a09968e603222d71ff779261fcf9f1f8"

        # ========================================================
        # PHASE 2 - CLEAN TREE
        # ========================================================
        $CurrentPhase = "clean-tree"
        Write-Host "[PHASE] working tree"
        $Tracked = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "status", "--porcelain=v1", "--untracked-files=no")
        if (-not [string]::IsNullOrWhiteSpace($Tracked)) {
            throw ("The controller project has uncommitted edits. The controller and every detached child import this working tree. Commit or stash first:`n" + $Tracked)
        }
        Write-Host "[PASS] tracked tree is clean"

        # ========================================================
        # PHASE 3 - THE EIGHT CONTRACTS
        # ========================================================
        $CurrentPhase = "contracts"
        Write-Host "[PHASE] committed contracts"
        foreach ($Task in $Targets) {
            $Exists = Invoke-Native -FilePath "git" -ArgumentList @("-C", $Source, "cat-file", "-e", ("HEAD:Tasks/" + $Task + ".yaml"))
            if ($Exists.ExitCode -ne 0) { throw ("Committed contract missing: Tasks/" + $Task + ".yaml") }
        }
        Write-Host "[PASS] all eight committed contracts are present at HEAD"

        # ========================================================
        # PHASE 4 - DOCKER (READ-ONLY)
        # ========================================================
        $CurrentPhase = "docker"
        Write-Host "[PHASE] docker"
        $DockerVersion = Invoke-Native -FilePath "docker" -ArgumentList @("version", "--format", "{{.Server.Version}}")
        if ($DockerVersion.ExitCode -ne 0) {
            $DockerVersion.StdErr | ForEach-Object { Write-Host ("[STDERR] " + $_) }
            throw "Docker Desktop is not reachable. Start it and rerun; do not start the controller."
        }
        Write-Host ("[PASS] docker server " + (($DockerVersion.StdOut -join "").Trim()))

        $Config = Get-Content -LiteralPath $WorkerConfig -Raw -Encoding UTF8 | ConvertFrom-Json
        $Volume = [string]$Config.credential_volume
        $VolumeList = Invoke-Native -FilePath "docker" -ArgumentList @("volume", "ls", "--format", "{{.Name}}")
        if ($VolumeList.ExitCode -ne 0) { throw "docker volume ls failed." }
        if (@($VolumeList.StdOut) -notcontains $Volume) { throw ("Credential volume '" + $Volume + "' named by the worker config is absent.") }
        Write-Host ("[PASS] credential volume " + $Volume + " present; provider " + $Config.provider + " model " + $Config.execution_model)

        # ========================================================
        # PHASE 5 - CHECKOUT ROOT AND SOURCE-SCOPED ADMISSIONS
        # ========================================================
        $CurrentPhase = "state"
        Write-Host "[PHASE] durable state"
        if (Test-Path -LiteralPath $Records) {
            Write-Host ("[STATE] records already exist: " + $Records)
            Get-ChildItem -LiteralPath $Records | ForEach-Object { Write-Host ("    " + $_.Name) }
        }
        else {
            Write-Host "[PASS] checkout root holds no .assistant-control yet (first run creates it)"
        }

        $AdmissionPath = Join-Path $Source ".git\assistant-control-admissions.json"
        if (Test-Path -LiteralPath $AdmissionPath) {
            $Admissions = Get-Content -LiteralPath $AdmissionPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($Reservation in @($Admissions.reservations)) {
                if ($null -eq $Reservation) { continue }
                Write-Host ("[STATE] reservation " + $Reservation.task_id + " -> " + $Reservation.checkout_root)
                if ($Reservation.checkout_root -ne $CheckoutRoot) {
                    throw "A reservation from another checkout root is consuming this Source's capacity. Escalate; do not edit the registry."
                }
            }
        }
        else {
            Write-Host "[PASS] no Source-scoped admission reservations"
        }

        # ========================================================
        # PHASE 6 - PORT 8817
        # ========================================================
        $CurrentPhase = "port"
        Write-Host "[PHASE] viewer port"
        $Listener = @(Get-NetTCPConnection -LocalPort 8817 -State Listen -ErrorAction SilentlyContinue)
        if ($Listener.Count -eq 0) {
            Write-Host "[STATE] port 8817 is free; start the viewer with section 3.1"
        }
        else {
            foreach ($Connection in $Listener) {
                $Owner = Get-Process -Id $Connection.OwningProcess -ErrorAction SilentlyContinue
                Write-Host ("[STATE] port 8817 held by pid " + $Connection.OwningProcess + " (" + $Owner.ProcessName + "); confirm its identity with section 3.2 before trusting it")
            }
        }

        # ========================================================
        # PHASE 7 - GRAPH-PLAN DRY RUN (READ-ONLY)
        # ========================================================
        $CurrentPhase = "graph-plan"
        Write-Host "[PHASE] graph-plan dry run"
        Set-Location $Source
        $TargetArguments = @()
        foreach ($Task in $Targets) { $TargetArguments += @("--task", $Task) }
        $PlanArguments = @(
            "-m", "Pipeline.AssistantControl",
            "--source", $Source,
            "--checkout-root", $CheckoutRoot,
            "graph-plan"
        ) + $TargetArguments + @(
            "--auto-approve-gauntlet",
            "--capacity", "3",
            "--target-branch", $ExpectedBranch,
            "--background-jobs", "4"
        )
        $PlanResult = Invoke-Native -FilePath "python" -ArgumentList $PlanArguments
        if ($PlanResult.ExitCode -ne 0) {
            $PlanResult.StdErr | ForEach-Object { Write-Host ("[STDERR] " + $_) }
            throw ("graph-plan failed with exit code " + $PlanResult.ExitCode + ".")
        }
        $Plan = ($PlanResult.StdOut -join "`n") | ConvertFrom-Json
        $InScope = @($Plan.in_scope)
        $Unexpected = @($InScope | Where-Object { $Targets -notcontains $_ })
        $Missing = @($Targets | Where-Object { $InScope -notcontains $_ })
        if ($Unexpected.Count -ne 0) { throw ("graph-plan pulled tasks outside the eight roots into scope: " + ($Unexpected -join ", ")) }
        if ($Missing.Count -ne 0) { throw ("graph-plan did not place these roots in scope: " + ($Missing -join ", ")) }
        Write-Host ("[PASS] in_scope is exactly the eight roots; status " + $Plan.status)
        foreach ($Action in @($Plan.next_actions)) { Write-Host ("    next " + $Action.kind + " " + $Action.task_id) }
        foreach ($Blocked in @($Plan.blocked)) { Write-Host ("    blocked " + $Blocked.task_id + ": " + $Blocked.reason) }

        Write-Host ""
        Write-Host "============================================================"
        Write-Host "[DONE] PREFLIGHT PASSED"
        Write-Host "============================================================"
        Write-Host ("[STATE] Source:        " + $Source + " @ " + $Head)
        Write-Host ("[STATE] Branch:        " + $Branch)
        Write-Host ("[STATE] Checkout root: " + $CheckoutRoot)
        Write-Host "[NEXT] Start or verify the viewer (section 3), then start the runner (section 4.3)."
    }
    catch {
        Write-Host ""
        Write-Host ("[BLOCKED] Preflight failed in phase " + $CurrentPhase)
        Write-Host ("[ERROR] " + $_.Exception.Message)
        Write-Host "[RECOVERY] Nothing was mutated. Do not start the controller. Escalate."
        throw
    }
}
```

### 2.2 What the dry run must print

On a genuinely fresh root the `graph-plan` output is exactly this shape (verified by
running it read-only on 2026-09-12 against
`C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2`):

```text
status                 actionable
targets / in_scope     NSC-1140 .. NSC-1147 (eight, nothing else)
next_actions           decompose NSC-1140
                       prepare NSC-1141 / 1142 / 1143 / 1144
blocked                NSC-1145 dependencies [NSC-1141]
                       NSC-1146 dependencies [NSC-1145]
                       NSC-1147 dependencies [NSC-1146]
background_jobs        []
provider_spend_authorized  false
mutations_performed        false
```

`provider_spend_authorized: false` is correct here — `graph-plan` has no
`--authorize-provider-spend` flag at all (`__main__.py:153-162`).

### 2.3 The task family (verified from the committed contracts)

| Task | `execution_scope` | `depends_on` |
|---|---|---|
| NSC-1140 | `needs_execution_decomposition` | — |
| NSC-1141 | `single_agent` | — |
| NSC-1142 | `single_agent` | — |
| NSC-1143 | `single_agent` | — |
| NSC-1144 | `single_agent` | — |
| NSC-1145 | `needs_execution_decomposition` | NSC-1141 |
| NSC-1146 | `needs_execution_decomposition` | NSC-1145 |
| NSC-1147 | `single_agent` | NSC-1146 |

All eight are `contract_disposition: active`; none registers a `unity_builder`, so
`post_crew` here is candidate registration without a Unity materialization step
(`Pipeline/AssistantControl/README.md`, background-jobs paragraph). Each of 1140,
1145 and 1146 is a paid **two-provider** decomposition proposal
(`--providers claude,codex`, `graph_controller.py:998-1005`) that yields two
children; the decomposer allocates them at the next free ids, so expect NSC-1148
upward. Child ids joining the run are expected in the `[RUN n]` lines and in the
viewer.

---

## 3. The viewer

### 3.1 Starting it (detached, hidden, read-only)

The viewer serves only the graph; every POST/PUT/PATCH/DELETE is refused with 405
(`viewer.py:879-884`). It starts no workers.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $Source = "C:\NSC\GauntletFresh1140-20260912-1"
    $CheckoutRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2"
    New-Item -ItemType Directory -Force -Path $CheckoutRoot | Out-Null
    $Out = Join-Path $CheckoutRoot "viewer-8817.log"
    $Err = Join-Path $CheckoutRoot "viewer-8817.err.log"
    $Arguments = @(
        "-m", "Pipeline.AssistantControl",
        "--source", $Source,
        "--checkout-root", $CheckoutRoot,
        "viewer", "--port", "8817"
    )
    $Process = Start-Process -FilePath "python" -ArgumentList $Arguments -WorkingDirectory $Source -RedirectStandardOutput $Out -RedirectStandardError $Err -WindowStyle Hidden -PassThru
    Write-Host ("[VIEWER] started pid " + $Process.Id)
    Write-Host ("[VIEWER] stdout " + $Out)
    Write-Host ("[VIEWER] stderr " + $Err)
    Write-Host "[NEXT] Confirm identity with section 3.2 before trusting the page."
}
```

The port is held exclusively: `_ExclusiveHTTPServer` sets `SO_EXCLUSIVEADDRUSE` and
turns `allow_reuse_address` off, so a second viewer on 8817 fails at bind with
`ExclusiveListenerError` instead of silently sharing the port
(`viewer.py:34-67`). If the block reports a bind failure, a viewer is already there
— verify it, do not force it.

### 3.2 Verifying you reached the right viewer (read-only)

```powershell
& {
    $ErrorActionPreference = "Stop"
    $Response = Invoke-RestMethod -Uri "http://127.0.0.1:8817/api/state" -TimeoutSec 20
    Write-Host ("[VIEWER] pid " + $Response.viewer_identity.pid + " instance " + $Response.viewer_identity.instance_id)
    Write-Host ("[VIEWER] source " + $Response.viewer_identity.source)
    Write-Host ("[VIEWER] checkout_root " + $Response.viewer_identity.checkout_root)
    Write-Host ("[RUN] source_commit " + $Response.run.source_commit + " branch " + $Response.run.source_branch)
    Write-Host ("[RUN] targets " + (@($Response.run.targets) -join ", "))
    if ($Response.run.scope) {
        Write-Host ("[SCOPE] run_scope_only " + $Response.run.scope.run_scope_only + " source " + $Response.run.scope.source)
        Write-Host ("[SCOPE] roots " + (@($Response.run.scope.roots) -join ", "))
        Write-Host ("[SCOPE] generated " + (@($Response.run.scope.generated) -join ", "))
        Write-Host ("[SCOPE] hidden_count " + $Response.run.scope.hidden_count)
    }
    Write-Host ("[TASKS] " + @($Response.tasks).Count + " rows served")
    foreach ($Row in @($Response.tasks)) { Write-Host ("    " + $Row.id + " " + $Row.state) }
}
```

`viewer_identity` is per-process and immutable (`viewer.py:869-877, 910-916`): its
`checkout_root` **must** be `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2`. If it
names the retired root, you are looking at the wrong viewer.

### 3.3 What "eight nodes" must look like

Before the first decomposition lands: exactly eight task rows, ids NSC-1140 through
NSC-1147, `hidden_count` equal to every other committed contract in the project
(the project carries ~100+ `Tasks/NSC-*.yaml` files, so this number is large and
that is correct). After a decomposition is applied: eight roots plus the generated
children (NSC-1148 upward), still nothing else.

Scope behaviour, as committed in `4f46117`: the run scope is derived
by `AssistantSnapshot._apply_controller_scope` (`viewer.py:473-512`) from the
explicit roots — the roots themselves plus every **active** contract whose parent
chain leads to one of them, never a root's dependencies, never a root's own parent,
never a cancelled contract, never another root's child. `run.targets` preserves the
controller's target list as given; the derived scope is reported beside it under
`run.scope` (`run_scope_only`, `source`, `roots`, `missing`, `excluded_roots`,
`generated`, `visible`, `hidden_count`). `_restrict_to_run_scope`
(`viewer.py:515-525`) then removes out-of-scope rows from the response entirely, so
nothing a browser computes can be influenced by them. A `graph-controller.json`
with explicit targets takes precedence over roots given at viewer launch
(`viewer.py:86-95, 141-145`).

The launch flag for those roots is `--task`, repeatable, on the `viewer`
subcommand (`__main__.py:51-54`), committed in `4f46117`:

```text
python -m Pipeline.AssistantControl --source C:\NSC\GauntletFresh1140-20260912-1 --checkout-root C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2 viewer --port 8817 --task NSC-1140 --task NSC-1141 --task NSC-1142 --task NSC-1143 --task NSC-1144 --task NSC-1145 --task NSC-1146 --task NSC-1147
```

**Caveat:** the viewer section of `Pipeline/AssistantControl/README.md` was **not**
updated by that commit and still does not mention `--task` or the run scope
(verified against the README at HEAD). Confirm the flag with
`python -m Pipeline.AssistantControl viewer --help` at run time, not from the
README. Once a controller record exists the flag is not needed at all, because the
controller's targets win (`viewer.py:141-145`), which is why section 3.1 starts the
viewer without it.

### 3.4 When a viewer restart is allowed

Allowed: before the controller starts; when `viewer_identity.checkout_root` is wrong;
when the viewer process is gone; after the viewer code itself changes (a running
viewer serves the code it imported at start — the scope change in 3.3 will not
appear until it is restarted). Restarting is safe at any time because the viewer
only reads.

Not a reason to restart: a task that looks stuck, a red node, a blank page, a
decomposition that has not appeared. Those are questions for the durable records
(section 5). A viewer failure is never a reason to touch the run.

---

## 4. The controller run

### 4.1 The exact `run-graph` command

```powershell
python -m Pipeline.AssistantControl `
  --source C:\NSC\GauntletFresh1140-20260912-1 `
  --checkout-root C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2 `
  run-graph `
  --task NSC-1140 --task NSC-1141 --task NSC-1142 --task NSC-1143 `
  --task NSC-1144 --task NSC-1145 --task NSC-1146 --task NSC-1147 `
  --worker-config C:\NSC\GauntletFresh1140-20260912-1\Pipeline\AssistantControl\worker-haiku.example.json `
  --human-review-task NSC-042 `
  --auto-approve-gauntlet `
  --authorize-provider-spend `
  --capacity 3 `
  --target-branch gauntlet-test/throughput-e90670d `
  --max-actions 240 `
  --background-jobs 4
```

Run it from `C:\NSC\GauntletFresh1140-20260912-1`. In practice use the runner of
section 4.2/4.3 rather than this single invocation; this is the authority for what
the runner sends.

| Flag | Meaning (source) |
|---|---|
| `--source` | The project whose committed `Tasks/` are the graph and whose HEAD every checkout is cloned from. Global option (`__main__.py:37`). |
| `--checkout-root` | Where per-task checkouts and `.assistant-control` records live. Required outside the source project (`__main__.py:238`). |
| `--task` (x8) | Target roots; repeat per root. Duplicates are collapsed in order (`__main__.py:268`). Committed descendants and transitive prerequisites are pulled into scope automatically (README, graph-controller section). |
| `--worker-config` | Required unless `--delegate-safe`; parsed as a JSON object (`__main__.py:284-292`). We use the checked-in `worker-haiku.example.json`: provider `claude`, model `claude-haiku-4-5-20251001`, credential volume `nosafecircle_claude-config`, `timeout_seconds` 900, `enable_session_pool` false. |
| `--human-review-task NSC-042` | Explicit and redundant — NSC-042 is added unconditionally (`__main__.py:266`) and `GraphPolicy` refuses to construct without it (`graph_controller.py:245`). Keep it as a visible statement of intent. |
| `--auto-approve-gauntlet` | Lets the controller approve **authenticated synthetic gauntlet** candidates itself instead of parking them in `waiting_human` (`graph_controller.py:768-783`, via `automation_policy.is_synthetic_gauntlet`). Without it the run stops at `awaiting_human` on the first candidate. |
| `--authorize-provider-spend` | The only way `decompose` and `start_worker` may run; everything provider-shaped raises `Graph provider work requires --authorize-provider-spend` without it (`graph_controller.py:968-970`). Cannot be combined with `--delegate-safe` (`__main__.py:280-283`). |
| `--capacity 3` | Maximum simultaneous admission reservations. `capacity_full = len(reservations) >= capacity` (`graph_controller.py:1386`), and `reserve` itself refuses past it (`admission.py:299`). The registry is **Source-scoped**, not checkout-scoped (section 5.6), so this bounds every worker against this Source. 3 is the floor the owner asked for; raise it only with Vincent's word. |
| `--target-branch` | Asserted against the Source's actual branch at every snapshot; a mismatch raises before anything runs (`graph_controller.py:426-428`). It is also the branch `integrate` fast-forwards. |
| `--max-actions 240` | Durable transitions per invocation; on reaching it the run returns `action_limit_reached` (`graph_controller.py:1589, 1629`) and the runner simply invokes again. |
| `--background-jobs 4` | Concurrent owned background jobs (`decompose`, `post_crew`). A launch past the limit is deferred and the loop waits on a running job instead (`graph_controller.py:1398-1407, 1464-1470`). Default is 4 (`__main__.py:197-200`). |

Not used here, and why: `--once` (one transition per process — too slow for a long
run), `--delegate-safe` (setup only; rejects provider spend), `--scope-dir`
(explicit scope-plan overrides; the automatic plan is correct for these contracts),
`--providers` / `--compose-project` (defaults `claude,codex` and `nosafecircle` are
what the decomposition tickets are meant to use).

### 4.2 The extracted runner

The runner is at `C:\nscrev\reports\gauntlet-run-runner.ps1` — parser-checked with
`C:\nscrev\reports\parse-check.ps1 -ScriptPath C:\nscrev\reports\gauntlet-run-runner.ps1`
(prints `[PARSE] OK`). It is the paste-ready block for a human window **and** the
file the detached start block of section 4.3 runs. Regenerate and re-parse-check it
whenever anything in section 4.1 changes.

> **Collision warning.** A second runner file,
> `C:\nscrev\reports\gauntlet-run-1140-runner.ps1`, was written by another session
> while this guide was being finished. It targets the same eight roots, the same
> checkout root and the same `--capacity 3 --background-jobs 4`, but pins
> `$ExpectedControlHead = 4f46117fff7504280b79ff30d762b0baa666d225` instead of
> checking ancestry. **Only one runner may be used for this run.** Decide with
> Vincent which file the operator pastes, then delete or rename the other before
> anything starts, so no session can begin a second controller by pasting the wrong
> file. The operator prompt in section 9.5.1 names
> `C:\nscrev\reports\gauntlet-run-runner.ps1`; change it there too if the other file
> wins.

Its content, verbatim:

```powershell
& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    # ============================================================
    # IDENTITY
    # ============================================================
    $Source = "C:\NSC\GauntletFresh1140-20260912-1"
    $ExpectedBranch = "gauntlet-test/throughput-e90670d"
    $GauntletCommit = "bdaaa2d153a0504c471fbd66afd70f1984b171d9"
    $ThroughputCommit = "3e5314d0511db15d98f386e5d31c8849a8d9c957"
    $CheckoutRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2"
    $ForbiddenRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts"
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
            [string[]]$ArgumentList = @(),

            [Parameter()]
            [int[]]$AllowedExitCodes = @(0)
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

            if ($AllowedExitCodes -notcontains $Code) {
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

    function Test-Ancestor {
        param(
            [Parameter(Mandatory = $true)]
            [string]$Repository,

            [Parameter(Mandatory = $true)]
            [string]$Ancestor,

            [Parameter(Mandatory = $true)]
            [string]$Descendant
        )

        $Previous = $ErrorActionPreference
        $Code = 1
        try {
            $ErrorActionPreference = "Continue"
            & git -C $Repository merge-base --is-ancestor $Ancestor $Descendant 1> $null 2> $null
            $Code = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $Previous
        }
        return ($Code -eq 0)
    }

    try {
        # ========================================================
        # PREFLIGHT
        # ========================================================
        $CurrentPhase = "preflight"

        if ([System.IO.Path]::GetFullPath($CheckoutRoot).TrimEnd("\") -eq [System.IO.Path]::GetFullPath($ForbiddenRoot).TrimEnd("\")) {
            throw "Refusing to run against the retired checkout root $ForbiddenRoot."
        }

        foreach ($Path in @($Source, $CheckoutRoot, $WorkerConfig)) {
            if (-not (Test-Path -LiteralPath $Path)) {
                throw "Missing path: $Path"
            }
        }

        $SourceBranch = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "branch", "--show-current")
        if ($SourceBranch -ne $ExpectedBranch) {
            throw "Source is on $SourceBranch, expected $ExpectedBranch. Escalate."
        }

        $SourceHead = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "rev-parse", "HEAD")
        if (-not (Test-Ancestor -Repository $Source -Ancestor $GauntletCommit -Descendant $SourceHead)) {
            throw "HEAD $SourceHead does not contain the 1140 gauntlet commit $GauntletCommit. Escalate."
        }
        if (-not (Test-Ancestor -Repository $Source -Ancestor $ThroughputCommit -Descendant $SourceHead)) {
            throw "HEAD $SourceHead does not contain the reviewed throughput commit $ThroughputCommit. Escalate."
        }

        $SourceEdits = Get-NativeText -FilePath "git" -ArgumentList @("-C", $Source, "status", "--porcelain=v1", "--untracked-files=no")
        if (-not [string]::IsNullOrWhiteSpace($SourceEdits)) {
            throw ("The controller project has uncommitted edits; a half-written module would be imported by the next child process. Commit or stash, then rerun.`n" + $SourceEdits)
        }

        Write-Host ("[PASS] Source " + $SourceBranch + " at " + $SourceHead)
        Write-Host ("[PASS] Contains " + $GauntletCommit + " and " + $ThroughputCommit)
        Write-Host "[PASS] Controller project tree is clean"

        # ========================================================
        # OBSERVE CURRENT STATE
        # ========================================================
        $CurrentPhase = "observe-current-state"

        $AdmissionPath = Join-Path $Source ".git\assistant-control-admissions.json"
        if (Test-Path -LiteralPath $AdmissionPath) {
            $Admissions = Get-Content -LiteralPath $AdmissionPath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($Reservation in @($Admissions.reservations)) {
                if ($null -eq $Reservation) {
                    continue
                }
                Write-Host ("[STATE] Reservation " + $Reservation.task_id + " in " + $Reservation.checkout_root)
                if ($Reservation.checkout_root -ne $CheckoutRoot) {
                    throw ("A Source-scoped admission reservation belongs to another checkout root (" + $Reservation.checkout_root + "). It consumes this run's capacity. Escalate; do not edit the registry.")
                }
            }
        }

        $OwnerPath = Join-Path $Records "graph-controller-owner.json"
        if (Test-Path -LiteralPath $OwnerPath) {
            $Owner = Get-Content -LiteralPath $OwnerPath -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-Host ("[STATE] Previous controller: " + $Owner.status + " (invocation " + $Owner.invocation_id + ", outcome " + $Owner.outcome + ")")
            if ($Owner.status -ne "controller_released") {
                throw ("A graph controller may still own the graph (owner status " + $Owner.status + "). Escalate; do not start a second controller.")
            }
        }

        $StatePath = Join-Path $Records "graph-controller.json"
        if (Test-Path -LiteralPath $StatePath) {
            $State = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
            Write-Host ("[STATE] Graph status before this run: " + $State.status + "; last error: " + $State.last_error)
        }

        if (Test-Path -LiteralPath $Records) {
            foreach ($Index in @(Get-ChildItem -LiteralPath $Records -Filter "NSC-*.background-job.json" -ErrorAction SilentlyContinue)) {
                $IndexText = [string](Get-Content -LiteralPath $Index.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue)
                $IndexStatus = "UNREADABLE"
                if (-not [string]::IsNullOrWhiteSpace($IndexText)) {
                    try {
                        $IndexStatus = [string]($IndexText | ConvertFrom-Json).status
                    }
                    catch {
                        $IndexStatus = "UNREADABLE"
                    }
                }
                Write-Host ("[STATE] Background job index " + $Index.Name + ": " + $IndexStatus)
                if ($IndexStatus -eq "UNREADABLE") {
                    throw ("Background job index " + $Index.FullName + " cannot be read. The controller would refuse startup. Escalate; do not delete or repair it yourself.")
                }
            }
        }

        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

        # ========================================================
        # WORK: bounded run-graph loop
        # ========================================================
        $CurrentPhase = "work"
        Set-Location $Source
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
                "--capacity", "3",
                "--target-branch", $ExpectedBranch,
                "--max-actions", "240",
                "--background-jobs", "4"
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
            if ($Result.waiting_human) {
                foreach ($Waiting in @($Result.waiting_human)) {
                    Write-Host ("    waiting_human " + $Waiting.task_id + " candidate " + $Waiting.candidate_commit)
                }
            }
            if ($Result.cleanup_pending) {
                foreach ($Pending in @($Result.cleanup_pending)) {
                    Write-Host ("    cleanup_pending " + $Pending)
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
        Write-Host ("[STATE] Source: " + $Source + " on " + $ExpectedBranch)
        Write-Host "[NEXT] complete -> tell Vincent. awaiting_human -> tell Vincent the waiting_human list. Anything else -> send the section 9.4 escalation to the reviewer and stop."
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

What it does, in phases:

1. `[PHASE] preflight` — refuses the retired checkout root by resolved path; checks
   the three paths; asserts branch; asserts both anchor commits are ancestors of
   HEAD (so the viewer change, or any later reviewed commit, may be committed
   without invalidating the runner); refuses to start with a dirty tracked tree.
2. `[PHASE] observe-current-state` — reads the Source-scoped admission registry and
   throws if a reservation belongs to another checkout root; reads
   `graph-controller-owner.json` and refuses unless it says `controller_released`;
   prints the previous `graph-controller.json` status; lists every
   `NSC-*.background-job.json` with its status and throws on one that cannot be
   parsed (the controller would refuse startup on it anyway — section 7.3).
3. `[PHASE] work` — up to 40 invocations of the section-4.1 command, each writing
   `operator-logs\run-graph-<stamp>.json` and `.stderr.log`. Each iteration prints
   `[RUN n] exit <code>; status <s>; actions <n>; harvested <n>` plus one line per
   completed action, background job, blocked task, `waiting_human` entry and
   `cleanup_pending` task. It continues only on `worker_still_running`,
   `background_jobs_running`, `action_limit_reached`, `capacity_full`; it sleeps
   30 s on `capacity_full`; it stops after three consecutive cycles with zero
   actions and zero harvests (`idle_loop:<status>`).
4. `[PHASE] final-report` — one `[DONE] Operator loop ended with status: X` line and
   the `[STATE]` pointers. Any throw prints `[BLOCKED]`, `[ERROR]`, `[RECOVERY]` and
   rethrows.

### 4.3 Starting it detached, and polling

An agent session whose tool calls time out cannot hold the runner in the foreground.
Start it detached. The start block refuses to start a second runner while the
transcript it recorded has not finished.

```powershell
& {
    $ErrorActionPreference = "Stop"
    $LogDir = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2\operator-logs"
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
    $Process = Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "C:\nscrev\reports\gauntlet-run-runner.ps1") -RedirectStandardOutput $Transcript -RedirectStandardError $Errors -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $Pointer -Value $Transcript -Encoding ascii
    Write-Host ("[RUNNER] started pid " + $Process.Id)
    Write-Host ("[RUNNER] transcript " + $Transcript)
    Write-Host ("[RUNNER] errors " + $Errors)
    Write-Host "[NEXT] Poll with section 4.3's poll block until it prints [POLL] finished."
}
```

Poll with `C:\nscrev\reports\gauntlet-run-poll.ps1` (also parser-checked). Each call
waits at most four minutes and reads exactly the transcript the start block
recorded in `operator-logs\runner-current.txt`, never "the newest file":

```powershell
& {
    $LogDir = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2\operator-logs"
    $Pointer = Join-Path $LogDir "runner-current.txt"
    if (-not (Test-Path -LiteralPath $Pointer)) {
        throw "No runner has been started from the section 4.3 block: $Pointer is missing."
    }
    $TranscriptPath = (Get-Content -LiteralPath $Pointer -Raw).Trim()
    if (-not (Test-Path -LiteralPath $TranscriptPath)) {
        throw "Recorded transcript is missing: $TranscriptPath"
    }
    $Deadline = (Get-Date).AddSeconds(240)
    $Text = ""
    do {
        $Text = [string](Get-Content -LiteralPath $TranscriptPath -Raw -ErrorAction SilentlyContinue)
        if ($Text -match "\[(DONE|BLOCKED)\]") {
            break
        }
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

Ctrl+C is not available to a detached runner. Stopping it is section 6.

### 4.4 What each `run-graph` status means

The command prints one JSON object and exits `0` unless `status` is `blocked` or
`command_failed` (`__main__.py:306`).

| `status` | Where it is set | Meaning | Runner behaviour |
|---|---|---|---|
| `complete` | `graph_controller.py:839` via `final_result(plan, plan["status"])` | Every in-scope task is complete. | terminal — stop, report |
| `awaiting_human` | `graph_controller.py:838` | No action left; something waits for a human decision. Under `--auto-approve-gauntlet` on this family, this should not happen; if it does, read `waiting_human[]`. | terminal — escalate |
| `blocked` | `graph_controller.py:840` | No action and no human wait: `blocked[]` names each task and reason. **Exit 1.** | terminal — escalate |
| `capacity_full` | `graph_controller.py:1602` | The planner had actions but `_choose_run_action` could pick none: every remaining action is a `reserve` blocked by full capacity or by a resource overlap whose owner has no action of its own (`graph_controller.py:1383-1471`). | continue, after 30 s |
| `worker_still_running` | `graph_controller.py:1224, 1627` | A `wait_worker` hit its budget (`timeout_seconds` + 180 s = 1080 s here) with the worker still alive. | continue |
| `background_jobs_running` | `graph_controller.py:1224, 1627` | A `wait_job` hit its budget (3780 s for `decompose`, 1800 s for `post_crew`; `graph_controller.py:70-71, 1199-1200`) with the job still alive. | continue |
| `stopped` | `graph_controller.py:1577` | A bound `stop-graph` request (or Ctrl+C path) was honoured; active jobs were cancelled. Carries `background_stops[]`, `cleanup_pending[]`, `stop_request`. Exit 0. | terminal — read `cleanup_pending` |
| `action_limit_reached` | `graph_controller.py:1629` | `--max-actions` transitions were performed. Normal for a long run. | continue |
| `handoff_required` | `graph_controller.py:1605` | `--delegate-safe` only; never in this run. | terminal — escalate |
| `command_failed` | `__main__.py:499` | The command raised `ValueError`/`RuntimeError`/`OSError`/`TimeoutExpired`. The JSON is `{"status": "command_failed", "error": "..."}` only. **Exit 1.** | terminal — escalate |
| `interrupted` (state file only) | `graph_controller.py:1639` | Ctrl+C. Written to `graph-controller.json`; the process then re-raises, so the runner sees a non-zero exit and no JSON. | terminal — escalate |

`startup_refused` is **not** a `run-graph` status. It is a journal event
(`graph_controller.py:1086`) emitted when `reconcile_startup` refuses to plan beside
an ambiguous ticket or an unverified container; the exception then surfaces to the
operator as `command_failed` with exit 1. Nothing is killed or removed on that path.
If you see exit 1 with `command_failed`, always check the journal for
`startup_refused` before anything else.

---

## 5. Reading the run while it goes

### 5.1 Read-only status (safe for any tier)

```powershell
& {
    $env:PYTHONUTF8 = "1"
    Set-Location "C:\NSC\GauntletFresh1140-20260912-1"
    python -m Pipeline.AssistantControl --source "C:\NSC\GauntletFresh1140-20260912-1" --checkout-root "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2" graph-plan --task NSC-1140 --task NSC-1141 --task NSC-1142 --task NSC-1143 --task NSC-1144 --task NSC-1145 --task NSC-1146 --task NSC-1147 --auto-approve-gauntlet --capacity 3 --target-branch gauntlet-test/throughput-e90670d --background-jobs 4
    Write-Host ("[EXIT] " + $LASTEXITCODE)
}
```

```powershell
Get-Content -LiteralPath "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2\.assistant-control\graph-controller-events.jsonl" -Tail 40
```

```powershell
python -m Pipeline.AssistantControl --source "C:\NSC\GauntletFresh1140-20260912-1" --checkout-root "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2" worker-status NSC-1141
```

`worker-status` inspects host identity and retained worker state
(`__main__.py:106-107`, `worker_control.status`). It mutates nothing. `settle-worker`
(`__main__.py:108-110`) **does** mutate — it releases a reservation — and belongs to
the controller, not to you; never run it by hand while the controller owns the graph.

### 5.2 `graph-controller.json` (`<records>\graph-controller.json`)

Written by `_save_state` (`graph_controller.py:859-901`) on every transition:

- `status` — the same vocabulary as section 4.4, plus `running` (mid-loop),
  `preflight`, `interrupted`, `blocked`.
- `invocation_id` — the current controller invocation; it also stamps every journal
  event, which is how you separate one invocation's work from the next.
- `targets`, `human_review_tasks`, `auto_approve_gauntlet` — the policy in force.
- `current_action` — the exact action dict being executed right now, or `null`.
- `last_error` — the `Type: message` of the exception that blocked the loop.
- `history` — the last 100 entries, each `{at, action, invocation_id, result_status}`.
  This is the cheapest per-action timeline.
- `background_jobs` — one `background_jobs.summary()` per task
  (`background_jobs.py:272-280`): `task_id`, `kind`, `job_id`, `attempt`, `status`,
  `identity`, `invocation_id`, `launched_at_utc`, `pid`, `process_identity`,
  `job_name`, `provider_container`, `provider_container_cleanup`, `authentication`,
  `reconciliation`, `stop`, `result_status`, `error`, `completed_at_utc`,
  `harvested_at_utc`, `harvest_invocation_id`, `run_root`.
- `background_stops` — present only after a stop: what each job's cancellation did.
- `cleanup_pending` — appears in the **`stopped` result** and in `stop-graph` /
  `stop-background-jobs` output: the task ids whose provider container is not yet
  finally verified absent. (It is not a standing field of the state file; the
  authority is `provider_container_cleanup` on each job index —
  `graph_controller.py:1788-1817`.)

### 5.3 The journal (`<records>\graph-controller-events.jsonl`)

One JSON object per line, fsynced on every append (`graph_controller.py:295-302`).
Every event carries `at_utc` and `event`; most carry `invocation_id`.

**Ownership**

- `controller_started` — the full owner record inlined: `invocation_id`, `pid`,
  `process_identity`, `source`, `source_commit`, `source_branch`, `targets`,
  `checkout_root`, `capacity`, `policy`, `policy_sha256`, `worker_config_sha256`,
  `max_actions` (`graph_controller.py:357-382`).
- `controller_released` — `outcome` is one of `returned`, `exception`,
  `interrupted`, `startup_failed`, `startup_interrupted`, plus `error_type`
  (`graph_controller.py:386-413`).
- `controller_stopped` — `reason`, `requested_at_utc`, `stopped_jobs`,
  `cleanup_pending` (`graph_controller.py:1569-1574`).
- `stop_request_ignored` — a stop request that did not bind to the running
  invocation was archived; nobody acts (`graph_controller.py:1262-1267`).
- `startup_refused` — with `error`, `task_id`, `kind`, `job_id`, `status`,
  `provider_container`, `provider_container_cleanup`. The reviewer reads `error`
  first; nothing was killed or removed (`graph_controller.py:1085-1091`).

**Actions** (`_append_action_event`, `graph_controller.py:926-947`)

- `action_started` — `action_id`, `kind`, `task_id`, `run_id`, `provider`, `model`.
- `action_completed` — the same plus `result_status` and **`duration_seconds`**.
- `action_failed` — the same plus `error` and `duration_seconds`.

There is no `action_finished` event; the correction matters for any parser you
write. `duration_seconds` is measured with `time.monotonic()` around
`execute(action)` (`graph_controller.py:949-966`), so it is the action's own wall
time and excludes planning.

**Background jobs** (`_append_job_event`, `graph_controller.py:1050-1065` — every one
of these carries `task_id`, `kind`, `job_id`, `attempt`, `identity`, `status`, `pid`,
`process_identity`, `launched_at_utc`, `result_status`, `error`, `completed_at_utc`,
`run_root`, `provider_container`, `provider_container_cleanup`)

| Event | Meaning | Who acts |
|---|---|---|
| `job_launched` | A detached ticket started (`graph_controller.py:1043`). | nobody |
| `job_spawn_failed` | The child never started; the retained `spawn_failed` index blocks only that task (`:1040`). | reviewer |
| `job_completed` / `job_failed` / `job_died` | Harvested from the child's own receipt, or from its absence (`:1171-1174`). `failed`/`died` block only that task. | reviewer on failure |
| `job_adopted` | A live child carried across a controller restart; never relaunched (`:1101`). | nobody |
| `job_quarantined` | A live child whose ticket no longer authenticated: stopped exactly, task blocked (`:1103`). | reviewer |
| `job_container_verified` | A pending container cleanup is finally proven absent (`:1105, 1152`). | nobody |
| `job_cleanup_pending` | The loop retried a container cleanup and it is not final yet, usually because its 60 s tombstone is still running (`:1143, 1151`). | nobody |
| `job_cleanup_superseded` | A ticket was cleared or replaced while its cleanup ran (`:1107, 1147`). | nobody |
| `job_harvest_deferred` | An ended job's record could not be read or authenticated this cycle; the loop moved on (`:1168`). | reviewer if it repeats |
| `job_unverifiable` | The child's liveness could not be determined this cycle (`:1160`). | reviewer if it repeats |
| `job_stopped` | One entry per cancelled job during a stop (`:1285-1288`). | nobody |

**Timing anchor.** Nothing in this journal records how long `plan()` took. See
section 8.2.

### 5.4 Worker records (`<records>\NSC-<id>.json`)

`Checkouts.observe` reads exactly this file (`checkouts.py:151-154`). Fields that
matter while the run goes:

- `task_id`, `source`, `source_commit`, `task_contract_sha256`, `checkout`, `status`.
- `scope` — `lease_id`, `plan_id`.
- `worker` (or `launch` before the handshake) — `task_id`, `run_id`, `lease_id`,
  `status` (`succeeded` / `failed` / `stopped` / `spawn_failed`; `_WORKER_TERMINAL`,
  `graph_controller.py:49`), `process_identity`, `job_name`, `stop_request_path`,
  `crew_run_id`, `receipt`, `capacity_released`, and the three timestamps
  `started_at` (`crew_worker.py:172`), `finished_at` (`crew_worker.py:105`),
  `settled_at` (`worker_settlement.py:123`).
- `candidate` — the registered candidate: `commit`, `authoritative_validations`,
  `original_candidate`.
- `approval`, `human_review`, `candidate_validation_failure`.

The run's own artifacts live under
`<records>\worker-runs\<task>\<sha256 of run_id>\` — `launch.request.json`,
`launcher.identity.json`, `child.identity.json`, `job.opened.json`,
`ready.receipt.json`, `launcher.status.json`, `stop.request`, `stdout.log`,
`stderr.log` (`worker_launcher.py:38-39, 152-188, 258-278`).

### 5.5 Background-job indexes and tickets

- Index: `<records>\NSC-<id>.background-job.json` (`background_jobs.py:165-166`).
  Statuses: active = `launched`, `running`; terminal = `completed`, `failed`,
  `died`, `cancelled`, `spawn_failed` (`background_jobs.py:70-71`).
- Cleared index: `<records>\NSC-<id>.background-job.<job_id>.cleared.json`
  (`background_jobs.py:2053-2056`). Nothing is ever deleted.
- Run root: `<records>\background-jobs\<task>\<job_id>\`
  (`background_jobs.py:556`), containing `launch.request.json`, `ready.receipt.json`,
  `receipt.json`, `stop.request.json`, `job.opened.json`, `launcher.identity.json`,
  `child.identity.json`, `stdout.log`, `stderr.log`
  (`background_jobs.py:564-580, 614, 624, 2365, 2391`) and, after a cooperative stop,
  `cooperative-stop.json` (`background_jobs.py:2229`).
- A decomposition ticket records `provider_container` (name
  `nsc-decompose-<job-id prefix>`, compose project, and the two labels
  `com.nosafecircle.assistant.job` / `com.nosafecircle.assistant.checkout`) before
  Docker can start, and `provider_container_cleanup` afterwards with
  `status` (`verified_absent`, `refused`, `unverified`, `in_progress`),
  `tombstone_until_utc`, `final_recheck_at_utc`, `retry_after_utc`,
  `authentication_failed`, removals and sightings
  (`background_jobs.py:86-88, 505-522`; README graph-controller section).

### 5.6 The Source-scoped admission registry

`reserve` and `settle-worker` read and write
`<Source>\.git\assistant-control-admissions.json` with
`<Source>\.git\assistant-control-admission.lock`
(`admission.py:27-31`; the path is the Git *common* dir of the Source). This is the
one piece of durable state that is **not** under the checkout root. Two consequences:

1. `--capacity` bounds workers per **Source**, not per checkout root. A reservation
   left behind by a run against a different checkout root would silently eat this
   run's capacity. The preflight and the runner both check for that.
2. It survives deleting a checkout root. Verified 2026-09-12: the file does not
   currently exist, so there are no stale reservations.

### 5.7 Durable state versus a process-liveness guess

Durable (believe it): the journal, `graph-controller.json`,
`graph-controller-owner.json`, `NSC-<id>.json`, the job indexes, every file under
`worker-runs\` and `background-jobs\`. These are written with `write_record` and
`os.fsync`.

A guess (do not believe it alone): a PID that is or is not in Task Manager; a
container name that appears in `docker ps`; a port that is listening; a viewer node
colour. The controller itself never trusts these on their own — it re-derives the
whole process identity (PID plus creation ticks plus image) and compares it against
`launcher.identity.json`, `child.identity.json` and `job.opened.json`
(`background_jobs.py:921-1013`), and it removes a container only by exact id after
the name, compose project, service and both ownership labels match
(README, graph-controller section).

The operational rule: **the owner record plus the lock decides who owns the graph.**
`graph-controller-owner.json` with `status: controller_started` *and* a held
`graph-controller.lock` means a live controller. The same record with a free lock
means a lost process, and `stop-graph` says so explicitly
(`graph_controller.py:1732-1741`).

---

## 6. Stopping

### 6.1 `stop-graph` — the normal stop for a detached controller

```powershell
& {
    $env:PYTHONUTF8 = "1"
    Set-Location "C:\NSC\GauntletFresh1140-20260912-1"
    python -m Pipeline.AssistantControl --source "C:\NSC\GauntletFresh1140-20260912-1" --checkout-root "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2" stop-graph --reason "reviewer stop" --grace-seconds 15 --wait-seconds 120
    Write-Host ("[EXIT] " + $LASTEXITCODE)
}
```

It writes `<records>\graph-controller.stop.json` bound to the running invocation,
PID and process identity; the controller honours it between actions and on every
wait poll, cancels its jobs (bound stop request, bounded grace, then the exact Job
Object trees) and returns `stopped`. It never terminates anything itself
(`graph_controller.py:1693-1785`).

Exit code: `0` for `stopped`, `stop_requested`, `already_released`; `1` otherwise
(`__main__.py:314`).

| Result `status` | Meaning | Next |
|---|---|---|
| `stopped` | The owner released and nothing is pending. | done |
| `stopped_cleanup_pending` | It stopped, but a container cleanup is not final (tombstone unfinished, Docker unreachable, or a name kept reappearing), or an index is unreadable. Exit 1. | run 6.2 until it prints `stopped` |
| `already_released` | The controller had already released. Idempotent repeat. | done |
| `already_released_cleanup_pending` | Released, but pending cleanup or an unreadable index remains. Exit 1. | run 6.2 |
| `released` | The owner released with a state other than `stopped` (it finished on its own first). | read the state |
| `stop_requested` | `--wait-seconds` elapsed before release. The request is bound and standing. | re-run, or read the runner transcript |
| raises | No controller ever owned this graph, or the owner record is unreadable, or the owner is stale (its lock is free — the process is gone). | for stale, run 6.2 |

`cleanup_pending` and `unreadable_indexes` in the result name exactly what is left
(`graph_controller.py:1671-1690, 1788-1817`).

### 6.2 `stop-background-jobs` — finish a stop, or recover after a lost controller

```powershell
& {
    $env:PYTHONUTF8 = "1"
    Set-Location "C:\NSC\GauntletFresh1140-20260912-1"
    python -m Pipeline.AssistantControl --source "C:\NSC\GauntletFresh1140-20260912-1" --checkout-root "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2" stop-background-jobs --grace-seconds 15
    Write-Host ("[EXIT] " + $LASTEXITCODE)
}
```

It takes the controller lock first and **refuses while a graph controller owns the
graph** ("a graph controller owns these jobs; interrupt it instead of stopping its
jobs underneath it", `__main__.py:322-328`). It finalizes: it waits each container's
60 s tombstone out and records the final recheck, so `stopped` really means done
(`__main__.py:330-336`). Expect it to take about a minute per killed decomposition.

| Result `status` | Exit | Meaning |
|---|---|---|
| `stopped` | 0 | Every job is terminal and every provider container is finally verified absent. |
| `cleanup_pending` | 1 | `cleanup_pending[]` names the tasks, `retry_after_utc[]` says when. Run the block again once the time has passed or Docker answers. |
| `stop_failed` | 1 | A job is still `running`, or a stop failed. Escalate. |

`unreadable_indexes[]` is reported by both commands with the exact path and error and
keeps the exit code at 1 for the whole graph; nothing repairs or deletes such a file
automatically (`__main__.py:339-352`; README).

### 6.3 Ctrl+C

Ctrl+C works **only in a foreground run**. It cancels active jobs with the same
bounded-grace-then-Job-Object-tree path, saves state `interrupted`, and re-raises
(`graph_controller.py:1630-1645`). A second Ctrl+C abandons the enforcement
(`graph_controller.py:1278-1280`) and you must finish with 6.2. The detached runner
of section 4.3 has no console: use 6.1.

### 6.4 What must never be done

- Never `Stop-Process` / `taskkill` a controller, a worker or a job child by PID.
- Never `docker stop` / `docker rm` / `docker compose down` a
  `nsc-decompose-*` or `assistant-crew-*` container or project by hand. Ownership is
  proven by labels and exact ids; a hand removal makes the ticket unclearable.
- Never edit, move, truncate or delete anything under `.assistant-control` — not a
  job index, not a receipt, not the owner record, not a lock file. The **only**
  sanctioned by-hand record move is the operator repair of an *unreadable* index in
  section 7.3, and that is the reviewer's decision with Vincent's word.
- Never run `settle-worker`, `stop-worker`, `reserve`, `start-worker`, `decompose`,
  `apply-decomposition`, `candidate`, `post-crew`, `review` or `integrate` by hand
  while a controller owns the graph.
- Never delete a checkout under the checkout root to "retry" a task.

---

## 7. Failure handling

### 7.1 A blocked task

`blocked[]` in the `run-graph` / `graph-plan` result gives `task_id` and `reason`.
The reasons the planner can emit (`graph_controller.py:697-818`):

| `reason` | Evidence to read |
|---|---|
| `dependencies` | `dependencies[]` in the same entry; then `graph-plan` for those tasks. Normal early on for 1145/1146/1147. |
| `background_job_<status>` | `<records>\NSC-<id>.background-job.json`, then `background-jobs\<task>\<job_id>\stderr.log` and `receipt.json` (`graph_controller.py:658-662`). |
| `decomposition_receipt_missing` | The ticket ran to completion without a proposal record. `background-jobs\<task>\<job_id>\receipt.json` is the authority. |
| `decomposition_failed` / `decomposition_<status>` | The retained decomposition review; `inspect-decomposition <task>` is the read-only reader (`__main__.py:146-147`). |
| `worker_<status>` | `<records>\NSC-<id>.json` → `worker.status`, `worker.error`, `worker.receipt`; then `worker-runs\<task>\<sha256 run_id>\stderr.log`. |
| `candidate_state:<status>` | `<records>\NSC-<id>.json` → `candidate`, `candidate_validation_failure`. |
| `changes_requested`, `validation_failed`, `materialization_failed`, `needs_materialization` | Same record; these are terminal failures (`graph_controller.py:45-48`). |
| `integration_receipt_not_current` | `<records>\NSC-<id>.json` → `status: integrated` against a moved Source. |
| `aggregate_children_incomplete` | A decomposed parent whose children are not all locally accepted. |

A blocked task blocks **only itself**. The rest of the graph keeps moving; the
runner keeps going until no action is left at all.

### 7.2 `clear-background-job` — reviewer only

```text
python -m Pipeline.AssistantControl --source C:\NSC\GauntletFresh1140-20260912-1 --checkout-root C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2 clear-background-job NSC-<n> --job-id <job_id>
```

(Shape, not paste-ready: `<n>` and `<job_id>` come from the task's
`NSC-<n>.background-job.json`.)

Before running it the reviewer must have read, for that exact job:

1. `background-jobs\<task>\<job_id>\stderr.log`
2. `background-jobs\<task>\<job_id>\receipt.json`
3. the index's `provider_container_cleanup` block
4. for a stopped decomposition, `background-jobs\<task>\<job_id>\cooperative-stop.json`

What the command refuses, from `background_jobs.clear`
(`background_jobs.py:1998-2058`):

- the exact index is not found, or its `job_id` differs → refuses;
- the job is still running, or has not been harvested → refuses;
- the ticket does not authenticate → refuses, **and durably records
  `authentication_failed`** on the cleanup (`background_jobs.py:2019-2028`);
- the cleanup is still pending after one retry → refuses with the reason;
- `verified_absent` but the 60 s tombstone is still active → refuses and tells you
  the exact `tombstone_until_utc` to retry after
  (`background_jobs.py:2038-2042`, `CONTAINER_TOMBSTONE_SECONDS = 60.0` at
  `background_jobs.py:75`);
- the index changed while it was being cleared → refuses.

On success the index is **archived**, never deleted:
`NSC-<id>.background-job.<job_id>.cleared.json`. Run roots and receipts are never
touched. Only after that may the planner issue a fresh ticket for that task.

### 7.3 `authentication_failed` and unreadable indexes

**`authentication_failed`** means the recorded identity no longer matches: the
request bytes against the recorded hash, the ticket schema/task/job/kind/identity,
the Job Object name, the Source and checkout root, the job id re-derived from this
checkout, the container labels this checkout derives, or the recorded PID and the
complete process-identity dict checked against `launcher.identity.json`,
`child.identity.json` and `job.opened.json` (README graph-controller section;
`background_jobs.py:853-1013`). It is never retried automatically. The index records
an `authentication` block listing every problem. The repair is by hand and by the
reviewer with Vincent's explicit word: read the index and `launch.request.json`
under `background-jobs\<task>\<job_id>\`, decide, move the file aside, and only then
consider a fresh ticket. Nothing was inspected, removed, signalled or terminated.

**An unreadable index** (missing, empty, truncated, malformed, or naming another
Source or checkout root) is never read as "nothing remains"
(`background_jobs.py:225-252`). `stop-background-jobs` and `stop-graph` report it in
`unreadable_indexes` with path and error and keep exit 1; the next controller start
refuses with `startup_refused` before it plans. The only repair is an operator
moving the file aside or restoring it by hand, after which the same commands report
finished again.

**A `refused` cleanup naming other identity** — an error containing
`carries other identity (job label ..., checkout label ...)` — means a container
under the ticket's name does not carry this ticket's labels. It belongs to another
checkout or was created by hand. The tool never removes it. The reviewer decides by
hand, with Vincent.

### 7.4 The 60-second tombstone, and why a stop can take a minute

One Docker operation may take up to a minute, so a kill-path container cleanup keeps
a tombstone (`tombstone_until_utc`, 60 s) and stays *pending* until that bound has
passed and one more exact look has been recorded as `final_recheck_at_utc`. A
sighting during that look removes the container, reruns the whole 15 s watch window
and starts a fresh bound. Therefore:

- `stop-graph` takes one exact look while the bound is active and reports
  `retry_after_utc`;
- `stop-background-jobs` waits the bound out, so it can take ~60 s per killed
  decomposition, and its `stopped` means done;
- a controller **start** also waits a killed decomposition's bound out before its
  first plan — a restart right after a kill can sit for about a minute before
  anything appears in the journal. That is not a hang.

(README graph-controller section; `background_jobs.py:73-75, 1425-1439`.)

### 7.5 When to escalate to the reviewer

Immediately, without retrying anything:

- any `[BLOCKED]` from the runner;
- exit 1, or `status` `blocked` / `command_failed` / `awaiting_human`;
- `no_json_output`;
- `idle_loop:<status>`;
- any `startup_refused`, `job_quarantined`, `authentication_failed`, or
  `unreadable_indexes`;
- a viewer row that disagrees with the durable record;
- any sign of a second controller, a worker for a task outside the eight roots and
  their generated children, or a container that is not `nsc-decompose-*` /
  `assistant-crew-*` for this run.

---

## 8. Measurement plan

The owner wants a report on whether the asynchronous controller actually overlaps
work. Everything below comes from read-only files.

### 8.1 What to measure and where it lives

| Measure | Source of truth |
|---|---|
| Total elapsed | first `controller_started` `at_utc` to the last journal event (or `controller_released`). |
| Time per action, by kind | `duration_seconds` on `action_completed` / `action_failed` (`graph_controller.py:944, 962-965`). Direct field; no derivation. |
| Time in each `plan()` call | **No direct field exists in the journal or the state file.** Derive it: the interval between one `action_completed`/`action_failed` `at_utc` and the next `action_started` `at_utc` in the same `invocation_id`. That interval is `_harvest_jobs()` + `plan()` + `_save_state()` (`graph_controller.py:1589-1608`), so report it as "harvest + plan + state write", never as `plan()` alone. The interval from `controller_started` to the first `action_started` additionally contains `_reconcile_startup()`, which can include a 60 s tombstone wait. Expected magnitude for calibration: ~0.2 s warm and ~5 s after a HEAD move on a 102-task graph (`Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md`, "Planning cost per cycle"). |
| Max simultaneous workers | Sweep the intervals `action_completed kind=start_worker` → `action_completed kind=settle_worker` per task. |
| Max simultaneous background jobs | Sweep `job_launched` → the first of `job_completed`/`job_failed`/`job_died`/`job_stopped`/`job_quarantined` with the same `job_id`. |
| Did unrelated work continue during a job? | For each job interval, list every `action_started` inside it whose `task_id` differs from the job's and whose `kind` is not `wait_job`/`wait_worker`. A non-empty list for a `decompose` job is the proof the owner is asking for; an empty list for every job means the loop serialized. |
| Worker completion → settlement delay | Exact, durable: `worker.settled_at` minus `worker.finished_at` in `<records>\NSC-<id>.json` (`crew_worker.py:105`, `worker_settlement.py:123`). The journal proxy — the `wait_worker` `action_completed` (which returns `progress`/`worker_exited`) to the following `settle_worker` `action_completed` — is coarser; prefer the record. |
| Duplicate launches | `job_launched` repeated for one `job_id` or one `task_id`; `action_completed kind=start_worker` repeated for one `(task_id, run_id)`; more than one run-root directory under `background-jobs\<task>\`. Any of these is a defect worth its own report line. |
| Blocked or failed tasks | `blocked[]` in the last result JSON, plus the failure events in 5.3, each with the exact run root. |
| Viewer versus durable records | Capture `/api/state` (section 3.2) at the same moment as `graph-controller.json` and compare `run.targets`, `run.scope.visible`, and each row's state against the record. Note every disagreement. |

### 8.2 Read-only measurement snippet

Save as `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2\operator-logs\measure.py`
(or anywhere outside the project) and run with `python measure.py`. It opens files
for reading only.

```python
"""Read-only measurement of one AssistantControl graph run. Writes nothing."""
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(r"C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2\.assistant-control")
JOB_END = {"job_completed", "job_failed", "job_died", "job_stopped", "job_quarantined"}
ACTION_END = {"action_completed", "action_failed"}

events = [json.loads(line) for line in
          (ROOT / "graph-controller-events.jsonl").read_text(encoding="utf-8").splitlines()
          if line.strip()]
events.sort(key=lambda e: e["at_utc"])
when = lambda e: datetime.fromisoformat(e["at_utc"])


def span(intervals):
    """Maximum simultaneous open intervals and when that peak happened."""
    edges = sorted([(s, 1) for s, _ in intervals] + [(e, -1) for _, e in intervals])
    now = peak = 0
    at = None
    for moment, delta in edges:
        now += delta
        if now > peak:
            peak, at = now, moment
    return peak, at


print("=== 1. total elapsed ===")
starts = [e for e in events if e["event"] == "controller_started"]
if starts:
    total = (when(events[-1]) - when(starts[0])).total_seconds()
    print(f"  first controller_started {starts[0]['at_utc']}")
    print(f"  last event               {events[-1]['at_utc']}")
    print(f"  wall clock               {total:.1f} s ({total/3600:.2f} h) over {len(starts)} invocation(s)")

print("=== 2. action time by kind (duration_seconds on action_completed/action_failed) ===")
by_kind = defaultdict(list)
for e in events:
    if e["event"] in ACTION_END and isinstance(e.get("duration_seconds"), (int, float)):
        by_kind[e.get("kind")].append(e["duration_seconds"])
for kind in sorted(by_kind):
    values = by_kind[kind]
    print(f"  {kind:<20} n={len(values):<4} total={sum(values):10.1f}s  max={max(values):8.1f}s")

print("=== 3. plan()+harvest gap (DERIVED: no direct field exists) ===")
gaps = []
by_invocation = defaultdict(list)
for e in events:
    if e["event"] in ACTION_END or e["event"] in {"action_started", "controller_started"}:
        by_invocation[e.get("invocation_id")].append(e)
for invocation, items in by_invocation.items():
    previous = None
    for e in items:
        if e["event"] == "action_started" and previous is not None:
            gaps.append(((when(e) - when(previous)).total_seconds(), previous["event"], e.get("kind")))
        if e["event"] in ACTION_END or e["event"] == "controller_started":
            previous = e
if gaps:
    warm = [g for g in gaps if g[1] != "controller_started"]
    cold = [g for g in gaps if g[1] == "controller_started"]
    if warm:
        print(f"  warm gaps  n={len(warm)} median={sorted(g[0] for g in warm)[len(warm)//2]:.2f}s "
              f"max={max(g[0] for g in warm):.2f}s total={sum(g[0] for g in warm):.1f}s")
    if cold:
        print(f"  startup reconcile + first plan: {[round(g[0], 2) for g in cold]} s")
    print("  NOTE: each gap is harvest + plan() + state write, not plan() alone.")

print("=== 4. peak concurrency ===")
worker_open, worker_intervals = {}, []
for e in events:
    if e["event"] == "action_completed" and e.get("kind") == "start_worker":
        worker_open[e.get("task_id")] = when(e)
    if e["event"] in ACTION_END and e.get("kind") == "settle_worker":
        started = worker_open.pop(e.get("task_id"), None)
        if started is not None:
            worker_intervals.append((started, when(e)))
for task, started in worker_open.items():
    worker_intervals.append((started, when(events[-1])))
    print(f"  WARN worker for {task} never settled in the journal")
job_open, job_intervals = {}, []
for e in events:
    if e["event"] == "job_launched":
        job_open[e.get("job_id")] = (when(e), e.get("task_id"))
    if e["event"] in JOB_END and e.get("job_id") in job_open:
        started, task = job_open.pop(e["job_id"])
        job_intervals.append((started, when(e), task, e["job_id"]))
for job_id, (started, task) in job_open.items():
    job_intervals.append((started, when(events[-1]), task, job_id))
peak_w, at_w = span(worker_intervals)
peak_j, at_j = span([(a, b) for a, b, _, _ in job_intervals])
print(f"  max simultaneous workers        = {peak_w} (at {at_w})")
print(f"  max simultaneous background jobs = {peak_j} (at {at_j})")

print("=== 5. unrelated work during background jobs ===")
for started, ended, task, job_id in job_intervals:
    others = sorted({f"{e.get('kind')}:{e.get('task_id')}" for e in events
                     if e["event"] == "action_started" and started < when(e) < ended
                     and e.get("task_id") != task
                     and e.get("kind") not in {"wait_job", "wait_worker"}})
    print(f"  job {job_id[:16]} ({task}, {(ended-started).total_seconds():.0f}s): "
          + (", ".join(others) if others else "NOTHING ELSE RAN"))

print("=== 6. worker completion -> settlement (durable records) ===")
for path in sorted(ROOT.glob("NSC-*.json")):
    if path.name.endswith(".background-job.json"):
        continue
    record = json.loads(path.read_text(encoding="utf-8"))
    worker = record.get("worker") or record.get("launch") or {}
    finished, settled = worker.get("finished_at"), worker.get("settled_at")
    if finished and settled:
        print(f"  {record.get('task_id')}: finished {finished} settled {settled} "
              f"delay {(datetime.fromisoformat(settled)-datetime.fromisoformat(finished)).total_seconds():.1f}s")
    elif worker:
        print(f"  {record.get('task_id')}: started={worker.get('started_at')} "
              f"finished={finished} settled={settled} status={worker.get('status')}")

print("=== 7. duplicate launches ===")
for label, counter in (("job_launched job_id", Counter(e.get("job_id") for e in events if e["event"] == "job_launched")),
                       ("job_launched task", Counter(e.get("task_id") for e in events if e["event"] == "job_launched")),
                       ("start_worker task+run", Counter((e.get("task_id"), e.get("run_id")) for e in events
                                                         if e["event"] == "action_completed" and e.get("kind") == "start_worker"))):
    dupes = {key: count for key, count in counter.items() if count > 1}
    print(f"  {label}: {dupes if dupes else 'no repeats'}")
jobs_root = ROOT / "background-jobs"
if jobs_root.is_dir():
    for task_dir in sorted(jobs_root.iterdir()):
        roots = sorted(p.name for p in task_dir.iterdir() if p.is_dir())
        print(f"  run roots {task_dir.name}: {len(roots)} {roots}")

print("=== 8. blocked / failed with durable evidence ===")
for e in events:
    if e["event"] in {"job_failed", "job_died", "job_quarantined", "job_spawn_failed",
                      "job_unverifiable", "job_harvest_deferred", "job_cleanup_pending",
                      "action_failed", "startup_refused", "controller_stopped", "stop_request_ignored"}:
        print(f"  {e['at_utc']} {e['event']} {e.get('kind')} {e.get('task_id')} "
              f"{str(e.get('error') or e.get('detail') or '')[:160]}")
        if e.get("run_root"):
            print(f"      evidence: {e['run_root']}\\stderr.log  {e['run_root']}\\receipt.json")
```

This snippet was exercised read-only against the eight-event journal in the retired
checkout root on 2026-09-12 and produced correct output for sections 1, 2, 3, 7 and
8; sections 4, 5 and 6 had no data there because that run never launched a job or a
worker. **UNVERIFIED:** the concurrency, overlap and settlement branches against a
real run's journal.

---

## 9. The three-agent topology

### 9.1 Shape

```text
                Vincent (relays, decides, owns every mutation outside the loop)
                                      |
             +------------------------+------------------------+
             |                        |                        |
        OPERATOR                 REVIEWER               LANE SUPERVISORS A / B / C
   one run-graph controller    judgment authority       read-only lane watchers
   (sections 4.2-4.3)          (sections 6, 7)          (graph-plan, worker-status,
                                                          viewer API, records)
```

- **Exactly one GraphController exists**: the process the operator's runner starts.
  Enforced by the exclusive lock at `<records>\graph-controller.lock`
  (`graph_controller.py:304-310`); a second `run-graph` raises
  `ControllerOwnerActiveError`.
- **Lanes are a convention, not a mechanism.** Nothing in the code assigns a task to
  an agent. Lanes exist so three watchers can read the same shared journal and task
  records without duplicating each other's reporting. Say so plainly in every
  report; do not describe a lane as a claim the controller honours.

| Lane | Tasks | Why it is a lane |
|---|---|---|
| A | NSC-1141 → NSC-1145 → NSC-1146 → NSC-1147 and 1145/1146's generated children | The serial dependency chain; the slowest path and the one where a stall is most expensive. |
| B | NSC-1142, NSC-1143, NSC-1144 | Three independent single-agent tasks; the parallel-admission evidence. |
| C | NSC-1140 and its generated children (NSC-1148 upward) | The first decomposition; the overlap evidence for section 8. |

Every lane's boundary moves when the decomposer allocates ids: a generated child
belongs to the lane of its parent. Read `run.scope.generated` from `/api/state`, or
`decomposition_children` on the parent's row, to find out which.

### 9.2 What a lane supervisor may do

Allowed, all read-only: `graph-plan` (section 5.1), `worker-status <task>`,
`inspect-decomposition <task>`, `checkout <task>`, `dependencies <task>`,
`status --task <task>`, `readiness <task>`, the viewer API, and reading any file
under `<records>` and `operator-logs`.

### 9.3 What an agent must never do

1. Never start a second controller. No `run-graph` from any session but the
   operator's runner.
2. Never run `start-worker`, `run-worker`, `reserve`, `settle-worker`,
   `stop-worker`, `decompose`, `apply-decomposition`, `candidate`, `post-crew`,
   `materialize-candidate`, `review`, `integrate`, `prepare`, `refresh-prepared`,
   `scope`, `sync-candidate`, `revise`, `preserve-success`, `maintenance-run` or
   `gauntlet-replay` by hand. Every one of these is the controller's own action.
3. Never touch another lane's task, checkout, record, job index or run root — not
   even to read it into a report as if it were yours. Report only your lane.
4. Never edit any file in `C:\NSC\GauntletFresh1140-20260912-1`, and never run a git
   command there that changes anything.
5. Never run `clear-background-job`, `stop-graph` or `stop-background-jobs` — those
   are the reviewer's, and `stop-*` needs Vincent's word.
6. Never touch Docker, Unity, GitHub, or the retired checkout root.
7. Never retry a failed command. Escalate with section 9.4 instead.

### 9.4 Escalation format

```text
ESCALATION from <OPERATOR | LANE A | LANE B | LANE C> - <UTC date time>
Lane / scope: <the exact task ids you are reporting on>
Loop ended with: <the [DONE] or [BLOCKED] line, verbatim>
Exit code of last run-graph: <code>
Last result JSON: <path>
Last 10 lines of the stderr log:
<paste>
Blocked tasks (task: reason):
<paste>
Background jobs (kind task: status):
<paste>
Journal events since my last report (at_utc event kind task_id):
<paste>
Owner status line: <paste the [STATE] Previous controller ... line>
Durable evidence paths I read:
<paste absolute paths>
I have not rerun, cleared, stopped or edited anything. Waiting for RESUME, STOP or TICKET.
```

The reviewer answers with one word first — `RESUME`, `STOP` or `TICKET` — then the
reasoning in a few sentences. `STOP` means wait for Vincent.

### 9.5 Role prompts

Three roles; five paste-ready prompts, because the lane-supervisor role is
instantiated three times and a spliced prompt is not acceptable. Paste each whole
into a fresh session.

#### 9.5.1 OPERATOR — fresh session, working directory `C:\NSC\GauntletFresh1140-20260912-1`

```text
You are the gauntlet OPERATOR for NSC-1140..NSC-1147. Your whole job is to run three fixed PowerShell blocks and report their result. You do not diagnose, fix, edit files, retry, clear or stop jobs, or change any command, flag or path.

Facts (never change them):
- Guide: C:\nscrev\reports\gauntlet-run-instructions.md
- Controller project and Source: C:\NSC\GauntletFresh1140-20260912-1 on branch gauntlet-test/throughput-e90670d
- Checkout root: C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2 (records in .assistant-control, your logs in operator-logs)
- The old root C:\NSC\GauntletFresh1140-20260912-1-Checkouts is evidence of an earlier failure. Never read from it, write to it, reset it or repair it.
- Viewer: http://127.0.0.1:8817/
- Exactly one graph controller may exist and it is the one your runner starts.

Your loop:
1. Paste section 2.1 of the guide (the preflight block) into a Windows PowerShell 5.1 window exactly as written. If it prints [BLOCKED], stop and send Vincent the escalation from section 9.4. Do not continue.
2. Confirm the viewer with section 3.2. Its viewer_identity.checkout_root must be C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2. If it is not, or the viewer is absent, start it with section 3.1 and confirm again.
3. Paste the start block of section 4.3. It starts C:\nscrev\reports\gauntlet-run-runner.ps1 detached and prints the transcript path.
4. Paste the poll block of section 4.3 repeatedly until it prints "[POLL] finished". Each call waits up to four minutes. The run is long; keep polling. Never start a second runner.
5. Read the line "[DONE] Operator loop ended with status: X" and act on X:
   - complete: tell Vincent "gauntlet complete" and paste the [STATE] lines.
   - awaiting_human: tell Vincent which tasks are waiting (the waiting_human list in the last result JSON).
   - anything else, [BLOCKED], or no JSON output: write the section 9.4 escalation, hand it to Vincent for the REVIEWER session, and stop.
6. Do not run anything again after an escalation until the reviewer answers RESUME.

Allowed: sections 2.1, 3.1, 3.2, 4.3, 5.1 (read-only status and journal tail), and reading files under the checkout root's .assistant-control and operator-logs.
Forbidden: editing any file; any git command that changes anything; clear-background-job; stop-graph; stop-background-jobs; Docker; Unity; GitHub; any python command other than the ones in those sections; retrying a failed command; changing any flag or path; starting a second runner or a second controller.

If anything is unclear, stop and ask Vincent. Reply in short plain sentences and paste exact output lines rather than paraphrasing them.
```

#### 9.5.2 LANE SUPERVISOR A — fresh session, working directory `C:\NSC\GauntletFresh1140-20260912-1`

```text
You are LANE SUPERVISOR A for the NSC-1140..NSC-1147 gauntlet. You are a read-only watcher. You never mutate anything.

Your lane: NSC-1141, NSC-1145, NSC-1146, NSC-1147, and any decomposition child generated for NSC-1145 or NSC-1146 (ids NSC-1148 upward; find them in run.scope.generated from the viewer API, or in the parent row's decomposition_children). This is the serial dependency chain: 1145 depends on 1141, 1146 on 1145, 1147 on 1146. A stall here costs the most, so report it first.

Facts:
- Guide: C:\nscrev\reports\gauntlet-run-instructions.md (read sections 1, 5, 7, 9 before your first report)
- Source: C:\NSC\GauntletFresh1140-20260912-1 on branch gauntlet-test/throughput-e90670d
- Checkout root: C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2; records in .assistant-control
- Viewer: http://127.0.0.1:8817/api/state
- Exactly one graph controller exists; it is the OPERATOR's runner. Lanes are a reporting convention, not something the controller enforces.

What you may run (all read-only): the graph-plan block of section 5.1; worker-status <task>; inspect-decomposition <task>; checkout <task>; dependencies <task>; status --task <task>; readiness <task>; the viewer API block of section 3.2; and reading any file under the checkout root's .assistant-control and operator-logs.

What you must never do: start a controller or a worker; run start-worker, run-worker, reserve, settle-worker, stop-worker, decompose, apply-decomposition, candidate, post-crew, materialize-candidate, review, integrate, prepare, refresh-prepared, scope, sync-candidate, revise, preserve-success, maintenance-run or gauntlet-replay; run clear-background-job, stop-graph or stop-background-jobs; edit any file anywhere; run any git command that changes anything; touch Docker, Unity, GitHub, the old checkout root C:\NSC\GauntletFresh1140-20260912-1-Checkouts, or any task outside your lane.

Report every 15 minutes, or immediately on a failure, in this shape:
LANE A - <UTC time>
Per task (NSC-1141, 1145, 1146, 1147 and children): planner action or blocked reason; worker status and run_id; background job kind/job_id/status; candidate commit if any.
New journal events since my last report, verbatim.
Durable evidence paths I read.
Anything that disagrees between the viewer and the records.
Nothing mutated.

On any failure in your lane, write the escalation in section 9.4 of the guide and hand it to Vincent for the REVIEWER. Then stop and wait. Never retry.
```

#### 9.5.3 LANE SUPERVISOR B — fresh session, working directory `C:\NSC\GauntletFresh1140-20260912-1`

```text
You are LANE SUPERVISOR B for the NSC-1140..NSC-1147 gauntlet. You are a read-only watcher. You never mutate anything.

Your lane: NSC-1142, NSC-1143, NSC-1144. These three are independent single-agent tasks with no dependencies, so they are the evidence for parallel admission. Watch how many of them hold an admission reservation at the same time and whether --capacity 3 is the binding limit.

Facts:
- Guide: C:\nscrev\reports\gauntlet-run-instructions.md (read sections 1, 5, 7, 9 before your first report)
- Source: C:\NSC\GauntletFresh1140-20260912-1 on branch gauntlet-test/throughput-e90670d
- Checkout root: C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2; records in .assistant-control
- The admission registry is Source-scoped: C:\NSC\GauntletFresh1140-20260912-1\.git\assistant-control-admissions.json. Read it; never edit it.
- Viewer: http://127.0.0.1:8817/api/state
- Exactly one graph controller exists; it is the OPERATOR's runner. Lanes are a reporting convention, not something the controller enforces.

What you may run (all read-only): the graph-plan block of section 5.1; worker-status <task>; checkout <task>; dependencies <task>; status --task <task>; readiness <task>; the viewer API block of section 3.2; and reading any file under the checkout root's .assistant-control and operator-logs, plus the admission registry above.

What you must never do: start a controller or a worker; run start-worker, run-worker, reserve, settle-worker, stop-worker, decompose, apply-decomposition, candidate, post-crew, materialize-candidate, review, integrate, prepare, refresh-prepared, scope, sync-candidate, revise, preserve-success, maintenance-run or gauntlet-replay; run clear-background-job, stop-graph or stop-background-jobs; edit any file anywhere; run any git command that changes anything; touch Docker, Unity, GitHub, the old checkout root C:\NSC\GauntletFresh1140-20260912-1-Checkouts, or any task outside your lane.

Report every 15 minutes, or immediately on a failure, in this shape:
LANE B - <UTC time>
Per task (NSC-1142, 1143, 1144): planner action or blocked reason; worker status, run_id, started_at / finished_at / settled_at; candidate commit if any.
Reservations currently in the Source registry, with their task_id and checkout_root.
Highest number of my tasks running a worker at the same time so far.
New journal events since my last report, verbatim.
Durable evidence paths I read.
Nothing mutated.

On any failure in your lane, write the escalation in section 9.4 of the guide and hand it to Vincent for the REVIEWER. Then stop and wait. Never retry.
```

#### 9.5.4 LANE SUPERVISOR C — fresh session, working directory `C:\NSC\GauntletFresh1140-20260912-1`

```text
You are LANE SUPERVISOR C for the NSC-1140..NSC-1147 gauntlet. You are a read-only watcher. You never mutate anything.

Your lane: NSC-1140 and every decomposition child generated for it (ids NSC-1148 upward; find them in run.scope.generated from the viewer API, or in NSC-1140's decomposition_children). NSC-1140 is the first paid two-provider decomposition, so your lane carries the overlap evidence the owner cares about: while the NSC-1140 decompose job runs, does the controller keep preparing, scoping, reserving and starting workers for other tasks?

Facts:
- Guide: C:\nscrev\reports\gauntlet-run-instructions.md (read sections 1, 5, 7, 8, 9 before your first report)
- Source: C:\NSC\GauntletFresh1140-20260912-1 on branch gauntlet-test/throughput-e90670d
- Checkout root: C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2; records in .assistant-control
- The NSC-1140 job index is .assistant-control\NSC-1140.background-job.json; its run root is .assistant-control\background-jobs\NSC-1140\<job_id>\ with launch.request.json, receipt.json, stdout.log, stderr.log and, after a stop, cooperative-stop.json.
- Viewer: http://127.0.0.1:8817/api/state
- Exactly one graph controller exists; it is the OPERATOR's runner. Lanes are a reporting convention, not something the controller enforces.

What you may run (all read-only): the graph-plan block of section 5.1; inspect-decomposition NSC-1140; worker-status <task>; checkout <task>; status --task <task>; the viewer API block of section 3.2; the measurement snippet in section 8.2; and reading any file under the checkout root's .assistant-control and operator-logs.

What you must never do: start a controller or a worker; run decompose, apply-decomposition, start-worker, run-worker, reserve, settle-worker, stop-worker, candidate, post-crew, materialize-candidate, review, integrate, prepare, refresh-prepared, scope, sync-candidate, revise, preserve-success, maintenance-run or gauntlet-replay; run clear-background-job, stop-graph or stop-background-jobs; docker stop, docker rm or docker compose anything; edit any file anywhere; run any git command that changes anything; touch Unity, GitHub, the old checkout root C:\NSC\GauntletFresh1140-20260912-1-Checkouts, or any task outside your lane.

Report every 15 minutes, or immediately on a failure, in this shape:
LANE C - <UTC time>
NSC-1140: planner action or blocked reason; background job kind/job_id/status/attempt; provider_container name and provider_container_cleanup status; elapsed time since job_launched.
Children (once they exist): id, planner action or blocked reason, worker status, candidate commit.
Overlap evidence: every action_started event in the journal that happened while the NSC-1140 job was open and belongs to a different task.
New journal events since my last report, verbatim.
Durable evidence paths I read.
Nothing mutated.

On any failure in your lane, write the escalation in section 9.4 of the guide and hand it to Vincent for the REVIEWER. Then stop and wait. Never retry.
```

#### 9.5.5 REVIEWER / INTEGRATOR — one session for the whole run, working directory `C:\NSC\GauntletFresh1140-20260912-1`

```text
You are the gauntlet REVIEWER and INTEGRATOR for NSC-1140..NSC-1147: the only session with judgment authority. An OPERATOR session runs the single graph controller; three LANE SUPERVISOR sessions watch disjoint lanes read-only and escalate to you. You verify everything they produce and never trust authorship.

Facts:
- Guide: C:\nscrev\reports\gauntlet-run-instructions.md - read every section first.
- Controller project and Source: C:\NSC\GauntletFresh1140-20260912-1, branch gauntlet-test/throughput-e90670d, head 3e5314d0511db15d98f386e5d31c8849a8d9c957 = the 1140 gauntlet commit bdaaa2d153a0504c471fbd66afd70f1984b171d9 plus the ten reviewed AssistantControl performance commits cherry-picked from C:\nscrev\throughput branch throughput/background-decomposition at e90670da5b5fc19567e1efe1cb655c43de292f4e. The Pipeline/AssistantControl tree is byte-identical to that reviewed head (tree 9195da84a09968e603222d71ff779261fcf9f1f8). Read Pipeline/AssistantControl/README.md, Pipeline/AssistantControl/CURRENT.md and Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md there.
- Checkout root: C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2.
- The old root C:\NSC\GauntletFresh1140-20260912-1-Checkouts holds durable evidence of two failed prepare NSC-1141 attempts on 2026-09-12 (git clone hit an MSYS sh.exe "couldn't create signal pipe, Win32 error 5"). Preserve it exactly. Never reuse, reset or repair it.
- Coordination issue: https://github.com/cathode26/NoSafeCircle-Homework-Rehearsal/issues/36

Rules:
- The live run is read-only for you unless Vincent explicitly authorizes a specific mutation in this conversation. Never move the Source branch, reset, delete records, or run any wipe command. Diagnose from worker outcomes (NSC-<id>.json, worker-runs\<task>\<sha>\stderr.log), job receipts (background-jobs\<task>\<job_id>\receipt.json, stderr.log, cooperative-stop.json) and the journal before touching anything.
- Never edit Pipeline/AssistantControl while the loop runs: the controller and every detached child import that working tree, so a half-written module would run. Fixes wait for the loop to end.
- No paid providers outside run-graph --authorize-provider-spend. No push, no merge, no GitHub state change other than the Issue #36 report when Vincent asks.
- To stop a running controller use the stop-graph block in section 6.1, and only with Vincent's word. Use stop-background-jobs (6.2) after the controller process was lost, and again whenever a stop result lists cleanup_pending, until it prints stopped. Expect roughly a minute per killed decomposition because of the 60 s container tombstone.
- A failed, died, cancelled or quarantined background job blocks only its task and is never relaunched automatically. You decide whether clear-background-job is justified, and only after reading that job's stderr.log, receipt.json, provider_container_cleanup and (for a stopped decomposition) cooperative-stop.json. It refuses while a tombstone is active or a ticket does not authenticate, and it tells you when to retry.
- An authentication_failed cleanup or an unreadable background-job index is an operator repair by hand, with Vincent, never an automatic retry. A startup_refused event means the controller refused to plan beside an ambiguous ticket or an unverified container; read its error first. Nothing was killed or removed on either path.
- Answer every escalation with one word first, RESUME, STOP or TICKET, then the reasoning in a few sentences. STOP means wait for Vincent.
- Own the measurement (guide section 8) and the final Issue #36 report (guide section 10). Apply its PASS/FAIL rule literally; do not soften it.

First actions now: read the guide; read graph-controller.json, graph-controller-owner.json, the last 40 journal events and every NSC-*.background-job.json under C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2\.assistant-control; summarize the run state to Vincent in under 15 lines; say whether the operator may start, and which risk you will watch first (the first concurrent decompositions under --background-jobs 4 against --capacity 3 workers, and whether git clone survives on this host after the 12:35Z sh.exe failure).
```

---

## 10. Final report for Issue #36

Repository-relative paths: everything under `.assistant-control/...` is relative to
the checkout root `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2`; everything under
`Tasks/...` and `Pipeline/...` is relative to the project
`C:\NSC\GauntletFresh1140-20260912-1`.

```markdown
## Gauntlet NSC-1140..NSC-1147 on the reviewed asynchronous graph controller

**Result: PASS | FAIL**

### Identity
- Project / Source: `C:\NSC\GauntletFresh1140-20260912-1`, branch `gauntlet-test/throughput-e90670d`, head `<sha>`
- Contains: gauntlet `bdaaa2d153a0504c471fbd66afd70f1984b171d9` + ten reviewed commits from `throughput/background-decomposition` @ `e90670da5b5fc19567e1efe1cb655c43de292f4e`
- `Pipeline/AssistantControl` tree: `<git rev-parse HEAD:Pipeline/AssistantControl>`
- Checkout root: `C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2`
- Worker config: `Pipeline/AssistantControl/worker-haiku.example.json` (provider claude, model claude-haiku-4-5-20251001)
- Flags: `--capacity 3 --background-jobs 4 --max-actions 240 --auto-approve-gauntlet --authorize-provider-spend --human-review-task NSC-042 --target-branch gauntlet-test/throughput-e90670d`

### Outcome per root
| Task | Final planner state | Candidate commit | Integrated | Evidence |
|---|---|---|---|---|
| NSC-1140 | | | | `.assistant-control/NSC-1140.json`, `Tasks/NSC-1140.yaml` |
| NSC-1141 | | | | `.assistant-control/NSC-1141.json`, `Tasks/NSC-1141.yaml` |
| NSC-1142 | | | | `.assistant-control/NSC-1142.json`, `Tasks/NSC-1142.yaml` |
| NSC-1143 | | | | `.assistant-control/NSC-1143.json`, `Tasks/NSC-1143.yaml` |
| NSC-1144 | | | | `.assistant-control/NSC-1144.json`, `Tasks/NSC-1144.yaml` |
| NSC-1145 | | | | `.assistant-control/NSC-1145.json`, `Tasks/NSC-1145.yaml` |
| NSC-1146 | | | | `.assistant-control/NSC-1146.json`, `Tasks/NSC-1146.yaml` |
| NSC-1147 | | | | `.assistant-control/NSC-1147.json`, `Tasks/NSC-1147.yaml` |
| NSC-1148+ (generated) | | | | `.assistant-control/NSC-<id>.json` |

### Measurements (from `.assistant-control/graph-controller-events.jsonl`)
- Total elapsed: `<s>` over `<n>` controller invocations
- Action time by kind: `<table>`
- Harvest + plan() + state-write gap: median `<s>`, max `<s>`, total `<s>` (DERIVED - no direct field exists)
- Max simultaneous workers: `<n>` at `<utc>`
- Max simultaneous background jobs: `<n>` at `<utc>`
- Unrelated work during each background job: `<per-job list, or NOTHING ELSE RAN>`
- Worker completion -> settlement delay per task (from `worker.finished_at` / `worker.settled_at`): `<list>`
- Duplicate launches: `<none | detail>`

### Blocked, failed and stopped
| Task | Event | Reason | Evidence path (relative to the checkout root) |
|---|---|---|---|
| | | | `.assistant-control/background-jobs/<task>/<job_id>/stderr.log` |
| | | | `.assistant-control/background-jobs/<task>/<job_id>/receipt.json` |
| | | | `.assistant-control/worker-runs/<task>/<sha256 run_id>/stderr.log` |

### Viewer versus durable records
- `/api/state` `viewer_identity.checkout_root`: `<value>`
- `run.targets` matched `graph-controller.json` `targets`: yes | no
- `run.scope.visible` matched the eight roots plus generated children: yes | no
- Disagreements observed: `<none | detail>`

### Preserved evidence
- Journal: `.assistant-control/graph-controller-events.jsonl`
- State: `.assistant-control/graph-controller.json`
- Owner: `.assistant-control/graph-controller-owner.json`
- Per-invocation results: `operator-logs/run-graph-*.json`
- Runner transcript: `operator-logs/runner-*.transcript.txt`
- Retired root left untouched: `C:\NSC\GauntletFresh1140-20260912-1-Checkouts` (two failed `prepare NSC-1141` attempts, 2026-09-12 12:35Z and 12:36Z)
```

### PASS/FAIL rule

**PASS** requires every one of these:

1. The last `run-graph` status is `complete`, and the final `graph-plan` reports
   `complete` with all eight roots and every generated child in `complete[]`.
2. `blocked[]` is empty and `waiting_human[]` is empty in that final plan.
3. No `startup_refused`, no `job_quarantined`, no `authentication_failed`, and no
   `unreadable_indexes` anywhere in the run.
4. No duplicate launch: no repeated `job_launched` for one `job_id` or one
   `task_id`, no repeated `start_worker` for one `(task_id, run_id)`, and exactly
   one run-root directory under `.assistant-control/background-jobs/<task>/` per
   attempt recorded on that task's index.
5. Max simultaneous background jobs is at least 2 **and** at least one `decompose`
   job interval contains an `action_started` for a different task — the controller
   demonstrably did unrelated work while a paid decomposition ran.
6. Every worker reached `settled_at`, and no worker record is left with
   `capacity_released` unset.
7. Every viewer observation matched the durable record at the time it was taken.
8. Nothing under `C:\NSC\GauntletFresh1140-20260912-1-Checkouts` was read into the
   run, modified or deleted, and nothing was pushed.

**FAIL** if any one of those is false. A run that finished but serialized (point 5
false) is a FAIL for the purpose of this trial, because the trial exists to measure
overlap; say so explicitly and keep the rest of the measurements.

---

## 11. If the staffing commit is integrated

A `--worker-slots N` staffing feature — three persistent logical worker slots under
one controller, with `staffing_slot_*` journal events and a slot projection in
`/api/state` — was being implemented concurrently in `C:\nscrev\throughput` while
this guide was written. It was **not reviewed, not integrated, and not present** in
`C:\NSC\GauntletFresh1140-20260912-1` at head `3e5314d`. Everything above is written
for the reviewed head without it.

If and only if the reviewer has integrated it into this project and verified it:

- **The run command gains one flag**, `--worker-slots 3`, alongside the existing
  `--capacity 3`. Add it to the `$Arguments` array in
  `C:\nscrev\reports\gauntlet-run-runner.ps1` after `"--capacity", "3",` and
  re-run `C:\nscrev\reports\parse-check.ps1 -ScriptPath C:\nscrev\reports\gauntlet-run-runner.ps1`
  before starting anything. Change nothing else in the runner.
- **UNVERIFIED:** how `--worker-slots` interacts with `--capacity`, whether one
  bounds the other, what its valid range is, whether it changes admission or only
  attributes work to a slot, and what the `staffing_slot_*` event names and fields
  actually are. Read the integrated code and the updated
  `Pipeline/AssistantControl/README.md` before writing any of that into a report.
  Do not assume the two numbers may differ, and do not assume a slot survives a
  controller restart.
- **Observation changes**: expect `staffing_slot_*` events in
  `.assistant-control/graph-controller-events.jsonl` and a slot projection in
  `/api/state`. Add to the measurement plan: peak occupied slots, idle-slot time,
  and whether a slot was ever occupied by two tasks at once. Keep the existing
  worker-interval sweep in section 8.2 as the independent check — a slot projection
  is a report of the run, not proof of it.
- **Nothing else in this guide changes.** The stop commands, the failure handling,
  the lane topology, the never-do lists and the PASS/FAIL rule all apply unchanged.
  If a staffing slot appears to hold a worker after `settle-worker`, that is a
  correctness problem: stop with section 6.1 and preserve everything.

---

## 12. Verification ledger

### 12.1 Verified by reading code, docs or durable records

| Fact | How |
|---|---|
| Project on `gauntlet-test/throughput-e90670d`; `bdaaa2d` is the gauntlet commit with ten AssistantControl commits above it ending at `3e5314d` | `git log --oneline -15` in the project |
| `Pipeline/AssistantControl` tree at `3e5314d` identical to the reviewed head | `git rev-parse 3e5314d:Pipeline/AssistantControl` = `9195da84a09968e603222d71ff779261fcf9f1f8` = `git rev-parse e90670da5b...:Pipeline/AssistantControl` in `C:\nscrev\throughput` |
| The branch advanced to `4f46117fff7504280b79ff30d762b0baa666d225` (viewer run-scope commit) during writing; `bdaaa2d` and `3e5314d` are still ancestors; the AC tree at HEAD is now `f9cab0ff85087f7af9d89ad928001b38e57aa9e7` | `git merge-base --is-ancestor`, `git show --stat HEAD`, `git rev-parse HEAD:Pipeline/AssistantControl` |
| `C:\nscrev\throughput` is on `throughput/background-decomposition` at `e90670da5b5fc19567e1efe1cb655c43de292f4e` | `git rev-parse` |
| Eight contracts, their `execution_scope`, `decomposition_state`, `depends_on`, `contract_disposition: active`, no `unity_builder` | read `Tasks/NSC-114*.yaml` |
| 1140 needs decomposition and yields an Alpha and a Beta child (AC-001/AC-002) | `Tasks/NSC-1140.yaml` |
| `graph-plan` lists exactly the eight roots, `status actionable`, `decompose NSC-1140` + four `prepare`, three dependency-blocked | ran read-only against `...-Checkouts-2` |
| Worker config contents (provider claude, `claude-haiku-4-5-20251001`, volume `nosafecircle_claude-config`, `timeout_seconds` 900) | read `worker-haiku.example.json` |
| Docker reachable, server 29.7.2; volume `nosafecircle_claude-config` present | `docker version`, `docker volume ls` |
| Port 8817 already held by a python listener; `...-Checkouts-2\viewer-8817.log` holds the viewer banner | `Get-NetTCPConnection`, file read |
| Viewer exclusive port bind, 405 on writes, `viewer_identity` fields | `viewer.py:34-67, 879-884, 910-916` |
| Viewer `--task` roots flag and the `run.scope` projection, committed in `4f46117` | `__main__.py:51-54`, `viewer.py:86-95, 141-145, 473-525` |
| The README viewer section still does not document `--task` or the run scope | `git show HEAD:Pipeline/AssistantControl/README.md`, viewer paragraph |
| Retired root evidence: released owner pid 50168, `blocked` state, MSYS `sh.exe` clone failure, 8 journal events, no `background-jobs` directory | read the files |
| Every `run-graph` flag name, default and constraint | `__main__.py:163-200, 260-306` |
| Exit codes: `run-graph` 0 unless `blocked`/`command_failed`; `stop-graph` 0 for `stopped`/`stop_requested`/`already_released`; `stop-background-jobs` 0 only for `stopped` | `__main__.py:306, 314, 354` |
| Statuses `complete`/`awaiting_human`/`blocked`/`actionable`, `capacity_full`, `action_limit_reached`, `stopped`, `handoff_required`, `worker_still_running`, `background_jobs_running`, `interrupted` | `graph_controller.py:838-840, 1599-1629, 1224, 1639` |
| `command_failed` shape | `__main__.py:498-500` |
| `startup_refused` is a journal event, not a status | `graph_controller.py:1081-1092` |
| Journal action events are `action_started`/`action_completed`/`action_failed` with `duration_seconds` | `graph_controller.py:926-966` |
| Every `job_*` event name and its trigger | `graph_controller.py:1040-1174, 1285-1288` |
| `controller_started`/`controller_released`/`controller_stopped`/`stop_request_ignored` payloads | `graph_controller.py:357-413, 1262-1267, 1569-1574` |
| State-file fields incl. `history` capped at 100 and `background_jobs` summary | `graph_controller.py:859-901`, `background_jobs.py:272-280` |
| `cleanup_pending` / `unreadable_indexes` derivation | `graph_controller.py:1671-1690, 1788-1817` |
| `stop-graph` statuses incl. `stopped_cleanup_pending` and `already_released_cleanup_pending`, and the stale-owner refusal | `graph_controller.py:1693-1785` |
| `stop-background-jobs` refuses under a live controller and finalizes tombstones | `__main__.py:315-354` |
| `clear-background-job` refusal conditions and the archive filename | `background_jobs.py:1998-2058` |
| `ACTIVE_STATUSES`, `TERMINAL_STATUSES`, `STOP_GRACE_SECONDS` 15, `CONTAINER_TOMBSTONE_SECONDS` 60, `CONTAINER_WINDOW_SECONDS` 15 | `background_jobs.py:70-75` |
| Ticket and run-root file layout, container labels | `background_jobs.py:165-208, 556-580, 614, 624, 2229, 2365, 2391` |
| Worker run root layout and `job_name` derivation | `worker_launcher.py:38-39, 152-188` |
| `worker.started_at` / `finished_at` / `settled_at` | `crew_worker.py:105, 172`, `worker_settlement.py:123` |
| Admission registry is Source-scoped in the Git common dir, and does not currently exist | `admission.py:27-31`, file check |
| Capacity semantics | `graph_controller.py:1386`, `admission.py:299` |
| Background-job limit and the deferred-launch wait | `graph_controller.py:1398-1407, 1464-1470` |
| Wait budgets: decompose 3780 s, post_crew 1800 s, worker `timeout_seconds`+180 | `graph_controller.py:70-71, 1195-1200` |
| Single-controller enforcement via the exclusive lock | `graph_controller.py:304-310` |
| `--target-branch` asserted against the actual branch; committed graph paths must be clean | `graph_controller.py:421-439` |
| NSC-042 permanently human-review | `graph_controller.py:245`, `__main__.py:266` |
| Planning cost calibration (~0.2 s warm, ~5 s after a HEAD move) | `Docs/AI-Pipeline/ASSISTANT_AUTONOMOUS_GRAPH.md`, "Planning cost per cycle" |
| Both extracted scripts parse | `parse-check.ps1 -ScriptPath ...` printed `[PARSE] OK` for the runner and the poll block |
| The measurement snippet runs and produces correct output on a real journal | exercised read-only against the retired root's 8-event journal |

### 12.2 UNVERIFIED

| Claim | Why it is not verified |
|---|---|
| The viewer currently listening on 8817 serves the `4f46117` scope change | A running viewer serves the code it imported at start, and that listener started at 16:43 local, before the commit. Restart it (section 3.4) if you need the scope projection. |
| The `4f46117` viewer commit itself has been reviewed | It landed on this branch while the guide was being written. Its own tests (`test_viewer.py`) were changed in the same commit; nobody in this guide's chain has reviewed it. The reviewer should look before the run starts. |
| `--worker-slots N` semantics, range, interaction with `--capacity`, and the `staffing_slot_*` event names and fields | Not present in this project at `3e5314d` or `4f46117`; being written elsewhere and not reviewed. |
| `C:\nscrev\reports\gauntlet-run-1140-runner.ps1` — a second runner file, written by another session while this guide was being finished, pinned to `$ExpectedControlHead = 4f46117f...` with the same checkout root and the same `--capacity 3 --background-jobs 4` | Read read-only; not written or modified here. **Only one runner may be used.** Decide with Vincent which file the operator pastes, and delete or rename the other before the run so no session starts a second controller. This guide's runner is `C:\nscrev\reports\gauntlet-run-runner.ps1`, which checks ancestry rather than pinning an exact head. |
| The concurrency, overlap and settlement branches of the section 8.2 snippet | The only journal available to test against had no jobs and no workers. |
| That `git clone` will now succeed on this host | The 12:35Z MSYS `sh.exe` "couldn't create signal pipe, Win32 error 5" failure is a host condition; nothing read here proves it is gone. It is the most likely early failure. |
| That `--capacity 3` and `--background-jobs 4` are the right numbers for this machine | The owner set the floors (workers >= 3, background jobs 4). Whether the host sustains 3 crews plus 4 detached children was not measured. |
| Expected total run time | No completed run of this family on this controller exists to compare against. |

---

## 13. What in the existing runbook is wrong for this project

`C:\nscrev\reports\gauntlet-orchestration-staffing.md` remains a good description of
the three-tier staffing idea, and sections 4.5, 5, 6 and 7 were the basis for
sections 4.3, 9.4 and 9.5 here. These specifics are wrong for this run:

1. **§2 / §4.1 controller source.** It runs the controller from
   `C:\nscrev\throughput` and asserts `$ExpectedControlHead = e90670da5b...`. This
   run has no separate controller clone: the controller runs from
   `C:\NSC\GauntletFresh1140-20260912-1`, and the equivalent assertion is that both
   `bdaaa2d` and `3e5314d` are ancestors of HEAD.
2. **§2 / §4.1 branch.** It names `gauntlet-replay/fresh-1140-20260912` and commit
   `bdaaa2d153a0504c471fbd66afd70f1984b171d9` as the live Source. The project is now
   on `gauntlet-test/throughput-e90670d` at `3e5314d`, ten commits ahead.
3. **§2 / §4.x checkout root.** Every block names
   `C:\NSC\GauntletFresh1140-20260912-1-Checkouts`. That root is now evidence of two
   failed `prepare NSC-1141` attempts and must not be used; this run uses
   `...-Checkouts-2`.
4. **§2 "the checkout root holds no `.assistant-control` yet".** No longer true of
   the old root: it holds an owner record, a `blocked` state file, an 8-event
   journal and `NSC-1141.json`.
5. **§4.1 `--capacity 20`.** Too high for what the owner asked for here
   (workers >= 3) and it hides the admission limit the trial is meant to observe.
   This guide uses `--capacity 3`.
6. **§4.1 `--background-jobs 2`.** The owner asked for 4 in this run, which is also
   the code default.
7. **§4.5 runner path.** It points at `C:\nscrev\reports\operator-runner-4-1.ps1`,
   which carries the throughput-clone identity. This run uses
   `C:\nscrev\reports\gauntlet-run-runner.ps1`.
8. **§4.6 / §8 event glossary is incomplete.** It omits `job_spawn_failed`,
   `job_unverifiable`, `job_cleanup_pending` as an ordinary loop retry,
   `controller_started`, `controller_released` and all three action events. It also
   describes "the viewer's run scope only shows the controller's targets" without
   the derived-scope distinction of section 3.3.
9. **Rule §3.1 is stated about the wrong directory.** "While the operator loop is
   running, nobody edits `C:\nscrev\throughput`" is correct in spirit but names the
   clone; here the rule binds
   `C:\NSC\GauntletFresh1140-20260912-1\Pipeline\AssistantControl`.
10. **It has no Source-scoped admission-registry check.** The reservation registry
    lives in the Source's Git common dir, not the checkout root, so a reservation
    from another checkout root silently consumes capacity. Both the preflight and
    the runner here check for it.
11. **§7.2 first-risk framing.** "The first concurrent Unity validations under
    `--background-jobs 2`" does not apply: none of these eight contracts registers a
    `unity_builder`, so `post_crew` here does candidate registration without a Unity
    materialization step.

Not wrong, but worth carrying forward unchanged: the `runner-current.txt` pointer
discipline (never poll "the newest file"), the idle-cycle guard, the
one-word-first RESUME/STOP/TICKET reply, and the rule that a failed background job
blocks only its task and is never relaunched automatically.
