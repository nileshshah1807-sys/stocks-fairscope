# DR. NILESH SHAH - STOCKS FAIRSCOPE

DR. NILESH SHAH - STOCKS FAIRSCOPE is a cross-platform Python desktop app for estimating the fair value of US, NSE, and BSE stocks. It uses the strategy you selected:

- **Normalized fundamentals:** latest revenue × median multi-year margin, stock-based compensation deducted, 10-year Screener.in margins for Indian stocks
- **Market-based cost of capital:** live US 10-year yield, 5-year regression beta, equity risk premium, and WACC
- **Sector-aware valuation:** FCFF DCF with an equity bridge or residual income, earnings power value, and growth-adjusted peer multiples blended with the stock's own valuation history
- **Three probability-weighted scenarios:** conservative, base, optimistic (25/50/25 by default)
- **Quality and forensic screens:** Piotroski F, Altman Z, Beneish M, ROIC/ROCE history, cash conversion cycle, owner earnings, capital allocation, promoter pledge, FII/DII trend
- **Point-in-time backtest:** re-runs the model at past fiscal year-ends and compares with the returns that followed
- **Free multi-source data:** Yahoo Finance primary, with Screener.in and NSE/BSE website verification for Indian stocks
- **Stock search and autocomplete:** company-name and ticker search with keyboard selection
- **Visual analysis:** price, model, fundamentals, scenarios, sensitivity and Monte Carlo valuation charts
- **Assumptions review:** automatic-versus-reviewed comparison, presets, locks, validation, notes, and PDF disclosure
- **Data lineage and citations:** metric-level source URLs, periods, transformations, status, CSV export, and PDF appendix
- **Model audit trail:** unique analysis IDs, versions, parent chain, Monte Carlo seed, ordered events, JSON export, and SHA-256 verification
- **Specialized financial companies:** bank/NBFC/insurer data, valuation, risk rules, manual review, lineage, audit, and PDF disclosure
- **External data review:** apply cited Moneycontrol or official-filing values without automated scraping
- **Watchlists and alerts:** local persistent tracking for valuation buffer, price, upside, risk, governance, discrepancies, confidence, and fair-value changes
- **Corporate monitoring:** SEC/NSE/BSE/Screener filings, announcements, dividends, splits, source links, and read history
- **Local database and cache:** configurable stock cache, stale fallback, local settings, and valuation audit history
- **Background processing:** bounded parallelism, retry/backoff, pause/resume/cancel, partial persistence, and crash recovery
- **Automated quality:** cross-platform CI, coverage, static analysis, PDF/import/extreme/cache/100-stock/network regression suites
- **Error monitoring and diagnostics:** sanitized rotating logs, provider/database health, maintenance, and support ZIP
- **Colour watchlist report:** complete valuation, thresholds, status, and alert history in branded PDF
- **Professional PDF design:** branded cover, executive summary, contents, bookmarks, score bars, charts, audit, and lineage appendices
- **Uncertainty-first language:** valuation-buffer terminology, no Buy/Sell labels, and explicit no-guarantee warnings
- **Readable notification dialogs:** explicit light backgrounds, dark selectable text, status colours, and an Open folder action that remain legible under Windows dark mode
- **Governance, promoter and order-book valuation:** governance risk contributes to the required return, approximately three-year promoter-holding trends contribute to governance risk, and verified order-book coverage cautiously adjusts forecast growth
- **Native currency:** USD for US listings; INR for Indian listings
- **Dynamic valuation buffer:** risk- and data-quality-adjusted, up to 50%
- **Full PDF export** from the app
- **Batch import:** analyze up to 100 stocks from CSV, TXT, TSV, or Excel
- **Batch exports:** summary CSV and branded PDF

> Educational research tool only. Not investment advice.

## Quick start

### Windows

1. Install Python 3.11 or newer from <https://python.org> and select “Add Python to PATH.”
2. Extract the ZIP.
3. Double-click **`install_and_run.bat`**.

### macOS / Linux

```bash
cd StockFairValueApp
chmod +x install_and_run.sh
./install_and_run.sh
```

The interface uses **PySide6/Qt 6**. On Linux, the system may also require standard Qt/XCB libraries supplied by the distribution.

