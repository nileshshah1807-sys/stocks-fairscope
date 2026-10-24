"""Free stock/company search for the Qt autocomplete control."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import requests

from ttl_cache import ttl_cache

USER_AGENT="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123 Safari/537.36 DR-Nilesh-Shah-Stocks-FairScope/8.4"

@dataclass(frozen=True)
class StockSearchResult:
    symbol:str
    company:str
    market:str
    exchange:str
    source:str

    @property
    def display(self)->str:
        exchange=self.exchange or self.market
        return f"{self.symbol}  —  {self.company}  •  {exchange}"


def _clean_symbol(value:str)->str:
    return str(value or "").strip().upper().replace(" ","")

# Empty results are not cached so a temporary network failure does not disable a query for the whole session.
# Providers return None when the lookup itself failed (rate limit, offline), which differs from "no matches".
@ttl_cache(3600,cache_if=bool)
def _search_yahoo(query:str,limit:int)->Optional[tuple[StockSearchResult,...]]:
    try:
        import yfinance as yf
        from yfinance.data import YfData
        def ask():return yf.Search(query,max_results=max(limit,12),news_count=0,lists_count=0,include_cb=False,include_nav_links=False,include_research=False,enable_fuzzy_query=True,timeout=12,raise_errors=True).quotes
        quotes=ask()
        if not quotes:
            # yfinance memoizes raw responses for the whole session, so one throttled empty reply would repeat forever; drop it and ask again.
            YfData.cache_get.cache_clear();quotes=ask()
        results=[]
        allowed={"NMS","NYQ","ASE","NCM","NGM","PCX","BTS","PNK","OQB","OEM"}
        for item in quotes:
            if item.get("quoteType")!="EQUITY":continue
            symbol=_clean_symbol(item.get("symbol"));exchange=str(item.get("exchange") or "")
            if not symbol or exchange not in allowed or "." in symbol:continue
            company=str(item.get("longname") or item.get("shortname") or symbol).strip()
            results.append(StockSearchResult(symbol,company,"US",str(item.get("exchDisp") or exchange),"Yahoo Finance"))
            if len(results)>=limit:break
        return tuple(results)
    except Exception:return None

@ttl_cache(3600,cache_if=bool)
def _search_screener(query:str,market:str,limit:int)->Optional[tuple[StockSearchResult,...]]:
    try:
        response=requests.get("https://www.screener.in/api/company/search/",params={"q":query},headers={"User-Agent":USER_AGENT,"Accept":"application/json"},timeout=12)
        response.raise_for_status()
        results=[]
        for item in response.json():
            url=str(item.get("url") or "")
            match=re.search(r"/company/([^/]+)/",url)
            if not match:
                continue
            symbol=_clean_symbol(match.group(1))
            company=str(item.get("name") or symbol).strip()
            if market=="NSE" and symbol.isdigit():
                continue
            if any(term in company.upper() for term in (" ETF"," EXCHANGE TRADED FUND")):
                continue
            if symbol and not any(x.symbol==symbol for x in results):
                results.append(StockSearchResult(symbol,company,market,market,"Screener.in"))
            if len(results)>=limit:
                break
        return tuple(results)
    except Exception:return None

@ttl_cache(3600,maxsize=512,cache_if=lambda results:any(result.source!="Direct entry" for result in results))
def search_stocks(query:str,market:str="US",limit:int=10)->tuple[StockSearchResult,...]:
    query=" ".join(str(query or "").strip().split())
    market=market.upper()
    if len(query)<2:return ()
    found=_search_yahoo(query,limit) if market=="US" else _search_screener(query,market,limit)
    results=list(found or ())
    exact=_clean_symbol(query).replace(".NS","").replace(".BO","")
    typed_as_ticker=query.replace(" ","")==query.replace(" ","").upper() or exact.isdigit()
    # Any single word is offered as a ticker when nothing matched: users type tickers in lowercase and Yahoo intermittently answers empty.
    if not results and (typed_as_ticker or " " not in query) and re.fullmatch(r"[A-Z0-9&-]{1,20}",exact):
        results.append(StockSearchResult(exact,"Use entered ticker" if found is not None else "Use entered ticker • live search unavailable",market,market,"Direct entry"))
    return tuple(results[:limit])
