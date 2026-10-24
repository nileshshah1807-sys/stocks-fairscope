import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import sec_facts

YEARS=range(2015,2025)

def flow(year,value,filed=None,form="10-K",fp="FY",start=None):
    return {"start":start or f"{year}-01-01","end":f"{year}-12-31","val":value,"form":form,"fp":fp,"filed":filed or f"{year+1}-02-15"}

def instant(year,value):return {"end":f"{year}-12-31","val":value,"form":"10-K","fp":"FY","filed":f"{year+1}-02-15"}

def company_facts():
    """SEC companyfacts shape: revenue switches tag in 2018 (ASC 606), one year is restated, and quarters/10-Qs must be ignored."""
    revenue=lambda year:1000+100*(year-2015)  # noqa: E731
    gaap={
        "SalesRevenueNet":{"units":{"USD":[flow(year,revenue(year)) for year in YEARS if year<2018]}},
        "RevenueFromContractWithCustomerExcludingAssessedTax":{"units":{"USD":[flow(year,revenue(year)) for year in YEARS if year>=2018]+[flow(2024,999,form="10-Q",fp="Q3"),flow(2024,450,start="2024-10-01")]}},
        "OperatingIncomeLoss":{"units":{"USD":[flow(year,.2*revenue(year)) for year in YEARS]+[flow(2020,1.0,filed="2021-02-15"),flow(2020,.2*revenue(2020),filed="2022-02-15")]}},
        "NetIncomeLoss":{"units":{"USD":[flow(year,.15*revenue(year)) for year in YEARS]}},
        "IncomeTaxExpenseBenefit":{"units":{"USD":[flow(year,.04*revenue(year)) for year in YEARS]}},
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest":{"units":{"USD":[flow(year,.19*revenue(year)) for year in YEARS]}},
        "NetCashProvidedByUsedInOperatingActivities":{"units":{"USD":[flow(year,.25*revenue(year)) for year in YEARS]}},
        "PaymentsToAcquirePropertyPlantAndEquipment":{"units":{"USD":[flow(year,.05*revenue(year)) for year in YEARS]}},
        "PaymentsOfDividends":{"units":{"USD":[flow(year,.06*revenue(year)) for year in YEARS]}},
        "StockholdersEquity":{"units":{"USD":[instant(year,2*revenue(year)) for year in YEARS]}},
        "LongTermDebt":{"units":{"USD":[instant(year,500.0) for year in YEARS]}},
        "WeightedAverageNumberOfDilutedSharesOutstanding":{"units":{"shares":[flow(year,100.0) for year in YEARS]}},
    }
    return {"facts":{"us-gaap":gaap}}

class SecFactsTests(unittest.TestCase):
    def test_annual_values_take_latest_filing_and_skip_quarters(self):
        values=sec_facts._annual([flow(2020,1.0,filed="2021-02-15"),flow(2020,2.0,filed="2022-02-15"),flow(2021,9.0,form="10-Q",fp="Q2"),flow(2021,5.0,start="2021-10-01"),instant(2021,7.0)])
        self.assertEqual(values,{"2020-12-31":2.0,"2021-12-31":7.0})
    def test_statements_merge_tags_align_years_and_use_app_signs(self):
        periods,statements=sec_facts.annual_statements(company_facts())
        self.assertEqual(periods[0],"2024-12-31");self.assertEqual(periods[-1],"2015-12-31");self.assertEqual(len(periods),10)
        self.assertEqual(statements["revenue"],[1000+100*(year-2015) for year in reversed(YEARS)])  # tag switch in 2018 is seamless; 10-Q and Q4 rows ignored
        self.assertAlmostEqual(statements["ebit"][4],.2*1500)  # 2020 restatement: the later filing wins
        self.assertAlmostEqual(statements["capital_expenditure"][0],-.05*1900);self.assertAlmostEqual(statements["free_cash_flow"][0],.2*1900)
        self.assertAlmostEqual(statements["tax_rate"][0],.04/.19);self.assertEqual(statements["diluted_shares"][0],100);self.assertEqual(statements["total_debt"][0],500)
        self.assertNotIn("pretax_income",statements)
    def test_long_history_matches_the_screener_series(self):
        periods,statements=sec_facts.annual_statements(company_facts());history=sec_facts.long_history(periods,statements)
        self.assertAlmostEqual(history["ebit_margin"][0],.2);self.assertAlmostEqual(history["net_margin"][9],.15);self.assertAlmostEqual(history["dividend_payout"][0],.06/.15)
        self.assertAlmostEqual(history["roce"][0],.2*1900/(2*1900+500));self.assertEqual(len(history["ebit_margin"]),10)
    def test_cik_lookup_matches_share_classes(self):
        with patch.object(sec_facts,"sec_tickers",return_value={"0":{"cik_str":1067983,"ticker":"BRK-B"}}):
            self.assertEqual(sec_facts.cik_for("BRK.B","agent"),"0001067983");self.assertIsNone(sec_facts.cik_for("ZZZZ","agent"))

if __name__=="__main__":unittest.main()
