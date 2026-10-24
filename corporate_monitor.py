"""Persistent corporate filing and corporate-action monitoring."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from data_provider import normalize_symbol
from india_sources import HEADERS, _resolve_bse_code, _screener_page, _screener_slug
from sec_facts import sec_tickers as _sec_tickers
from sec_facts import user_agent as sec_user_agent
from secure_storage import data_directory, protect_path


@dataclass
class MonitorEntry:
    id:int
    symbol:str
    market:str
    company:str=""
    cik:str=""
    last_checked:str=""
    status:str="Not checked"

@dataclass
class CorporateEvent:
    id:int
    monitor_id:int
    event_key:str
    event_date:str
    severity:str
    event_type:str
    source:str
    symbol:str
    title:str
    url:str=""
    details:str=""
    is_read:bool=False

class CorporateMonitorStore:
    def __init__(self,path=None):
        self.path=Path(path) if path else data_directory()/"corporate_monitor.db";self.path.parent.mkdir(parents=True,exist_ok=True);self.connection=sqlite3.connect(self.path);self.connection.row_factory=sqlite3.Row;self.connection.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS monitored(id INTEGER PRIMARY KEY AUTOINCREMENT,symbol TEXT NOT NULL,market TEXT NOT NULL,company TEXT DEFAULT '',cik TEXT DEFAULT '',last_checked TEXT DEFAULT '',status TEXT DEFAULT 'Not checked',UNIQUE(symbol,market));
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,monitor_id INTEGER NOT NULL,event_key TEXT NOT NULL UNIQUE,event_date TEXT,severity TEXT,event_type TEXT,source TEXT,symbol TEXT,title TEXT,url TEXT,details TEXT,is_read INTEGER DEFAULT 0,FOREIGN KEY(monitor_id) REFERENCES monitored(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        """);self.connection.commit();protect_path(self.path);protect_path(str(self.path)+"-wal");protect_path(str(self.path)+"-shm")
    def close(self):self.connection.close()
    def add(self,symbol,market,company="",cik=""):
        symbol=symbol.strip().upper();market=market.strip().upper();self.connection.execute("INSERT INTO monitored(symbol,market,company,cik) VALUES(?,?,?,?) ON CONFLICT(symbol,market) DO UPDATE SET company=CASE WHEN excluded.company<>'' THEN excluded.company ELSE monitored.company END,cik=CASE WHEN excluded.cik<>'' THEN excluded.cik ELSE monitored.cik END",(symbol,market,company,cik));self.connection.commit();return self._entry(self.connection.execute("SELECT * FROM monitored WHERE symbol=? AND market=?",(symbol,market)).fetchone())
    def remove(self,entry_id):self.connection.execute("DELETE FROM monitored WHERE id=?",(entry_id,));self.connection.commit()
    def entries(self):return [self._entry(row) for row in self.connection.execute("SELECT * FROM monitored ORDER BY symbol")]
    def update_status(self,entry_id,status,cik=""):self.connection.execute("UPDATE monitored SET last_checked=?,status=?,cik=CASE WHEN ?<>'' THEN ? ELSE cik END WHERE id=?",(datetime.now().astimezone().isoformat(),status,cik,cik,entry_id));self.connection.commit()
    def add_events(self,entry,events):
        added=[]
        for event in events:
            cursor=self.connection.execute("INSERT OR IGNORE INTO events(monitor_id,event_key,event_date,severity,event_type,source,symbol,title,url,details) VALUES(?,?,?,?,?,?,?,?,?,?)",(entry.id,event.event_key,event.event_date,event.severity,event.event_type,event.source,event.symbol,event.title,event.url,event.details))
            if cursor.rowcount:added.append(event)
        self.connection.commit();return added
    def events(self,unread_only=False,limit=1000):
        query="SELECT * FROM events"+(" WHERE is_read=0" if unread_only else "")+" ORDER BY event_date DESC,id DESC LIMIT ?";return [self._event(row) for row in self.connection.execute(query,(limit,))]
    def mark_all_read(self):self.connection.execute("UPDATE events SET is_read=1");self.connection.commit()
    def unread_count(self):return int(self.connection.execute("SELECT COUNT(*) FROM events WHERE is_read=0").fetchone()[0])
    def set_setting(self,key,value):self.connection.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(key,value));self.connection.commit()
    def get_setting(self,key,default=""):
        row=self.connection.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone();return row[0] if row else default
    def _entry(self,row):return MonitorEntry(row["id"],row["symbol"],row["market"],row["company"],row["cik"],row["last_checked"],row["status"])
    def _event(self,row):return CorporateEvent(row["id"],row["monitor_id"],row["event_key"],row["event_date"],row["severity"],row["event_type"],row["source"],row["symbol"],row["title"],row["url"],row["details"],bool(row["is_read"]))

