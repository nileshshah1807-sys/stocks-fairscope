"""Quality, forensic-accounting, cash-conversion, capital-allocation, and own-history analytics from free statement data.

All statement series are aligned by fiscal year, latest first, and may contain None where a provider omitted a value.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date, datetime
from statistics import median, pstdev
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from valuation import StockData

MANUFACTURING_SECTORS={"industrials","basic materials","energy","consumer cyclical","consumer defensive"}
BENEISH_THRESHOLD=-1.78

def series(data:"StockData",key:str)->list[Optional[float]]:
    return list((data.statements or {}).get(key) or [])

def value_at(values:list[Optional[float]],index:int)->Optional[float]:
    return values[index] if 0<=index<len(values) and values[index] is not None else None

def cagr(latest_first:list[Optional[float]])->Optional[float]:
    """Annual growth across the first five positive values; the span counts positions, so a blank or loss year is not dropped from the elapsed years."""
    points=[(index,value) for index,value in enumerate(latest_first[:5]) if value is not None and value>0]
    if len(points)<3:return None
    (first,latest),(last,oldest)=points[0],points[-1]
    try:return (latest/oldest)**(1/(last-first))-1
    except OverflowError:return None

def _ratio(numerator:Optional[float],denominator:Optional[float])->Optional[float]:
    if numerator is None or denominator is None or denominator==0:return None
    return numerator/denominator

def normalized_cash_flows(statements:dict,revenue_latest:Optional[float],shares:Optional[float])->tuple[Optional[float],Optional[float],Optional[float]]:
    """Margin-based normalization: latest revenue × median margin, so growing companies are not anchored to stale years.

    Returns (normalized free cash flow after stock-based compensation, normalized net income, EPS).
    """
    revenue=statements.get("revenue") or [];fcf=statements.get("free_cash_flow") or [];ocf=statements.get("operating_cash_flow") or [];capex=statements.get("capital_expenditure") or [];sbc=statements.get("stock_based_compensation") or [];income=statements.get("net_income") or []
    fcf_margins=[];net_margins=[]
    for index,sales in enumerate(revenue):
        if sales is None or sales<=0:continue
        cash=value_at(fcf,index)
        if cash is None and value_at(ocf,index) is not None and value_at(capex,index) is not None:
            spend=value_at(capex,index);cash=value_at(ocf,index)+(spend if spend<=0 else -spend)
        if cash is not None:fcf_margins.append((cash-(value_at(sbc,index) or 0))/sales)
        profit=value_at(income,index)
        if profit is not None:net_margins.append(profit/sales)
    base=revenue_latest if revenue_latest and revenue_latest>0 else None
    normalized_fcf=base*median(fcf_margins) if base and len(fcf_margins)>=2 else None
    normalized_income=base*median(net_margins) if base and len(net_margins)>=2 else None
    eps=normalized_income/shares if normalized_income is not None and shares else None
    return normalized_fcf,normalized_income,eps

def month_key(period:str)->Optional[str]:
    text=str(period or "").strip()
    if len(text)>=7 and text[4]=="-":return text[:7]
    try:return datetime.strptime(text,"%b %Y").strftime("%Y-%m")
    except ValueError:return None

def level_adjusted_long_median(long_values:list[Optional[float]],long_periods:list[str],statement_years:list[str],recent_values:list[Optional[float]])->Optional[float]:
    """Ten-year median of a Screener.in margin series rescaled to the Yahoo definition.

    The providers define profit differently (other income, minority interest), so the long series supplies the cycle
    shape while overlapping fiscal years supply the level. Returns None when fewer than two years overlap.
    """
    values=[x for x in long_values[:10] if x is not None]
    if len(values)<6:return None
    positions={month_key(period):index for index,period in enumerate(long_periods)}
    ratios=[]
    for index,period in enumerate(statement_years):
        recent=value_at(recent_values,index);position=positions.get(month_key(period))
        long=value_at(long_values,position) if position is not None else None
        if recent is not None and long is not None and recent>0 and long>0:ratios.append(recent/long)
    if len(ratios)<2:return None
    return median(values)*min(1.5,max(.5,median(ratios)))

def effective_tax_rate(data:"StockData",default:float)->float:
    if data.effective_tax_rate is not None and 0<=data.effective_tax_rate<=.45:return data.effective_tax_rate
    rates=[rate for rate in series(data,"tax_rate") if rate is not None and 0<=rate<=.45]
    if len(rates)<2:rates+= [rate for rate in (data.long_history or {}).get("tax_rate",[])[:5] if rate is not None and 0<=rate<=.45]
    return median(rates) if rates else default

RESEARCH_LIFE=5

def research_capital(data:"StockData")->list[tuple[float,float,float]]:
    """R&D treated as investment (Damodaran), per fiscal year latest first: (spending, unamortized research asset, amortization).

    shortcut: Yahoo supplies only 4-5 years, so years before the oldest report are assumed equal to it (conservative for growing R&D);
    use 10-year filings when available.
    """
    spending=series(data,"research_development");oldest=next((value for value in reversed(spending) if value is not None),None);result=[]
    def spent(position):return value_at(spending,position) if position<len(spending) else oldest
    for index in range(len(spending)):
        asset=sum(value*(1-lag/RESEARCH_LIFE) for lag in range(RESEARCH_LIFE) if (value:=spent(index+lag)) is not None)
        amortization=sum(value/RESEARCH_LIFE for lag in range(1,RESEARCH_LIFE+1) if (value:=spent(index+lag)) is not None)
        result.append((value_at(spending,index) or 0.0,asset,amortization))
    return result

def roic_history(data:"StockData",tax:float)->list[Optional[float]]:
    ebit=series(data,"ebit");equity=series(data,"equity");debt=series(data,"total_debt");cash=series(data,"cash");research=research_capital(data);values=[]
    for index,operating in enumerate(ebit):
        spent,asset,amortization=research[index] if index<len(research) else (0.0,0.0,0.0)
        capital=(value_at(equity,index) or 0)+(value_at(debt,index) or 0)-(value_at(cash,index) or 0)+asset
        values.append((operating+spent-amortization)*(1-tax)/capital if operating is not None and value_at(equity,index) is not None and capital>0 else None)
    return values

def piotroski_f_score(data:"StockData")->Optional[dict]:
    """Nine binary strength tests; reported only when at least seven can be evaluated."""
    ni=series(data,"net_income");ocf=series(data,"operating_cash_flow");assets=series(data,"total_assets");ltd=series(data,"long_term_debt");ca=series(data,"current_assets");cl=series(data,"current_liabilities");shares=series(data,"diluted_shares");gp=series(data,"gross_profit");revenue=series(data,"revenue")
    def roa(i):return _ratio(value_at(ni,i),value_at(assets,i+1) or value_at(assets,i))
    def leverage(i):return _ratio(value_at(ltd,i) or 0.0,value_at(assets,i)) if value_at(assets,i) else None
    def current(i):return _ratio(value_at(ca,i),value_at(cl,i))
    def margin(i):return _ratio(value_at(gp,i),value_at(revenue,i))
    def turnover(i):return _ratio(value_at(revenue,i),value_at(assets,i+1) or value_at(assets,i))
    def compare(a,b,better):return None if a is None or b is None else (a>b if better else a<b)
    tests={
        "Positive return on assets":None if roa(0) is None else roa(0)>0,
        "Positive operating cash flow":None if value_at(ocf,0) is None else value_at(ocf,0)>0,
        "Improving return on assets":compare(roa(0),roa(1),True),
        "Operating cash flow exceeds net income":compare(value_at(ocf,0),value_at(ni,0),True),
        "Lower long-term leverage":compare(leverage(0),leverage(1),False) if leverage(0)!=leverage(1) else True if leverage(0) is not None else None,
        "Improving current ratio":compare(current(0),current(1),True),
        "No share dilution":None if value_at(shares,0) is None or value_at(shares,1) is None else value_at(shares,0)<=value_at(shares,1)*1.005,
        "Improving gross margin":compare(margin(0),margin(1),True),
        "Improving asset turnover":compare(turnover(0),turnover(1),True),
    }
    tested={name:result for name,result in tests.items() if result is not None}
    if len(tested)<7:return None
    return {"score":sum(1 for result in tested.values() if result),"tested":len(tested),"failed":[name for name,result in tested.items() if not result]}

def altman_z_score(data:"StockData",market_cap:Optional[float])->Optional[dict]:
    """Original Z for manufacturers with a market value; Z'' (non-manufacturing / emerging-market form) otherwise."""
    assets=value_at(series(data,"total_assets"),0);liabilities=value_at(series(data,"total_liabilities"),0);ca=value_at(series(data,"current_assets"),0);cl=value_at(series(data,"current_liabilities"),0)
    retained=value_at(series(data,"retained_earnings"),0);ebit=value_at(series(data,"ebit"),0);sales=value_at(series(data,"revenue"),0);equity=value_at(series(data,"equity"),0)
    if not assets or assets<=0 or not liabilities or liabilities<=0 or ca is None or cl is None or retained is None or ebit is None:return None
    x1=(ca-cl)/assets;x2=retained/assets;x3=ebit/assets
    if data.sector.lower() in MANUFACTURING_SECTORS and market_cap and market_cap>0 and sales is not None:
        score=1.2*x1+1.4*x2+3.3*x3+.6*market_cap/liabilities+1.0*sales/assets;safe,distress,model=2.99,1.81,"Altman Z (manufacturing)"
    elif equity is not None:
        score=6.56*x1+3.26*x2+6.72*x3+1.05*equity/liabilities;safe,distress,model=2.6,1.1,"Altman Z'' (non-manufacturing)"
    else:return None
    return {"score":score,"zone":"Safe" if score>safe else "Distress" if score<distress else "Grey","model":model}

def beneish_m_score(data:"StockData")->Optional[dict]:
    """Eight-variable M-score; values above -1.78 resemble historical earnings manipulators. Needs two fiscal years."""
    def at(key,i):return value_at(series(data,key),i)
    sales0,sales1=at("revenue",0),at("revenue",1)
    if not sales0 or not sales1 or sales0<=0 or sales1<=0:return None
    missing=0
    def index(value):
        nonlocal missing
        if value is None or value<=0:missing+=1;return 1.0
        return value
    def gross(i):
        cost=at("cost_of_revenue",i);profit=at("gross_profit",i);sales=at("revenue",i)
        if profit is None and cost is not None and sales:profit=sales-cost
        return _ratio(profit,sales)
    def quality(i):
        ca,ppe,assets=at("current_assets",i),at("ppe",i),at("total_assets",i)
        return None if ca is None or ppe is None or not assets else 1-(ca+ppe)/assets
    def depreciation_rate(i):
        dep,ppe=at("depreciation",i),at("ppe",i)
        return None if dep is None or ppe is None or dep+ppe<=0 else dep/(dep+ppe)
    def leverage(i):
        cl,ltd,assets=at("current_liabilities",i),at("long_term_debt",i),at("total_assets",i)
        return None if cl is None or not assets else (cl+(ltd or 0))/assets
    receivable0,receivable1=_ratio(at("receivables",0),sales0),_ratio(at("receivables",1),sales1)
    dsri=index(_ratio(receivable0,receivable1));gmi=index(_ratio(gross(1),gross(0)));aqi=index(_ratio(quality(0),quality(1)));sgi=sales0/sales1
    depi=index(_ratio(depreciation_rate(1),depreciation_rate(0)));sgai=index(_ratio(_ratio(at("sga",0),sales0),_ratio(at("sga",1),sales1)));lvgi=index(_ratio(leverage(0),leverage(1)))
    ni,ocf,assets=at("net_income",0),at("operating_cash_flow",0),at("total_assets",0)
    if ni is None or ocf is None or not assets:missing+=1;tata=0.0
    else:tata=(ni-ocf)/assets
    if missing>3:return None
    score=-4.84+.92*dsri+.528*gmi+.404*aqi+.892*sgi+.115*depi-.172*sgai+4.679*tata-.327*lvgi
    return {"score":score,"flag":score>BENEISH_THRESHOLD,"missing_inputs":missing}

def margin_stability(data:"StockData")->Optional[dict]:
    revenue=series(data,"revenue");ebit=series(data,"ebit")
    margins=[value_at(ebit,i)/sales for i,sales in enumerate(revenue) if sales and sales>0 and value_at(ebit,i) is not None]
    long=[x for x in (data.long_history or {}).get("ebit_margin",[])[:10] if x is not None]
    values=long if len(long)>len(margins) else margins
    if len(values)<3:return None
    mean=sum(values)/len(values)
    return {"median_margin":median(values),"variation":pstdev(values)/abs(mean) if mean else None,"years":len(values)}

def cash_conversion_cycle(data:"StockData")->Optional[dict]:
    long=[x for x in (data.long_history or {}).get("cash_conversion_cycle",[]) if x is not None]
    if len(long)>=2:return {"latest":long[0],"change":long[0]-long[min(len(long),5)-1],"years":min(len(long),5),"source":"Screener.in"}
    revenue=series(data,"revenue");cost=series(data,"cost_of_revenue");receivables=series(data,"receivables");inventory=series(data,"inventory");payables=series(data,"payables");values=[]
    for i,sales in enumerate(revenue):
        cogs=value_at(cost,i)
        if not sales or sales<=0 or value_at(receivables,i) is None:values.append(None);continue
        days=value_at(receivables,i)/sales*365
        if cogs and cogs>0:days+=((value_at(inventory,i) or 0)-(value_at(payables,i) or 0))/cogs*365
        values.append(days)
    usable=[x for x in values if x is not None]
    if len(usable)<2:return None
    return {"latest":usable[0],"change":usable[0]-usable[-1],"years":len(usable),"source":"Yahoo Finance statements"}

def owner_earnings(data:"StockData")->Optional[float]:
    """Operating cash flow less maintenance capital spending, approximated by the lower of capex and depreciation."""
    ocf=value_at(series(data,"operating_cash_flow"),0);capex=value_at(series(data,"capital_expenditure"),0);dep=value_at(series(data,"depreciation"),0)
    if ocf is None or capex is None:return None
    maintenance=min(abs(capex),dep) if dep is not None and dep>0 else abs(capex)
    return ocf-maintenance-(value_at(series(data,"stock_based_compensation"),0) or 0)

def capital_allocation(data:"StockData",market_cap:Optional[float])->dict:
    repurchase=value_at(series(data,"repurchase_of_stock"),0);issuance=value_at(series(data,"issuance_of_stock"),0);dividends=value_at(series(data,"dividends_paid"),0);income=value_at(series(data,"net_income"),0);result={}
    if market_cap and market_cap>0 and (repurchase is not None or issuance is not None):result["net_repurchase_yield"]=(-(repurchase or 0)-(issuance or 0))/market_cap
    if dividends is not None and income and income>0:result["dividend_payout"]=abs(dividends)/income
    elif data.dividend_payout is not None:result["dividend_payout"]=data.dividend_payout
    return result

def institutional_trend(data:"StockData")->Optional[float]:
    long=data.long_history or {};fii=[x for x in long.get("fii",[])[:12] if x is not None];dii=[x for x in long.get("dii",[])[:12] if x is not None]
    count=min(len(fii),len(dii))
    return (fii[0]+dii[0])-(fii[count-1]+dii[count-1]) if count>=3 else None

def historical_multiples(data:"StockData")->dict:
    """The stock's own median P/E, EV/EBITDA, and P/B at past fiscal year-ends (split-adjusted closes)."""
    dates=data.long_price_dates or [];prices=data.long_prices or []
    if len(dates)<12 or len(dates)!=len(prices) or not data.statement_years:return {}
    shares_series=series(data,"diluted_shares");income=series(data,"net_income");ebitda=series(data,"ebitda");ebit=series(data,"ebit");dep=series(data,"depreciation");debt=series(data,"total_debt");cash=series(data,"cash");equity=series(data,"equity")
    pe=[];ev=[];pb=[];p_ffo=[]
    for i,period in enumerate(data.statement_years):
        try:target=date.fromisoformat(period[:10])
        except ValueError:continue
        position=bisect_right(dates,target.isoformat())-1
        if position<0 or (target-date.fromisoformat(dates[position][:10])).days>40:continue
        price=prices[position];shares=value_at(shares_series,i)
        if not shares or not data.shares or not .5<=shares/data.shares<=2:shares=data.shares
        if not shares or not price:continue
        cap=price*shares;profit=value_at(income,i);operating=value_at(ebitda,i)
        if operating is None and value_at(ebit,i) is not None and value_at(dep,i) is not None:operating=value_at(ebit,i)+value_at(dep,i)
        if profit and profit>0 and 3<=cap/profit<=150:pe.append(cap/profit)
        funds=profit+value_at(dep,i) if profit is not None and value_at(dep,i) is not None else None
        if funds and funds>0 and 3<=cap/funds<=60:p_ffo.append(cap/funds)
        if operating and operating>0:
            multiple=(cap+(value_at(debt,i) or 0)-(value_at(cash,i) or 0))/operating
            if 1<=multiple<=80:ev.append(multiple)
        book=value_at(equity,i)
        if book and book>0 and .1<=cap/book<=30:pb.append(cap/book)
    result={}
    if len(pe)>=2:result["pe"]=median(pe)
    if len(ev)>=2:result["ev_ebitda"]=median(ev)
    if len(pb)>=2:result["pb"]=median(pb)
    if len(p_ffo)>=2:result["p_ffo"]=median(p_ffo)
    if result:result["observations"]=max(len(pe),len(ev),len(pb))
    return result
