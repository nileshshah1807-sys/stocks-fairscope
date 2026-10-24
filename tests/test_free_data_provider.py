import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import data_provider
from data_provider import PROVIDER_NAME, normalize_symbol
from india_sources import IndiaSourceResult
from local_database import LocalDatabase

YEARS=["2025-12-31","2024-12-31","2023-12-31","2022-12-31"]
EMPTY_PEERS={"pe":None,"pb":None,"forward_pe":None,"ev_ebitda":None,"roe":None,"growth":None,"symbols":()}

def statement(rows):
    """Yahoo layout: line items as rows, fiscal year-ends as columns (latest first); None becomes NaN."""
    import pandas as pd
    return pd.DataFrame(rows,index=pd.to_datetime(YEARS)).T

def fake_yfinance(info,income=None,cashflow=None,balance=None,fx=None):
    """Offline stand-in for yfinance; an Exception passed as info is raised by the profile call, and FX pairs (=X) quote fx."""
    import pandas as pd
    def prices(value):return pd.DataFrame({"Close":[value]*30,"Adj Close":[value]*30,"High":[value]*30,"Low":[value]*30},index=pd.date_range("2025-01-01",periods=30,freq="D"))
    class Ticker:
        quarterly_cashflow=quarterly_income_stmt=growth_estimates=None
        def __init__(self,symbol):self.symbol=symbol;self.income_stmt,self.cashflow,self.balance_sheet=income,cashflow,balance
        def history(self,*args,**kwargs):
            if self.symbol.endswith("=X"):return prices(fx) if fx else pd.DataFrame()
            return prices(100.0)
        @property
        def info(self):
            if isinstance(info,Exception):raise info
            return info
        def get_shares_full(self,**kwargs):raise RuntimeError("unavailable")
    return types.SimpleNamespace(Ticker=Ticker)


class FreeDataProviderTests(unittest.TestCase):
    def test_no_key_symbol_mapping(self):
        self.assertEqual(normalize_symbol("aapl","US"),"AAPL")
        self.assertEqual(normalize_symbol("reliance","NSE"),"RELIANCE.NS")
        self.assertEqual(normalize_symbol("500325","BSE"),"500325.BO")
        self.assertEqual(normalize_symbol("reliance.nse","NSE"),"RELIANCE.NS")
        self.assertEqual(normalize_symbol("BRK.B","US"),"BRK-B")
    def test_provider_disclosure(self):
        self.assertIn("Yahoo Finance",PROVIDER_NAME)
        self.assertIn("free",PROVIDER_NAME.lower())


