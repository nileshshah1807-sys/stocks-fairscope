# Watchlists and Alerts — Version 9.3

Implemented on 18 August 2026.

## Persistent local watchlist

Watchlists are stored locally in SQLite under the user application-data directory. No account or cloud service is required.

## Alert conditions

- Price enters dynamic valuation-buffer zone
- Price reaches a custom target
- Modeled upside reaches a selected threshold
- Financial-risk score crosses a threshold
- Governance-risk score crosses a threshold
- Material cross-source discrepancy appears
- Fair value changes by a configured percentage
- Valuation confidence falls below 50

## State-aware alerts

An alert is created only when a condition changes from inactive to active. Repeated refreshes do not duplicate the same unresolved alert. If the condition clears, it can trigger again later.

## Controls

- Add an exact symbol
- Add the currently analyzed stock
- Refresh all watchlist valuations
- Remove selected stock
- Save per-stock alert thresholds
- Mark alerts read
- Export watchlist CSV

## Local privacy

Watchlist symbols, thresholds, last values, and alert history remain in a local SQLite database. The app does not upload them to a FairScope server.

## Limitations

Alerts run when the user presses Refresh all alerts; this version does not run a background cloud service when the desktop app is closed. Free data and website access can be delayed, blocked, or incomplete. Alerts are research notifications, not trading instructions.
