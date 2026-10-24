# Stock Search and Autocomplete — Version 8.4

Implemented on 16 August 2026.

## Search behavior

- Choose US, NSE, or BSE before searching.
- Enter at least two characters of a company name or ticker.
- A 350 ms debounce avoids sending a request for every keystroke.
- Results appear in a keyboard-accessible Qt completion popup.
- Up/Down navigates results; Enter selects one.
- The selected symbol is inserted into the valuation field.
- Company, exchange, market, and source are shown before analysis.

## Sources

### US
Yahoo Finance search is filtered to equity results on recognized US exchanges. Global duplicate listings are excluded from the US result list.

### NSE and BSE
Screener.in public company search provides Indian company names and symbols. The selected market determines whether `.NS` or `.BO` is added during analysis.

## Reliability

- Search runs in a Qt background worker and does not freeze the window.
- Queries are cached during the session.
- Stale results are discarded when the user changes text or market.
- Selecting a result invalidates outstanding older searches.
- Temporary search failure displays a non-blocking status message.
- Exact ticker entry continues to work when search is unavailable.
- Uppercase ticker-like input receives a direct-entry fallback; ordinary company words do not become fake ticker suggestions.

## Tests

Added tests for Screener search parsing, direct ticker fallback, short-query behavior, false-ticker prevention, Qt model population, and selection behavior.
