import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from data_provider import normalize_symbol
from valuation import Assumptions, FinancialCompanyMetrics, StockData, audit_record, default_assumptions, value_stock, verify_audit_hash


class ValuationTests(unittest.TestCase):
    def setUp(self):
        self.stock = StockData(symbol="TEST", company="Test Corp", market="US", currency="USD", price=100,
            shares=100, free_cash_flow=900, eps=6, book_value_per_share=30, growth_estimate=.09)

    def test_three_scenarios_and_order(self):
        r = value_stock(self.stock)
        self.assertEqual(set(r.scenarios), {"Conservative", "Base", "Optimistic"})
        self.assertLess(r.scenarios["Conservative"].fair_value, r.scenarios["Optimistic"].fair_value)

    def test_stale_cache_reduces_data_quality(self):
        fresh=value_stock(self.stock);self.stock.is_stale=True;self.stock.cache_status="stale cache";self.stock.cache_age_hours=72;stale=value_stock(self.stock);self.assertLess(stale.data_quality_score,fresh.data_quality_score);self.assertTrue(any("Stale cached" in flag for flag in stale.quality_flags))

    def test_dynamic_margin_of_safety(self):
        r = value_stock(self.stock)
        self.assertGreaterEqual(r.dynamic_margin, .20)
        self.assertLessEqual(r.dynamic_margin, .50)
        self.assertAlmostEqual(r.margin_price, r.fair_value * (1-r.dynamic_margin))

    def test_missing_dcf_reweights(self):
        self.stock.free_cash_flow = None
        r = value_stock(self.stock)
        self.assertIsNone(r.scenarios["Base"].dcf)
        self.assertGreater(r.fair_value, 0)

    def test_market_defaults_and_symbols(self):
        india = StockData(symbol="X.NS", company="X", market="NSE", currency="INR", price=10)
        self.assertGreaterEqual(default_assumptions(india).discount_rate, .115)
        self.assertEqual(default_assumptions(india).years, 10)
        self.assertEqual(normalize_symbol("reliance", "NSE"), "RELIANCE.NS")
        self.assertEqual(normalize_symbol("500325", "BSE"), "500325.BO")
        self.assertEqual(normalize_symbol("aapl", "US"), "AAPL")
        self.assertEqual(normalize_symbol("TCS.NS", "NSE"), "TCS.NS")

    def test_phase2_sensitivity_quality_and_confidence(self):
        self.stock.fcf_history=[900,850,800,760]
        self.stock.revenue_history=[5000,4600,4200,3900]
        self.stock.net_income=600; self.stock.operating_cash_flow=750
        self.stock.stockholder_equity=3000; self.stock.total_debt=500; self.stock.cash=300; self.stock.ebit=700
        self.stock.return_on_equity=.20; self.stock.operating_margins=.18
        self.stock.diluted_shares_history=[100,101,102,103]
        r=value_stock(self.stock)
        self.assertEqual(len(r.sensitivity_values),5)
        self.assertTrue(all(len(row)==5 for row in r.sensitivity_values))
        self.assertTrue(0<=r.business_quality_score<=100)
        self.assertTrue(0<=r.governance_risk_score<=100)
        self.assertTrue(0<=r.confidence_score<=100)
        self.assertTrue(r.reverse_dcf_note)
        self.assertEqual(r.monte_carlo_iterations,2000)
        self.assertEqual(set(r.monte_carlo_percentiles),{"P10","P25","P50","P75","P90"})
        self.assertTrue(0<=r.monte_carlo_probability_above_price<=1)

    def test_model_audit_hash_and_parent_chain(self):
        first=value_stock(self.stock)
        self.assertTrue(first.analysis_id.startswith("FS-"));self.assertTrue(verify_audit_hash(first));self.assertEqual(len(first.audit_hash),64);self.assertGreaterEqual(len(first.audit_events),10)
        payload=audit_record(first);self.assertEqual(payload["analysis_id"],first.analysis_id);self.assertEqual(payload["monte_carlo_seed"],first.monte_carlo_seed)
        second=value_stock(self.stock,parent_analysis_id=first.analysis_id)
        self.assertEqual(second.parent_analysis_id,first.analysis_id);self.assertNotEqual(second.analysis_id,first.analysis_id);self.assertEqual(second.monte_carlo_seed,first.monte_carlo_seed);self.assertTrue(verify_audit_hash(second))
        original=first.fair_value;first.fair_value+=1
        self.assertFalse(verify_audit_hash(first));first.fair_value=original;self.assertTrue(verify_audit_hash(first))

    def test_assumption_override_audit_trail(self):
        automatic=default_assumptions(self.stock)
        reviewed=Assumptions(automatic.growth+.01,automatic.discount_rate,automatic.terminal_growth,automatic.years,automatic.dcf_weight,automatic.graham_weight,automatic.relative_weight,automatic.margin_of_safety+.05)
        result=value_stock(self.stock,reviewed,automatic_assumptions=automatic,assumption_note="Higher minimum valuation buffer.",assumption_preset="Custom review")
        self.assertIn("growth",result.manual_overrides);self.assertIn("margin_of_safety",result.manual_overrides)
        self.assertEqual(result.assumption_preset,"Custom review");self.assertEqual(result.assumption_note,"Higher minimum valuation buffer.")
        self.assertIs(result.automatic_assumptions,automatic)

    def test_loss_making_asset_revenue_fallback(self):
        stock=StockData(symbol="LOSS",company="Loss Co",market="BSE",currency="INR",price=20,shares=100,free_cash_flow=-10,eps=-1,book_value_per_share=18,growth_estimate=.02,sector="Consumer Cyclical",revenue_history=[1000,950,900],fcf_history=[-10,-8,-12],peer_median_pb=1.3,peer_symbols=["P1","P2","P3"])
        result=value_stock(stock)
        self.assertTrue(result.fallback_valuation);self.assertGreater(result.fair_value,0);self.assertLessEqual(result.confidence_score,49);self.assertGreaterEqual(result.dynamic_margin,.35);self.assertEqual(result.model_labels["relative"],"Peer P/B fallback")

    def test_specialized_bank_and_insurer_models(self):
        bank_metrics=FinancialCompanyMetrics(subtype="Bank",gross_npa=.015,net_npa=.004,capital_adequacy=.19,cet1_ratio=.16,provision_coverage=.75,casa_ratio=.42,net_interest_margin=.038,credit_cost=.009,deposit_growth=.12,cost_to_income=.44)
        bank=StockData(symbol="BANK",company="Bank",market="NSE",currency="INR",price=100,eps=8,book_value_per_share=60,sector="Financial Services",industry="Banks - Regional",return_on_equity=.16,peer_median_pb=1.8,peer_symbols=["B1","B2","B3"],financial_metrics=bank_metrics)
        result=value_stock(bank)
        self.assertEqual(result.model_labels["graham"],"Justified P/B");self.assertIsNotNone(result.scenarios["Base"].graham);self.assertLess(result.risk_score,50);self.assertTrue(verify_audit_hash(result))
        bank_metrics.gross_npa=.05;self.assertFalse(verify_audit_hash(result));bank_metrics.gross_npa=.015;self.assertTrue(verify_audit_hash(result))
        insurer_metrics=FinancialCompanyMetrics(subtype="Insurance",embedded_value_per_share=120,fair_price_to_embedded_value=1.5,solvency_ratio=1.9,vnb_margin=.24,premium_growth=.12)
        insurer=StockData(symbol="INS",company="Insurer",market="NSE",currency="INR",price=150,eps=6,book_value_per_share=50,sector="Financial Services",industry="Insurance - Life",return_on_equity=.15,peer_median_pb=2,financial_metrics=insurer_metrics)
        insured=value_stock(insurer)
        self.assertEqual(insured.model_labels["graham"],"Embedded value");self.assertAlmostEqual(insured.scenarios["Base"].graham,180)

    def test_governance_promoter_and_order_book_affect_automatic_fair_value(self):
        base=dict(symbol="IND",company="Industrial",market="NSE",currency="INR",price=100,shares=100,free_cash_flow=900,eps=6,book_value_per_share=30,growth_estimate=.08,sector="Industrials",revenue_history=[1000,900,820],fcf_history=[900,850,800],peer_median_pe=18,peer_symbols=["P1","P2","P3","P4"])
        improving=StockData(**base,order_book=2500,order_book_period="FY2027",promoter_holding_history=[.58,.57,.56,.55])
        declining=StockData(**base,order_book=400,order_book_period="FY2027",promoter_holding_history=[.43,.47,.51,.55],audit_risk=9,board_risk=8)
        good=value_stock(improving);weak=value_stock(declining)
        self.assertGreater(good.order_book_score,weak.order_book_score)
        self.assertLess(good.governance_risk_score,weak.governance_risk_score)
        self.assertLess(good.base_assumptions.discount_rate,weak.base_assumptions.discount_rate)
        self.assertGreater(good.base_assumptions.growth,weak.base_assumptions.growth)
        self.assertGreater(good.fair_value,weak.fair_value)
        self.assertIn("order_book_score",audit_record(good));self.assertTrue(verify_audit_hash(good))

    def test_live_peer_and_sector_profile(self):
        self.stock.peer_median_pe = 18
        self.stock.peer_symbols = ["P1", "P2", "P3", "P4"]
        r = value_stock(self.stock)
        self.assertEqual(r.scenarios["Base"].relative, self.stock.eps * 18)
        bank = StockData(symbol="BANK", company="Bank", market="US", currency="USD", price=50,
            eps=5, book_value_per_share=40, sector="Financial Services", peer_median_pb=1.5,
            peer_symbols=["B1","B2","B3","B4"])
        rb = value_stock(bank)
        self.assertEqual(rb.methodology_profile, "Financial institution")
        self.assertEqual(rb.model_labels["relative"], "Peer P/B")

    def test_scenario_order_holds_for_reviewed_extremes(self):
        from valuation import scenario_assumptions
        for base in (Assumptions(.30,.10,.03),Assumptions(.05,.06,.02),Assumptions(.05,.09,.08),Assumptions(-.10,.10,.02)):
            s=scenario_assumptions(base);cons,opt=s["Conservative"],s["Optimistic"]
            self.assertLessEqual(cons.growth,base.growth);self.assertGreaterEqual(opt.growth,base.growth)
            self.assertLessEqual(opt.discount_rate,base.discount_rate);self.assertGreaterEqual(opt.terminal_growth,base.terminal_growth);self.assertGreater(opt.discount_rate,opt.terminal_growth)
        r=value_stock(self.stock,Assumptions(.30,.10,.03))
        self.assertLessEqual(r.scenarios["Conservative"].fair_value,r.scenarios["Base"].fair_value);self.assertLessEqual(r.scenarios["Base"].fair_value,r.scenarios["Optimistic"].fair_value)

if __name__ == "__main__": unittest.main()