class StockLoaderTests(unittest.TestCase):
    def fetch(self,yf,symbol="TEST",market="US",verification=None,sec=None):
        data_provider._fx_rate.cache_clear()
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);database=LocalDatabase(handle.name);self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name));self.addCleanup(database.close)
        with patch.dict(sys.modules,{"yfinance":yf}),patch.object(data_provider,"_fetch_peers",return_value=EMPTY_PEERS),patch.object(data_provider,"_index_monthly",return_value={}),patch.object(data_provider,"verify_indian_stock",return_value=verification),patch.object(data_provider,"_sec_history",return_value=sec):
            try:return data_provider._fetch_stock(symbol,market,database,True,False),database
            except data_provider.DataProviderError as exc:return exc,database

    def test_us_statements_become_normalized_inputs(self):
        income=statement({"Total Revenue":[1000,900,800,700],"Net Income":[100,90,80,70],"EBIT":[150,135,120,105]})
        # No Free Cash Flow row and a blank 2024 capex: each year's operating cash flow must meet that year's (negative) capex.
        cashflow=statement({"Operating Cash Flow":[130,120,110,100],"Capital Expenditure":[-30,None,-25,-20],"Stock Based Compensation":[10,10,10,10]})
        data,database=self.fetch(fake_yfinance({"sharesOutstanding":100,"sector":"Technology","currency":"USD","longName":"Test Corp"},income,cashflow))
        self.assertEqual(data.shares,100);self.assertEqual(data.fcf_history,[100,85,80]);self.assertEqual(data.revenue_history,[1000,900,800,700])
        self.assertAlmostEqual(data.free_cash_flow,93.75)  # latest revenue × median FCF margin after stock-based compensation
        self.assertAlmostEqual(data.eps,1.0);self.assertAlmostEqual(data.growth_estimate,(1000/700)**(1/3)-1)
        self.assertIsNotNone(database.load_stock("TEST","US"))

    def test_indian_exchange_price_and_screener_crore_values_win(self):
        verification=IndiaSourceResult(exchange_price=102.0,exchange_name="NSE India",exchange_timestamp="17-Oct-2026 15:30",exchange_url="https://www.nseindia.com/get-quotes/equity?symbol=TEST",screener_ratios={"Market Cap":500.0,"Book Value":40.0},screener_url="https://www.screener.in/company/TEST/",sources_checked=["Screener.in","NSE India"])
        data,_database=self.fetch(fake_yfinance({"sharesOutstanding":100,"sector":"Industrials","currency":"INR","marketCap":1.0}),"TEST.NS","NSE",verification)
        self.assertEqual(data.price,102.0);self.assertEqual(data.market_cap,500*10_000_000);self.assertEqual(data.book_value_per_share,40.0);self.assertAlmostEqual(data.price_to_book,102/40)

    def test_foreign_listing_is_converted_to_trading_currency(self):
        # TSM-style ADR: statements in TWD, quote in USD; Yahoo's book value and price/book mix units.
        income=statement({"Total Revenue":[1000,900,800,700],"Net Income":[100,90,80,70],"Diluted Average Shares":[500,500,500,500],"Tax Rate For Calcs":[.2,.2,.2,.2]})
        info={"currency":"USD","financialCurrency":"TWD","sharesOutstanding":999,"marketCap":10_000.0,"bookValue":5.2,"priceToBook":79.9,"totalDebt":300.0,"sector":"Technology"}
        data,_database=self.fetch(fake_yfinance(info,income,fx=.03))
        self.assertAlmostEqual(data.revenue_history[0],30.0);self.assertAlmostEqual(data.total_debt,9.0);self.assertEqual(data.shares,100.0)  # market cap ÷ price
        self.assertEqual(data.statements["diluted_shares"][0],500);self.assertAlmostEqual(data.statements["tax_rate"][0],.2)
        self.assertAlmostEqual(data.eps,.03);self.assertIsNone(data.book_value_per_share);self.assertIsNone(data.price_to_book)
        self.assertTrue(any(entry.metric=="Currency conversion" for entry in data.lineage))

    def test_foreign_listing_without_fx_rate_is_refused(self):
        info={"currency":"USD","financialCurrency":"TWD","marketCap":10_000.0,"sector":"Technology"}
        outcome,_database=self.fetch(fake_yfinance(info,statement({"Total Revenue":[1000,900,800,700]})))
        self.assertIsInstance(outcome,data_provider.DataProviderError);self.assertIn("mixed currencies",str(outcome))

    def test_us_stock_gets_sec_ten_year_history(self):
        from test_sec_facts import company_facts

        import sec_facts
        periods,statements=sec_facts.annual_statements(company_facts())
        income=statement({"Total Revenue":[1900,1800,1700,1600],"Operating Income":[380,360,340,320],"Net Income":[285,270,255,240]})
        data,_database=self.fetch(fake_yfinance({"sharesOutstanding":100,"sector":"Technology","currency":"USD"},income),sec=(periods,statements,"0000000001"))
        self.assertEqual(len(data.long_history["ebit_margin"]),10);self.assertEqual(data.long_history_periods[0],"2024-12-31");self.assertEqual(data.long_statement_years,periods)
        self.assertIn("SEC EDGAR",data.data_sources);self.assertTrue(any(entry.metric=="SEC EDGAR 10-K history" and entry.status=="Received" for entry in data.lineage))
        self.assertEqual(data.statement_years[0],"2025-12-31")  # Yahoo statements stay primary when present
    def test_sec_stands_in_when_yahoo_statements_fail(self):
        from test_sec_facts import company_facts

        import sec_facts
        periods,statements=sec_facts.annual_statements(company_facts())
        data,_database=self.fetch(fake_yfinance({"sharesOutstanding":100,"sector":"Technology","currency":"USD"}),sec=(periods,statements,"0000000001"))
        self.assertEqual(data.statement_years,periods[:5]);self.assertEqual(data.revenue_history[0],1900);self.assertTrue(any("SEC EDGAR 10-K figures were used" in warning for warning in data.warnings))
    def test_us_stock_without_sec_email_says_why(self):
        data,_database=self.fetch(fake_yfinance({"sharesOutstanding":100,"sector":"Technology","currency":"USD"}))
        self.assertTrue(any(entry.metric=="SEC EDGAR 10-K history" and entry.status=="Unavailable" for entry in data.lineage))

    def test_rate_limited_profile_is_retried_not_valued(self):
        outcome,database=self.fetch(fake_yfinance(RuntimeError("Too Many Requests. Rate limited. Try after a while.")))
        self.assertIsInstance(outcome,data_provider.DataProviderError);self.assertTrue(data_provider.is_transient_error(str(outcome)));self.assertIsNone(database.load_stock("TEST","US",allow_expired=True))

    def test_missing_profile_snapshot_is_not_cached(self):
        outcome,database=self.fetch(fake_yfinance(ValueError("Invalid crumb")))
        self.assertEqual(outcome.price,100.0);self.assertIn("Detailed company profile was partly unavailable.",outcome.warnings);self.assertIsNone(database.load_stock("TEST","US",allow_expired=True))

if __name__=="__main__":unittest.main()
