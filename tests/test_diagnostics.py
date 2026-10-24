import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from diagnostics import DiagnosticManager


class Response:
    status_code=200
    class Elapsed:
        def total_seconds(self):return .05
    elapsed=Elapsed()

class DiagnosticsTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.manager=DiagnosticManager(self.temp.name,max_bytes=1000,backups=2)
    def tearDown(self):self.temp.cleanup()
    def test_redaction_logging_and_clear(self):
        self.manager.error("Test","Failure for user@example.com","api_key=secret password=hunter2");events=self.manager.events();serialized=json.dumps(events);self.assertNotIn("user@example.com",serialized);self.assertNotIn("secret",serialized);self.assertEqual(self.manager.error_count(),1);self.manager.clear();self.assertEqual(self.manager.events(),[])
    def test_health_database_and_zip(self):
        database=Path(self.temp.name)/"test.db";connection=sqlite3.connect(database);connection.execute("CREATE TABLE sample(id INTEGER)");connection.commit();connection.close()
        with patch("diagnostics.requests.get",return_value=Response()):health=self.manager.health_checks()
        self.assertTrue(all(value["status"]=="OK" for value in health.values()));db_health=self.manager.database_checks([database]);self.assertEqual(db_health["test.db"]["status"],"OK");maintenance=self.manager.maintain_databases([database]);self.assertEqual(maintenance["test.db"],"Optimized")
        self.manager.error("Portfolio","SECRETSTOCK failed","symbol SECRETSTOCK");archive=Path(self.temp.name)/"diagnostics.zip";self.manager.export_zip(archive,{"cached":1},health,db_health,["SECRETSTOCK"]);self.assertTrue(archive.exists())
        with zipfile.ZipFile(archive) as bundle:
            names=bundle.namelist();self.assertIn("system_summary.json",names);self.assertIn("recent_events.json",names);self.assertFalse(any(name.endswith(".db") for name in names));content="\n".join(bundle.read(name).decode("utf-8",errors="ignore") for name in names if name.endswith((".json",".jsonl")));self.assertNotIn("SECRETSTOCK",content);self.assertIn("REDACTED_SYMBOL",content)
    def test_short_symbol_redaction_keeps_export_readable(self):
        self.manager.error("Watchlist refresh","T failed","timeout for T");archive=Path(self.temp.name)/"short.zip";self.manager.export_zip(archive,sensitive_terms=["T"])
        with zipfile.ZipFile(archive) as bundle:events=json.loads(bundle.read("recent_events.json").decode("utf-8"))
        self.assertIn("timestamp",events[-1]);self.assertEqual(events[-1]["message"],"[REDACTED_SYMBOL] failed");self.assertEqual(events[-1]["details"],"timeout for [REDACTED_SYMBOL]")

if __name__=="__main__":unittest.main()
