"""Point-in-time backtest: re-run the valuation at past fiscal year-ends and compare it with the returns that followed.

Statements, prices, and long-run Screener.in history are truncated to what was public about 90 days after each fiscal
year-end. Peer multiples, beta, and the risk-free rate are today's values (free sources keep no history), so results carry
some look-ahead bias and cover only the 4-5 years of annual statements Yahoo provides.
"""
from __future__ import annotations

from bisect import bisect_right
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from statistics import median
from typing import Optional

from fundamentals import cagr, month_key, normalized_cash_flows, value_at
from valuation import StockData, value_stock

REPORTING_LAG_DAYS=90
LOOK_AHEAD_NOTE="Peer multiples, beta, and the risk-free rate use current values because free sources keep no history; results are indicative, not a rigorous out-of-sample test."

@dataclass
class BacktestPoint:
    symbol:str
    market:str
    fiscal_year_end:str
    as_of:str
    price_then:float
    fair_value_then:float
    upside_then:float  # percent
    below_buffer:bool
    forward_return:float  # total return to the latest price, percent
    annualized_return:float  # percent per year
    months_held:int
    label:str

def _clean(values):return [value for value in values if value is not None]

def as_of_snapshot(data:StockData,years_back:int)->Optional[tuple[StockData,float,float,str,str,int]]:
    """Rebuild the snapshot as it looked about 90 days after an earlier fiscal year-end.

    Returns (snapshot, total-return price then, total-return price now, as-of date, fiscal year-end, months held).
    """
    k=years_back
    # SEC EDGAR supplies 10-15 fiscal years for US listings against Yahoo's 4-5, so backtests reach further back when it is present.
    years,source=(data.long_statement_years,data.long_statements) if len(data.long_statement_years)>len(data.statement_years) else (data.statement_years,data.statements)
    if k<1 or len(years)<=k or len(data.long_price_dates)<13 or len(data.long_adjusted_prices)!=len(data.long_price_dates):return None
    fiscal_end=years[k]
    try:as_of=(date.fromisoformat(fiscal_end[:10])+timedelta(days=REPORTING_LAG_DAYS)).isoformat()
    except ValueError:return None
    position=bisect_right(data.long_price_dates,as_of)-1
    if position<0 or position>=len(data.long_price_dates)-3:return None
    # Five years per snapshot, matching what the live valuation normalizes over.
    statements={key:values[k:k+5] for key,values in (source or {}).items()}
    revenue=_clean(statements.get("revenue",[]))
    if not revenue:return None
    shares=value_at(statements.get("diluted_shares",[]),0)
    if not shares or not data.shares or not .5<=shares/data.shares<=2:shares=data.shares
    def latest(key):return value_at(statements.get(key,[]),0)
    fcf,income,eps=normalized_cash_flows(statements,revenue[0],shares);net=_clean(statements.get("net_income",[]))
    if income is None and net and shares:eps=median(net)/shares
    equity=latest("equity");ebit=latest("ebit");ebitda=latest("ebitda")
    if ebitda is None and ebit is not None and latest("depreciation") is not None:ebitda=ebit+latest("depreciation")
    growth=[g for g in (cagr(statements.get("revenue",[])),cagr(statements.get("net_income",[]))) if g is not None and -.5<g<1]
    # Screener.in annual series are latest first; drop periods published after the as-of fiscal year.
    later=sum(1 for period in data.long_history_periods if (month_key(period) or "")>fiscal_end[:7])
    long={key:values[later:] for key,values in (data.long_history or {}).items() if key not in {"promoter","fii","dii"}}
    for key in ("promoter","fii","dii"):
        if key in (data.long_history or {}):long[key]=data.long_history[key][4*later+1:]
    price=data.long_prices[position]
    snapshot=replace(data,price=price,shares=shares,market_cap=price*shares if shares else None,statements=statements,statement_years=years[k:k+5],long_statement_years=[],long_statements={},
        revenue_history=revenue,net_income_history=net,fcf_history=_clean(statements.get("free_cash_flow",[])),free_cash_flow=fcf,eps=eps,
        book_value_per_share=equity/shares if equity and shares else None,growth_estimate=median(growth) if growth else None,
        total_debt=latest("total_debt"),cash=latest("cash"),ebitda=ebitda,ebit=ebit,interest_expense=latest("interest_expense"),current_assets=latest("current_assets"),
        current_liabilities=latest("current_liabilities"),stockholder_equity=equity,operating_cash_flow=latest("operating_cash_flow"),net_income=net[0] if net else None,
        return_on_equity=net[0]/equity if net and equity and equity>0 else None,diluted_shares_history=_clean(statements.get("diluted_shares",[])),
        receivables_history=_clean(statements.get("receivables",[])),inventory_history=_clean(statements.get("inventory",[])),
        long_history=long,long_history_periods=data.long_history_periods[later:],long_price_dates=data.long_price_dates[:position+1],long_prices=data.long_prices[:position+1],
        long_adjusted_prices=data.long_adjusted_prices[:position+1],price_history=[],price_dates=[],lineage=[],warnings=[],trailing_pe=None,price_to_book=None,
        analyst_growth=None,analyst_long_term_growth=None,forward_eps=None,forward_pe=None,enterprise_to_ebitda=None,order_book=None,promoter_pledge=None,
        promoter_holding_history=(data.promoter_holding_history or [])[4*later+1:] if data.promoter_holding_history else [],external_reviews=[],source_discrepancies=[],
        is_stale=False,cache_status="point-in-time backtest",cache_age_hours=0.0,data_timestamp=as_of,source_updated_date=as_of)
    return snapshot,data.long_adjusted_prices[position],data.long_adjusted_prices[-1],as_of,fiscal_end,len(data.long_price_dates)-1-position

