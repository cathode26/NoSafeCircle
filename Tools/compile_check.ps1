<#
Compile the project's own assemblies with Unity's Roslyn, WITHOUT opening Unity.

WHY THIS EXISTS. Two bounded workers invented this independently on 2026-09-26 because they were
forbidden to run Unity and still needed feedback. It is strictly better than an editor for the one
question "does it build": seconds instead of minutes, and NINE WORKERS CAN RUN IT AT ONCE where
nine editors cannot run at all.

AND THE INTEGRATOR SHOULD RUN IT TOO. Twice on the night it was written, a one-line error cost a
full Unity run - `destroyCancellation.Token` for `destroyCancellationToken`, and a local shadowing
one in an enclosing scope. Both would have surfaced here in seconds.

FOUR THINGS THAT MAKE IT HONEST RATHER THAN DECORATIVE:

  1. IT CHECKS ONLY THE PROJECT'S OWN ASSEMBLIES, read from the .asmdef files. The first version
     globbed every .rsp under Library\Bee and "checked" 97 assemblies, 93 of which were Bee's
     internal artifacts - hash-named response files and .mvfrm module manifests that are not C# at
     all. It reported 93 failures, none real. A check that cannot tell its subject from its
     toolchain's scratch files is worse than none: it buries the four results that matter under
     ninety that do not.

  2. THE RESPONSE FILE IS A SNAPSHOT OF THE LAST IMPORT. Unity writes one .rsp per assembly with
     that import's source list, so a file added since then is MISSING and you get a phantom "type
     or namespace could not be found" for code that is fine. This appends every .cs that exists now
     under that assembly's own asmdef folder, minus any nested assembly's subtree. Without it the
     check lies toward false alarm.

  3. IT IS NOT UNITY'S COMPILE. Defines, analyzers and asmdef resolution are Unity's; this uses the
     response file Unity itself produced, which is close but not identical. A PASS here is strong
     evidence, not proof. A FAILURE here is proof.

  4. IT WRITES NOTHING INTO THE PROJECT, AND IT MEASURES THAT ON EVERY RUN. Every earlier version
     poisoned Library\Bee (2026-09-26, 05:23 and again 05:40). Unity's response file carries TWO
     output switches, -out: AND -refout:, and the script replaced only -out:. csc therefore wrote
     the reference assembly to Unity's own path, Library\Bee\artifacts\<dag>\<Name>.ref.dll, with
     the identity of the redirected -out: name, "nsc-compile-<Name>". Unity's next build compiled
     NoSafeCircle.DoorPrototype against such a file, recorded a reference to an assembly that
     exists nowhere, refused to load it at domain reload, and PlayMode discovered ZERO tests with
     exit code 0. Bee never rebuilds an assembly whose inputs did not change, so the poison
     survived every later Unity run. Full diagnosis:
     C:\nscrev\reports\design\diagnosis-playmode-zero-discovery-20260926.md
     Hence: every output switch is stripped, not just -out:; outputs go to a private directory
     under the REAL assembly name, so even a leak would carry the right identity; the script
     refuses to run while Unity holds the project; it names any reference assembly that was not
     written by Unity; and a tripwire snapshots Library before and after and FAILS the run
     (exit 3) if anything under it changed.

Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File Tools\compile_check.ps1
Exit 0 when every assembly compiles, 1 when any fails, 2 when the toolchain or the response files
cannot be found or Unity holds the project, 3 when the check itself wrote into the project -
deliberately distinguishable, because "nothing was checked" is not a pass, and "checked, and broke
the project" is worse than either.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath = (Get-Location).Path,
    [string]$UnityRoot = "C:\Program Files\Unity\Hub\Editor\6000.1.8f1"
)

