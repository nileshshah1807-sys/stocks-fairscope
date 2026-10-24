import os
import sys
import tempfile
import unittest
import unittest.mock
from dataclasses import replace

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import backtest
import data_provider
import india_sources
from fundamentals import altman_z_score, beneish_m_score, level_adjusted_long_median, normalized_cash_flows, piotroski_f_score
from local_database import LocalDatabase
from valuation import Assumptions, StockData, build_context, cost_of_capital, default_assumptions, relative_valuation, reverse_dcf, value_stock, verify_audit_hash

YEARS=["2025-12-31","2024-12-31","2023-12-31","2022-12-31"]
STATEMENTS={"revenue":[1000,900,810,730],"ebit":[250,220,190,170],"ebitda":[290,256,223,200],"depreciation":[40,36,33,30],"capital_expenditure":[-50,-45,-40,-36],"working_capital_change":[-10,-8,-7,-6],
    "net_income":[190,165,140,125],"operating_cash_flow":[260,230,200,180],"free_cash_flow":[210,185,160,144],"stock_based_compensation":[20,18,15,12],"tax_rate":[.21,.21,.2,.2],
    "total_assets":[1500,1400,1300,1200],"current_assets":[600,560,520,480],"current_liabilities":[300,290,280,270],"total_liabilities":[700,680,660,640],"long_term_debt":[100,110,120,130],
    "total_debt":[100,110,120,130],"cash":[200,180,160,140],"equity":[800,720,640,560],"ppe":[400,380,360,340],"receivables":[150,135,120,110],"inventory":[80,75,70,65],"payables":[90,85,80,75],
    "retained_earnings":[500,420,350,290],"diluted_shares":[100,101,102,103],"gross_profit":[600,535,480,430],"cost_of_revenue":[400,365,330,300],"sga":[300,270,250,225],
    "repurchase_of_stock":[-60,-50,-40,-30],"issuance_of_stock":[5,5,5,5],"dividends_paid":[-40,-35,-30,-25]}

def compounder(**changes):
    months=[f"{2021+index//12}-{index%12+1:02d}-28" for index in range(60)];prices=[30*(1.01**index) for index in range(60)]
    base=StockData(symbol="SYN",company="Synthetic Tech",market="US",currency="USD",price=60,shares=100,free_cash_flow=190,eps=1.9,book_value_per_share=8,growth_estimate=.10,sector="Technology",industry="Software",market_cap=6000,
        total_debt=100,cash=200,ebitda=290,ebit=250,interest_expense=5,stockholder_equity=800,revenue_history=[1000,900,810,730],fcf_history=[210,185,160,144],net_income_history=[190,165,140,125],
        statement_years=list(YEARS),statements={key:list(values) for key,values in STATEMENTS.items()},beta=1.1,risk_free_rate=.043,equity_risk_premium=.045,
        long_price_dates=months,long_prices=prices,long_adjusted_prices=prices)
    return replace(base,**changes)

