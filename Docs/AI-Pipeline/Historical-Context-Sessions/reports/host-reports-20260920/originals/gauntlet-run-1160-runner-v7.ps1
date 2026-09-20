& {
    # v6 = v5 with ONE change: a bounded recovery for the transient
    # checkouts.lock acquisition race. v5 broke on any non-zero exit, which
    # ended run 2 after a single invocation when a post_crew launch lost a 10 s
    # race for .assistant-control\checkouts.lock against a background child
    # that had launched 1.1 s earlier. The failure is non-destructive: every
    # background child kept its own run root, finished, and wrote its receipt,
    # and the controller released the graph cleanly. Nothing else in the
    # identity gate, the selection or the parameters is changed.
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    # ============================================================
    # IDENTITY
    # ============================================================
    $ControlSource = "C:\NSC\GauntletFresh1140-20260912-1"
    $ExpectedControlHead = "799907e03959626323f74e2662378931e734234a"
    $Source = "C:\NSC\GauntletFresh1140-20260912-1"
    $ExpectedBranch = "gauntlet-replay/fresh-1160-20260913"
    $CheckoutRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-6"
    $Records = Join-Path $CheckoutRoot ".assistant-control"
    $WorkerConfig = Join-Path $Source "Pipeline\AssistantControl\worker-haiku.example.json"
    $Targets = @("NSC-1160", "NSC-1161", "NSC-1162", "NSC-1163", "NSC-1164", "NSC-1165", "NSC-1166", "NSC-1167")
    $LogDir = Join-Path $CheckoutRoot "operator-logs"
    $MaxInvocations = 40
    $ContinueStatuses = @("worker_still_running", "background_jobs_running", "action_limit_reached", "capacity_full")
    # v7 = v6 with a larger lock-contention allowance, two concurrent
    # background jobs instead of four (less density on checkouts.lock), and a
    # durable progress guard: a recovery that adds no journal line counts as
    # idle, and three idle recoveries in a row stop the loop. Everything else,
    # including the identity gate, the eight targets, capacity 10, max-actions
    # 240 and the human-review boundary, is unchanged from v5/v6.
    $MaxLockRecoveries = 20
    $LockRecoveries = 0
    $IdleRecoveries = 0
    $JournalPath = Join-Path $Records "graph-controller-events.jsonl"
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
        # The controller runs from the Source itself, and integrations move its
        # HEAD forward during the run: require descent from the reviewed head,
        # not equality with it.
        $Previous = $ErrorActionPreference
        $Ancestry = 1
        try {
            $ErrorActionPreference = "Continue"
            & git -C $ControlSource merge-base --is-ancestor $ExpectedControlHead HEAD 1> $null 2> $null
            $Ancestry = $LASTEXITCODE
        }
        finally {
            $ErrorActionPreference = $Previous
        }
        if ($Ancestry -ne 0) {
            throw "Controller source HEAD $ControlHead does not descend from $ExpectedControlHead. Escalate."
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
                "--capacity", "10",
                "--target-branch", $ExpectedBranch,
                "--max-actions", "240",
                "--background-jobs", "2"
            )

            $JournalBefore = 0
            if (Test-Path -LiteralPath $JournalPath) {
                $JournalBefore = @(Get-Content -LiteralPath $JournalPath).Count
            }

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

            # --- v6: bounded recovery for the transient checkouts.lock race ---
            $IsLockContention = ($LastStatus -eq "command_failed") -and ([string]$Result.error -like "*waiting for exclusive file lock*")
            if ($IsLockContention) {
                if ($LockRecoveries -ge $MaxLockRecoveries) {
                    $LastStatus = "lock_contention_exhausted:" + $LastStatus
                    Write-Host ("[STOP] checkouts.lock contention recurred more than " + $MaxLockRecoveries + " times. Escalate; this is a controller defect, not an environment problem.")
                    break
                }
                $JournalAfter = 0
                if (Test-Path -LiteralPath $JournalPath) {
                    $JournalAfter = @(Get-Content -LiteralPath $JournalPath).Count
                }
                if ($JournalAfter -gt $JournalBefore) {
                    $IdleRecoveries = 0
                }
                else {
                    $IdleRecoveries++
                }
                if ($IdleRecoveries -ge 3) {
                    $LastStatus = "lock_contention_no_progress:" + $LastStatus
                    Write-Host "[STOP] Three consecutive lock-contention recoveries added no journal event. Escalate."
                    break
                }
                $LockRecoveries++
                Write-Host ("[RECOVER " + $LockRecoveries + "/" + $MaxLockRecoveries + "] checkouts.lock contention; controller released cleanly, receipts retained, journal " + $JournalBefore + " -> " + $JournalAfter + " (idle recoveries " + $IdleRecoveries + "/3). Resuming in 25 s.")
                Start-Sleep -Seconds 25
                continue
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
        Write-Host ("[DONE] checkouts.lock recoveries used: " + $LockRecoveries + "/" + $MaxLockRecoveries)
        Write-Host "============================================================"
        Write-Host ("[STATE] Last result JSON: " + $LastOut)
        Write-Host ("[STATE] Records: " + $Records)
        Write-Host ("[STATE] Journal: " + (Join-Path $Records "graph-controller-events.jsonl"))
        Write-Host "[NEXT] complete -> tell Vincent. awaiting_human -> tell Vincent the waiting_human list. Anything else -> send the escalation to the reviewer and stop."
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