## Modern Qt interface

Version 6.0 replaces Tkinter with PySide6/Qt 6. The app now uses a professional sidebar workspace, responsive metric cards, polished tables, high-DPI icons, light-theme styling, non-blocking QRunnable workers, a painted Monte Carlo histogram, and dedicated Dashboard, Batch, Risk, Monte Carlo, Assumptions, Data Settings, and Methodology pages.

## Free data source

The app uses Yahoo Finance through `yfinance` as the primary source. For Indian stocks it also performs best-effort cross-checks using Screener.in and the public website endpoints used by NSE India or BSE India. No API key or account is required.

Data roles:

- **Yahoo Finance:** price history, financial statements, company profile, governance fields, and peers.
- **Screener.in:** current price, P/E, book value, ROE, market cap, and 52-week range when the public company page is accessible.
- **NSE India:** official-site last-price verification for NSE symbols.
- **BSE India:** official-site last-price verification for BSE scrip codes.

The official exchange-site price takes priority when available. Screener values fill or verify selected ratios. Differences above 2% are reported as data-quality warnings. Website endpoints can block automated requests or change without notice, so the app falls back to Yahoo and clearly reports which checks succeeded.

## Manual start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

## Symbol entry

| Market selector | Example entries | App lookup |
|---|---|---|
| US | `AAPL`, `MSFT`, `BRK-B` | As entered |
| NSE | `RELIANCE`, `TCS`, `HDFCBANK` | Adds `.NS` |
| BSE | `500325`, `532540` | Adds `.BO` |

You may also enter full Yahoo symbols such as `RELIANCE.NS` or `500325.BO`.

## Stock search and autocomplete

Choose a market and type at least two characters in **Company or ticker**. Search runs after a 350 ms debounce without freezing the interface.

- **US:** Yahoo Finance company/ticker search, filtered to US equity exchanges.
- **NSE/BSE:** Screener.in public company search, interpreted using the selected exchange.
- Use Up/Down to navigate and Enter to select.
- Exact uppercase tickers receive a direct-entry fallback when no company match is found.
- Stale network responses are discarded when the query or market changes.
- Search failure never blocks exact ticker entry or valuation.

## Visual analysis and chart explanations

The **Visual analysis** workspace contains four native Qt charts:

- **Price vs valuation:** one-year price history with today's fair-value and valuation-buffer reference lines.
- **Model comparison:** primary model, earnings power value, peer and own-history multiples, blended value, and market price.
- **Fundamental trends:** revenue, net income, and free cash flow across up to five annual observations.
- **Scenario range:** conservative-to-optimistic range with market, base, and valuation buffer markers.

Additional visual improvements:

- Sensitivity values use a green/amber/red heatmap and bold base-assumption cell.
- Monte Carlo includes a market-price marker and distribution bars.
- Detailed PDFs include a price chart, model bars, sensitivity heatmap, and Monte Carlo histogram.

Reference lines are today's model outputs—not historical fair values. Charts explain estimates and must not be interpreted as forecasts or trading signals.

## Assumptions review

After analyzing a stock, open **Assumptions review** to compare automatic and reviewed inputs. The screen provides automatic values, editable reviewed values, differences, per-field locks, presets, weight-total validation, and an optional reviewer note.

- Presets never change locked fields.
- Model weights must total 100%.
- Discount rate must remain above terminal growth.
- Unaccepted changes pause PDF export to prevent stale reports.
- Accepted overrides are recalculated across scenarios, sensitivity, Monte Carlo, charts, and dynamic valuation buffer.
- PDFs disclose every automatic-versus-reviewed difference and the reviewer note.
- Batch CSV exports include preset and override metadata.

## Data lineage and citations

After analysis, open **Data lineage** to inspect each important input. Rows show the value used, source, period, transformation, and status. Select a row to open its public citation or export the full lineage trail to CSV.

Detailed PDFs include the same lineage as a clickable appendix. Batch CSVs include lineage count, sources checked, and de-duplicated citation URLs. Typical transformations identify median normalization, EPS derivation, crore-to-currency conversion, peer-median construction, and official-exchange price selection. Citations document provenance but do not guarantee that the source is accurate or unchanged.

## Model audit trail