class CostOfCapitalTests(unittest.TestCase):
    def test_capm_blume_beta_and_wacc(self):
        data=compounder(total_debt=3000,interest_expense=180,market_cap=6000);capital=cost_of_capital(data,"Technology operating company",.21,20,20)
        self.assertAlmostEqual(capital.beta,.67*1.1+.33);self.assertAlmostEqual(capital.cost_of_equity,.043+capital.beta*.045)
        # EBIT 250 ÷ interest 180 = 1.39× coverage → B- → 5.09% over the government yield.
        self.assertAlmostEqual(capital.debt_weight,3000/9000);self.assertLess(capital.wacc,capital.cost_of_equity);self.assertEqual(capital.debt_rating,"B-");self.assertAlmostEqual(capital.pre_tax_cost_of_debt,min(.043+.0509,capital.cost_of_equity))
        india=cost_of_capital(compounder(market="NSE",interest_expense=10,risk_free_rate=.065-.0187,country_default_spread=.0187),"Technology operating company",.25,20,20)
        self.assertEqual(india.debt_rating,"AAA");self.assertAlmostEqual(india.pre_tax_cost_of_debt,.065+.004);self.assertAlmostEqual(india.risk_free_rate,.065-.0187)
        losing=cost_of_capital(compounder(ebit=-50,total_debt=3000,interest_expense=180),"Standard operating company",.21,20,20)
        self.assertEqual(losing.debt_rating,"D");self.assertAlmostEqual(losing.pre_tax_cost_of_debt,losing.cost_of_equity);self.assertLessEqual(losing.wacc,losing.cost_of_equity)
    def test_sector_beta_premiums_and_financial_equity_rate(self):
        data=compounder(beta=None,sector="Utilities");capital=cost_of_capital(data,"Regulated / utility",.25,85,80)
        self.assertEqual(capital.beta,.7);self.assertIn("Sector default",capital.beta_source);self.assertAlmostEqual(capital.company_risk_premium,.016+(80-35)/65*.02)
        bank=cost_of_capital(compounder(total_debt=5000),"Financial institution",.25,20,20);self.assertEqual(bank.debt_weight,0);self.assertAlmostEqual(bank.wacc,bank.cost_of_equity)

class OperatingModelTests(unittest.TestCase):
    def test_fcff_path_bridge_epv_and_weighted_fair_value(self):
        result=value_stock(compounder(),monte_carlo_iterations=200)
        self.assertEqual(result.valuation_drivers["basis"],"FCFF");self.assertEqual(result.model_labels["dcf"],"FCFF DCF (WACC)");self.assertEqual(result.model_labels["graham"],"Earnings power value")
        drivers=result.valuation_drivers;rate=result.base_assumptions.discount_rate
        self.assertAlmostEqual(result.scenarios["Base"].graham,(1000*drivers["nopat_margin"]/rate-drivers["net_claims"])/100)
        weights=result.scenario_weights;expected=sum(weight*result.scenarios[name].fair_value for weight,name in zip(weights,("Conservative","Base","Optimistic")))
        self.assertAlmostEqual(result.fair_value,expected);self.assertEqual(result.base_fair_value,result.scenarios["Base"].fair_value);self.assertTrue(0<result.terminal_value_share<1);self.assertTrue(verify_audit_hash(result))
        plain=value_stock(compounder(),monte_carlo_iterations=0).scenarios["Base"].dcf
        self.assertAlmostEqual(value_stock(compounder(minority_interest=500),monte_carlo_iterations=0).scenarios["Base"].dcf,plain-5,places=6)
        self.assertAlmostEqual(value_stock(compounder(listed_investments_value=1000,holding_discount=.2),monte_carlo_iterations=0).scenarios["Base"].dcf,plain+8,places=6)
    def test_high_roic_compounder_gets_longer_growth_stage_and_blended_growth(self):
        data=compounder(analyst_growth=.12);automatic=default_assumptions(data);context=build_context(data)
        self.assertEqual(automatic.high_growth_years,10);self.assertEqual(automatic.years,15)
        self.assertIn("Analyst consensus",value_stock(data,monte_carlo_iterations=0).growth_components)
        weak=compounder(statements={**STATEMENTS,"ebit":[20,18,16,15]},ebit=20);self.assertEqual(default_assumptions(weak).high_growth_years,3)
        self.assertGreater(context.drivers.roic,context.capital.wacc)
    def test_margin_normalization_deducts_sbc_and_tracks_latest_revenue(self):
        fcf,income,eps=normalized_cash_flows(STATEMENTS,1000,100)
        margins=sorted([(210-20)/1000,(185-18)/900,(160-15)/810,(144-12)/730]);self.assertAlmostEqual(fcf,1000*(margins[1]+margins[2])/2);self.assertAlmostEqual(eps,income/100)
        levels=sorted([210-20,185-18,160-15,144-12]);self.assertGreater(fcf,(levels[1]+levels[2])/2)
    def test_loss_maker_uses_margin_convergence(self):
        data=StockData(symbol="LOSS",company="Loss",market="US",currency="USD",price=5,shares=100,free_cash_flow=-50,eps=-.4,book_value_per_share=3,sector="Technology",revenue_history=[1000,800,600])
        result=value_stock(data,monte_carlo_iterations=0)
        self.assertEqual(result.model_labels["dcf"],"Revenue DCF (margin convergence)");self.assertTrue(result.fallback_valuation);self.assertGreater(result.scenarios["Base"].dcf,0)
        self.assertTrue(any("converging" in reason for reason in result.fallback_reasons))
    def test_relative_components_growth_adjustment_and_own_history(self):
        data=compounder(peer_median_pe=20,peer_median_growth=.05,growth_estimate=.15,peer_median_ev_ebitda=15,peer_median_forward_pe=18,forward_eps=2.0)
        context=build_context(data);value,components,label=relative_valuation(data,context.profile,context.drivers,{"pe":25,"ev_ebitda":18})
        self.assertAlmostEqual(components["Peer P/E"],20*1.9*1.15);self.assertAlmostEqual(components["Peer EV/EBITDA"],(15*290+100)/100);self.assertIn("Own P/E history",components)
        peers=[components[key] for key in ("Peer P/E","Peer forward P/E","Peer EV/EBITDA")];own=[components[key] for key in ("Own P/E history","Own EV/EBITDA history")]
        self.assertAlmostEqual(value,.6*sum(peers)/3+.4*sum(own)/2);self.assertEqual(label,"Peer multiples + own history")
    def test_reverse_dcf_treats_negative_equity_as_zero(self):
        data=compounder(total_debt=5000,cash=0);automatic=default_assumptions(data);context=build_context(data)
        implied,note=reverse_dcf(data,automatic,context.profile,context)
        self.assertIsNotNone(implied,note);self.assertIn("implies",note)

