# Windows x64 installer and Authenticode signing

## Important status

The repository is **signing-ready but not signed** because no code-signing certificate was supplied. A trusted signed installer cannot be created honestly without control of a valid private key and certificate.

Do not distribute an installer as “signed” unless `verify_installer.ps1` reports `Status: Valid`.

## Required software on Windows

- Windows 10/11 x64 build machine or `windows-latest` GitHub Actions runner
- Python 3.11–3.13 x64
- Inno Setup 6
- Windows 10/11 SDK (`signtool.exe`)
- Valid Authenticode code-signing certificate

For fewer Microsoft SmartScreen reputation warnings, an EV code-signing certificate is generally preferable, although reputation is not guaranteed.

## Certificate options

### Certificate installed in the Windows certificate store

```powershell
$env:FAIRSCOPE_CERT_THUMBPRINT="YOUR_CERTIFICATE_THUMBPRINT"
.\packaging\windows\build_windows.ps1 -RequireSignature
```

### PFX certificate

```powershell
$env:FAIRSCOPE_SIGNING_PFX="C:\secure\certificate.pfx"
$env:FAIRSCOPE_SIGNING_PASSWORD="use-a-secret-environment-value"
.\packaging\windows\build_windows.ps1 -RequireSignature
```

Never commit a PFX file, password, base64 certificate, hardware-token PIN, or private key.

## Build output

```text
installer_output/
  Dr_Nilesh_Shah_Stocks_FairScope_Setup_x64_v10.4.0.exe
  Dr_Nilesh_Shah_Stocks_FairScope_Setup_x64_v10.4.0.exe.sha256
  build-manifest.json
```

The build signs twice:

1. The packaged application executable
2. The final Inno Setup installer

Both use SHA-256 and RFC 3161 timestamping through DigiCert. The installer is then verified with the Windows Authenticode policy.

## Verify before distribution

```powershell
.\packaging\windows\verify_installer.ps1 `
  .\installer_output\Dr_Nilesh_Shah_Stocks_FairScope_Setup_x64_v10.4.0.exe
```

Expected result:

```text
Status: Valid
Signature verification passed.
```

Also compare the SHA-256 value with the `.sha256` file.

## GitHub Actions secrets

The included workflow expects:

- `WINDOWS_CERTIFICATE_BASE64` — base64-encoded PFX bytes
- `WINDOWS_CERTIFICATE_PASSWORD` — PFX password

Run **Windows signed installer** manually with `require_signature=true`. The workflow fails rather than publishing an unsigned artifact when trusted signing cannot be completed.

If your certificate uses an HSM/cloud signing service instead of a PFX, adapt `Sign-Artifact` to the vendor's supported signing client. Modern publicly trusted code-signing certificates may require hardware-backed private keys.

## Unsigned test build

For internal testing only:

```powershell
.\packaging\windows\build_windows.ps1
```

This may produce an installer, but the manifest will state that signing is false and Windows will show an unknown-publisher warning. It must not be described as a signed installer.
