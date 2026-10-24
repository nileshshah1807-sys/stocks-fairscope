# Credentials and Portfolio Privacy — Version 9.9

Implemented on 20 August 2026.

## Secure secret storage

SEC contact email is encrypted with Fernet. The master key is stored in the operating-system credential manager when available; otherwise a restricted-permission local key file is used. Legacy plaintext SEC email is migrated and removed from SQLite.

## File permissions

Application data directories use owner-only permissions where supported. SQLite databases, WAL/SHM files, encryption key, secure settings, and diagnostic logs use restrictive local permissions.

## Portfolio privacy mode


Portfolio transactions remain memory-only unless the user explicitly exports a file.

## Diagnostic privacy

Support ZIPs exclude databases, watchlists, transactions, valuations, SEC email, and credentials. Symbols present in logs are replaced with `[REDACTED_SYMBOL]` using the active watchlist/transaction/monitor symbol set.

## Dependency security

Cryptography is constrained to version 50.x after dependency auditing identified advisories in an older installed build. Final `pip-audit` result: no known vulnerabilities.

## Watchlist popup fix

The native dark QMessageBox alert was replaced with a custom white/light dialog. High, warning, and informational alerts use light red, amber, and blue cards with dark readable text and high-contrast headings.
