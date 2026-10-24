"""Colourful complete watchlist and alert PDF export."""
from __future__ import annotations

import html
import os
from datetime import datetime


def create_watchlist_pdf(entries,alerts,result_map,path):
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:raise RuntimeError("reportlab is required for PDF export.") from exc
    navy=colors.HexColor("#10233F");green=colors.HexColor("#138A5B");red=colors.HexColor("#C2413B");amber=colors.HexColor("#D18B00");light=colors.HexColor("#EEF3F8")
    styles=getSampleStyleSheet();styles.add(ParagraphStyle(name="WT",parent=styles["Title"],fontSize=19,textColor=navy,alignment=0));styles.add(ParagraphStyle(name="WS",parent=styles["Normal"],fontSize=7.5,leading=10,textColor=colors.HexColor("#526072")))
    def footer(canvas,doc):canvas.saveState();canvas.setFont("Helvetica",7);canvas.setFillColor(colors.HexColor("#68778A"));canvas.drawString(14*mm,7*mm,"DR. NILESH SHAH - STOCKS FAIRSCOPE • Watchlist & alerts • Educational use only");canvas.drawRightString(283*mm,7*mm,f"Page {doc.page}");canvas.restoreState()
    doc=SimpleDocTemplate(path,pagesize=landscape(A4),leftMargin=14*mm,rightMargin=14*mm,topMargin=12*mm,bottomMargin=14*mm,title="Watchlist and Alerts",author="DR. NILESH SHAH - STOCKS FAIRSCOPE")
    unread=sum(1 for alert in alerts if not alert.is_read);high=sum(1 for alert in alerts if not alert.is_read and alert.severity=="high");mos=sum(1 for entry in entries if result_map.get(entry.id) and result_map[entry.id].data.price<=result_map[entry.id].margin_price);heading=[Paragraph("Watchlist & Alert Report",styles["WT"]),Paragraph(f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')} • Complete local snapshot",styles["WS"])];story=[];logo=os.path.join(os.path.dirname(__file__),"assets","logo_256.png")
    if os.path.exists(logo):header=Table([[Image(logo,18*mm,18*mm),heading]],colWidths=[23*mm,245*mm]);header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE")]));story.append(header)
    else:story.extend(heading)
    metrics=[["WATCHLIST STOCKS","UNREAD ALERTS","HIGH-RISK ALERTS","BELOW BUFFER"],[str(len(entries)),str(unread),str(high),str(mos)]];mt=Table(metrics,colWidths=[50*mm]*4);mt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("FONT",(0,1),(-1,1),"Helvetica-Bold",12),("TEXTCOLOR",(1,1),(1,1),amber if unread else green),("TEXTCOLOR",(2,1),(2,1),red if high else green),("TEXTCOLOR",(3,1),(3,1),green),("ALIGN",(0,0),(-1,-1),"CENTER"),("BACKGROUND",(0,1),(-1,1),light),("GRID",(0,0),(-1,-1),.3,colors.white),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]));story += [Spacer(1,3*mm),mt,Paragraph("Valuation snapshot",styles["Heading2"])]
    valuation=[["Symbol","Market","Company","Price","Fair value","Buffer price","Upside","Confidence","Fin risk","Gov risk","Data quality","Basis"]]
    for entry in entries:
        result=result_map.get(entry.id)
        if result:valuation.append([result.data.symbol,result.data.market,Paragraph(html.escape(result.data.company),styles["WS"]),f"{result.data.currency} {result.data.price:,.2f}",f"{result.fair_value:,.2f}",f"{result.margin_price:,.2f}",f"{result.upside_pct:+.1f}%",f"{result.confidence_score}/100",str(result.risk_score),str(result.governance_risk_score),str(result.data_quality_score),"Fallback" if result.fallback_valuation else result.methodology_profile])
        else:valuation.append([entry.symbol,entry.market,Paragraph(html.escape(entry.company or "—"),styles["WS"]),"—" if entry.last_price is None else f"{entry.last_price:,.2f}","—" if entry.last_fair_value is None else f"{entry.last_fair_value:,.2f}","—","—","—","—","—","—","Stored only"])
    vt=Table(valuation,colWidths=[24*mm,14*mm,43*mm,25*mm,24*mm,24*mm,20*mm,20*mm,16*mm,16*mm,19*mm,37*mm],repeatRows=1);vt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",6.5),("FONT",(0,1),(-1,-1),"Helvetica",6.7),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#CAD4E0")),("ALIGN",(3,1),(10,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]));story += [vt,Paragraph("Alert settings and last status",styles["Heading2"])]
    settings=[["Symbol","Custom price","Min upside","Max fin risk","Max gov risk","FV change","Buffer alert","Last checked","Last status"]]
    for entry in entries:settings.append([entry.symbol,"Off" if entry.custom_price is None else f"{entry.custom_price:,.2f}",f"{entry.min_upside:.1f}%",f"{entry.max_financial_risk:.0f}",f"{entry.max_governance_risk:.0f}",f"{entry.fair_value_change:.1f}%","Yes" if entry.alert_mos else "No",entry.last_checked[:19] or "—",Paragraph(html.escape(entry.last_status),styles["WS"])])
    st=Table(settings,colWidths=[27*mm,27*mm,27*mm,27*mm,27*mm,25*mm,20*mm,39*mm,50*mm],repeatRows=1);st.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",6.5),("FONT",(0,1),(-1,-1),"Helvetica",6.8),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#CAD4E0")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]));story += [st,Paragraph("Complete alert history",styles["Heading2"])]
    alert_rows=[["Time","Severity","Symbol","Type","Message","Read"]]
    for alert in alerts:alert_rows.append([alert.created_at[:19],alert.severity.upper(),alert.symbol,alert.kind.replace("_"," ").title(),Paragraph(html.escape(alert.message),styles["WS"]),"Yes" if alert.is_read else "No"])
    at=Table(alert_rows,colWidths=[40*mm,22*mm,27*mm,35*mm,125*mm,18*mm],repeatRows=1);style=[("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",6.5),("FONT",(0,1),(-1,-1),"Helvetica",6.8),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#CAD4E0")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]
    for row,alert in enumerate(alerts,1):style.append(("BACKGROUND",(0,row),(-1,row),colors.HexColor("#FADBD8") if alert.severity=="high" else colors.HexColor("#FFF0CC") if alert.severity=="warning" else colors.HexColor("#E4F4EA")))
    at.setStyle(TableStyle(style));story += [at,Spacer(1,3*mm),Paragraph("Alerts are research notifications, not trading instructions. Free source data can be delayed, blocked, restated, or incomplete. Verify official filings and market prices before acting.",styles["WS"])];doc.build(story,onFirstPage=footer,onLaterPages=footer)
