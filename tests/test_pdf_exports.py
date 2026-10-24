import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
try:
    from pypdf import PdfReader
    PDF_AVAILABLE=True
except ImportError:
    PDF_AVAILABLE=False
from batch_import import BatchItem
from batch_pdf_report import create_batch_pdf
from pdf_report import create_pdf
from valuation import StockData, value_stock
from watchlist_report import create_watchlist_pdf
from watchlist_store import AlertRecord, WatchlistEntry


@unittest.skipUnless(PDF_AVAILABLE,"pypdf development dependency unavailable")
class PdfExportTests(unittest.TestCase):
    def result(self,symbol="TEST"):
        start=date.today()-timedelta(days=59);dates=[(start+timedelta(days=i)).isoformat() for i in range(60)];prices=[90+i*.2 for i in range(60)];data=StockData(symbol=symbol,company="PDF Test Company",market="US",currency="USD",price=prices[-1],shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,sector="Technology",fcf_history=[800,760,720],revenue_history=[4000,3800,3600],net_income_history=[500,470,440],price_history=prices,price_dates=dates);return value_stock(data),start
    def temporary(self):
        handle=tempfile.NamedTemporaryFile(suffix=".pdf",delete=False);handle.close();self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name));return handle.name
    def assert_pdf(self,path,min_pages=1):
        with open(path,"rb") as handle:self.assertEqual(handle.read(5),b"%PDF-")
        reader=PdfReader(path);self.assertGreaterEqual(len(reader.pages),min_pages);self.assertGreater(os.path.getsize(path),3000)
    def test_detailed_pdf(self):
        result,_=self.result();path=self.temporary();create_pdf(result,path);self.assert_pdf(path,2);text="\n".join(page.extract_text() or "" for page in PdfReader(path).pages);self.assertIn("Independent Fair Value",text);self.assertIn("Contents",text);self.assertIn("Executive summary",text);self.assertIn("Model audit trail",text);self.assertIn("Data lineage",text);self.assertIn("valuation buffer",text.lower());self.assertIn("not a buy/sell recommendation",text.lower());self.assertNotIn("MOS PRICE",text);self.assertGreater(len(PdfReader(path).outline),5)
    def test_batch_pdf(self):
        result,_=self.result();path=self.temporary();create_batch_pdf([(BatchItem("TEST","US"),result,"")],path);self.assert_pdf(path)
    def test_colour_watchlist_pdf(self):
        result,_=self.result();entry=WatchlistEntry(1,"Main","TEST","US","PDF Test Company",90,20,60,60,10,True,result.data.price,result.fair_value,"2026-08-19T10:00:00","Checked");alert=AlertRecord(1,1,"2026-08-19T10:00:00","high","custom_price","TEST","Price reached target",False);path=self.temporary();create_watchlist_pdf([entry],[alert],{1:result},path);self.assert_pdf(path);text="\n".join(page.extract_text() or "" for page in PdfReader(path).pages);self.assertIn("Complete alert history",text);self.assertIn("Valuation snapshot",text)
    def test_markup_characters_are_rendered_literally(self):
        result,_=self.result();result.data.company="AT&T Inc.";path=self.temporary();error="Could not retrieve BAD: NewConnectionError('<urllib3.connection.HTTPSConnection object>') <b>unclosed"
        create_batch_pdf([(BatchItem("T","US"),result,""),(BatchItem("BAD","US"),None,error)],path);text="\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        flat=text.replace("\n","");self.assertIn("AT&T Inc.",flat);self.assertNotIn("AT&T;",flat);self.assertIn("<urllib3.connection.HTTPSConnection",flat);self.assertIn("<b>unclosed",flat)
        entry=WatchlistEntry(1,"Main","T","US","AT&T Inc.",None,20,60,60,10,True,None,None,"2026-08-19T10:00:00","Error: <b>unclosed");path=self.temporary();create_watchlist_pdf([entry],[],{},path);text="\n".join(page.extract_text() or "" for page in PdfReader(path).pages);self.assertIn("<b>unclosed",text)
    def test_ampersand_ticker_in_full_report(self):
        result,_=self.result("M&M.NS");path=self.temporary();create_pdf(result,path);text="".join(page.extract_text() or "" for page in PdfReader(path).pages[:3]).replace("\n","")
        self.assertIn("M&M.NS",text);self.assertNotIn("M&M.NS;",text)

if __name__=="__main__":unittest.main()
