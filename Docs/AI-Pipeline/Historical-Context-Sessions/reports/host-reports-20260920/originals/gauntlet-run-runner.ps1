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
