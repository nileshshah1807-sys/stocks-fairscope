# Background Processing — Version 9.6

Implemented on 19 August 2026.

## Bounded parallel analysis

Batch, watchlist, and transaction-portfolio valuation use a configurable bounded thread pool. Default concurrency is three workers, limited to 1–6 to reduce provider overload.

## Pause, resume, and cancel

A global job bar provides determinate progress, status, Pause/Resume, and Cancel controls. Active HTTP requests cannot be forcibly interrupted safely, so cancellation completes after active requests return and prevents remaining/retry work.

## Retry and backoff

Transient connection, timeout, 429/rate-limit, and 5xx failures retry up to three times with exponential backoff and jitter. Permanent symbol/data errors fail immediately without unnecessary retries.

## Partial persistence and crash recovery

Background job payload, progress, attempts, success/error summary, analysis IDs, and state are written to local SQLite. Jobs left running by a crash are marked interrupted on the next launch and can be recovered from the Local database workspace.

Recovery restarts the item list as a batch analysis. Completed valuation audits remain available in history.

## Cache-aware processing

Normal batch analysis can reuse fresh cache. Watchlist and transaction-performance refreshes request current data while retaining stale-cache fallback for source outages. Single-stock analysis includes a Refresh sources checkbox.

## Interface safeguards

Long jobs disable conflicting imports and analysis actions. The progress bar always resets after completion, cancellation, or failure. Retry attempts and partial completion are visible.
