# PySide6 / Qt Interface Upgrade — Version 6.0

Implemented on 16 August 2026.

## Tkinter removed from the application path

The desktop interface has been rebuilt with PySide6 and Qt 6. `app.py` is now a small Qt launcher and contains no Tkinter dependency. Core valuation, free-data, reporting, batch, Monte Carlo, and portfolio modules remain reusable and independent of the UI.

## Professional application shell

- Branded navy sidebar with logo
- Eight clearly separated workspaces
- Responsive content area
- High-DPI Qt icon handling
- Consistent cards, buttons, inputs, tables, and status messages
- Minimum-window safeguards and resizable split views
- Modern Qt stylesheet with accessible contrast

## Workspaces

1. Dashboard
2. Batch analysis
3. Safety & sensitivity
4. Monte Carlo
6. Assumptions
7. Data settings
8. Methodology

## Responsive background processing

Network and long-running work uses `QThreadPool` and `QRunnable` workers:

- Single-stock Yahoo Finance retrieval
- Batch analysis

The interface remains responsive and reports progress through the status bar and progress indicator.

## Data visualization

A native Qt-painted Monte Carlo histogram displays:

- Simulated valuation distribution
- Native-currency endpoints
- Current market-price marker
- Automatic redraw when the window is resized

Sensitivity, scenario, batch, and portfolio information use sortable-looking, stretchable Qt tables designed for large screens and high-DPI displays.

## Secure data settings

The Qt settings page includes masked token entry, secure credential storage selection, asynchronous connection testing, token clearing, provider-plan guidance, and strict no-fallback disclosure.

## Packaging

PySide6 is now included in `requirements.txt`. Windows, macOS, and Linux launch scripts continue to create an isolated environment before starting the Qt application. PyInstaller instructions remain available for native executable packaging.

## Validation

- All Python modules compile
- Offline valuation, provider, batch, Monte Carlo, and portfolio tests continue to pass
- Qt offscreen smoke test verifies window construction and all eight workspaces when PySide6 is installed

## Limitation

A modern interface does not make valuation results more certain. Model, provider, governance, market, and portfolio limitations remain fully applicable.
