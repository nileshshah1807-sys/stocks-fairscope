"""Free Yahoo Finance adapter through yfinance. No API key is required."""
from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any, Optional

import sec_facts
from fundamentals import cagr, level_adjusted_long_median, normalized_cash_flows
from india_sources import screener_asset_quality, screener_long_history, verify_indian_stock
from local_database import get_local_database
from logger import get_logger
from secure_storage import SecureStorage, data_directory
from ttl_cache import ttl_cache
from valuation import DataLineageEntry, FinancialCompanyMetrics, StockData

logger = get_logger("DataProvider")
PROVIDER_NAME="Yahoo Finance (free)"

class DataProviderError(RuntimeError):
    """Base error for data retrieval."""
    pass

class RateLimitError(DataProviderError):
    """429 Too Many Requests."""
    pass

class NetworkError(DataProviderError):
    """Transient connection/timeout issue."""
    pass

class MissingDataError(DataProviderError):
    """Ticker exists but required fundamentals are missing."""
    pass

def is_transient_error(message:str)->bool:
    message=message.lower()
    return any(token in message for token in ("429","rate limit","timeout","timed out","temporar","connection","connect","network","502","503","504","too many requests"))

def _optional(fetch):
    """Fetch a secondary Yahoo endpoint; transient failures propagate so the batch retry backs off instead of valuing and caching a degraded snapshot."""
    try:return fetch()
    except Exception as exc:
        if is_transient_error(str(exc)):raise
        return None

def normalize_symbol(raw:str,market:str)->str:
    symbol=raw.strip().upper().replace(" ","")
    if not symbol:raise DataProviderError("Enter a ticker symbol.")
    if symbol.endswith(".NSE"):symbol=symbol[:-4]+".NS"
    elif symbol.endswith(".BSE"):symbol=symbol[:-4]+".BO"
    elif market=="US" and symbol.count(".")==1:symbol=symbol.replace(".","-")
    if market=="NSE" and not symbol.endswith((".NS",".BO")):symbol+=".NS"
    elif market=="BSE" and not symbol.endswith((".BO",".NS")):symbol+=".BO"
    return symbol

def _number(value:Any)->Optional[float]:
    try:
        value=float(value);return value if value==value and value not in (float("inf"),float("-inf")) else None
    except (TypeError,ValueError):return None

def _in_currency(frame:Any,rate:float)->Any:
    """Convert statement money rows at an FX rate; share counts and tax rates keep their units."""
    if frame is None or getattr(frame,"empty",True):return frame
    money=[name for name in frame.index if "Share" not in str(name) and "Rate" not in str(name)]
    frame=frame.copy();frame.loc[money]=frame.loc[money].astype(float)*rate;return frame

@ttl_cache(3600,cache_if=lambda rate:rate is not None)
def _fx_rate(source:str,target:str)->Optional[float]:
    """Latest Yahoo close for one unit of source currency in target currency; transient errors propagate to the retry."""
    import yfinance as yf
    closes=_optional(lambda:yf.Ticker(f"{source}{target}=X").history(period="5d")["Close"].dropna())
    rate=_number(closes.iloc[-1]) if closes is not None and len(closes) else None
    return rate if rate and rate>0 else None

def _statement_values(statement:Any,names:list[str],limit:int=5)->list[float]:
    if statement is None or getattr(statement,"empty",True):return []
    for name in names:
        if name in statement.index:
            values=[]
            for value in statement.loc[name]:
                parsed=_number(value)
                if parsed is not None:values.append(parsed)
                if len(values)>=limit:break
            return values
    return []
def _first(statement:Any,names:list[str])->Optional[float]:
    values=_statement_values(statement,names,1);return values[0] if values else None
def _ttm(statement:Any,names:list[str])->Optional[float]:
    values=_statement_values(statement,names,4)
    return sum(values) if values else None
def _peer_key(symbol:str)->str:return symbol.upper().split(".")[0]

# Statement rows aligned by fiscal year (latest first). Yahoo signs: capex, repurchases, and dividends are negative.
STATEMENT_ROWS={
    "revenue":("income",["Total Revenue","Operating Revenue"]),"cost_of_revenue":("income",["Cost Of Revenue","Reconciled Cost Of Revenue"]),"gross_profit":("income",["Gross Profit"]),
    "sga":("income",["Selling General And Administration"]),"ebit":("income",["EBIT","Operating Income"]),"ebitda":("income",["EBITDA","Normalized EBITDA"]),
    "net_income":("income",["Net Income","Net Income Common Stockholders"]),"tax_rate":("income",["Tax Rate For Calcs"]),"interest_expense":("income",["Interest Expense","Interest Expense Non Operating"]),
    "diluted_shares":("income",["Diluted Average Shares","Basic Average Shares"]),
    "depreciation":("cashflow",["Depreciation And Amortization","Depreciation Amortization Depletion","Depreciation"]),"capital_expenditure":("cashflow",["Capital Expenditure","Capital Expenditures"]),
    "working_capital_change":("cashflow",["Change In Working Capital"]),"stock_based_compensation":("cashflow",["Stock Based Compensation"]),
    "operating_cash_flow":("cashflow",["Operating Cash Flow","Total Cash From Operating Activities"]),"free_cash_flow":("cashflow",["Free Cash Flow"]),
    "repurchase_of_stock":("cashflow",["Repurchase Of Capital Stock","Common Stock Payments"]),"issuance_of_stock":("cashflow",["Issuance Of Capital Stock","Common Stock Issuance"]),
    "dividends_paid":("cashflow",["Cash Dividends Paid","Common Stock Dividend Paid"]),
    "total_assets":("balance",["Total Assets"]),"current_assets":("balance",["Current Assets","Total Current Assets"]),"current_liabilities":("balance",["Current Liabilities","Total Current Liabilities"]),
    "total_liabilities":("balance",["Total Liabilities Net Minority Interest","Total Liabilities"]),"long_term_debt":("balance",["Long Term Debt","Long Term Debt And Capital Lease Obligation"]),
    "total_debt":("balance",["Total Debt"]),"cash":("balance",["Cash Cash Equivalents And Short Term Investments","Cash And Cash Equivalents"]),
    "equity":("balance",["Stockholders Equity","Total Stockholder Equity","Common Stock Equity"]),"ppe":("balance",["Net PPE","Net Property Plant And Equipment"]),
    "receivables":("balance",["Accounts Receivable","Receivables","Net Receivables"]),"inventory":("balance",["Inventory"]),"payables":("balance",["Accounts Payable","Payables"]),
    "retained_earnings":("balance",["Retained Earnings"]),"research_development":("income",["Research And Development"]),
}

def _period_key(column:Any)->str:
    try:return column.date().isoformat()
    except Exception:return str(column)[:10]