$ErrorActionPreference = "Stop"
$ProjectPath = (Resolve-Path -LiteralPath $ProjectPath).Path.TrimEnd('\', '/')
Set-Location -LiteralPath $ProjectPath

$csc = Join-Path $UnityRoot "Editor\Data\DotNetSdkRoslyn\csc.dll"
if (-not (Test-Path -LiteralPath $csc)) {
    Write-Output "FAIL: Roslyn not found at $csc. Nothing was checked."
    exit 2
}
# Unity's own runtime runs Unity's own csc. Fall back to whatever `dotnet` is on PATH only if the
# bundled one is missing, so the check does not depend on a host-installed SDK version.
$dotnet = Join-Path $UnityRoot "Editor\Data\NetCoreRuntime\dotnet.exe"
if (-not (Test-Path -LiteralPath $dotnet)) { $dotnet = "dotnet" }

# GUARD 1 - NEVER WHILE UNITY HOLDS THE PROJECT. Unity keeps Temp\UnityLockfile open for as long as
# an editor (batchmode included) owns the project. While it does, Bee may be rewriting the very
# response files this script reads, and the tripwire below could not tell Unity's writes from ours.
# A lockfile left behind by a crash is not locked, opens fine, and is ignored.
$lockFile = Join-Path $ProjectPath "Temp\UnityLockfile"
if (Test-Path -LiteralPath $lockFile) {
    try {
        $probe = [System.IO.File]::Open($lockFile, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
        $probe.Close()
    }
    catch {
        Write-Output "FAIL: Unity holds this project ($lockFile is locked). Run the check in your own checkout, or after Unity exits. Nothing was checked."
        exit 2
    }
}

# THE EDITOR BUILD GRAPH, newest if there are several, and never the player graph: the player
# response files lack UNITY_EDITOR and the UnityEditor references, so editor-only code would
# "fail" for a reason that is an artifact of this script.
$artifactsRoot = Join-Path $ProjectPath "Library\Bee\artifacts"
$dagDirs = @(Get-ChildItem -LiteralPath $artifactsRoot -Directory -Filter "*.dag" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTimeUtc -Descending)

# The project's own assemblies, named by their .asmdef rather than guessed or globbed.
$asmdefFiles = @(Get-ChildItem "Assets" -Recurse -Filter "*.asmdef" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "Plugins" })
if (-not $asmdefFiles) {
    Write-Output "FAIL: no .asmdef files under Assets. Nothing was checked."
    exit 2
}

$dagDir = $null
foreach ($candidate in $dagDirs) {
    foreach ($asmdef in $asmdefFiles) {
        $probeName = (Get-Content -LiteralPath $asmdef.FullName -Raw | ConvertFrom-Json).name
        $probeRsp = Join-Path $candidate.FullName "$probeName.rsp"
        if ((Test-Path -LiteralPath $probeRsp) -and (Select-String -LiteralPath $probeRsp -Pattern '^-define:UNITY_EDITOR$' -Quiet)) {
            $dagDir = $candidate
            break
        }
    }
    if ($dagDir) { break }
}
if (-not $dagDir) {
    Write-Output "FAIL: no Editor build graph under $artifactsRoot holds a response file for a project assembly. Open the project in Unity once. Nothing was checked."
    exit 2
}

$assemblies = @()
foreach ($asmdef in $asmdefFiles) {
    $name = (Get-Content -LiteralPath $asmdef.FullName -Raw | ConvertFrom-Json).name
    $rsp = Join-Path $dagDir.FullName "$name.rsp"
    if (Test-Path -LiteralPath $rsp) {
        $assemblies += [pscustomobject]@{ Name = $name; Rsp = $rsp; AsmdefDir = $asmdef.DirectoryName }
    }
    else {
        Write-Output "NOTE: no response file for $name in $($dagDir.Name) - it was not built in the last import."
    }
}
if (-not $assemblies) {
    Write-Output "FAIL: no response files matched any project assembly in $($dagDir.Name). Open the project in Unity once."
    exit 2
}

# GUARD 2 - NAME THE POISON IF IT IS ALREADY THERE. Unity writes every reference assembly as
# <Name>.ref.dll with the identity <Name>. One whose identity differs was written by something
# other than Unity, and every assembly Unity compiles against it will refuse to load. The C# check
# below is still valid - csc resolves references by path, not by identity - so this warns rather
# than stops; but the integrator must know before the next Unity run, not after.
$poisoned = @()
foreach ($ref in Get-ChildItem -LiteralPath $dagDir.FullName -Filter "*.ref.dll" -ErrorAction SilentlyContinue) {
    $expected = $ref.Name.Substring(0, $ref.Name.Length - 8)
    try { $identity = [System.Reflection.AssemblyName]::GetAssemblyName($ref.FullName).Name } catch { continue }
    if ($identity -ne $expected) { $poisoned += "$($ref.Name) has identity '$identity'" }
}
if ($poisoned.Count -gt 0) {
    Write-Output "WARNING: $($poisoned.Count) reference assembly/assemblies in $($dagDir.Name) were NOT written by Unity. Unity's next build will produce assemblies that cannot load. Delete Library\Bee and Library\ScriptAssemblies and let Unity rebuild:"
    $poisoned | ForEach-Object { Write-Output "   $_" }
}

# GUARD 3, first half - SNAPSHOT THE PROJECT'S LIBRARY BEFORE TOUCHING ANYTHING. Compared after
# the compile; any difference is this script's own write, because Unity is not running (guard 1).
function Get-TreeSnapshot([string]$Root) {
    $snapshot = @{}
    if (Test-Path -LiteralPath $Root) {
        foreach ($f in Get-ChildItem -LiteralPath $Root -Recurse -File -Force -ErrorAction SilentlyContinue) {
            $snapshot[$f.FullName] = "$($f.Length):$($f.LastWriteTimeUtc.Ticks)"
        }
    }
    return $snapshot
}
$libraryRoot = Join-Path $ProjectPath "Library"
$before = Get-TreeSnapshot $libraryRoot

# EVERY OUTPUT OF THIS SCRIPT LIVES HERE AND NOWHERE ELSE, under the assembly's REAL name so the
# identity csc derives from -out: is the real one. Deleted at the end whatever happens.
$runDir = Join-Path ([System.IO.Path]::GetTempPath()) ("nsc-compile-check-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $runDir | Out-Null

# EVERY csc SWITCH THAT NAMES AN OUTPUT. -out: is replaced below; the rest are dropped outright.
# -refout: is the one that poisoned Library\Bee; the others are csc's remaining file-writing
# options, listed so that a response file that starts using one tomorrow still cannot write into
# the project. Anything not on this list is caught by the tripwire, not trusted.
$outputSwitch = '^[-/](out|refout|refonly|pdb|doc|errorlog|generatedfilesout|touchedfiles)(:|$)'

$failed = 0
try {
    foreach ($item in $assemblies) {
        $assembly = $item.Name
        $lines = @(Get-Content -LiteralPath $item.Rsp | Where-Object { $_ -notmatch $outputSwitch })

        $known = @{}
        foreach ($line in $lines) {
            if ($line -match '^"?(Assets[\\/].*\.cs)"?$') {
                $known[$matches[1].Replace('/', '\')] = $true
            }
        }

        # RECURSE FROM THE ASSEMBLY'S OWN ASMDEF FOLDER, not from the directories the snapshot
        # happened to know. FOUND BY THE HUD WORKER, and it is a SILENT FALSE PASS - the worst
        # kind: an entirely NEW FOLDER like Scripts/Hud/ was skipped without a word and the
        # assembly reported PASS while none of its new code was compiled. A NESTED .asmdef OWNS
        # ITS OWN SUBTREE, so a child assembly's sources are not swept into the parent.
        $asmdefDir = $item.AsmdefDir
        $added = 0
        Get-ChildItem -LiteralPath $asmdefDir -Recurse -Filter *.cs -ErrorAction SilentlyContinue | ForEach-Object {
            $rel = $_.FullName.Substring($ProjectPath.Length + 1)
            $ownedByChild = $false
            $probe = $_.Directory
            while ($probe -and $probe.FullName.Length -gt $asmdefDir.Length) {
                if (Get-ChildItem -LiteralPath $probe.FullName -Filter *.asmdef -ErrorAction SilentlyContinue) {
                    $ownedByChild = $true
                    break
                }
                $probe = $probe.Parent
            }
            if ($ownedByChild) { return }
            if (-not $known.ContainsKey($rel)) {
                $lines += ('"' + $rel + '"')
                $known[$rel] = $true
                $added++
            }
        }

        $out = Join-Path $runDir "$assembly.dll"
        $tmp = Join-Path $runDir "$assembly.rsp"
        ($lines + ('-out:"' + $out + '"')) | Set-Content -LiteralPath $tmp -Encoding utf8

        $output = & $dotnet $csc "@$tmp" 2>&1
        $cscExit = $LASTEXITCODE
        $errors = @($output | Select-String -Pattern "error CS")

        if ($errors.Count -gt 0 -or $cscExit -ne 0) {
            $failed++
            Write-Output "FAIL $assembly (csc exit $cscExit)"
            if ($errors.Count -gt 0) { $errors | Select-Object -First 8 | ForEach-Object { Write-Output "   $_" } }
            else { $output | Select-Object -First 8 | ForEach-Object { Write-Output "   $_" } }
        }
        else {
            Write-Output "PASS $assembly ($($known.Count) sources, $added appended since last import)"
        }
    }
}
finally {
    Remove-Item -LiteralPath $runDir -Recurse -Force -ErrorAction SilentlyContinue
}

# GUARD 3, second half - THE TRIPWIRE. A check that writes into the project it checks is not a
# check; it is the defect of 2026-09-26 wearing a PASS line. Exit 3 is neither "compiles" nor
# "does not compile" - it is "this script is broken, fix it before trusting anything it printed".
$after = Get-TreeSnapshot $libraryRoot
$changed = @()
foreach ($key in $after.Keys) {
    if (-not $before.ContainsKey($key) -or $before[$key] -ne $after[$key]) { $changed += $key }
}
foreach ($key in $before.Keys) {
    if (-not $after.ContainsKey($key)) { $changed += "$key (deleted)" }
}
if ($changed.Count -gt 0) {
    Write-Output "FAIL: compile_check WROTE INTO THE PROJECT - $($changed.Count) file(s) under Library changed during the check. Treat the project as contaminated (delete Library\Bee and Library\ScriptAssemblies) and fix this script before running it again:"
    $changed | Select-Object -First 20 | ForEach-Object { Write-Output "   $_" }
    exit 3
}

Write-Output "compile_check: $($assemblies.Count) project assembly/assemblies in $($dagDir.Name), $failed failed, 0 project files written."
if ($failed) { exit 1 } else { exit 0 }
