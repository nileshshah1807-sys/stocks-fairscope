import os
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from batch_import import BatchItem, export_batch_csv
from batch_pdf_report import create_batch_pdf
from valuation import StockData, value_stock


class LargeBatchPerformanceTests(unittest.TestCase):
    def test_100_stock_offline_batch(self):
        started=time.monotonic();records=[]
        cheap_mc=({"P10":80,"P25":90,"P50":100,"P75":110,"P90":120},.5,10,[50,150],[100],100,12345)
        with patch("valuation.monte_carlo_valuation",return_value=cheap_mc):
            for index in range(100):
                prices=[80+day*.1+index*.01 for day in range(60)];data=StockData(symbol=f"T{index:03d}",company=f"Test {index}",market="US",currency="USD",price=prices[-1],shares=100,free_cash_flow=800+index,eps=5,book_value_per_share=25,growth_estimate=.07,sector="Technology" if index%2 else "Industrials",fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=prices);records.append((BatchItem(data.symbol,"US",target_weight=1),value_stock(data),""))
        self.assertEqual(len(records),100);self.assertTrue(all(result is not None for _,result,_ in records))
        csv_handle=tempfile.NamedTemporaryFile(suffix=".csv",delete=False);csv_handle.close();pdf_handle=tempfile.NamedTemporaryFile(suffix=".pdf",delete=False);pdf_handle.close();self.addCleanup(lambda:os.path.exists(csv_handle.name) and os.unlink(csv_handle.name));self.addCleanup(lambda:os.path.exists(pdf_handle.name) and os.unlink(pdf_handle.name));export_batch_csv(records,csv_handle.name);create_batch_pdf(records,pdf_handle.name);self.assertGreater(os.path.getsize(pdf_handle.name),5000);self.assertLess(time.monotonic()-started,30)

if __name__=="__main__":unittest.main()
