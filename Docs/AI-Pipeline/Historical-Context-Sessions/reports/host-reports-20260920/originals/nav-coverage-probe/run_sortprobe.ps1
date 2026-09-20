$ErrorActionPreference = 'Stop'
$unity = 'C:\Program Files\Unity\Hub\Editor\6000.1.8f1\Editor\Unity.exe'
$out = 'C:\nscrev\reports\nav-coverage-probe\sorting-probe.txt'
$log = 'C:\nscrev\reports\nav-coverage-probe\sorting-probe.log'
if (Test-Path $out) { Remove-Item $out -Force }
$a = @('-batchmode','-quit','-nographics','-projectPath','C:\nscrev\branch-verify',
       '-executeMethod','NscDiag.SortingLayerProbe.Run','-probeOut',$out,'-logFile',$log)
$p = Start-Process -FilePath $unity -ArgumentList $a -WindowStyle Hidden -PassThru -Wait
"exit=$($p.ExitCode)" | Out-File 'C:\nscrev\reports\nav-coverage-probe\sorting-probe-exit.txt' -Encoding utf8