Every valuation receives a unique analysis ID, UTC creation time, app/model/audit-schema versions, Monte Carlo seed, ordered audit events, and SHA-256 content hash. Accepted assumption recalculations create a new analysis ID linked to the previous one through `parent_analysis_id`.

The **Model audit** workspace displays all events and can export the complete record to JSON, copy the analysis ID, and verify integrity. Detailed PDFs contain the audit metadata and event log; batch PDFs contain an audit manifest; batch CSVs include IDs, versions, seed, and hash.

The audit hash provides tamper-evidence only. It is not an Authenticode or cryptographic publisher signature and does not prove that the model is accurate.

## Specialized financial-company data

For banks, NBFCs/lenders, insurers, and other financial institutions, open **Financial company** to review regulatory and operating metrics that ordinary-company debt/EBITDA and FCF analysis cannot represent properly. Public values and proxies are shown separately from reviewed manual values.

The specialized engine uses residual income, justified P/B, peer multiples, and insurer embedded value when available. Manual inputs create lineage records, a child audit ID, a new audit hash, and updated risk/quality/confidence/valuation-buffer results. Unavailable fields remain “Not set”; they are never treated as zero.

All NPA, capital, CET1, provision coverage, CASA, credit cost, solvency, embedded value, VNB, and premium figures must be verified against official regulatory or company filings.

## Broad stock coverage and fallback valuation

The app now supports loss-making or negative-FCF operating companies using clearly labeled low-confidence fallbacks when positive public inputs exist:

- Bounded sector revenue multiple
- 80% positive book-value or positive net-cash floor
- Peer P/B fallback when peer P/E cannot be used
- Quarterly TTM and trailing-provider data when annual statements are unavailable
- Share-count inference from market cap ÷ price when necessary

Fallback results are capped at Low confidence, require at least a 35% dynamic valuation buffer, appear prominently in the UI/PDF, and are recorded in lineage and audit events. The BSE resolver now requires an exact security-ID match, preventing symbols such as `SIL` from incorrectly resolving to `CRISIL`.

No free source can guarantee every listed, suspended, newly listed, pre-revenue, or delisted security. If no positive FCF, revenue/share, book/net-cash, or peer-supported input exists, the app gives a precise “fair value unavailable” explanation rather than fabricating a number.

## External Moneycontrol and filing review

For Indian stocks, open **External review**, click **Find on Moneycontrol**, and enter only the values you verified. Paste the exact source URL and financial period before applying. The app does not automatically scrape Moneycontrol or bypass access controls.

Official NSE/BSE price remains preferred. Manually reviewed values can fill or compare P/E, book value, ROE, market cap, revenue, net profit, and FCF. Every accepted field creates lineage, a child audit ID, a new hash, PDF disclosure, and an external-review record. Pending external entries pause PDF export to prevent stale or uncited reports.

## Watchlists and alerts

Add a symbol or the current analysis to the persistent local watchlist. Configure a custom price, minimum modeled upside, maximum financial/governance risk, fair-value-change threshold, and valuation buffer alert. **Refresh all alerts** updates valuations and creates alerts only when a condition changes from inactive to active.

Unread alerts, last price/fair value, status, and thresholds are stored locally in SQLite. The app does not require a FairScope account or upload the watchlist to a FairScope cloud service. Alerts run while the desktop app is open and refreshed; they are research notifications, not trading instructions.

## Corporate filings and actions

Use **Filings & actions** to monitor SEC EDGAR forms for US companies, public company documents for Indian stocks, best-effort NSE/BSE announcements/actions, and Yahoo dividends/splits. Events are de-duplicated, stored locally, linked to the original source, and retain read/unread status.

US SEC monitoring requires a contact email stored locally for the SEC User-Agent. Monitoring runs only when the app is open and refreshed; it is not a 24/7 cloud service. Website access can fail or change, so official filings remain the final source.

## Local database and caching

The **Local database** workspace shows cached stock snapshots, freshness, source date, payload size, and the latest 1,000 valuation audit records. The default cache lifetime is six hours and can be changed from 0.5 to 168 hours.

If network sources fail, optional stale fallback keeps analysis available while clearly recording cache age and reducing data-quality confidence. Stock cache, history, watchlists, and corporate-monitor data remain local and are cleared independently.