LONG_YEARS=[f"{year}-12-31" for year in range(2025,2017,-1)]
def history(revenue,ebit):return compounder(long_statement_years=LONG_YEARS,long_statements={"revenue":revenue,"ebit":ebit})

class UncertaintyTests(unittest.TestCase):
    def spreads(self,data):
        from valuation import monte_carlo_spreads
        context=build_context(data);return monte_carlo_spreads(data,default_assumptions(data,context),context)
    def test_monte_carlo_spreads_follow_company_history(self):
        steady=self.spreads(history([1000*1.05**-index for index in range(8)],[250*1.05**-index for index in range(8)]))
        volatile=self.spreads(history([1000,600,1100,500,900,400,950,450],[250,-30,300,-50,200,-60,240,-40]))
        self.assertAlmostEqual(steady["growth"],.02);self.assertAlmostEqual(steady["margin"],.06);self.assertEqual(steady["history_years"],7)
        self.assertAlmostEqual(volatile["growth"],.10);self.assertAlmostEqual(volatile["margin"],.35);self.assertGreater(volatile["correlation"],.5)
        self.assertLess(self.spreads(compounder(beta_standard_error=.05))["discount"],self.spreads(compounder(beta_standard_error=.6))["discount"])
    def test_screener_sales_history_feeds_indian_spreads(self):
        sales=[1000*1.1**-index for index in range(11)];margins=[.2]*11
        spreads=self.spreads(compounder(market="NSE",long_history={"revenue":sales,"ebit_margin":margins}))
        self.assertEqual(spreads["history_years"],10);self.assertAlmostEqual(spreads["growth"],.02)
    def test_simulation_width_reflects_the_company(self):
        steady=value_stock(history([1000*1.05**-index for index in range(8)],[250*1.05**-index for index in range(8)]),monte_carlo_iterations=600)
        volatile=value_stock(history([1000,600,1100,500,900,400,950,450],[250,-30,300,-50,200,-60,240,-40]),monte_carlo_iterations=600)
        def width(result):return result.monte_carlo_percentiles["P90"]/result.monte_carlo_percentiles["P10"]
        self.assertGreater(width(volatile),width(steady));self.assertTrue(any("calibrated to this company" in note for note in steady.model_notes));self.assertIn("growth",steady.monte_carlo_spreads)
    def test_implied_return_equals_cost_of_equity_at_model_value(self):
        from valuation import _primary_value, implied_return
        data=compounder();context=build_context(data);base=default_assumptions(data,context);value=_primary_value(data,base,context.profile,context)
        at_value,_note=implied_return(replace(data,price=value),base,context.profile,context)
        self.assertAlmostEqual(at_value,context.capital.cost_of_equity,places=4)
        cheaper,note=implied_return(replace(data,price=value*.5),base,context.profile,context)
        self.assertGreater(cheaper,context.capital.cost_of_equity);self.assertIn("a year for shareholders",note)
        self.assertEqual(value_stock(data,monte_carlo_iterations=0).implied_return is not None,True)

