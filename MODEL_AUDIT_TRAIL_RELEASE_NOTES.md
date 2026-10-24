# Model Audit Trail — Version 8.8

Implemented on 17 August 2026.

## Identity and versioning

Every valuation now records:

- Unique analysis ID
- Optional parent analysis ID
- UTC creation timestamp
- Application version
- Valuation-model version
- Audit-schema version
- Symbol, market, currency, and data snapshot

A reviewed-assumption recalculation creates a new analysis ID and links back to the previous valuation.

## Ordered audit events

Events document:

1. Analysis creation and versions
2. Data-source snapshot and discrepancy count
3. Sector/methodology selection
4. Historical normalization inputs
5. Automatic assumption baseline
6. Reviewed assumptions, preset, overrides, and note
7. Base model execution and exclusions
8. Scenario values
9. Financial/data/business/governance/confidence scores and dynamic valuation buffer
10. Sensitivity-grid parameters
11. Monte Carlo seed, iterations, percentiles, and probability
12. Final fair value, upside/downside, valuation-buffer price, and assessment

## Reproducibility

The audit record includes the deterministic Monte Carlo seed, peer symbols, model labels, model notes, automatic and reviewed assumptions, scenario outputs, and final result.

## Integrity verification

A canonical JSON representation is hashed with SHA-256. The app can recompute and verify the hash. Any later mutation of covered fields or events causes verification to fail.

The hash is tamper-evident, not a digital signature. It does not authenticate the publisher and does not guarantee data or model accuracy.

## Exports and reports

- Full audit JSON export
- Copyable analysis ID
- In-app verification control
- Detailed PDF audit metadata and ordered event table
- Batch PDF audit manifest
- Batch CSV analysis ID, parent ID, versions, audit hash, and Monte Carlo seed
- Standalone `verify_audit_json.py` command-line verifier

## Version source

Application, valuation-model, and audit-schema versions are managed centrally in `version.py` to prevent inconsistent metadata across the UI, reports, and installer packaging.
