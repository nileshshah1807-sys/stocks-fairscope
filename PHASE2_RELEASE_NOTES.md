# Phase 2 Upgrade — Version 3.0

Implemented on 16 August 2026.

## Sensitivity analysis

Every completed valuation includes a 5×5 table of blended fair values. Rows vary the discount rate by approximately ±2 percentage points; columns vary terminal growth by approximately ±1 point. Invalid combinations are excluded. The table appears in the app and detailed PDF.

## Reverse DCF / residual income

The engine solves for the initial five-year growth rate that makes the primary intrinsic-value model equal the current market price. Growth then fades toward terminal growth. If the price implies growth above the 50% search ceiling, or the primary model is unavailable, the app reports that limitation instead of fabricating a value.

## Business-quality score

The 0–100 score considers available evidence for:

- Estimated ROIC relative to the required return
- ROE
- Operating margin
- Operating-cash-flow conversion
- Multi-year FCF consistency
- Revenue trend
- Share-count dilution or buybacks

Higher is better. Missing data reduces certainty and is explained in the notes.

## Governance-risk screen

The 0–100 risk score checks:

- Provider audit, board, shareholder-rights, and overall governance ratings when available
- Material share dilution
- Receivables growth relative to revenue
- Inventory growth relative to revenue
- Profit unsupported by operating cash flow
- Availability of insider/promoter ownership data

Lower is better. This is an accounting/governance screen, not a forensic audit. For Indian companies, promoter pledging, related-party transactions, auditor qualifications, and contingent liabilities are explicitly identified as manual NSE/BSE filing checks because the available free Yahoo Finance fields do not reliably provide them.

## Expanded confidence score

Confidence is now numeric and combines:

- Data quality: 30%
- Agreement between valuation models: 20%
- Balance-sheet resilience: 15%
- Business quality: 15%
- Governance coverage/risk: 10%
- Model completeness: 10%

The score is labeled Higher, Moderate, or Low and appears in the dashboard, safety tab, PDFs, and batch CSV.

## User-interface and reporting changes

- New **Safety & sensitivity** tab
- Five headline analytics: business quality, governance risk, confidence, reverse DCF, and model dispersion
- Detailed quality/governance explanations
- Phase-2 section and sensitivity matrix in detailed PDFs
- Phase-2 score columns in batch CSV and batch PDF

## Limitation

