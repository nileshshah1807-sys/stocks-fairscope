"""Long-run annual financials from SEC EDGAR XBRL company facts (official 10-K filings) for US listings."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Optional

import requests

# App statement keys → us-gaap concepts in preference order. Companies switch tags over time (e.g. revenue under ASC 606),
# so later concepts fill only the fiscal years the earlier ones lack.
CONCEPTS={
    "revenue":["Revenues","RevenueFromContractWithCustomerExcludingAssessedTax","SalesRevenueNet","RevenueFromContractWithCustomerIncludingAssessedTax","SalesRevenueGoodsNet"],
    "cost_of_revenue":["CostOfRevenue","CostOfGoodsAndServicesSold","CostOfGoodsSold"],"gross_profit":["GrossProfit"],
    "sga":["SellingGeneralAndAdministrativeExpense"],"research_development":["ResearchAndDevelopmentExpense"],
    "ebit":["OperatingIncomeLoss"],"net_income":["NetIncomeLoss","ProfitLoss"],"interest_expense":["InterestExpense","InterestExpenseDebt"],
    "pretax_income":["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest","IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "income_tax":["IncomeTaxExpenseBenefit"],"diluted_shares":["WeightedAverageNumberOfDilutedSharesOutstanding"],
    "depreciation":["DepreciationDepletionAndAmortization","DepreciationAndAmortization","DepreciationAmortizationAndAccretionNet"],
    "capital_expenditure":["PaymentsToAcquirePropertyPlantAndEquipment","PaymentsToAcquireProductiveAssets"],
    "operating_cash_flow":["NetCashProvidedByUsedInOperatingActivities","NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "working_capital_change":["IncreaseDecreaseInOperatingCapital"],"stock_based_compensation":["ShareBasedCompensation","AllocatedShareBasedCompensationExpense"],
    "repurchase_of_stock":["PaymentsForRepurchaseOfCommonStock"],"issuance_of_stock":["ProceedsFromIssuanceOfCommonStock"],"dividends_paid":["PaymentsOfDividends","PaymentsOfDividendsCommonStock"],
    "total_assets":["Assets"],"current_assets":["AssetsCurrent"],"current_liabilities":["LiabilitiesCurrent"],"total_liabilities":["Liabilities"],
    "long_term_debt":["LongTermDebtNoncurrent","LongTermDebt"],"debt_total":["LongTermDebt"],"debt_current":["LongTermDebtCurrent"],"short_term_borrowings":["ShortTermBorrowings","CommercialPaper"],
    "cash":["CashAndCashEquivalentsAtCarryingValue","CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
    "equity":["StockholdersEquity","StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],"ppe":["PropertyPlantAndEquipmentNet"],
    "receivables":["AccountsReceivableNetCurrent"],"inventory":["InventoryNet"],"payables":["AccountsPayableCurrent"],"retained_earnings":["RetainedEarningsAccumulatedDeficit"],
}
# Filings report these payments as positive amounts; the app (like Yahoo) stores cash outflows as negatives.
OUTFLOWS={"capital_expenditure","repurchase_of_stock","dividends_paid","working_capital_change"}
HELPERS=("pretax_income","income_tax","debt_total","debt_current","short_term_borrowings")

def user_agent(contact_email:str)->str:return f"DR Nilesh Shah Stocks FairScope {contact_email}"

@lru_cache(maxsize=1)
def sec_tickers(agent:str)->dict:
    response=requests.get("https://www.sec.gov/files/company_tickers.json",headers={"User-Agent":agent,"Accept":"application/json"},timeout=20);response.raise_for_status();return response.json()

def cik_for(symbol:str,agent:str)->Optional[str]:
    wanted=symbol.upper().replace(".","-")
    match=next((item for item in sec_tickers(agent).values() if str(item.get("ticker","")).upper().replace(".","-")==wanted),None)
    return str(match["cik_str"]).zfill(10) if match else None

def company_facts(cik:str,agent:str)->dict:
    response=requests.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",headers={"User-Agent":agent,"Accept":"application/json"},timeout=30);response.raise_for_status();return response.json()

def _annual(entries:list[dict])->dict[str,float]:
    """Fiscal-year values by period end from 10-K filings; the latest filing wins, so restated figures replace originals."""
    chosen:dict[str,tuple[str,float]]={}
    for item in entries:
        if item.get("form") not in {"10-K","10-K/A"} or item.get("fp")!="FY" or item.get("val") is None or not item.get("end"):continue
        if item.get("start") and not 350<=(date.fromisoformat(item["end"])-date.fromisoformat(item["start"])).days<=380:continue
        filed=str(item.get("filed",""))
        if item["end"] not in chosen or filed>=chosen[item["end"]][0]:chosen[item["end"]]=(filed,float(item["val"]))
    return {end:value for end,(_filed,value) in chosen.items()}

def annual_statements(facts:dict,years:int=15)->tuple[list[str],dict[str,list[Optional[float]]]]:
    """Up to `years` fiscal year-ends (latest first) and app statement rows aligned to them, with derived FCF, EBITDA, tax rate, and total debt."""
    gaap=(facts.get("facts") or {}).get("us-gaap") or {};by_end={}
    for key,concepts in CONCEPTS.items():
        merged:dict[str,float]={}
        for concept in concepts:
            units=(gaap.get(concept) or {}).get("units") or {}
            for end,value in _annual(units.get("USD") or units.get("shares") or []).items():merged.setdefault(end,value)
        if merged:by_end[key]=merged
    periods=sorted(by_end.get("revenue") or by_end.get("net_income") or {},reverse=True)[:years]
    rows={key:[(-abs(values[end]) if key in OUTFLOWS else values[end]) if end in values else None for end in periods] for key,values in by_end.items()}
    def at(key,index):return (rows.get(key) or [None]*len(periods))[index]
    derived={"free_cash_flow":[],"ebitda":[],"tax_rate":[],"total_debt":[]}
    for index in range(len(periods)):
        ocf,capex,ebit,dep,pretax,tax=at("operating_cash_flow",index),at("capital_expenditure",index),at("ebit",index),at("depreciation",index),at("pretax_income",index),at("income_tax",index)
        derived["free_cash_flow"].append(ocf+capex if ocf is not None and capex is not None else None)
        derived["ebitda"].append(ebit+dep if ebit is not None and dep is not None else None)
        rate=tax/pretax if tax is not None and pretax and pretax>0 else None
        derived["tax_rate"].append(rate if rate is not None and 0<=rate<=.6 else None)
        long_term=at("debt_total",index) if at("debt_total",index) is not None else (at("long_term_debt",index) or 0)+(at("debt_current",index) or 0) if at("long_term_debt",index) is not None else None
        derived["total_debt"].append(long_term+(at("short_term_borrowings",index) or 0) if long_term is not None else None)
    rows.update(derived)
    return periods,{key:values for key,values in rows.items() if key not in HELPERS and any(value is not None for value in values)}

def long_history(periods:list[str],statements:dict)->dict[str,list[Optional[float]]]:
    """The same long-run series Screener.in supplies for Indian stocks (latest first): margins, tax, payout, and pre-tax ROCE."""
    def at(key,index):return (statements.get(key) or [None]*len(periods))[index]
    history={"ebit_margin":[],"net_margin":[],"tax_rate":[],"dividend_payout":[],"roce":[]}
    for index in range(len(periods)):
        sales,ebit,income,equity,debt,dividends=at("revenue",index),at("ebit",index),at("net_income",index),at("equity",index),at("total_debt",index),at("dividends_paid",index)
        history["ebit_margin"].append(ebit/sales if ebit is not None and sales and sales>0 else None)
        history["net_margin"].append(income/sales if income is not None and sales and sales>0 else None)
        history["tax_rate"].append(at("tax_rate",index))
        history["dividend_payout"].append(-dividends/income if dividends is not None and income and income>0 else None)
        capital=(equity or 0)+(debt or 0)
        history["roce"].append(ebit/capital if ebit is not None and equity is not None and capital>0 else None)
    return {key:values for key,values in history.items() if any(value is not None for value in values)}