class ForwardTrackingTests(unittest.TestCase):
    def test_forward_points_dedupe_wait_and_annualize(self):
        from datetime import date
        rows=[{"symbol":"AAA","market":"US","created_at":"2025-01-10T12:00:00+00:00","market_price":100,"fair_value":150,"upside_pct":50,"margin_price":110},
              {"symbol":"AAA","market":"US","created_at":"2025-01-10T09:00:00+00:00","market_price":90,"fair_value":150,"upside_pct":66,"margin_price":110},
              {"symbol":"BBB","market":"US","created_at":"2026-10-10T09:00:00+00:00","market_price":10,"fair_value":12,"upside_pct":20,"margin_price":9},
              {"symbol":"CCC","market":"NSE","created_at":"2026-06-01T09:00:00+00:00","market_price":50,"fair_value":40,"upside_pct":-20,"margin_price":30}]
        points={point.symbol:point for point in backtest.forward_points(rows,{"AAA":120,"BBB":11,"CCC":55},date(2026,10,24))}
        self.assertEqual(sorted(points),["AAA","CCC"]);self.assertEqual(points["AAA"].price_then,100);self.assertTrue(points["AAA"].below_buffer)
        self.assertAlmostEqual(points["AAA"].forward_return,20);self.assertAlmostEqual(points["AAA"].annualized_return,(1.2**(365.25/652)-1)*100)
        self.assertAlmostEqual(points["CCC"].annualized_return,10);self.assertFalse(points["CCC"].below_buffer)
    def test_saved_history_supplies_the_buffer_price(self):
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);database=LocalDatabase(handle.name);self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name));self.addCleanup(database.close)
        result=value_stock(compounder(),monte_carlo_iterations=0);database.save_valuation(result)
        self.assertAlmostEqual(database.tracking_rows()[0]["margin_price"],result.margin_price)
        from datetime import date
        points,errors=backtest.track_saved_valuations(database,date.today());self.assertEqual(points,[]);self.assertIn("30 days old",errors[0])
    def test_latest_closes_reads_a_batched_download(self):
        import pandas as pd
        frame=pd.DataFrame({("Close","AAA"):[10.0,11.0],("Close","BBB"):[5.0,None]},index=pd.date_range("2026-10-22",periods=2))
        with unittest.mock.patch("yfinance.download",return_value=frame):self.assertEqual(data_provider.latest_closes(["AAA","BBB"]),{"AAA":11.0,"BBB":5.0})

class SecBacktestTests(unittest.TestCase):
    def test_sec_history_lets_backtests_reach_further_back(self):
        years=[f"{year}-12-31" for year in range(2025,2017,-1)];long={key:list(values)+[value*.8 for value in values] if all(isinstance(value,(int,float)) for value in values) else list(values)+list(values) for key,values in STATEMENTS.items()}
        months=[f"{2016+index//12}-{index%12+1:02d}-28" for index in range(120)];prices=[20*(1.01**index) for index in range(120)]
        data=compounder(long_statement_years=years,long_statements=long,long_price_dates=months,long_prices=prices,long_adjusted_prices=prices)
        yahoo_only,_=backtest.backtest_stock(compounder(long_price_dates=months,long_prices=prices,long_adjusted_prices=prices),7)
        points,errors=backtest.backtest_stock(data,7)
        self.assertEqual(len(yahoo_only),3);self.assertEqual(len(points),7);self.assertFalse(errors);self.assertEqual(points[-1].fiscal_year_end,"2018-12-31")

