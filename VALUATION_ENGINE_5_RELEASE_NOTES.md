# Valuation Engine 5.0

Implemented on 26 September 2026. Model version `FairValueEngine 5.0`, audit schema `1.5`.

Fair values from this engine differ from engine 4.4 results for the same stock. Audit records keep the model version, so older history entries remain identifiable.

## Normalization

- Normalized free cash flow and earnings = latest annual revenue × median multi-year margin (previously the median of absolute values, which lagged growing companies by roughly 13–32%).
- Stock-based compensation is deducted from free cash flow.
- Indian stocks blend 10-year Screener.in operating and net margins, rescaled to the Yahoo definition using overlapping fiscal years; cyclicals use the 10-year mid-cycle margin.

## Cost of capital

- CAPM cost of equity: risk-free rate + beta × equity risk premium + company-specific premium (financial and governance risk, up to 2 points each).
- Live US 10-year Treasury yield (^TNX) with a settings fallback; editable India 10-year yield.
- Beta: 5-year monthly regression against the S&P 500 or NIFTY 50, Yahoo beta as fallback, Blume-adjusted and bounded to 0.6–2.0.
- WACC at market-value weights; cost of debt from interest expense ÷ debt, bounded to risk-free + 0.5 to 8 points.
- New **Valuation parameters** card on the Data source page: risk-free rates, equity risk premiums, scenario weights, holding-company discount.

## Models

- FCFF DCF at WACC with an equity bridge (debt, minority interest, cash, non-operating and listed investments).
- High-growth stage of 3, 5, 7, or 10 years from the ROIC-minus-cost-of-capital spread and its consistency (10-year ROCE for Indian stocks); forecast period extends to at least five fade years.
- Terminal value = NOPAT × (1 − g ÷ return on new capital) ÷ (WACC − g); terminal values above 75% of the total are flagged, cut confidence by 5 points, and add 2 points to the valuation buffer.
- Earnings power value replaces Graham's formula as the secondary model.
- Relative value: growth-adjusted peer P/E, peer forward P/E, peer EV/EBITDA (ROE-adjusted P/B for financials), blended 60/40 with the stock's own median P/E, EV/EBITDA, or P/B at past fiscal year-ends.
- Initial growth blends historical trend (40%), analyst consensus (30%), and reinvestment rate × ROIC (30%).
- Fair value is probability-weighted across conservative, base, and optimistic scenarios (25/50/25 by default).
- Loss-making companies: revenue DCF with margins converging to a sector target (replaces the revenue-multiple fallback).
- Holding companies: listed investments credited after a holding discount (default 20%).
- Banks: Gross/Net NPA read from Screener.in quarterly results when available.

## Quality and forensic screens

Piotroski F-score, Altman Z (manufacturing) or Z'' (non-manufacturing), Beneish M-score, ROIC history, 10-year ROCE, operating-margin stability, cash conversion cycle, owner earnings, net share repurchase yield, dividend payout, effective tax rate, promoter pledge (NSE best effort or manual entry), and FII/DII holding trend. They feed the financial-risk, governance-risk, and business-quality scores and appear in a new row on the Risk & sensitivity page and in the PDF.

## Backtest

New **Backtest** workspace: rebuilds each stock about 90 days after each of the last one to four fiscal year-ends, values it with only that data, and reports rank correlation, directional hit rate, and annualized returns of model-undervalued versus model-overvalued stocks. Peer multiples, beta, and the risk-free rate use current values, so results carry look-ahead bias and cover only the four to five years of free annual statements.

## Reports and exports

- PDF: probability-weighted fair value, Cost of capital & value drivers, Relative valuation components, and Quality & forensic screens sections; high-growth years and scenario weights in the assumptions table.
- Batch CSV: base fair value, scenario weights, discount rate, cost of equity, beta, primary basis, secondary value, terminal value share, high-growth years, Piotroski F, Altman Z, Beneish M, median ROIC.
- Assumptions review: new High-growth years row. External review: promoter pledge and listed-investment fields.

## Fixes found during implementation

- The resilience-bar chart in the PDF drew its sixth bar below the chart and overlapped the following text.
- Reverse DCF reported "unavailable" when equity value reached zero at low growth for indebted companies; zero is now treated as a value.
- The test suite wrote sample valuations into the user's real data folder; `tests/conftest.py` now isolates it.
