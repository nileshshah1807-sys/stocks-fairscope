# Version 10.2 — Readable Windows notification dialogs

## Problem fixed

On some Windows systems using dark mode or a custom colour theme, native Qt message boxes could combine a dark body with dark message text. Export confirmations such as **Watchlist report saved** were therefore difficult or impossible to read.

## Improvement

FairScope now uses its own high-contrast notification dialog instead of native one-way message boxes.

- Explicit white content background and dark navy message text
- Clear blue, green, amber, or red status headers
- Large status icon and heading
- Word wrapping for long messages and file paths
- Selectable message text for copying paths and technical details
- **Open folder** action when the message is an existing local file path
- Keyboard-default **OK** action
- Consistent rendering independent of Windows light/dark theme

The fix applies to report/export confirmations, information notices, warnings, and error messages throughout the Qt application. Destructive yes/no confirmation prompts retain their existing explicit confirmation flow.

## Validation

An automated Qt regression test checks the explicit white/dark colour pair, success palette, selectable message text, and complete file-path visibility. The existing watchlist-alert colour test remains in place.