class EngineFiveOneTests(unittest.TestCase):
    def test_terminal_growth_capped_by_risk_free_and_halved_when_shrinking(self):
        self.assertAlmostEqual(default_assumptions(compounder(risk_free_rate=.02)).terminal_growth,.02)
        self.assertAlmostEqual(default_assumptions(compounder(revenue_history=[700,800,900,1000])).terminal_growth,.0125)
    def test_growth_ceiling_tightens_with_size(self):
        hot=dict(growth_estimate=.4,analyst_growth=.4)
        self.assertAlmostEqual(default_assumptions(compounder(market_cap=3e11,**hot)).growth,.10)
        self.assertAlmostEqual(default_assumptions(compounder(market_cap=5e10,**hot)).growth,.13)
        self.assertAlmostEqual(default_assumptions(compounder(**hot)).growth,.16)
    def test_research_is_capitalized(self):
        from fundamentals import research_capital
        data=compounder(statements={**STATEMENTS,"research_development":[100,90,80,70]})
        # Five-year life; the year before the oldest report is assumed equal to it: asset 100+72+48+28+14, amortization (90+80+70+70+70)/5.
        for actual,expected in zip(research_capital(data)[0],(100,262,76)):self.assertAlmostEqual(actual,expected)
        with_rd,plain=build_context(data).drivers,build_context(compounder()).drivers
        self.assertAlmostEqual(with_rd.research_margin,(100-76)*(1-with_rd.tax_rate)/1000);self.assertAlmostEqual(with_rd.invested_capital,plain.invested_capital+262)
        self.assertGreater(with_rd.reinvestment_rate,plain.reinvestment_rate)
    def test_one_roic_definition_in_business_quality(self):
        from fundamentals import effective_tax_rate, roic_history
        from valuation import business_quality_assessment
        data=compounder();expected=roic_history(data,effective_tax_rate(data,.24))[0];_score,flags=business_quality_assessment(data,.09)
        self.assertTrue(any(f"Estimated ROIC ({expected:.1%})" in flag for flag in flags))
    def test_bank_residual_income_uses_reported_payout(self):
        from valuation import residual_income_value
        bank=dict(sector="Financial Services",industry="Banks - Regional",eps=8,book_value_per_share=60);a=Assumptions(growth=.1,discount_rate=.12,terminal_growth=.04,years=10,high_growth_years=5)
        self.assertGreater(residual_income_value(compounder(dividend_payout=.8,**bank),a),residual_income_value(compounder(dividend_payout=.2,**bank),a))
    def test_utility_uses_dividend_discount_model(self):
        result=value_stock(compounder(sector="Utilities",industry="Utilities - Regulated Electric",dividend_payout=.65),monte_carlo_iterations=0)
        self.assertEqual(result.model_labels["graham"],"Dividend discount model");self.assertGreater(result.scenarios["Base"].graham,0);self.assertFalse(result.fallback_valuation)
    def test_loss_maker_gets_peer_ev_sales(self):
        data=StockData(symbol="LOSS",company="Loss",market="US",currency="USD",price=5,shares=100,free_cash_flow=-50,eps=-.4,book_value_per_share=3,sector="Technology",revenue_history=[1000,800,600],peer_median_ev_revenue=2.0)
        self.assertAlmostEqual(build_context(data).relative_components["Peer EV/Sales"],2.0*1000/100)
    def test_peer_pe_read_from_growth_line_within_peer_range(self):
        fit=[10,50,0,.3]
        self.assertAlmostEqual(build_context(compounder(peer_median_pe=15,peer_pe_growth_fit=fit,analyst_growth=.2)).relative_components["Peer P/E"],(10+50*.2)*1.9)
        self.assertAlmostEqual(build_context(compounder(peer_median_pe=15,peer_pe_growth_fit=fit,analyst_growth=.9)).relative_components["Peer P/E"],(10+50*.3)*1.9)
    def test_reit_adds_own_price_to_ffo_history(self):
        self.assertIn("Own P/FFO history",build_context(compounder(sector="Real Estate",industry="REIT - Residential")).relative_components)

