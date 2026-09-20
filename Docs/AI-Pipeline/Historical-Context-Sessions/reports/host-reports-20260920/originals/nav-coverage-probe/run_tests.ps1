$ErrorActionPreference = 'Stop'
$unity = 'C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe'
$project = 'C:\nscrev\branch-verify'
$results = 'C:\nscrev\reports\nav-coverage-probe\editmode-results.xml'
$log = 'C:\nscrev\reports\nav-coverage-probe\editmode.log'
if (Test-Path $results) { Remove-Item $results -Force }
$a = @(
  '-batchmode','-nographics',
  '-projectPath', $project,
  '-runTests','-testPlatform','EditMode',
  '-testFilter','EnemySpawnPlacementTests;DoorPrototypeSceneBuilderTests;NavMeshAgentConfigurationTests',
  '-testResults', $results,
  '-logFile', $log
)
$p = Start-Process -FilePath $unity -ArgumentList $a -WindowStyle Hidden -PassThru -Wait
"exit=$($p.ExitCode)" | Out-File 'C:\nscrev\reports\nav-coverage-probe\tests-exit.txt' -Encoding utf8
