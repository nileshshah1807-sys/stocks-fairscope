import os
import sys
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QFrame, QLabel

    from app_qt import APP_VERSION, AccessibleMessageDialog, FairScopeWindow, WatchlistAlertDialog
    QT_AVAILABLE=True
except (ImportError,OSError):
    QT_AVAILABLE=False

@unittest.skipUnless(QT_AVAILABLE,"PySide6 or required Qt system libraries unavailable")
class QtInterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_window_and_workspaces(self):
        window=FairScopeWindow()
        self.assertEqual(window.stack.count(),17);self.assertEqual(window.nav.count(),17)
        self.assertIn("STOCKS FAIRSCOPE",window.windowTitle())
        self.assertEqual(APP_VERSION,"10.4.1")
        window.close()
    def test_visual_charts_receive_analysis_result(self):
        from valuation import StockData, value_stock
        data=StockData(symbol="TEST",company="Test Corp",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,sector="Technology",fcf_history=[800,760,710,680],revenue_history=[4000,3700,3400,3100],net_income_history=[500,450,410,380],price_history=[80+i*.1 for i in range(200)])
        result=value_stock(data);window=FairScopeWindow();window.result=result;window.render_result()
        self.assertIs(window.price_value_chart.result,result);self.assertIs(window.model_chart.result,result)
        self.assertEqual(window.sensitivity.rowCount(),5)
        self.assertTrue(window.sensitivity.item(2,3).background().color().isValid())
        window.close()
    def test_model_audit_page_and_integrity(self):
        from valuation import StockData, value_stock, verify_audit_hash
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[80+i*.1 for i in range(100)])
        result=value_stock(data);window=FairScopeWindow();window.result=result;window.render_result()
        self.assertEqual(window.audit_table.rowCount(),len(result.audit_events));self.assertTrue(verify_audit_hash(result));self.assertEqual(window.audit_metrics[3].value.text(),"Valid");self.assertTrue(window.audit_export_btn.isEnabled());window.close()

    def test_data_lineage_table_and_citation_state(self):
        from valuation import DataLineageEntry, StockData, value_stock
        lineage=[DataLineageEntry("Market price","USD 100.00","Yahoo Finance","https://finance.yahoo.com/quote/TEST","2026-08-16","2026-08-16 10:00 IST","Latest close","Selected"),DataLineageEntry("Normalized FCF","USD 800.00","Yahoo Finance","https://finance.yahoo.com/quote/TEST/cash-flow","2023–2025","2026-08-16 10:00 IST","Median of annual FCF","Normalized")]
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[80+i*.1 for i in range(100)],data_sources=["Yahoo Finance"],lineage=lineage)
        result=value_stock(data);window=FairScopeWindow();window.result=result;window.render_result()
        self.assertEqual(window.lineage_table.rowCount(),2);self.assertEqual(window.lineage_table.item(0,0).text(),"Market price");self.assertTrue(window.lineage_urls[0].startswith("https://"))
        window.lineage_table.selectRow(0);window.lineage_selection_changed();self.assertTrue(window.lineage_open_btn.isEnabled());window.close()
    def test_diagnostics_workspace(self):
        import tempfile

        from diagnostics import DiagnosticManager
        with tempfile.TemporaryDirectory() as directory:
            window=FairScopeWindow();window.diagnostics=DiagnosticManager(directory);window.diagnostics.error("Test","Sanitized test error");window.load_diagnostics();self.assertEqual(window.diagnostic_table.rowCount(),1);self.assertEqual(window.diagnostic_metrics[0].value.text(),"1");window.close()

    def test_local_database_workspace(self):
        import os
        import tempfile

        from local_database import LocalDatabase
        from valuation import StockData, value_stock
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);database=LocalDatabase(handle.name);window=FairScopeWindow();window.local_database=database;data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600]);database.save_stock(data);database.save_valuation(value_stock(data));window.load_database_page();self.assertEqual(window.cache_table.rowCount(),1);self.assertEqual(window.history_table.rowCount(),1);window.close();database.close();self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name))

    def test_corporate_monitor_workspace(self):
        import os
        import tempfile

        from corporate_monitor import CorporateEvent, CorporateMonitorStore
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);window=FairScopeWindow();window.corporate_store.close();window.corporate_store=CorporateMonitorStore(handle.name);self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name));entry=window.corporate_store.add("AAPL","US","Apple Inc.");event=CorporateEvent(0,0,"event-key","2026-08-18","high","8-K","SEC EDGAR","AAPL","Current report","https://www.sec.gov/example","");window.corporate_store.add_events(entry,[event]);window.load_corporate_monitor();self.assertEqual(window.corporate_company_table.rowCount(),1);self.assertEqual(window.corporate_event_table.rowCount(),1);self.assertEqual(window.corporate_store.unread_count(),1);window.close()

    def test_accessible_message_dialog_uses_explicit_high_contrast_colours(self):
        dialog=AccessibleMessageDialog("Watchlist report saved",r"C:\Users\NILESH\Desktop\FairScope_Watchlist.pdf",kind="success")
        self.assertIn("QDialog{background:#FFFFFF;color:#14243A;}",dialog.styleSheet())
        self.assertIn("#E7F6EE",dialog.styleSheet())
        body=dialog.findChild(QLabel,"messageBody")
        self.assertIsNotNone(body);self.assertIn("FairScope_Watchlist.pdf",body.text());self.assertTrue(body.textInteractionFlags()&Qt.TextSelectableByMouse)
        dialog.close()

    def test_watchlist_alert_popup_has_readable_colours(self):
        from watchlist_store import AlertRecord
        alerts=[AlertRecord(1,1,"2026-08-20T10:00:00","high","custom_price","TEST","Price reached target",False),AlertRecord(2,1,"2026-08-20T10:01:00","info","upside","TEST","Upside threshold reached",False)];dialog=WatchlistAlertDialog(alerts);self.assertIn("background:#F4F7FB",dialog.styleSheet());cards=dialog.findChildren(QFrame,"alertCard");self.assertEqual(len(cards),2);self.assertTrue(any("#FDE8E7" in card.styleSheet() for card in cards));dialog.close()

    def test_watchlist_and_alert_workspace(self):
        import os
        import tempfile

        from valuation import StockData, value_stock
        from watchlist_store import WatchlistStore
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name)
        window=FairScopeWindow();window.watchlist_store.close();window.watchlist_store=WatchlistStore(handle.name);self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name));data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=50,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[40+i*.1 for i in range(80)]);result=value_stock(data);entry=window.watchlist_store.add("TEST","US","Test");window.watchlist_store.update_settings(entry.id,60,10,60,60,10,True);window.watchlist_store.evaluate(window.watchlist_store.entries()[0],result);window.watchlist_store.update_result(entry.id,result,result.label);window.watchlist_results[entry.id]=result;window.load_watchlist();self.assertEqual(window.watchlist_table.rowCount(),1);self.assertGreater(window.alert_table.rowCount(),0);self.assertGreater(window.watchlist_store.unread_count(),0);window.close()

    def test_external_review_creates_lineage_and_child_audit(self):
        from valuation import StockData, value_stock, verify_audit_hash
        data=StockData(symbol="TEST.NS",company="Test",market="NSE",currency="INR",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[80,90,100])
        result=value_stock(data);window=FairScopeWindow();window.result=result;window.render_result();window.load_assumptions(result,True);window.load_financial_company(result,True);window.load_external_review(result,True);old_id=result.analysis_id
        window.external_inputs["book_value_per_share"].setValue(30);window.external_url.setText("https://www.moneycontrol.com/example");window.external_period.setText("FY2026");self.assertTrue(window.external_apply_btn.isEnabled());window.apply_external_review()
        self.assertEqual(window.result.data.book_value_per_share,30);self.assertEqual(window.result.parent_analysis_id,old_id);self.assertEqual(len(window.result.data.external_reviews),1);self.assertTrue(any(entry.status=="Manual" for entry in window.result.data.lineage));self.assertTrue(verify_audit_hash(window.result));window.close()

    def test_external_revenue_review_moves_fcff_dcf(self):
        from valuation import StockData, value_stock
        statements={"revenue":[1000,900,800,700],"ebit":[200,180,160,140],"depreciation":[30,28,26,24],"capital_expenditure":[-40,-38,-36,-34],"working_capital_change":[-5,-5,-5,-5]}
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=50,shares=100,free_cash_flow=120,eps=1.5,book_value_per_share=8,sector="Technology",revenue_history=[1000,900,800,700],fcf_history=[120,110,100],statements=statements,statement_years=["2025-12-31","2024-12-31","2023-12-31","2022-12-31"])
        result=value_stock(data);self.assertEqual(result.valuation_drivers["basis"],"FCFF");window=FairScopeWindow();window.result=result;window.render_result();window.load_assumptions(result,True);window.load_financial_company(result,True);window.load_external_review(result,True)
        window.external_inputs["revenue"].setValue(2000);window.external_url.setText("https://www.moneycontrol.com/example");window.external_period.setText("FY2025");window.apply_external_review()
        self.assertEqual(window.result.data.statements["revenue"][0],2000);self.assertGreater(window.result.scenarios["Base"].dcf,result.scenarios["Base"].dcf);self.assertEqual(data.statements["revenue"][0],1000);window.close()

    def test_implied_return_card_and_forward_tracking_display(self):
        from backtest import FORWARD_NOTE, BacktestPoint
        from valuation import StockData, value_stock
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=50,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[40+i*.1 for i in range(80)])
        result=value_stock(data,monte_carlo_iterations=0);window=FairScopeWindow();window.result=result;window.render_result()
        self.assertIn(f"{result.implied_return:.1%}",window.dashboard_metrics[4].value.text())
        point=BacktestPoint("AAA","US","Saved valuation","2026-01-10",100,150,50,True,20,20,9,"Forward tracking")
        window.backtest_done(([point],[],FORWARD_NOTE));self.assertEqual(window.backtest_table.rowCount(),1);self.assertIn("no look-ahead bias",window.backtest_summary.text());self.assertEqual(window.backtest_table.item(0,1).text(),"Saved valuation")
        window.backtest_done(([],["No saved valuation is 30 days old yet."],FORWARD_NOTE));self.assertIn("30 days old",window.backtest_summary.text());window.close()

    def test_second_job_cannot_start_while_one_runs(self):
        from unittest.mock import patch

        from batch_import import BatchItem
        window=FairScopeWindow();window._active_workers.append(object());window.symbol.setText("AAPL");window.batch_items=[BatchItem("AAPL","US")]
        with patch.object(window,"launch_controlled_worker") as launch,patch.object(window,"launch_worker") as plain:
            window.analyze();window.analyze_batch();window.run_diagnostic_health()
        launch.assert_not_called();plain.assert_not_called();window._active_workers.clear();window.close()

    def test_specialized_financial_review_and_recalculation(self):
        from valuation import FinancialCompanyMetrics, StockData, value_stock, verify_audit_hash
        metrics=FinancialCompanyMetrics(subtype="Bank",gross_npa=.015,net_npa=.004,capital_adequacy=.18,net_interest_margin=.035,automatic_values={"gross_npa":.015,"net_npa":.004,"capital_adequacy":.18,"net_interest_margin":.035})
        data=StockData(symbol="BANK",company="Bank",market="NSE",currency="INR",price=100,eps=8,book_value_per_share=60,sector="Financial Services",industry="Banks - Regional",return_on_equity=.16,peer_median_pb=1.8,financial_metrics=metrics)
        result=value_stock(data);window=FairScopeWindow();window.result=result;window.render_result();window.load_assumptions(result,True);window.load_financial_company(result,True);old_id=result.analysis_id
        window.financial_inputs["gross_npa"].setValue(3.5);self.assertTrue(window.financial_apply_btn.isEnabled());self.assertTrue(window._financial_changes_pending)
        window.apply_financial_company_data();self.assertAlmostEqual(window.result.data.financial_metrics.gross_npa,.035);self.assertIn("gross_npa",window.result.data.financial_metrics.manual_fields);self.assertEqual(window.result.parent_analysis_id,old_id);self.assertTrue(verify_audit_hash(window.result));window.close()

    def test_assumption_review_presets_locks_and_validation(self):
        from valuation import StockData, value_stock
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.10155,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[80+i*.1 for i in range(100)])
        result=value_stock(data);window=FairScopeWindow();window.result=result;window.render_result();window.load_assumptions(result,reset_values=True)
        self.assertAlmostEqual(window.reviewed_assumptions().growth,result.automatic_assumptions.growth)
        auto_growth=window.inputs["growth"].value();window.assumption_locks["growth"].setChecked(True);window.assumption_preset.setCurrentText("Conservative overlay");window.apply_assumption_preset()
        self.assertEqual(window.inputs["growth"].value(),auto_growth);self.assertGreater(window.inputs["discount"].value(),window.auto_assumption_values["discount"])
        window.assumption_locks["growth"].setChecked(False);window.inputs["growth"].setValue(auto_growth+1)
        self.assertIn("override",window.override_summary.text());self.assertEqual(window.assumption_preset.currentText(),"Custom review")
        window.inputs["dcf_weight"].setValue(50);window.inputs["graham_weight"].setValue(10);window.inputs["relative_weight"].setValue(10)
        self.assertFalse(window.review_recalc_btn.isEnabled());self.assertIn("100%",window.assumption_review_status.text())
        window.close()
    def test_autocomplete_result_and_selection(self):
        from stock_search import StockSearchResult
        window=FairScopeWindow();window._search_generation=3
        result=StockSearchResult("RELIANCE","Reliance Industries Ltd","NSE","NSE","Screener.in")
        window.apply_search_results((result,),3,"rel")
        self.assertEqual(window.search_model.rowCount(),1)
        window.apply_search_choice(result.display)
        self.assertEqual(window.symbol.text(),"RELIANCE")
        self.assertIn("Reliance Industries",window.search_status.text())
        window.close()
    def test_progress_stops_after_worker_completion(self):
        import time

        from app_qt import Worker
        window=FairScopeWindow();window.busy(True,"Testing")
        worker=Worker(lambda:42);window.launch_worker(worker)
        deadline=time.time()+3
        while window._active_workers and time.time()<deadline:
            self.app.processEvents();time.sleep(.01)
        self.app.processEvents()
        self.assertFalse(window._active_workers)
        self.assertTrue(window.progress.isHidden())
        self.assertEqual(window.progress.maximum(),100)
        window.close()
    def test_negative_automatic_growth_is_not_a_pending_override(self):
        from valuation import StockData, value_stock
        data=StockData(symbol="DECL",company="Declining",market="US",currency="USD",price=40,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=-.03,fcf_history=[800,820,850],revenue_history=[3600,3800,4000],price_history=[40+i*.1 for i in range(50)])
        result=value_stock(data);self.assertLess(result.automatic_assumptions.growth,0);window=FairScopeWindow();window.result=result;window.render_result();window.load_assumptions(result,reset_values=True)
        self.assertAlmostEqual(window.inputs["growth"].value(),result.automatic_assumptions.growth*100,places=2);self.assertFalse(window._assumption_changes_pending);self.assertAlmostEqual(window.reviewed_assumptions().growth,result.automatic_assumptions.growth);window.close()
    def test_watchlist_refresh_skips_entries_removed_during_refresh(self):
        import os
        import tempfile

        from valuation import StockData, value_stock
        from watchlist_store import WatchlistStore
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name)
        window=FairScopeWindow();window.watchlist_store.close();window.watchlist_store=WatchlistStore(handle.name);self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name))
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=50,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600]);result=value_stock(data)
        removed=window.watchlist_store.add("GONE","US");kept=window.watchlist_store.add("TEST","US");window.watchlist_store.remove(removed.id)
        window.watchlist_done([(removed,result,""),(kept,None,"timeout")]);self.assertEqual(window.watchlist_table.rowCount(),1);self.assertTrue(window.watchlist_store.entries()[0].last_status.startswith("Error"));window.watchlist_store.close();window.close()

if __name__=="__main__":unittest.main()
