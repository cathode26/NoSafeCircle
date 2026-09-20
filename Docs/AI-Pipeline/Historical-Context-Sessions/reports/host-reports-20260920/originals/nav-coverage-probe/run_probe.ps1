$ErrorActionPreference = 'Stop'
$unity = 'C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe'
$project = 'C:\nscrev\branch-verify'
$out = 'C:\nscrev\reports\nav-coverage-probe\coverage2.txt'
$log = 'C:\nscrev\reports\nav-coverage-probe\unity2.log'
if (Test-Path $out) { Remove-Item $out -Force }
$args = @(
  '-batchmode','-quit','-nographics',
  '-projectPath', $project,
  '-executeMethod','NscDiag.NavCoverageProbe2.Run',
  '-navProbeOut', $out,
  '-logFile', $log
)
$p = Start-Process -FilePath $unity -ArgumentList $args -WindowStyle Hidden -PassThru -Wait
"exit=$($p.ExitCode)" | Out-File -FilePath 'C:\nscrev\reports\nav-coverage-probe\exit.txt' -Encoding utf8
