param(
    [string]$Python = "py",
    [switch]$SkipInstall,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $Root

function Invoke-Native([string]$File, [string[]]$Arguments) {
    & $File @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$File failed with exit code $LASTEXITCODE" }
}

function Find-SignTool {
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path $kits) {
        $candidate = Get-ChildItem $kits -Filter signtool.exe -Recurse -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -match '\\x64\\signtool\.exe$' } |
            Sort-Object FullName -Descending | Select-Object -First 1
        if ($candidate) { return $candidate.FullName }
    }
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Sign-Artifact([string]$Path) {
    $signTool = Find-SignTool
    $thumbprint = $env:FAIRSCOPE_CERT_THUMBPRINT
    $pfx = $env:FAIRSCOPE_SIGNING_PFX
    $password = $env:FAIRSCOPE_SIGNING_PASSWORD
    if (-not $signTool) {
        if ($RequireSignature) { throw "signtool.exe was not found. Install the Windows SDK." }
        Write-Warning "signtool.exe not found; artifact remains UNSIGNED."
        return $false
    }
    if ($thumbprint) {
        Invoke-Native $signTool @("sign","/sha1",$thumbprint,"/fd","SHA256","/tr","http://timestamp.digicert.com","/td","SHA256","/v",$Path)
    } elseif ($pfx -and $password) {
        Invoke-Native $signTool @("sign","/f",$pfx,"/p",$password,"/fd","SHA256","/tr","http://timestamp.digicert.com","/td","SHA256","/v",$Path)
    } else {
        if ($RequireSignature) { throw "No signing identity configured. Set FAIRSCOPE_CERT_THUMBPRINT or FAIRSCOPE_SIGNING_PFX and FAIRSCOPE_SIGNING_PASSWORD." }
        Write-Warning "No certificate configured; artifact remains UNSIGNED."
        return $false
    }
    Invoke-Native $signTool @("verify","/pa","/all","/v",$Path)
    return $true
}

if (-not $SkipInstall) {
    # "-3" is a py-launcher flag; a plain interpreter path (CI passes setup-python's python) takes no version switch.
    $venvArgs = if ((Split-Path $Python -Leaf) -in @("py", "py.exe")) { @("-3","-m","venv",".build-venv") } else { @("-m","venv",".build-venv") }
    if (-not (Test-Path ".build-venv")) { Invoke-Native $Python $venvArgs }
    $Py = Join-Path $Root ".build-venv\Scripts\python.exe"
    Invoke-Native $Py @("-m","pip","install","--upgrade","pip")
    Invoke-Native $Py @("-m","pip","install","-r","requirements.txt","pyinstaller>=6.10,<7")
} else {
    $Py = Join-Path $Root ".build-venv\Scripts\python.exe"
}

if (-not (Test-Path $Py)) { throw "Build Python not found: $Py" }
# A running copy locks dist\ files; deleting around it destroys the previous build and fails halfway.
$running = Get-Process -Name "DrNileshShahStocksFairScope" -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith((Join-Path $Root "dist"), [StringComparison]::OrdinalIgnoreCase) }
if ($running) { throw "Close FairScope (running from dist\, PID $($running.Id -join ', ')) before building." }
# Resolve Inno Setup (machine-wide, per-user, or PATH) before deleting the previous build output.
$ISCC = @((Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"), (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $ISCC) {
    $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($cmd) { $ISCC = $cmd.Source } else { throw "Inno Setup 6 was not found." }
}
Remove-Item build,dist,installer_output -Recurse -Force -ErrorAction SilentlyContinue
Invoke-Native $Py @("-m","PyInstaller","--clean","--noconfirm","packaging\windows\FairScope.spec")

$AppExe = Join-Path $Root "dist\DrNileshShahStocksFairScope\DrNileshShahStocksFairScope.exe"
if (-not (Test-Path $AppExe)) { throw "Application executable was not created." }
$AppSigned = Sign-Artifact $AppExe

Invoke-Native $ISCC @("packaging\windows\FairScope.iss")

$Installer = Join-Path $Root "installer_output\Dr_Nilesh_Shah_Stocks_FairScope_Setup_x64_v10.4.1.exe"
if (-not (Test-Path $Installer)) { throw "Installer was not created." }
$InstallerSigned = Sign-Artifact $Installer
$hash = (Get-FileHash $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($Installer))" | Set-Content "$Installer.sha256" -Encoding ascii

$signature = Get-AuthenticodeSignature $Installer
$manifest = [ordered]@{
    product = "DR. NILESH SHAH - STOCKS FAIRSCOPE"
    version = "10.4.1"
    architecture = "x64"
    built_utc = [DateTime]::UtcNow.ToString("o")
    app_signed = $AppSigned
    installer_signed = $InstallerSigned
    authenticode_status = $signature.Status.ToString()
    signer = if ($signature.SignerCertificate) { $signature.SignerCertificate.Subject } else { $null }
    sha256 = $hash
}
$manifest | ConvertTo-Json | Set-Content (Join-Path $Root "installer_output\build-manifest.json") -Encoding utf8

Write-Host ""
Write-Host "Build complete: $Installer" -ForegroundColor Green
Write-Host "Authenticode: $($signature.Status)"
Write-Host "SHA-256: $hash"
if (-not $InstallerSigned) { Write-Warning "This build is NOT trusted/signed. Obtain a valid code-signing certificate and rerun with -RequireSignature." }
