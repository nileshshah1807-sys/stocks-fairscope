param(
    [Parameter(Mandatory=$true)][string]$Installer
)
$ErrorActionPreference="Stop"
if (-not (Test-Path $Installer)) { throw "Installer not found: $Installer" }
$signature=Get-AuthenticodeSignature $Installer
$hash=Get-FileHash $Installer -Algorithm SHA256
Write-Host "File:       $($hash.Path)"
Write-Host "SHA-256:    $($hash.Hash.ToLowerInvariant())"
Write-Host "Status:     $($signature.Status)"
Write-Host "Status msg: $($signature.StatusMessage)"
if ($signature.SignerCertificate) {
    Write-Host "Subject:    $($signature.SignerCertificate.Subject)"
    Write-Host "Issuer:     $($signature.SignerCertificate.Issuer)"
    Write-Host "Thumbprint: $($signature.SignerCertificate.Thumbprint)"
    Write-Host "Valid from: $($signature.SignerCertificate.NotBefore)"
    Write-Host "Valid to:   $($signature.SignerCertificate.NotAfter)"
}
if ($signature.TimeStamperCertificate) {
    Write-Host "Timestamp:  $($signature.TimeStamperCertificate.Subject)"
}
if ($signature.Status -ne "Valid") { throw "Installer does not have a valid trusted Authenticode signature." }
Write-Host "Signature verification passed." -ForegroundColor Green
