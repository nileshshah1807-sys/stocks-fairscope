"""Full stock valuation PDF export."""
from __future__ import annotations

import html
import os
from datetime import datetime

from valuation import ValuationResult, verify_audit_hash


def _money(value, currency: str) -> str:
    return "—" if value is None else f"{currency} {value:,.2f}"


def create_pdf(result: ValuationResult, output_path: str) -> None:
    try:
        from reportlab.graphics.shapes import Drawing, Line, PolyLine, Rect, String
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Image,
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.platypus.tableofcontents import TableOfContents
    except ImportError as exc:
        raise RuntimeError("reportlab is not installed. Run: pip install -r requirements.txt") from exc

    d, a, ccy = result.data, result.base_assumptions, result.data.currency
    navy, blue, green, red, light = colors.HexColor("#10233F"), colors.HexColor("#2563EB"), colors.HexColor("#138A5B"), colors.HexColor("#C2413B"), colors.HexColor("#EEF3F8")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleX", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=navy, alignment=0, spaceAfter=4))
    styles.add(ParagraphStyle(name="BrandX", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=blue, alignment=0, spaceAfter=3))
    styles.add(ParagraphStyle(name="Sub", parent=styles["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#526072"), alignment=0, spaceAfter=0))
    styles.add(ParagraphStyle(name="H2X", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=14, textColor=navy, spaceBefore=10, spaceAfter=7))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8.5, leading=12, textColor=colors.HexColor("#526072")))
    styles.add(ParagraphStyle(name="BodyX", parent=styles["BodyText"], fontSize=9.5, leading=14))
    styles.add(ParagraphStyle(name="CoverBrand", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=blue, alignment=1, spaceAfter=6))
    styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=27, leading=32, textColor=navy, alignment=1, spaceAfter=8))
    styles.add(ParagraphStyle(name="CoverCompany", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=16, leading=21, textColor=navy, alignment=1, spaceAfter=5))
    styles.add(ParagraphStyle(name="CoverSub", parent=styles["Normal"], fontSize=9, leading=13, textColor=colors.HexColor("#526072"), alignment=1, spaceAfter=7))
    styles.add(ParagraphStyle(name="TOCHeading", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=21, textColor=navy, spaceAfter=12))

    class BrandedDocTemplate(SimpleDocTemplate):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs);self._section_counter=0
        def beforeDocument(self):
            self._section_counter=0
        def afterFlowable(self,flowable):
            if isinstance(flowable,Paragraph) and flowable.style.name=="H2X":
                self._section_counter+=1;text=flowable.getPlainText();key=f"section-{self._section_counter}";self.canv.bookmarkPage(key);self.canv.addOutlineEntry(text,key,level=0,closed=False);self.notify("TOCEntry",(0,text,self.page,key))

    def header_footer(canvas, doc):
        canvas.saveState()
        if doc.page==1:
            canvas.setFont("Helvetica",7);canvas.setFillColor(colors.HexColor("#7A8797"));canvas.drawCentredString(105*mm,9*mm,"Confidential research copy • Educational use only • Not investment advice")
        else:
            canvas.setStrokeColor(colors.HexColor("#D7DEE8"));canvas.line(18*mm,285*mm,192*mm,285*mm);canvas.line(18*mm,16*mm,192*mm,16*mm)
            canvas.setFont("Helvetica-Bold",7.5);canvas.setFillColor(navy);canvas.drawString(18*mm,289*mm,"DR. NILESH SHAH - STOCKS FAIRSCOPE")
            canvas.setFont("Helvetica",7.5);canvas.setFillColor(colors.HexColor("#68778A"));canvas.drawRightString(192*mm,289*mm,f"{d.symbol} • {result.analysis_id[-12:] if result.analysis_id else 'analysis'}");canvas.drawString(18*mm,10*mm,f"{result.model_version} • Audit {result.audit_schema_version} • Educational valuation");canvas.drawRightString(192*mm,10*mm,f"Page {doc.page}")
        canvas.restoreState()

    def price_visual():
        values=list(d.price_history or [])
        if len(values)<2:return None
        width,height=485,145;left,bottom,right,top=42,20,405,132;refs=[result.fair_value,result.margin_price];low=min(values+refs);high=max(values+refs);span=(high-low) or 1;low-=span*.08;high+=span*.08
        drawing=Drawing(width,height)
        for index in range(4):
            y=bottom+(top-bottom)*index/3;drawing.add(Line(left,y,right,y,strokeColor=colors.HexColor("#DCE4ED"),strokeWidth=.5));level=low+(high-low)*index/3;drawing.add(String(2,y-3,f"{level:,.0f}",fontSize=6.5,fillColor=colors.HexColor("#68778A")))
        points=[(left+i*(right-left)/(len(values)-1),bottom+(value-low)/(high-low)*(top-bottom)) for i,value in enumerate(values)];drawing.add(PolyLine(points,strokeColor=blue,strokeWidth=1.7))
        for level,color,label in ((result.fair_value,green,"Fair value"),(result.margin_price,colors.HexColor("#C58B13"),f"Buffer {result.dynamic_margin:.0%}")):
            y=bottom+(level-low)/(high-low)*(top-bottom);drawing.add(Line(left,y,right,y,strokeColor=color,strokeWidth=1.2,strokeDashArray=[4,3]));drawing.add(String(right+7,y-3,label,fontSize=7,fillColor=color))
        drawing.add(String(left,4,"1 year ago",fontSize=6.5,fillColor=colors.HexColor("#68778A")));drawing.add(String(right-18,4,"Latest",fontSize=6.5,fillColor=colors.HexColor("#68778A")))
        return drawing

    def model_visual():
        base=result.scenarios["Base"];rows=[(result.model_labels.get("dcf","Primary"),base.dcf,colors.HexColor("#6B8ED6")),(result.model_labels.get("graham","Graham"),base.graham,colors.HexColor("#8AA5C8")),(result.model_labels.get("relative","Peers"),base.relative,colors.HexColor("#6AB5A1")),("Blended fair value",result.fair_value,blue),("Market price",d.price,red)];usable=[value for _,value,_ in rows if value is not None and value>0]
        if not usable:return None
        width,height=485,125;left,right=112,390;maximum=max(usable)*1.08;drawing=Drawing(width,height)
        for index,(label,value,color) in enumerate(rows):
            y=height-21-index*23;drawing.add(String(2,y+3,label[:24],fontSize=7,fillColor=navy));drawing.add(Rect(left,y,right-left,11,fillColor=colors.HexColor("#EDF2F7"),strokeColor=None,rx=3,ry=3))
            if value is not None and value>0:
                drawing.add(Rect(left,y,(right-left)*value/maximum,11,fillColor=color,strokeColor=None,rx=3,ry=3));drawing.add(String(right+7,y+2,_money(value,ccy),fontSize=7,fillColor=navy))
            else:drawing.add(String(right+7,y+2,"Unavailable",fontSize=7,fillColor=colors.HexColor("#68778A")))
        return drawing

    def score_visual():
        rows=[("Balance-sheet resilience",100-result.risk_score),("Data quality",result.data_quality_score),("Business quality",result.business_quality_score),("Governance resilience",100-result.governance_risk_score),("Order book",result.order_book_score if result.data.order_book is not None else None),("Confidence",result.confidence_score)];drawing=Drawing(485,132);left,right=110,420
        for index,(label,value) in enumerate(rows):
            y=112-index*20;color=green if value is not None and value>=70 else colors.HexColor("#D18B00") if value is not None and value>=45 else red;drawing.add(String(2,y+2,label,fontSize=7.5,fillColor=navy));drawing.add(Rect(left,y,right-left,10,fillColor=colors.HexColor("#EDF2F7"),strokeColor=None,rx=3,ry=3));
            if value is not None:drawing.add(Rect(left,y,(right-left)*max(0,min(100,value))/100,10,fillColor=color,strokeColor=None,rx=3,ry=3));drawing.add(String(right+7,y+1,f"{value:.0f}/100",fontSize=7.5,fillColor=color))
            else:drawing.add(String(right+7,y+1,"Unavailable",fontSize=7.5,fillColor=colors.HexColor("#68778A")))
        return drawing

    def monte_carlo_visual():
        counts=result.monte_carlo_bin_counts;edges=result.monte_carlo_bin_edges
        if not counts or not edges:return None
        width,height=485,125;left,bottom,right,top=42,18,460,112;maximum=max(counts) or 1;bar_width=(right-left)/len(counts);drawing=Drawing(width,height)
        drawing.add(Line(left,bottom,right,bottom,strokeColor=colors.HexColor("#B8C5D4"),strokeWidth=.7))
        for index,count in enumerate(counts):drawing.add(Rect(left+index*bar_width+1,bottom,max(1,bar_width-2),(top-bottom)*count/maximum,fillColor=blue,strokeColor=None))
        if edges[-1]>edges[0] and edges[0]<=d.price<=edges[-1]:
            x=left+(d.price-edges[0])/(edges[-1]-edges[0])*(right-left);drawing.add(Line(x,bottom,x,top,strokeColor=red,strokeWidth=1.2,strokeDashArray=[4,3]));drawing.add(String(x-19,top+3,"Market",fontSize=6.5,fillColor=red))
        drawing.add(String(left,3,_money(edges[0],ccy),fontSize=6.5,fillColor=colors.HexColor("#68778A")));drawing.add(String(right-42,3,_money(edges[-1],ccy),fontSize=6.5,fillColor=colors.HexColor("#68778A")))
        return drawing

    doc = BrandedDocTemplate(output_path, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm, topMargin=18*mm, bottomMargin=20*mm,
                            title=f"{d.symbol} Fair Value Report", author="DR. NILESH SHAH - STOCKS FAIRSCOPE", subject=f"Fair value analysis for {d.company}", keywords="fair value, valuation, DCF, risk, audit, data lineage")
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "logo_256.png")
    story=[Spacer(1,12*mm)]
    if os.path.exists(logo_path):
        cover_logo=Image(logo_path,width=36*mm,height=36*mm);cover_logo.hAlign="CENTER";story += [cover_logo,Spacer(1,5*mm)]
    story += [Paragraph("DR. NILESH SHAH - STOCKS FAIRSCOPE",styles["CoverBrand"]),Paragraph("Independent Fair Value & Risk Report",styles["CoverTitle"]),Paragraph(html.escape(d.company),styles["CoverCompany"]),Paragraph(f"{html.escape(d.symbol)} • {d.market} • {d.currency} • {html.escape(d.sector)}",styles["CoverSub"]),HRFlowable(width="72%",thickness=1,color=colors.HexColor("#CDD7E3"),spaceBefore=4*mm,spaceAfter=7*mm,hAlign="CENTER")]
    cover_metrics=[["MARKET PRICE","FAIR VALUE","UPSIDE / DOWNSIDE","BUFFER PRICE"],[_money(d.price,ccy),_money(result.fair_value,ccy),f"{result.upside_pct:+.1f}%",_money(result.margin_price,ccy)]];cover_table=Table(cover_metrics,colWidths=[41*mm]*4,rowHeights=[9*mm,15*mm]);cover_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("FONT",(0,1),(-1,1),"Helvetica-Bold",12),("ALIGN",(0,0),(-1,-1),"CENTER"),("BACKGROUND",(0,1),(-1,1),light),("TEXTCOLOR",(1,1),(1,1),blue),("TEXTCOLOR",(2,1),(2,1),green if result.upside_pct>=0 else red),("GRID",(0,0),(-1,-1),.4,colors.white),("VALIGN",(0,0),(-1,-1),"MIDDLE")]));story += [cover_table,Spacer(1,7*mm)]
    cover_status_color=colors.HexColor("#E4F5EE") if result.upside_pct>=0 else colors.HexColor("#FBE9E7");status_table=Table([[Paragraph(f"<b>{html.escape(result.label)}</b><br/><font size='8'>Confidence {result.confidence_score}/100 • Required valuation buffer {result.dynamic_margin:.0%} • {html.escape(result.methodology_profile)}</font>",styles["BodyX"]) ]],colWidths=[164*mm]);status_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),cover_status_color),("BOX",(0,0),(-1,-1),.6,green if result.upside_pct>=0 else red),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8)]));story += [status_table,Spacer(1,7*mm)]
    cover_meta=[["Analysis ID",result.analysis_id],["Model",f"{result.model_version} • Audit schema {result.audit_schema_version}"],["Data",f"{d.data_provider} • {d.cache_status}"],["Generated",datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")]];meta_table=Table(cover_meta,colWidths=[35*mm,129*mm]);meta_table.setStyle(TableStyle([("FONT",(0,0),(0,-1),"Helvetica-Bold",8),("FONT",(1,0),(1,-1),"Helvetica",8),("TEXTCOLOR",(0,0),(-1,-1),colors.HexColor("#526072")),("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.white,colors.HexColor("#F7F9FC")]),("LINEBELOW",(0,0),(-1,-2),.25,colors.HexColor("#E0E6EE")),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]));story += [meta_table,Spacer(1,8*mm),Paragraph("Automated research estimate • Not a Buy/Sell recommendation • Valuation buffer does not guarantee protection from loss",styles["CoverSub"]),PageBreak(),Paragraph("Contents",styles["TOCHeading"])]
    toc=TableOfContents();toc.levelStyles=[ParagraphStyle(name="TOCLevel1",fontName="Helvetica",fontSize=10,leading=16,leftIndent=8,firstLineIndent=-8,textColor=navy,spaceBefore=2)];story += [toc,PageBreak()]
    if os.path.exists(logo_path):
        logo=Image(logo_path,width=22*mm,height=22*mm);heading=[Paragraph("DR. NILESH SHAH - STOCKS FAIRSCOPE",styles["BrandX"]),Paragraph("Fair Value Analysis",styles["TitleX"]),Paragraph(f"{html.escape(d.company)} ({html.escape(d.symbol)}) • {d.market} • Generated {datetime.now().strftime('%d %b %Y, %H:%M')}",styles["Sub"])];brand_table=Table([[logo,heading]],colWidths=[27*mm,145*mm],rowHeights=[25*mm]);brand_table.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]));story += [brand_table,Spacer(1,4*mm)]
    else:story += [Paragraph("DR. NILESH SHAH - STOCKS FAIRSCOPE",styles["BrandX"]),Paragraph("Fair Value Analysis",styles["TitleX"]),Paragraph(f"{html.escape(d.company)} ({html.escape(d.symbol)}) • {d.market}",styles["Sub"]),Spacer(1,4*mm)]

    story += [Paragraph("Executive summary",styles["H2X"])]
    metric_data = [
        ["MARKET PRICE", "FAIR VALUE (WEIGHTED)", "UPSIDE / DOWNSIDE", f"{result.dynamic_margin:.0%} BUFFER PRICE"],
        [_money(d.price, ccy), _money(result.fair_value, ccy), f"{result.upside_pct:+.1f}%", _money(result.margin_price, ccy)],
    ]
    metric_table = Table(metric_data, colWidths=[43*mm]*4, rowHeights=[8*mm, 13*mm])
    metric_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), navy), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold", 7.5), ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONT", (0,1), (-1,1), "Helvetica-Bold", 12), ("TEXTCOLOR", (1,1), (1,1), blue),
        ("TEXTCOLOR", (2,1), (2,1), green if result.upside_pct >= 0 else red),
        ("BACKGROUND", (0,1), (-1,1), light), ("GRID", (0,0), (-1,-1), 0.5, colors.white),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))
    story += [metric_table, Spacer(1, 7*mm), Paragraph(f"Assessment: <b>{html.escape(result.label)}</b> &nbsp;&nbsp;|&nbsp;&nbsp; Model coverage: <b>{result.confidence}</b>", styles["BodyX"])]
    if result.base_fair_value is not None and result.scenario_weights:story += [Spacer(1,2*mm),Paragraph(f"Fair value is probability-weighted across scenarios ({' / '.join(f'{weight:.0%}' for weight in result.scenario_weights)} conservative / base / optimistic). Base-case value: {_money(result.base_fair_value,ccy)}.",styles["Small"])]
    if result.implied_return_note:story += [Spacer(1,1*mm),Paragraph("<b>Implied return:</b> "+html.escape(result.implied_return_note),styles["Small"])]
    if result.fallback_valuation:story += [Spacer(1,2*mm),Paragraph("<b>LOW-CONFIDENCE FALLBACK:</b> "+html.escape(" ".join(result.fallback_reasons))+" The result uses a minimum 35% valuation buffer and must not be treated as equivalent to a positive-earnings/FCF valuation.",styles["Small"])]
    price_drawing=price_visual()
    if price_drawing:story += [Paragraph("Price vs valuation",styles["H2X"]),price_drawing,Paragraph("The historical line is market price; fair value and the valuation-buffer line are today's model references, not historical estimates.",styles["Small"])]
    model_drawing=model_visual()
    if model_drawing:story += [Paragraph("Base model comparison",styles["H2X"]),model_drawing]

    story += [Paragraph("Scenario valuation", styles["H2X"])]
    rows = [["Scenario", "Growth", "Discount", "Terminal", result.model_labels.get("dcf","Primary"), result.model_labels.get("graham","Graham"), result.model_labels.get("relative","Live peers"), "Blended"]]
    scenario_weight=dict(zip(("Conservative","Base","Optimistic"),result.scenario_weights or [.25,.5,.25]))
    for s in result.scenarios.values():
        rows.append([f"{s.name} ({scenario_weight.get(s.name,0):.0%})", f"{s.growth:.1%}", f"{s.discount_rate:.1%}", f"{s.terminal_growth:.1%}", _money(s.dcf, ccy), _money(s.graham, ccy), _money(s.relative, ccy), _money(s.fair_value, ccy)])
    table = Table(rows, colWidths=[23*mm, 16*mm, 17*mm, 17*mm, 24*mm, 24*mm, 27*mm, 24*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), navy), ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold", 7), ("FONT", (0,1), (-1,-1), "Helvetica", 7.3),
        ("ALIGN", (1,0), (-1,-1), "RIGHT"), ("ALIGN", (0,0), (0,-1), "LEFT"),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, light]), ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#C9D3DF")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(table)

    story += [Paragraph("Company & market snapshot", styles["H2X"])]
    snapshot = [
        ["Sector", d.sector, "Industry", d.industry],
        ["Market cap", _money(d.market_cap, ccy), "Trailing P/E", f"{d.trailing_pe:.2f}" if d.trailing_pe else "—"],
        ["52-week range", f"{_money(d.fifty_two_week_low, ccy)} – {_money(d.fifty_two_week_high, ccy)}", "Price / book", f"{d.price_to_book:.2f}" if d.price_to_book else "—"],
        ["Normalized EPS", _money(d.eps, ccy), "Book value / share", _money(d.book_value_per_share, ccy)],
        ["Normalized FCF", _money(d.free_cash_flow, ccy), "Peer median", (f"{d.peer_median_pb:.2f}× P/B" if result.methodology_profile in {"Financial institution", "Real estate / REIT"} and d.peer_median_pb else (f"{d.peer_median_pe:.2f}× P/E" if d.peer_median_pe else "—"))],
    ]
    st = Table(snapshot, colWidths=[28*mm, 58*mm, 30*mm, 56*mm])
    st.setStyle(TableStyle([("BACKGROUND", (0,0), (0,-1), light), ("BACKGROUND", (2,0), (2,-1), light), ("FONT", (0,0), (-1,-1), "Helvetica", 8), ("FONT", (0,0), (0,-1), "Helvetica-Bold", 8), ("FONT", (2,0), (2,-1), "Helvetica-Bold", 8), ("GRID", (0,0), (-1,-1), .35, colors.HexColor("#CFD8E3")), ("VALIGN", (0,0), (-1,-1), "MIDDLE"), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
    story.append(st)

    def key_value_table(rows):
        table=Table([[Paragraph(html.escape(str(label)),styles["Small"]),Paragraph(html.escape(str(value)),styles["Small"])] for label,value in rows],colWidths=[58*mm,114*mm],hAlign="LEFT")
        table.setStyle(TableStyle([("ROWBACKGROUNDS",(0,0),(-1,-1),[light,colors.white]),("BOX",(0,0),(-1,-1),.35,colors.HexColor("#CFD8E3")),("INNERGRID",(0,0),(-1,-1),.25,colors.HexColor("#DDE4EC")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
        return table
    capital=result.cost_of_capital or {};drivers=result.valuation_drivers or {};driver_rows=[]
    if capital:
        driver_rows+=[("Risk-free rate",f"{capital['risk_free_rate']:.2%} • {capital['risk_free_source']}"),("Beta",f"{capital['beta']:.2f} • {capital['beta_source']}"),("Equity risk premium",f"{capital['equity_risk_premium']:.2%}"),
            ("Company-specific premium",f"{capital['company_risk_premium']:.2%} from financial and governance risk"),("Cost of equity",f"{capital['cost_of_equity']:.2%}"),("Pre-tax cost of debt / debt weight",f"{capital['pre_tax_cost_of_debt']:.2%} / {capital['debt_weight']:.0%}"),
            ("Tax rate",f"{capital['tax_rate']:.1%}"),("Cost of equity used" if result.methodology_profile=="Financial institution" else "WACC",f"{capital['wacc']:.2%}")]
    if drivers.get("basis") and drivers.get("basis")!="Residual income":
        driver_rows.append(("Primary model basis",drivers["basis"]))
        driver_rows+=[(label,f"{drivers[key]:.1%}") for key,label in (("fcff_margin","Normalized FCFF margin"),("nopat_margin","Normalized NOPAT margin"),("roic","ROIC"),("reinvestment_rate","Reinvestment rate")) if drivers.get(key) is not None]
        if drivers.get("shares"):driver_rows.append(("Net claims per share",_money(drivers["net_claims"]/drivers["shares"],ccy)+" (debt + minority interest - cash - credited investments)"))
        if drivers.get("margin_note"):driver_rows.append(("Margin normalization",drivers["margin_note"]))
    driver_rows.append(("High-growth stage",f"{a.high_growth_years} of {a.years} forecast years"))
    if result.terminal_value_share is not None:driver_rows.append(("Terminal value share",f"{result.terminal_value_share:.0%} of the primary model's value"))
    if result.growth_components:driver_rows.append(("Initial growth sources","; ".join(f"{name} {value:.1%}" for name,value in result.growth_components.items())))
    story += [Paragraph("Cost of capital & value drivers",styles["H2X"]),key_value_table(driver_rows)]
    if result.relative_components:
        story += [Paragraph("Relative valuation components",styles["H2X"]),key_value_table([(name,_money(value,ccy)+" per share") for name,value in result.relative_components.items()]+[("Blended relative value",_money(result.scenarios["Base"].relative,ccy)+" • "+result.model_labels.get("relative",""))]),Paragraph("Peer medians are adjusted for growth (P/E) and ROE (P/B) differences within bounded limits, then blended 60/40 with the stock's own median multiples at past fiscal year-ends.",styles["Small"])]
    if d.financial_metrics is not None:
        fm=d.financial_metrics;story += [Paragraph("Specialized financial-company data",styles["H2X"]),Paragraph(f"Subtype: <b>{html.escape(fm.subtype)}</b> • Source: {html.escape(fm.source)} • Specialized secondary model: <b>{html.escape(result.model_labels.get('graham','Justified P/B'))}</b>",styles["BodyX"])]
        financial_labels=[("reviewed_roe","Reviewed ROE",fm.reviewed_roe,"percent"),("net_interest_margin","Net interest margin",fm.net_interest_margin,"percent"),("financing_margin","Financing margin",fm.financing_margin,"percent"),("gross_npa","Gross NPA",fm.gross_npa,"percent"),("net_npa","Net NPA",fm.net_npa,"percent"),("capital_adequacy","Capital adequacy",fm.capital_adequacy,"percent"),("cet1_ratio","CET1",fm.cet1_ratio,"percent"),("provision_coverage","Provision coverage",fm.provision_coverage,"percent"),("casa_ratio","CASA ratio",fm.casa_ratio,"percent"),("credit_cost","Credit cost",fm.credit_cost,"percent"),("deposit_growth","Deposit growth",fm.deposit_growth,"percent"),("loan_growth","Loan growth",fm.loan_growth,"percent"),("cost_to_income","Cost-to-income",fm.cost_to_income,"percent"),("equity_to_assets","Equity-to-assets proxy",fm.equity_to_assets,"percent"),("solvency_ratio","Solvency ratio",fm.solvency_ratio,"multiple"),("embedded_value_per_share","Embedded value/share",fm.embedded_value_per_share,"money"),("fair_price_to_embedded_value","Fair P/EV",fm.fair_price_to_embedded_value,"multiple"),("vnb_margin","VNB margin",fm.vnb_margin,"percent"),("premium_growth","Premium growth",fm.premium_growth,"percent")]
        financial_rows=[["Metric","Value","Status"]]
        for field,label,value,kind in financial_labels:
            if value is None:display="—"
            elif kind=="percent":display=f"{value:.2%}"
            elif kind=="multiple":display=f"{value:.2f}x"
            else:display=_money(value,ccy)
            financial_rows.append([label,display,"Manual" if field in fm.manual_fields else "Public / derived"])
        ft=Table(financial_rows,colWidths=[72*mm,45*mm,50*mm],repeatRows=1)
        ft.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("FONT",(0,1),(-1,-1),"Helvetica",7.5),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#CAD4E0")),("ALIGN",(1,1),(1,-1),"RIGHT"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]));story.append(ft)
        if fm.review_note:story.append(Paragraph("<b>Specialized-data note:</b> "+html.escape(fm.review_note),styles["Small"]))
        story.append(Paragraph("NPA, capital, CET1, provisioning, CASA, credit-cost, solvency, embedded-value, and VNB figures must be verified against regulatory filings. Public proxies are explicitly labeled and are not regulatory substitutes.",styles["Small"]))
    if d.external_reviews:
        story += [Paragraph("External manual reviews",styles["H2X"])]
        external_rows=[["Source","Period","Fields","Citation"]]
        for review in d.external_reviews:
            source=html.escape(review.get("source","Manual review"));url=review.get("url","");citation=f'<link href="{html.escape(url,quote=True)}" color="#2563EB"><u>Open source</u></link>' if url else "—";external_rows.append([Paragraph(source,styles["Small"]),Paragraph(html.escape(review.get("period","")),styles["Small"]),Paragraph(html.escape(review.get("fields","")),styles["Small"]),Paragraph(citation,styles["Small"])])
        external_table=Table(external_rows,colWidths=[42*mm,30*mm,70*mm,28*mm],repeatRows=1);external_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("FONT",(0,1),(-1,-1),"Helvetica",7.5),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#CAD4E0")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]));story += [external_table,Paragraph("External manual values are user-reviewed inputs. The cited source remains subject to its own terms and accuracy limitations.",styles["Small"])]

    story += [Paragraph("Method and assumptions", styles["H2X"]), Paragraph(
        f"Profile selected: {result.methodology_profile}. Normalized inputs are latest revenue × median multi-year margin (stock-based compensation deducted). The primary model is an FCFF DCF at WACC with an equity bridge (residual income for financial institutions), the secondary model is earnings power value (justified P/B or embedded value for financial institutions), and relative value blends growth/ROE-adjusted peer multiples with the stock's own valuation history. Sector-aware weights are {a.dcf_weight:.0%}, {a.graham_weight:.0%}, and {a.relative_weight:.0%}. Missing methods are omitted and remaining weights are re-normalized. Scenarios are estimates, not price forecasts.", styles["BodyX"])]
    assumptions = [["Valuation profile", result.methodology_profile], ["Forecast period", f"{a.years} years; growth fades after year {a.high_growth_years}"], ["High-growth years", f"{a.high_growth_years} (from ROIC versus cost of capital)"], ["Scenario weights", " / ".join(f"{weight:.0%}" for weight in (result.scenario_weights or [.25,.5,.25]))], ["Base growth", f"{a.growth:.1%}"], ["Base discount rate", f"{a.discount_rate:.1%}"], ["Base terminal growth", f"{a.terminal_growth:.1%}"], ["Minimum / required buffer", f"{a.margin_of_safety:.0%} / {result.dynamic_margin:.0%}"], ["Financial risk score", f"{result.risk_score}/100 (lower is better)"], ["Data quality score", f"{result.data_quality_score}/100"], ["Live peers", ", ".join(d.peer_symbols[:8]) if d.peer_symbols else "Unavailable"], ["Data source", f"{d.data_provider} • {d.source_symbol or d.symbol}"], ["Source updated", d.source_updated_date or "Not supplied"], ["Sources checked", ", ".join(d.data_sources) if d.data_sources else d.data_provider], ["Cache delivery", f"{d.cache_status} • age {d.cache_age_hours:.1f}h" if d.cache_status!="network" else "Network retrieval"], ["Data retrieved", d.data_timestamp or "Not recorded"]]
    at = Table(assumptions, colWidths=[55*mm, 65*mm], hAlign="LEFT")
    at.setStyle(TableStyle([("ROWBACKGROUNDS", (0,0), (-1,-1), [light, colors.white]), ("FONT", (0,0), (0,-1), "Helvetica-Bold", 8.5), ("FONT", (1,0), (1,-1), "Helvetica", 8.5), ("BOX", (0,0), (-1,-1), .35, colors.HexColor("#CFD8E3")), ("INNERGRID", (0,0), (-1,-1), .25, colors.HexColor("#DDE4EC")), ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5)]))
    story.append(at)
    story += [Paragraph("Assumption review & override disclosure",styles["H2X"])]
    override_labels={"growth":"Base growth","discount_rate":"Discount rate","terminal_growth":"Terminal growth","years":"Forecast period","high_growth_years":"High-growth years","dcf_weight":"Primary model weight","graham_weight":"Graham/book weight","relative_weight":"Live-peer weight","margin_of_safety":"Minimum valuation buffer"}
    if result.manual_overrides:
        review_rows=[["Assumption","Automatic","Reviewed","Difference"]]
        for key,(automatic,reviewed) in result.manual_overrides.items():
            if key in {"years","high_growth_years"}:auto_text=f"{automatic:.0f} years";reviewed_text=f"{reviewed:.0f} years";difference=f"{reviewed-automatic:+.0f} years"
            else:auto_text=f"{automatic:.1%}";reviewed_text=f"{reviewed:.1%}";difference=f"{(reviewed-automatic)*100:+.1f} pp"
            review_rows.append([override_labels.get(key,key),auto_text,reviewed_text,difference])
        review=Table(review_rows,colWidths=[60*mm,35*mm,35*mm,35*mm],repeatRows=1)
        review.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7.5),("FONT",(0,1),(-1,-1),"Helvetica",8),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#FFF7DF")]),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#C9D3DF")),("ALIGN",(1,1),(-1,-1),"RIGHT"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]));story += [Paragraph(f"Preset: <b>{html.escape(result.assumption_preset)}</b> • {len(result.manual_overrides)} manual override(s)",styles["BodyX"]),review]
    else:story.append(Paragraph("Automatic defaults were used without manual overrides.",styles["BodyX"]))
    if result.assumption_note:story += [Spacer(1,2*mm),Paragraph("<b>Reviewer note:</b> "+result.assumption_note.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;"),styles["Small"])]

    story += [Paragraph("Risk, resilience and confidence analytics", styles["H2X"])]
    phase2 = [["Business quality", f"{result.business_quality_score}/100 (higher is better)", "Governance risk", f"{result.governance_risk_score}/100 (lower is better)"],
              ["Order book", f"{result.order_book_score}/100" if result.data.order_book is not None else "Unavailable", "Promoter trend", f"{result.data.promoter_holding_history[0]:.2%} latest / {result.data.promoter_holding_history[-1]:.2%} earliest" if len(result.data.promoter_holding_history)>=3 else "Unavailable"],
              ["Confidence", f"{result.confidence_score}/100 — {result.confidence}", "Model dispersion", f"{result.model_dispersion:.1%}" if result.model_dispersion is not None else "—"],
              ["Reverse DCF", f"{result.reverse_dcf_growth:.1%} implied initial growth" if result.reverse_dcf_growth is not None else "Unavailable", "Required valuation buffer", f"{result.dynamic_margin:.0%}"]]
    p2=Table(phase2,colWidths=[30*mm,56*mm,30*mm,56*mm])
    p2.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),light),("BACKGROUND",(2,0),(2,-1),light),("FONT",(0,0),(0,-1),"Helvetica-Bold",8),("FONT",(2,0),(2,-1),"Helvetica-Bold",8),("FONT",(1,0),(1,-1),"Helvetica",8),("FONT",(3,0),(3,-1),"Helvetica",8),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#CFD8E3")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)])); story += [p2,Spacer(1,2*mm),score_visual(),Paragraph("Resilience bars invert financial/governance risk so longer green bars indicate stronger modeled resilience. They do not guarantee protection from loss.",styles["Small"]),Paragraph(html.escape(result.reverse_dcf_note),styles["Small"])]
    forensic=result.forensic_scores or {};forensic_rows=[]
    if forensic.get("piotroski"):forensic_rows.append(("Piotroski F-score",f"{forensic['piotroski']['score']} of {forensic['piotroski']['tested']} tests passed"+(" • failed: "+", ".join(forensic['piotroski']['failed']) if forensic['piotroski']['failed'] else "")))
    if forensic.get("altman"):forensic_rows.append((forensic["altman"]["model"],f"{forensic['altman']['score']:.2f} • {forensic['altman']['zone']} zone"))
    if forensic.get("beneish"):forensic_rows.append(("Beneish M-score",f"{forensic['beneish']['score']:.2f} • {'above' if forensic['beneish']['flag'] else 'below'} the -1.78 screening threshold"))
    if forensic.get("roic_median") is not None:forensic_rows.append(("Median ROIC",f"{forensic['roic_median']:.1%} over {forensic.get('roic_years') or 1} year(s) vs cost of capital {capital.get('wacc',a.discount_rate):.1%}"))
    if forensic.get("roce_median_10y") is not None:forensic_rows.append(("Ten-year median ROCE",f"{forensic['roce_median_10y']:.1%} (Screener.in)"))
    if forensic.get("margin_stability"):forensic_rows.append(("Operating margin stability",f"median {forensic['margin_stability']['median_margin']:.1%}"+(f", variation {forensic['margin_stability']['variation']:.2f}" if forensic['margin_stability'].get('variation') is not None else "")+f" over {forensic['margin_stability']['years']} years"))
    if forensic.get("cash_conversion_cycle"):forensic_rows.append(("Cash conversion cycle",f"{forensic['cash_conversion_cycle']['latest']:.0f} days ({forensic['cash_conversion_cycle']['change']:+.0f} over {forensic['cash_conversion_cycle']['years']} years; {forensic['cash_conversion_cycle']['source']})"))
    if forensic.get("owner_earnings_per_share") is not None:forensic_rows.append(("Owner earnings per share",_money(forensic["owner_earnings_per_share"],ccy)+(f" • yield {forensic['owner_earnings_yield']:.1%}" if forensic.get("owner_earnings_yield") is not None else "")))
    allocation=forensic.get("capital_allocation") or {}
    if allocation.get("net_repurchase_yield") is not None:forensic_rows.append(("Net share repurchase yield",f"{allocation['net_repurchase_yield']:.2%}"))
    if allocation.get("dividend_payout") is not None:forensic_rows.append(("Dividend payout",f"{allocation['dividend_payout']:.0%}"))
    if forensic.get("institutional_trend") is not None:forensic_rows.append(("FII + DII holding change",f"{forensic['institutional_trend']:+.1%} over the available quarters"))
    if forensic.get("promoter_pledge") is not None:forensic_rows.append(("Promoter pledge",f"{forensic['promoter_pledge']:.1%} of promoter holding"))
    if forensic.get("effective_tax_rate") is not None:forensic_rows.append(("Effective tax rate",f"{forensic['effective_tax_rate']:.1%}"))
    if forensic_rows:story += [Paragraph("Quality & forensic screens",styles["H2X"]),key_value_table(forensic_rows),Paragraph("Forensic scores are statistical screens, not findings of misstatement. Piotroski and Altman scores feed financial risk; Beneish M-score and promoter pledge feed governance risk; ROIC, ROCE, margin stability, and the cash cycle feed business quality.",styles["Small"])]

    if result.sensitivity_values:
        story += [Paragraph("Fair-value sensitivity",styles["H2X"])]
        sens_rows=[["Discount \\ Terminal"]+[f"{x:.1%}" for x in result.sensitivity_terminal_growths]]
        for rate,row in zip(result.sensitivity_discount_rates,result.sensitivity_values):
            sens_rows.append([f"{rate:.1%}"]+[_money(v,ccy) for v in row])
        sens=Table(sens_rows,colWidths=[28*mm]+[28.8*mm]*5,repeatRows=1)
        sens.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("BACKGROUND",(0,1),(0,-1),light),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("FONT",(0,1),(-1,-1),"Helvetica",7.3),("ALIGN",(1,0),(-1,-1),"RIGHT"),("ALIGN",(0,0),(0,-1),"CENTER"),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#C9D3DF")),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        heat=[]
        for row_index,row in enumerate(result.sensitivity_values,1):
            for col_index,value in enumerate(row,1):
                if value is None:continue
                ratio=value/d.price;color=colors.HexColor("#CDEEDD") if ratio>=1.2 else colors.HexColor("#E4F4EA") if ratio>=1 else colors.HexColor("#FFF0CC") if ratio>=.8 else colors.HexColor("#FADBD8");heat.append(("BACKGROUND",(col_index,row_index),(col_index,row_index),color))
        heat.append(("FONT",(3,3),(3,3),"Helvetica-Bold",7.3));sens.setStyle(TableStyle(heat));story += [sens,Paragraph("Green: above market price • Amber: near market price • Red: below market price • Bold: base assumptions",styles["Small"])]

    if result.monte_carlo_percentiles:
        story += [Paragraph("Monte Carlo valuation — Phase 3 item 11",styles["H2X"])]
        mc=result.monte_carlo_percentiles
        mc_rows=[["P10","P25","Median","P75","P90","Probability FV > price","Simulations"],[_money(mc.get("P10"),ccy),_money(mc.get("P25"),ccy),_money(mc.get("P50"),ccy),_money(mc.get("P75"),ccy),_money(mc.get("P90"),ccy),f"{result.monte_carlo_probability_above_price:.1%}" if result.monte_carlo_probability_above_price is not None else "—",f"{result.monte_carlo_iterations:,}"]]
        mt=Table(mc_rows,colWidths=[23*mm,23*mm,26*mm,23*mm,23*mm,31*mm,23*mm])
        mt.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("FONT",(0,1),(-1,1),"Helvetica-Bold",8),("ALIGN",(0,0),(-1,-1),"CENTER"),("BACKGROUND",(0,1),(-1,1),light),("GRID",(0,0),(-1,-1),.35,colors.HexColor("#C9D3DF")),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5)]));story += [mt,Spacer(1,2*mm)]
        mc_drawing=monte_carlo_visual()
        if mc_drawing:story.append(mc_drawing)
        story.append(Paragraph("Simulation varies normalized financial inputs, initial growth, discount rate, terminal growth, and peer multiples. Percentiles describe model uncertainty—not expected returns or the probability of making a profit.",styles["Small"]))

    story += [Paragraph("Model audit trail",styles["H2X"])]
    audit_meta=[["Analysis ID",result.analysis_id,"Model version",result.model_version],["Parent analysis",result.parent_analysis_id or "None","App / schema",f"{result.app_version} / {result.audit_schema_version}"],["Created UTC",result.created_at,"Monte Carlo seed",str(result.monte_carlo_seed)],["Audit SHA-256",Paragraph(result.audit_hash,styles["Small"]),"Integrity","Valid" if verify_audit_hash(result) else "FAILED"]]
    audit_meta_table=Table(audit_meta,colWidths=[28*mm,61*mm,30*mm,53*mm])
    audit_meta_table.setStyle(TableStyle([("BACKGROUND",(0,0),(0,-1),light),("BACKGROUND",(2,0),(2,-1),light),("FONT",(0,0),(0,-1),"Helvetica-Bold",7.5),("FONT",(2,0),(2,-1),"Helvetica-Bold",7.5),("FONT",(1,0),(1,-1),"Helvetica",7),("FONT",(3,0),(3,-1),"Helvetica",7),("GRID",(0,0),(-1,-1),.3,colors.HexColor("#CAD4E0")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]));story.append(audit_meta_table)
    if result.audit_events:
        audit_rows=[["Stage","Action","Details"]]
        for event in result.audit_events:
            details="; ".join(f"{key}={value}" for key,value in event.details.items());audit_rows.append([Paragraph(html.escape(event.stage),styles["Small"]),Paragraph(html.escape(event.action),styles["Small"]),Paragraph(html.escape(details),styles["Small"])])
        audit_table=Table(audit_rows,colWidths=[28*mm,45*mm,99*mm],repeatRows=1)
        audit_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",7),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#CAD4E0")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]));story += [Spacer(1,2*mm),audit_table,Paragraph("The SHA-256 hash provides tamper-evidence for this audit record; it is not a digital signature or guarantee of model accuracy.",styles["Small"])]

    story += [Paragraph("Data lineage & citations",styles["H2X"])]
    if d.lineage:
        lineage_rows=[["Metric","Value","Source","Period","Transformation","Status"]]
        for entry in d.lineage:
            source_text=html.escape(entry.source)
            if entry.source_url:source_text=f'<link href="{html.escape(entry.source_url,quote=True)}" color="#2563EB"><u>{source_text}</u></link>'
            lineage_rows.append([Paragraph(html.escape(entry.metric),styles["Small"]),Paragraph(html.escape(entry.value),styles["Small"]),Paragraph(source_text,styles["Small"]),Paragraph(html.escape(entry.period or "—"),styles["Small"]),Paragraph(html.escape(entry.transformation),styles["Small"]),Paragraph(html.escape(entry.status),styles["Small"])])
        lineage_table=Table(lineage_rows,colWidths=[28*mm,30*mm,24*mm,24*mm,51*mm,16*mm],repeatRows=1)
        lineage_table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),navy),("TEXTCOLOR",(0,0),(-1,0),colors.white),("FONT",(0,0),(-1,0),"Helvetica-Bold",6.8),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,light]),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#CAD4E0")),("VALIGN",(0,0),(-1,-1),"TOP"),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]));story += [lineage_table,Spacer(1,2*mm),Paragraph("Links open the cited public source. Values can change after retrieval; this table records the period, retrieval context, and transformation used by the analysis.",styles["Small"])]
    else:story.append(Paragraph("Detailed source lineage was unavailable for this analysis. Verify all figures manually.",styles["Small"]))

    story += [Paragraph("Interpretation, limitations & risks", styles["H2X"])]
    bullets = [
        "Fair value is highly sensitive to growth, discount-rate, terminal-growth, and normalized earnings assumptions.",
        "Free Yahoo/Screener/NSE/BSE website data can be delayed, incomplete, restated, rate-limited, blocked, or unavailable; verify figures against company filings.",
        "Banks, insurers, REITs, cyclical firms, loss-making firms, and businesses with unusual capital structures may require specialized models.",
        "Live peers are screened through free Yahoo Finance region, industry/sector, and market-cap filters; they may still differ in growth, leverage, accounting, or business mix.",
        "Currency is native to the listing. This report does not fully model governance, taxes, FX, liquidity, or portfolio concentration.",
    ] + result.risk_flags + result.quality_flags + result.business_quality_flags + result.governance_flags + result.order_book_flags + d.warnings + result.model_notes
    for item in bullets:
        story.append(Paragraph("• " + html.escape(item), styles["BodyX"])); story.append(Spacer(1, 1.5*mm))

    story += [Spacer(1, 3*mm), KeepTogether([Paragraph("Important disclaimer", styles["H2X"]), Paragraph(
        "For education and research only. This is an automated estimate, not investment advice, a recommendation, an offer, or a guarantee of future returns. Market prices can differ materially from model values. Independently verify all data and consult a SEBI-registered investment adviser in India or an appropriately registered financial professional in your jurisdiction before making investment decisions.", styles["Small"])])]
    doc.multiBuild(story, onFirstPage=header_footer, onLaterPages=header_footer)
