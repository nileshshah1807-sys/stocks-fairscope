# Assumptions Review — Version 8.6

Implemented on 16 August 2026.

## Review table

The Assumptions workspace now compares eight inputs side by side:

- Base growth
- Discount rate
- Terminal growth
- Forecast period
- Primary-model weight
- Graham/book weight
- Live-peer weight
- Minimum valuation buffer

Columns show automatic value, reviewed value, difference, and lock state.

## Presets

- Automatic defaults
- Conservative overlay
- DCF emphasis
- Peer balanced
- Custom review

Presets update only unlocked assumptions. Locked values remain unchanged until explicitly unlocked.

## Validation

The review screen prevents acceptance when:

- Discount rate does not exceed terminal growth
- Model weights do not total 100%
- No stock has been analyzed

A status banner distinguishes invalid, pending, accepted-with-overrides, and unchanged automatic reviews.

## Pending-change protection

Editing an assumption or reviewer note pauses PDF export until the reviewed inputs are accepted and the valuation is recalculated. This prevents a report from silently using stale assumptions.

## Audit trail

Accepted recalculations retain:

- Original automatic assumptions
- Reviewed assumptions
- Every changed field
- Automatic and reviewed values
- Difference in percentage points or years
- Preset name
- Reviewer note

The detailed PDF contains an Assumption Review & Override Disclosure section. Batch CSV output includes preset, override count, and reviewer note.

## Safety

The review screen does not describe an override as safer or more accurate. It records and explains user judgment while preserving the automatic baseline for comparison.
