import os
import sys
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from data_provider import fetch_stock
from valuation import value_stock


@unittest.skipUnless(os.environ.get("FAIRSCOPE_RUN_NETWORK_TESTS")=="1","live network integration disabled")
class LiveNetworkIntegrationTests(unittest.TestCase):
    def test_us_knsl(self):
        result=value_stock(fetch_stock("KNSL","US",force_refresh=True));self.assertGreater(result.fair_value,0)
    def test_bse_sil_exact_resolution(self):
        result=value_stock(fetch_stock("SIL","BSE",force_refresh=True));self.assertEqual(result.data.symbol,"SIL.BO");self.assertLess(result.data.price,1000);self.assertGreater(result.fair_value,0)
    def test_indian_financial_company(self):
        result=value_stock(fetch_stock("HDFCBANK","NSE",force_refresh=True));self.assertEqual(result.methodology_profile,"Financial institution");self.assertIsNotNone(result.data.financial_metrics)

if __name__=="__main__":unittest.main()