class ForensicScoreTests(unittest.TestCase):
    def test_strong_company_scores(self):
        data=compounder()
        self.assertEqual(piotroski_f_score(data)["score"],9);self.assertEqual(altman_z_score(data,6000)["zone"],"Safe");self.assertFalse(beneish_m_score(data)["flag"])
    def test_manipulation_and_distress_patterns(self):
        stressed={**STATEMENTS,"receivables":[450,135,120,110],"operating_cash_flow":[-80,230,200,180],"net_income":[-50,165,140,125],"revenue":[1000,700,650,600],"retained_earnings":[-900,-700,-500,-300],"current_assets":[300,560,520,480],"current_liabilities":[700,290,280,270],"ebit":[20,220,190,170]}
        data=compounder(statements=stressed)
        self.assertTrue(beneish_m_score(data)["flag"]);self.assertEqual(altman_z_score(data,6000)["zone"],"Distress");self.assertLessEqual(piotroski_f_score(data)["score"],4)
        healthy=value_stock(compounder(),monte_carlo_iterations=0);weak=value_stock(data,monte_carlo_iterations=0)
        self.assertGreater(weak.risk_score,healthy.risk_score);self.assertGreater(weak.governance_risk_score,healthy.governance_risk_score)
    def test_promoter_pledge_raises_governance_risk(self):
        clean=value_stock(compounder(market="NSE",currency="INR",promoter_pledge=0.0),monte_carlo_iterations=0);pledged=value_stock(compounder(market="NSE",currency="INR",promoter_pledge=.30),monte_carlo_iterations=0)
        self.assertGreaterEqual(pledged.governance_risk_score,clean.governance_risk_score+20);self.assertTrue(any("pledge is high" in flag for flag in pledged.governance_flags))

class LongHistoryTests(unittest.TestCase):
    def test_cagr_counts_blank_and_loss_years_in_the_span(self):
        from fundamentals import cagr
        self.assertAlmostEqual(cagr([133.1,None,110,100]),.10);self.assertAlmostEqual(cagr([133.1,-5,110,100]),.10);self.assertAlmostEqual(cagr([121,110,100]),.10);self.assertIsNone(cagr([100,None,90]))
    def test_screener_margins_are_level_matched_to_yahoo(self):
        long=[.10,.10,.12,.08,.10,.11,.09];periods=["Mar 2025","Mar 2024","Mar 2023","Mar 2022","Mar 2021","Mar 2020","Mar 2019"]
        adjusted=level_adjusted_long_median(long,periods,["2025-03-31","2024-03-31"],[.08,.08])
        self.assertAlmostEqual(adjusted,.10*.8);self.assertIsNone(level_adjusted_long_median(long,periods,["2018-03-31"],[.08]))
    def test_screener_tables_long_history_and_npa(self):
        html="""<section><h2>Profit &amp; Loss</h2><table><tr><th></th><th>Mar 2024</th><th>Mar 2025</th><th>TTM</th></tr><tr><td>Sales +</td><td>1,000</td><td>1,200</td><td>1,300</td></tr><tr><td>Operating Profit</td><td>200</td><td>240</td><td>260</td></tr><tr><td>Depreciation</td><td>50</td><td>60</td><td>62</td></tr><tr><td>Net Profit +</td><td>100</td><td>132</td><td>140</td></tr><tr><td>Tax %</td><td>25%</td><td>26%</td><td></td></tr></table></section>
        <section><h2>Ratios</h2><table><tr><th></th><th>Mar 2024</th><th>Mar 2025</th></tr><tr><td>ROCE %</td><td>18%</td><td>20%</td></tr><tr><td>Cash Conversion Cycle</td><td>40</td><td>55</td></tr></table></section>
        <section><h2>Quarterly Results</h2><table><tr><th></th><th>Dec 2025</th><th>Mar 2026</th></tr><tr><td>Gross NPA %</td><td>1.40%</td><td>1.33%</td></tr><tr><td>Net NPA %</td><td>0.45%</td><td>0.43%</td></tr></table></section>"""
        with unittest.mock.patch.object(india_sources,"_screener_page",return_value=(html,"url","")):
            india_sources.fetch_screener_tables.cache_clear();tables=india_sources.fetch_screener_tables("TEST.NS")
        history,periods=india_sources.screener_long_history(tables)
        self.assertEqual(periods,["Mar 2025","Mar 2024"]);self.assertAlmostEqual(history["ebit_margin"][0],(240-60)/1200);self.assertAlmostEqual(history["net_margin"][1],.1);self.assertAlmostEqual(history["tax_rate"][0],.26)
        self.assertEqual(history["roce"],[.20,.18]);self.assertEqual(history["cash_conversion_cycle"],[55,40])
        quality=india_sources.screener_asset_quality(tables);self.assertAlmostEqual(quality["gross_npa"],.0133);self.assertAlmostEqual(quality["net_npa"],.0043)
        india_sources.fetch_screener_tables.cache_clear()

