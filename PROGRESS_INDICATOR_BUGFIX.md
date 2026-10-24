# Progress Indicator Bug Fix — Version 8.1

Implemented on 16 August 2026.

## Problem

The indeterminate blue progress line could continue moving after a single-stock or batch analysis had already completed.

## Fix

- Added explicit worker retention so Qt worker/signal objects remain alive until completion.
- Added a central worker launcher and active-worker registry.
- Connected every worker to a guaranteed cleanup handler.
- Wrapped batch-worker execution in `try/finally` so its completion signal is emitted on success, partial failure, or unexpected error.
- Progress animation now stops only when the final active worker finishes.
- Reset the progress bar from indeterminate range `(0, 0)` to normal range `(0, 100)` before hiding it.
- Restored Analyze and Batch buttons after cleanup.

## Regression test

A Qt offscreen test starts a background worker, processes queued Qt events, and verifies that:

- The active-worker registry becomes empty.
- The progress bar is hidden.
- The progress range is reset.

This test runs alongside the valuation, provider, batch, portfolio, and interface test suite.
