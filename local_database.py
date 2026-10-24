"""Thread-safe local SQLite cache and valuation-history database."""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from logger import get_logger
from secure_storage import data_directory, protect_path
from valuation import (
    DataLineageEntry,
    FinancialCompanyMetrics,
    StockData,
    ValuationResult,
    audit_record,
)

logger = get_logger("LocalDatabase")

CACHE_SCHEMA_VERSION="1.0"

class LocalDatabase:
    def __init__(self,path:Optional[str|Path]=None):
        self.path=Path(path) if path else data_directory()/"fairscope_cache.db";self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock();self.connection=sqlite3.connect(self.path,check_same_thread=False);self.connection.row_factory=sqlite3.Row;self.connection.execute("PRAGMA journal_mode=WAL");self.connection.execute("PRAGMA foreign_keys=ON");self._create();protect_path(self.path);protect_path(str(self.path)+"-wal");protect_path(str(self.path)+"-shm")
    def _create(self):
        with self.lock:
            self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS stock_cache(symbol TEXT NOT NULL,market TEXT NOT NULL,fetched_at REAL NOT NULL,expires_at REAL NOT NULL,last_accessed REAL NOT NULL,source_updated TEXT,data_provider TEXT,payload TEXT NOT NULL,payload_bytes INTEGER NOT NULL,schema_version TEXT NOT NULL,PRIMARY KEY(symbol,market));
            CREATE TABLE IF NOT EXISTS valuation_history(analysis_id TEXT PRIMARY KEY,parent_analysis_id TEXT,symbol TEXT,market TEXT,company TEXT,created_at TEXT,app_version TEXT,model_version TEXT,market_price REAL,fair_value REAL,upside_pct REAL,confidence_score INTEGER,audit_hash TEXT,audit_json TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS idx_history_symbol ON valuation_history(symbol,created_at DESC);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS background_jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,job_type TEXT NOT NULL,status TEXT NOT NULL,total INTEGER NOT NULL,completed INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL,partial_results TEXT NOT NULL DEFAULT '[]',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,error TEXT DEFAULT '');
            """)
            # Migration: add last_accessed to stock_cache if it doesn't exist
            cols = [row[1] for row in self.connection.execute("PRAGMA table_info(stock_cache)").fetchall()]
            if "last_accessed" not in cols:
                logger.info("Migrating database: adding last_accessed column to stock_cache")
                self.connection.execute("ALTER TABLE stock_cache ADD COLUMN last_accessed REAL NOT NULL DEFAULT 0")
            self.connection.commit()
    def close(self):
        with self.lock:self.connection.close()
    def setting(self,key,default):
        with self.lock:
            row=self.connection.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
        if not row:return default
        try:return json.loads(row[0])
        except Exception:return default
    def set_setting(self,key,value):
        with self.lock:self.connection.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,json.dumps(value)));self.connection.commit()
    def cache_ttl_hours(self)->float:return float(self.setting("cache_ttl_hours",6.0))
    def allow_stale_fallback(self)->bool:return bool(self.setting("allow_stale_fallback",True))
    def save_stock(self,data:StockData,ttl_hours:Optional[float]=None):
        now=datetime.now(timezone.utc).timestamp();ttl=self.cache_ttl_hours() if ttl_hours is None else ttl_hours;payload=json.dumps(asdict(data),ensure_ascii=False,default=str,separators=(",",":"));symbol=data.symbol.upper()
        with self.lock:self.connection.execute("INSERT INTO stock_cache(symbol,market,fetched_at,expires_at,last_accessed,source_updated,data_provider,payload,payload_bytes,schema_version) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(symbol,market) DO UPDATE SET fetched_at=excluded.fetched_at,expires_at=excluded.expires_at,last_accessed=excluded.last_accessed,source_updated=excluded.source_updated,data_provider=excluded.data_provider,payload=excluded.payload,payload_bytes=excluded.payload_bytes,schema_version=excluded.schema_version",(symbol,data.market,now,now+ttl*3600,now,data.source_updated_date,data.data_provider,payload,len(payload.encode("utf-8")),CACHE_SCHEMA_VERSION));self.connection.commit()
    def load_stock(self,symbol:str,market:str,allow_expired=False):
        with self.lock:row=self.connection.execute("SELECT * FROM stock_cache WHERE symbol=? AND market=?",(symbol.upper(),market)).fetchone()
        if not row:return None
        now=datetime.now(timezone.utc).timestamp();expired=now>row["expires_at"]
        with self.lock:self.connection.execute("UPDATE stock_cache SET last_accessed=? WHERE symbol=? AND market=?",(now,symbol.upper(),market));self.connection.commit()
        if expired and not allow_expired:return None
        try:data=_stock_from_dict(json.loads(row["payload"]));age=max(0,(now-row["fetched_at"])/3600);data.cache_status="stale cache" if expired else "fresh cache";data.cache_saved_at=datetime.fromtimestamp(row["fetched_at"],timezone.utc).isoformat();data.cache_age_hours=age;data.is_stale=expired;data.warnings=list(data.warnings)+[f"Loaded from {'stale' if expired else 'fresh'} local cache ({age:.1f} hours old)."]
        except Exception:return None
        return data
    def save_valuation(self,result:ValuationResult):
        record=audit_record(result);payload=json.dumps(record,ensure_ascii=False,default=str,separators=(",",":"))
        with self.lock:self.connection.execute("INSERT OR REPLACE INTO valuation_history(analysis_id,parent_analysis_id,symbol,market,company,created_at,app_version,model_version,market_price,fair_value,upside_pct,confidence_score,audit_hash,audit_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(result.analysis_id,result.parent_analysis_id,result.data.symbol,result.data.market,result.data.company,result.created_at,result.app_version,result.model_version,result.data.price,result.fair_value,result.upside_pct,result.confidence_score,result.audit_hash,payload));self.connection.execute("DELETE FROM valuation_history WHERE analysis_id NOT IN (SELECT analysis_id FROM valuation_history ORDER BY created_at DESC LIMIT 1000)");self.connection.commit()
    def cache_rows(self):
        now=datetime.now(timezone.utc).timestamp()
        with self.lock:return [dict(row)|{"is_stale":now>row["expires_at"],"age_hours":max(0,(now-row["fetched_at"])/3600)} for row in self.connection.execute("SELECT symbol,market,fetched_at,expires_at,source_updated,data_provider,payload_bytes FROM stock_cache ORDER BY fetched_at DESC")]
    def history_rows(self,limit=500):
        with self.lock:return [dict(row) for row in self.connection.execute("SELECT analysis_id,parent_analysis_id,symbol,market,company,created_at,app_version,model_version,market_price,fair_value,upside_pct,confidence_score,audit_hash FROM valuation_history ORDER BY created_at DESC LIMIT ?",(limit,))]
    def tracking_rows(self,limit=1000):
        """Saved valuations with the price, fair value, and valuation-buffer price recorded at the time, latest first."""
        with self.lock:return [dict(row) for row in self.connection.execute("SELECT symbol,market,created_at,market_price,fair_value,upside_pct,json_extract(audit_json,'$.margin_price') AS margin_price FROM valuation_history ORDER BY created_at DESC LIMIT ?",(limit,))]
    def history_audit(self,analysis_id):
        with self.lock:row=self.connection.execute("SELECT audit_json FROM valuation_history WHERE analysis_id=?",(analysis_id,)).fetchone()
        return json.loads(row[0]) if row else None
    def create_job(self,job_type,items):
        now=datetime.now(timezone.utc).isoformat();payload=json.dumps([{"symbol":item.symbol,"market":item.market} for item in items]);
        with self.lock:
            cursor=self.connection.execute("INSERT INTO background_jobs(job_type,status,total,completed,payload,created_at,updated_at) VALUES(?, 'running', ?, 0, ?, ?, ?)",(job_type,len(items),payload,now,now));self.connection.commit();return cursor.lastrowid
    def update_job(self,job_id,completed,outcome=None):
        now=datetime.now(timezone.utc).isoformat()
        with self.lock:
            row=self.connection.execute("SELECT partial_results FROM background_jobs WHERE id=?",(job_id,)).fetchone();partial=json.loads(row[0]) if row else []
            if outcome is not None:partial.append({"symbol":outcome.item.symbol,"market":outcome.item.market,"success":outcome.result is not None,"error":outcome.error,"analysis_id":outcome.result.analysis_id if outcome.result else "","attempts":outcome.attempts})
            self.connection.execute("UPDATE background_jobs SET completed=?,partial_results=?,updated_at=? WHERE id=?",(completed,json.dumps(partial),now,job_id));self.connection.commit()
    def finish_job(self,job_id,status,error=""):
        with self.lock:self.connection.execute("UPDATE background_jobs SET status=?,error=?,updated_at=? WHERE id=?",(status,error,datetime.now(timezone.utc).isoformat(),job_id));self.connection.execute("DELETE FROM background_jobs WHERE id NOT IN (SELECT id FROM background_jobs ORDER BY id DESC LIMIT 500)");self.connection.commit()
    def mark_running_interrupted(self):
        with self.lock:
            cursor=self.connection.execute("UPDATE background_jobs SET status='interrupted',updated_at=? WHERE status='running'",(datetime.now(timezone.utc).isoformat(),));self.connection.commit();return cursor.rowcount
    def recoverable_jobs(self,limit=20):
        with self.lock:return [dict(row) for row in self.connection.execute("SELECT * FROM background_jobs WHERE status IN ('interrupted','cancelled') ORDER BY id DESC LIMIT ?",(limit,))]
    def recent_jobs(self,limit=50):
        with self.lock:return [dict(row) for row in self.connection.execute("SELECT * FROM background_jobs ORDER BY id DESC LIMIT ?",(limit,))]
    def delete_job(self,job_id):
        with self.lock:self.connection.execute("DELETE FROM background_jobs WHERE id=?",(job_id,));self.connection.commit()
    def stats(self):
        with self.lock:
            cached=self.connection.execute("SELECT COUNT(*),COALESCE(SUM(payload_bytes),0) FROM stock_cache").fetchone();history=self.connection.execute("SELECT COUNT(*) FROM valuation_history").fetchone()[0];jobs=self.connection.execute("SELECT COUNT(*) FROM background_jobs").fetchone()[0]
        stale=sum(1 for row in self.cache_rows() if row["is_stale"]);size=self.path.stat().st_size if self.path.exists() else 0;return {"cached_stocks":cached[0],"payload_bytes":cached[1],"stale_stocks":stale,"history_records":history,"background_jobs":jobs,"database_bytes":size}
    def clear_expired(self):
        now=datetime.now(timezone.utc).timestamp()
        with self.lock:self.connection.execute("DELETE FROM stock_cache WHERE expires_at<?",(now,));self.connection.commit()
        self.prune_cache()

    def prune_cache(self,limit=1000):
        with self.lock:self.connection.execute("DELETE FROM stock_cache WHERE (symbol,market) NOT IN (SELECT symbol,market FROM stock_cache ORDER BY last_accessed DESC LIMIT ?)",(limit,));self.connection.commit()
    def clear_cache(self):
        with self.lock:self.connection.execute("DELETE FROM stock_cache");self.connection.commit()
    def clear_history(self):
        with self.lock:self.connection.execute("DELETE FROM valuation_history");self.connection.commit()

def _stock_from_dict(payload):
    payload=dict(payload);payload["lineage"]=[DataLineageEntry(**item) for item in payload.get("lineage",[])];metrics=payload.get("financial_metrics");payload["financial_metrics"]=FinancialCompanyMetrics(**metrics) if metrics else None;allowed={item.name for item in fields(StockData)};return StockData(**{key:value for key,value in payload.items() if key in allowed})

_default_database=None
_default_lock=threading.Lock()
def get_local_database()->LocalDatabase:
    global _default_database
    with _default_lock:
        if _default_database is None:_default_database=LocalDatabase()
        return _default_database
