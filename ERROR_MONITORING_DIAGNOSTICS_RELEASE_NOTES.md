# Error Monitoring and Diagnostics — Version 9.8

Implemented on 20 August 2026.

## Structured local logs

Errors and operational events are stored as sanitized JSON Lines with UTC timestamp, level, component, message, details, thread, and app version. Logs rotate at 5 MB with four backups.

Emails, tokens, API keys, and password-like query values are redacted. Watchlist, transaction, valuation, and database contents are not placed in the support ZIP.

## Diagnostics workspace

- Recorded error count and recent event table
- Last error
- Yahoo/Screener/NSE/BSE connectivity and latency checks
- SQLite quick integrity checks
- REINDEX/VACUUM maintenance
- Copy last error
- Clear logs
- Open log folder
- Export sanitized diagnostic ZIP

## Diagnostic ZIP

Includes system/app/model/audit versions, Python/OS details, sanitized recent events, provider health, database health, and database/cache statistics. It excludes databases, watchlists, portfolios, transactions, SEC email, and credentials.

## Global exception capture

Unexpected Qt/Python exceptions are recorded locally and show a user-friendly instruction to export diagnostics.

## Colour watchlist PDF

A complete branded landscape PDF includes summary cards, valuation snapshot, alert settings, last status, and complete alert history. High, warning, and informational alert rows use red, amber, and green backgrounds.