class DataProviderHelperTests(unittest.TestCase):
    def test_aligned_statements_regression_beta_and_market_parameters(self):
        import pandas as pd
        income=pd.DataFrame({pd.Timestamp("2025-12-31"):[1000,250],pd.Timestamp("2024-12-31"):[900,None]},index=["Total Revenue","EBIT"])
        cashflow=pd.DataFrame({pd.Timestamp("2025-12-31"):[-50],pd.Timestamp("2024-12-30"):[-45]},index=["Capital Expenditure"])
        years,statements=data_provider._aligned_statements(income,None,cashflow)
        self.assertEqual(years,["2025-12-31","2024-12-31"]);self.assertEqual(statements["ebit"],[250,None]);self.assertEqual(statements["capital_expenditure"],[-50,-45])
        months=[f"{2021+index//12}-{index%12+1:02d}" for index in range(40)];market=[100*(1.01**index)*(1.03 if index%2 else .98) for index in range(40)]
        stock=[100]
        for index in range(1,40):stock.append(stock[-1]*(1+1.5*(market[index]/market[index-1]-1)))
        beta,error=data_provider._regression_beta([month+"-28" for month in months],stock,dict(zip(months,market)));self.assertAlmostEqual(beta,1.5,places=6);self.assertLess(error,1e-6)  # exact linear fit: no estimation error
        noisy=[stock[0]]+[stock[index]*(1+(.02 if index%3 else -.03)) for index in range(1,40)]
        self.assertGreater(data_provider._regression_beta([month+"-28" for month in months],noisy,dict(zip(months,market)))[1],.01)
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);database=LocalDatabase(handle.name);self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name))
        database.set_setting("live_us_risk_free",False);database.set_setting("risk_free_us",.04);database.set_setting("erp_india",.06);database.set_setting("scenario_weights",[.2,.6,.2]);database.set_setting("damodaran_erp",False)
        us=data_provider.apply_market_parameters(StockData(symbol="A",company="A",market="US",currency="USD",price=1),database);india=data_provider.apply_market_parameters(StockData(symbol="B.NS",company="B",market="NSE",currency="INR",price=1),database)
        self.assertEqual(us.risk_free_rate,.04);self.assertEqual(us.scenario_weights,[.2,.6,.2]);self.assertEqual(india.equity_risk_premium,.06);self.assertEqual(india.risk_free_rate,.065)
        self.assertTrue(any(entry.metric=="Risk-free rate" for entry in us.lineage))
        # Damodaran path (live table unreachable → built-in January 2026 values): total premium, yield less the sovereign default spread.
        database.set_setting("damodaran_erp",True)
        with unittest.mock.patch.object(data_provider,"_damodaran_country_premiums",return_value=None):
            india=data_provider.apply_market_parameters(StockData(symbol="B.NS",company="B",market="NSE",currency="INR",price=1),database)
        self.assertAlmostEqual(india.equity_risk_premium,.0708);self.assertAlmostEqual(india.risk_free_rate,.065-.0187);self.assertAlmostEqual(india.country_default_spread,.0187)
        self.assertIn("Damodaran",next(entry.source for entry in india.lineage if entry.metric=="Equity risk premium"));database.close()

    def test_damodaran_country_table_parsing(self):
        html="<table><tr><td>Country</td><td>Rating</td><td>Spread</td><td>CRP</td><td>ERP</td></tr><tr><td>India</td><td>Baa3</td><td>1.87%</td><td>2.85%</td><td>7.08%</td></tr><tr><td>United States</td><td>Aa1</td><td>0.23%</td><td>0.23%</td><td>4.46%</td></tr></table>"
        parsed=data_provider._country_premiums_from_html(html)
        self.assertAlmostEqual(parsed["IN"]["erp"],.0708);self.assertAlmostEqual(parsed["US"]["default_spread"],.0023);self.assertIsNone(data_provider._country_premiums_from_html("<table></table>"))

    def test_peer_regression_line(self):
        fit=data_provider._fit_line([(.0,10),(.1,15),(.2,20),(.3,25),(.4,30)])
        self.assertAlmostEqual(fit[0],10);self.assertAlmostEqual(fit[1],50);self.assertEqual(fit[2:],[0,.4]);self.assertIsNone(data_provider._fit_line([(.1,10)]*6))

