# Certificate acquisition checklist

A trusted Windows installer requires an Authenticode certificate issued to the publisher.

1. Choose a reputable publicly trusted code-signing certificate authority or managed signing service.
2. Decide between standard organization-validation and EV code signing.
3. Complete publisher identity/organization validation using the exact intended publisher name.
4. Use the required hardware token, HSM, or cloud key storage. Do not export or share private keys unless the product explicitly supports secure PFX delivery.
5. Confirm compatibility with `signtool.exe`, SHA-256 file digest, and RFC 3161 timestamping.
6. Record the certificate subject, issuer, thumbprint, expiration, and renewal owner.
7. Store signing credentials in an access-controlled build environment or GitHub Actions secrets.
8. Test signing on a non-production build and run `verify_installer.ps1`.
9. Submit the signed installer to antivirus/malware scanning and test it on a clean Windows VM.
10. Renew before expiration. Timestamped signatures generally remain valid after certificate expiry, provided the certificate was valid and not revoked at signing time.

Never send the certificate password or private key in chat or commit it to source control.
