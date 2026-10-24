# Strengthened Automated Testing — Version 9.7

Implemented on 19 August 2026.

## Test framework and coverage

- Pytest configuration and strict markers
- Branch coverage with pytest-cov
- 55% enforced minimum across core engines/providers
- Ruff fatal, undefined-name, unused-import, and import-order checks
- Python compile-all and pip dependency consistency
- Optional pip-audit security job

## CI matrix

GitHub Actions runs offline tests on Ubuntu, Windows, and macOS with Python 3.11, 3.12, and 3.13. Linux uses Qt/Xvfb dependencies. Coverage XML is uploaded per platform/version.

## New regression suites

- Detailed, batch, and performance PDF generation/readability
- CSV and Excel stock-list/transaction imports
- Zero/negative/NaN price and invalid-assumption rejection
- Very large numeric values
- Refusal to fabricate fair value without economic inputs
- Monte Carlo reproducibility
- Cache network-failure stale fallback
- 100-stock offline batch stress test
- Background pause/cancel/retry/backoff
- SQLite cache/history/job recovery
- Watchlist alert state/deduplication
- SEC/Screener/BSE corporate-event parsing
- Qt workspace construction and specialized workflows

## Live tests

KNSL, SIL.BO, and HDFCBANK network integration tests are included but disabled by default. Set `FAIRSCOPE_RUN_NETWORK_TESTS=1` to run them deliberately.

## Developer command

`python run_quality_checks.py` runs compilation, Ruff, offline tests with coverage, and pip consistency.
