"""Best-effort Indian-market verification from Screener.in and NSE/BSE public web endpoints."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

from ttl_cache import ttl_cache

# Quotes expire quickly so refreshes see current prices; failed lookups are not cached so they are retried.
QUOTE_TTL_SECONDS=60
PAGE_TTL_SECONDS=600
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36 DR-Nilesh-Shah-Stocks-FairScope/8.0"
HEADERS={"User-Agent":UA,"Accept":"application/json, text/plain, */*","Accept-Language":"en-US,en;q=0.9"}

@dataclass
class IndiaSourceResult:
    exchange_price:Optional[float]=None
    exchange_name:str=""
    exchange_timestamp:str=""
    exchange_url:str=""
    screener_ratios:dict[str,float]=field(default_factory=dict)
    screener_financials:dict[str,list[float]]=field(default_factory=dict)
    screener_periods:dict[str,list[str]]=field(default_factory=dict)
    screener_url:str=""
    screener_tables:dict[str,dict]=field(default_factory=dict)
    promoter_pledge:Optional[float]=None
    sources_checked:list[str]=field(default_factory=list)
    warnings:list[str]=field(default_factory=list)

def _num(value)->Optional[float]:
    if value is None:return None
    try:return float(str(value).replace(",","").replace("₹","").replace("%","").strip())
    except (TypeError,ValueError):return None

def _screener_slug(symbol:str)->str:return symbol.upper().replace(".NS","").replace(".BO","")

@ttl_cache(PAGE_TTL_SECONDS,cache_if=lambda result:bool(result[0]))
def _screener_page(symbol:str)->tuple[str,str,str]:
    slug=_screener_slug(symbol);url=f"https://www.screener.in/company/{slug}/consolidated/"
    try:
        response=requests.get(url,headers={"User-Agent":UA,"Accept":"text/html"},timeout=15)
        if response.status_code==404:
            url=f"https://www.screener.in/company/{slug}/";response=requests.get(url,headers={"User-Agent":UA,"Accept":"text/html"},timeout=15)
        response.raise_for_status();return response.text,url,""
    except Exception as exc:return "",url,f"Screener.in verification unavailable: {type(exc).__name__}."

@ttl_cache(PAGE_TTL_SECONDS,cache_if=lambda result:bool(result[0]))
def fetch_screener(symbol:str)->tuple[dict[str,float],str,str]:
    text,url,error=_screener_page(symbol)
    if not text:return {},url,error
    soup=BeautifulSoup(text,"html.parser");ratios={}
    for li in soup.select("#top-ratios li"):
        name=li.select_one(".name");numbers=li.select(".number")
        if not name or not numbers:continue
        label=" ".join(name.get_text(" ",strip=True).split());values=[_num(x.get_text(" ",strip=True)) for x in numbers];values=[x for x in values if x is not None]
        if values:ratios[label]=values[0]
        if label=="High / Low" and len(values)>1:ratios["52W High"],ratios["52W Low"]=values[0],values[1]
    return ratios,url,error

@ttl_cache(PAGE_TTL_SECONDS,cache_if=bool)
def fetch_screener_tables(symbol:str)->dict[str,dict]:
    """Screener.in statement tables with column positions preserved: {section: {"periods": [...], "rows": {label: [values or None]}}}."""
    text,_url,_error=_screener_page(symbol)
    if not text:return {}
    soup=BeautifulSoup(text,"html.parser");tables={}
    for section in soup.select("section"):
        heading=section.find(["h2","h3"]);table=section.find("table")
        if not heading or not table:continue
        section_name=heading.get_text(" ",strip=True)
        if section_name not in {"Quarterly Results","Profit & Loss","Balance Sheet","Cash Flows","Ratios","Shareholding Pattern"} or section_name in tables:continue
        rows=table.find_all("tr")
        if not rows:continue
        values={}
        for row in rows[1:]:
            cells=[cell.get_text(" ",strip=True) for cell in row.find_all(["th","td"])]
            if len(cells)<2:continue
            values[" ".join(cells[0].replace("+","").split())]=[_num(cell) for cell in cells[1:]]
        tables[section_name]={"periods":[cell.get_text(" ",strip=True) for cell in rows[0].find_all(["th","td"])][1:],"rows":values}
    return tables

@ttl_cache(PAGE_TTL_SECONDS,cache_if=lambda result:bool(result[0]))
def fetch_screener_financials(symbol:str)->tuple[dict[str,list[float]],dict[str,list[str]]]:
    tables=fetch_screener_tables(symbol);series={};periods={}
    for section_name in ("Profit & Loss","Balance Sheet","Ratios","Shareholding Pattern"):
        table=tables.get(section_name)
        if not table:continue
        periods[section_name]=table["periods"]
        for label,values in table["rows"].items():
            usable=[value for value in values if value is not None]
            if usable:series[f"{section_name}:{label}"]=usable
    return series,periods

def _annual_rows(table:dict)->tuple[list[str],dict[str,list[Optional[float]]]]:
    periods=table.get("periods",[]);keep=[index for index,period in enumerate(periods) if period.strip().upper()!="TTM"]
    return [periods[index] for index in keep],{label:[values[index] if index<len(values) else None for index in keep] for label,values in table.get("rows",{}).items()}

def screener_long_history(tables:dict)->tuple[dict[str,list[Optional[float]]],list[str]]:
    """Up to 12 annual Screener.in observations, latest first: operating and net margins, tax, payout, ROCE, working-capital days, and holdings."""
    history={};periods=[]
    if tables.get("Profit & Loss"):
        periods,rows=_annual_rows(tables["Profit & Loss"]);sales=rows.get("Sales") or rows.get("Revenue") or [];operating=rows.get("Operating Profit",[]);depreciation=rows.get("Depreciation",[]);profit=rows.get("Net Profit",[])
        def at(values,index):return values[index] if index<len(values) else None
        ebit_margin=[];net_margin=[]
        for index in range(len(periods)):
            revenue=at(sales,index);op=at(operating,index);net=at(profit,index)
            ebit_margin.append((op-(at(depreciation,index) or 0))/revenue if revenue and revenue>0 and op is not None else None)
            net_margin.append(net/revenue if revenue and revenue>0 and net is not None else None)
        history["ebit_margin"]=ebit_margin[::-1];history["net_margin"]=net_margin[::-1];history["revenue"]=[at(sales,index) for index in range(len(periods))][::-1];periods=periods[::-1]
        for label,key in (("Tax %","tax_rate"),("Dividend Payout %","dividend_payout")):
            if label in rows:history[key]=[value/100 if value is not None else None for value in rows[label]][::-1]
    if tables.get("Ratios"):
        _periods,rows=_annual_rows(tables["Ratios"])
        for label,key,scale in (("ROCE %","roce",100),("Debtor Days","debtor_days",1),("Inventory Days","inventory_days",1),("Days Payable","payable_days",1),("Cash Conversion Cycle","cash_conversion_cycle",1),("Working Capital Days","working_capital_days",1)):
            if label in rows:history[key]=[value/scale if value is not None else None for value in rows[label]][::-1]
    if tables.get("Shareholding Pattern"):
        rows=tables["Shareholding Pattern"].get("rows",{})
        for label,key in (("Promoters","promoter"),("FIIs","fii"),("DIIs","dii")):
            if label in rows:history[key]=[value/100 if value is not None else None for value in rows[label]][::-1]
    return history,periods

def screener_asset_quality(tables:dict)->dict[str,float]:
    """Latest bank Gross/Net NPA ratios from Screener.in quarterly results, as decimals."""
    rows=(tables.get("Quarterly Results") or {}).get("rows",{});result={}
    for label,key in (("Gross NPA %","gross_npa"),("Net NPA %","net_npa")):
        values=[value for value in rows.get(label,[]) if value is not None]
        if values:result[key]=values[-1]/100
    return result

@ttl_cache(12*3600,cache_if=lambda result:result is not None)
def fetch_nse_pledge(symbol:str)->Optional[float]:
    """Best-effort share of promoter holding pledged (0-1) from NSE's public pledge disclosures; None when unavailable."""
    code=_screener_slug(symbol)
    try:
        session=requests.Session();session.headers.update({**HEADERS,"Referer":"https://www.nseindia.com/companies-listing/corporate-filings-pledged-data"})
        session.get("https://www.nseindia.com/",timeout=10)
        response=session.get("https://www.nseindia.com/api/corporate-pledgedata",params={"index":"equities","symbol":code},timeout=10);response.raise_for_status();payload=response.json()
        rows=payload.get("data") if isinstance(payload,dict) else payload
        if not isinstance(rows,list) or not rows or not isinstance(rows[0],dict):return None
        latest=rows[0];key=next((name for name in ("percSharesPledged","perSharesPledged") if name in latest),None) or next((name for name in latest if "pledge" in name.lower() and "per" in name.lower()),None)
        value=_num(latest.get(key)) if key else None
        return value/100 if value is not None and 0<=value<=100 else None
    except Exception:return None

