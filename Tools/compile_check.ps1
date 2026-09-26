<#
Compile the project's own assemblies with Unity's Roslyn, WITHOUT opening Unity.

WHY THIS EXISTS. Two bounded workers invented this independently on 2026-09-26 because they were
forbidden to run Unity and still needed feedback. It is strictly better than an editor for the one
question "does it build": seconds instead of minutes, and NINE WORKERS CAN RUN IT AT ONCE where
nine editors cannot run at all.

AND THE INTEGRATOR SHOULD RUN IT TOO. Twice on the night it was written, a one-line error cost a
full Unity run - `destroyCancellation.Token` for `destroyCancellationToken`, and a local shadowing
one in an enclosing scope. Both would have surfaced here in seconds.

THREE THINGS THAT MAKE IT HONEST RATHER THAN DECORATIVE:

  1. IT CHECKS ONLY THE PROJECT'S OWN ASSEMBLIES, read from the .asmdef files. The first version
     globbed every .rsp under Library\Bee and "checked" 97 assemblies, 93 of which were Bee's
     internal artifacts - hash-named response files and .mvfrm module manifests that are not C# at
     all. It reported 93 failures, none real. A check that cannot tell its subject from its
     toolchain's scratch files is worse than none: it buries the four results that matter under
     ninety that do not.

  2. THE RESPONSE FILE IS A SNAPSHOT OF THE LAST IMPORT. Unity writes one .rsp per assembly with
     that import's source list, so a file added since then is MISSING and you get a phantom "type
     or namespace could not be found" for code that is fine. This appends every .cs that exists now
     under that assembly's own source roots. Without it the check lies toward false alarm.

  3. IT IS NOT UNITY'S COMPILE. Defines, analyzers and asmdef resolution are Unity's; this uses the
     response file Unity itself produced, which is close but not identical. A PASS here is strong
     evidence, not proof. A FAILURE here is proof.

Usage:  powershell -NoProfile -ExecutionPolicy Bypass -File Tools\compile_check.ps1
Exit 0 when every assembly compiles, 1 when any fails, 2 when the toolchain or the response files
cannot be found - deliberately distinguishable, because "nothing was checked" is not a pass.
#>
[CmdletBinding()]
param(
    [string]$ProjectPath = (Get-Location).Path,
    [string]$UnityRoot = "C:\Program Files\Unity\Hub\Editor\6000.1.8f1"
)

$ErrorActionPreference = "Stop"
Set-Location $ProjectPath

$csc = Join-Path $UnityRoot "Editor\Data\DotNetSdkRoslyn\csc.dll"
if (-not (Test-Path $csc)) {
    Write-Output "FAIL: Roslyn not found at $csc. Nothing was checked."
    exit 2
}

# The project's own assemblies, named by their .asmdef rather than guessed or globbed.
$assemblyNames = Get-ChildItem "Assets" -Recurse -Filter "*.asmdef" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "Plugins" } |
    ForEach-Object { (Get-Content $_.FullName -Raw | ConvertFrom-Json).name }

if (-not $assemblyNames) {
    Write-Output "FAIL: no .asmdef files under Assets. Nothing was checked."
    exit 2
}

$responseFiles = @()
foreach ($name in $assemblyNames) {
    $found = Get-ChildItem "Library\Bee\artifacts" -Recurse -Filter "$name.rsp" -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($found) {
        $responseFiles += $found
    }
    else {
        Write-Output "NOTE: no response file for $name - it was not built in the last import."
    }
}

if (-not $responseFiles) {
    Write-Output "FAIL: no response files matched any project assembly. Open the project in Unity once."
    exit 2
}

$failed = 0
foreach ($rsp in $responseFiles) {
    $assembly = [System.IO.Path]::GetFileNameWithoutExtension($rsp.Name)
    $lines = Get-Content $rsp.FullName | Where-Object { $_ -notmatch '^-?/?out:' }

    $known = @{}
    $roots = @{}
    foreach ($line in $lines) {
        if ($line -match '^"?(Assets[\\/].*\.cs)"?$') {
            $path = $matches[1].Replace('/', '\')
            $known[$path] = $true
            $roots[[System.IO.Path]::GetDirectoryName($path)] = $true
        }
    }

    # RECURSE FROM THE ASSEMBLY'S OWN ROOT, not from the directories the snapshot happened to know.
    # FOUND BY THE HUD WORKER, and it is a SILENT FALSE PASS - the worst kind. The first version
    # walked only $roots (directories that already contained a source in the last import), so an
    # entirely NEW FOLDER like Scripts/Hud/ was skipped without a word and the assembly reported
    # PASS while none of its new code was compiled. A check that quietly narrows its own subject is
    # worse than one that fails.
    $asmdefDir = $null
    foreach ($candidate in Get-ChildItem "Assets" -Recurse -Filter "$assembly.asmdef" -ErrorAction SilentlyContinue) {
        $asmdefDir = $candidate.DirectoryName
        break
    }
    $searchRoots = if ($asmdefDir) { @($asmdefDir) } else { @($roots.Keys) }

    $added = 0
    foreach ($dir in $searchRoots) {
        if (-not (Test-Path $dir)) { continue }
        Get-ChildItem $dir -Recurse -Filter *.cs -ErrorAction SilentlyContinue | ForEach-Object {
            $rel = $_.FullName.Substring($ProjectPath.Length + 1)
            # A NESTED .asmdef OWNS ITS OWN SUBTREE. Recursing from the asmdef folder would
            # otherwise sweep a child assembly's sources into the parent and produce errors that
            # are artifacts of this script rather than of the code.
            $ownedByChild = $false
            $probe = $_.Directory
            while ($probe -and $probe.FullName.Length -gt $asmdefDir.Length) {
                if (Get-ChildItem $probe.FullName -Filter *.asmdef -ErrorAction SilentlyContinue) {
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
    }

    $out = Join-Path $env:TEMP "nsc-compile-$assembly.dll"
    $tmp = Join-Path $env:TEMP "nsc-compile-$assembly.rsp"
    ($lines + "-out:$out") | Set-Content $tmp -Encoding utf8

    $output = & dotnet $csc "@$tmp" 2>&1
    $errors = $output | Select-String -Pattern "error CS"

    if ($errors) {
        $failed++
        Write-Output "FAIL $assembly"
        $errors | Select-Object -First 8 | ForEach-Object { Write-Output "   $_" }
    }
    else {
        Write-Output "PASS $assembly ($($known.Count) sources, $added appended since last import)"
    }
}

Write-Output "compile_check: $($responseFiles.Count) project assembly/assemblies, $failed failed."
if ($failed) { exit 1 } else { exit 0 }
