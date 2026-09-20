$ErrorActionPreference = 'Stop'
$unity = 'C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe'
$out = 'C:\nscrev\reports\door-crack-probe\result.txt'
$log = 'C:\nscrev\reports\door-crack-probe\unity.log'
if (Test-Path $out) { Remove-Item $out -Force }
$a = @('-batchmode','-quit','-nographics','-projectPath','C:\nscrev\branch-verify',
       '-executeMethod','NscDiag.DoorCrackProbe.Run','-probeOut',$out,'-logFile',$log)
$p = Start-Process -FilePath $unity -ArgumentList $a -WindowStyle Hidden -PassThru -Wait
"exit=$($p.ExitCode)" | Out-File 'C:\nscrev\reports\door-crack-probe\exit.txt' -Encoding utf8
