"""Persistent local watchlists, alert conditions, and alert history."""
from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from batch_import import write_csv_row
from secure_storage import data_directory, protect_path
from valuation import ValuationResult


@dataclass
class WatchlistEntry:
    id:int
    name:str
    symbol:str
    market:str
    company:str=""
    custom_price:Optional[float]=None
    min_upside:float=25.0
    max_financial_risk:float=60.0
    max_governance_risk:float=60.0
    fair_value_change:float=10.0
    alert_mos:bool=True
    last_price:Optional[float]=None
    last_fair_value:Optional[float]=None
    last_checked:str=""
    last_status:str="Not checked"

@dataclass
class AlertRecord:
    id:int
    watchlist_id:int
    created_at:str
    severity:str
    kind:str
    symbol:str
    message:str
    is_read:bool=False

class WatchlistStore:
    def __init__(self,path:Optional[str|Path]=None):
        self.path=Path(path) if path else data_directory()/"watchlists.db";self.path.parent.mkdir(parents=True,exist_ok=True);self.connection=sqlite3.connect(self.path);self.connection.row_factory=sqlite3.Row;self._create();protect_path(self.path);protect_path(str(self.path)+"-wal");protect_path(str(self.path)+"-shm")
    def _create(self):
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS watchlist(
          id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL DEFAULT 'Main',symbol TEXT NOT NULL,market TEXT NOT NULL,company TEXT DEFAULT '',
          custom_price REAL,min_upside REAL NOT NULL DEFAULT 25,max_financial_risk REAL NOT NULL DEFAULT 60,max_governance_risk REAL NOT NULL DEFAULT 60,
          fair_value_change REAL NOT NULL DEFAULT 10,alert_mos INTEGER NOT NULL DEFAULT 1,last_price REAL,last_fair_value REAL,last_checked TEXT DEFAULT '',last_status TEXT DEFAULT 'Not checked',
          UNIQUE(name,symbol,market));
        CREATE TABLE IF NOT EXISTS alerts(
          id INTEGER PRIMARY KEY AUTOINCREMENT,watchlist_id INTEGER NOT NULL,created_at TEXT NOT NULL,severity TEXT NOT NULL,kind TEXT NOT NULL,symbol TEXT NOT NULL,message TEXT NOT NULL,is_read INTEGER NOT NULL DEFAULT 0,
          FOREIGN KEY(watchlist_id) REFERENCES watchlist(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS alert_state(
          watchlist_id INTEGER NOT NULL,kind TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(watchlist_id,kind),
          FOREIGN KEY(watchlist_id) REFERENCES watchlist(id) ON DELETE CASCADE);
        PRAGMA foreign_keys=ON;
        """);self.connection.commit()
    def close(self):self.connection.close()
    def add(self,symbol:str,market:str,company:str="",name:str="Main")->WatchlistEntry:
        symbol=symbol.strip().upper();market=market.strip().upper();self.connection.execute("INSERT INTO watchlist(name,symbol,market,company) VALUES(?,?,?,?) ON CONFLICT(name,symbol,market) DO UPDATE SET company=CASE WHEN excluded.company<>'' THEN excluded.company ELSE watchlist.company END",(name,symbol,market,company));self.connection.commit();row=self.connection.execute("SELECT * FROM watchlist WHERE name=? AND symbol=? AND market=?",(name,symbol,market)).fetchone();return self._entry(row)
    def remove(self,entry_id:int):self.connection.execute("DELETE FROM watchlist WHERE id=?",(entry_id,));self.connection.commit()
    def entries(self,name:str="Main")->list[WatchlistEntry]:return [self._entry(row) for row in self.connection.execute("SELECT * FROM watchlist WHERE name=? ORDER BY symbol",(name,))]
    def update_settings(self,entry_id:int,custom_price,min_upside,max_financial_risk,max_governance_risk,fair_value_change,alert_mos):
        self.connection.execute("UPDATE watchlist SET custom_price=?,min_upside=?,max_financial_risk=?,max_governance_risk=?,fair_value_change=?,alert_mos=? WHERE id=?",(custom_price,min_upside,max_financial_risk,max_governance_risk,fair_value_change,1 if alert_mos else 0,entry_id));self.connection.execute("UPDATE alert_state SET active=0,updated_at=? WHERE watchlist_id=?",(datetime.now().astimezone().isoformat(),entry_id));self.connection.commit()
    def update_result(self,entry_id:int,result:ValuationResult,status:str):
        self.connection.execute("UPDATE watchlist SET company=?,last_price=?,last_fair_value=?,last_checked=?,last_status=? WHERE id=?",(result.data.company,result.data.price,result.fair_value,datetime.now().astimezone().isoformat(),status,entry_id));self.connection.commit()
    def update_failure(self,entry_id:int,message:str):self.connection.execute("UPDATE watchlist SET last_checked=?,last_status=? WHERE id=?",(datetime.now().astimezone().isoformat(),"Error: "+message[:180],entry_id));self.connection.commit()
    def evaluate(self,entry:WatchlistEntry,result:ValuationResult)->list[AlertRecord]:
        conditions=[]
        if entry.alert_mos and result.data.price<=result.margin_price:conditions.append(("info","valuation_buffer",f"Price {result.data.currency} {result.data.price:,.2f} is below the {result.dynamic_margin:.0%} valuation-buffer threshold ({result.margin_price:,.2f}). This does not imply the investment is safe or protected from loss."))
        if entry.custom_price is not None and result.data.price<=entry.custom_price:conditions.append(("high","custom_price",f"Price {result.data.price:,.2f} is at or below custom target {entry.custom_price:,.2f}."))
        if result.upside_pct>=entry.min_upside:conditions.append(("info","upside",f"Modeled upside {result.upside_pct:.1f}% reached the {entry.min_upside:.1f}% alert threshold."))
        if result.risk_score>=entry.max_financial_risk:conditions.append(("high","financial_risk",f"Financial risk score {result.risk_score}/100 reached the {entry.max_financial_risk:.0f} threshold."))
        if result.governance_risk_score>=entry.max_governance_risk:conditions.append(("high","governance_risk",f"Governance risk score {result.governance_risk_score}/100 reached the {entry.max_governance_risk:.0f} threshold."))
        if result.data.source_discrepancies:conditions.append(("warning","source_discrepancy",f"{len(result.data.source_discrepancies)} material source discrepancy warning(s) detected."))
        if entry.last_fair_value and abs(result.fair_value/entry.last_fair_value-1)*100>=entry.fair_value_change:conditions.append(("warning","fair_value_change",f"Fair value changed from {entry.last_fair_value:,.2f} to {result.fair_value:,.2f}, exceeding {entry.fair_value_change:.1f}%."))
        if result.confidence_score<50:conditions.append(("warning","low_confidence",f"Valuation confidence is Low ({result.confidence_score}/100)."))
        triggered={kind for _severity,kind,_message in conditions};new=[];now=datetime.now().astimezone().isoformat()
        known={row["kind"]:bool(row["active"]) for row in self.connection.execute("SELECT kind,active FROM alert_state WHERE watchlist_id=?",(entry.id,))}
        for severity,kind,message in conditions:
            if not known.get(kind,False):
                cursor=self.connection.execute("INSERT INTO alerts(watchlist_id,created_at,severity,kind,symbol,message) VALUES(?,?,?,?,?,?)",(entry.id,now,severity,kind,result.data.symbol,message));new.append(AlertRecord(cursor.lastrowid,entry.id,now,severity,kind,result.data.symbol,message,False))
            self.connection.execute("INSERT INTO alert_state(watchlist_id,kind,active,updated_at) VALUES(?,?,1,?) ON CONFLICT(watchlist_id,kind) DO UPDATE SET active=1,updated_at=excluded.updated_at",(entry.id,kind,now))
        for kind,active in known.items():
            if active and kind not in triggered:self.connection.execute("UPDATE alert_state SET active=0,updated_at=? WHERE watchlist_id=? AND kind=?",(now,entry.id,kind))
        self.connection.commit();return new
    def alerts(self,unread_only:bool=False,limit:int=500)->list[AlertRecord]:
        query="SELECT * FROM alerts"+(" WHERE is_read=0" if unread_only else "")+" ORDER BY id DESC LIMIT ?";return [self._alert(row) for row in self.connection.execute(query,(limit,))]
    def unread_count(self)->int:return int(self.connection.execute("SELECT COUNT(*) FROM alerts WHERE is_read=0").fetchone()[0])
    def mark_all_read(self):self.connection.execute("UPDATE alerts SET is_read=1");self.connection.commit()
    def export_csv(self,path:str):
        with open(path,"w",encoding="utf-8-sig",newline="") as handle:
            writer=csv.writer(handle);writer.writerow(["Symbol","Market","Company","Custom Price","Min Upside %","Max Financial Risk","Max Governance Risk","Fair Value Change %","Alert Valuation Buffer","Last Price","Last Fair Value","Last Checked","Status"])
            for entry in self.entries():write_csv_row(writer,[entry.symbol,entry.market,entry.company,entry.custom_price,entry.min_upside,entry.max_financial_risk,entry.max_governance_risk,entry.fair_value_change,entry.alert_mos,entry.last_price,entry.last_fair_value,entry.last_checked,entry.last_status])
    def _entry(self,row):return WatchlistEntry(row["id"],row["name"],row["symbol"],row["market"],row["company"],row["custom_price"],row["min_upside"],row["max_financial_risk"],row["max_governance_risk"],row["fair_value_change"],bool(row["alert_mos"]),row["last_price"],row["last_fair_value"],row["last_checked"],row["last_status"])
    def _alert(self,row):return AlertRecord(row["id"],row["watchlist_id"],row["created_at"],row["severity"],row["kind"],row["symbol"],row["message"],bool(row["is_read"]))
