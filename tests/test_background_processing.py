import os
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import background_processing
from background_processing import JobControl, analyze_with_retry, is_transient_error
from batch_import import BatchItem
from valuation import StockData, value_stock


class BackgroundProcessingTests(unittest.TestCase):
    def result(self):
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600]);return value_stock(data)
    def test_transient_retry_succeeds(self):
        calls={"count":0};result=self.result()
        def fake_fetch(*args,**kwargs):
            calls["count"]+=1
            if calls["count"]<3:raise RuntimeError("429 rate limit")
            return result.data
        with patch.object(background_processing,"fetch_stock",side_effect=fake_fetch):outcome=analyze_with_retry(0,BatchItem("TEST","US"),JobControl(),3)
        self.assertIsNotNone(outcome.result);self.assertEqual(outcome.attempts,3);self.assertTrue(is_transient_error("connection timeout"))
    def test_cancel_before_start(self):
        control=JobControl();control.cancel();outcome=analyze_with_retry(0,BatchItem("TEST","US"),control,3);self.assertTrue(outcome.cancelled);self.assertIsNone(outcome.result)
    def test_pause_and_resume(self):
        control=JobControl();control.pause();holder={}
        thread=threading.Thread(target=lambda:holder.setdefault("outcome",analyze_with_retry(0,BatchItem("TEST","US"),control,1)));thread.start();time.sleep(.15);self.assertTrue(thread.is_alive())
        with patch.object(background_processing,"fetch_stock",return_value=self.result().data):control.resume();thread.join(2)
        self.assertFalse(thread.is_alive())

if __name__=="__main__":unittest.main()