## Background processing

Batch and watchlist jobs use up to three parallel workers by default, with automatic retry/backoff for temporary network and rate-limit errors. A determinate job bar supports Pause, Resume, and Cancel.

Progress and partial results are written to SQLite. If the app closes unexpectedly, the Local database workspace identifies the interrupted job and offers **Recover job**. A single-stock **Refresh sources** option bypasses fresh cache when new data is required.

## Automated testing and quality

The project includes cross-platform GitHub Actions for Windows, macOS, and Linux on Python 3.11–3.13. Offline tests cover valuation, PDFs, CSV/XLSX imports, caching, stale fallback, audit integrity, background jobs, watchlists, corporate monitoring, extreme inputs, and a 100-stock stress batch.

Run `python run_quality_checks.py` after installing `requirements-dev.txt`. Live KNSL, SIL.BO, and HDFCBANK tests are optional through `FAIRSCOPE_RUN_NETWORK_TESTS=1` so ordinary CI remains reproducible.

## Error monitoring and diagnostics

The **Diagnostics** workspace records sanitized local errors, checks Yahoo/Screener/NSE/BSE connectivity, verifies/optimizes SQLite databases, copies the last error, opens logs, and exports a support ZIP. Support ZIPs intentionally exclude databases, watchlists and valuations, SEC email, and credentials.

## Colour watchlist and alert PDF

The Watchlists & alerts workspace exports a complete branded PDF with summary cards, valuation/buffer/risk snapshot, all thresholds, last status, and complete alert history. Alert rows are colour-coded red, amber, or green by severity.

## Credentials and local privacy

The SEC contact email is encrypted using an OS-keychain-backed Fernet key where available, with a protected local-key fallback. Databases, WAL/SHM files, encryption material, secure settings, and logs use restrictive local permissions where supported. Privacy mode masks watchlist values, and diagnostic ZIPs exclude application databases and redact active watchlist symbols.

## Professional PDF design

Detailed stock reports now begin with a branded cover and executive summary, followed by a clickable contents page and PDF bookmarks. Running headers/footers identify the symbol, analysis ID, model/audit versions, and page number.

The report combines valuation cards, charts, score bars, sensitivity heatmap, Monte Carlo distribution, assumptions disclosure, specialized financial data, external reviews, model audit, and clickable lineage citations. PDF metadata and vector graphics support clear printing and zooming.

## Uncertainty-first wording

The app does not label any stock Safe, Guaranteed, Buy, Strong Buy, or Risk-free. User-facing “margin of safety” wording is replaced with **valuation buffer**, which is explicitly defined as an assumption-based threshold that does not protect against loss. Model confidence describes input/model consistency—not the probability of earning a return.

An exported audit can also be verified from the command line:

```bash
python verify_audit_json.py Sample_AAPL_Model_Audit.json
```

## Using the app

1. Choose **US**, **NSE**, or **BSE**.
2. Enter a ticker and click **Analyze stock**.
3. Review the three scenario values and blended base fair value.
4. Optionally edit the **Assumptions** tab and click **Recalculate scenarios**.
5. Click **Export full PDF** and choose where to save the report.

## Import and analyze a stock list

1. Open the **Import stock list** tab.
2. Click **Import CSV / Excel / TXT**. Files may contain a required `Symbol` (or `Ticker`) column and an optional `Market` (or `Exchange`) column.
3. Click **Analyze imported list**. Up to 100 unique stocks are processed without freezing the interface.
4. Export the completed table to CSV or a branded batch-summary PDF.
5. Double-click a successful row to open its detailed scenarios and export an individual full report.

Example:

```csv
Symbol,Market,Quantity,Cost Basis,Target Weight
AAPL,US,10,180,
MSFT,US,5,420,
RELIANCE,NSE,25,1200,
TCS,NSE,10,3500,
500325,BSE,20,1300,
```

Use the current market selector as the default when a row has no Market value. Full `.NS` and `.BO` symbols are recognized automatically.

## Valuation engine 5.0