@ttl_cache(QUOTE_TTL_SECONDS,cache_if=lambda result:result[0] is not None)
def fetch_nse_quote(symbol:str)->tuple[Optional[float],str,str]:
    code=_screener_slug(symbol)
    try:
        session=requests.Session();session.headers.update({**HEADERS,"Referer":"https://www.nseindia.com/get-quotes/equity?symbol="+code})
        session.get("https://www.nseindia.com/",timeout=12)
        response=session.get("https://www.nseindia.com/api/quote-equity",params={"symbol":code},timeout=12);response.raise_for_status();data=response.json();price=_num((data.get("priceInfo") or {}).get("lastPrice"));stamp=str((data.get("metadata") or {}).get("lastUpdateTime") or "")
        return price,stamp,"" if price is not None else "NSE India returned no last price."
    except Exception as exc:return None,"",f"NSE India verification unavailable: {type(exc).__name__}."

@ttl_cache(12*3600,cache_if=lambda code:code is not None)
def _resolve_bse_code(symbol:str)->Optional[str]:
    slug=_screener_slug(symbol)
    if slug.isdigit():return slug
    try:
        response=requests.get(
            "https://api.bseindia.com/Msource/1D/getQouteSearch.aspx",
            params={"Type":"EQ","text":slug,"flag":"site"},
            headers={**HEADERS,"Origin":"https://www.bseindia.com","Referer":"https://www.bseindia.com/"},
            timeout=12,
        )
        response.raise_for_status()
        soup=BeautifulSoup(response.text,"html.parser")
        candidates=[]
        for anchor in soup.find_all("a",href=True):
            match=re.search(r"/([^/]+)/(\d{6})/?$",anchor["href"])
            if match:candidates.append((match.group(1).upper(),match.group(2)))
        exact=next((code for security_id,code in candidates if security_id==slug),None)
        return exact
    except Exception:
        return None