def backtest_stock(data:StockData,max_years_back:int=3)->tuple[list[BacktestPoint],list[str]]:
    points=[];errors=[]
    for years_back in range(1,max_years_back+1):
        built=as_of_snapshot(data,years_back)
        if built is None:continue
        snapshot,then,now,as_of,fiscal_end,months=built
        try:result=value_stock(snapshot,monte_carlo_iterations=0)
        except ValueError as exc:errors.append(f"{data.symbol} {fiscal_end}: {exc}");continue
        total=(now/then-1) if then>0 else 0.0;annual=((1+total)**(12/months)-1) if months>0 and total>-1 else total
        points.append(BacktestPoint(data.symbol,data.market,fiscal_end,as_of,snapshot.price,result.fair_value,result.upside_pct,snapshot.price<=result.margin_price,total*100,annual*100,months,result.label))
    if not points and not errors:errors.append(f"{data.symbol}: fewer than two fiscal years or 13 months of history were available before the test dates.")
    return points,errors

def _ranks(values:list[float])->list[float]:
    order=sorted(range(len(values)),key=lambda index:values[index]);ranks=[0.0]*len(values);position=0
    while position<len(order):
        end=position
        while end+1<len(order) and values[order[end+1]]==values[order[position]]:end+=1
        for index in order[position:end+1]:ranks[index]=(position+end)/2+1
        position=end+1
    return ranks

def spearman(first:list[float],second:list[float])->Optional[float]:
    if len(first)<3 or len(first)!=len(second):return None
    a,b=_ranks(first),_ranks(second);mean_a,mean_b=sum(a)/len(a),sum(b)/len(b)
    numerator=sum((x-mean_a)*(y-mean_b) for x,y in zip(a,b));denominator=(sum((x-mean_a)**2 for x in a)*sum((y-mean_b)**2 for y in b))**.5
    return numerator/denominator if denominator else None

def summarize(points:list[BacktestPoint])->dict:
    """Rank correlation, directional hit rate, and annualized returns of stocks the model saw as under- or overvalued."""
    if not points:return {"observations":0,"note":LOOK_AHEAD_NOTE}
    def average(values):return sum(values)/len(values) if values else None
    upside=[point.upside_then for point in points];returns=[point.annualized_return for point in points]
    return {"observations":len(points),"stocks":len({point.symbol for point in points}),"rank_correlation":spearman(upside,returns),
        "hit_rate":sum(1 for point in points if (point.upside_then>0)==(point.annualized_return>0))/len(points),
        "avg_return_undervalued":average([point.annualized_return for point in points if point.upside_then>0]),
        "avg_return_overvalued":average([point.annualized_return for point in points if point.upside_then<=0]),
        "avg_return_below_buffer":average([point.annualized_return for point in points if point.below_buffer]),
        "avg_return_all":average(returns),"note":LOOK_AHEAD_NOTE}

def point_record(point:BacktestPoint)->dict:return asdict(point)

FORWARD_NOTE="Forward tracking scores valuations this app actually saved against today's price, so nothing is re-estimated and there is no look-ahead bias. Price return only (dividends excluded); holdings under a year are not annualized."
MIN_TRACK_DAYS=30

def forward_points(rows:list[dict],closes:dict[str,float],today:date)->list[BacktestPoint]:
    """One point per stock per saved day (the latest that day) at least MIN_TRACK_DAYS old, scored against today's close."""
    points=[];seen=set()
    for row in rows:
        symbol,day=str(row.get("symbol") or ""),str(row.get("created_at") or "")[:10];price_then,fair=row.get("market_price"),row.get("fair_value")
        if (symbol,day) in seen or symbol not in closes or not price_then or price_then<=0 or not fair:continue
        try:held=(today-date.fromisoformat(day)).days
        except ValueError:continue
        if held<MIN_TRACK_DAYS:continue
        seen.add((symbol,day));total=closes[symbol]/price_then-1
        annual=(1+total)**(365.25/held)-1 if held>=365 and total>-1 else total
        margin=row.get("margin_price")
        points.append(BacktestPoint(symbol,str(row.get("market") or ""),"Saved valuation",day,price_then,fair,float(row.get("upside_pct") or 0),bool(margin) and price_then<=margin,total*100,annual*100,round(held/30.44),"Forward tracking"))
    return points

def track_saved_valuations(database,today:Optional[date]=None)->tuple[list[BacktestPoint],list[str]]:
    """Score the app's saved valuation history against today's prices."""
    from data_provider import latest_closes
    today=today or date.today();rows=database.tracking_rows()
    symbols=sorted({str(row["symbol"]) for row in rows if str(row.get("created_at") or "")[:10] and (today-date.fromisoformat(str(row["created_at"])[:10])).days>=MIN_TRACK_DAYS})
    if not symbols:return [],[f"No saved valuation is {MIN_TRACK_DAYS} days old yet; forward tracking fills in as time passes."]
    closes=latest_closes(symbols)
    return forward_points(rows,closes,today),[f"{symbol}: today's price was unavailable" for symbol in symbols if symbol not in closes]