class BacktestTests(unittest.TestCase):
    def test_point_in_time_snapshot_and_summary(self):
        data=compounder(long_history={"ebit_margin":[.25,.24,.23,.22,.21,.2,.2],"fii":[.2]*12,"dii":[.1]*12},long_history_periods=["Dec 2025","Dec 2024","Dec 2023","Dec 2022","Dec 2021","Dec 2020","Dec 2019"])
        snapshot,then,now,as_of,fiscal_end,months=backtest.as_of_snapshot(data,1)
        self.assertEqual(fiscal_end,"2024-12-31");self.assertEqual(as_of,"2025-03-31");self.assertEqual(snapshot.statement_years,YEARS[1:]);self.assertEqual(snapshot.revenue_history,[900,810,730])
        self.assertTrue(all(date<=as_of for date in snapshot.long_price_dates));self.assertEqual(snapshot.long_history_periods[0],"Dec 2024");self.assertEqual(snapshot.long_history["ebit_margin"][0],.24)
        self.assertLess(then,now);self.assertGreater(months,0);self.assertIsNone(snapshot.analyst_growth)
        points,errors=backtest.backtest_stock(data,2);self.assertEqual(len(points),2);self.assertFalse(errors)
        self.assertAlmostEqual(backtest.spearman([1,2,3,4],[10,20,30,40]),1.0);self.assertAlmostEqual(backtest.spearman([1,2,3,4],[40,30,20,10]),-1.0)
        summary=backtest.summarize(points);self.assertEqual(summary["observations"],2);self.assertIn("current values",summary["note"])
    def test_short_history_is_reported_not_raised(self):
        points,errors=backtest.backtest_stock(StockData(symbol="NEW",company="New",market="US",currency="USD",price=10),3)
        self.assertEqual(points,[]);self.assertTrue(errors)

class AssumptionCompatibilityTests(unittest.TestCase):
    def test_reviewed_high_growth_years_is_recorded_as_override(self):
        data=compounder();automatic=default_assumptions(data);reviewed=replace(automatic,high_growth_years=4)
        result=value_stock(data,reviewed,automatic_assumptions=automatic,monte_carlo_iterations=0)
        self.assertIn("high_growth_years",result.manual_overrides);self.assertIn("for 4 years",result.reverse_dcf_note)
        with self.assertRaisesRegex(ValueError,"Scenario weights"):value_stock(data,replace(automatic,scenario_weights=(0,0,0)),monte_carlo_iterations=0)
        self.assertEqual(Assumptions(.05,.1,.02).high_growth_years,5)

if __name__=="__main__":unittest.main()
