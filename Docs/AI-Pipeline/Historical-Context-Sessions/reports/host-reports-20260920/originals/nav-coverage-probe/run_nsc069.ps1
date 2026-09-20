$ErrorActionPreference = 'Stop'
$unity = 'C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe'
$results = 'C:\nscrev\reports\nav-coverage-probe\nsc069-results.xml'
$log = 'C:\nscrev\reports\nav-coverage-probe\nsc069.log'
if (Test-Path $results) { Remove-Item $results -Force }
$a = @('-batchmode','-nographics','-projectPath','C:\nscrev\branch-verify',
       '-runTests','-testPlatform','EditMode',
       '-testFilter','NoSafeCircle.DoorPrototype.Tests.Editor.World.RoomSceneCompositionFoundationTests',
       '-testResults',$results,'-logFile',$log)
$p = Start-Process -FilePath $unity -ArgumentList $a -WindowStyle Hidden -PassThru -Wait
"exit=$($p.ExitCode)" | Out-File 'C:\nscrev\reports\nav-coverage-probe\nsc069-exit.txt' -Encoding utf8
