# Local Database and Caching Layer — Version 9.5

Implemented on 19 August 2026.

## Local SQLite database

The app stores stock snapshots, cache metadata, settings, and up to 1,000 valuation audit records in a WAL-backed SQLite database under the user application-data directory.

## Stock cache

- Default six-hour lifetime
- User-configurable 0.5–168 hour TTL
- Fresh-cache reuse for faster repeat analysis and lower source load
- Optional stale-cache fallback when network sources fail
- Payload size, source date, provider, age, and freshness display
- Clear expired or all stock-cache controls

## Offline resilience

When a network request fails and stale fallback is enabled, the latest cached snapshot can be used with an explicit warning. Stale age is recorded in lineage/audit/report metadata and reduces data-quality confidence progressively.

## Valuation history

Every rendered, batch, or watchlist valuation stores its audit JSON and summary by unique analysis ID. The Local database workspace lists the latest 1,000 analyses and can export a selected historical audit JSON.

## Privacy

The cache and history are local. Clearing stock cache does not delete watchlists or valuation history; clearing history does not delete cached stock data.

## Technical design

- Thread-safe SQLite connection
- WAL journaling
- JSON serialization of StockData, lineage, and specialized financial metrics
- Schema version 1.0
- Central settings for TTL and stale fallback

Audit schema 1.3 records cache delivery status, age, and staleness. FairValueEngine 4.3 applies a stale-data quality penalty.
