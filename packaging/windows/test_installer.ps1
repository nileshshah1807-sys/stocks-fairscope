param(
    [Parameter(Mandatory=$true)][string]$Installer,
    [switch]$RequireSignature
)
$ErrorActionPreference="Stop"
$Root=Join-Path $env:TEMP "FairScope-Installer-Test"
Remove-Item $Root -Recurse -Force -ErrorAction SilentlyContinue

if ($RequireSignature) { & "$PSScriptRoot\verify_installer.ps1" $Installer }

$install=Start-Process -FilePath $Installer -ArgumentList @("/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/DIR=$Root") -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Silent install failed with code $($install.ExitCode)." }
$exe=Join-Path $Root "DrNileshShahStocksFairScope.exe"
if (-not (Test-Path $exe)) { throw "Installed application executable was not found." }
$version=(Get-Item $exe).VersionInfo.ProductVersion
if (-not $version.StartsWith("10.4.1")) { throw "Unexpected installed version: $version" }

$process=Start-Process -FilePath $exe -PassThru
Start-Sleep -Seconds 8
if ($process.HasExited) { throw "Application exited unexpectedly with code $($process.ExitCode)." }
Stop-Process -Id $process.Id -Force

$uninstaller=Join-Path $Root "unins000.exe"
if (-not (Test-Path $uninstaller)) { throw "Uninstaller was not created." }
$uninstall=Start-Process -FilePath $uninstaller -ArgumentList @("/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART") -Wait -PassThru
if ($uninstall.ExitCode -ne 0) { throw "Silent uninstall failed with code $($uninstall.ExitCode)." }
Write-Host "Installer smoke test passed." -ForegroundColor Green
