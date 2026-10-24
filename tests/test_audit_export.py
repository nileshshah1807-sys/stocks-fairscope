import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from valuation import StockData, audit_record, value_stock
from verify_audit_json import verify_file


class AuditExportTests(unittest.TestCase):
    def test_exported_json_verifies_and_tamper_fails(self):
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[80,90,100])
        result=value_stock(data)
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=".json",delete=False) as handle:
            json.dump(audit_record(result),handle,indent=2,ensure_ascii=False);path=handle.name
        self.addCleanup(lambda:os.path.exists(path) and os.unlink(path))
        valid,stored,calculated=verify_file(path);self.assertTrue(valid);self.assertEqual(stored,calculated)
        with open(path,encoding="utf-8") as handle:record=json.load(handle)
        record["fair_value"]+=1
        with open(path,"w",encoding="utf-8") as handle:json.dump(record,handle,indent=2,ensure_ascii=False)
        self.assertFalse(verify_file(path)[0])

if __name__=="__main__":unittest.main()
