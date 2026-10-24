import os
import sys
import tempfile
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from local_database import LocalDatabase
from valuation import DataLineageEntry, FinancialCompanyMetrics, StockData, value_stock


class LocalDatabaseTests(unittest.TestCase):
    def setUp(self):
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);self.path=handle.name;self.db=LocalDatabase(self.path)
    def tearDown(self):
        self.db.close()
        for suffix in ("","-wal","-shm"):
            if os.path.exists(self.path+suffix):os.unlink(self.path+suffix)
    def stock(self):
        return StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[90,95,100],price_dates=["2026-08-16","2026-08-17","2026-08-18"],lineage=[DataLineageEntry("Price","USD 100","Yahoo","https://example.com")],financial_metrics=FinancialCompanyMetrics(subtype="Bank",gross_npa=.01))
    def test_stock_cache_roundtrip_and_stale(self):
        if os.name!="nt":self.assertEqual(os.stat(self.path).st_mode & 0o777,0o600)
        stock=self.stock();self.db.save_stock(stock,ttl_hours=1);cached=self.db.load_stock("TEST","US");self.assertEqual(cached.symbol,"TEST");self.assertEqual(cached.financial_metrics.gross_npa,.01);self.assertEqual(cached.lineage[0].metric,"Price");self.assertEqual(cached.cache_status,"fresh cache")
        self.db.save_stock(stock,ttl_hours=-1);self.assertIsNone(self.db.load_stock("TEST","US"));stale=self.db.load_stock("TEST","US",allow_expired=True);self.assertTrue(stale.is_stale)
    def test_valuation_history_and_settings(self):
        result=value_stock(self.stock());self.db.save_valuation(result);rows=self.db.history_rows();self.assertEqual(rows[0]["analysis_id"],result.analysis_id);self.assertEqual(self.db.history_audit(result.analysis_id)["audit_hash"],result.audit_hash);self.db.set_setting("cache_ttl_hours",12);self.assertEqual(self.db.cache_ttl_hours(),12);self.assertEqual(self.db.stats()["history_records"],1);self.db.clear_history();self.assertEqual(self.db.history_rows(),[])
    def test_background_job_recovery_metadata(self):
        from batch_import import BatchItem
        job_id=self.db.create_job("batch",[BatchItem("AAPL","US"),BatchItem("MSFT","US")]);self.db.update_job(job_id,1);self.assertEqual(self.db.mark_running_interrupted(),1);job=self.db.recoverable_jobs()[0];self.assertEqual(job["completed"],1);self.assertEqual(job["total"],2);self.db.delete_job(job_id);self.assertEqual(self.db.recoverable_jobs(),[])
    def test_clear_expired_and_cache(self):
        self.db.save_stock(self.stock(),ttl_hours=-1);self.db.clear_expired();self.assertEqual(self.db.stats()["cached_stocks"],0);self.db.save_stock(self.stock(),ttl_hours=1);self.db.clear_cache();self.assertEqual(self.db.stats()["cached_stocks"],0)

if __name__=="__main__":unittest.main()
