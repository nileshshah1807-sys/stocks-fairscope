import os
import sys
import tempfile
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from valuation import StockData, value_stock
from watchlist_store import WatchlistStore


class WatchlistStoreTests(unittest.TestCase):
    def setUp(self):
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);self.path=handle.name;self.store=WatchlistStore(self.path)
    def tearDown(self):
        self.store.close()
        if os.path.exists(self.path):os.unlink(self.path)
    def result(self,price=50):
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=price,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[40+i*.1 for i in range(80)])
        return value_stock(data)
    def test_persistence_settings_and_alert_state(self):
        entry=self.store.add("TEST","US","Test");self.store.update_settings(entry.id,60,10,60,60,10,True);entry=self.store.entries()[0];self.assertEqual(entry.custom_price,60);self.assertEqual(entry.min_upside,10)
        result=self.result(50);first=self.store.evaluate(entry,result);second=self.store.evaluate(entry,result);self.assertGreater(len(first),0);self.assertEqual(second,[]);self.assertEqual(self.store.unread_count(),len(first));self.store.mark_all_read();self.assertEqual(self.store.unread_count(),0)
    def test_remove_cascades(self):
        entry=self.store.add("TEST","US");self.store.evaluate(entry,self.result());self.store.remove(entry.id);self.assertEqual(self.store.entries(),[]);self.assertEqual(self.store.alerts(),[])

if __name__=="__main__":unittest.main()
