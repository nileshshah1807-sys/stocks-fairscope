import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import stock_search


class Response:
    def raise_for_status(self):pass
    def json(self):
        return [
            {"id":2726,"name":"Reliance Industries Ltd","url":"/company/RELIANCE/consolidated/"},
            {"id":2729,"name":"Reliance Power Ltd","url":"/company/RPOWER/consolidated/"},
            {"id":1,"name":"BSE Only Ltd","url":"/company/539760/"},
            {"id":2,"name":"Reliance Nifty ETF","url":"/company/RELIETF/"},
        ]

class StockSearchTests(unittest.TestCase):
    def setUp(self):
        stock_search.search_stocks.cache_clear();stock_search._search_screener.cache_clear();stock_search._search_yahoo.cache_clear()
    def test_screener_company_search(self):
        with patch.object(stock_search.requests,"get",return_value=Response()):
            results=stock_search.search_stocks("reliance","NSE",10)
        self.assertEqual(results[0].symbol,"RELIANCE");self.assertEqual(results[0].company,"Reliance Industries Ltd")
        self.assertIn("Screener.in",results[0].source);self.assertIn("RELIANCE",results[0].display)
        self.assertNotIn("539760",[x.symbol for x in results]);self.assertNotIn("RELIETF",[x.symbol for x in results])
    def test_uppercase_direct_ticker_fallback(self):
        with patch.object(stock_search,"_search_yahoo",return_value=()):
            results=stock_search.search_stocks("AAPL","US",10)
        self.assertEqual(results[0].symbol,"AAPL");self.assertEqual(results[0].source,"Direct entry")
    def test_company_phrase_does_not_become_fake_ticker(self):
        with patch.object(stock_search,"_search_yahoo",return_value=()):
            self.assertEqual(stock_search.search_stocks("apple inc","US",10),())
            self.assertEqual(stock_search.search_stocks("ccne","US",10)[0].company,"Use entered ticker")
    def test_failed_live_search_still_offers_lowercase_ticker(self):
        with patch.object(stock_search,"_search_yahoo",return_value=None):
            results=stock_search.search_stocks("fatn","US",10)
            self.assertEqual(stock_search.search_stocks("apple inc","US",10),())
        self.assertEqual(results[0].symbol,"FATN");self.assertEqual(results[0].source,"Direct entry");self.assertIn("unavailable",results[0].company)
    def test_empty_yahoo_reply_is_not_replayed_from_yfinance_cache(self):
        from types import SimpleNamespace
        empty,found=SimpleNamespace(quotes=[]),SimpleNamespace(quotes=[{"symbol":"FATN","quoteType":"EQUITY","exchange":"NCM","longname":"FatPipe, Inc.","exchDisp":"NASDAQ"}])
        with patch("yfinance.Search",side_effect=[empty,found]) as search,patch("yfinance.data.YfData.cache_get.cache_clear") as clear:
            results=stock_search._search_yahoo("fatn",10)
        self.assertEqual(search.call_count,2);clear.assert_called_once();self.assertEqual(results[0].company,"FatPipe, Inc.")
    def test_yahoo_errors_are_reported_not_hidden(self):
        with patch("yfinance.Search",side_effect=RuntimeError("Too Many Requests. Rate limited.")):
            self.assertIsNone(stock_search._search_yahoo("FATN",10))
    def test_short_query_returns_no_results(self):
        self.assertEqual(stock_search.search_stocks("A","US",10),())

if __name__=="__main__":unittest.main()
