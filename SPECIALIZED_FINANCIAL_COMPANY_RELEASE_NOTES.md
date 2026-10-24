# Specialized Financial-Company Data — Version 8.9

Implemented on 17 August 2026.

## Financial-company classification

The app identifies banks, NBFCs/lenders, insurers, capital-market/asset-management firms, and diversified financial companies from sector and industry metadata.

## Specialized data workspace

A new **Financial company** workspace reviews:

- Reviewed ROE used by justified P/B
- Net interest margin
- Public financing margin
- Gross NPA
- Net NPA
- Capital adequacy
- CET1
- Provision coverage
- CASA ratio
- Credit cost
- Deposit growth
- Loan growth
- Cost-to-income
- Equity-to-assets proxy
- Insurer solvency ratio
- Embedded value per share
- Fair price-to-embedded-value multiple
- VNB margin
- Premium growth

Unavailable fields display “Not set” instead of zero. Users can enter reviewed values from official results and add a filing/page note.

## Automatic public data

For Indian financial companies, public Screener.in P&L and balance-sheet tables can provide financing margin, deposits, borrowings, total assets, and deposit growth. Yahoo data can provide ROE, ROA, equity, assets, revenue, expenses, and other available fundamentals. Derived proxies are explicitly labeled as proxies, not regulatory ratios.

## Specialized valuation

- Banks/NBFCs use residual income, justified P/B, and peer P/B/P/E fallback.
- Justified P/B uses ROE, required return, sustainable growth, and bounded multiples.
- Insurers can use embedded value per share × reviewed fair P/EV when those inputs are supplied.
- Ordinary-company debt/EBITDA logic remains excluded for financial institutions.

## Risk and quality

Financial risk now responds to available NPA, capital adequacy, CET1, provision coverage, credit cost, equity/assets, insurer solvency, and premium-growth data. Business quality can use margin, NPA, CASA, cost-to-income, deposit growth, insurer solvency, VNB margin, and premium growth.

## Audit, lineage, and reports

Audit schema 1.1 adds specialized financial metrics and manual-field provenance.

Manual specialized fields:

- Create user-input lineage entries
- Appear in the model audit JSON and hash
- Create a new child analysis ID
- Recalculate risk, quality, confidence, dynamic valuation buffer, scenarios, sensitivity, and Monte Carlo
- Appear in a specialized PDF section with public/manual status

## Broader listed-stock fallback support

The same release fixes BSE symbol ambiguity by requiring an exact BSE security-ID match. It also adds low-confidence revenue, book/net-cash, and peer P/B fallbacks for loss-making or negative-FCF operating companies. Fallbacks require at least a 35% valuation buffer and cannot exceed Low confidence.

## Important limitation

Free public sources do not reliably provide all regulatory metrics. Users must verify NPA, capital, CET1, provisioning, CASA, credit cost, solvency, embedded value, and VNB against official bank/insurer filings. Proxies are not regulatory substitutes.