def _aligned_row(statement:Any,names:list[str],periods:list[str])->list[Optional[float]]:
    if statement is None or getattr(statement,"empty",True):return [None]*len(periods)
    for name in names:
        if name not in statement.index:continue
        try:row=statement.loc[name]
        except Exception:continue
        if getattr(row,"ndim",1)>1:row=row.iloc[0]
        exact={};by_year={}
        for column,value in row.items():
            key=_period_key(column);number=_number(value);exact[key]=number;by_year.setdefault(key[:4],number)
        values=[exact[period] if period in exact else by_year.get(period[:4]) for period in periods]
        if any(value is not None for value in values):return values
    return [None]*len(periods)

def _aligned_statements(income:Any,balance:Any,cashflow:Any)->tuple[list[str],dict[str,list[Optional[float]]]]:
    frames={"income":income,"balance":balance,"cashflow":cashflow}
    master=next((frame for frame in (income,cashflow,balance) if frame is not None and not getattr(frame,"empty",True)),None)
    if master is None:return [],{}
    periods=[_period_key(column) for column in list(master.columns)[:5]];statements={}
    for key,(frame,names) in STATEMENT_ROWS.items():
        values=_aligned_row(frames[frame],names,periods)
        if any(value is not None for value in values):statements[key]=values
    if "depreciation" not in statements:
        values=_aligned_row(income,["Reconciled Depreciation"],periods)
        if any(value is not None for value in values):statements["depreciation"]=values
    return periods,statements

def _monthly_series(history:Any)->tuple[list[str],list[float],list[float]]:
    """Month-end split-adjusted and total-return closes, oldest first; the final point is the latest session."""
    closes=history["Close"].tolist();adjusted=history["Adj Close"].tolist() if "Adj Close" in history.columns else closes;months={}
    for index,close,total in zip(history.index,closes,adjusted):
        price=_number(close)
        if price is None:continue
        months[(index.year,index.month)]=(str(index.date()),price,_number(total) or price)
    ordered=[months[key] for key in sorted(months)]
    return [item[0] for item in ordered],[item[1] for item in ordered],[item[2] for item in ordered]

INDEX_BENCHMARKS={"US":("^GSPC","S&P 500"),"IN":("^NSEI","NIFTY 50")}

@ttl_cache(24*3600,maxsize=4,cache_if=bool)
def _index_monthly(symbol:str)->dict[str,float]:
    try:
        import yfinance as yf
        dates,_closes,adjusted=_monthly_series(yf.Ticker(symbol).history(period="5y",auto_adjust=False))
        return {date[:7]:value for date,value in zip(dates,adjusted)}
    except Exception:return {}

def _regression_beta(dates:list[str],adjusted:list[float],index_by_month:dict[str,float])->Optional[tuple[float,float]]:
    """Five-year monthly total-return beta against the market index and its standard error; needs at least 24 overlapping months."""
    pairs=[]
    for position in range(1,len(dates)):
        start,end=dates[position-1][:7],dates[position][:7]
        if start in index_by_month and end in index_by_month and adjusted[position-1]>0 and index_by_month[start]>0:
            pairs.append((adjusted[position]/adjusted[position-1]-1,index_by_month[end]/index_by_month[start]-1))
    if len(pairs)<24:return None
    stock_mean=sum(x for x,_ in pairs)/len(pairs);market_mean=sum(y for _,y in pairs)/len(pairs)
    variance=sum((y-market_mean)**2 for _,y in pairs)
    if variance<=0:return None
    beta=sum((x-stock_mean)*(y-market_mean) for x,y in pairs)/variance
    residual=sum((x-stock_mean-beta*(y-market_mean))**2 for x,y in pairs)
    return (beta,(residual/(len(pairs)-2)/variance)**.5) if -1<beta<4 else None

MARKET_PARAMETER_DEFAULTS={"live_us_risk_free":True,"risk_free_us":.043,"risk_free_india":.065,"erp_us":.045,"erp_india":.055,"damodaran_erp":True,"scenario_weights":[.25,.50,.25],"holding_discount":.20}

# Damodaran (NYU Stern) total equity risk premium and sovereign default spread; used offline when the live table is unreachable.
DAMODARAN_URL="https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ctryprem.html"
DAMODARAN_FALLBACK={"US":{"erp":.0446,"default_spread":.0023},"IN":{"erp":.0708,"default_spread":.0187},"as_of":"January 2026, built-in"}

def _country_premiums_from_html(text:str)->Optional[dict]:
    """US and India rows of Damodaran's country risk table: (adjusted default spread, total equity risk premium)."""
    from bs4 import BeautifulSoup
    found={}
    for row in BeautifulSoup(text,"html.parser").find_all("tr"):
        cells=[" ".join(cell.get_text(" ",strip=True).split()) for cell in row.find_all(["td","th"])]
        if len(cells)>=5 and cells[0] in {"United States","India"}:
            spread,erp=_number(cells[2].rstrip("%")),_number(cells[4].rstrip("%"))
            if spread is not None and erp is not None and 0<=spread<=10 and 2<=erp<=15:found["US" if cells[0]=="United States" else "IN"]={"erp":erp/100,"default_spread":spread/100}
    return {**found,"as_of":"Damodaran live table"} if len(found)==2 else None

@ttl_cache(24*3600,cache_if=lambda value:value is not None)
def _damodaran_country_premiums()->Optional[dict]:
    try:
        import requests
        response=requests.get(DAMODARAN_URL,headers={"User-Agent":"Mozilla/5.0 DR-Nilesh-Shah-Stocks-FairScope"},timeout=20);response.raise_for_status()
        return _country_premiums_from_html(response.text)
    except Exception:return None

@ttl_cache(6*3600,cache_if=lambda value:value is not None)
def _live_us_risk_free()->Optional[float]:
    try:
        import yfinance as yf
        closes=yf.Ticker("^TNX").history(period="5d")["Close"].dropna()
        value=_number(closes.iloc[-1])/100 if len(closes) else None
        return value if value is not None and .002<=value<=.15 else None
    except Exception:return None

def valuation_settings(database)->dict:
    return {key:database.setting(key,default) for key,default in MARKET_PARAMETER_DEFAULTS.items()}

