"""Fair-value engine: normalized drivers, CAPM/WACC cost of capital, FCFF DCF, EPV, peer and own-history multiples,
forensic quality scores, probability-weighted scenarios, and risk-aware valuation buffers."""
from __future__ import annotations

import hashlib
import json
import random
import uuid
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from math import exp, isfinite, sqrt
from statistics import StatisticsError, correlation, median, pstdev
from typing import Dict, Optional

from fundamentals import (
    BENEISH_THRESHOLD,
    altman_z_score,
    beneish_m_score,
    cagr,
    capital_allocation,
    cash_conversion_cycle,
    effective_tax_rate,
    historical_multiples,
    institutional_trend,
    level_adjusted_long_median,
    margin_stability,
    owner_earnings,
    piotroski_f_score,
    research_capital,
    roic_history,
    series,
    value_at,
)
from logger import get_logger
from version import APP_VERSION, AUDIT_SCHEMA_VERSION, MODEL_VERSION

logger = get_logger("ValuationEngine")


@dataclass
class DataLineageEntry:
    metric: str
    value: str
    source: str
    source_url: str = ""
    period: str = ""
    retrieved_at: str = ""
    transformation: str = "Direct value"
    status: str = "Received"


@dataclass
class FinancialCompanyMetrics:
    subtype: str = "Diversified financial"
    reviewed_roe: Optional[float] = None
    net_interest_margin: Optional[float] = None
    financing_margin: Optional[float] = None
    gross_npa: Optional[float] = None
    net_npa: Optional[float] = None
    capital_adequacy: Optional[float] = None
    cet1_ratio: Optional[float] = None
    provision_coverage: Optional[float] = None
    casa_ratio: Optional[float] = None
    credit_cost: Optional[float] = None
    deposit_growth: Optional[float] = None
    loan_growth: Optional[float] = None
    cost_to_income: Optional[float] = None
    equity_to_assets: Optional[float] = None
    solvency_ratio: Optional[float] = None
    embedded_value_per_share: Optional[float] = None
    fair_price_to_embedded_value: Optional[float] = None
    vnb_margin: Optional[float] = None
    premium_growth: Optional[float] = None
    deposits: Optional[float] = None
    borrowings: Optional[float] = None
    total_assets: Optional[float] = None
    source: str = "Automatic public data"
    review_note: str = ""
    automatic_values: dict[str, Optional[float]] = field(default_factory=dict)
    manual_fields: list[str] = field(default_factory=list)


@dataclass
class StockData:
    symbol: str
    company: str
    market: str
    currency: str
    price: float
    shares: Optional[float] = None
    free_cash_flow: Optional[float] = None  # normalized 3–5 year FCF
    eps: Optional[float] = None             # normalized EPS when history is available
    book_value_per_share: Optional[float] = None
    growth_estimate: Optional[float] = None
    sector: str = "Not available"
    industry: str = "Not available"
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    price_to_book: Optional[float] = None
    fifty_two_week_low: Optional[float] = None
    fifty_two_week_high: Optional[float] = None
    data_timestamp: str = ""
    warnings: list[str] = field(default_factory=list)
    # Phase-1 inputs
    fcf_history: list[float] = field(default_factory=list)
    revenue_history: list[float] = field(default_factory=list)
    net_income_history: list[float] = field(default_factory=list)
    current_fcf: Optional[float] = None
    total_debt: Optional[float] = None
    cash: Optional[float] = None
    ebitda: Optional[float] = None
    ebit: Optional[float] = None
    interest_expense: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    stockholder_equity: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    net_income: Optional[float] = None
    peer_median_pe: Optional[float] = None
    peer_median_pb: Optional[float] = None
    peer_symbols: list[str] = field(default_factory=list)
    fiscal_years: list[str] = field(default_factory=list)
    # Phase-2 quality and governance inputs
    return_on_equity: Optional[float] = None
    return_on_assets: Optional[float] = None
    gross_margins: Optional[float] = None
    operating_margins: Optional[float] = None
    profit_margins: Optional[float] = None
    diluted_shares_history: list[float] = field(default_factory=list)
    receivables_history: list[float] = field(default_factory=list)
    inventory_history: list[float] = field(default_factory=list)
    capital_expenditure: Optional[float] = None
    audit_risk: Optional[float] = None
    board_risk: Optional[float] = None
    shareholder_rights_risk: Optional[float] = None
    overall_governance_risk: Optional[float] = None
    insider_ownership: Optional[float] = None
    promoter_holding_history: list[float] = field(default_factory=list)  # latest first; decimal fractions
    promoter_holding_periods: list[str] = field(default_factory=list)
    order_book: Optional[float] = None  # outstanding executable orders, same units as revenue
    order_book_period: str = ""
    order_book_source: str = ""
    price_history: list[float] = field(default_factory=list)
    price_dates: list[str] = field(default_factory=list)
    data_provider: str = "Yahoo Finance (free)"
    source_symbol: str = ""
    source_updated_date: str = ""
    licensed_data: bool = False
    data_sources: list[str] = field(default_factory=list)
    source_checks: dict[str, str] = field(default_factory=dict)
    source_discrepancies: list[str] = field(default_factory=list)
    lineage: list[DataLineageEntry] = field(default_factory=list)
    financial_metrics: Optional[FinancialCompanyMetrics] = None
    external_reviews: list[dict[str, str]] = field(default_factory=list)
    cache_status: str = "network"
    cache_saved_at: str = ""
    cache_age_hours: float = 0.0
    is_stale: bool = False
    # Engine-5 inputs: market-based cost of capital, aligned statements, peers, own history, and long-run Indian data
    beta: Optional[float] = None
    beta_source: str = ""
    risk_free_rate: Optional[float] = None
    risk_free_source: str = ""
    equity_risk_premium: Optional[float] = None
    scenario_weights: list[float] = field(default_factory=list)  # conservative, base, optimistic
    holding_discount: Optional[float] = None
    effective_tax_rate: Optional[float] = None
    statement_years: list[str] = field(default_factory=list)  # fiscal period ends, latest first
    statements: dict[str, list[Optional[float]]] = field(default_factory=dict)  # aligned to statement_years
    long_history: dict[str, list[Optional[float]]] = field(default_factory=dict)  # Screener.in 10-12 year series, latest first
    long_history_periods: list[str] = field(default_factory=list)
    long_price_dates: list[str] = field(default_factory=list)  # month-end dates, oldest first
    long_prices: list[float] = field(default_factory=list)  # split-adjusted closes
    long_adjusted_prices: list[float] = field(default_factory=list)  # dividend- and split-adjusted closes
    non_operating_investments: Optional[float] = None
    minority_interest: Optional[float] = None
    listed_investments_value: Optional[float] = None  # reviewed market value of listed holdings (sum of the parts)
    forward_eps: Optional[float] = None
    forward_pe: Optional[float] = None
    enterprise_to_ebitda: Optional[float] = None
    analyst_growth: Optional[float] = None
    analyst_long_term_growth: Optional[float] = None
    peer_median_forward_pe: Optional[float] = None
    peer_median_ev_ebitda: Optional[float] = None
    peer_median_roe: Optional[float] = None
    peer_median_growth: Optional[float] = None
    promoter_pledge: Optional[float] = None  # share of promoter holding pledged, 0-1
    dividend_payout: Optional[float] = None
    stock_based_compensation: Optional[float] = None
    # Engine-5.1 inputs: sovereign default spread removed from the government yield, peer EV/Sales, and peer regression lines
    country_default_spread: Optional[float] = None
    peer_median_ev_revenue: Optional[float] = None
    peer_pe_growth_fit: list[float] = field(default_factory=list)  # intercept, slope, peer growth min, max
    peer_pb_roe_fit: list[float] = field(default_factory=list)  # intercept, slope, peer ROE min, max
    beta_standard_error: Optional[float] = None  # standard error of the regression beta; sizes the Monte Carlo discount-rate spread
    long_statement_years: list[str] = field(default_factory=list)  # SEC EDGAR 10-K fiscal year-ends, latest first (US, up to 15)
    long_statements: dict[str, list[Optional[float]]] = field(default_factory=dict)  # statement rows aligned to long_statement_years


@dataclass
class Assumptions:
    growth: float
    discount_rate: float
    terminal_growth: float
    years: int = 10
    dcf_weight: float = 0.50
    graham_weight: float = 0.20
    relative_weight: float = 0.30
    margin_of_safety: float = 0.20  # minimum; risk engine may require more
    high_growth_years: int = 5
    scenario_weights: tuple[float, float, float] = (0.25, 0.50, 0.25)


@dataclass
class ScenarioResult:
    name: str
    growth: float
    discount_rate: float
    terminal_growth: float
    dcf: Optional[float]
    graham: Optional[float]
    relative: Optional[float]
    fair_value: Optional[float]


@dataclass
class AuditEvent:
    timestamp: str
    stage: str
    action: str
    details: dict[str, str] = field(default_factory=dict)


@dataclass
class ValuationResult:
    data: StockData
    base_assumptions: Assumptions
    scenarios: Dict[str, ScenarioResult]
    fair_value: float
    upside_pct: float
    margin_price: float
    label: str
    confidence: str
    model_notes: list[str]
    model_labels: dict[str, str] = field(default_factory=dict)
    methodology_profile: str = "Standard operating company"
    risk_score: int = 50
    data_quality_score: int = 50
    risk_flags: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    dynamic_margin: float = 0.20
    model_dispersion: Optional[float] = None
    business_quality_score: int = 50
    governance_risk_score: int = 50
    order_book_score: int = 50
    confidence_score: int = 50
    business_quality_flags: list[str] = field(default_factory=list)
    order_book_flags: list[str] = field(default_factory=list)
    governance_flags: list[str] = field(default_factory=list)
    reverse_dcf_growth: Optional[float] = None
    reverse_dcf_note: str = ""
    sensitivity_discount_rates: list[float] = field(default_factory=list)
    sensitivity_terminal_growths: list[float] = field(default_factory=list)
    sensitivity_values: list[list[Optional[float]]] = field(default_factory=list)
    monte_carlo_iterations: int = 0
    monte_carlo_percentiles: dict[str, float] = field(default_factory=dict)
    monte_carlo_probability_above_price: Optional[float] = None
    monte_carlo_std: Optional[float] = None
    monte_carlo_bin_edges: list[float] = field(default_factory=list)
    monte_carlo_bin_counts: list[int] = field(default_factory=list)
    automatic_assumptions: Optional[Assumptions] = None
    manual_overrides: dict[str, tuple[float, float]] = field(default_factory=dict)
    assumption_note: str = ""
    assumption_preset: str = "Automatic defaults"
    analysis_id: str = ""
    parent_analysis_id: str = ""
    created_at: str = ""
    app_version: str = APP_VERSION
    model_version: str = MODEL_VERSION
    audit_schema_version: str = AUDIT_SCHEMA_VERSION
    monte_carlo_seed: int = 0
    audit_events: list[AuditEvent] = field(default_factory=list)
    audit_hash: str = ""
    fallback_valuation: bool = False
    fallback_reasons: list[str] = field(default_factory=list)
    base_fair_value: Optional[float] = None
    scenario_weights: list[float] = field(default_factory=list)
    cost_of_capital: dict = field(default_factory=dict)
    valuation_drivers: dict = field(default_factory=dict)
    relative_components: dict[str, float] = field(default_factory=dict)
    growth_components: dict[str, float] = field(default_factory=dict)
    terminal_value_share: Optional[float] = None
    forensic_scores: dict = field(default_factory=dict)
    monte_carlo_spreads: dict = field(default_factory=dict)
    implied_return: Optional[float] = None  # annual shareholder return implied by today's price (primary model)
    implied_return_note: str = ""


def _valid_positive(value: Optional[float]) -> bool:
    return value is not None and isfinite(value) and value > 0


