import math
import os
import sys
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from valuation import Assumptions, StockData, value_stock


class ExtremeValuationTests(unittest.TestCase):
    def base(self):return StockData(symbol="X",company="X",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600])
    def test_zero_and_nan_price_rejected(self):
        for value in (0,-1,float("nan")):
            data=self.base();data.price=value
            with self.assertRaisesRegex(ValueError,"positive market price"):value_stock(data)
    def test_invalid_assumptions_rejected(self):
        data=self.base()
        with self.assertRaisesRegex(ValueError,"Discount rate"):value_stock(data,Assumptions(.05,.03,.04))
        with self.assertRaisesRegex(ValueError,"Forecast period"):value_stock(data,Assumptions(.05,.10,.02,years=0))
        with self.assertRaisesRegex(ValueError,"weights"):value_stock(data,Assumptions(.05,.10,.02,dcf_weight=-1,graham_weight=0,relative_weight=0))
    def test_large_values_remain_finite(self):
        data=StockData(symbol="BIG",company="Big",market="US",currency="USD",price=1_000_000,shares=1_000_000_000_000,free_cash_flow=5_000_000_000_000,eps=1000,book_value_per_share=5000,growth_estimate=.15,fcf_history=[5e12,4e12,3e12],revenue_history=[1e14,8e13,7e13]);result=value_stock(data);self.assertTrue(math.isfinite(result.fair_value));self.assertGreater(result.fair_value,0)
    def test_no_economic_inputs_refuses_fabrication(self):
        data=StockData(symbol="EMPTY",company="Empty",market="US",currency="USD",price=10,shares=100,eps=-1,book_value_per_share=-2,free_cash_flow=-5,revenue_history=[])
        with self.assertRaisesRegex(ValueError,"will not fabricate"):value_stock(data)
    def test_monte_carlo_is_reproducible(self):
        first=value_stock(self.base());second=value_stock(self.base());self.assertEqual(first.monte_carlo_seed,second.monte_carlo_seed);self.assertEqual(first.monte_carlo_percentiles,second.monte_carlo_percentiles)

if __name__=="__main__":unittest.main()