### Normalization
Free cash flow and earnings are normalized as the latest annual revenue multiplied by the median margin of the last four to five years, so growing companies are not anchored to stale years. Stock-based compensation is deducted from free cash flow. For Indian stocks, 10-year Screener.in operating and net margins are blended in (cyclicals use the 10-year mid-cycle margin); the long series is rescaled to the Yahoo definition using overlapping fiscal years.

### Cost of capital
Cost of equity = risk-free rate + beta × equity risk premium + company-specific premium (up to 2 points each for financial and governance risk). The US risk-free rate is the live 10-year Treasury yield (^TNX); India uses an editable 10-year government bond yield. Beta is a 5-year monthly regression against the S&P 500 or NIFTY 50 (Yahoo beta as fallback), Blume-adjusted and bounded to 0.6–2.0. WACC blends after-tax debt cost at market-value weights (capped at 60% debt). Defaults: US ERP 4.5%, India ERP 5.5%; change them under **Data source → Valuation parameters**.

### Primary, secondary, and relative models
- **FCFF DCF at WACC:** normalized FCFF (EBIT after tax + depreciation − capex − working-capital investment) grows through a high-growth stage of 3–10 years, set by how far and how consistently ROIC has exceeded the cost of capital, then fades to terminal growth. Terminal value deducts the reinvestment needed for terminal growth (g ÷ return on new capital). Equity value = enterprise value − debt − minority interest + cash + investments. Terminal values above 75% of the total are flagged and widen the valuation buffer.
- **Earnings power value** replaces Graham's formula: normalized after-tax operating profit ÷ cost of capital, less net claims — the zero-growth value.
- **Relative value:** peer P/E (growth-adjusted), forward P/E, EV/EBITDA, or ROE-adjusted P/B for financials, blended 60/40 with the stock's own median multiples at past fiscal year-ends.
- **Financial institutions** keep residual income and justified P/B or embedded value; bank Gross/Net NPA is read from Screener.in quarterly results when available.
- **Loss-making companies** use a revenue DCF with free-cash-flow margins converging to a sector target (fallback, minimum 35% buffer). **Holding companies** credit listed investments (enter market value under External review) after a 20% holding discount.

### Growth and scenarios
Initial growth blends the historical/provider trend (40%), analyst consensus (30%), and fundamental growth = reinvestment rate × ROIC (30%), re-normalized when a source is missing. Fair value is probability-weighted across the three scenarios; the base-case value is shown alongside.

### Quality and forensic screens
Piotroski F-score and Altman Z feed financial risk; Beneish M-score, promoter pledge (NSE best effort or manual entry), and FII/DII trend feed governance risk; ROIC history, 10-year ROCE, margin stability, cash conversion cycle, and net share repurchases feed business quality. They are statistical screens, not findings of misstatement.

### Backtest
The **Backtest** workspace rebuilds each stock as it looked about 90 days after each of the last one to four fiscal year-ends, values it with only that data, and compares the modeled upside with the total return that followed (rank correlation, hit rate, and annualized returns of model-undervalued versus model-overvalued stocks). Peer multiples, beta, and the risk-free rate use current values because free sources keep no history, so results are indicative, not a rigorous out-of-sample test.

## Phase-1 valuation engine

_Engine 5.0 above replaces the median normalization, fixed discount rates, and Graham value described in this section; the remaining Phase-1 to Phase-3 features still apply._

### Multi-year normalization
The engine uses the median of up to five annual free-cash-flow and net-income observations. Historical revenue and earnings growth are combined with available reported growth, then bounded by sector.

### Two-stage intrinsic value
Normal companies use a ten-year normalized FCF-per-share DCF: initial growth applies for five years and then fades toward terminal growth. Financial institutions use a residual-income model because ordinary FCF and debt ratios are not directly comparable.

### Live comparable companies
Yahoo Finance's free screener selects real same-industry or same-sector companies from the same region and a comparable market-cap range. The app uses median P/E for most operating companies and median P/B for financial institutions and real estate/REIT profiles. The selected peer symbols appear in the PDF.

### Sector-specific profiles
Financial institutions, real estate/REITs, commodity/cyclical companies, utilities, technology firms, and standard operating companies receive different model labels, weights, growth caps, and risk treatment.

### Dynamic valuation buffer
The user's margin is a minimum. The required margin can rise to 50% based on leverage, interest coverage, liquidity, unstable cash flow, incomplete data, cyclical exposure, and disagreement between model values.

