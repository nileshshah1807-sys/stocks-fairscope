# Windows Signed Installer Pipeline — Version 8.3

Prepared on 16 August 2026.

## Requested target

- Operating system: Windows
- Architecture: x64
- Format: Setup EXE
- Certificate status: No certificate currently available

## Added

- PyInstaller one-folder specification optimized for PySide6
- Windows EXE version metadata and application icon
- Modern Inno Setup 6 installer definition
- Start Menu shortcut and optional desktop shortcut
- Standard Windows uninstaller
- Educational-use EULA
- PowerShell build automation
- Authenticode SHA-256 signing for both application and installer
- RFC 3161 DigiCert timestamping
- Signature verification script
- Silent install/launch/uninstall smoke-test script
- SHA-256 checksum output
- JSON build manifest recording signature status and signer
- GitHub Actions Windows build workflow
- Certificate acquisition and handling checklist

## Trust enforcement

Running the build with `-RequireSignature` fails when:

- No certificate identity is configured
- `signtool.exe` is unavailable
- Application signing fails
- Installer signing fails
- Authenticode verification is not valid

The GitHub workflow defaults to requiring a valid signature and does not upload a falsely labeled “signed” artifact after signing failure.

## Current deliverable status

No trusted signed EXE is included because no valid certificate/private key was supplied. The repository is ready to generate one as soon as a certificate thumbprint, secure PFX, hardware token, HSM, or cloud-signing identity is configured on a native Windows x64 build environment.

A self-signed certificate was intentionally not used because it would still display an unknown/untrusted publisher warning and must not be represented as a publicly trusted signature.
