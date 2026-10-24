import os
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import data_provider
from local_database import LocalDatabase
from valuation import StockData


class CacheFailureFallbackTests(unittest.TestCase):
    def test_network_failure_returns_stale_cache(self):
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);database=LocalDatabase(handle.name);self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name))
        stock=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,revenue_history=[1000]);database.save_stock(stock,ttl_hours=-1)
        class Ticker:
            def __init__(self,symbol):pass
            def history(self,*args,**kwargs):raise RuntimeError("network connection timeout")
        fake=types.SimpleNamespace(Ticker=Ticker)
        with patch.object(data_provider,"get_local_database",return_value=database),patch.dict(sys.modules,{"yfinance":fake}),patch.object(data_provider,"_damodaran_country_premiums",return_value=None):result=data_provider.fetch_stock("TEST","US",force_refresh=True,allow_stale=True)
        self.assertTrue(result.is_stale);self.assertEqual(result.cache_status,"stale cache");database.close()

if __name__=="__main__":unittest.main()
