$ErrorActionPreference = 'Stop'
$unity = 'C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe'
$out = 'C:\nscrev\reports\enemy-art-map\wiring.txt'
$log = 'C:\nscrev\reports\enemy-art-map\unity.log'
if (Test-Path $out) { Remove-Item $out -Force }
$a = @('-batchmode','-quit','-nographics','-projectPath','C:\nscrev\branch-verify',
       '-executeMethod','NscDiag.EnemyWiringProbe.Run','-probeOut',$out,'-logFile',$log)
$p = Start-Process -FilePath $unity -ArgumentList $a -WindowStyle Hidden -PassThru -Wait
"exit=$($p.ExitCode)" | Out-File 'C:\nscrev\reports\enemy-art-map\exit.txt' -Encoding utf8
