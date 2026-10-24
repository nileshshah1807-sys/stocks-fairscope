# Indian Multi-Source Verification — Version 8.0

Implemented on 16 August 2026.

## Source roles

### Yahoo Finance
Primary source for US and Indian company fundamentals, annual statements, price history, company profile, governance fields, and peer screening.

### Screener.in
For NSE/BSE companies, the app makes one cached, best-effort request to the public consolidated company page and extracts selected top ratios:

- Current price
- Stock P/E
- Book value per share
- ROE
- Market capitalization
- 52-week high and low

Screener values verify or fill selected Yahoo fields. The app does not log in, bypass access controls, or download premium exports.

### NSE India
For NSE symbols, the app attempts a public quote-page session followed by the quote-equity endpoint. When accessible, the NSE last price takes priority over Yahoo's price. NSE may reject automated requests depending on location, cookies, rate limits, or anti-bot controls; failure is non-fatal and explicitly reported.

### BSE India
For BSE symbols, the app resolves a six-digit scrip code when needed and requests the public BSE quote header endpoint. When accessible, the BSE last price takes priority over Yahoo's price.

## Cross-source checks

- Records exactly which sources responded
- Records source URLs/timestamps where available
- Warns when Yahoo and NSE/BSE prices differ by more than 2%
- Warns when Yahoo and Screener prices differ by more than 2%
- Reduces data-quality score when a material discrepancy exists
- Reduces data-quality score when no Indian secondary source is available
- Includes sources checked in the detailed PDF and batch CSV

## Reliability and access safeguards

- Short request timeouts
- Normal browser identification
- One cached request per source and symbol per session
- No login automation
- No CAPTCHA bypass
- No premium Screener export access
- Yahoo fallback when a verification source is unavailable

## Important limitation

Screener.in and the NSE/BSE website endpoints are not guaranteed stable public developer APIs. Their structure, access rules, anti-bot controls, and terms may change. Users are responsible for compliant use and must verify official filings and exchange announcements before investing.