def apply_market_parameters(data:StockData,database)->StockData:
    """Stamp the current risk-free rate, equity risk premium, scenario weights, and holding discount onto the snapshot."""
    settings=valuation_settings(database);region="IN" if data.market in {"NSE","BSE"} else "US"
    if region=="IN":rate,source,premium=float(settings["risk_free_india"]),"India 10-year government bond yield (Settings)",float(settings["erp_india"])
    else:
        live=_live_us_risk_free() if settings["live_us_risk_free"] else None
        rate,source=(live,"US 10-year Treasury yield (^TNX, live)") if live is not None else (float(settings["risk_free_us"]),"US 10-year Treasury yield (Settings)")
        premium=float(settings["erp_us"])
    spread=0.0;premium_source="Settings";premium_url=""
    if settings.get("damodaran_erp",True):
        country=_damodaran_country_premiums() or DAMODARAN_FALLBACK
        premium,spread=country[region]["erp"],country[region]["default_spread"];premium_source=f"Damodaran country risk premiums ({country['as_of']})";premium_url=DAMODARAN_URL
        # Damodaran's total premium already prices country risk, so the government yield sheds its default spread to avoid counting it twice.
        source+=f" less {spread:.2%} sovereign default spread"
    rate-=spread
    data.risk_free_rate=rate;data.risk_free_source=source;data.equity_risk_premium=premium;data.country_default_spread=spread
    weights=[float(value) for value in (settings["scenario_weights"] or [])][:3]
    data.scenario_weights=weights if len(weights)==3 and all(value>=0 for value in weights) and sum(weights)>0 else list(MARKET_PARAMETER_DEFAULTS["scenario_weights"])
    data.holding_discount=min(.9,max(0.0,float(settings["holding_discount"])))
    stamp=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    data.lineage=[entry for entry in data.lineage if entry.metric not in {"Risk-free rate","Equity risk premium"}]+[
        DataLineageEntry("Risk-free rate",f"{rate:.2%}",source,"https://finance.yahoo.com/quote/%5ETNX" if "live" in source else "",stamp[:10],stamp,"Used in CAPM cost of equity and cost of debt floor","Selected"),
        DataLineageEntry("Equity risk premium",f"{premium:.2%}",premium_source,premium_url,stamp[:10],stamp,"Market premium (including country risk) multiplied by adjusted beta","Selected")]
    return data

def latest_closes(symbols:list[str])->dict[str,float]:
    """Latest daily close per Yahoo symbol, in one batched download."""
    if not symbols:return {}
    import yfinance as yf
    frame=yf.download(sorted(set(symbols)),period="5d",auto_adjust=False,progress=False,multi_level_index=True,threads=False)
    if frame is None or frame.empty:return {}
    closes=frame["Close"].ffill().iloc[-1]
    return {str(symbol):float(value) for symbol,value in closes.items() if _number(value)}

@ttl_cache(300,cache_if=bool)
def _sec_contact_email()->str:
    """The EDGAR contact email saved on the Filings & actions page; SEC refuses requests without one."""
    if not (data_directory()/"secure_settings.json").exists():return ""  # nothing ever saved: skip the OS keychain
    try:return SecureStorage(data_directory()).get_secret("sec_contact_email")
    except Exception:return ""

@ttl_cache(12*3600,maxsize=256,cache_if=lambda result:result is not None)
def _sec_history(symbol:str)->Optional[tuple[list[str],dict,str]]:
    """Up to 15 fiscal years of SEC EDGAR 10-K figures (periods, statement rows, CIK); None without an email, a CIK, or us-gaap filings."""
    email=_sec_contact_email()
    if not email or "@" not in email:return None
    agent=sec_facts.user_agent(email)
    try:
        cik=sec_facts.cik_for(symbol,agent)
        if not cik:return None
        periods,statements=sec_facts.annual_statements(sec_facts.company_facts(cik,agent))
        return (periods,statements,cik) if len(periods)>=3 else None
    except Exception:return None  # SEC history is supplementary; Yahoo data still values the stock

@ttl_cache(12*3600,maxsize=512,cache_if=lambda value:value is not None)
def _peer_enterprise_multiples(symbol:str)->Optional[tuple[Optional[float],Optional[float]]]:
    """A peer's (EV/EBITDA, EV/Sales) from one profile request, after outlier bounds."""
    try:
        import yfinance as yf
        info=yf.Ticker(symbol).info or {};ebitda=_number(info.get("enterpriseToEbitda"));sales=_number(info.get("enterpriseToRevenue"))
        multiples=(ebitda if ebitda is not None and 1<=ebitda<=80 else None,sales if sales is not None and .1<=sales<=30 else None)
        return multiples if any(value is not None for value in multiples) else None
    except Exception:return None

def _fit_line(pairs:list[tuple[float,float]])->Optional[list[float]]:
    """Least-squares [intercept, slope, x_min, x_max] of a multiple on its driver across peers; needs five peers with spread in the driver."""
    low,high=min((x for x,_ in pairs),default=0),max((x for x,_ in pairs),default=0)
    if len(pairs)<5 or high<=low:return None
    mean_x=sum(x for x,_ in pairs)/len(pairs);mean_y=sum(y for _,y in pairs)/len(pairs)
    slope=sum((x-mean_x)*(y-mean_y) for x,y in pairs)/sum((x-mean_x)**2 for x,_ in pairs)
    return [mean_y-slope*mean_x,slope,low,high]

@ttl_cache(6*3600,maxsize=128,cache_if=lambda result:bool(result["symbols"]))
def _fetch_peers(region:str,sector:str,industry:str,market_cap_bucket:int,own_symbol:str,include_enterprise:bool=True)->dict:
    """Same-region peers by industry/sector and size: trailing/forward P/E, P/B, EV/EBITDA, ROE (P/B ÷ P/E), and EPS growth."""
    empty={"pe":None,"pb":None,"forward_pe":None,"ev_ebitda":None,"ev_revenue":None,"roe":None,"growth":None,"pe_growth_fit":None,"pb_roe_fit":None,"symbols":()}
    try:
        import yfinance as yf
        cap=float(market_cap_bucket);probe=yf.EquityQuery("eq",["region",region]);scopes=[]
        if industry and industry in probe.valid_values.get("industry",[]):scopes.append(("industry",industry))
        if sector and sector in probe.valid_values.get("sector",[]):scopes.append(("sector",sector))
        pe_values=[];pb_values=[];forward=[];roes=[];growths=[];pe_growth=[];pb_roe=[];symbols=[];seen={_peer_key(own_symbol)}
        for field,value in scopes:
            for broad in (False,True):
                filters=[yf.EquityQuery("eq",["region",region]),yf.EquityQuery("eq",[field,value])]
                if cap>0:
                    low=cap*(.05 if broad else .15);high=cap*(15 if broad else 6)
                    filters += [yf.EquityQuery("gte",["intradaymarketcap",max(1_000_000,low)]),yf.EquityQuery("lte",["intradaymarketcap",high])]
                response=yf.screen(yf.EquityQuery("and",filters),size=40,sortField="intradaymarketcap",sortAsc=False)
                for quote in response.get("quotes",[]):
                    symbol=str(quote.get("symbol") or "");key=_peer_key(symbol)
                    if not symbol or key in seen:continue
                    pe=_number(quote.get("trailingPE"));pb=_number(quote.get("priceToBook"));forward_pe=_number(quote.get("forwardPE"));eps_forward=_number(quote.get("epsForward"));eps_trailing=_number(quote.get("epsTrailingTwelveMonths"))
                    if pe is not None and 3<=pe<=80:pe_values.append(pe)
                    if pb is not None and .1<=pb<=15:pb_values.append(pb)
                    if forward_pe is not None and 3<=forward_pe<=80:forward.append(forward_pe)
                    if pe is not None and pb is not None and 3<=pe<=80 and .1<=pb<=15:roes.append(pb/pe);pb_roe.append((pb/pe,pb))
                    if eps_forward is not None and eps_trailing and eps_trailing>0 and -.5<eps_forward/eps_trailing-1<1:
                        growths.append(eps_forward/eps_trailing-1)
                        if pe is not None and 3<=pe<=80:pe_growth.append((eps_forward/eps_trailing-1,pe))
                    if pe is not None or pb is not None:symbols.append(symbol);seen.add(key)
                    if len(symbols)>=12:break
                if len(symbols)>=8:break
            if len(symbols)>=8:break
        enterprise=[multiples for multiples in (_peer_enterprise_multiples(peer) for peer in symbols[:5]) if multiples is not None] if include_enterprise else []
        def middle(values):return median(values) if len(values)>=3 else None
        return {"pe":middle(pe_values),"pb":middle(pb_values),"forward_pe":middle(forward),"ev_ebitda":middle([x for x,_ in enterprise if x is not None]),"ev_revenue":middle([y for _,y in enterprise if y is not None]),"roe":middle(roes),"growth":middle(growths),"pe_growth_fit":_fit_line(pe_growth),"pb_roe_fit":_fit_line(pb_roe),"symbols":tuple(symbols)}
    except Exception:return empty

