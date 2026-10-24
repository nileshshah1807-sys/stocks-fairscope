# Corporate Filings and Corporate-Action Monitoring — Version 9.4

Implemented on 19 August 2026.

## US monitoring

- SEC EDGAR company-ticker/CIK resolution
- 10-K, 10-Q, 8-K, 20-F, 6-K, DEF 14A, Form 4, S-1, S-3, and 424B filings
- Direct SEC filing links and accession details
- Yahoo dividend, stock-split, and capital-gain actions

SEC requests require a locally stored contact email in the User-Agent, consistent with SEC access guidance.

## Indian monitoring

- Screener.in public document links and annual reports
- Best-effort NSE corporate announcements
- Best-effort NSE corporate actions
- Best-effort BSE announcement feed and filing attachments
- Yahoo dividend and split actions

## Persistent local monitor

Monitored companies and event history are stored in a local SQLite database. Events are de-duplicated by a stable source/symbol/type/date/title hash.

## Interface

- Add exact symbol or current analysis
- Refresh monitored companies
- View source, severity, event type, title, and read state
- Open the original filing/action link
- Mark events read
- Remove monitored company
- Save SEC contact email locally

## Severity

Material reports/actions such as 8-K, splits, bonuses, rights issues, buybacks, defaults, fraud, insolvency, or resignations receive elevated severity where detectable.

## Limitations

Website endpoints can be blocked, delayed, incomplete, or changed. NSE/BSE/Screener parsing is best effort. The monitor runs only when the desktop app is open and refreshed; it is not a 24/7 cloud service. Users must verify official filings and corporate-action notices.
