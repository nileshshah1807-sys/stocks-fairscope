import os
import sys
import tempfile
import unittest

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
try:
    from openpyxl import Workbook
    EXCEL_AVAILABLE=True
except ImportError:
    EXCEL_AVAILABLE=False
from batch_import import import_stock_list


@unittest.skipUnless(EXCEL_AVAILABLE,"openpyxl unavailable")
class ExcelImportTests(unittest.TestCase):
    def path(self):
        handle=tempfile.NamedTemporaryFile(suffix=".xlsx",delete=False);handle.close();self.addCleanup(lambda:os.path.exists(handle.name) and os.unlink(handle.name));return handle.name
    def test_stock_list_xlsx(self):
        path=self.path();book=Workbook();sheet=book.active;sheet.append(["Symbol","Market","Quantity","Target Weight"]);sheet.append(["AAPL","US",10,60]);sheet.append(["RELIANCE","NSE",20,40]);book.save(path);items=import_stock_list(path);self.assertEqual(len(items),2);self.assertEqual(items[1].market,"NSE");self.assertEqual(items[0].quantity,10)

if __name__=="__main__":unittest.main()