def fetch_stock(raw_symbol:str,market:str,force_refresh:bool=False,allow_stale:Optional[bool]=None)->StockData:
    symbol=normalize_symbol(raw_symbol,market);database=get_local_database();data=_fetch_stock(symbol,market,database,force_refresh,allow_stale)
    try:apply_market_parameters(data,database)
    except Exception:pass
    return data

def _fetch_stock(symbol:str,market:str,database,force_refresh:bool,allow_stale:Optional[bool])->StockData:
    stale_allowed=database.allow_stale_fallback() if allow_stale is None else allow_stale
    if not force_refresh:
        cached=database.load_stock(symbol,market,allow_expired=False)
        if cached is not None:return cached
    try:
        import yfinance as yf
    except ImportError as exc:
        stale=database.load_stock(symbol,market,allow_expired=True) if stale_allowed else None
        if stale is not None:return stale
        raise DataProviderError("yfinance is not installed. Run: pip install -r requirements.txt") from exc
    try:
        ticker=yf.Ticker(symbol);history=ticker.history(period="10y",auto_adjust=False)  # ten years so SEC-backed backtests have prices; beta still uses the 5-year index overlap
        if history.empty:raise DataProviderError(f"No market data found for {symbol}. Check the ticker and exchange.")
        price=_number(history["Close"].dropna().iloc[-1])
        if not price or price<=0:raise DataProviderError(f"No valid latest price found for {symbol}.")
        warnings=["Free Yahoo Finance data may be delayed, incomplete, rate-limited, or changed without notice. Verify official filings."]
        info=_optional(lambda:ticker.info) or {}
        if not info:warnings.append("Detailed company profile was partly unavailable.")
        cashflow=_optional(lambda:ticker.cashflow);income=_optional(lambda:ticker.income_stmt);balance=_optional(lambda:ticker.balance_sheet)
        # Foreign listings (ADRs such as TSM) report in their home currency; convert so per-share values match the quoted price.
        currency=info.get("currency") or ("INR" if market in {"NSE","BSE"} else "USD");reporting=info.get("financialCurrency") or currency;fx=1.0
        if reporting!=currency:
            fx=_fx_rate(reporting,currency)
            if fx is None:raise DataProviderError(f"{symbol} reports in {reporting} but trades in {currency}, and the {reporting}/{currency} exchange rate was unavailable; the app will not value it with mixed currencies. Retry shortly.")
            cashflow,income,balance=(_in_currency(frame,fx) for frame in (cashflow,income,balance))
            # Yahoo quotes these totals in the reporting currency; its book value and price/book mix units for ADRs, so they are rebuilt from converted equity.
            info={**info,**{key:info[key]*fx for key in ("totalDebt","totalCash","ebitda","totalRevenue","netIncomeToCommon","freeCashflow") if _number(info.get(key)) is not None},"bookValue":None,"priceToBook":None}
            if _number(info.get("marketCap")):info["sharesOutstanding"]=info["marketCap"]/price  # ADR-equivalent shares, consistent with the quoted price
            warnings.append(f"Financial statements are reported in {reporting} and were converted to {currency} at {fx:.6g} ({reporting}{currency}=X); the share count is listing-equivalent (market cap ÷ price).")
        shares=_number(info.get("sharesOutstanding"))
        if not shares:
            try:shares=_number(ticker.get_shares_full(start=None,end=None).dropna().iloc[-1])
            except Exception:pass
        if not shares:
            market_cap_hint=_number(info.get("marketCap"))
            if market_cap_hint and price:shares=market_cap_hint/price;warnings.append("Share count was inferred from market capitalization divided by price.")
        # Histories come from the year-aligned rows, so a blank year is skipped instead of shifting later years onto the wrong period.
        statement_years,statements=_aligned_statements(income,balance,cashflow)
        sec=_sec_history(symbol) if market=="US" and reporting=="USD" else None
        if sec and not statements:
            # Yahoo statements unavailable: the latest five SEC 10-K years stand in, so the stock can still be valued.
            statement_years,statements=sec[0][:5],{key:values[:5] for key,values in sec[1].items()};warnings.append("Yahoo financial statements were unavailable; SEC EDGAR 10-K figures were used.")
        sbc_values=[value for value in statements.get("stock_based_compensation",[]) if value is not None]
        def reported(key):return [value for value in statements.get(key,[]) if value is not None]
        fcf_history=reported("free_cash_flow") or [o+c if c<0 else o-c for o,c in zip(statements.get("operating_cash_flow",[]),statements.get("capital_expenditure",[])) if o is not None and c is not None]
        revenue_history=reported("revenue");net_income_history=reported("net_income")
        if not fcf_history or not revenue_history or not net_income_history:
            try:quarterly_cashflow=ticker.quarterly_cashflow
            except Exception:quarterly_cashflow=None
            try:quarterly_income=ticker.quarterly_income_stmt
            except Exception:quarterly_income=None
            if fx!=1:quarterly_cashflow,quarterly_income=_in_currency(quarterly_cashflow,fx),_in_currency(quarterly_income,fx)
            if not fcf_history:
                ttm_fcf=_ttm(quarterly_cashflow,["Free Cash Flow"])
                if ttm_fcf is None:
                    ttm_ocf=_ttm(quarterly_cashflow,["Operating Cash Flow","Total Cash From Operating Activities"]);ttm_capex=_ttm(quarterly_cashflow,["Capital Expenditure","Capital Expenditures"])
                    if ttm_ocf is not None and ttm_capex is not None:ttm_fcf=ttm_ocf+ttm_capex if ttm_capex<0 else ttm_ocf-ttm_capex
                if ttm_fcf is not None:fcf_history=[ttm_fcf];warnings.append("Annual FCF was unavailable; trailing-four-quarter FCF was used.")
            if not revenue_history:
                ttm_revenue=_ttm(quarterly_income,["Total Revenue","Operating Revenue"])
                if ttm_revenue is not None:revenue_history=[ttm_revenue];warnings.append("Annual revenue was unavailable; trailing-four-quarter revenue was used.")
            if not net_income_history:
                ttm_income=_ttm(quarterly_income,["Net Income","Net Income Common Stockholders"])
                if ttm_income is not None:net_income_history=[ttm_income]
        if not revenue_history and _number(info.get("totalRevenue")) is not None:revenue_history=[_number(info.get("totalRevenue"))];warnings.append("Annual revenue history was unavailable; trailing revenue was used for fallback analysis.")
        if not net_income_history and _number(info.get("netIncomeToCommon")) is not None:net_income_history=[_number(info.get("netIncomeToCommon"))]
        if not fcf_history and _number(info.get("freeCashflow")) is not None:fcf_history=[_number(info.get("freeCashflow"))];warnings.append("Annual FCF history was unavailable; trailing free cash flow was used.")
        latest_revenue=revenue_history[0] if revenue_history else None;margin_fcf,margin_income,_eps=normalized_cash_flows(statements,latest_revenue,shares)
        normalized_income=margin_income if margin_income is not None else (median(net_income_history) if net_income_history else None)
        eps=(normalized_income/shares) if normalized_income is not None and shares else (_number(info.get("trailingEps")) or _number(info.get("forwardEps")))
        normalized_fcf=margin_fcf if margin_fcf is not None else ((median(fcf_history)-(median(sbc_values) if sbc_values else 0.0)) if fcf_history else None)
        analyst_growth=analyst_long_term=None
        try:
            estimates=ticker.growth_estimates
            if estimates is not None and not estimates.empty and "stockTrend" in estimates.columns:
                def estimate(labels):
                    for label in labels:
                        value=_number(estimates.loc[label,"stockTrend"]) if label in estimates.index else None
                        if value is not None and -.5<value<1:return value
                    return None
                analyst_growth=estimate(("+1y","0y"));analyst_long_term=estimate(("LTG","+5y"))
        except Exception:pass
        long_dates,long_closes,long_adjusted=_monthly_series(history)
        equity=_first(balance,["Stockholders Equity","Total Stockholder Equity"]);bvps=_number(info.get("bookValue")) or ((equity/shares) if equity and shares else None)
        growths=[_number(info.get("earningsGrowth")),_number(info.get("revenueGrowth")),cagr(statements.get("revenue",[])),cagr(statements.get("net_income",[]))];growths=[x for x in growths if x is not None and -.5<x<1]
        if len(fcf_history)<3:warnings.append("Fewer than three annual free-cash-flow observations were available.")
        sector=info.get("sector") or "Not available";industry=info.get("industry") or "Not available";market_cap=_number(info.get("marketCap"));region="in" if market in {"NSE","BSE"} else "us";cap_bucket=int(round((market_cap or 0)/100_000_000)*100_000_000)
        financial_like="financial" in sector.lower() or "real estate" in sector.lower() or any(key in industry.lower() for key in ("bank","insurance","credit services","capital markets","reit"))
        peers=_fetch_peers(region,sector,industry,cap_bucket,symbol,not financial_like);peer_pe,peer_pb,peer_symbols=peers["pe"],peers["pb"],peers["symbols"]
        if not peer_symbols:warnings.append("Free peer screening returned too few usable comparable companies.")
        total_debt=_number(info.get("totalDebt")) or _first(balance,["Total Debt"]);cash=_number(info.get("totalCash")) or _first(balance,["Cash Cash Equivalents And Short Term Investments","Cash And Cash Equivalents"])
        ebitda=_number(info.get("ebitda")) or _first(income,["EBITDA","Normalized EBITDA"]);ebit=_first(income,["EBIT","Operating Income"]);interest=abs(_first(income,["Interest Expense","Interest Expense Non Operating"]) or 0) or None
        ocf=_first(cashflow,["Operating Cash Flow","Total Cash From Operating Activities"]);diluted=reported("diluted_shares");receivables=reported("receivables");inventory=reported("inventory")
        valid_history=history["Close"].dropna().tail(252);closes=[float(value) for value in valid_history.tolist() if _number(value) is not None];price_dates=[str(index.date()) for index in valid_history.index]
        source_updated=str(history.index[-1].date()) if len(history.index) else ""
        sources=["Yahoo Finance"]+(["SEC EDGAR"] if sec else []);checks={"Yahoo Finance":f"Price/fundamentals retrieved {source_updated or 'date unavailable'}"};discrepancies=[]
        trailing_pe=_number(info.get("trailingPE"));price_to_book=_number(info.get("priceToBook")) or (price/bvps if bvps else None);return_on_equity=_number(info.get("returnOnEquity"));verification=None;promoter_history=[];promoter_periods=[];low52=_number(info.get("fiftyTwoWeekLow")) or _number(history["Low"].tail(252).min());high52=_number(info.get("fiftyTwoWeekHigh")) or _number(history["High"].tail(252).max())
        if market in {"NSE","BSE"}:
            verification=verify_indian_stock(symbol,market,price);sources.extend(verification.sources_checked);warnings.extend(verification.warnings);discrepancies.extend([x for x in verification.warnings if "discrepancy" in x.lower()])
            if verification.exchange_price is not None:
                price=verification.exchange_price;checks[verification.exchange_name]=f"Official-site last price {price:,.2f} {verification.exchange_timestamp}".strip()
            ratios=verification.screener_ratios
            if ratios:
                checks["Screener.in"]=f"Ratios verified at {verification.screener_url}"
                trailing_pe=ratios.get("Stock P/E") or trailing_pe;bvps=ratios.get("Book Value") or bvps
                if ratios.get("ROE") is not None:return_on_equity=ratios["ROE"]/100
                if ratios.get("Market Cap") is not None:market_cap=ratios["Market Cap"]*10_000_000
                low52=ratios.get("52W Low") or low52;high52=ratios.get("52W High") or high52
                if price and bvps:price_to_book=price/bvps
            shareholding=verification.screener_financials
            promoter_key=next((key for key in shareholding if key.lower().startswith("shareholding pattern:promoter")),None)
            if promoter_key:
                values=shareholding[promoter_key];headers=verification.screener_periods.get("Shareholding Pattern",[])
                promoter_history=[value/100 for value in reversed(values[-13:]) if 0<=value<=100]
                promoter_periods=list(reversed(headers[-len(promoter_history):])) if headers and promoter_history else []
        tables=verification.screener_tables if verification is not None else {};long_history,long_periods=screener_long_history(tables)
        # US listings get the same 10+ year margin, tax, payout, and ROCE series from SEC 10-K filings that Screener.in supplies for India.
        if sec and not long_history:long_history,long_periods=sec_facts.long_history(sec[0],sec[1]),list(sec[0])
        asset_quality=screener_asset_quality(tables)
        long_net=[value for value in long_history.get("net_margin",[])[:10] if value is not None]
        net_margins=[income_value/sales if income_value is not None and sales and sales>0 else None for income_value,sales in zip(statements.get("net_income",[]),statements.get("revenue",[]))]
        long_net_margin=level_adjusted_long_median(long_history.get("net_margin",[]),long_periods,statement_years,net_margins)
        if long_net_margin is not None and margin_income is not None and latest_revenue and latest_revenue>0 and shares:
            recent_margin=margin_income/latest_revenue;blended=long_net_margin if sector.lower() in {"energy","basic materials"} else .5*recent_margin+.5*long_net_margin
            normalized_income=latest_revenue*blended;eps=normalized_income/shares
        financial_metrics=None;financial_keywords=("bank","insurance","credit services","financial services","capital markets","asset management","mortgage","consumer finance")
        if "financial" in sector.lower() or any(keyword in industry.lower() for keyword in financial_keywords):
            industry_lower=industry.lower();subtype="Insurance" if "insurance" in industry_lower else "Bank" if "bank" in industry_lower else "NBFC / lender" if any(key in industry_lower for key in ("credit","mortgage","consumer finance")) else "Capital markets / asset management" if any(key in industry_lower for key in ("capital markets","asset management")) else "Diversified financial"
            screen_financials=verification.screener_financials if verification is not None else {}
            deposits_series=screen_financials.get("Balance Sheet:Deposits",[]);borrowings_series=screen_financials.get("Balance Sheet:Borrowing",[]) or screen_financials.get("Balance Sheet:Borrowings",[]);assets_series=screen_financials.get("Balance Sheet:Total Assets",[]);financing_series=screen_financials.get("Profit & Loss:Financing Margin %",[])
            total_assets_yahoo=_first(balance,["Total Assets"]);expense=_first(income,["Operating Expense","Total Operating Expenses"]);latest_revenue=revenue_history[0] if revenue_history else None;unit_multiplier=10_000_000 if currency=="INR" else 1
            financial_metrics=FinancialCompanyMetrics(subtype=subtype,reviewed_roe=return_on_equity,gross_npa=asset_quality.get("gross_npa"),net_npa=asset_quality.get("net_npa"),financing_margin=(financing_series[-1]/100 if financing_series else None),deposit_growth=((deposits_series[-1]/deposits_series[-2]-1) if len(deposits_series)>=2 and deposits_series[-2]>0 else None),cost_to_income=((expense/latest_revenue) if expense is not None and latest_revenue and latest_revenue>0 else None),equity_to_assets=((equity/total_assets_yahoo) if equity is not None and total_assets_yahoo and total_assets_yahoo>0 else None),premium_growth=(cagr(statements.get("revenue",[])) if subtype=="Insurance" else None),deposits=(deposits_series[-1]*unit_multiplier if deposits_series else None),borrowings=(borrowings_series[-1]*unit_multiplier if borrowings_series else total_debt),total_assets=(assets_series[-1]*unit_multiplier if assets_series else total_assets_yahoo),source="Yahoo Finance + Screener.in" if screen_financials else "Yahoo Finance")
            financial_metrics.automatic_values={key:getattr(financial_metrics,key) for key in ("reviewed_roe","net_interest_margin","financing_margin","gross_npa","net_npa","capital_adequacy","cet1_ratio","provision_coverage","casa_ratio","credit_cost","deposit_growth","loan_growth","cost_to_income","equity_to_assets","solvency_ratio","embedded_value_per_share","fair_price_to_embedded_value","vnb_margin","premium_growth")}
        provider_label=" + ".join(sources);retrieved_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z");years=[str(getattr(c,"year",c)) for c in getattr(cashflow,"columns",[])[:5]];periods=", ".join(years) or "Period unavailable";quote_url=f"https://finance.yahoo.com/quote/{symbol}";lineage=[]
        def add_lineage(metric,value,source,url,period,transformation,status):lineage.append(DataLineageEntry(metric,str(value),source,url,period,retrieved_at,transformation,status))
        selected_price_source=verification.exchange_name if market in {"NSE","BSE"} and verification.exchange_price is not None else "Yahoo Finance";selected_price_url=verification.exchange_url if market in {"NSE","BSE"} and verification.exchange_price is not None else quote_url
        add_lineage("Market price",f"{currency} {price:,.2f}",selected_price_source,selected_price_url,verification.exchange_timestamp if market in {"NSE","BSE"} and verification.exchange_price is not None else source_updated,"Official-site price selected when available; otherwise latest Yahoo close","Selected")
        add_lineage("One-year price history",f"{len(closes)} sessions","Yahoo Finance",quote_url+"/history",f"Through {source_updated}","Latest available closing prices; last 252 sessions retained","Received")
        if fx!=1:add_lineage("Currency conversion",f"1 {reporting} = {fx:.6g} {currency}","Yahoo Finance",f"https://finance.yahoo.com/quote/{reporting}{currency}%3DX",source_updated,"Statement amounts converted from the reporting currency to the listing currency; share count is listing-equivalent (market cap ÷ price)","Derived")
        if shares is not None:add_lineage("Shares outstanding",f"{shares:,.0f}","Yahoo Finance",quote_url+"/key-statistics",source_updated,"Reported shares outstanding; fallback to share-history endpoint","Received")
        if revenue_history:add_lineage("Revenue history",f"{len(revenue_history)} annual values","Yahoo Finance",quote_url+"/financials",periods,"Up to five annual statement values, latest first","Received")
        if normalized_income is not None:add_lineage("Normalized net income",f"{currency} {normalized_income:,.2f}","Yahoo Finance"+(" + Screener.in" if long_net_margin is not None else ""),quote_url+"/financials",periods,"Latest revenue × median net margin"+(" blended with the level-matched 10-year Screener.in median" if long_net_margin is not None else "")+"; median net income when margins are unavailable","Normalized")
        if normalized_fcf is not None:add_lineage("Normalized free cash flow",f"{currency} {normalized_fcf:,.2f}","Yahoo Finance",quote_url+"/cash-flow",periods,"Latest revenue × median FCF margin after stock-based compensation; median FCF fallback","Normalized")
        if sbc_values:add_lineage("Stock-based compensation",f"{currency} {sbc_values[0]:,.2f}","Yahoo Finance",quote_url+"/cash-flow",periods,"Deducted from free cash flow as a real cost to shareholders","Received")
        if eps is not None:add_lineage("Normalized EPS",f"{currency} {eps:,.4f}","Yahoo Finance",quote_url+"/financials",periods,"Normalized net income divided by current shares; reported EPS fallback","Derived")
        if sec:add_lineage("SEC EDGAR 10-K history",f"{len(sec[0])} fiscal years • {len(sec[1])} line items","SEC EDGAR",f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={sec[2]}&type=10-K",f"{sec[0][-1][:4]}–{sec[0][0][:4]}","us-gaap facts from 10-K filings (latest filing wins for restated years); feeds long-run margins, ROCE, tax, payout, and backtests","Received")
        elif market=="US" and reporting=="USD":add_lineage("SEC EDGAR 10-K history","Unavailable","SEC EDGAR","",source_updated,"Save an SEC contact email on the Filings & actions page to add 10-15 years of official 10-K history","Unavailable")
        if statements:add_lineage("Aligned statement history",f"{len(statement_years)} fiscal years • {len(statements)} line items","Yahoo Finance",quote_url+"/financials",", ".join(statement_years),"Income, balance-sheet, and cash-flow rows aligned by fiscal period for FCFF, ROIC, and forensic scores","Received")
        book_source="Screener.in" if market in {"NSE","BSE"} and verification.screener_ratios.get("Book Value") is not None else "Yahoo Finance";book_url=verification.screener_url if book_source=="Screener.in" else quote_url+"/balance-sheet"
        if bvps is not None:add_lineage("Book value per share",f"{currency} {bvps:,.4f}",book_source,book_url,source_updated,"Public top ratio or equity divided by shares","Selected")
        pe_source="Screener.in" if market in {"NSE","BSE"} and verification.screener_ratios.get("Stock P/E") is not None else "Yahoo Finance";pe_url=verification.screener_url if pe_source=="Screener.in" else quote_url
        if trailing_pe is not None:add_lineage("Trailing P/E",f"{trailing_pe:.3f}x",pe_source,pe_url,source_updated,"Direct provider ratio","Selected")
        if market_cap is not None:
            screener_market_cap=market in {"NSE","BSE"} and verification.screener_ratios.get("Market Cap") is not None
            add_lineage("Market capitalization",f"{currency} {market_cap:,.2f}","Screener.in" if screener_market_cap else "Yahoo Finance",verification.screener_url if screener_market_cap else quote_url,source_updated,"Crore value converted to currency units" if screener_market_cap else "Direct provider market-cap value","Selected")
        if return_on_equity is not None:add_lineage("Return on equity",f"{return_on_equity:.2%}","Screener.in" if market in {"NSE","BSE"} and verification.screener_ratios.get("ROE") is not None else "Yahoo Finance",verification.screener_url if market in {"NSE","BSE"} and verification.screener_ratios.get("ROE") is not None else quote_url+"/key-statistics",source_updated,"Direct ratio; Screener percentage converted to decimal","Selected")
        if total_debt is not None:add_lineage("Total debt",f"{currency} {total_debt:,.2f}","Yahoo Finance",quote_url+"/balance-sheet",periods,"Latest available annual balance-sheet value","Received")
        if cash is not None:add_lineage("Cash and equivalents",f"{currency} {cash:,.2f}","Yahoo Finance",quote_url+"/balance-sheet",periods,"Latest available annual balance-sheet value","Received")
        peer_value=peer_pb if peer_pb is not None else peer_pe;peer_label="Peer median P/B" if peer_pb is not None else "Peer median P/E"
        if peer_value is not None:add_lineage(peer_label,f"{peer_value:.3f}x","Yahoo Finance",quote_url,source_updated,f"Median of {len(peer_symbols)} screened same-region industry/sector peers after outlier bounds","Derived")
        else:add_lineage("Peer median","Unavailable","Yahoo Finance",quote_url,source_updated,"Peer screen returned fewer than three usable multiples","Unavailable")
        if market in {"NSE","BSE"} and verification.screener_ratios:add_lineage("Indian ratio cross-check",f"{len(verification.screener_ratios)} public top ratios","Screener.in",verification.screener_url,source_updated,"Cross-check selected price and fundamental ratios","Verified")
        if promoter_history:add_lineage("Promoter holding history",f"{promoter_history[0]:.2%} latest • {len(promoter_history)} observations","Screener.in",verification.screener_url,", ".join(promoter_periods[:13]),"Public shareholding-pattern observations stored latest first; approximately three years retained","Received")
        if market in {"NSE","BSE"}:add_lineage("Official exchange price check",f"{currency} {verification.exchange_price:,.2f}" if verification.exchange_price is not None else "Unavailable",verification.exchange_name,verification.exchange_url,verification.exchange_timestamp,"Best-effort public website quote check","Verified" if verification.exchange_price is not None else "Unavailable")
        provider_beta=_number(info.get("beta"));forward_eps=_number(info.get("forwardEps"));index_symbol,index_name=INDEX_BENCHMARKS["IN" if market in {"NSE","BSE"} else "US"]
        regression_beta,beta_error=_regression_beta(long_dates,long_adjusted,_index_monthly(index_symbol)) or (None,None)
        beta,beta_source=(regression_beta,f"5-year monthly regression vs {index_name}") if regression_beta is not None else (provider_beta,"Yahoo Finance beta" if provider_beta is not None else "")
        if beta is not None:add_lineage("Beta",f"{beta:.2f}"+(f" (Yahoo {provider_beta:.2f})" if regression_beta is not None and provider_beta is not None else ""),beta_source,quote_url+"/key-statistics",f"Through {source_updated}","Blume adjustment and 0.6-2.0 bounds applied in the cost of equity","Derived" if regression_beta is not None else "Received")
        if analyst_growth is not None or analyst_long_term is not None:add_lineage("Analyst growth estimates"," • ".join(text for text in (f"next year {analyst_growth:.1%}" if analyst_growth is not None else "",f"long-term {analyst_long_term:.1%}" if analyst_long_term is not None else "") if text),"Yahoo Finance",quote_url+"/analysis",source_updated,"Consensus EPS growth; weighted 30% in the automatic growth estimate","Received")
        if forward_eps is not None:add_lineage("Forward EPS",f"{currency} {forward_eps:,.4f}","Yahoo Finance",quote_url+"/analysis",source_updated,"Consensus next-year EPS used with the peer forward P/E","Received")
        for label,key,unit in (("Peer median forward P/E","forward_pe","x"),("Peer median EV/EBITDA","ev_ebitda","x"),("Peer median EV/Sales","ev_revenue","x"),("Peer median ROE","roe","%"),("Peer median EPS growth","growth","%")):
            if peers.get(key) is not None:add_lineage(label,f"{peers[key]:.2%}" if unit=="%" else f"{peers[key]:.2f}x","Yahoo Finance",quote_url,source_updated,"Median of screened peers after outlier bounds; ROE derived as P/B ÷ P/E","Derived")
        for label,key,driver in (("Peer P/E vs growth fit","pe_growth_fit","EPS growth"),("Peer P/B vs ROE fit","pb_roe_fit","ROE")):
            fit=peers.get(key)
            if fit:add_lineage(label,f"{fit[0]:.2f} + {fit[1]:.2f} × {driver}","Yahoo Finance",quote_url,source_updated,f"Least-squares line across screened peers; applied only within the peers' {driver} range","Derived")
        if len(long_net)>=6 and verification is not None:add_lineage("Ten-year margins, ROCE, and working capital",f"{len(long_history.get('ebit_margin',[]))} annual periods","Screener.in",verification.screener_url,", ".join(long_periods[:12]),"Operating margin = (operating profit - depreciation) / sales; used for margin normalization, ROCE, and cash-cycle scores","Received")
        if verification is not None and verification.promoter_pledge is not None:add_lineage("Promoter pledge",f"{verification.promoter_pledge:.2%} of promoter holding","NSE India","https://www.nseindia.com/companies-listing/corporate-filings-pledged-data",source_updated,"Latest public pledge disclosure (best effort)","Received")
        for label,key in (("Gross NPA","gross_npa"),("Net NPA","net_npa")):
            if key in asset_quality:add_lineage(label,f"{asset_quality[key]:.2%}","Screener.in",verification.screener_url,"Latest quarter","Quarterly results table","Received")
        if financial_metrics is not None:
            add_lineage("Financial company subtype",financial_metrics.subtype,"Classification engine",quote_url,source_updated,"Industry keyword classification for specialized model and risk rules","Derived")
            specialized=[("Financing margin",financial_metrics.financing_margin,"Screener.in",verification.screener_url if verification else quote_url,"Latest public P&L financing margin"),("Deposit growth",financial_metrics.deposit_growth,"Screener.in",verification.screener_url if verification else quote_url,"Latest deposits versus prior annual period"),("Cost-to-income proxy",financial_metrics.cost_to_income,"Yahoo Finance",quote_url+"/financials","Operating expense divided by reported revenue; not regulatory cost-to-income"),("Equity-to-assets",financial_metrics.equity_to_assets,"Yahoo Finance",quote_url+"/balance-sheet","Book equity divided by total assets; not regulatory capital adequacy"),("Premium growth",financial_metrics.premium_growth,"Yahoo Finance",quote_url+"/financials","Multi-year revenue CAGR proxy for insurer premium growth")]
            for metric,value,source,url,transformation in specialized:
                if value is not None:add_lineage(metric,f"{value:.2%}",source,url,periods,transformation,"Derived")
            for metric,value in (("Deposits",financial_metrics.deposits),("Borrowings",financial_metrics.borrowings),("Total assets",financial_metrics.total_assets)):
                if value is not None:add_lineage(metric,f"{currency} {value:,.2f}",financial_metrics.source,verification.screener_url if verification and verification.screener_financials else quote_url+"/balance-sheet",periods,"Latest available financial-company balance-sheet value","Received")
        result=StockData(symbol=symbol,company=info.get("longName") or info.get("shortName") or symbol,market=market,currency=currency,price=float(price),shares=shares,
            free_cash_flow=normalized_fcf,eps=eps,book_value_per_share=bvps,growth_estimate=median(growths) if growths else None,sector=sector,industry=industry,market_cap=market_cap,trailing_pe=trailing_pe,price_to_book=price_to_book,
            fifty_two_week_low=low52,fifty_two_week_high=high52,data_timestamp=retrieved_at,warnings=warnings,
            fcf_history=fcf_history,revenue_history=revenue_history,net_income_history=net_income_history,current_fcf=fcf_history[0] if fcf_history else None,total_debt=total_debt,cash=cash,ebitda=ebitda,ebit=ebit,interest_expense=interest,
            current_assets=_first(balance,["Current Assets","Total Current Assets"]),current_liabilities=_first(balance,["Current Liabilities","Total Current Liabilities"]),stockholder_equity=equity,operating_cash_flow=ocf,net_income=net_income_history[0] if net_income_history else None,
            peer_median_pe=peer_pe,peer_median_pb=peer_pb,peer_symbols=list(peer_symbols),fiscal_years=years,return_on_equity=return_on_equity,return_on_assets=_number(info.get("returnOnAssets")),gross_margins=_number(info.get("grossMargins")),operating_margins=_number(info.get("operatingMargins")),profit_margins=_number(info.get("profitMargins")),
            diluted_shares_history=diluted,receivables_history=receivables,inventory_history=inventory,capital_expenditure=abs(_first(cashflow,["Capital Expenditure","Capital Expenditures"]) or 0) or None,audit_risk=_number(info.get("auditRisk")),board_risk=_number(info.get("boardRisk")),shareholder_rights_risk=_number(info.get("shareHolderRightsRisk")),overall_governance_risk=_number(info.get("overallRisk")),insider_ownership=_number(info.get("heldPercentInsiders")),promoter_holding_history=promoter_history,promoter_holding_periods=promoter_periods,price_history=closes,price_dates=price_dates,
            data_provider=provider_label,source_symbol=symbol,source_updated_date=source_updated,licensed_data=False,data_sources=sources,source_checks=checks,source_discrepancies=discrepancies,lineage=lineage,financial_metrics=financial_metrics,cache_status="network",
            beta=beta,beta_source=beta_source,beta_standard_error=beta_error if regression_beta is not None else None,statement_years=statement_years,statements=statements,long_history=long_history,long_history_periods=long_periods,long_statement_years=list(sec[0]) if sec else [],long_statements=dict(sec[1]) if sec else {},long_price_dates=long_dates,long_prices=long_closes,long_adjusted_prices=long_adjusted,
            non_operating_investments=_first(balance,["Long Term Equity Investment","Investments In Other Ventures Under Equity Method"]),minority_interest=_first(balance,["Minority Interest"]),
            forward_eps=forward_eps,forward_pe=_number(info.get("forwardPE")),enterprise_to_ebitda=_number(info.get("enterpriseToEbitda")),analyst_growth=analyst_growth,analyst_long_term_growth=analyst_long_term,
            peer_median_forward_pe=peers["forward_pe"],peer_median_ev_ebitda=peers["ev_ebitda"],peer_median_roe=peers["roe"],peer_median_growth=peers["growth"],
            peer_median_ev_revenue=peers.get("ev_revenue"),peer_pe_growth_fit=list(peers.get("pe_growth_fit") or []),peer_pb_roe_fit=list(peers.get("pb_roe_fit") or []),
            promoter_pledge=verification.promoter_pledge if verification is not None else None,dividend_payout=_number(info.get("payoutRatio")),stock_based_compensation=sbc_values[0] if sbc_values else None)
        # Without the profile there is no sector, so no sector model; keep it out of the cache so the next run retries.
        if info:
            try:database.save_stock(result)
            except Exception:result.warnings.append("Local cache could not be updated; this analysis used freshly retrieved data.")
        return result
    except DataProviderError:
        stale=database.load_stock(symbol,market,allow_expired=True) if stale_allowed else None
        if stale is not None:return stale
        raise
    except Exception as exc:
        stale=database.load_stock(symbol,market,allow_expired=True) if stale_allowed else None
        if stale is not None:return stale
        raise DataProviderError(f"Could not retrieve {symbol}: {exc}") from exc
