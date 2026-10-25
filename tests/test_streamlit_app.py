import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"packaging"/"huggingface"))
try:
    from streamlit.testing.v1 import AppTest
    STREAMLIT=True
except ImportError:
    STREAMLIT=False


class WebVersionTests(unittest.TestCase):
    @unittest.skipUnless(STREAMLIT,"streamlit is only installed for the web version (web/requirements.txt)")
    def test_ticker_produces_valuation_metrics_and_pdf(self):
        import background_processing
        from valuation import StockData
        dates=[(date(2026,1,1)+timedelta(days=index)).isoformat() for index in range(80)]
        offline=StockData(symbol="TEST",company="Test Corp",market="US",currency="USD",price=50,shares=100,free_cash_flow=800,eps=5,book_value_per_share=25,growth_estimate=.07,fcf_history=[800,760,720],revenue_history=[4000,3800,3600],price_history=[40+index*.1 for index in range(80)],price_dates=dates)
        # The page fetches through the desktop retry helper, which holds its own reference to fetch_stock.
        with patch.object(background_processing,"fetch_stock",return_value=offline):
            app=AppTest.from_file(str(ROOT/"web"/"streamlit_app.py"),default_timeout=120).run()
            app.text_input[0].input("TEST");app.button[0].click();app.run()
        self.assertFalse(app.exception);metrics={metric.label:metric.value for metric in app.metric}
        self.assertEqual(metrics["Market price"],"USD 50.00");self.assertIn("Implied return / year",metrics);self.assertEqual(app.subheader[0].value,"Test Corp · TEST")
        self.assertTrue(any(type(element).__name__=="DownloadButton" for element in app.main))

    def test_space_bundle_is_self_contained(self):
        from build_space import build
        target=build(Path(tempfile.mkdtemp())/"space")
        for name in ("Dockerfile","README.md","requirements.txt","streamlit_app.py","assets/logo_256.png"):self.assertTrue((target/name).is_file(),name)
        self.assertIn("sdk: docker",(target/"README.md").read_text(encoding="utf-8"));self.assertNotIn("PySide6",(target/"requirements.txt").read_text(encoding="utf-8"))
        # Import the engine from the bundle alone (no repository folder on the path), as the Space will.
        # Coverage settings would follow the child process into the bundle folder, where the project's branch-coverage config is absent.
        env={key:value for key,value in os.environ.items() if not key.startswith(("COV_CORE","COVERAGE"))}|{"LOCALAPPDATA":tempfile.mkdtemp(),"XDG_DATA_HOME":tempfile.mkdtemp(),"PYTHONPATH":""}
        check=subprocess.run([sys.executable,"-c","import background_processing, batch_import, data_provider, pdf_report, valuation"],cwd=target,capture_output=True,text=True,env=env)
        self.assertEqual(check.returncode,0,check.stderr[-800:])

if __name__=="__main__":unittest.main()