def _iso_date(value)->str:
    """Normalize exchange dates such as '26-Sep-2024 19:34:12' to ISO; unrecognized text is kept as supplied."""
    text=str(value or "").strip()
    if re.match(r"\d{4}-\d{2}-\d{2}",text):return text[:10]
    token=text.split()[0] if text else ""
    for pattern in ("%d-%b-%Y","%d-%m-%Y","%d/%m/%Y"):
        try:return datetime.strptime(token,pattern).date().isoformat()
        except ValueError:continue
    return text

def _key(source,symbol,event_type,event_date,title):return hashlib.sha256(f"{source}|{symbol}|{event_type}|{event_date}|{title}".encode()).hexdigest()
def _event(source,symbol,event_type,event_date,title,url="",details="",severity="info"):return CorporateEvent(0,0,_key(source,symbol,event_type,event_date,title),event_date,severity,event_type,source,symbol,title,url,details,False)

def fetch_sec_filings(symbol,contact_email,days=365):
    if not contact_email or "@" not in contact_email:return [],"SEC contact email required for EDGAR requests.",""
    user_agent=sec_user_agent(contact_email)
    symbol=symbol.upper().replace("-",".")
    tickers=_sec_tickers(user_agent)
    wanted=symbol.replace(".","-")
    match=next((item for item in tickers.values() if str(item.get("ticker","")).upper().replace(".","-")==wanted),None)
    if not match:return [],"SEC CIK not found for symbol.",""
    cik=str(match["cik_str"]).zfill(10);response=requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json",headers={"User-Agent":user_agent,"Accept":"application/json"},timeout=20);response.raise_for_status();data=response.json();recent=(data.get("filings") or {}).get("recent") or {};cutoff=date.today()-timedelta(days=days);events=[]
    forms=recent.get("form",[]);dates=recent.get("filingDate",[]);accessions=recent.get("accessionNumber",[]);documents=recent.get("primaryDocument",[]);descriptions=recent.get("primaryDocDescription",[])
    monitored={"10-K","10-Q","8-K","20-F","6-K","DEF 14A","4","S-1","S-3","424B"}
    for form,filing_date,accession,document,description in zip(forms,dates,accessions,documents,descriptions):
        try:
            if date.fromisoformat(filing_date)<cutoff:continue
        except ValueError:continue
        if not any(form.startswith(prefix) for prefix in monitored):continue
        accession_clean=accession.replace("-","");url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_clean}/{document}";severity="high" if form.startswith("8-K") else "warning" if form=="4" else "info";events.append(_event("SEC EDGAR",symbol,form,filing_date,description or f"SEC {form} filing",url,f"Accession {accession}",severity))
    return events,"",cik

def fetch_yahoo_actions(symbol,days=365):
    try:
        import yfinance as yf
        actions=yf.Ticker(symbol).actions
        if actions is None or actions.empty:return [],""
        cutoff=date.today()-timedelta(days=days);events=[]
        for index,row in actions.iterrows():
            event_date=index.date();
            if event_date<cutoff:continue
            dividend=float(row.get("Dividends",0) or 0);split=float(row.get("Stock Splits",0) or 0);capital=float(row.get("Capital Gains",0) or 0)
            if dividend:events.append(_event("Yahoo Finance",symbol,"Dividend",event_date.isoformat(),f"Dividend {dividend:g} per share",f"https://finance.yahoo.com/quote/{symbol}/history",severity="info"))
            if split:events.append(_event("Yahoo Finance",symbol,"Stock split",event_date.isoformat(),f"Stock split factor {split:g}",f"https://finance.yahoo.com/quote/{symbol}/history",severity="high"))
            if capital:events.append(_event("Yahoo Finance",symbol,"Capital gain",event_date.isoformat(),f"Capital gain distribution {capital:g}",f"https://finance.yahoo.com/quote/{symbol}/history",severity="info"))
        return events,""
    except Exception as exc:return [],f"Yahoo corporate actions unavailable: {type(exc).__name__}."

def fetch_screener_documents(symbol,days=365):
    text,url,error=_screener_page(symbol)
    if not text:return [],error
    soup=BeautifulSoup(text,"html.parser");cutoff=date.today()-timedelta(days=days);events=[]
    for section in soup.select("section"):
        heading=section.find(["h2","h3"])
        if not heading or heading.get_text(" ",strip=True)!="Documents":continue
        for anchor in section.find_all("a",href=True):
            title=" ".join(anchor.get_text(" ",strip=True).split())
            if not title or title.lower() in {"all","more","view all"}:continue
            parent=anchor.parent.get_text(" ",strip=True)
            match=re.search(r"(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})",parent)
            event_date=""
            if match:
                try:event_date=datetime.strptime(match.group(1),"%d %b %Y").date().isoformat()
                except ValueError:pass
            if event_date and date.fromisoformat(event_date)<cutoff:continue
            href=anchor["href"];href=requests.compat.urljoin("https://www.screener.in",href);kind="Annual report" if "annual" in title.lower() else "Announcement";events.append(_event("Screener.in",_screener_slug(symbol),kind,event_date or date.today().isoformat(),title,href,parent,"info"))
    return events,""

