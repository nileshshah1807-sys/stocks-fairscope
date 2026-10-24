"""Structured local error monitoring, health checks, database diagnostics, and support ZIP export."""
from __future__ import annotations

import json
import os
import platform
import re
import sqlite3
import sys
import threading
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import requests

from secure_storage import data_directory, protect_path
from version import APP_VERSION, AUDIT_SCHEMA_VERSION, MODEL_VERSION


def _redact(value):
    text=str(value or "");text=re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}","[REDACTED_EMAIL]",text);text=re.sub(r"(?i)(api[_-]?key|token|password)=([^&\s]+)",r"\1=[REDACTED]",text);return text[:12000]

def _redact_terms(text,terms):
    """Redact whole symbols only, so short tickers such as T or F do not corrupt surrounding words and JSON keys."""
    for term in sorted({str(term) for term in (terms or []) if term},key=len,reverse=True):text=re.sub(r"(?<![A-Za-z0-9])"+re.escape(term)+r"(?![A-Za-z0-9])","[REDACTED_SYMBOL]",text,flags=re.IGNORECASE)
    return text

class DiagnosticManager:
    def __init__(self,root=None,max_bytes=5_000_000,backups=4):
        self.root=Path(root) if root else data_directory();self.root.mkdir(parents=True,exist_ok=True);self.log_path=self.root/"diagnostics.jsonl";self.max_bytes=max_bytes;self.backups=backups;self.lock=threading.RLock();self.last_error=""
    def _rotate(self):
        if not self.log_path.exists() or self.log_path.stat().st_size<self.max_bytes:return
        for index in range(self.backups,0,-1):
            source=self.root/("diagnostics.jsonl" if index==1 else f"diagnostics.jsonl.{index-1}");target=self.root/f"diagnostics.jsonl.{index}"
            if source.exists():
                if target.exists():target.unlink()
                source.rename(target)
    def log(self,level,component,message,details=""):
        event={"timestamp":datetime.now(timezone.utc).isoformat(),"level":str(level).upper(),"component":_redact(component),"message":_redact(message),"details":_redact(details),"thread":threading.current_thread().name,"app_version":APP_VERSION}
        if event["level"] in {"ERROR","CRITICAL"}:self.last_error=event["message"]
        with self.lock:
            self._rotate()
            with open(self.log_path,"a",encoding="utf-8") as handle:handle.write(json.dumps(event,ensure_ascii=False)+"\n")
            protect_path(self.log_path)
        return event
    def error(self,component,message,details=""):return self.log("ERROR",component,message,details)
    def exception(self,component,exc):return self.log("CRITICAL",component,str(exc),"".join(traceback.format_exception(type(exc),exc,exc.__traceback__)))
    def events(self,limit=500):
        paths=[self.root/f"diagnostics.jsonl.{index}" for index in range(self.backups,0,-1)]+[self.log_path];events=[]
        for path in paths:
            if not path.exists():continue
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:events.append(json.loads(line))
                    except json.JSONDecodeError:continue
            except OSError:continue
        return list(reversed(events[-limit:]))
    def error_count(self):return sum(1 for event in self.events(5000) if event.get("level") in {"ERROR","CRITICAL"})
    def clear(self):
        with self.lock:
            for path in [self.log_path]+[self.root/f"diagnostics.jsonl.{index}" for index in range(1,self.backups+1)]:
                if path.exists():path.unlink()
            self.last_error=""
    def health_checks(self):
        endpoints={"Yahoo Finance":"https://query1.finance.yahoo.com/v8/finance/chart/AAPL?range=1d&interval=1d","Screener.in":"https://www.screener.in/api/company/search/?q=RELIANCE","NSE India":"https://www.nseindia.com/","BSE India":"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Debtflag=&scripcode=500325&seriesid="}
        results={};headers={"User-Agent":"Mozilla/5.0 DR-Nilesh-Shah-Stocks-FairScope-Diagnostics/1.0","Accept":"application/json,text/html,*/*"}
        for name,url in endpoints.items():
            try:
                response=requests.get(url,headers=headers,timeout=10);status="OK" if response.status_code<400 else "BLOCKED" if response.status_code in {401,403,429} else "ERROR";results[name]={"status":status,"http":response.status_code,"latency_ms":round(response.elapsed.total_seconds()*1000),"message":"Accessible" if status=="OK" else "Website rejected or limited the diagnostic request"}
            except Exception as exc:results[name]={"status":"ERROR","http":None,"latency_ms":None,"message":_redact(exc)}
        self.log("INFO","Network health","Provider checks completed",json.dumps(results));return results
    def database_checks(self,paths):
        results={}
        for path in paths:
            path=Path(path);name=path.name
            if not path.exists():results[name]={"status":"MISSING","message":"Database not created yet"};continue
            try:
                connection=sqlite3.connect(path);check=connection.execute("PRAGMA quick_check").fetchone()[0];tables=connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0];connection.close();results[name]={"status":"OK" if check=="ok" else "ERROR","message":check,"tables":tables,"bytes":path.stat().st_size}
            except Exception as exc:results[name]={"status":"ERROR","message":_redact(exc)}
        self.log("INFO","Database health","SQLite checks completed",json.dumps(results));return results
    def maintain_databases(self,paths):
        results={}
        for path in paths:
            path=Path(path)
            if not path.exists():continue
            try:
                connection=sqlite3.connect(path);check=connection.execute("PRAGMA quick_check").fetchone()[0]
                if check=="ok":connection.execute("REINDEX");connection.execute("VACUUM");connection.close();results[path.name]="Optimized"
                else:connection.close();results[path.name]=f"Integrity error: {check}"
            except Exception as exc:results[path.name]=f"Error: {_redact(exc)}"
        self.log("INFO","Database maintenance","Maintenance completed",json.dumps(results));return results
    def export_zip(self,path,database_stats=None,health=None,db_health=None,sensitive_terms=None):
        system={"generated_utc":datetime.now(timezone.utc).isoformat(),"app_version":APP_VERSION,"model_version":MODEL_VERSION,"audit_schema":AUDIT_SCHEMA_VERSION,"python":sys.version,"platform":platform.platform(),"machine":platform.machine(),"database_stats":database_stats or {},"provider_health":health or {},"database_health":db_health or {},"environment":{"QT_QPA_PLATFORM":os.environ.get("QT_QPA_PLATFORM","")}}
        event_text=json.dumps(list(reversed(self.events(500))),indent=2,ensure_ascii=False)
        event_text=_redact_terms(event_text,sensitive_terms)
        with zipfile.ZipFile(path,"w",zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("system_summary.json",json.dumps(system,indent=2,ensure_ascii=False,default=str));archive.writestr("recent_events.json",event_text)
            for log in [self.log_path]+[self.root/f"diagnostics.jsonl.{index}" for index in range(1,self.backups+1)]:
                if log.exists():
                    text=log.read_text(encoding="utf-8",errors="replace")
                    text=_redact_terms(text,sensitive_terms)
                    archive.writestr(f"logs/{log.name}",text)
            archive.writestr("README.txt","This ZIP contains sanitized diagnostics, system versions, provider/database health, and local error logs. It intentionally excludes watchlists, transactions, valuation payloads, SEC email, API credentials, and database files.\n")
        self.log("INFO","Diagnostics","Diagnostic ZIP exported",str(path));return path

_default=None
def get_diagnostics():
    global _default
    if _default is None:_default=DiagnosticManager()
    return _default
