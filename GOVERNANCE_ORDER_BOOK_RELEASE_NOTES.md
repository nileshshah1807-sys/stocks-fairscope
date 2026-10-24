# Version 10.3 — Governance, promoter holding and order-book valuation

## Fair-value integration

FairValueEngine 4.4 now incorporates three additional forward-looking and stewardship factors without treating them as guarantees:

1. **Governance risk in required return** — governance risk above the neutral threshold adds up to 2.0 percentage points to the automatic discount rate. This directly affects DCF/residual-income fair value. The existing financial-risk premium remains separate.
2. **Approximately three-year promoter-holding trend** — increasing, broadly stable, or decreasing promoter ownership contributes to the governance-risk score. Declines receive a larger adverse adjustment than increases receive a favourable adjustment. Dilution, mergers, family transfers and corporate actions must be verified before interpretation.
3. **Verified order-book coverage** — order book is compared with latest annual revenue and scored from 0–100. When a cited positive order book is available, the automatic initial growth rate can change by no more than **+1.5 or −1.0 percentage points**. Very high coverage is not assumed to convert fully into revenue.

Order-book values and promoter observations are included in lineage and the model audit. The Risk workspace and detailed PDF show the order-book score and promoter trend.

## Data workflow

- For Indian stocks, FairScope attempts to read public promoter shareholding history from Screener.in’s company page.
- Users can enter a verified order book, current promoter holding and promoter holding from approximately three years ago in **External review**, with a source URL and period.
- Order-book values should come from an official annual report, results presentation, exchange filing or company announcement.
- Moneycontrol remains manual-review only; FairScope does not automatically scrape or bypass it.

## Safeguards

- Missing order-book information is neutral and does not reduce fair value.
- Order book is not guaranteed revenue. Execution timing, cancellations, margins, customer concentration and working-capital needs remain material.
- Promoter holding is not automatically evidence of good or bad governance.
- The assumptions remain reviewable, and accepted manual changes create a child audit record.
- Valuation buffers do not guarantee protection from loss.