### Risk and quality checks
Every result includes a financial-risk score, data-quality score, confidence level, risk flags, and data warnings. Missing models are excluded and remaining weights are re-normalized.

### Phase-2 analytics

- **Sensitivity table:** 5×5 blended fair values across discount-rate and terminal-growth combinations.
- **Reverse DCF:** solves for the initial five-year growth rate implied by the current market price.
- **Business-quality score:** evaluates estimated ROIC, ROE, margins, cash conversion, FCF consistency, revenue trend, and dilution.
- **Governance-risk screen:** checks available provider ratings, dilution, receivables/inventory divergence, and profit-to-cash gaps. India-specific promoter pledging, related parties, auditor qualifications, and contingent liabilities remain manual filing checks.
- **Expanded confidence score:** combines data quality, model agreement, financial risk, business quality, governance risk, and model completeness.

### Phase-3 items 11 and 12

#### 11. Monte Carlo valuation
Each stock runs 2,000 reproducible simulations varying normalized FCF/earnings/book value, initial growth, discount rate, terminal growth, and peer multiples. The app and PDF show P10, P25, median, P75, P90, valuation dispersion, and the percentage of simulations where fair value exceeds market price. These are model probabilities—not return forecasts.

> No fair-value calculation makes investing safe or guarantees returns. Verify all figures against official filings and independently review governance, business quality, and valuation risk.

## Windows x64 signed installer

Version 8.3 adds a reproducible PyInstaller + Inno Setup build and Authenticode signing pipeline under `packaging/windows/`.

A trusted signed installer requires a valid code-signing certificate. No certificate was supplied, so the downloadable source package is signing-ready but does **not** claim to contain a signed setup EXE.

On a Windows x64 build machine with Python, Inno Setup 6, the Windows SDK, and a certificate:

```powershell
$env:FAIRSCOPE_CERT_THUMBPRINT="YOUR_CERTIFICATE_THUMBPRINT"
.\packaging\windows\build_windows.ps1 -RequireSignature
```

For a PFX-based certificate, use `FAIRSCOPE_SIGNING_PFX` and `FAIRSCOPE_SIGNING_PASSWORD` as protected environment values. Never commit private keys or passwords.

The pipeline:

1. Builds a versioned Qt application with PyInstaller.
2. Signs and verifies the application EXE.
3. Builds a modern Inno Setup x64 installer.
4. Signs and verifies the final installer.
5. Runs a silent install/launch/uninstall smoke test.
6. Produces a SHA-256 file and JSON build manifest.

See `packaging/windows/README_SIGNING.md`. The included GitHub Actions workflow can produce a signed artifact after certificate secrets are configured.

## Data and limitations

The app uses free Yahoo Finance data plus best-effort Screener.in and NSE/BSE website verification. These are not guaranteed developer APIs: availability, HTML/JSON structure, anti-bot controls, delays, and field depth can change without notice. Automated access must comply with each site's terms. Always verify data against SEC filings, NSE/BSE disclosures, and company annual reports. Financial companies, REITs, cyclicals, and loss-making companies may require specialized valuation methods.

## Files

