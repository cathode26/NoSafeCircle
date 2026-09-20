$ErrorActionPreference = 'Stop'
$unity = 'C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe'
$project = 'C:\nscrev\branch-verify'
$results = 'C:\nscrev\reports\nav-coverage-probe\playmode-results.xml'
$log = 'C:\nscrev\reports\nav-coverage-probe\playmode.log'
if (Test-Path $results) { Remove-Item $results -Force }
$a = @(
  '-batchmode','-nographics',
  '-projectPath', $project,
  '-runTests','-testPlatform','PlayMode',
  '-testFilter','EnemyPursuitPlayModeTests',
  '-testResults', $results,
  '-logFile', $log
)
$p = Start-Process -FilePath $unity -ArgumentList $a -WindowStyle Hidden -PassThru -Wait
"exit=$($p.ExitCode)" | Out-File 'C:\nscrev\reports\nav-coverage-probe\playmode-exit.txt' -Encoding utf8
