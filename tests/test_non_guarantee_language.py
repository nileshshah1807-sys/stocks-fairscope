import os
import sys
import tempfile
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from valuation import StockData, value_stock
from watchlist_store import WatchlistStore


class NonGuaranteeLanguageTests(unittest.TestCase):
    def result(self,price=50):
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=price,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600]);return value_stock(data)
    def test_assessment_uses_buffer_not_safety_claim(self):
        result=self.result();text=(result.label+" "+" ".join(result.model_notes)).lower();self.assertNotIn("buy",text);self.assertNotIn("guaranteed",text);self.assertIn("valuation buffer",text)
    def test_watchlist_buffer_alert_disclaims_protection(self):
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);store=WatchlistStore(handle.name)
        try:
            entry=store.add("TEST","US");result=self.result(1);alerts=store.evaluate(entry,result);messages=" ".join(alert.message for alert in alerts).lower();self.assertIn("valuation-buffer",messages);self.assertIn("does not imply",messages);self.assertNotIn("margin-of-safety",messages)
        finally:
            store.close()
            for suffix in ("","-wal","-shm"):
                if os.path.exists(handle.name+suffix):os.unlink(handle.name+suffix)

if __name__=="__main__":unittest.main()
