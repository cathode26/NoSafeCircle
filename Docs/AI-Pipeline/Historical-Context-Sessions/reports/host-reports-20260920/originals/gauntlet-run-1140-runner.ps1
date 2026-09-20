& {
    $ErrorActionPreference = "Stop"
    $env:PYTHONUTF8 = "1"
    $env:PYTHONDONTWRITEBYTECODE = "1"

    # ============================================================
    # IDENTITY
    # ============================================================
    $ControlSource = "C:\NSC\GauntletFresh1140-20260912-1"
    $ExpectedControlHead = "4f46117fff7504280b79ff30d762b0baa666d225"
    $Source = "C:\NSC\GauntletFresh1140-20260912-1"
    $ExpectedBranch = "gauntlet-test/throughput-e90670d"
    $CheckoutRoot = "C:\NSC\GauntletFresh1140-20260912-1-Checkouts-2"
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
