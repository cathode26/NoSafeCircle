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