@ttl_cache(QUOTE_TTL_SECONDS,cache_if=lambda result:result[0] is not None)
def fetch_bse_quote(symbol:str)->tuple[Optional[float],str,str]:
    code=_resolve_bse_code(symbol)
    if not code:return None,"","BSE India scrip code could not be resolved."
    try:
        headers={**HEADERS,"Origin":"https://www.bseindia.com","Referer":"https://www.bseindia.com/"}
        r=requests.get("https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w",params={"Debtflag":"","scripcode":code,"seriesid":""},headers=headers,timeout=12);r.raise_for_status();data=r.json();price=_num((data.get("CurrRate") or {}).get("LTP"));stamp=str((data.get("Header") or {}).get("Ason") or "")
        return price,stamp,"" if price is not None else "BSE India returned no last price."
    except Exception as exc:return None,"",f"BSE India verification unavailable: {type(exc).__name__}."

def verify_indian_stock(symbol:str,market:str,yahoo_price:Optional[float])->IndiaSourceResult:
    result=IndiaSourceResult();ratios,url,error=fetch_screener(symbol);financials,periods=fetch_screener_financials(symbol);result.screener_ratios=ratios;result.screener_financials=financials;result.screener_periods=periods;result.screener_url=url;result.screener_tables=fetch_screener_tables(symbol)
    if market=="NSE":result.promoter_pledge=fetch_nse_pledge(symbol)
    if ratios:result.sources_checked.append("Screener.in")
    if error:result.warnings.append(error)
    if market=="NSE":price,stamp,error=fetch_nse_quote(symbol);name="NSE India"
    else:price,stamp,error=fetch_bse_quote(symbol);name="BSE India"
    result.exchange_price=price;result.exchange_name=name;result.exchange_timestamp=stamp
    if market=="NSE":result.exchange_url=f"https://www.nseindia.com/get-quotes/equity?symbol={_screener_slug(symbol)}"
    else:
        code=_resolve_bse_code(symbol);result.exchange_url=f"https://api.bseindia.com/BseIndiaAPI/api/getScripHeaderData/w?Debtflag=&scripcode={code or _screener_slug(symbol)}&seriesid="
    if price is not None:result.sources_checked.append(name)
    if error:result.warnings.append(error)
    if price and yahoo_price and abs(price-yahoo_price)/max(price,yahoo_price)>.02:result.warnings.append(f"Price discrepancy: Yahoo {yahoo_price:,.2f} vs {name} {price:,.2f} exceeds 2%.")
    screener_price=ratios.get("Current Price")
    if screener_price and yahoo_price and abs(screener_price-yahoo_price)/max(screener_price,yahoo_price)>.02:result.warnings.append(f"Price discrepancy: Yahoo {yahoo_price:,.2f} vs Screener.in {screener_price:,.2f} exceeds 2%.")
    return result
