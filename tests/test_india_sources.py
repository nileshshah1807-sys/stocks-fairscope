import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import india_sources


class Response:
    def __init__(self,text="",data=None,status=200):self.text=text;self._data=data;self.status_code=status
    def raise_for_status(self):
        if self.status_code>=400:raise RuntimeError("http")
    def json(self):return self._data

class IndiaSourcesTests(unittest.TestCase):
    def setUp(self):india_sources._screener_page.cache_clear();india_sources.fetch_screener.cache_clear();india_sources.fetch_screener_financials.cache_clear();india_sources.fetch_bse_quote.cache_clear();india_sources.fetch_nse_quote.cache_clear();india_sources._resolve_bse_code.cache_clear();india_sources.fetch_screener_tables.cache_clear();india_sources.fetch_nse_pledge.cache_clear()
    def test_screener_top_ratios(self):
        html='''<div id="top-ratios"><ul><li><span class="name">Current Price</span><span class="number">1,310</span></li><li><span class="name">Stock P/E</span><span class="number">23.7</span></li><li><span class="name">Book Value</span><span class="number">668</span></li><li><span class="name">High / Low</span><span class="number">1,612</span><span class="number">1,250</span></li></ul></div>'''
        with patch.object(india_sources.requests,"get",return_value=Response(html)):
            ratios,url,error=india_sources.fetch_screener("RELIANCE.NS")
        self.assertFalse(error);self.assertEqual(ratios["Current Price"],1310);self.assertEqual(ratios["Stock P/E"],23.7);self.assertEqual(ratios["52W Low"],1250)
    def test_screener_financial_series(self):
        html='''<section><h2>Profit &amp; Loss</h2><table><tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr><tr><td>Financing Margin %</td><td>12%</td><td>14%</td></tr></table></section><section><h2>Balance Sheet</h2><table><tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr><tr><td>Deposits</td><td>1,000</td><td>1,200</td></tr></table></section>'''
        with patch.object(india_sources.requests,"get",return_value=Response(html)):
            series,periods=india_sources.fetch_screener_financials("BANK.NS")
        self.assertEqual(series["Profit & Loss:Financing Margin %"], [12,14]);self.assertEqual(series["Balance Sheet:Deposits"], [1000,1200]);self.assertEqual(periods["Balance Sheet"], ["Mar 2024","Mar 2025"])

    def test_bse_symbol_resolver_requires_exact_security_id(self):
        html="<a href='/stock-share-price/crisil-ltd/crisil/500092/'>CRISIL</a><a href='/stock-share-price/standard-industries-ltd/sil/530017/'>SIL</a>"
        with patch.object(india_sources.requests,"get",return_value=Response(html)):
            self.assertEqual(india_sources._resolve_bse_code("SIL.BO"),"530017")

    def test_bse_quote(self):
        payload={"CurrRate":{"LTP":"1,308.00"},"Header":{"Ason":"16 Aug 2026"}}
        with patch.object(india_sources.requests,"get",return_value=Response(data=payload)):
            price,stamp,error=india_sources.fetch_bse_quote("500325.BO")
        self.assertEqual(price,1308);self.assertEqual(stamp,"16 Aug 2026");self.assertFalse(error)
    def test_discrepancy_warning(self):
        with patch.object(india_sources,"fetch_screener",return_value=({"Current Price":90},"url","")),patch.object(india_sources,"fetch_screener_financials",return_value=({},{})),patch.object(india_sources,"fetch_nse_quote",return_value=(80,"now","")),patch.object(india_sources,"fetch_screener_tables",return_value={}),patch.object(india_sources,"fetch_nse_pledge",return_value=None):
            result=india_sources.verify_indian_stock("TEST.NS","NSE",100)
        self.assertIn("Screener.in",result.sources_checked);self.assertTrue(any("discrepancy" in x.lower() for x in result.warnings));self.assertIn("nseindia.com",result.exchange_url)

if __name__=="__main__":unittest.main()