- `app.py` — PySide6 application entry point
- `app_qt.py` — modern Qt 6 interface, charts, navigation, and background workers
- `data_provider.py` — free Yahoo Finance fundamentals, history, and peer retrieval
- `india_sources.py` — Screener.in and NSE/BSE website verification with discrepancy checks
- `stock_search.py` — debounced US/NSE/BSE company and ticker search
- `valuation.py` — scenario, blended valuation, audit events, and integrity engine
- `version.py` — central app, model, and audit-schema versions
- `verify_audit_json.py` — standalone SHA-256 audit JSON verifier
- `pdf_report.py` — full branded single-stock PDF exporter
- `batch_import.py` — CSV/TXT/Excel list import and result export
- `batch_pdf_report.py` — branded batch-summary PDF exporter
- `stock_list_template.csv` — ready-to-use import example
- `PHASE1_RELEASE_NOTES.md` — version 2.0 upgrade details
- `PHASE2_RELEASE_NOTES.md` — version 3.0 sensitivity, quality, governance, and confidence details
- `QT_INTERFACE_RELEASE_NOTES.md` — version 6.0 PySide6/Qt interface details
- `FREE_DATA_SOURCE_RELEASE_NOTES.md` — version 7.0 free Yahoo Finance data change
- `INDIA_MULTI_SOURCE_RELEASE_NOTES.md` — version 8.0 Screener.in and NSE/BSE verification
- `PROGRESS_INDICATOR_BUGFIX.md` — version 8.1 background-worker and progress cleanup fix
- `APP_REVIEW_BUGFIXES.md` — version 8.2 full review and additional fixes
- `SIGNED_INSTALLER_PIPELINE_RELEASE_NOTES.md` — version 8.3 signing-ready installer details
- `SEARCH_AUTOCOMPLETE_RELEASE_NOTES.md` — version 8.4 company/ticker search details
- `CHARTS_VISUAL_EXPLANATIONS_RELEASE_NOTES.md` — version 8.5 chart and PDF visual details
- `ASSUMPTIONS_REVIEW_RELEASE_NOTES.md` — version 8.6 review, validation, and disclosure details
- `DATA_LINEAGE_CITATIONS_RELEASE_NOTES.md` — version 8.7 metric-level provenance and links
- `MODEL_AUDIT_TRAIL_RELEASE_NOTES.md` — version 8.8 analysis identity, events, and integrity hash
- `SPECIALIZED_FINANCIAL_COMPANY_RELEASE_NOTES.md` — version 8.9 bank/NBFC/insurer data and models
- `EXTERNAL_DATA_REVIEW_RELEASE_NOTES.md` — version 9.0 cited Moneycontrol/filing review workflow
- `WATCHLISTS_ALERTS_RELEASE_NOTES.md` — version 9.3 persistent local watchlists and state-aware alerts
- `CORPORATE_MONITORING_RELEASE_NOTES.md` — version 9.4 SEC/NSE/BSE/Screener filings and actions
- `LOCAL_DATABASE_CACHE_RELEASE_NOTES.md` — version 9.5 SQLite cache, stale fallback, settings and history
- `BACKGROUND_PROCESSING_RELEASE_NOTES.md` — version 9.6 parallelism, retries, controls, persistence and recovery
- `AUTOMATED_TESTING_RELEASE_NOTES.md` — version 9.7 CI matrix, coverage and regression suites
- `ERROR_MONITORING_DIAGNOSTICS_RELEASE_NOTES.md` — version 9.8 logs, health, support ZIP and watchlist PDF
- `CREDENTIALS_PRIVACY_RELEASE_NOTES.md` — version 9.9 encryption, permissions, privacy mode and popup fix
- `PDF_DESIGN_RELEASE_NOTES.md` — version 10.0 cover, TOC, bookmarks, charts and appendices
- `NON_GUARANTEE_LANGUAGE_RELEASE_NOTES.md` — version 10.1 valuation-buffer and uncertainty-first wording
- `READABLE_DIALOGS_RELEASE_NOTES.md` — version 10.2 high-contrast notification and export-confirmation dialogs
- `GOVERNANCE_ORDER_BOOK_RELEASE_NOTES.md` — version 10.3 governance-risk, promoter-holding and order-book valuation integration
- `FEATURE_REMOVAL_RELEASE_NOTES.md` — version 10.4 simplified valuation-focused interface
- `packaging/windows/` — Windows x64 PyInstaller, Inno Setup, signing, verification, and smoke-test scripts
- `.github/workflows/windows-signed-installer.yml` — certificate-secret-aware Windows build pipeline
- `.github/workflows/quality-tests.yml` — Windows/macOS/Linux Python 3.11–3.13 CI matrix
- `requirements-dev.txt`, `pyproject.toml`, `run_quality_checks.py` — reproducible local quality and coverage tooling
- `watchlist_store.py` — local SQLite watchlist, thresholds, alert state, and history
- `corporate_monitor.py` — SEC/NSE/BSE/Screener/Yahoo event retrieval and local event database
- `local_database.py` — thread-safe SQLite stock cache, settings, valuation history, and job recovery
- `background_processing.py` — cancellation, pause/resume, retries, backoff, and bounded analysis helpers
- `diagnostics.py` — sanitized rotating logs, health checks, SQLite maintenance, and support ZIP
- `secure_storage.py` — OS-keychain/Fernet secret encryption and restrictive file permissions
- `watchlist_report.py` — colourful complete watchlist and alert PDF
- `MULTI_SOURCE_Validation.csv` — live Yahoo, Screener.in, NSE/BSE verification results
- `Dr_Nilesh_Shah_Stocks_FairScope_Sample_AAPL_Reviewed_Report.pdf` — sample override disclosure report
- `Sample_AAPL_Model_Audit.json` — complete sample model audit record and SHA-256 hash
- `Dr_Nilesh_Shah_Stocks_FairScope_Sample_HDFCBANK_Specialized_Report.pdf` — sample bank review with manual regulatory fields
- `Dr_Nilesh_Shah_Stocks_FairScope_Sample_SIL_Fallback_Report.pdf` — loss-making BSE stock fallback example
- `Dr_Nilesh_Shah_Stocks_FairScope_Sample_RELIANCE_External_Review_Report.pdf` — cited manual external-review example
- `COVERAGE_VALIDATION_KNSL_SIL.csv` — live validation for KNSL and SIL on BSE/NSE
- `Dr_Nilesh_Shah_Stocks_FairScope_Coverage_Validation_KNSL_SIL.pdf` — coverage validation report
- `WATCHLIST_ALERTS_Validation.csv` — sample persistent watchlist thresholds and last status
- `CORPORATE_MONITORING_Validation.csv` — filing/action event persistence and display validation
- `LOCAL_DATABASE_CACHE_Validation.txt` — network/cache/stale/history validation summary
- `BACKGROUND_PROCESSING_Validation.txt` — retry, pause/cancel, persistence, recovery, and cache validation
- `AUTOMATED_TESTING_Validation.txt` — test count, coverage, static, dependency, and security results
- `FairScope_Diagnostics_Sample.zip` — privacy-safe sample support bundle
- `ERROR_MONITORING_DIAGNOSTICS_Validation.txt` — logging, redaction, health, ZIP, PDF and security validation
- `CREDENTIALS_PRIVACY_Validation.txt` — encryption, permissions, masking, export confirmation, and redaction validation
- `PDF_DESIGN_Validation.txt` — cover, contents, bookmarks, metadata, vector charts, audit and lineage validation
- `NON_GUARANTEE_LANGUAGE_Validation.txt` — valuation-buffer and no-recommendation wording validation
- `Dr_Nilesh_Shah_Stocks_FairScope_Watchlist_Alerts_Report.pdf` — complete colourful watchlist/alert report
- `Qt_Background_Processing_Preview.png` — determinate progress, pause, cancel, and worker-status preview
- `Qt_Interface_Preview.png` — dashboard preview of the modern desktop interface
- `Qt_Search_Autocomplete_Preview.png` — company-name autocomplete preview
- `Qt_Visual_Analysis_Preview.png` — price, model, fundamental, and scenario chart preview
- `Qt_Assumptions_Review_Preview.png` — automatic-versus-reviewed assumptions preview
- `Qt_Data_Lineage_Preview.png` — source, period, transformation, status, and citation preview
- `Qt_Model_Audit_Preview.png` — analysis ID, versions, ordered events, and integrity preview
- `Qt_Financial_Company_Preview.png` — bank/NBFC/insurer specialized-data review preview
- `Qt_External_Data_Review_Preview.png` — cited Moneycontrol/filing manual-review preview
- `Qt_Watchlists_Alerts_Preview.png` — persistent watchlist, thresholds, and alert-history preview
- `Qt_Corporate_Filings_Actions_Preview.png` — SEC/NSE/BSE/Screener filing and action monitor preview
- `Qt_Local_Database_Cache_Preview.png` — cache freshness, settings, size, and valuation-history preview
- `Qt_Diagnostics_Preview.png` — sanitized logs, provider/database health, maintenance, and export preview
- `Qt_Watchlist_Alert_Popup_Preview.png` — readable light alert popup with severity colours
- `Qt_Monte_Carlo_Preview.png` — live Yahoo Finance rendering of the Qt Monte Carlo page
- `assets/` — app icon and report-ready logo files
- `tests/test_valuation.py` — offline model tests
