# Free Data Source Change — Version 7.0

Implemented on 16 August 2026 at the user's request.

## EODHD removed

- Removed EODHD API integration
- Removed API-token and credential-manager features
- Removed `keyring` dependency
- Removed EODHD settings, subscription messaging, and validation files
- No paid data subscription is required

## Yahoo Finance enabled

The app now uses Yahoo Finance through `yfinance` for:

- Latest available prices
- One-year adjusted and unadjusted price history
- Company profiles
- Annual income statements
- Annual balance sheets
- Annual cash-flow statements
- Shares outstanding
- Valuation and governance fields when available
- Same-region industry/sector peer screening

## Symbol handling

- US: `AAPL`, `MSFT`, `BRK-B`
- NSE: `RELIANCE` or `RELIANCE.NS`
- BSE: `500325` or `500325.BO`

The selected market automatically adds `.NS` or `.BO` when needed.

## Qt interface changes

The Data Settings workspace is now a read-only **Free Data Source** page. It explains coverage, confirms that no API key is required, and prominently warns users to verify official filings.

## Important limitation

Yahoo Finance access through yfinance is free and convenient but unofficial. Data may be delayed, incomplete, restated, rate-limited, blocked, or changed without notice. It is not a substitute for SEC filings, NSE India, BSE India, exchange announcements, or company annual reports. Scraping of Screener.in, NSE India, or BSE India was not added; those sites can change access controls and terms, and official documents should be reviewed directly.
