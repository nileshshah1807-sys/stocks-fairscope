import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import corporate_monitor
from corporate_monitor import CorporateEvent, CorporateMonitorStore, fetch_screener_documents, fetch_sec_filings


class Response:
    def __init__(self,data=None,text="",ok=True):self._data=data;self.text=text;self.ok=ok
    def raise_for_status(self):
        if not self.ok:raise RuntimeError("http")
    def json(self):return self._data

class CorporateMonitorTests(unittest.TestCase):
    def setUp(self):
        handle=tempfile.NamedTemporaryFile(suffix=".db",delete=False);handle.close();os.unlink(handle.name);self.path=handle.name;self.store=CorporateMonitorStore(self.path);corporate_monitor._sec_tickers.cache_clear()
    def tearDown(self):
        self.store.close()
        if os.path.exists(self.path):os.unlink(self.path)
    def test_store_deduplicates_events(self):
        entry=self.store.add("AAPL","US","Apple");event=CorporateEvent(0,0,"key","2026-08-18","high","8-K","SEC EDGAR","AAPL","Material event","https://sec.gov","")
        self.assertEqual(len(self.store.add_events(entry,[event])),1);self.assertEqual(len(self.store.add_events(entry,[event])),0);self.assertEqual(self.store.unread_count(),1);self.store.mark_all_read();self.assertEqual(self.store.unread_count(),0);self.store.remove(entry.id);self.assertEqual(self.store.events(),[])
    def test_sec_filings_parser(self):
        tickers={"0":{"cik_str":320193,"ticker":"AAPL","title":"Apple Inc."}};submissions={"filings":{"recent":{"form":["10-K","8-K"],"filingDate":["2026-08-01","2026-08-10"],"accessionNumber":["0001-26-000001","0001-26-000002"],"primaryDocument":["a10k.htm","a8k.htm"],"primaryDocDescription":["Annual report","Current report"]}}}
        with patch.object(corporate_monitor.requests,"get",side_effect=[Response(tickers),Response(submissions)]):events,error,cik=fetch_sec_filings("AAPL","user@example.com")
        self.assertFalse(error);self.assertEqual(cik,"0000320193");self.assertEqual(len(events),2);self.assertTrue(any(event.event_type=="8-K" and event.severity=="high" for event in events))
    def test_bse_no_record_response(self):
        with patch.object(corporate_monitor,"_resolve_bse_code",return_value="530017"),patch.object(corporate_monitor.requests,"get",return_value=Response("No Record Found!")):
            events,error=corporate_monitor.fetch_bse_announcements("SIL.BO")
        self.assertEqual(events,[]);self.assertFalse(error)
    def test_screener_documents_parser(self):
        html='<section><h2>Documents</h2><p>18 Aug 2026 <a href="/company/TEST/annual-reports/test.pdf">Annual Report 2026</a></p></section>'
        with patch.object(corporate_monitor,"_screener_page",return_value=(html,"url","")):events,error=fetch_screener_documents("TEST.NS")
        self.assertFalse(error);self.assertEqual(len(events),1);self.assertEqual(events[0].event_type,"Annual report");self.assertTrue(events[0].url.startswith("https://"))
    def test_exchange_dates_are_normalized_to_iso(self):
        self.assertEqual(corporate_monitor._iso_date("26-Sep-2024 19:34:12"),"2024-09-26");self.assertEqual(corporate_monitor._iso_date("15-Jul-2024"),"2024-07-15");self.assertEqual(corporate_monitor._iso_date("2024-09-26T19:34:12.13"),"2024-09-26");self.assertEqual(corporate_monitor._iso_date(None),"")
    def test_sec_class_share_ticker_matches(self):
        tickers={"0":{"cik_str":1067983,"ticker":"BRK-B","title":"Berkshire Hathaway"}};submissions={"filings":{"recent":{}}}
        with patch.object(corporate_monitor.requests,"get",side_effect=[Response(tickers),Response(submissions)]):events,error,cik=fetch_sec_filings("BRK.B","user@example.com")
        self.assertFalse(error);self.assertEqual(cik,"0001067983")
    def test_yahoo_actions_use_exchange_suffix(self):
        entry=self.store.add("RELIANCE","NSE","Reliance")
        with patch.object(corporate_monitor,"fetch_yahoo_actions",return_value=([],"")) as yahoo,patch.object(corporate_monitor,"fetch_screener_documents",return_value=([],"")),patch.object(corporate_monitor,"fetch_nse_events",return_value=([],"")):corporate_monitor.monitor_entry(entry)
        yahoo.assert_called_once_with("RELIANCE.NS")

if __name__=="__main__":unittest.main()
