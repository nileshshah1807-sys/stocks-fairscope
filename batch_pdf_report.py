"""Branded summary PDF for imported stock lists."""
from __future__ import annotations

import html
import os
from datetime import datetime
from typing import Optional

from batch_import import BatchItem
from valuation import ValuationResult


def create_batch_pdf(records: list[tuple[BatchItem, Optional[ValuationResult], str]], output_path: str) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Image,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("reportlab is not installed. Run: pip install -r requirements.txt") from exc

    navy=colors.HexColor("#10233F"); blue=colors.HexColor("#2563EB"); light=colors.HexColor("#EEF3F8"); green=colors.HexColor("#138A5B"); red=colors.HexColor("#C2413B")
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BatchTitle",parent=styles["Title"],fontName="Helvetica-Bold",fontSize=18,leading=22,textColor=navy,alignment=0,spaceAfter=3))
    styles.add(ParagraphStyle(name="Brand",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=9,textColor=blue,spaceAfter=3))
    styles.add(ParagraphStyle(name="SmallX",parent=styles["Normal"],fontSize=7.5,leading=10,textColor=colors.HexColor("#526072")))

    def footer(canvas, doc):
        canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#D7DEE8")); canvas.line(14*mm,12*mm,283*mm,12*mm)
        canvas.setFont("Helvetica",7); canvas.setFillColor(colors.HexColor("#68778A")); canvas.drawString(14*mm,7*mm,"DR. NILESH SHAH - STOCKS FAIRSCOPE • Batch valuation • Educational use only"); canvas.drawRightString(283*mm,7*mm,f"Page {doc.page}"); canvas.restoreState()

    doc=SimpleDocTemplate(output_path,pagesize=landscape(A4),leftMargin=14*mm,rightMargin=14*mm,topMargin=12*mm,bottomMargin=16*mm,title="Batch Stock Fair Value Report",author="DR. NILESH SHAH - STOCKS FAIRSCOPE")
    logo_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),"assets","logo_256.png")
    heading=[Paragraph("DR. NILESH SHAH - STOCKS FAIRSCOPE",styles["Brand"]),Paragraph("Imported Stock List — Fair Value Summary",styles["BatchTitle"]),Paragraph(f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')} • {len(records)} imported stocks • Free Yahoo/Screener/NSE/BSE data",styles["SmallX"])]
    if os.path.exists(logo_path):
        header=Table([[Image(logo_path,width=18*mm,height=18*mm),heading]],colWidths=[23*mm,245*mm],rowHeights=[20*mm])
        header.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)])); story=[header,Spacer(1,4*mm)]
    else:
        story=heading+[Spacer(1,4*mm)]

    successful=sum(1 for _,r,_ in records if r); failed=len(records)-successful
    summary=Table([["COMPLETED",str(successful),"FAILED",str(failed),"VALUATION DATE",datetime.now().strftime("%d %b %Y")]],colWidths=[29*mm,19*mm,23*mm,19*mm,34*mm,38*mm],hAlign="LEFT")
    summary.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),light),("FONT",(0,0),(-1,-1),"Helvetica",8),("FONT",(0,0),(0,0),"Helvetica-Bold",7),("FONT",(2,0),(2,0),"Helvetica-Bold",7),("FONT",(4,0),(4,0),"Helvetica-Bold",7),("TEXTCOLOR",(1,0),(1,0),green),("TEXTCOLOR",(3,0),(3,0),red),("BOX",(0,0),(-1,-1),.4,colors.HexColor("#CDD7E3")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6)])); story += [summary,Spacer(1,5*mm)]

    rows=[["#","Symbol","Market","Company","CCY","Price","Fair value","Upside","Buffer price","Assessment","R / DQ / BQ / G / C"]]
    for i,(item,r,error) in enumerate(records,1):
        if r:
            d=r.data; rows.append([str(i),d.symbol,d.market,Paragraph(html.escape(d.company),styles["SmallX"]),d.currency,f"{d.price:,.2f}",f"{r.fair_value:,.2f}",f"{r.upside_pct:+.1f}%",f"{r.margin_price:,.2f} ({r.dynamic_margin:.0%})",Paragraph(html.escape(r.label),styles["SmallX"]),f"{r.risk_score}/{r.data_quality_score}/{r.business_quality_score}/{r.governance_risk_score}/{r.confidence_score}"])
        else:
            rows.append([str(i),item.symbol,item.market,"—","—","—","—","—","—","Failed",Paragraph(html.escape(error or "Unknown error"),styles["SmallX"])])
    table=Table(rows,colWidths=[8*mm,25*mm,14*mm,54*mm,12*mm,23*mm,25*mm,18*mm,23*mm,41*mm,31*mm],repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("FONT",(0,1),(-1,-1),"Helvetica",7),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#C9D3DF")),("ALIGN",(0,0),(0,-1),"CENTER"),("ALIGN",(4,1),(8,-1),"RIGHT"),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)])); story.append(table)
    audit_rows=[["Symbol","Analysis ID","Model version","Audit SHA-256","Parent analysis"]]
    for item,result,error in records:
        if result:audit_rows.append([result.data.symbol,result.analysis_id,result.model_version,result.audit_hash,result.parent_analysis_id or "—"])
    if len(audit_rows)>1:
        audit_table=Table(audit_rows,colWidths=[28*mm,52*mm,35*mm,83*mm,55*mm],repeatRows=1)
        audit_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",6.8),("FONT",(0,1),(-1,-1),"Helvetica",6.2),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#C9D3DF")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3)]));story += [Paragraph("Batch audit manifest",styles["BatchTitle"]),audit_table,Paragraph("Each hash is a tamper-evident SHA-256 content hash, not a digital signature.",styles["SmallX"])]
    story += [Spacer(1,5*mm),Paragraph("Scores: R = financial risk, DQ = data quality, BQ = business quality, G = governance risk, C = confidence. Method: Up to five annual observations are normalized; an FCFF DCF at WACC (residual income for financial institutions) is blended with earnings power value and growth-adjusted peer multiples plus the stock's own valuation history using sector-specific weights, and fair value is probability-weighted across scenarios. The required valuation buffer rises with financial risk, incomplete data, cyclicality, and model disagreement. Monte Carlo percentiles are model outputs, not return forecasts. Values use native currency and are estimates, not forecasts.",styles["SmallX"]),Spacer(1,2*mm),Paragraph("Important: For education and research only—not investment advice or a recommendation. No valuation makes investing safe. Free Yahoo/Screener/NSE/BSE data can be delayed, incomplete, rate-limited, or unavailable. Verify all figures against official filings and consult an appropriately registered financial professional.",styles["SmallX"])]
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