def fetch_nse_events(symbol,days=90):
    code=_screener_slug(symbol)
    try:
        end=date.today();start=end-timedelta(days=min(days,90));session=requests.Session();session.headers.update({**HEADERS,"Referer":f"https://www.nseindia.com/get-quotes/equity?symbol={code}"});session.get("https://www.nseindia.com/",timeout=12);events=[]
        announcement=session.get("https://www.nseindia.com/api/corporate-announcements",params={"index":"equities","symbol":code,"from_date":start.strftime("%d-%m-%Y"),"to_date":end.strftime("%d-%m-%Y")},timeout=18)
        if announcement.ok:
            for item in announcement.json():
                title=str(item.get("desc") or item.get("subject") or "NSE announcement");event_date=_iso_date(item.get("an_dt") or item.get("sort_date"));url=str(item.get("attchmntFile") or item.get("attchmntFileUrl") or "");url=requests.compat.urljoin("https://www.nseindia.com",url);events.append(_event("NSE India",code,"Announcement",event_date,title,url,str(item.get("sm_name") or ""),"warning" if any(word in title.lower() for word in ("default","fraud","resignation","insolvency")) else "info"))
        actions=session.get("https://www.nseindia.com/api/corporates-corporateActions",params={"index":"equities","symbol":code,"from_date":start.strftime("%d-%m-%Y"),"to_date":end.strftime("%d-%m-%Y")},timeout=18)
        if actions.ok:
            for item in actions.json():
                title=str(item.get("subject") or item.get("purpose") or "Corporate action");event_date=_iso_date(item.get("exDate") or item.get("ex_date"));events.append(_event("NSE India",code,"Corporate action",event_date,title,"https://www.nseindia.com/companies-listing/corporate-filings-actions",json.dumps(item,default=str),"high" if any(word in title.lower() for word in ("split","bonus","rights","buyback")) else "info"))
        return events,""
    except Exception as exc:return [],f"NSE events unavailable: {type(exc).__name__}."

def fetch_bse_announcements(symbol,days=90):
    code=_resolve_bse_code(symbol)
    if not code:return [],"BSE scrip code unavailable."
    try:
        end=date.today();start=end-timedelta(days=min(days,90));params={"pageno":1,"strCat":-1,"strPrevDate":start.strftime("%Y%m%d"),"strScrip":code,"strSearch":"P","strToDate":end.strftime("%Y%m%d"),"strType":"C"};headers={**HEADERS,"Origin":"https://www.bseindia.com","Referer":"https://www.bseindia.com/"};response=requests.get("https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w",params=params,headers=headers,timeout=20);response.raise_for_status();events=[]
        payload=response.json()
        if not isinstance(payload,dict):return [],""
        for item in payload.get("Table",[]):
            title=str(item.get("HEADLINE") or item.get("NEWSSUB") or "BSE announcement");event_date=_iso_date(item.get("NEWS_DT") or item.get("DissemDT"));attachment=item.get("ATTACHMENTNAME") or "";url=f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{attachment}" if attachment else "https://www.bseindia.com/corporates/ann.html";events.append(_event("BSE India",symbol,"Announcement",event_date,title,url,str(item.get("MORE") or ""),"warning" if any(word in title.lower() for word in ("fraud","default","resignation","insolvency")) else "info"))
        return events,""
    except Exception as exc:return [],f"BSE announcements unavailable: {type(exc).__name__}."

def monitor_entry(entry:MonitorEntry,contact_email=""):
    events=[];warnings=[];cik=entry.cik
    try:yahoo_symbol=normalize_symbol(entry.symbol,entry.market)
    except Exception:yahoo_symbol=entry.symbol
    yahoo,error=fetch_yahoo_actions(yahoo_symbol);events.extend(yahoo)
    if error:warnings.append(error)
    if entry.market=="US":
        try:sec,error,cik=fetch_sec_filings(entry.symbol,contact_email);events.extend(sec)
        except Exception as exc:error=f"SEC filings unavailable: {type(exc).__name__}."
        if error:warnings.append(error)
    else:
        documents,error=fetch_screener_documents(entry.symbol);events.extend(documents)
        if error:warnings.append(error)
        if entry.market=="NSE":
            nse,error=fetch_nse_events(entry.symbol);events.extend(nse)
            if error:warnings.append(error)
        elif entry.market=="BSE":
            bse,error=fetch_bse_announcements(entry.symbol);events.extend(bse)
            if error:warnings.append(error)
    unique={event.event_key:event for event in events};return list(unique.values()),warnings,cik
