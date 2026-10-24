# External Data Review — Version 9.0

Implemented on 17 August 2026.

## Safe Moneycontrol support

Moneycontrol is supported through a user-cited manual review workflow rather than automated scraping, login automation, paywall access, or access-control bypass.

The app opens a browser search for the selected symbol. The user can enter only the values they verified and paste the exact page URL and period.

## Reviewed fields

- Market price comparison
- Trailing P/E
- Book value per share
- ROE
- Market capitalization
- Latest revenue
- Latest net profit
- Latest free cash flow

Official NSE/BSE price remains preferred. A manually reviewed price is used for discrepancy analysis only and does not silently replace the selected exchange price.

## Recalculation and controls

Applied external values can update book/peer models, financial-company ROE, revenue fallback, reviewed EPS, and reviewed FCF. Pending entries pause PDF export until citation, period, and recalculation are complete.

## Provenance

Every accepted field creates a Manual lineage record with source, URL, period, retrieval timestamp, and transformation note. The complete review is included in audit JSON, SHA-256 integrity verification, child analysis ID, detailed PDF, and batch export metadata.

## Audit schema

Audit schema 1.2 includes external manual review records.

## Compliance posture

The workflow does not claim Moneycontrol as an automated API. Users remain responsible for lawful access, source terms, and verification against official company and exchange filings.
