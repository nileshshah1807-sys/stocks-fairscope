"""Browser version of the FairScope valuation for one ticker (Streamlit). Watchlists, history, batch, and backtests stay in the desktop app."""
from __future__ import annotations

import os
import tempfile

import pandas as pd
import streamlit as st

from data_provider import DataProviderError, fetch_stock
from pdf_report import create_pdf
from valuation import ValuationResult, value_stock
from version import APP_VERSION, MODEL_VERSION

st.set_page_config(page_title="Stocks FairScope", layout="wide")


@st.cache_data(ttl=3600, show_spinner=False, max_entries=200)
def analyze(symbol: str, market: str) -> ValuationResult:
    # One hour of caching per ticker keeps repeat visits from re-querying Yahoo, which rate-limits shared cloud addresses.
    return value_stock(fetch_stock(symbol, market))


def money(value, currency):
    return "—" if value is None else f"{currency} {value:,.2f}"


@st.cache_data(max_entries=50, show_spinner=False)
def pdf_bytes(analysis_id: str, _result: ValuationResult) -> bytes:
    # Keyed by analysis ID (the leading underscore stops Streamlit hashing the whole result), so reruns don't rebuild the PDF.
    result = _result
    handle = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    handle.close()
    try:
        create_pdf(result, handle.name)
        with open(handle.name, "rb") as stream:
            return stream.read()
    finally:
        os.unlink(handle.name)


st.title("Stocks FairScope")
st.caption(f"DR. NILESH SHAH • {MODEL_VERSION} • v{APP_VERSION} • Educational fair-value estimate, not investment advice • Free Yahoo / Screener.in / NSE / BSE data can be delayed or unavailable")

with st.form("analyze"):
    market_column, symbol_column, button_column = st.columns([1, 3, 1])
    market = market_column.selectbox("Market", ["US", "NSE", "BSE"])
    symbol = symbol_column.text_input("Ticker", value="AAPL", help="Exchange suffixes are added automatically, e.g. RELIANCE on NSE.")
    button_column.write("")
    submitted = button_column.form_submit_button("Analyze", type="primary", width="stretch")

if submitted and symbol.strip():
    with st.spinner(f"Retrieving data and valuing {symbol.strip().upper()}…"):
        try:
            st.session_state["result"] = analyze(symbol.strip().upper(), market)
        except (DataProviderError, ValueError) as exc:
            st.session_state.pop("result", None)
            st.error(str(exc))

result: ValuationResult | None = st.session_state.get("result")
if result:
    data, currency = result.data, result.data.currency
    st.subheader(f"{data.company} · {data.symbol}")
    st.caption(f"{data.market} • {data.sector} • {data.industry} • {result.methodology_profile} • data: {data.data_provider}")
    required = (result.cost_of_capital or {}).get("cost_of_equity")
    price, fair, upside, buffer, implied = st.columns(5)
    price.metric("Market price", money(data.price, currency))
    fair.metric("Fair value (weighted)", money(result.fair_value, currency))
    upside.metric("Upside / downside", f"{result.upside_pct:+.1f}%")
    buffer.metric(f"Buffer price ({result.dynamic_margin:.0%})", money(result.margin_price, currency))
    implied.metric("Implied return / year", "—" if result.implied_return is None else f"{result.implied_return:.1%}",
                   None if result.implied_return is None or required is None else f"{(result.implied_return - required) * 100:+.1f} pts vs {required:.1%} required")
    (st.success if result.upside_pct >= 0 else st.warning)(f"{result.label} • Confidence {result.confidence_score}/100 • Financial risk {result.risk_score}/100 • Governance risk {result.governance_risk_score}/100")

    left, right = st.columns([3, 2])
    with left:
        if len(data.price_history) >= 2:
            index = pd.to_datetime(data.price_dates) if len(data.price_dates) == len(data.price_history) else range(len(data.price_history))
            st.markdown("**One-year price vs today's fair value and buffer price**")
            st.line_chart(pd.DataFrame({"Price": data.price_history, "Fair value": result.fair_value, "Buffer price": result.margin_price}, index=index))
    with right:
        labels = result.model_labels
        st.markdown("**Scenarios**")
        st.dataframe(pd.DataFrame([{"Scenario": scenario.name, "Growth": f"{scenario.growth:.1%}", "Discount": f"{scenario.discount_rate:.1%}",
                                    labels.get("dcf", "Primary"): money(scenario.dcf, currency), labels.get("graham", "Secondary"): money(scenario.graham, currency),
                                    labels.get("relative", "Peers"): money(scenario.relative, currency), "Blended": money(scenario.fair_value, currency)}
                                   for scenario in result.scenarios.values()]), hide_index=True, width="stretch")
        percentiles = result.monte_carlo_percentiles
        if percentiles:
            st.markdown("**Monte Carlo fair-value range**")
            st.dataframe(pd.DataFrame([{key: money(value, currency) for key, value in percentiles.items()}]), hide_index=True, width="stretch")
            if result.monte_carlo_probability_above_price is not None:
                st.caption(f"{result.monte_carlo_probability_above_price:.0%} of simulations put fair value above today's price. Model uncertainty, not a return forecast.")

    with st.expander("How the estimate was built"):
        for note in result.model_notes:
            st.markdown(f"- {note}")
    with st.expander("Risks and data-quality flags"):
        for flag in result.risk_flags + result.quality_flags + result.governance_flags + data.warnings:
            st.markdown(f"- {flag}")
    with st.expander("Data sources and lineage"):
        st.dataframe(pd.DataFrame([{"Metric": entry.metric, "Value": entry.value, "Source": entry.source, "Period": entry.period, "Status": entry.status, "URL": entry.source_url}
                                   for entry in data.lineage]), hide_index=True, width="stretch")
    st.download_button("Download full PDF report", data=pdf_bytes(result.analysis_id, result), file_name=f"{data.symbol.replace('.', '_')}_Fair_Value_Report.pdf", mime="application/pdf")

st.caption("For education and research only. No valuation makes investing safe. Verify figures against official filings and consult a registered adviser.")