def _safe_ratio(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


DEFAULT_RISK_FREE = {"US": .043, "IN": .065}
DEFAULT_EQUITY_RISK_PREMIUM = {"US": .045, "IN": .055}
DEFAULT_TAX_RATE = {"US": .24, "IN": .2517}
DEFAULT_SCENARIO_WEIGHTS = (.25, .50, .25)
DEFAULT_HOLDING_DISCOUNT = .20
SECTOR_BETA = {"technology": 1.15, "communication services": 1.0, "consumer cyclical": 1.15, "consumer defensive": .75, "healthcare": .9, "industrials": 1.05, "basic materials": 1.15, "energy": 1.1, "utilities": .7, "real estate": .9, "financial services": 1.05}
TARGET_FCFF_MARGIN = {"technology": .18, "communication services": .14, "healthcare": .14, "consumer cyclical": .07, "consumer defensive": .07, "industrials": .08, "basic materials": .08, "energy": .08, "utilities": .10, "real estate": .25}
GROWTH_COMPONENT_WEIGHTS = {"Historical and provider trend": .40, "Analyst consensus": .30, "Fundamental (reinvestment × ROIC)": .30}
# Damodaran (January 2026), large non-financial firms: minimum interest coverage → synthetic rating → default spread.
COVERAGE_SPREADS = ((8.5, "AAA", .0040), (6.5, "AA", .0055), (5.5, "A+", .0070), (4.25, "A", .0078), (3.0, "A-", .0089), (2.5, "BBB", .0111), (2.25, "BB+", .0138), (2.0, "BB", .0184), (1.75, "B+", .0275), (1.5, "B", .0321), (1.25, "B-", .0509), (.8, "CCC", .0885), (.65, "CC", .1261), (.2, "C", .16), (float("-inf"), "D", .19))


def synthetic_rating(coverage: float) -> tuple[str, float]:
    """Rating and default spread implied by EBIT ÷ interest expense."""
    return next((rating, spread) for floor, rating, spread in COVERAGE_SPREADS if coverage >= floor)


@dataclass
class CapitalCost:
    risk_free_rate: float
    risk_free_source: str
    beta: float
    beta_source: str
    equity_risk_premium: float
    company_risk_premium: float
    cost_of_equity: float
    pre_tax_cost_of_debt: float
    tax_rate: float
    debt_weight: float
    wacc: float
    debt_rating: str = ""


@dataclass
class Drivers:
    basis: str = "Unavailable"
    revenue: Optional[float] = None
    shares: Optional[float] = None
    fcff_margin: Optional[float] = None
    ebit_margin: Optional[float] = None
    nopat_margin: Optional[float] = None
    tax_rate: float = .25
    net_claims: float = 0.0  # debt + minority interest - cash - credited investments
    investments_credit: float = 0.0
    invested_capital: Optional[float] = None
    roic: Optional[float] = None
    roic_history: list[Optional[float]] = field(default_factory=list)
    reinvestment_rate: Optional[float] = None
    current_margin: Optional[float] = None
    target_margin: Optional[float] = None
    margin_note: str = ""
    observations: int = 0
    research_margin: float = 0.0  # after-tax R&D add-back ÷ revenue from capitalizing research


@dataclass
class ValuationContext:
    profile: str
    tax_rate: float
    drivers: Drivers
    capital: CapitalCost
    risk_score: int
    risk_flags: list[str]
    governance_score: int
    governance_flags: list[str]
    historical: dict
    relative_value: Optional[float]
    relative_components: dict[str, float]
    relative_label: str

    @property
    def equity_spread(self) -> float:
        """Cost of equity minus WACC; equity cash flows and per-share earnings are discounted at the cost of equity."""
        return max(0.0, self.capital.cost_of_equity - self.capital.wacc)


def _region(data: StockData) -> str:
    return "IN" if data.market in {"NSE", "BSE"} else "US"


def _market_value(data: StockData) -> Optional[float]:
    if _valid_positive(data.market_cap):
        return data.market_cap
    return data.price * data.shares if _valid_positive(data.price) and _valid_positive(data.shares) else None


def _is_holding_company(data: StockData) -> bool:
    text = f"{data.industry} {data.company}".lower()
    return "conglomerate" in text or "holding" in text


def cost_of_capital(data: StockData, profile: str, tax: float, risk_score: int, governance_score: int) -> CapitalCost:
    """CAPM cost of equity plus company-specific premiums, blended with after-tax debt cost at market-value weights."""
    region = _region(data)
    rf = data.risk_free_rate if data.risk_free_rate is not None and isfinite(data.risk_free_rate) and 0 < data.risk_free_rate < .2 else DEFAULT_RISK_FREE[region]
    source = data.risk_free_source or ("Default India 10-year government bond yield" if region == "IN" else "Default US 10-year Treasury yield")
    erp = data.equity_risk_premium if data.equity_risk_premium is not None and isfinite(data.equity_risk_premium) and 0 < data.equity_risk_premium < .2 else DEFAULT_EQUITY_RISK_PREMIUM[region]
    if data.beta is not None and isfinite(data.beta) and .05 <= data.beta <= 4:
        beta = min(2.0, max(.6, .67 * data.beta + .33)); beta_source = f"{data.beta_source or 'Provider beta'} {data.beta:.2f}, Blume-adjusted"
    else:
        beta = SECTOR_BETA.get(data.sector.lower(), 1.0); beta_source = "Sector default beta (provider beta unavailable)"
    # Beta already prices market risk, so balance-sheet and governance premiums are capped at 2 points each.
    premium = max(0.0, (risk_score - 25) / 75 * .02) + max(0.0, (governance_score - 35) / 65 * .02)
    cost_of_equity = rf + beta * erp + premium
    debt = data.total_debt if _valid_positive(data.total_debt) else 0.0
    # Lenders charge the full government yield (sovereign spread included) plus the spread for the coverage-implied rating.
    government = rf + (data.country_default_spread or 0.0)
    rating, default_spread = synthetic_rating(data.ebit / data.interest_expense) if data.ebit is not None and _valid_positive(data.interest_expense) else ("Unrated", .02)
    # Loss-makers rate "D" on negative coverage; lenders still rank ahead of shareholders, so debt never costs more than equity.
    cost_of_debt = min(government + default_spread, cost_of_equity)
    equity_value = _market_value(data)
    debt_weight = 0.0 if profile == "Financial institution" or not equity_value or debt <= 0 else min(.6, debt / (debt + equity_value))
    wacc = (1 - debt_weight) * cost_of_equity + debt_weight * cost_of_debt * (1 - tax)
    return CapitalCost(rf, source, beta, beta_source, erp, premium, cost_of_equity, cost_of_debt, tax, debt_weight, wacc, rating)


def build_drivers(data: StockData, profile: str, tax: float) -> Drivers:
    """Normalized operating drivers: latest revenue × median free-cash-flow-to-firm and operating margins."""
    drivers = Drivers(shares=data.shares if _valid_positive(data.shares) else None, tax_rate=tax)
    revenue = series(data, "revenue")
    drivers.revenue = next((value for value in revenue if value is not None and value > 0), None) or (data.revenue_history[0] if data.revenue_history and _valid_positive(data.revenue_history[0]) else None)
    if profile == "Financial institution":
        drivers.basis = "Residual income"
        return drivers
    ebit, dep, capex, working = series(data, "ebit"), series(data, "depreciation"), series(data, "capital_expenditure"), series(data, "working_capital_change")
    fcff_margins, ebit_margins = [], []
    for index, sales in enumerate(revenue[:5]):
        operating = value_at(ebit, index)
        if sales is None or sales <= 0 or operating is None:
            continue
        ebit_margins.append(operating / sales)
        depreciation, spend = value_at(dep, index), value_at(capex, index)
        if depreciation is not None and spend is not None:
            fcff = operating * (1 - tax) + depreciation + (spend if spend <= 0 else -spend) + (value_at(working, index) or 0.0)
            fcff_margins.append(fcff / sales)
    drivers.observations = len(fcff_margins)
    fcff_margin = median(fcff_margins) if fcff_margins else None
    ebit_margin = median(ebit_margins) if ebit_margins else None
    recent_margins = [value_at(ebit, index) / sales if sales and sales > 0 and value_at(ebit, index) is not None else None for index, sales in enumerate(revenue)]
    long_run = level_adjusted_long_median((data.long_history or {}).get("ebit_margin", []), data.long_history_periods, data.statement_years, recent_margins)
    if ebit_margin is not None and long_run is not None:
        adjusted = long_run if profile == "Cyclical / commodity" else .5 * ebit_margin + .5 * long_run
        drivers.margin_note = ("Mid-cycle: 10-year median operating margin" if profile == "Cyclical / commodity" else "Operating margin blends recent and 10-year medians") + f" ({ebit_margin:.1%} recent, {long_run:.1%} long-run; Screener.in history level-matched to Yahoo)."
        if fcff_margin is not None:
            fcff_margin += (adjusted - ebit_margin) * (1 - tax)
        ebit_margin = adjusted
    elif profile == "Cyclical / commodity" and ebit_margin is not None:
        drivers.margin_note = "Cyclical margins use only the available annual statements; a full-cycle history was unavailable."
    drivers.fcff_margin, drivers.ebit_margin = fcff_margin, ebit_margin
    # R&D above its amortization is growth investment (Damodaran): NOPAT adds it back and invested capital carries the research asset.
    research_spent, research_asset, research_amortization = (research_capital(data) or [(0.0, 0.0, 0.0)])[0]
    drivers.research_margin = (research_spent - research_amortization) * (1 - tax) / drivers.revenue if drivers.revenue and research_spent > 0 else 0.0
    drivers.nopat_margin = ebit_margin * (1 - tax) + drivers.research_margin if ebit_margin is not None else None
    holding = data.holding_discount if data.holding_discount is not None and 0 <= data.holding_discount < 1 else DEFAULT_HOLDING_DISCOUNT
    if _valid_positive(data.listed_investments_value):
        investments = data.listed_investments_value * (1 - holding)
    elif _valid_positive(data.non_operating_investments):
        investments = data.non_operating_investments * ((1 - holding) if _is_holding_company(data) else 1.0)
    else:
        investments = 0.0
    drivers.investments_credit = investments
    drivers.net_claims = (data.total_debt or 0.0) + (data.minority_interest or 0.0) - (data.cash or 0.0) - investments
    capital = (data.stockholder_equity or 0.0) + (data.total_debt or 0.0) - (data.cash or 0.0) + research_asset
    if data.stockholder_equity is not None and capital > 0:
        drivers.invested_capital = capital
    if drivers.invested_capital and drivers.nopat_margin is not None and drivers.revenue:
        drivers.roic = drivers.revenue * drivers.nopat_margin / drivers.invested_capital
    drivers.roic_history = roic_history(data, tax)
    if drivers.nopat_margin and drivers.nopat_margin > 0 and fcff_margin is not None:
        drivers.reinvestment_rate = min(1.5, max(-.5, 1 - fcff_margin / drivers.nopat_margin))
    if fcff_margin is not None and fcff_margin > 0 and drivers.revenue and drivers.shares:
        drivers.basis = "FCFF"
    elif _valid_positive(data.free_cash_flow) and drivers.shares:
        drivers.basis = "Equity FCF"
    elif drivers.revenue and drivers.shares:
        drivers.basis = "Revenue DCF (margin convergence)"
        drivers.target_margin = TARGET_FCFF_MARGIN.get(data.sector.lower(), .08)
        current = fcff_margin if fcff_margin is not None else (data.free_cash_flow / drivers.revenue if data.free_cash_flow is not None and isfinite(data.free_cash_flow) else 0.0)
        drivers.current_margin = min(current, drivers.target_margin)
    return drivers


def build_context(data: StockData) -> ValuationContext:
    profile, _, _ = methodology_for(data)
    tax = effective_tax_rate(data, DEFAULT_TAX_RATE[_region(data)])
    drivers = build_drivers(data, profile, tax)
    risk_score, risk_flags = risk_assessment(data)
    governance_score, governance_flags = governance_assessment(data)
    capital = cost_of_capital(data, profile, tax, risk_score, governance_score)
    historical = historical_multiples(data)
    relative, components, label = relative_valuation(data, profile, drivers, historical)
    return ValuationContext(profile, tax, drivers, capital, risk_score, risk_flags, governance_score, governance_flags, historical, relative, components, label)


def growth_components(data: StockData, context: ValuationContext) -> dict[str, float]:
    """Historical/provider trend, analyst consensus, and fundamental growth (reinvestment rate × ROIC)."""
    components = {}
    if data.growth_estimate is not None and isfinite(data.growth_estimate):
        components["Historical and provider trend"] = data.growth_estimate
    analyst = data.analyst_long_term_growth if data.analyst_long_term_growth is not None else data.analyst_growth
    if analyst is not None and isfinite(analyst) and -.5 < analyst < 1:
        components["Analyst consensus"] = analyst
    d = context.drivers
    if d.reinvestment_rate is not None and d.roic is not None and d.reinvestment_rate > 0 and d.roic > 0:
        components["Fundamental (reinvestment × ROIC)"] = min(.40, d.reinvestment_rate * d.roic)
    return components


def competitive_advantage_years(data: StockData, context: ValuationContext) -> int:
    """High-growth stage length (3-10 years) from how far and how consistently ROIC exceeded the cost of capital."""
    values = [x for x in context.drivers.roic_history if x is not None]
    long = [x * (1 - context.tax_rate) for x in (data.long_history or {}).get("roce", [])[:10] if x is not None]
    if len(long) > len(values):
        values = long
    if not values and context.drivers.roic is not None:
        values = [context.drivers.roic]
    if not values:
        return 5
    spread = median(values) - context.capital.wacc
    consistency = sum(1 for x in values if x > context.capital.wacc) / len(values)
    if spread >= .10 and consistency >= .99 and len(values) >= 3:
        return 10
    if spread >= .05 and consistency >= .75:
        return 7
    return 5 if spread > 0 else 3


def _scenario_weights(data: StockData) -> tuple[float, float, float]:
    weights = [float(x) for x in (data.scenario_weights or [])[:3] if x is not None and isfinite(float(x)) and float(x) >= 0]
    if len(weights) != 3 or sum(weights) <= 0:
        return DEFAULT_SCENARIO_WEIGHTS
    total = sum(weights)
    return (weights[0] / total, weights[1] / total, weights[2] / total)


def methodology_for(data: StockData) -> tuple[str, tuple[float, float, float], dict[str, str]]:
    sector, industry = data.sector.lower(), data.industry.lower()
    if "financial" in sector or any(x in industry for x in ("bank", "insurance", "credit services", "capital markets")):
        return "Financial institution", (0.35, 0.15, 0.50), {"dcf": "Residual income", "graham": "Graham / book", "relative": "Peer P/B"}
    if "real estate" in sector or "reit" in industry:
        return "Real estate / REIT", (0.35, 0.20, 0.45), {"dcf": "Normalized cash flow", "graham": "Earnings power value", "relative": "Peer P/B"}
    if sector in {"energy", "basic materials"}:
        return "Cyclical / commodity", (0.40, 0.25, 0.35), {"dcf": "Mid-cycle DCF", "graham": "Earnings power value", "relative": "Peer P/E"}
    if sector == "utilities":
        return "Regulated / utility", (0.50, 0.15, 0.35), {"dcf": "Two-stage DCF", "graham": "Earnings power value", "relative": "Peer P/E"}
    if sector == "technology":
        return "Technology operating company", (0.55, 0.10, 0.35), {"dcf": "Two-stage DCF", "graham": "Earnings power value", "relative": "Peer P/E"}
    return "Standard operating company", (0.50, 0.20, 0.30), {"dcf": "Two-stage DCF", "graham": "Earnings power value", "relative": "Peer P/E"}


def risk_assessment(data: StockData) -> tuple[int, list[str]]:
    score, flags = 20, []
    profile, _, _ = methodology_for(data)
    if profile == "Financial institution":
        score = 25
        if not _valid_positive(data.book_value_per_share):
            score += 20; flags.append("Positive book value per share could not be verified.")
        if not _valid_positive(data.eps):
            score += 25; flags.append("Positive normalized earnings could not be verified.")
        if data.price_to_book is not None and data.price_to_book > 5:
            score += 10; flags.append(f"Price/book is elevated ({data.price_to_book:.1f}×).")
        if not data.peer_symbols:
            score += 10; flags.append("Comparable financial institutions were unavailable.")
        metrics=data.financial_metrics
        if metrics:
            if metrics.gross_npa is not None:
                if metrics.gross_npa>.05:score+=20;flags.append(f"Gross NPA is high ({metrics.gross_npa:.2%}).")
                elif metrics.gross_npa>.03:score+=10;flags.append(f"Gross NPA is elevated ({metrics.gross_npa:.2%}).")
            if metrics.net_npa is not None:
                if metrics.net_npa>.02:score+=15;flags.append(f"Net NPA is high ({metrics.net_npa:.2%}).")
                elif metrics.net_npa>.01:score+=7;flags.append(f"Net NPA is elevated ({metrics.net_npa:.2%}).")
            if metrics.capital_adequacy is not None:
                if metrics.capital_adequacy<.12:score+=20;flags.append(f"Capital adequacy is weak ({metrics.capital_adequacy:.2%}).")
                elif metrics.capital_adequacy<.15:score+=8;flags.append(f"Capital adequacy buffer is limited ({metrics.capital_adequacy:.2%}).")
            if metrics.cet1_ratio is not None and metrics.cet1_ratio<.10:score+=15;flags.append(f"CET1 ratio is below 10% ({metrics.cet1_ratio:.2%}).")
            if metrics.provision_coverage is not None and metrics.provision_coverage<.60:score+=10;flags.append(f"Provision coverage is below 60% ({metrics.provision_coverage:.2%}).")
            if metrics.credit_cost is not None and metrics.credit_cost>.025:score+=10;flags.append(f"Credit cost is elevated ({metrics.credit_cost:.2%}).")
            if metrics.equity_to_assets is not None and metrics.equity_to_assets<.05:score+=8;flags.append(f"Equity-to-assets proxy is low ({metrics.equity_to_assets:.2%}).")
            if metrics.subtype=="Insurance":
                if metrics.solvency_ratio is not None and metrics.solvency_ratio<1.5:score+=20;flags.append(f"Insurer solvency ratio is below 1.50x ({metrics.solvency_ratio:.2f}x).")
                if metrics.premium_growth is not None and metrics.premium_growth<0:score+=10;flags.append(f"Premium/revenue growth proxy is negative ({metrics.premium_growth:.2%}).")
            required=(metrics.solvency_ratio,) if metrics.subtype=="Insurance" else (metrics.gross_npa,metrics.net_npa,metrics.capital_adequacy)
            if all(value is None for value in required):flags.append("Key regulatory or asset-quality metrics are missing; review official filings or enter reviewed specialized data.")
        else:flags.append("Specialized financial-company metrics were unavailable; regulatory-capital and asset-quality review remains manual.")
        return max(0,min(100,score)), flags
    debt_ebitda = _safe_ratio(data.total_debt, data.ebitda)
    if debt_ebitda is None:
        score += 8; flags.append("Debt/EBITDA could not be verified.")
    elif debt_ebitda > 5:
        score += 25; flags.append(f"High debt/EBITDA ({debt_ebitda:.1f}×).")
    elif debt_ebitda > 3:
        score += 14; flags.append(f"Elevated debt/EBITDA ({debt_ebitda:.1f}×).")
    elif debt_ebitda < 1:
        score -= 5

    interest_cover = _safe_ratio(data.ebit, data.interest_expense)
    if interest_cover is not None:
        if interest_cover < 1.5:
            score += 22; flags.append(f"Weak interest coverage ({interest_cover:.1f}×).")
        elif interest_cover < 3:
            score += 10; flags.append(f"Limited interest coverage ({interest_cover:.1f}×).")
    current_ratio = _safe_ratio(data.current_assets, data.current_liabilities)
    if current_ratio is not None and current_ratio < 1:
        score += 10; flags.append(f"Current ratio below 1 ({current_ratio:.2f}).")

    if data.fcf_history:
        negative = sum(1 for x in data.fcf_history if x <= 0)
        if negative >= 2:
            score += 18; flags.append(f"Free cash flow was non-positive in {negative} reported years.")
        positive = [x for x in data.fcf_history if x > 0]
        if len(positive) >= 3 and max(positive) / max(min(positive), 1) > 5:
            score += 8; flags.append("Free cash flow has been highly volatile.")
    else:
        score += 12; flags.append("Multi-year free-cash-flow history is unavailable.")

    if data.net_income and data.operating_cash_flow is not None and data.net_income > 0 and data.operating_cash_flow < data.net_income * 0.6:
        score += 10; flags.append("Operating cash flow is materially below reported net income.")
    net_debt = (data.total_debt or 0) - (data.cash or 0)
    if data.stockholder_equity and data.stockholder_equity > 0 and net_debt / data.stockholder_equity > 1.5:
        score += 10; flags.append("Net debt is high relative to equity.")
    altman = altman_z_score(data, _market_value(data))
    if altman:
        if altman["zone"] == "Distress":
            score += 15; flags.append(f"{altman['model']} is in the distress zone ({altman['score']:.2f}).")
        elif altman["zone"] == "Grey":
            score += 6; flags.append(f"{altman['model']} is in the grey zone ({altman['score']:.2f}).")
        else:
            score -= 3
    piotroski = piotroski_f_score(data)
    if piotroski:
        if piotroski["score"] <= 3:
            score += 8; flags.append(f"Piotroski F-score is weak ({piotroski['score']} of {piotroski['tested']} tests passed).")
        elif piotroski["score"] >= 7:
            score -= 4
    return max(0, min(100, int(round(score)))), flags


def data_quality_assessment(data: StockData) -> tuple[int, list[str]]:
    score, flags = 100, []
    profile, _, _ = methodology_for(data)
    if profile != "Financial institution" and len(data.fcf_history) < 3:
        score -= 20; flags.append("Fewer than three annual FCF observations were available.")
    if len(data.revenue_history) < 3:
        score -= 10; flags.append("Revenue history is incomplete.")
    if not _valid_positive(data.shares):
        score -= 20; flags.append("Share count was unavailable.")
    if data.eps is None:
        score -= 15; flags.append("Normalized EPS was unavailable.")
    if data.book_value_per_share is None:
        score -= 10; flags.append("Book value per share was unavailable.")
    if not data.peer_symbols:
        score -= 15; flags.append("A usable live peer set was unavailable.")
    if data.peer_symbols and len(data.peer_symbols) < 4:
        score -= 7; flags.append("The live peer sample is small.")
    if data.source_discrepancies:
        score -= min(20,10*len(data.source_discrepancies));flags.extend(data.source_discrepancies)
    if data.market in {"NSE","BSE"} and len(data.data_sources)<2:
        score -= 5;flags.append("NSE/BSE/Screener secondary verification was unavailable; Yahoo data was used alone.")
    if data.is_stale:
        penalty=min(25,5+int(data.cache_age_hours/24)*5);score-=penalty;flags.append(f"Stale cached data is {data.cache_age_hours:.1f} hours old; data-quality score reduced by {penalty} points.")
    if profile=="Financial institution":
        if data.financial_metrics is None:score-=15;flags.append("Specialized financial-company data was unavailable.")
        else:
            metrics=data.financial_metrics;key_values=(metrics.gross_npa,metrics.net_npa,metrics.capital_adequacy,metrics.solvency_ratio,metrics.embedded_value_per_share)
            if all(value is None for value in key_values):score-=8;flags.append("Regulatory asset-quality/capital or embedded-value metrics remain incomplete.")
    return max(0, min(100, score)), flags


def business_quality_assessment(data: StockData, discount_rate: float) -> tuple[int,list[str]]:
    """Score durable economics and cash conversion; 100 is strongest."""
    score=50; flags=[]
    profile,_,_=methodology_for(data)
    if profile=="Financial institution":
        roe=data.financial_metrics.reviewed_roe if data.financial_metrics and data.financial_metrics.reviewed_roe is not None else data.return_on_equity
        if roe is not None:
            if roe>=.18: score+=20
            elif roe>=.12: score+=10
            elif roe<.08: score-=18; flags.append(f"Return on equity is low ({roe:.1%}).")
        else: score-=8; flags.append("Return on equity was unavailable.")
        if data.profit_margins is not None:
            if data.profit_margins>=.20: score+=10
            elif data.profit_margins<.08: score-=10
        earnings_growth=cagr(data.net_income_history)
        if earnings_growth is not None:
            if .05<=earnings_growth<=.25: score+=12
            elif earnings_growth<0: score-=15; flags.append(f"Multi-year earnings trend is negative ({earnings_growth:.1%}).")
        dilution=cagr(data.diluted_shares_history)
        if dilution is not None and dilution>.08: score-=10; flags.append(f"Reported diluted share count rose materially ({dilution:.1%} annualized); verify mergers and corporate actions.")
        metrics=data.financial_metrics
        if metrics:
            margin=metrics.net_interest_margin if metrics.net_interest_margin is not None else metrics.financing_margin
            if margin is not None:
                if margin>=.035:score+=8
                elif margin<.02:score-=8;flags.append(f"Interest/financing margin is weak ({margin:.2%}).")
            if metrics.gross_npa is not None and metrics.gross_npa<.02:score+=8
            if metrics.casa_ratio is not None and metrics.casa_ratio>=.40:score+=6
            if metrics.cost_to_income is not None:
                if metrics.cost_to_income<=.45:score+=6
                elif metrics.cost_to_income>.65:score-=8;flags.append(f"Cost-to-income ratio is high ({metrics.cost_to_income:.2%}).")
            if metrics.deposit_growth is not None:
                if .05<=metrics.deposit_growth<=.25:score+=6
                elif metrics.deposit_growth<0:score-=8;flags.append(f"Deposit growth is negative ({metrics.deposit_growth:.2%}).")
            if metrics.subtype=="Insurance":
                if metrics.solvency_ratio is not None and metrics.solvency_ratio>=1.8:score+=8
                if metrics.vnb_margin is not None and metrics.vnb_margin>=.20:score+=10
                if metrics.premium_growth is not None and metrics.premium_growth>=.08:score+=6
        flags.append("Specialized scores remain screening aids; verify asset quality, capital, provisioning, and regulatory disclosures.")
        return max(0,min(100,int(round(score)))),flags
    # One ROIC definition everywhere: effective tax rate and capitalized research, as in the operating drivers.
    tax=effective_tax_rate(data,DEFAULT_TAX_RATE[_region(data)]);yearly=roic_history(data,tax);history=[x for x in yearly if x is not None]
    invested=(data.stockholder_equity or 0)+(data.total_debt or 0)-(data.cash or 0)
    roic=yearly[0] if yearly and yearly[0] is not None else (data.ebit*(1-tax)/invested) if data.ebit is not None and invested>0 else None
    if roic is not None:
        if roic>discount_rate+0.05: score+=18; flags.append(f"Estimated ROIC ({roic:.1%}) comfortably exceeds the required return.")
        elif roic>discount_rate: score+=9; flags.append(f"Estimated ROIC ({roic:.1%}) exceeds the required return.")
        else: score-=14; flags.append(f"Estimated ROIC ({roic:.1%}) is below the required return.")
    else: score-=7; flags.append("ROIC could not be estimated from the available statements.")
    roe=data.return_on_equity
    if roe is not None:
        if roe>=.18: score+=10
        elif roe<.08: score-=10; flags.append(f"Return on equity is low ({roe:.1%}).")
    if data.operating_margins is not None:
        if data.operating_margins>=.20: score+=8
        elif data.operating_margins<.05: score-=8; flags.append(f"Operating margin is thin ({data.operating_margins:.1%}).")
    if data.net_income and data.net_income>0 and data.operating_cash_flow is not None:
        conversion=data.operating_cash_flow/data.net_income
        if conversion>=1: score+=12
        elif conversion<.6: score-=15; flags.append(f"Operating cash conversion is weak ({conversion:.2f}× net income).")
    if data.fcf_history:
        positive=sum(1 for x in data.fcf_history if x>0)
        ratio=positive/len(data.fcf_history)
        if ratio>=.8: score+=10
        elif ratio<.5: score-=15; flags.append("Free cash flow was positive in fewer than half of reported years.")
    revenue_growth=cagr(data.revenue_history)
    if revenue_growth is not None:
        if .04<=revenue_growth<=.25: score+=7
        elif revenue_growth<0: score-=10; flags.append(f"Multi-year revenue trend is negative ({revenue_growth:.1%}).")
    dilution=cagr(data.diluted_shares_history)
    if dilution is not None and dilution>.03:
        score-=12; flags.append(f"Diluted share count increased approximately {dilution:.1%} annually.")
    elif dilution is not None and dilution<-.02: score+=5
    if len(history)>=3:
        above=sum(1 for x in history if x>discount_rate)/len(history)
        if above>=.99: score+=6; flags.append(f"ROIC exceeded the required return in all {len(history)} reported years.")
        elif above<.5: score-=6; flags.append(f"ROIC was below the required return in most of the {len(history)} reported years.")
    roce=[x for x in (data.long_history or {}).get("roce",[])[:10] if x is not None]
    if len(roce)>=5:
        typical=median(roce)
        if typical>=.20: score+=8; flags.append(f"Ten-year median ROCE is strong ({typical:.1%}).")
        elif typical<.10: score-=8; flags.append(f"Ten-year median ROCE is weak ({typical:.1%}).")
    stability=margin_stability(data)
    if stability and stability["variation"] is not None:
        if stability["variation"]<=.15: score+=5
        elif stability["variation"]>.5: score-=6; flags.append(f"Operating margins have been highly unstable over {stability['years']} years.")
    cycle=cash_conversion_cycle(data)
    if cycle and cycle["change"]>20: score-=5; flags.append(f"Cash conversion cycle lengthened by {cycle['change']:.0f} days over {cycle['years']} years.")
    elif cycle and cycle["change"]<-15: score+=3
    if capital_allocation(data,_market_value(data)).get("net_repurchase_yield",0)>=.01: score+=3
    return max(0,min(100,int(round(score)))),flags


def governance_assessment(data: StockData) -> tuple[int,list[str]]:
    """Governance/accounting risk screen; 0 is best. It is not a forensic audit."""
    score=20; flags=[]; observed=0
    for label,value in (("Audit",data.audit_risk),("Board",data.board_risk),("Shareholder-rights",data.shareholder_rights_risk),("Overall governance",data.overall_governance_risk)):
        if value is not None:
            observed+=1
            if value>=8: score+=12; flags.append(f"{label} risk supplied by the data provider is high ({value:.0f}/10).")
            elif value>=6: score+=6; flags.append(f"{label} risk is elevated ({value:.0f}/10).")
            elif value<=3: score-=2
    dilution=cagr(data.diluted_shares_history)
    if dilution is not None and dilution>.05: score+=15; flags.append(f"Reported share count increased materially ({dilution:.1%} annualized); verify dilution, splits, mergers, and corporate actions.")
    rev_growth=cagr(data.revenue_history)
    rec_growth=cagr(data.receivables_history)
    inv_growth=cagr(data.inventory_history)
    if rec_growth is not None and rev_growth is not None and rec_growth>rev_growth+.10:
        score+=15; flags.append("Receivables have grown materially faster than revenue.")
    if inv_growth is not None and rev_growth is not None and inv_growth>rev_growth+.12:
        score+=10; flags.append("Inventory has grown materially faster than revenue.")
    if data.net_income and data.net_income>0 and data.operating_cash_flow is not None and data.operating_cash_flow<data.net_income*.5:
        score+=15; flags.append("Reported profit is not well supported by operating cash flow.")
    if observed==0:
        score+=10; flags.append("Provider governance ratings were unavailable; auditor, board, and related-party review remains manual.")
    promoter=[value for value in data.promoter_holding_history[:13] if value is not None and 0<=value<=1]
    if len(promoter)>=3:
        change=promoter[0]-promoter[-1]
        if change>=.02:score-=min(8,int(round(change*100)));flags.append(f"Promoter holding increased by approximately {change:.1%} over the available three-year trend.")
        elif change<=-.02:score+=min(15,int(round(abs(change)*150)));flags.append(f"Promoter holding decreased by approximately {abs(change):.1%} over the available three-year trend; verify dilution, sales, and corporate actions.")
        else:flags.append("Promoter holding was broadly stable over the available three-year trend.")
    elif data.market in {"NSE","BSE"}:score+=5;flags.append("A usable three-year promoter-holding history was unavailable.")
    beneish=beneish_m_score(data) if methodology_for(data)[0]!="Financial institution" else None
    if beneish and beneish["flag"]:score+=15;flags.append(f"Beneish M-score is {beneish['score']:.2f}, above the {BENEISH_THRESHOLD} screening threshold; review revenue recognition, receivables, and accruals.")
    pledge=data.promoter_pledge
    if pledge is not None and 0<=pledge<=1:
        if pledge>=.25:score+=20;flags.append(f"Promoter pledge is high ({pledge:.1%} of promoter holding).")
        elif pledge>=.10:score+=10;flags.append(f"Promoter pledge is elevated ({pledge:.1%} of promoter holding).")
        elif pledge>0:score+=3;flags.append(f"Some promoter shares are pledged ({pledge:.1%} of promoter holding).")
        else:flags.append("No promoter pledge was reported in the reviewed source.")
    institutional=institutional_trend(data)
    if institutional is not None and institutional<=-.05:score+=5;flags.append(f"Combined FII and DII holding fell by {abs(institutional):.1%} over the available quarters.")
    if data.market in {"NSE","BSE"}:
        flags.append(("Related-party transactions" if pledge is not None else "Promoter pledging, related-party transactions")+", auditor qualifications, and contingent liabilities must be checked in NSE/BSE filings.")
    return max(0,min(100,int(round(score)))),flags


def order_book_assessment(data: StockData) -> tuple[int,list[str]]:
    """Score order-book coverage without assuming every announced order becomes revenue."""
    if not _valid_positive(data.order_book) or not data.revenue_history or not _valid_positive(data.revenue_history[0]):
        return 50,["Verified order-book coverage was unavailable; no order-book growth adjustment was applied."]
    coverage=float(data.order_book)/float(data.revenue_history[0]);flags=[f"Order book equals approximately {coverage:.2f}× latest annual revenue."]
    if coverage<.5:score=30
    elif coverage<1:score=45
    elif coverage<2:score=60
    elif coverage<=4:score=75
    else:score=70;flags.append("Very high order-book coverage may carry execution, cancellation, margin, concentration, and timing risk.")
    flags.append("Order book is not guaranteed revenue; verify executable orders, timing, margins, cancellations, and customer concentration in official filings.")
    return score,flags


def default_assumptions(data: StockData, context: Optional[ValuationContext] = None) -> Assumptions:
    is_india = data.market in {"NSE", "BSE"}
    context = context or build_context(data)
    profile, weights, _ = methodology_for(data)
    default_growth = 0.10 if is_india else 0.07
    ceiling = 0.20 if is_india else 0.16
    if profile in {"Cyclical / commodity", "Regulated / utility"}:
        ceiling = 0.10 if is_india else 0.08
        default_growth = 0.06 if is_india else 0.04
    # Base rates: very large companies rarely sustain high growth, so the ceiling tightens with size (₹ thresholds for Indian listings).
    size = _market_value(data) or 0.0
    large, mega = (5e11, 1e13) if is_india else (1e10, 2e11)
    if size >= mega:
        ceiling = min(ceiling, 0.13 if is_india else 0.10)
    elif size >= large:
        ceiling = min(ceiling, 0.16 if is_india else 0.13)
    components = growth_components(data, context)
    total_weight = sum(GROWTH_COMPONENT_WEIGHTS[name] for name in components)
    growth = sum(value * GROWTH_COMPONENT_WEIGHTS[name] for name, value in components.items()) / total_weight if total_weight else default_growth
    order_score,_=order_book_assessment(data)
    order_growth_adjustment=max(-.01,min(.015,(order_score-50)/25*.015)) if _valid_positive(data.order_book) else 0.0
    growth = min(max(growth+order_growth_adjustment, -0.05), ceiling)
    # Perpetual growth cannot outrun the risk-free rate; a shrinking business gets half the usual long-run rate.
    terminal = min(0.05 if is_india else 0.025, context.capital.risk_free_rate)
    revenue_trend = cagr(data.revenue_history)
    if revenue_trend is not None and revenue_trend < 0:
        terminal /= 2
    high_growth = competitive_advantage_years(data, context)
    return Assumptions(
        growth=growth,
        discount_rate=max(context.capital.wacc, terminal + 0.03),
        terminal_growth=terminal,
        years=max(10, high_growth + 5),
        dcf_weight=weights[0], graham_weight=weights[1], relative_weight=weights[2],
        margin_of_safety=0.20,
        high_growth_years=high_growth,
        scenario_weights=_scenario_weights(data),
    )


def scenario_assumptions(base: Assumptions) -> dict[str, Assumptions]:
    # Caps and floors never cross the base case, so reviewed values outside the usual range keep the scenario order.
    optimistic_rate = min(base.discount_rate, max(base.discount_rate - 0.015, base.terminal_growth + 0.025))
    return {
        "Conservative": replace(base, growth=min(base.growth, max(-0.08, base.growth - 0.04)), discount_rate=base.discount_rate + 0.02, terminal_growth=max(0.0, base.terminal_growth - 0.01)),
        "Base": base,
        "Optimistic": replace(base, growth=max(base.growth, min(0.25, base.growth + 0.04)), discount_rate=optimistic_rate, terminal_growth=max(base.terminal_growth, min(base.discount_rate - 0.025, base.terminal_growth + 0.0125))),
    }


def _growth_path(a: Assumptions):
    """Initial growth for the high-growth stage, then a linear fade to terminal growth by the final forecast year."""
    stage_one = max(1, min(a.high_growth_years, a.years))
    for year in range(1, a.years + 1):
        if year <= stage_one or a.years == stage_one:
            yield year, a.growth
        else:
            yield year, a.growth + (a.terminal_growth - a.growth) * ((year - stage_one) / (a.years - stage_one))


def _equity_dcf(data: StockData, a: Assumptions) -> tuple[Optional[float], Optional[float]]:
    if not (_valid_positive(data.free_cash_flow) and _valid_positive(data.shares)) or a.discount_rate <= a.terminal_growth:
        return None, None
    cash = data.free_cash_flow / data.shares
    pv = 0.0
    for year, year_growth in _growth_path(a):
        cash *= 1 + year_growth
        pv += cash / ((1 + a.discount_rate) ** year)
    terminal = cash * (1 + a.terminal_growth) / (a.discount_rate - a.terminal_growth) / ((1 + a.discount_rate) ** a.years)
    value = pv + terminal
    return (value, terminal / value) if _valid_positive(value) else (None, None)


def two_stage_dcf(data: StockData, a: Assumptions) -> Optional[float]:
    """Equity free-cash-flow DCF per share, used when operating-profit drivers are unavailable."""
    return _equity_dcf(data, a)[0]


def residual_income_value(data: StockData, a: Assumptions) -> Optional[float]:
    if not (_valid_positive(data.eps) and _valid_positive(data.book_value_per_share)) or a.discount_rate <= a.terminal_growth:
        return None
    book, eps, pv = data.book_value_per_share, data.eps, data.book_value_per_share
    payout = data.dividend_payout if data.dividend_payout is not None and 0 <= data.dividend_payout <= .9 else 0.35
    for year in range(1, a.years + 1):
        stage = max(1, min(a.high_growth_years, a.years))
        growth = a.growth if year <= stage else a.growth + (a.terminal_growth-a.growth)*((year-stage)/max(1,a.years-stage))
        eps *= 1 + growth
        excess = eps - a.discount_rate * book
        pv += excess / ((1+a.discount_rate)**year)
        book += max(0.0, eps * (1-payout))
    # Competition erodes excess returns: as in the FCFF terminal value, half of the final excess return survives in perpetuity.
    terminal_excess = .5 * max(0.0, eps*(1+a.terminal_growth) - a.discount_rate*book)
    pv += (terminal_excess/(a.discount_rate-a.terminal_growth))/((1+a.discount_rate)**a.years)
    return pv if _valid_positive(pv) else None


def asset_book_value(data: StockData) -> Optional[float]:
    if _valid_positive(data.book_value_per_share):return data.book_value_per_share*.80
    if _valid_positive(data.shares):
        net_cash=(data.cash or 0)-(data.total_debt or 0)
        if net_cash>0:return net_cash/data.shares
    return None


def financial_secondary_value(data: StockData, a: Assumptions) -> Optional[float]:
    metrics=data.financial_metrics
    if metrics and metrics.subtype=="Insurance" and _valid_positive(metrics.embedded_value_per_share):
        multiple=metrics.fair_price_to_embedded_value if _valid_positive(metrics.fair_price_to_embedded_value) else 1.0
        value=metrics.embedded_value_per_share*multiple
        return value if _valid_positive(value) else None
    if not _valid_positive(data.book_value_per_share):return None
    roe=metrics.reviewed_roe if metrics and metrics.reviewed_roe is not None else data.return_on_equity
    if roe is None and _valid_positive(data.eps):roe=data.eps/data.book_value_per_share
    if roe is None:return None
    growth=min(a.terminal_growth,max(-.02,roe-.01))
    if a.discount_rate<=growth:return None
    justified_pb=(roe-growth)/(a.discount_rate-growth);justified_pb=min(4.0,max(.4,justified_pb));value=data.book_value_per_share*justified_pb
    return value if _valid_positive(value) else None


def _terminal_return(drivers: Drivers, rate: float) -> float:
    """Return on new capital after the forecast: half of today's excess return survives, capped at 30%."""
    if drivers.roic is None:
        return rate
    return min(.30, max(rate, rate + .5 * (drivers.roic - rate)))


def enterprise_dcf(data: StockData, a: Assumptions, drivers: Drivers) -> tuple[Optional[float], Optional[float]]:
    """FCFF DCF at WACC; the terminal value pays for its own growth (g / RONIC reinvestment); equity = EV - net claims.

    Returns (value per share, terminal value share of enterprise value).
    """
    rate, g = a.discount_rate, a.terminal_growth
    convergence = drivers.basis == "Revenue DCF (margin convergence)"
    if rate <= g or not (_valid_positive(drivers.revenue) and _valid_positive(drivers.shares)):
        return None, None
    if not convergence and not (drivers.basis == "FCFF" and drivers.fcff_margin and drivers.fcff_margin > 0):
        return None, None
    revenue, pv, fcff = drivers.revenue, 0.0, 0.0
    for year, year_growth in _growth_path(a):
        revenue *= 1 + year_growth
        margin = drivers.current_margin + (drivers.target_margin - drivers.current_margin) * min(1.0, year / a.years) if convergence else drivers.fcff_margin
        fcff = revenue * margin
        pv += fcff / ((1 + rate) ** year)
    if convergence:
        terminal = revenue * (1 + g) * drivers.target_margin / (rate - g)
    elif drivers.nopat_margin and drivers.nopat_margin > 0:
        reinvestment = min(1.0, max(0.0, g / _terminal_return(drivers, rate)))
        terminal = revenue * (1 + g) * drivers.nopat_margin * (1 - reinvestment) / (rate - g)
    else:
        terminal = fcff * (1 + g) / (rate - g)
    terminal_pv = terminal / ((1 + rate) ** a.years)
    enterprise = pv + terminal_pv
    per_share = (enterprise - drivers.net_claims) / drivers.shares
    if enterprise <= 0 or not _valid_positive(per_share):
        return None, None
    return per_share, terminal_pv / enterprise


def earnings_power_value(data: StockData, a: Assumptions, drivers: Drivers, equity_spread: float = 0.0) -> Optional[float]:
    """Zero-growth value (Greenwald EPV): normalized after-tax operating profit ÷ cost of capital, less net claims."""
    if drivers.nopat_margin is not None and drivers.nopat_margin > 0 and _valid_positive(drivers.revenue) and _valid_positive(drivers.shares) and a.discount_rate > 0:
        value = (drivers.revenue * drivers.nopat_margin / a.discount_rate - drivers.net_claims) / drivers.shares
        return value if _valid_positive(value) else None
    rate = a.discount_rate + equity_spread
    if _valid_positive(data.eps) and rate > 0:
        value = data.eps / rate
        return value if _valid_positive(value) else None
    return None


def dividend_discount_value(data: StockData, a: Assumptions, equity_spread: float = 0.0) -> Optional[float]:
    """Two-stage dividend discount model at the cost of equity: normalized EPS × payout, growing on the forecast path."""
    payout = data.dividend_payout
    rate, g = a.discount_rate + equity_spread, a.terminal_growth
    if not (_valid_positive(data.eps) and payout is not None and 0 < payout <= 1) or rate <= g:
        return None
    dividend, pv = data.eps * payout, 0.0
    for year, year_growth in _growth_path(a):
        dividend *= 1 + year_growth
        pv += dividend / ((1 + rate) ** year)
    value = pv + dividend * (1 + g) / (rate - g) / ((1 + rate) ** a.years)
    return value if _valid_positive(value) else None


def relative_valuation(data: StockData, profile: str, drivers: Drivers, historical: dict) -> tuple[Optional[float], dict[str, float], str]:
    """Peer multiples adjusted for growth/ROE differences, blended 60/40 with the stock's own valuation history."""
    financial = profile in {"Financial institution", "Real estate / REIT"}
    components: dict[str, float] = {}
    own_growth = data.analyst_growth if data.analyst_growth is not None else data.growth_estimate
    growth_factor = 1.0 if own_growth is None or data.peer_median_growth is None else min(1.25, max(.8, 1 + 1.5 * (own_growth - data.peer_median_growth)))
    roe_factor = 1.0 if data.return_on_equity is None or data.peer_median_roe is None or data.peer_median_roe <= .02 else min(1.4, max(.7, data.return_on_equity / data.peer_median_roe))
    ebitda = data.ebitda if _valid_positive(data.ebitda) else None

    def from_enterprise_multiple(multiple):
        if not (_valid_positive(multiple) and ebitda and _valid_positive(drivers.shares)):
            return None
        value = (multiple * ebitda - drivers.net_claims) / drivers.shares
        return value if _valid_positive(value) else None

    def fitted(fit, driver, low, high):
        """Peer multiple read off the cross-peer line at the company's own driver, kept inside the peers' driver range."""
        if len(fit) != 4 or fit[1] <= 0 or driver is None:
            return None
        multiple = fit[0] + fit[1] * min(fit[3], max(fit[2], driver))
        return multiple if low <= multiple <= high else None

    # A regression across peers (P/E on growth, P/B on ROE) replaces the bounded median adjustment when five or more peers support it.
    pe_multiple = fitted(data.peer_pe_growth_fit, own_growth, 3, 80) or (data.peer_median_pe * growth_factor if _valid_positive(data.peer_median_pe) else None)
    if pe_multiple and _valid_positive(data.eps):
        components["Peer P/E"] = pe_multiple * data.eps
    pb_multiple = fitted(data.peer_pb_roe_fit, data.return_on_equity, .1, 15) or (data.peer_median_pb * roe_factor if _valid_positive(data.peer_median_pb) else None)
    if pb_multiple and _valid_positive(data.book_value_per_share):
        components["Peer P/B"] = pb_multiple * data.book_value_per_share
    if not financial:
        if _valid_positive(data.peer_median_forward_pe) and _valid_positive(data.forward_eps):
            components["Peer forward P/E"] = data.peer_median_forward_pe * data.forward_eps
        value = from_enterprise_multiple(data.peer_median_ev_ebitda)
        if value:
            components["Peer EV/EBITDA"] = value
        if not _valid_positive(data.eps) and _valid_positive(data.peer_median_ev_revenue) and _valid_positive(drivers.revenue) and _valid_positive(drivers.shares):
            # Loss-makers have no usable P/E, so growth-adjusted peer EV/Sales values the revenue base instead.
            value = (data.peer_median_ev_revenue * growth_factor * drivers.revenue - drivers.net_claims) / drivers.shares
            if value > 0:
                components["Peer EV/Sales"] = value
        if historical.get("pe") and _valid_positive(data.eps):
            components["Own P/E history"] = historical["pe"] * data.eps
        value = from_enterprise_multiple(historical.get("ev_ebitda"))
        if value:
            components["Own EV/EBITDA history"] = value
    elif historical.get("pb") and _valid_positive(data.book_value_per_share):
        components["Own P/B history"] = historical["pb"] * data.book_value_per_share
    if profile == "Real estate / REIT" and historical.get("p_ffo") and _valid_positive(drivers.shares):
        # REITs are priced on funds from operations (net income + depreciation), not on earnings.
        ffo = (value_at(series(data, "net_income"), 0) or 0.0) + (value_at(series(data, "depreciation"), 0) or 0.0)
        if ffo > 0:
            components["Own P/FFO history"] = historical["p_ffo"] * ffo / drivers.shares
    if financial:
        peer_keys = ["Peer P/B"] if "Peer P/B" in components else ["Peer P/E"] if "Peer P/E" in components else []
        label = "Peer P/B" if peer_keys == ["Peer P/B"] else "Peer P/E fallback" if peer_keys else ""
    else:
        peer_keys = [key for key in ("Peer P/E", "Peer forward P/E", "Peer EV/EBITDA", "Peer EV/Sales") if key in components]
        label = ("Peer P/E" if peer_keys == ["Peer P/E"] else "Peer multiples") if peer_keys else ""
        if not peer_keys and "Peer P/B" in components:
            peer_keys, label = ["Peer P/B"], "Peer P/B fallback"
    own_keys = [key for key in components if key.startswith("Own")]
    used = {key: components[key] for key in peer_keys + own_keys}
    peer = sum(components[key] for key in peer_keys) / len(peer_keys) if peer_keys else None
    own = sum(components[key] for key in own_keys) / len(own_keys) if own_keys else None
    if peer is not None and own is not None:
        return .6 * peer + .4 * own, used, label + " + own history"
    if peer is not None:
        return peer, used, label
    if own is not None:
        return own, used, "Own valuation history"
    return None, used, "Peer multiples"


def _blend(values: dict[str, Optional[float]], a: Assumptions) -> Optional[float]:
    weights = {"dcf": a.dcf_weight, "graham": a.graham_weight, "relative": a.relative_weight}
    usable = [(values[k], weights[k]) for k in values if _valid_positive(values[k]) and weights[k] > 0]
    total_weight = sum(w for _, w in usable)
    return sum(v*w for v,w in usable)/total_weight if total_weight > 0 else None  # type: ignore[operator]


def _primary_value(data: StockData, a: Assumptions, profile: str, context: ValuationContext) -> Optional[float]:
    if profile == "Financial institution":
        return residual_income_value(data, a)
    if context.drivers.basis == "Equity FCF":
        return two_stage_dcf(data, replace(a, discount_rate=a.discount_rate + context.equity_spread))
    return enterprise_dcf(data, a, context.drivers)[0]


def _secondary_value(data: StockData, a: Assumptions, profile: str, context: ValuationContext) -> Optional[float]:
    if profile == "Financial institution":
        return financial_secondary_value(data, a)
    # Regulated utilities pay out most earnings, so their dividends are the cash flow to value; zero-growth EPV understates them.
    dividends = dividend_discount_value(data, a, context.equity_spread) if profile == "Regulated / utility" else None
    return dividends or earnings_power_value(data, a, context.drivers, context.equity_spread) or asset_book_value(data)


def _terminal_share(data: StockData, a: Assumptions, profile: str, context: ValuationContext) -> Optional[float]:
    if profile == "Financial institution":
        return None
    if context.drivers.basis == "Equity FCF":
        return _equity_dcf(data, replace(a, discount_rate=a.discount_rate + context.equity_spread))[1]
    return enterprise_dcf(data, a, context.drivers)[1]


def forensic_summary(data: StockData, context: ValuationContext) -> dict:
    market = _market_value(data)
    roic = [x for x in context.drivers.roic_history if x is not None]
    roce = [x for x in (data.long_history or {}).get("roce", [])[:10] if x is not None]
    # Working-capital, distress, and manipulation screens assume an operating company; they are not meaningful for lenders.
    operating = context.profile != "Financial institution"
    earnings = owner_earnings(data) if operating else None
    return {
        "piotroski": piotroski_f_score(data) if operating else None,
        "altman": altman_z_score(data, market) if operating else None,
        "beneish": beneish_m_score(data) if operating else None,
        "roic_median": median(roic) if roic else context.drivers.roic,
        "roic_years": len(roic),
        "roce_median_10y": median(roce) if len(roce) >= 3 else None,
        "margin_stability": margin_stability(data) if operating else None,
        "cash_conversion_cycle": cash_conversion_cycle(data) if operating else None,
        "owner_earnings": earnings,
        "owner_earnings_per_share": earnings / data.shares if earnings is not None and _valid_positive(data.shares) else None,
        "owner_earnings_yield": earnings / market if earnings is not None and market else None,
        "capital_allocation": capital_allocation(data, market),
        "institutional_trend": institutional_trend(data),
        "promoter_pledge": data.promoter_pledge,
        "effective_tax_rate": context.tax_rate,
        "historical_multiples": context.historical,
    }


def reverse_dcf(data: StockData, base: Assumptions, profile: str, context: Optional[ValuationContext] = None) -> tuple[Optional[float],str]:
    """Solve for the initial growth rate that makes intrinsic primary value equal market price."""
    context = context or build_context(data)
    low,high=-0.15,0.50
    def calc(g):
        # A non-positive equity value (for example when net debt exceeds enterprise value) counts as zero, not missing.
        value=_primary_value(data,replace(base,growth=g),profile,context)
        return value if value is not None else 0.0
    lv,hv=calc(low),calc(high)
    if hv<=0:
        return None,"Reverse valuation unavailable because the primary model lacks required positive inputs."
    if data.price<min(lv,hv): return low,f"Market price is below the primary model even at {low:.0%} initial growth."
    if data.price>max(lv,hv): return None,f"Market price implies growth above the model search ceiling of {high:.0%}."
    for _ in range(60):
        mid=(low+high)/2; mv=calc(mid)
        if mv<data.price: low=mid
        else: high=mid
    implied=(low+high)/2
    stage=max(1,min(base.high_growth_years,base.years))
    return implied,f"The market price implies approximately {implied:.1%} annual initial growth for {stage} years, fading thereafter."


def implied_return(data: StockData, base: Assumptions, profile: str, context: ValuationContext) -> tuple[Optional[float], str]:
    """Annual return to shareholders that today's price implies if the primary model's cash flows arrive (its internal rate of return)."""
    def value(rate):
        # A non-positive equity value counts as zero, as in the reverse DCF.
        return _primary_value(data, replace(base, discount_rate=rate), profile, context) or 0.0
    low, high = base.terminal_growth + .005, .60
    if _primary_value(data, base, profile, context) is None:
        return None, "Implied return unavailable because the primary model lacks required positive inputs."
    if value(low) < data.price:
        return None, "Today's price is above the primary model's value even at the lowest usable discount rate, so the implied return is below long-run growth."
    if value(high) > data.price:
        return None, f"Today's price implies an annual return above {high:.0%}."
    for _ in range(60):
        mid = (low + high) / 2
        low, high = (mid, high) if value(mid) > data.price else (low, mid)
    rate, capital = (low + high) / 2, context.capital
    # The solved rate is the model's own discount rate: WACC for the firm-level DCF, which is converted back to a shareholder return.
    if profile == "Financial institution":
        equity = rate
    elif context.drivers.basis == "Equity FCF":
        equity = rate + context.equity_spread
    else:
        equity = (rate - capital.debt_weight * capital.pre_tax_cost_of_debt * (1 - capital.tax_rate)) / (1 - capital.debt_weight)
    return equity, f"At today's price the primary model implies about {equity:.1%} a year for shareholders, against the {capital.cost_of_equity:.1%} they require."


def sensitivity_table(data: StockData, base: Assumptions, profile: str, context: Optional[ValuationContext] = None) -> tuple[list[float],list[float],list[list[Optional[float]]]]:
    context = context or build_context(data)
    rates=[max(base.terminal_growth+.015,base.discount_rate+x) for x in (-.02,-.01,0,.01,.02)]
    terminals=[max(0,base.terminal_growth+x) for x in (-.01,-.005,0,.005,.01)]
    grid=[]
    for rate in rates:
        row=[]
        for terminal in terminals:
            if rate<=terminal+.005: row.append(None); continue
            a=replace(base,discount_rate=rate,terminal_growth=terminal)
            row.append(_blend({"dcf":_primary_value(data,a,profile,context),"graham":_secondary_value(data,a,profile,context),"relative":context.relative_value},a))
        grid.append(row)
    return rates,terminals,grid


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values: return 0.0
    position=(len(sorted_values)-1)*p
    low=int(position); high=min(low+1,len(sorted_values)-1); fraction=position-low
    return sorted_values[low]*(1-fraction)+sorted_values[high]*fraction


def monte_carlo_spreads(data: StockData, base: Assumptions, context: ValuationContext) -> dict[str, float]:
    """Company-specific Monte Carlo spreads from its own history; the old fixed spreads apply where history is too short.

    growth: year-to-year revenue growth volatility ÷ √(high-growth years), the uncertainty of a multi-year average;
    margin: coefficient of variation of the operating margin (FCF swings a third more); discount: Blume-adjusted beta
    standard error × equity risk premium plus 0.5 point of rate noise; correlation: revenue growth vs margin change.
    """
    # Aligned (revenue, operating margin) series, latest first: SEC 10-K history, Screener.in long history, or Yahoo statements, whichever is longest.
    def margins_of(revenue, ebit): return [e / r if e is not None and r and r > 0 else None for e, r in zip(ebit, revenue)]
    long = data.long_history or {}
    candidates = [(list(data.long_statements.get("revenue") or []), margins_of(data.long_statements.get("revenue") or [], data.long_statements.get("ebit") or [])),
                  (list(long.get("revenue") or []), list(long.get("ebit_margin") or [])),
                  (list(series(data, "revenue") or data.revenue_history), margins_of(series(data, "revenue"), series(data, "ebit")))]
    revenue, margin_path = max(candidates, key=lambda pair: sum(1 for value in pair[0] if value))
    def valid(index, values): return index < len(values) and values[index] is not None
    growths = [revenue[i] / revenue[i + 1] - 1 for i in range(len(revenue) - 1) if valid(i, revenue) and valid(i + 1, revenue) and revenue[i] > 0 and revenue[i + 1] > 0]
    pairs = [(revenue[i] / revenue[i + 1] - 1, margin_path[i] - margin_path[i + 1]) for i in range(min(len(revenue), len(margin_path)) - 1)
             if valid(i, revenue) and valid(i + 1, revenue) and valid(i, margin_path) and valid(i + 1, margin_path) and revenue[i] > 0 and revenue[i + 1] > 0]
    margins = [x for x in (long.get("ebit_margin") or margin_path)[:10] if x is not None]
    stage = max(1, min(base.high_growth_years, base.years))
    growth = min(.10, max(.02, pstdev(growths) / sqrt(stage))) if len(growths) >= 4 else max(.02, min(.06, abs(base.growth) * .30))
    mean_margin = sum(margins) / len(margins) if margins else 0.0
    margin = min(.35, max(.06, pstdev(margins) / abs(mean_margin))) if len(margins) >= 4 and mean_margin else .12
    beta_error = data.beta_standard_error if data.beta_standard_error is not None and isfinite(data.beta_standard_error) else .25
    # Beta estimation error, the equity premium's own uncertainty (about ±0.75 point), and rate noise.
    discount = min(.03, max(.008, sqrt((.67 * beta_error * context.capital.equity_risk_premium) ** 2 + (context.capital.beta * .0075) ** 2 + .005 ** 2)))
    try:
        rho = min(.8, max(0.0, correlation([x for x, _ in pairs], [y for _, y in pairs]))) if len(pairs) >= 6 else .5
    except StatisticsError:
        rho = .5
    return {"growth": growth, "margin": margin, "fcf": min(.45, margin * 4 / 3), "discount": discount, "correlation": rho, "history_years": len(growths)}


def monte_carlo_valuation(data: StockData, base: Assumptions, profile: str, context: Optional[ValuationContext] = None, iterations: int=2000, spreads: Optional[dict] = None) -> tuple[dict[str,float],Optional[float],Optional[float],list[float],list[int],int,int]:
    """Simulate valuation uncertainty with company-calibrated spreads; deterministic seed keeps a report reproducible."""
    context = context or build_context(data)
    spreads = spreads or monte_carlo_spreads(data, base, context)
    seed=int(hashlib.sha256(f"{data.symbol}|{data.data_timestamp[:10]}|phase3".encode()).hexdigest()[:16],16)
    rng=random.Random(seed); values=[]
    drivers=context.drivers;rho=spreads["correlation"];sigma_margin,sigma_fcf=spreads["margin"],spreads["fcf"]
    book_based=context.relative_label.startswith("Peer P/B") or (profile=="Financial institution" and context.relative_label=="Own valuation history")
    for _ in range(iterations):
        terminal=max(0.0,rng.gauss(base.terminal_growth,.006))
        discount=max(terminal+.015,rng.gauss(base.discount_rate,spreads["discount"]))
        # Faster growth tends to arrive with wider margins (operating leverage), so the two shocks share the company's correlation.
        growth_shock=rng.gauss(0,1);margin_shock=rho*growth_shock+sqrt(1-rho*rho)*rng.gauss(0,1)
        growth=max(-.15,min(.45,base.growth+spreads["growth"]*growth_shock))
        # Lognormal scale factors preserve sign and model uncertainty in normalized inputs, margins, and multiples.
        fcf_scale=exp(-.5*sigma_fcf**2+sigma_fcf*margin_shock); earnings_scale=exp(-.5*sigma_margin**2+sigma_margin*margin_shock); book_scale=exp(rng.gauss(-.5*.08**2,.08)); multiple_scale=exp(rng.gauss(-.5*.10**2,.10))
        simulated=replace(data,
            free_cash_flow=(data.free_cash_flow*fcf_scale if data.free_cash_flow is not None else None),
            eps=(data.eps*earnings_scale if data.eps is not None else None),
            book_value_per_share=(data.book_value_per_share*book_scale if data.book_value_per_share is not None else None))
        simulated_context=replace(context,drivers=replace(drivers,
            fcff_margin=(drivers.fcff_margin*fcf_scale if drivers.fcff_margin is not None else None),
            nopat_margin=(drivers.nopat_margin*earnings_scale if drivers.nopat_margin is not None else None),
            target_margin=(drivers.target_margin*fcf_scale if drivers.target_margin is not None else None)))
        relative=context.relative_value*(book_scale if book_based else earnings_scale)*multiple_scale if context.relative_value is not None else None
        a=replace(base,growth=growth,discount_rate=discount,terminal_growth=terminal)
        value=_blend({"dcf":_primary_value(simulated,a,profile,simulated_context),"graham":_secondary_value(simulated,a,profile,simulated_context),"relative":relative},a)
        if _valid_positive(value): values.append(float(value))
    if not values: return {},None,None,[],[],0,seed
    values.sort(); percentiles={f"P{int(p*100)}":_percentile(values,p) for p in (.10,.25,.50,.75,.90)}
    probability=sum(1 for v in values if v>data.price)/len(values)
    deviation=pstdev(values) if len(values)>1 else 0.0
    low,high=values[0],values[-1]; bins=12
    if high<=low: edges=[low,high]; counts=[len(values)]
    else:
        width=(high-low)/bins; edges=[low+i*width for i in range(bins+1)]; counts=[0]*bins
        for value in values: counts[min(bins-1,int((value-low)/width))]+=1
    return percentiles,probability,deviation,edges,counts,len(values),seed


def value_stock(data: StockData, assumptions: Optional[Assumptions] = None, automatic_assumptions: Optional[Assumptions] = None, assumption_note: str = "", assumption_preset: str = "Automatic defaults", parent_analysis_id: str = "", monte_carlo_iterations: int = 2000) -> ValuationResult:
    if not _valid_positive(data.price):raise ValueError("A positive market price is required for valuation.")
    context=build_context(data);profile=context.profile;drivers=context.drivers;capital=context.capital
    _, _, labels = methodology_for(data)
    automatic=automatic_assumptions or default_assumptions(data,context)
    base = assumptions or automatic
    if base.years<1 or base.years>20:raise ValueError("Forecast period must be between 1 and 20 years.")
    if base.discount_rate<=base.terminal_growth:raise ValueError("Discount rate must exceed terminal growth.")
    weights=(base.dcf_weight,base.graham_weight,base.relative_weight)
    if any(weight<0 for weight in weights) or sum(weights)<=0:raise ValueError("Model weights must be non-negative and have a positive total.")
    if base.high_growth_years<1:raise ValueError("High-growth years must be at least 1.")
    raw_weights=tuple(base.scenario_weights)
    if len(raw_weights)!=3 or any(weight<0 for weight in raw_weights) or sum(raw_weights)<=0:raise ValueError("Scenario weights must be three non-negative values with a positive total.")
    scenario_weights=[weight/sum(raw_weights) for weight in raw_weights]
    labels["dcf"]={"FCFF":"Mid-cycle FCFF DCF" if profile=="Cyclical / commodity" else "FCFF DCF (WACC)","Equity FCF":"Equity FCF DCF","Revenue DCF (margin convergence)":"Revenue DCF (margin convergence)","Residual income":"Residual income"}.get(drivers.basis,"FCFF DCF (WACC)")
    labels["relative"]=context.relative_label
    if profile=="Financial institution":
        labels["graham"]="Embedded value" if data.financial_metrics and data.financial_metrics.subtype=="Insurance" and _valid_positive(data.financial_metrics.embedded_value_per_share) else "Justified P/B"
    dividends_used=profile=="Regulated / utility" and dividend_discount_value(data,base,context.equity_spread) is not None
    if profile!="Financial institution":labels["graham"]="Dividend discount model" if dividends_used else "Earnings power value"
    scenarios: dict[str, ScenarioResult] = {}
    for name, a in scenario_assumptions(base).items():
        values = {"dcf": _primary_value(data,a,profile,context), "graham": _secondary_value(data,a,profile,context), "relative": context.relative_value}
        scenarios[name] = ScenarioResult(name, a.growth, a.discount_rate, a.terminal_growth, values["dcf"], values["graham"], values["relative"], _blend(values, a))
    base_fair = scenarios["Base"].fair_value
    if not _valid_positive(base_fair):
        raise ValueError("Fair value unavailable: the free sources supplied no usable positive cash flow, revenue-per-share fallback, book/net-cash floor, or peer-supported earnings/book input. Verify the ticker and filings; the app will not fabricate a value.")
    fallback_reasons=[]
    if profile!="Financial institution":
        if drivers.basis=="Revenue DCF (margin convergence)" and scenarios["Base"].dcf is not None:fallback_reasons.append(f"Positive normalized free cash flow was unavailable; revenue is projected with free-cash-flow margins converging from {drivers.current_margin:.1%} to a {drivers.target_margin:.0%} sector target.")
        if not dividends_used and earnings_power_value(data,base,drivers,context.equity_spread) is None and asset_book_value(data) is not None:labels["graham"]="Asset / book floor";fallback_reasons.append("Positive normalized operating earnings were unavailable; a conservative positive book-value or net-cash floor was used.")
        if context.relative_label.startswith("Peer P/B fallback"):fallback_reasons.append("Peer P/E was unusable; peer P/B was applied to positive book value.")
    scenario_values=[scenarios[name].fair_value for name in ("Conservative","Base","Optimistic")]
    fair=sum(weight*value for weight,value in zip(scenario_weights,scenario_values)) if all(_valid_positive(value) for value in scenario_values) else base_fair
    notes: list[str] = ["Cash flow and earnings inputs are normalized as latest revenue × median multi-year margin; stock-based compensation is deducted from free cash flow."]

    base_values=[x for x in (scenarios["Base"].dcf,scenarios["Base"].graham,scenarios["Base"].relative) if _valid_positive(x)]
    available=len(base_values)
    risk_score,risk_flags=context.risk_score,list(context.risk_flags)
    quality_score,quality_flags=data_quality_assessment(data)
    terminal_share=_terminal_share(data,base,profile,context)
    if terminal_share is not None and terminal_share>.75:quality_flags.append(f"Terminal value is {terminal_share:.0%} of the primary model's value; the estimate depends heavily on long-run assumptions.")
    dispersion=None
    if len(base_values)>=2:
        dispersion=(max(base_values)-min(base_values))/median(base_values)
    dynamic_margin=base.margin_of_safety
    dynamic_margin += max(0,risk_score-30)/70*0.12
    dynamic_margin += max(0,75-quality_score)/75*0.10
    if dispersion is not None: dynamic_margin += min(0.10,dispersion*0.08)
    if profile == "Cyclical / commodity": dynamic_margin += 0.05
    if terminal_share is not None and terminal_share>.75: dynamic_margin += 0.02
    dynamic_margin=max(0.15,min(0.50,dynamic_margin))

    business_score,business_flags=business_quality_assessment(data,base.discount_rate)
    governance_score,governance_flags=context.governance_score,list(context.governance_flags);order_score,order_flags=order_book_assessment(data)
    dynamic_margin += max(0,50-business_score)/50*0.04
    if _valid_positive(data.order_book):dynamic_margin += max(0,50-order_score)/50*.02
    dynamic_margin += max(0,governance_score-35)/65*0.04
    dynamic_margin=max(0.15,min(0.50,dynamic_margin));fallback_used=bool(fallback_reasons)
    if fallback_used:dynamic_margin=max(dynamic_margin,.35)
    agreement_score=100-min(100,(dispersion if dispersion is not None else .75)*100)
    completeness=available/3*100
    confidence_points=int(round(quality_score*.30+agreement_score*.20+(100-risk_score)*.15+business_score*.15+(100-governance_score)*.10+completeness*.10))
    if terminal_share is not None and terminal_share>.75:confidence_points-=5
    if fallback_used:confidence_points=min(confidence_points,49)
    confidence_points=max(0,min(100,confidence_points))
    confidence="Higher" if confidence_points>=75 else "Moderate" if confidence_points>=50 else "Low"
    implied_growth,reverse_note=reverse_dcf(data,base,profile,context)
    history_growth=cagr(data.revenue_history)
    if implied_growth is not None and history_growth is not None:reverse_note+=f" For comparison, revenue grew {history_growth:.1%} a year over the reported history."
    shareholder_return,return_note=implied_return(data,base,profile,context)
    sensitivity_rates,sensitivity_terms,sensitivity_values=sensitivity_table(data,base,profile,context)
    spreads=monte_carlo_spreads(data,base,context)
    mc_percentiles,mc_probability,mc_std,mc_edges,mc_counts,mc_iterations,mc_seed=monte_carlo_valuation(data,base,profile,context,monte_carlo_iterations,spreads)
    growth_parts=growth_components(data,context);forensic=forensic_summary(data,context)
    notes.append(f"Monte Carlo spreads are calibrated to this company ({spreads['history_years']} years of revenue history): initial growth ±{spreads['growth']:.1%}, operating margin ±{spreads['margin']:.0%}, discount rate ±{spreads['discount']:.2%}, growth–margin correlation {spreads['correlation']:.2f}.")
    notes.append(return_note)
    if scenarios["Base"].dcf is None: notes.append(f"{labels['dcf']} was excluded because required positive inputs were unavailable.")
    if scenarios["Base"].graham is None: notes.append(f"{labels['graham']} was excluded because required positive earnings/book or embedded-value inputs were unavailable.")
    if scenarios["Base"].relative is None: notes.append(f"{labels['relative']} was excluded because a usable peer median or company input was unavailable.")
    if fallback_used:notes.extend(fallback_reasons);notes.append("Fallback valuation is a low-confidence heuristic, not a substitute for normalized earnings or cash-flow analysis and not a guarantee against loss.")
    notes.append("Available model weights are automatically re-normalized when a model cannot be calculated.")
    rate_name="Cost of equity" if profile=="Financial institution" else "WACC"
    notes.append(f"{rate_name} {capital.wacc:.2%}: risk-free {capital.risk_free_rate:.2%} ({capital.risk_free_source}) + beta {capital.beta:.2f} ({capital.beta_source}) × equity risk premium {capital.equity_risk_premium:.2%} + company-specific premium {capital.company_risk_premium:.2%}"+(f"; debt weight {capital.debt_weight:.0%} at {capital.pre_tax_cost_of_debt:.2%} pre-tax ({capital.debt_rating} synthetic rating from interest coverage)." if capital.debt_weight>0 else "."))
    notes.append(f"Terminal growth is {base.terminal_growth:.2%}: capped at the risk-free rate and halved when revenue has been shrinking.")
    if drivers.research_margin:notes.append(f"R&D is treated as investment amortized over five years: NOPAT adds back {drivers.research_margin:.1%} of revenue and invested capital includes the research asset.")
    for fit,key,driver in ((data.peer_pe_growth_fit,"Peer P/E","growth"),(data.peer_pb_roe_fit,"Peer P/B","ROE")):
        if len(fit)==4 and fit[1]>0 and key in context.relative_components:notes.append(f"{key} is read from a least-squares line of the multiple against {driver} across screened peers, not the plain median.")
    if dividends_used:notes.append(f"The secondary model is a dividend discount model at the cost of equity using a {data.dividend_payout:.0%} payout of normalized earnings.")
    if drivers.basis=="FCFF":notes.append(f"FCFF margin {drivers.fcff_margin:.1%} and NOPAT margin {drivers.nopat_margin:.1%} are applied to latest revenue; equity value deducts net debt, minority interest, and credits cash and investments.")
    if drivers.margin_note:notes.append(drivers.margin_note)
    notes.append(f"High-growth stage lasts {max(1,min(base.high_growth_years,base.years))} of {base.years} forecast years, set from how consistently ROIC exceeded the cost of capital; terminal value deducts the reinvestment needed for terminal growth.")
    if growth_parts:notes.append("Initial growth blends "+", ".join(f"{name} {value:.1%}" for name,value in growth_parts.items())+" (weights 40/30/30, re-normalized when a source is missing).")
    notes.append(f"Fair value is probability-weighted across scenarios ({scenario_weights[0]:.0%} conservative / {scenario_weights[1]:.0%} base / {scenario_weights[2]:.0%} optimistic); the base-case value is {base_fair:,.2f}.")
    notes.append(f"Governance risk is incorporated into the automatic discount rate; verified order-book coverage can adjust initial growth by at most +1.5 or -1.0 percentage points. Promoter-holding trend contributes to governance risk. Current automatic discount rate: {automatic.discount_rate:.2%}; order-book score: {order_score}/100.")
    notes.append(f"Dynamic valuation buffer is {dynamic_margin:.0%} versus the {base.margin_of_safety:.0%} minimum after financial, quality, governance, order-book, data, sector, and model-disagreement adjustments. This buffer does not guarantee protection from loss.")

    fair=float(fair); ratio=data.price/fair
    if ratio <= 1-dynamic_margin: label="Below valuation-buffer threshold"
    elif ratio <= 1: label="Below estimated fair value — buffer threshold not met"
    elif ratio <= 1.2: label="Near estimated fair value"
    else: label="Above estimated fair value"
    if fallback_used:label="Fallback valuation — high uncertainty • "+label
    override_fields=("growth","discount_rate","terminal_growth","years","high_growth_years","dcf_weight","graham_weight","relative_weight","margin_of_safety")
    manual_overrides={name:(getattr(automatic,name),getattr(base,name)) for name in override_fields if abs(float(getattr(automatic,name))-float(getattr(base,name)))>1e-9}
    created_at=datetime.now(timezone.utc).isoformat();analysis_id=f"FS-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:12].upper()}"
    def audit_event(stage,action,details):return AuditEvent(created_at,stage,action,{str(key):str(value) for key,value in details.items()})
    base_scenario=scenarios["Base"];excluded=[labels[key] for key,value in (("dcf",base_scenario.dcf),("graham",base_scenario.graham),("relative",base_scenario.relative)) if value is None]
    driver_record={key:value for key,value in asdict(drivers).items() if key!="roic_history"}|{"roic_history":json.dumps(drivers.roic_history)}
    events=[
        audit_event("Identity","Analysis created",{"analysis_id":analysis_id,"parent_analysis_id":parent_analysis_id or "None","app_version":APP_VERSION,"model_version":MODEL_VERSION,"audit_schema":AUDIT_SCHEMA_VERSION}),
        audit_event("Data","Source snapshot",{"symbol":data.symbol,"sources":", ".join(data.data_sources or [data.data_provider]),"source_updated":data.source_updated_date,"retrieved":data.data_timestamp,"lineage_records":len(data.lineage),"discrepancies":len(data.source_discrepancies),"external_reviews":len(data.external_reviews),"cache_status":data.cache_status,"cache_age_hours":data.cache_age_hours,"is_stale":data.is_stale}),
        audit_event("Methodology","Profile selected",{"profile":profile,"primary_model":labels.get("dcf",""),"secondary_model":labels.get("graham",""),"peer_model":labels.get("relative","")}),
        audit_event("Specialized financials","Financial-company metrics recorded",{"applicable":profile=="Financial institution","metrics":json.dumps(asdict(data.financial_metrics),sort_keys=True) if data.financial_metrics else "None"}),
        audit_event("Normalization","Historical inputs normalized",{"fcf_observations":len(data.fcf_history),"revenue_observations":len(data.revenue_history),"income_observations":len(data.net_income_history),"normalized_fcf":data.free_cash_flow,"normalized_eps":data.eps,"book_value_per_share":data.book_value_per_share,"order_book":data.order_book,"order_book_score":order_score,"promoter_holding_observations":len(data.promoter_holding_history)}),
        audit_event("Cost of capital","Discount rate derived",asdict(capital)),
        audit_event("Drivers","Operating drivers normalized",driver_record),
        audit_event("Assumptions","Automatic baseline recorded",asdict(automatic)|{"growth_components":json.dumps(growth_parts,sort_keys=True)}),
        audit_event("Assumptions","Reviewed assumptions accepted",{"preset":assumption_preset,"override_count":len(manual_overrides),"overrides":json.dumps(manual_overrides,sort_keys=True),"reviewer_note":assumption_note.strip() or "None",**{key:value for key,value in asdict(base).items()}}),
        audit_event("Models","Base models executed",{"primary":base_scenario.dcf,"secondary":base_scenario.graham,"relative":base_scenario.relative,"blended":base_scenario.fair_value,"terminal_value_share":terminal_share,"excluded_models":", ".join(excluded) or "None","peer_symbols":", ".join(data.peer_symbols) or "None","fallback_used":fallback_used,"fallback_reasons":" | ".join(fallback_reasons) or "None"}),
        audit_event("Relative valuation","Peer and own-history components",{"label":context.relative_label,"components":json.dumps(context.relative_components,sort_keys=True),"historical_multiples":json.dumps(context.historical,sort_keys=True)}),
        audit_event("Scenarios","Scenario values calculated",{**{name:scenario.fair_value for name,scenario in scenarios.items()},"weights":json.dumps(scenario_weights),"probability_weighted":fair}),
        audit_event("Forensic","Quality and forensic scores",{"scores":json.dumps(forensic,sort_keys=True,default=str)}),
        audit_event("Risk","Scores and valuation buffer calculated",{"financial_risk":risk_score,"data_quality":quality_score,"business_quality":business_score,"governance_risk":governance_score,"order_book_score":order_score,"confidence":confidence_points,"dynamic_margin":dynamic_margin,"model_dispersion":dispersion,"automatic_discount_rate":automatic.discount_rate,"automatic_growth":automatic.growth}),
        audit_event("Sensitivity","Sensitivity grid calculated",{"discount_rates":json.dumps(sensitivity_rates),"terminal_growth_rates":json.dumps(sensitivity_terms),"cells":sum(len(row) for row in sensitivity_values)}),
        audit_event("Monte Carlo","Simulation completed",{"seed":mc_seed,"requested_iterations":monte_carlo_iterations,"successful_iterations":mc_iterations,"spreads":json.dumps(spreads,sort_keys=True),"implied_shareholder_return":shareholder_return,"percentiles":json.dumps(mc_percentiles,sort_keys=True),"probability_fair_value_above_price":mc_probability}),
        audit_event("Decision","Final estimate recorded",{"market_price":data.price,"fair_value":fair,"base_fair_value":base_fair,"upside_pct":(fair/data.price-1)*100,"mos_price":fair*(1-dynamic_margin),"assessment":label}),
    ]
    result_obj=ValuationResult(data=data,base_assumptions=base,scenarios=scenarios,fair_value=fair,upside_pct=(fair/data.price-1)*100,
        margin_price=fair*(1-dynamic_margin),label=label,confidence=confidence,model_notes=notes,model_labels=labels,
        methodology_profile=profile,risk_score=risk_score,data_quality_score=quality_score,risk_flags=risk_flags,
        quality_flags=quality_flags,dynamic_margin=dynamic_margin,model_dispersion=dispersion,business_quality_score=business_score,
        governance_risk_score=governance_score,order_book_score=order_score,confidence_score=confidence_points,business_quality_flags=business_flags,order_book_flags=order_flags,
        governance_flags=governance_flags,reverse_dcf_growth=implied_growth,reverse_dcf_note=reverse_note,
        sensitivity_discount_rates=sensitivity_rates,sensitivity_terminal_growths=sensitivity_terms,sensitivity_values=sensitivity_values,
        monte_carlo_iterations=mc_iterations,monte_carlo_percentiles=mc_percentiles,monte_carlo_probability_above_price=mc_probability,
        monte_carlo_std=mc_std,monte_carlo_bin_edges=mc_edges,monte_carlo_bin_counts=mc_counts,
        automatic_assumptions=automatic,manual_overrides=manual_overrides,assumption_note=assumption_note.strip(),assumption_preset=assumption_preset,
        analysis_id=analysis_id,parent_analysis_id=parent_analysis_id,created_at=created_at,app_version=APP_VERSION,model_version=MODEL_VERSION,audit_schema_version=AUDIT_SCHEMA_VERSION,monte_carlo_seed=mc_seed,audit_events=events,fallback_valuation=fallback_used,fallback_reasons=fallback_reasons,
        base_fair_value=base_fair,scenario_weights=scenario_weights,cost_of_capital=asdict(capital),valuation_drivers=asdict(drivers),relative_components=dict(context.relative_components),
        growth_components=growth_parts,terminal_value_share=terminal_share,forensic_scores=forensic,monte_carlo_spreads=spreads,implied_return=shareholder_return,implied_return_note=return_note)
    result_obj.audit_hash=compute_audit_hash(result_obj)
    return result_obj


def audit_record(result: ValuationResult, include_hash: bool = True) -> dict:
    record={
        "analysis_id":result.analysis_id,"parent_analysis_id":result.parent_analysis_id or None,"created_at":result.created_at,
        "app_version":result.app_version,"model_version":result.model_version,"audit_schema_version":result.audit_schema_version,
        "symbol":result.data.symbol,"company":result.data.company,"market":result.data.market,"currency":result.data.currency,
        "data_sources":result.data.data_sources or [result.data.data_provider],"source_updated_date":result.data.source_updated_date,"retrieved_at":result.data.data_timestamp,"cache_status":result.data.cache_status,"cache_age_hours":result.data.cache_age_hours,"is_stale":result.data.is_stale,
        "source_checks":result.data.source_checks,"source_discrepancies":result.data.source_discrepancies,"data_lineage":[asdict(entry) for entry in result.data.lineage],
        "financial_company_metrics":asdict(result.data.financial_metrics) if result.data.financial_metrics else None,"external_reviews":result.data.external_reviews,
        "automatic_assumptions":asdict(result.automatic_assumptions) if result.automatic_assumptions else None,"reviewed_assumptions":asdict(result.base_assumptions),
        "manual_overrides":result.manual_overrides,"assumption_preset":result.assumption_preset,"assumption_note":result.assumption_note,
        "methodology_profile":result.methodology_profile,"model_labels":result.model_labels,"model_notes":result.model_notes,
        "peer_symbols":result.data.peer_symbols,"scenario_results":{name:asdict(scenario) for name,scenario in result.scenarios.items()},
        "fair_value":result.fair_value,"market_price":result.data.price,"upside_pct":result.upside_pct,"margin_price":result.margin_price,"dynamic_margin":result.dynamic_margin,"assessment":result.label,"fallback_valuation":result.fallback_valuation,"fallback_reasons":result.fallback_reasons,
        "risk_score":result.risk_score,"data_quality_score":result.data_quality_score,"business_quality_score":result.business_quality_score,"governance_risk_score":result.governance_risk_score,"order_book_score":result.order_book_score,"confidence_score":result.confidence_score,
        "order_book":result.data.order_book,"order_book_period":result.data.order_book_period,"order_book_source":result.data.order_book_source,"promoter_holding_history":result.data.promoter_holding_history,"promoter_holding_periods":result.data.promoter_holding_periods,
        "monte_carlo_seed":result.monte_carlo_seed,"monte_carlo_iterations":result.monte_carlo_iterations,"monte_carlo_percentiles":result.monte_carlo_percentiles,
        "audit_events":[asdict(event) for event in result.audit_events],
        "base_fair_value":result.base_fair_value,"scenario_weights":result.scenario_weights,"cost_of_capital":result.cost_of_capital,"valuation_drivers":result.valuation_drivers,
        "relative_components":result.relative_components,"growth_components":result.growth_components,"terminal_value_share":result.terminal_value_share,"forensic_scores":result.forensic_scores,"monte_carlo_spreads":result.monte_carlo_spreads,"implied_return":result.implied_return,
    }
    if include_hash:record["audit_hash"]=result.audit_hash
    return record


def compute_audit_hash(result: ValuationResult) -> str:
    canonical=json.dumps(audit_record(result,include_hash=False),sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_audit_hash(result: ValuationResult) -> bool:
    return bool(result.audit_hash) and compute_audit_hash(result)==result.audit_hash
