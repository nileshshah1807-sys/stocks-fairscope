# Data Lineage and Citations — Version 8.7

Implemented on 16 August 2026.

## New Data lineage & citations workspace

Every important retrieved or transformed input can record:

- Metric name
- Value used by the app
- Source name
- Clickable source URL
- Financial period or market date
- Retrieval timestamp
- Transformation or normalization rule
- Status: Received, Selected, Verified, Normalized, Derived, or Unavailable

Double-clicking a row or pressing **Open selected citation** opens the source in the default browser.

## Lineage coverage

The Yahoo/Screener/NSE/BSE provider records lineage for available items including:

- Selected market price
- One-year price history
- Shares outstanding
- Revenue history
- Normalized net income
- Normalized free cash flow
- Normalized EPS
- Book value per share
- Trailing P/E
- Market capitalization
- ROE
- Total debt
- Cash and equivalents
- Peer median multiple
- Screener.in ratio cross-check
- NSE/BSE official-site price check

## Transformation explanations

Examples:

- “Median of available annual net-income observations”
- “Median annual net income divided by current shares; reported EPS fallback”
- “Screener crore value converted to currency units when available”
- “Median of screened same-region industry/sector peers after outlier bounds”
- “Official-site price selected when available; otherwise latest Yahoo close”

## Citation export

The workspace exports a UTF-8 CSV containing the complete lineage trail. Formula-like user-controlled text is escaped before spreadsheet use.

## PDF appendix

Detailed stock reports include a **Data Lineage & Citations** table with clickable source links. The appendix records period, transformation, and status and warns that website data may change after retrieval.

## Data quality integration

Existing source-discrepancy warnings remain connected to the data-quality score. Unavailable peer or official-exchange checks are identified rather than silently represented as successful.
