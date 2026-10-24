# Application Review and Bug Fixes — Version 8.2

Reviewed on 16 August 2026.

## Review performed

- Full Python byte-code compilation
- 21 automated unit/interface tests
- Qt offscreen construction of all eight workspaces
- Real Yahoo, Screener.in, and BSE India data retrieval
- NSE failure/fallback behavior
- Single-stock and batch PDF generation
- 100-stock PDF stress test
- Dependency consistency check
- Ruff undefined-name, unused-import, and import-structure checks
- ZIP integrity test

## Additional issues fixed

### Stale batch exports
After importing a new list, CSV/PDF buttons could remain enabled for the previous batch. They are now disabled immediately and remain disabled until the new batch finishes.

### Stale portfolio display
A newly imported list could temporarily show portfolio metrics from the previous list. Portfolio cards, table, notes, records, and risk state are now cleared on import.

### Batch mutation during scanning
The Import button remained active while a worker was running. It is now disabled during active analysis, preventing the displayed list from changing while progress signals refer to the original list.

### PDF button state
The single-stock PDF button now follows worker state consistently and is only enabled when analysis is idle and a valid result exists.

### CSV formula injection
User-controlled imported text beginning with `=`, `+`, `-`, or `@` could be interpreted as a spreadsheet formula after CSV export. Non-numeric formula-like text is now escaped. Legitimate signed numeric and percentage values remain unchanged.

### Source cleanup
Unused imports and import-order issues identified by static analysis were removed. The source passes Ruff fatal/undefined/unused-import checks.

## Confirmed limitations—not code defects

- NSE India can block requests based on location, cookies, or anti-bot policy; Yahoo/Screener fallback and a warning are used.
- Free website structures may change.
- A 100-stock batch can take time because each valuation includes network verification and 2,000 Monte Carlo iterations.
- Portfolio cross-currency VaR excludes FX unless users provide deliberate target weights; the app warns about this.
- No valuation result guarantees investment safety or future returns.
