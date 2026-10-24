import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from batch_import import export_batch_csv, import_stock_list
from valuation import StockData, value_stock


class BatchImportTests(unittest.TestCase):
    def _temp(self, text, suffix=".csv"):
        handle=tempfile.NamedTemporaryFile("w",encoding="utf-8",suffix=suffix,delete=False,newline="")
        handle.write(text); handle.close(); self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name)); return handle.name

    def test_header_markets_and_duplicates(self):
        path=self._temp("Ticker,Exchange\nAAPL,NASDAQ\nreliance,NSE\nRELIANCE,NSE\n500325,BSE\n")
        items=import_stock_list(path)
        self.assertEqual([(x.symbol,x.market) for x in items],[('AAPL','US'),('RELIANCE','NSE'),('500325','BSE')])

    def test_portfolio_columns(self):
        path=self._temp("Symbol,Market,Quantity,Cost Basis,Target Weight\nAAPL,US,10,180,25\n")
        item=import_stock_list(path)[0]
        self.assertEqual(item.quantity,10); self.assertEqual(item.cost_basis,180); self.assertEqual(item.target_weight,25)

    def test_csv_formula_injection_is_escaped(self):
        from batch_import import write_csv_row
        path=self._temp("")
        with open(path,"w",encoding="utf-8",newline="") as handle:
            write_csv_row(csv.writer(handle),["=2+2","@command","-12.5","+3.0%"])
        with open(path,encoding="utf-8") as handle: row=next(csv.reader(handle))
        self.assertEqual(row[0],"'=2+2");self.assertEqual(row[1],"'@command")
        self.assertEqual(row[2],"-12.5");self.assertEqual(row[3],"+3.0%")

    def test_headerless_and_suffix_inference(self):
        path=self._temp("MSFT\nTCS.NS\n500325.BO\n", ".txt")
        items=import_stock_list(path)
        self.assertEqual([x.market for x in items],["US","NSE","BSE"])

    def test_export_results(self):
        item=import_stock_list(self._temp("Symbol,Market\nTEST,US\n"))[0]
        data=StockData(symbol="TEST",company="Test",market="US",currency="USD",price=100,shares=100,free_cash_flow=900,eps=6,book_value_per_share=30,growth_estimate=.09)
        result=value_stock(data); out=self._temp("")
        export_batch_csv([(item,result,"")],out)
        with open(out,encoding="utf-8-sig") as h: rows=list(csv.reader(h))
        self.assertEqual(len(rows[0]),len(rows[1]));self.assertEqual(rows[1][0],"TEST"); self.assertEqual(rows[1][rows[0].index("Currency")],"USD")
        self.assertNotIn("Portfolio Weight %",rows[0]);self.assertNotIn("Risk Contribution %",rows[0]);self.assertEqual(rows[1][rows[0].index("Assumption Preset")],"Automatic defaults");self.assertEqual(rows[1][rows[0].index("Manual Override Count")],"0")

if __name__ == "__main__": unittest.main()
