# Phase 1 Fair-Value Upgrade — Version 2.0

Implemented on 16 August 2026.

## 1. Multi-year financial normalization

- Collects up to five annual free-cash-flow, revenue, and net-income observations.
- Uses median normalized FCF and earnings to reduce one-year distortions.
- Combines historical CAGR and reported growth, with sector-specific caps.
- Reports missing or short financial histories as data-quality warnings.

## 2. Improved two-stage intrinsic-value model

- Ten-year explicit forecast instead of five years.
- Initial growth applies for five years and then fades toward terminal growth.
- Conservative, base, and optimistic cases retain independent growth and discount-rate assumptions.
- Financial institutions automatically use a residual-income model instead of ordinary DCF.

## 3. Real peer comparison

- Uses free Yahoo Finance industry/sector screening through yfinance.
- Selects same-industry peers first, then broadens to the same sector when necessary.
- Restricts results to the same country and a comparable market-cap range.
- Removes duplicate NSE/BSE listings and extreme multiple outliers.
- Uses peer median P/E for operating companies and peer median P/B for financial and real-estate profiles.
- Lists selected peer symbols in the detailed PDF.

## 4. Sector-specific model selection

Profiles include:

- Financial institution
- Real estate / REIT
- Cyclical / commodity
- Regulated / utility
- Technology operating company
- Standard operating company

Each profile uses appropriate primary-model labels, weights, growth limits, peer multiple, and risk treatment.

## 5. Dynamic valuation buffer

- User-entered margin is treated as the minimum.
- Required margin can rise to 50%.
- Adjustments consider financial risk, data completeness, model disagreement, and cyclical exposure.
- The dashboard, batch CSV, batch PDF, and detailed PDF show the resulting required margin.

## 6. Financial-risk and data-quality warnings

The engine now evaluates available indicators including:

- Debt/EBITDA
- Interest coverage
- Current ratio
- FCF stability
- Cash conversion
- Net debt/equity
- Historical-data completeness
- Peer-set size
- Model agreement

Financial institutions receive separate treatment and an explicit warning that regulatory capital and asset quality require review outside the free data feed.

## Important limitation

