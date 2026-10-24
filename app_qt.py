"""Modern PySide6 desktop interface for DR. NILESH SHAH - STOCKS FAIRSCOPE."""
from __future__ import annotations

import csv
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote

from PySide6.QtCore import (
    QObject,
    QPointF,
    QRectF,
    QRunnable,
    QStringListModel,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDesktopServices,
    QIcon,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from background_processing import JobControl, analyze_with_retry
from backtest import FORWARD_NOTE, LOOK_AHEAD_NOTE, backtest_stock, point_record, summarize, track_saved_valuations
from batch_import import BatchItem, export_batch_csv, import_stock_list, write_csv_row
from batch_pdf_report import create_batch_pdf
from corporate_monitor import CorporateMonitorStore, monitor_entry
from data_provider import MARKET_PARAMETER_DEFAULTS, fetch_stock, valuation_settings
from diagnostics import get_diagnostics
from local_database import get_local_database
from pdf_report import create_pdf
from secure_storage import SecureStorage, data_directory
from stock_search import search_stocks
from valuation import (
    Assumptions,
    DataLineageEntry,
    FinancialCompanyMetrics,
    ValuationResult,
    audit_record,
    value_stock,
    verify_audit_hash,
)
from version import APP_VERSION
from watchlist_report import create_watchlist_pdf
from watchlist_store import WatchlistStore

NAVY="#10233F";NAVY2="#18395F";BLUE="#2563EB";GREEN="#138A5B";RED="#C2413B";BG="#F3F6FA";CARD="#FFFFFF";TEXT="#14243A";MUTED="#67768A";BORDER="#D8E1EC"

def resource_path(path:str)->str:
    return os.path.join(getattr(sys,"_MEIPASS",os.path.dirname(os.path.abspath(__file__))),path)

def money(value:float|None,currency:str)->str:
    return "—" if value is None else f"{currency} {value:,.2f}"

def compact_value(value:float|None,currency:str="")->str:
    if value is None:return "—"
    absolute=abs(value)
    for divisor,suffix in ((1_000_000_000_000,"T"),(1_000_000_000,"B"),(1_000_000,"M"),(1_000,"K")):
        if absolute>=divisor:return f"{currency} {value/divisor:,.1f}{suffix}".strip()
    return f"{currency} {value:,.2f}".strip()

class WorkerSignals(QObject):
    result=Signal(object);error=Signal(str);progress=Signal(object);status=Signal(str);finished=Signal()
class Worker(QRunnable):
    def __init__(self,fn:Callable[...,Any],*args,**kwargs):
        super().__init__();self.fn=fn;self.args=args;self.kwargs=kwargs;self.signals=WorkerSignals()
    def run(self):
        try:self.signals.result.emit(self.fn(*self.args,**self.kwargs))
        except Exception as exc:self.signals.error.emit(str(exc))
        finally:self.signals.finished.emit()
class BatchWorker(QRunnable):
    def __init__(self,items:list[BatchItem],database=None,job_type="batch",max_workers=3,force_refresh=False):
        super().__init__();self.items=list(items);self.signals=WorkerSignals();self.control=JobControl();self.database=database;self.job_id=database.create_job(job_type,self.items) if database else None;self.max_workers=max(1,min(6,max_workers));self.force_refresh=force_refresh
    def pause(self):self.control.pause();self.signals.status.emit("Paused")
    def resume(self):self.control.resume();self.signals.status.emit("Running")
    def cancel(self):self.control.cancel();self.signals.status.emit("Cancelling after active network requests finish…")
    def run(self):
        outcomes=[];completed=0
        try:
            self.signals.status.emit(f"Running with {self.max_workers} parallel workers")
            with ThreadPoolExecutor(max_workers=self.max_workers,thread_name_prefix="FairScope") as executor:
                futures=[executor.submit(analyze_with_retry,index,item,self.control,3,self.force_refresh) for index,item in enumerate(self.items)]
                for future in as_completed(futures):
                    outcome=future.result();outcomes.append(outcome);completed+=1
                    if self.database and self.job_id:self.database.update_job(self.job_id,completed,outcome)
                    self.signals.progress.emit((outcome.index,outcome.result,outcome.error,completed,len(self.items),outcome.attempts,outcome.cancelled))
            outcomes_by_index={outcome.index:outcome for outcome in outcomes};records=[]
            for index,item in enumerate(self.items):
                outcome=outcomes_by_index.get(index);records.append((item,outcome.result if outcome else None,outcome.error if outcome else "Cancelled"))
            if self.database and self.job_id:self.database.finish_job(self.job_id,"cancelled" if self.control.cancelled else "completed")
            self.signals.result.emit(records)
        except Exception as exc:
            if self.database and self.job_id:self.database.finish_job(self.job_id,"failed",str(exc))
            self.signals.error.emit(str(exc))
        finally:self.signals.finished.emit()

class BacktestWorker(QRunnable):
    def __init__(self,items:list[BatchItem],years_back:int,max_workers=3):
        super().__init__();self.items=list(items);self.years_back=years_back;self.max_workers=max(1,min(6,max_workers));self.signals=WorkerSignals();self.control=JobControl()
    def pause(self):self.control.pause();self.signals.status.emit("Paused")
    def resume(self):self.control.resume();self.signals.status.emit("Running")
    def cancel(self):self.control.cancel();self.signals.status.emit("Cancelling after active network requests finish…")
    def _one(self,item):
        if not self.control.checkpoint():return [],[f"{item.symbol}: cancelled"]
        try:return backtest_stock(fetch_stock(item.symbol,item.market),self.years_back)
        except Exception as exc:return [],[f"{item.symbol}: {exc}"]
    def run(self):
        points=[];errors=[];completed=0
        try:
            with ThreadPoolExecutor(max_workers=self.max_workers,thread_name_prefix="FairScopeBacktest") as executor:
                for future in as_completed([executor.submit(self._one,item) for item in self.items]):
                    found,problems=future.result();points+=found;errors+=problems;completed+=1
                    self.signals.progress.emit((0,None,"",completed,len(self.items),1,False))
            self.signals.result.emit((points,errors))
        except Exception as exc:self.signals.error.emit(str(exc))
        finally:self.signals.finished.emit()

class CorporateMonitorWorker(QRunnable):
    def __init__(self,entries,contact_email):super().__init__();self.entries=entries;self.contact_email=contact_email;self.signals=WorkerSignals()
    def run(self):
        results=[]
        try:
            for index,entry in enumerate(self.entries):
                try:events,warnings,cik=monitor_entry(entry,self.contact_email);error=""
                except Exception as exc:events=[];warnings=[];cik=entry.cik;error=str(exc)
                results.append((entry,events,warnings,cik,error));self.signals.progress.emit((index,entry,len(events),error))
            self.signals.result.emit(results)
        except Exception as exc:self.signals.error.emit(str(exc))
        finally:self.signals.finished.emit()

class Card(QFrame):
    def __init__(self,parent=None):super().__init__(parent);self.setObjectName("card")
class MetricCard(Card):
    def __init__(self,title:str):
        super().__init__();layout=QVBoxLayout(self);layout.setContentsMargins(16,12,16,12);layout.setSpacing(5)
        t=QLabel(title);t.setObjectName("metricTitle");self.value=QLabel("—");self.value.setObjectName("metricValue");layout.addWidget(t);layout.addWidget(self.value)
    def set_value(self,value:str,color:str|None=None):self.value.setText(value);self.value.setStyleSheet(f"color:{color or TEXT};")

class AccessibleMessageDialog(QDialog):
    """High-contrast, non-native message dialog that remains readable in Windows dark mode."""
    PALETTES={
        "information":("#E8F1FF","#1D4ED8","#173B70","i"),
        "success":("#E7F6EE","#138A5B","#135C42","✓"),
        "warning":("#FFF4D8","#A15C00","#704000","!"),
        "critical":("#FDE9E7","#C2413B","#7F2521","×"),
    }
    def __init__(self,title:str,message:str,parent=None,kind="information"):
        super().__init__(parent);self.setWindowTitle(title);self.setWindowModality(Qt.WindowModal);self.setMinimumWidth(560);self.setMaximumWidth(780);self.setAttribute(Qt.WA_StyledBackground,True)
        background,accent,dark,icon=self.PALETTES.get(kind,self.PALETTES["information"])
        self.setStyleSheet(f"""
            QDialog{{background:#FFFFFF;color:#14243A;}}
            QFrame#messageHeader{{background:{background};border-bottom:1px solid {accent};}}
            QLabel#messageIcon{{background:{accent};color:#FFFFFF;border-radius:18px;font-size:17pt;font-weight:800;}}
            QLabel#messageTitle{{color:{dark};font-size:15pt;font-weight:800;background:transparent;}}
            QLabel#messageBody{{color:#14243A;background:#FFFFFF;font-size:10.5pt;line-height:1.35;}}
            QLabel#messageHint{{color:#526072;background:#FFFFFF;font-size:9pt;}}
            QPushButton{{background:#EEF3F8;color:#14243A;border:1px solid #C8D4E2;border-radius:7px;padding:8px 18px;font-weight:700;min-width:76px;}}
            QPushButton:hover{{background:#DFE9F4;}}
            QPushButton#messagePrimary{{background:{accent};color:#FFFFFF;border:1px solid {accent};}}
            QPushButton#messagePrimary:hover{{background:{dark};}}
        """)
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        header=QFrame();header.setObjectName("messageHeader");head=QHBoxLayout(header);head.setContentsMargins(22,18,22,18);head.setSpacing(14)
        badge=QLabel(icon);badge.setObjectName("messageIcon");badge.setFixedSize(36,36);badge.setAlignment(Qt.AlignCenter)
        heading=QLabel(title);heading.setObjectName("messageTitle");heading.setWordWrap(True);head.addWidget(badge);head.addWidget(heading,1);outer.addWidget(header)
        body=QWidget();body.setStyleSheet("background:#FFFFFF;");layout=QVBoxLayout(body);layout.setContentsMargins(24,20,24,20);layout.setSpacing(14)
        text=QLabel(str(message));text.setObjectName("messageBody");text.setWordWrap(True);text.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard);text.setMinimumWidth(480);layout.addWidget(text)
        hint=QLabel("You can select and copy the message text.");hint.setObjectName("messageHint");layout.addWidget(hint)
        actions=QHBoxLayout();actions.addStretch()
        path=str(message).strip();folder=os.path.dirname(path) if os.path.isabs(path) else ""
        if folder and os.path.isdir(folder):
            open_folder=QPushButton("Open folder");open_folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(folder)));actions.addWidget(open_folder)
        close=QPushButton("OK");close.setObjectName("messagePrimary");close.setDefault(True);close.clicked.connect(self.accept);actions.addWidget(close);layout.addLayout(actions);outer.addWidget(body)
        self.adjustSize()

    @classmethod
    def information(cls,parent,title,message):return cls(title,message,parent,"information").exec()
    @classmethod
    def success(cls,parent,title,message):return cls(title,message,parent,"success").exec()
    @classmethod
    def warning(cls,parent,title,message):return cls(title,message,parent,"warning").exec()
    @classmethod
    def critical(cls,parent,title,message):return cls(title,message,parent,"critical").exec()

class WatchlistAlertDialog(QDialog):
    def __init__(self,alerts,parent=None):
        super().__init__(parent);self.setWindowTitle("New FairScope watchlist alerts");self.setMinimumSize(620,360);self.setStyleSheet("QDialog{background:#F4F7FB;} QLabel{color:#14243A;background:transparent;} QFrame#alertCard{border-radius:8px;} QPushButton{background:#2563EB;color:white;border:0;border-radius:6px;padding:8px 18px;font-weight:700;} QScrollArea{border:0;background:#F4F7FB;}")
        layout=QVBoxLayout(self);title=QLabel(f"{len(alerts)} new watchlist alert{'s' if len(alerts)!=1 else ''}");title.setStyleSheet("font-size:18pt;font-weight:800;color:#10233F;");subtitle=QLabel("Review these research notifications. They are not trading instructions.");subtitle.setStyleSheet("color:#526072;");layout.addWidget(title);layout.addWidget(subtitle);scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();content_layout=QVBoxLayout(content)
        palette={"high":("#FDE8E7","#B42318"),"warning":("#FFF3D6","#8A5A00"),"info":("#E7F0FF","#1D4ED8")}
        for alert in alerts:
            background,accent=palette.get(alert.severity,palette["info"]);card=QFrame();card.setObjectName("alertCard");card.setStyleSheet(f"QFrame#alertCard{{background:{background};border-left:6px solid {accent};}} QLabel{{color:#14243A;}}");card_layout=QVBoxLayout(card);heading=QLabel(f"{alert.symbol}  •  {alert.kind.replace('_',' ').title()}  •  {alert.severity.upper()}");heading.setStyleSheet(f"font-weight:800;color:{accent};font-size:11pt;");message=QLabel(alert.message);message.setWordWrap(True);message.setStyleSheet("color:#14243A;font-size:10pt;");time_label=QLabel(alert.created_at[:19]);time_label.setStyleSheet("color:#66768A;font-size:8pt;");card_layout.addWidget(heading);card_layout.addWidget(message);card_layout.addWidget(time_label);content_layout.addWidget(card)
        content_layout.addStretch();scroll.setWidget(content);layout.addWidget(scroll,1);close=QPushButton("Close");close.clicked.connect(self.accept);layout.addWidget(close,0,Qt.AlignRight)

class HistogramWidget(QWidget):
    def __init__(self):super().__init__();self.result:ValuationResult|None=None;self.setMinimumHeight(260)
    def set_result(self,result):self.result=result;self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing);p.fillRect(self.rect(),QColor(CARD))
        r=self.result
        if not r or not r.monte_carlo_bin_counts:
            p.setPen(QColor(MUTED));p.drawText(20,30,"Analyze a stock to generate its Monte Carlo distribution.");return
        counts=r.monte_carlo_bin_counts;edges=r.monte_carlo_bin_edges;left,top,right,bottom=58,25,self.width()-22,self.height()-40
        p.setPen(QPen(QColor("#AAB7C6"),1));p.drawLine(left,bottom,right,bottom)
        maxc=max(counts) or 1;bw=(right-left)/len(counts)
        p.setPen(Qt.NoPen);p.setBrush(QColor(BLUE))
        for i,count in enumerate(counts):
            height=(bottom-top)*count/maxc;p.drawRoundedRect(int(left+i*bw+2),int(bottom-height),max(2,int(bw-4)),int(height),3,3)
        p.setPen(QColor(MUTED));p.drawText(left,bottom+22,f"{r.data.currency} {edges[0]:,.0f}");label=f"{r.data.currency} {edges[-1]:,.0f}";p.drawText(right-p.fontMetrics().horizontalAdvance(label),bottom+22,label)
        if edges[-1]>edges[0] and edges[0]<=r.data.price<=edges[-1]:
            x=left+(r.data.price-edges[0])/(edges[-1]-edges[0])*(right-left);p.setPen(QPen(QColor(RED),2,Qt.DashLine));p.drawLine(int(x),top,int(x),bottom);p.drawText(int(x)-35,top-5,"Market price")

class PriceValueChart(QWidget):
    """One-year price path with current fair-value and valuation-buffer reference lines."""
    def __init__(self):super().__init__();self.result:ValuationResult|None=None;self.setMinimumHeight(230)
    def set_result(self,result):self.result=result;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),QColor(CARD));r=self.result
        if not r or len(r.data.price_history)<2:
            painter.setPen(QColor(MUTED));painter.drawText(18,28,"Analyze a stock to display its one-year price path.");return
        values=list(r.data.price_history);refs=[r.fair_value,r.margin_price];low=min(values+refs);high=max(values+refs);span=(high-low) or 1;low-=span*.08;high+=span*.08
        left,top,right,bottom=58,20,self.width()-95,self.height()-34
        painter.setPen(QPen(QColor("#D7E0EA"),1))
        for i in range(5):
            y=top+(bottom-top)*i/4;painter.drawLine(left,int(y),right,int(y));level=high-(high-low)*i/4;painter.setPen(QColor(MUTED));painter.drawText(4,int(y)+4,compact_value(level,r.data.currency));painter.setPen(QPen(QColor("#D7E0EA"),1))
        points=QPolygonF([QPointF(left+i*(right-left)/(len(values)-1),bottom-(v-low)/(high-low)*(bottom-top)) for i,v in enumerate(values)])
        painter.setPen(QPen(QColor(BLUE),2.2));painter.drawPolyline(points)
        for level,color,label in ((r.fair_value,GREEN,"Fair value"),(r.margin_price,"#C58B13",f"Buffer {r.dynamic_margin:.0%}")):
            y=bottom-(level-low)/(high-low)*(bottom-top);painter.setPen(QPen(QColor(color),1.8,Qt.DashLine));painter.drawLine(left,int(y),right,int(y));painter.setPen(QColor(color));painter.drawText(right+7,int(y)+4,label)
        painter.setPen(QColor(MUTED));painter.drawText(left,bottom+22,"1 year ago");latest="Latest";painter.drawText(right-painter.fontMetrics().horizontalAdvance(latest),bottom+22,latest)
        last=points[-1];painter.setBrush(QColor(BLUE));painter.setPen(Qt.NoPen);painter.drawEllipse(last,4,4)

class ModelBarChart(QWidget):
    def __init__(self):super().__init__();self.result:ValuationResult|None=None;self.setMinimumHeight(230)
    def set_result(self,result):self.result=result;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),QColor(CARD));r=self.result
        if not r:
            painter.setPen(QColor(MUTED));painter.drawText(18,28,"Model values will appear after analysis.");return
        base=r.scenarios["Base"];rows=[(r.model_labels.get("dcf","Primary"),base.dcf,"#6B8ED6"),(r.model_labels.get("graham","Graham"),base.graham,"#8AA5C8"),(r.model_labels.get("relative","Peers"),base.relative,"#6AB5A1"),("Blended fair value",r.fair_value,BLUE),("Market price",r.data.price,RED)]
        usable=[v for _,v,_ in rows if v is not None and v>0]
        if not usable:return
        maximum=max(usable)*1.08;left=145;right=self.width()-88;top=18;row_h=max(31,(self.height()-35)//len(rows))
        for index,(label,value,color) in enumerate(rows):
            y=top+index*row_h;painter.setPen(QColor(TEXT));painter.drawText(8,y+18,label)
            painter.setBrush(QColor("#EDF2F7"));painter.setPen(Qt.NoPen);painter.drawRoundedRect(left,y+4,max(10,right-left),18,5,5)
            if value is not None and value>0:
                width=(right-left)*value/maximum;painter.setBrush(QColor(color));painter.drawRoundedRect(left,y+4,max(3,int(width)),18,5,5);painter.setPen(QColor(TEXT));text=money(value,r.data.currency);painter.drawText(right+7,y+18,text)
            else:
                painter.setPen(QColor(MUTED));painter.drawText(right+7,y+18,"Unavailable")

class FundamentalTrendsChart(QWidget):
    def __init__(self):super().__init__();self.result:ValuationResult|None=None;self.setMinimumHeight(230)
    def set_result(self,result):self.result=result;self.update()
    def _draw_series(self,painter,label,values,color,currency,rect):
        x,y,w,h=rect;painter.setPen(QColor(TEXT));painter.drawText(x,y+15,label)
        usable=[float(v) for v in reversed(values[:5])]
        if len(usable)<2:
            painter.setPen(QColor(MUTED));painter.drawText(x+120,y+15,"Insufficient history");return
        minimum=min(usable);maximum=max(usable);span=max(maximum-minimum,abs(maximum)*.08,1);chart_left=x+120;chart_right=x+w-82;chart_top=y+4;chart_bottom=y+h-8
        if minimum<0<maximum:
            zero=chart_bottom-(0-minimum)/span*(chart_bottom-chart_top);painter.setPen(QPen(QColor("#D9E1EA"),1));painter.drawLine(chart_left,int(zero),chart_right,int(zero))
        points=QPolygonF([QPointF(chart_left+i*(chart_right-chart_left)/(len(usable)-1),chart_bottom-(v-minimum)/span*(chart_bottom-chart_top)) for i,v in enumerate(usable)])
        painter.setPen(QPen(QColor(color),2.1));painter.drawPolyline(points);painter.setBrush(QColor(color));painter.setPen(Qt.NoPen)
        for point in points:painter.drawEllipse(point,3,3)
        painter.setPen(QColor(MUTED));painter.drawText(chart_right+8,y+15,compact_value(usable[-1],currency))
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),QColor(CARD));r=self.result
        if not r:
            painter.setPen(QColor(MUTED));painter.drawText(18,28,"Revenue, earnings, and cash-flow trends will appear after analysis.");return
        height=max(55,(self.height()-14)//3);width=self.width()-20
        self._draw_series(painter,"Revenue",r.data.revenue_history,"#466FD4",r.data.currency,(10,5,width,height))
        self._draw_series(painter,"Net income",r.data.net_income_history,"#138A5B",r.data.currency,(10,5+height,width,height))
        self._draw_series(painter,"Free cash flow",r.data.fcf_history,"#8B5CB8",r.data.currency,(10,5+height*2,width,height))

class ScenarioGauge(QWidget):
    def __init__(self):super().__init__();self.result:ValuationResult|None=None;self.setMinimumHeight(230)
    def set_result(self,result):self.result=result;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing);painter.fillRect(self.rect(),QColor(CARD));r=self.result
        if not r:
            painter.setPen(QColor(MUTED));painter.drawText(18,28,"Scenario range will appear after analysis.");return
        scenarios=[(name,s.fair_value) for name,s in r.scenarios.items() if s.fair_value is not None];all_values=[v for _,v in scenarios]+[r.data.price,r.margin_price]
        low=min(all_values)*.9;high=max(all_values)*1.1;span=(high-low) or 1;left=48;right=self.width()-48;y=self.height()//2
        painter.setPen(QPen(QColor("#B8C5D4"),5));painter.drawLine(left,y,right,y)
        cons=r.scenarios["Conservative"].fair_value;opt=r.scenarios["Optimistic"].fair_value
        if cons is not None and opt is not None:
            x1=left+(min(cons,opt)-low)/span*(right-left);x2=left+(max(cons,opt)-low)/span*(right-left);painter.setPen(QPen(QColor("#BBD4FF"),13));painter.drawLine(int(x1),y,int(x2),y)
        markers=[("Market",r.data.price,RED,-42),("Buffer",r.margin_price,"#C58B13",42),("Base",r.fair_value,BLUE,-42)]
        for label,value,color,offset in markers:
            x=left+(value-low)/span*(right-left);painter.setPen(QPen(QColor(color),2));painter.drawLine(int(x),y-14,int(x),y+14);painter.setPen(QColor(color));text=f"{label}\n{money(value,r.data.currency)}";box=QRectF(x-65,y+offset,130,34);painter.drawText(box,Qt.AlignCenter,text)
        painter.setPen(QColor(MUTED));painter.drawText(left,self.height()-16,money(low,r.data.currency));high_text=money(high,r.data.currency);painter.drawText(right-painter.fontMetrics().horizontalAdvance(high_text),self.height()-16,high_text)

class FairScopeWindow(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle("DR. NILESH SHAH - STOCKS FAIRSCOPE");self.resize(1280,820);self.setMinimumSize(1050,700)
        self.setWindowIcon(QIcon(resource_path("assets/app_icon.ico")));self.pool=QThreadPool.globalInstance();self._active_workers=[];self._search_workers=[];self.current_control_worker=None;self._search_generation=0;self._search_results={};self._suppress_search=False;self.result:ValuationResult|None=None;self.batch_items=[];self.batch_records=[];self.diagnostics=get_diagnostics();self.secure_storage=SecureStorage(data_directory());self.watchlist_store=WatchlistStore();self.watchlist_results={};self.corporate_store=CorporateMonitorStore();legacy_email=self.corporate_store.get_setting("sec_contact_email");
        if legacy_email and not self.secure_storage.get_secret("sec_contact_email"):self.secure_storage.set_secret("sec_contact_email",legacy_email);self.corporate_store.set_setting("sec_contact_email","")
        self.local_database=get_local_database();self.privacy_mode=bool(self.local_database.setting("privacy_mode",False));self.interrupted_jobs=self.local_database.mark_running_interrupted()
        self._build_ui();self._apply_style();self.diagnostics.log("INFO","Application","Application started",f"Interrupted jobs: {self.interrupted_jobs}");self.statusBar().showMessage(f"Ready • {self.interrupted_jobs} recoverable interrupted job(s)" if self.interrupted_jobs else "Ready • Free Yahoo Finance data • No API key required")
    def _apply_style(self):
        self.setStyleSheet(f"""
        *{{font-family:'Segoe UI','Arial';font-size:10pt;color:{TEXT};}} QMainWindow,QWidget#root{{background:{BG};}}
        QFrame#sidebar{{background:{NAVY};}} QLabel#brand{{color:white;font-size:17pt;font-weight:700;}} QLabel#tagline{{color:#BFD0E5;font-size:9pt;}}
        QListWidget#nav{{background:transparent;border:0;outline:0;color:#D9E5F3;padding:6px;}} QListWidget#nav::item{{height:32px;padding-left:11px;border-radius:7px;color:#D9E5F3;}} QListWidget#nav::item:selected{{background:{BLUE};color:white;font-weight:600;}} QListWidget#nav::item:hover{{background:{NAVY2};}}
        QFrame#card{{background:{CARD};border:1px solid {BORDER};border-radius:10px;}} QLabel#pageTitle{{font-size:19pt;font-weight:700;color:{NAVY};}} QLabel#pageSub{{color:{MUTED};}} QLabel#metricTitle{{font-size:8pt;font-weight:700;color:{MUTED};}} QLabel#metricValue{{font-size:16pt;font-weight:700;color:{TEXT};}}
        QPushButton{{background:#E8EEF6;border:1px solid {BORDER};border-radius:7px;padding:8px 14px;font-weight:600;}} QPushButton:hover{{background:#DCE6F2;}} QPushButton#primary{{background:{BLUE};color:white;border:0;}} QPushButton#primary:hover{{background:#1D4ED8;}} QPushButton:disabled{{background:#E5E7EB;color:#9CA3AF;}}
        QLineEdit,QComboBox,QDoubleSpinBox,QSpinBox{{background:white;border:1px solid #C9D5E3;border-radius:6px;padding:7px;}} QLineEdit:focus,QComboBox:focus,QDoubleSpinBox:focus,QSpinBox:focus{{border:2px solid {BLUE};}}
        QTableWidget{{background:white;border:1px solid {BORDER};border-radius:7px;gridline-color:#E3E9F0;selection-background-color:#DCE8FF;}} QHeaderView::section{{background:#EAF0F6;color:{NAVY};font-weight:700;border:0;border-bottom:1px solid #CCD7E3;padding:8px;}}
        QTabWidget::pane{{border:1px solid {BORDER};background:white;border-radius:7px;}} QTabBar::tab{{background:#E6ECF3;padding:9px 16px;margin-right:2px;}} QTabBar::tab:selected{{background:white;color:{BLUE};font-weight:700;}}
        QTextEdit{{background:white;border:1px solid {BORDER};border-radius:7px;padding:8px;}} QProgressBar{{border:0;background:#DCE4EE;height:5px;}} QProgressBar::chunk{{background:{BLUE};}}
        QStatusBar{{background:white;border-top:1px solid {BORDER};color:{MUTED};}}
        """)
    def _build_ui(self):
        root=QWidget();root.setObjectName("root");self.setCentralWidget(root);outer=QHBoxLayout(root);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        sidebar=QFrame();sidebar.setObjectName("sidebar");sidebar.setFixedWidth(270);sl=QVBoxLayout(sidebar);sl.setContentsMargins(18,20,18,18)
        brandrow=QHBoxLayout();logo=QLabel();logo.setPixmap(QPixmap(resource_path("assets/logo_64.png")).scaled(54,54,Qt.KeepAspectRatio,Qt.SmoothTransformation));brandbox=QVBoxLayout();brand=QLabel("STOCKS\nFAIRSCOPE");brand.setObjectName("brand");tag=QLabel("DR. NILESH SHAH");tag.setObjectName("tagline");brandbox.addWidget(brand);brandbox.addWidget(tag);brandrow.addWidget(logo);brandrow.addLayout(brandbox);sl.addLayout(brandrow);sl.addSpacing(20)
        self.nav=QListWidget();self.nav.setObjectName("nav");self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);items=["Dashboard","Watchlists & alerts","Filings & actions","Visual analysis","Data lineage","Model audit","Batch analysis","Backtest","Risk & sensitivity","Monte Carlo","Assumptions review","Financial company","External review","Local database","Diagnostics","Data source","Methodology"]
        for text in items:self.nav.addItem(QListWidgetItem(text))
        sl.addWidget(self.nav,1);source=QLabel(f"VERSION {APP_VERSION}\nFREE MULTI-SOURCE DATA\nYAHOO • SCREENER • NSE • BSE");source.setObjectName("tagline");source.setWordWrap(True);sl.addWidget(source);outer.addWidget(sidebar)
        main=QWidget();ml=QVBoxLayout(main);ml.setContentsMargins(22,16,22,12);ml.setSpacing(10)
        self.job_bar=QFrame();job_layout=QHBoxLayout(self.job_bar);job_layout.setContentsMargins(0,0,0,0);self.job_status=QLabel("");self.progress=QProgressBar();self.progress.setTextVisible(True);self.pause_job_btn=QPushButton("Pause");self.cancel_job_btn=QPushButton("Cancel");self.pause_job_btn.setEnabled(False);self.cancel_job_btn.setEnabled(False);job_layout.addWidget(self.job_status);job_layout.addWidget(self.progress,1);job_layout.addWidget(self.pause_job_btn);job_layout.addWidget(self.cancel_job_btn);self.job_bar.hide();ml.addWidget(self.job_bar);self.pause_job_btn.clicked.connect(self.toggle_current_job_pause);self.cancel_job_btn.clicked.connect(self.cancel_current_job)
        self.stack=QStackedWidget();ml.addWidget(self.stack,1);outer.addWidget(main,1)
        self.pages=[]
        for builder in (self._dashboard_page,self._watchlist_page,self._corporate_monitor_page,self._visual_page,self._lineage_page,self._audit_page,self._batch_page,self._backtest_page,self._safety_page,self._monte_carlo_page,self._assumptions_page,self._financial_company_page,self._external_review_page,self._database_page,self._diagnostics_page,self._settings_page,self._method_page):
            page=builder();self.pages.append(page);self.stack.addWidget(page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex);self.nav.setCurrentRow(0);self.setStatusBar(QStatusBar())
    def _page(self,title,subtitle):
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,0,0,0);head=QLabel(title);head.setObjectName("pageTitle");sub=QLabel(subtitle);sub.setObjectName("pageSub");sub.setWordWrap(True);layout.addWidget(head);layout.addWidget(sub);layout.addSpacing(4);return page,layout
    def _dashboard_page(self):
        page,l=self._page("Stock valuation","Analyze with Yahoo Finance plus best-effort Screener.in and official NSE/BSE website verification for Indian stocks.")
        search=Card();s=QHBoxLayout(search);self.market=QComboBox();self.market.addItems(["US","NSE","BSE"]);self.symbol=QLineEdit("AAPL");self.symbol.setPlaceholderText("Ticker symbol");self.force_refresh_check=QCheckBox("Refresh sources");self.analyze_btn=QPushButton("Analyze stock");self.analyze_btn.setObjectName("primary");self.pdf_btn=QPushButton("Export full PDF");self.pdf_btn.setEnabled(False)
        s.addWidget(QLabel("Market"));s.addWidget(self.market);s.addWidget(QLabel("Company or ticker"));s.addWidget(self.symbol,1);s.addWidget(self.force_refresh_check);s.addWidget(self.analyze_btn);s.addWidget(self.pdf_btn);l.addWidget(search)
        self.search_status=QLabel("Type at least 2 characters to search by company name or ticker.");self.search_status.setObjectName("pageSub");l.addWidget(self.search_status);uncertainty=QLabel("Model estimate only • Not a Buy/Sell recommendation • A valuation buffer does not guarantee protection from loss • Verify official filings");uncertainty.setWordWrap(True);uncertainty.setStyleSheet("padding:7px 10px;background:#E7F0FF;color:#244A7C;border-radius:6px;font-weight:600;");l.addWidget(uncertainty)
        self.search_model=QStringListModel(self);self.completer=QCompleter(self.search_model,self);self.completer.setCaseSensitivity(Qt.CaseInsensitive);self.completer.setFilterMode(Qt.MatchContains);self.completer.setCompletionMode(QCompleter.PopupCompletion);self.completer.setMaxVisibleItems(10);self.completer.popup().setMinimumWidth(560);self.symbol.setCompleter(self.completer)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(350);self.search_timer.timeout.connect(self.run_stock_search);self.symbol.textEdited.connect(self.schedule_stock_search);self.market.currentTextChanged.connect(self.market_search_changed);self.completer.activated[str].connect(self.apply_search_choice)
        self.company=QLabel("No stock analyzed");self.company.setStyleSheet(f"font-size:14pt;font-weight:700;color:{NAVY};");self.company_meta=QLabel("Enter a ticker above. Exchange suffixes are added automatically.");self.company_meta.setObjectName("pageSub");l.addWidget(self.company);l.addWidget(self.company_meta)
        metrics=QHBoxLayout();self.dashboard_metrics=[MetricCard(x) for x in ("MARKET PRICE","FAIR VALUE (WEIGHTED)","UPSIDE / DOWNSIDE","VALUATION BUFFER PRICE","IMPLIED RETURN / YEAR")]
        for card in self.dashboard_metrics:
            metrics.addWidget(card)
        l.addLayout(metrics)
        split=QSplitter();tablecard=Card();tl=QVBoxLayout(tablecard);tl.addWidget(QLabel("Scenario comparison"));self.scenario_table=QTableWidget(0,8);self.scenario_table.setHorizontalHeaderLabels(["Scenario","Growth","Discount","Terminal","Primary","Graham","Live peers","Blended"]);self._setup_table(self.scenario_table);tl.addWidget(self.scenario_table);split.addWidget(tablecard)
        assessment=Card();al=QVBoxLayout(assessment);al.addWidget(QLabel("Assessment"));self.assessment=QLabel("Awaiting analysis");self.assessment.setWordWrap(True);self.assessment.setStyleSheet("padding:12px;background:#E8EEF6;border-radius:7px;font-weight:700;");self.snapshot=QLabel("Model profile, scores, peer data, and valuation buffer will appear here.");self.snapshot.setWordWrap(True);self.snapshot.setAlignment(Qt.AlignTop);al.addWidget(self.assessment);al.addWidget(self.snapshot,1);split.addWidget(assessment);split.setSizes([800,310]);l.addWidget(split,1)
        self.analyze_btn.clicked.connect(self.analyze);self.symbol.returnPressed.connect(self.analyze);self.pdf_btn.clicked.connect(self.export_pdf);return page
    def _watchlist_page(self):
        page,l=self._page("Watchlists & alerts","Track fair value, valuation-buffer entry, price targets, risk thresholds, source discrepancies, and material fair-value changes.")
        metrics=QHBoxLayout();self.watchlist_metrics=[MetricCard(x) for x in ("WATCHLIST STOCKS","UNREAD ALERTS","BELOW BUFFER","HIGH-RISK ALERTS")]
        for card in self.watchlist_metrics:metrics.addWidget(card)
        l.addLayout(metrics)
        toolbar=Card();tb=QHBoxLayout(toolbar);self.watch_market=QComboBox();self.watch_market.addItems(["US","NSE","BSE"]);self.watch_symbol=QLineEdit();self.watch_symbol.setPlaceholderText("Symbol");add_symbol=QPushButton("Add symbol");self.watch_add_current=QPushButton("Add current");self.watch_refresh=QPushButton("Refresh alerts");self.watch_refresh.setObjectName("primary");self.watch_remove=QPushButton("Remove");self.watch_mark_read=QPushButton("Mark read");self.watch_export_csv=QPushButton("CSV");self.watch_export_pdf=QPushButton("Colour PDF");tb.addWidget(self.watch_market);tb.addWidget(self.watch_symbol);tb.addWidget(add_symbol);tb.addWidget(self.watch_add_current);tb.addWidget(self.watch_refresh);tb.addWidget(self.watch_remove);tb.addWidget(self.watch_mark_read);tb.addWidget(self.watch_export_csv);tb.addWidget(self.watch_export_pdf);l.addWidget(toolbar)
        settings=Card();sg=QHBoxLayout(settings);self.watch_custom_price=QDoubleSpinBox();self.watch_custom_price.setRange(0,10000000);self.watch_custom_price.setSpecialValueText("Off");self.watch_custom_price.setDecimals(2);self.watch_min_upside=QDoubleSpinBox();self.watch_min_upside.setRange(0,1000);self.watch_min_upside.setValue(25);self.watch_min_upside.setSuffix(" %");self.watch_max_risk=QDoubleSpinBox();self.watch_max_risk.setRange(0,100);self.watch_max_risk.setValue(60);self.watch_max_governance=QDoubleSpinBox();self.watch_max_governance.setRange(0,100);self.watch_max_governance.setValue(60);self.watch_fv_change=QDoubleSpinBox();self.watch_fv_change.setRange(1,1000);self.watch_fv_change.setValue(10);self.watch_fv_change.setSuffix(" %");self.watch_mos=QCheckBox("Alert below valuation buffer");self.watch_mos.setChecked(True);self.watch_save_settings=QPushButton("Save alerts")
        for label,widget in (("Custom price",self.watch_custom_price),("Min upside",self.watch_min_upside),("Max fin risk",self.watch_max_risk),("Max gov risk",self.watch_max_governance),("FV change",self.watch_fv_change)):sg.addWidget(QLabel(label));sg.addWidget(widget)
        sg.addWidget(self.watch_mos);sg.addWidget(self.watch_save_settings);l.addWidget(settings)
        split=QSplitter(Qt.Vertical);watch_card=Card();wl=QVBoxLayout(watch_card);wl.addWidget(QLabel("Watchlist"));self.watchlist_table=QTableWidget(0,10);self.watchlist_table.setHorizontalHeaderLabels(["Symbol","Market","Company","Price","Fair value","Buffer price","Upside","Confidence","Risk","Last check / status"]);self._setup_table(self.watchlist_table);wl.addWidget(self.watchlist_table);split.addWidget(watch_card);alert_card=Card();al=QVBoxLayout(alert_card);al.addWidget(QLabel("Alert history"));self.alert_table=QTableWidget(0,6);self.alert_table.setHorizontalHeaderLabels(["Time","Severity","Symbol","Type","Message","Read"]);self._setup_table(self.alert_table);al.addWidget(self.alert_table);split.addWidget(alert_card);split.setSizes([310,220]);l.addWidget(split,1)
        add_symbol.clicked.connect(self.add_watch_symbol);self.watch_add_current.clicked.connect(self.add_current_to_watchlist);self.watch_refresh.clicked.connect(self.refresh_watchlist);self.watch_remove.clicked.connect(self.remove_watchlist_entry);self.watch_mark_read.clicked.connect(self.mark_watchlist_alerts_read);self.watch_export_csv.clicked.connect(self.export_watchlist_csv);self.watch_export_pdf.clicked.connect(self.export_watchlist_pdf);self.watch_save_settings.clicked.connect(self.save_watchlist_settings);self.watchlist_table.itemSelectionChanged.connect(self.load_watchlist_settings);self.load_watchlist();return page
    def _corporate_monitor_page(self):
        page,l=self._page("Corporate filings & actions","Monitor SEC filings, Indian company documents, BSE announcements, dividends, splits, and other corporate events.")
        metrics=QHBoxLayout();self.corporate_metrics=[MetricCard(x) for x in ("MONITORED COMPANIES","UNREAD EVENTS","REGULATORY FILINGS","CORPORATE ACTIONS")]
        for card in self.corporate_metrics:metrics.addWidget(card)
        l.addLayout(metrics)
        toolbar=Card();tb=QHBoxLayout(toolbar);self.corp_market=QComboBox();self.corp_market.addItems(["US","NSE","BSE"]);self.corp_symbol=QLineEdit();self.corp_symbol.setPlaceholderText("Symbol");corp_add=QPushButton("Add symbol");self.corp_add_current=QPushButton("Add current");self.corp_refresh=QPushButton("Refresh events");self.corp_refresh.setObjectName("primary");self.corp_remove=QPushButton("Remove");self.corp_mark_read=QPushButton("Mark read");self.corp_open=QPushButton("Open event");tb.addWidget(self.corp_market);tb.addWidget(self.corp_symbol);tb.addWidget(corp_add);tb.addWidget(self.corp_add_current);tb.addWidget(self.corp_refresh);tb.addWidget(self.corp_remove);tb.addWidget(self.corp_mark_read);tb.addWidget(self.corp_open);l.addWidget(toolbar)
        sec_card=Card();sl=QHBoxLayout(sec_card);sl.addWidget(QLabel("SEC contact email (required by EDGAR for US filings monitoring and 10-15 years of 10-K history)"));self.sec_contact_email=QLineEdit(self.secure_storage.get_secret("sec_contact_email"));self.sec_contact_email.setPlaceholderText("name@example.com");self.sec_save_email=QPushButton("Save email locally");sl.addWidget(self.sec_contact_email,1);sl.addWidget(self.sec_save_email);l.addWidget(sec_card)
        split=QSplitter(Qt.Vertical);companies=Card();cl=QVBoxLayout(companies);cl.addWidget(QLabel("Monitored companies"));self.corporate_company_table=QTableWidget(0,6);self.corporate_company_table.setHorizontalHeaderLabels(["Symbol","Market","Company","CIK","Last checked","Status"]);self._setup_table(self.corporate_company_table);cl.addWidget(self.corporate_company_table);split.addWidget(companies);events=Card();el=QVBoxLayout(events);el.addWidget(QLabel("Filings and corporate actions"));self.corporate_event_table=QTableWidget(0,7);self.corporate_event_table.setHorizontalHeaderLabels(["Date","Severity","Symbol","Type","Source","Title","Read"]);self._setup_table(self.corporate_event_table);el.addWidget(self.corporate_event_table);split.addWidget(events);split.setSizes([220,320]);l.addWidget(split,1);self.corporate_status=QLabel("Refresh is manual; the app does not run a cloud monitor while closed.");self.corporate_status.setObjectName("pageSub");l.addWidget(self.corporate_status);self.corporate_entry_ids=[];self.corporate_event_urls=[];corp_add.clicked.connect(self.add_corporate_symbol);self.corp_add_current.clicked.connect(self.add_current_to_corporate_monitor);self.corp_refresh.clicked.connect(self.refresh_corporate_monitor);self.corp_remove.clicked.connect(self.remove_corporate_entry);self.corp_mark_read.clicked.connect(self.mark_corporate_events_read);self.corp_open.clicked.connect(self.open_corporate_event);self.sec_save_email.clicked.connect(self.save_sec_email);self.corporate_company_table.itemSelectionChanged.connect(self.corporate_selection_changed);self.corporate_event_table.itemSelectionChanged.connect(self.corporate_event_selection_changed);self.corporate_event_table.doubleClicked.connect(lambda _index:self.open_corporate_event());self.load_corporate_monitor();return page
    def _visual_page(self):
        page,l=self._page("Visual analysis","Use price, model, fundamental, and scenario charts to understand why the estimate differs from the market price.")
        grid=QGridLayout();grid.setSpacing(10)
        def add_chart(row,column,title,subtitle,widget):
            card=Card();layout=QVBoxLayout(card);heading=QLabel(title);heading.setStyleSheet(f"font-weight:700;color:{NAVY};font-size:11pt;");caption=QLabel(subtitle);caption.setObjectName("pageSub");caption.setWordWrap(True);layout.addWidget(heading);layout.addWidget(caption);layout.addWidget(widget,1);grid.addWidget(card,row,column)
        self.price_value_chart=PriceValueChart();add_chart(0,0,"Price vs valuation","One-year market price with today's blended fair value and dynamic valuation-buffer price.",self.price_value_chart)
        self.model_chart=ModelBarChart();add_chart(0,1,"Model comparison","Compare each available base model, the blended estimate, and current market price.",self.model_chart)
        self.fundamental_chart=FundamentalTrendsChart();add_chart(1,0,"Fundamental trends","Revenue, net income, and free-cash-flow direction using up to five annual observations.",self.fundamental_chart)
        self.scenario_gauge=ScenarioGauge();add_chart(1,1,"Scenario range & price position","Shows where market price and valuation-buffer threshold sit relative to conservative, base, and optimistic values.",self.scenario_gauge)
        grid.setRowStretch(0,1);grid.setRowStretch(1,1);grid.setColumnStretch(0,1);grid.setColumnStretch(1,1);l.addLayout(grid,1)
        explanation=QLabel("How to read: green valuation references above market price may indicate modeled upside; red or large gaps require caution. Charts explain model outputs—they are not forecasts or trading signals.");explanation.setObjectName("pageSub");explanation.setWordWrap(True);l.addWidget(explanation);return page
    def _lineage_page(self):
        page,l=self._page("Data lineage & citations","Trace important inputs from source URL and period through normalization or selection into the valuation.")
        row=QHBoxLayout();self.lineage_metrics=[MetricCard(x) for x in ("SOURCES CHECKED","LINEAGE RECORDS","NORMALIZED / DERIVED","UNAVAILABLE")]
        for card in self.lineage_metrics:row.addWidget(card)
        l.addLayout(row)
        toolbar=Card();tb=QHBoxLayout(toolbar);self.lineage_export_btn=QPushButton("Export lineage CSV");self.lineage_open_btn=QPushButton("Open selected citation");self.lineage_export_btn.setEnabled(False);self.lineage_open_btn.setEnabled(False);tb.addWidget(self.lineage_export_btn);tb.addWidget(self.lineage_open_btn);tb.addStretch();self.lineage_summary=QLabel("Analyze a stock to build its source and transformation trail.");self.lineage_summary.setObjectName("pageSub");tb.addWidget(self.lineage_summary);l.addWidget(toolbar)
        self.lineage_table=QTableWidget(0,7);self.lineage_table.setHorizontalHeaderLabels(["Metric","Value","Source","Period","Transformation","Status","Citation"]);self.lineage_table.setAlternatingRowColors(True);self.lineage_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.lineage_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.lineage_table.verticalHeader().setVisible(False);header=self.lineage_table.horizontalHeader();header.setSectionResizeMode(0,QHeaderView.ResizeToContents);header.setSectionResizeMode(1,QHeaderView.ResizeToContents);header.setSectionResizeMode(2,QHeaderView.ResizeToContents);header.setSectionResizeMode(3,QHeaderView.ResizeToContents);header.setSectionResizeMode(4,QHeaderView.Stretch);header.setSectionResizeMode(5,QHeaderView.ResizeToContents);header.setSectionResizeMode(6,QHeaderView.ResizeToContents);l.addWidget(self.lineage_table,1)
        note=QLabel("Citation links open in the default browser. Website data can change after retrieval; the report records the retrieval timestamp and transformation used by this analysis.");note.setObjectName("pageSub");note.setWordWrap(True);l.addWidget(note);self.lineage_urls=[];self.lineage_table.itemSelectionChanged.connect(self.lineage_selection_changed);self.lineage_table.doubleClicked.connect(lambda _index:self.open_selected_citation());self.lineage_open_btn.clicked.connect(self.open_selected_citation);self.lineage_export_btn.clicked.connect(self.export_lineage_csv);return page
    def _audit_page(self):
        page,l=self._page("Model audit trail","Reproduce and verify how data, assumptions, models, scenarios, risk scores, and simulation outputs produced the final estimate.")
        row=QHBoxLayout();self.audit_metrics=[MetricCard(x) for x in ("ANALYSIS ID","MODEL VERSION","AUDIT EVENTS","INTEGRITY")]
        for card in self.audit_metrics:row.addWidget(card)
        l.addLayout(row)
        toolbar=Card();tb=QHBoxLayout(toolbar);self.audit_export_btn=QPushButton("Export audit JSON");self.audit_copy_btn=QPushButton("Copy analysis ID");self.audit_verify_btn=QPushButton("Verify audit hash");self.audit_export_btn.setEnabled(False);self.audit_copy_btn.setEnabled(False);self.audit_verify_btn.setEnabled(False);tb.addWidget(self.audit_export_btn);tb.addWidget(self.audit_copy_btn);tb.addWidget(self.audit_verify_btn);tb.addStretch();self.audit_summary=QLabel("Analyze a stock to create a versioned audit record.");self.audit_summary.setObjectName("pageSub");tb.addWidget(self.audit_summary);l.addWidget(toolbar)
        self.audit_table=QTableWidget(0,4);self.audit_table.setHorizontalHeaderLabels(["UTC timestamp","Stage","Action","Details"]);self.audit_table.setAlternatingRowColors(True);self.audit_table.setSelectionBehavior(QAbstractItemView.SelectRows);self.audit_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.audit_table.verticalHeader().setVisible(False);audit_header=self.audit_table.horizontalHeader();audit_header.setSectionResizeMode(0,QHeaderView.ResizeToContents);audit_header.setSectionResizeMode(1,QHeaderView.ResizeToContents);audit_header.setSectionResizeMode(2,QHeaderView.ResizeToContents);audit_header.setSectionResizeMode(3,QHeaderView.Stretch);l.addWidget(self.audit_table,1)
        note=QLabel("The SHA-256 audit hash covers the analysis identity, versions, data snapshot, assumptions, model/scenario outputs, peers, scores, Monte Carlo seed, final result, and ordered events. Any later mutation causes verification to fail. This is tamper-evidence, not a digital signature.");note.setObjectName("pageSub");note.setWordWrap(True);l.addWidget(note);self.audit_export_btn.clicked.connect(self.export_audit_json);self.audit_copy_btn.clicked.connect(self.copy_analysis_id);self.audit_verify_btn.clicked.connect(self.verify_current_audit);return page
    def _batch_page(self):
        page,l=self._page("Batch analysis","Import up to 100 stocks from CSV, TXT, TSV, or Excel for efficient multi-stock valuation.")
        bar=Card();b=QHBoxLayout(bar);self.import_btn=QPushButton("Import list");self.import_btn.setObjectName("primary");self.batch_run=QPushButton("Analyze list");self.batch_run.setEnabled(False);self.batch_csv=QPushButton("Export CSV");self.batch_pdf=QPushButton("Export PDF");self.batch_csv.setEnabled(False);self.batch_pdf.setEnabled(False);template=QPushButton("Save template")
        for w in (self.import_btn,self.batch_run,self.batch_csv,self.batch_pdf):
            b.addWidget(w)
        b.addStretch();b.addWidget(template);l.addWidget(bar)
        self.batch_info=QLabel("Required column: Symbol. Optional column: Market.");self.batch_info.setObjectName("pageSub");l.addWidget(self.batch_info)
        self.batch_table=QTableWidget(0,8);self.batch_table.setHorizontalHeaderLabels(["#","Symbol","Market","Status","Price","Fair value","Upside","Assessment"]);self._setup_table(self.batch_table);self.batch_table.doubleClicked.connect(self.open_batch_result);l.addWidget(self.batch_table,1)
        self.import_btn.clicked.connect(self.import_batch);self.batch_run.clicked.connect(self.analyze_batch);self.batch_csv.clicked.connect(self.export_batch_csv);self.batch_pdf.clicked.connect(self.export_batch_pdf);template.clicked.connect(self.save_template);return page
    def _backtest_page(self):
        page,l=self._page("Backtest","Re-run the model at past fiscal year-ends using data that was public at the time, then compare with the total returns that followed.")
        metrics=QHBoxLayout();self.backtest_metrics=[MetricCard(x) for x in ("OBSERVATIONS","RANK CORRELATION","DIRECTION HIT RATE","MODEL-UNDERVALUED / YR","MODEL-OVERVALUED / YR")]
        for card in self.backtest_metrics:metrics.addWidget(card)
        l.addLayout(metrics)
        bar=Card();b=QHBoxLayout(bar);self.backtest_source=QLabel("Uses the imported batch list, or the current stock when no list is imported.");self.backtest_source.setObjectName("pageSub");self.backtest_years=QSpinBox();self.backtest_years.setRange(1,10);self.backtest_years.setValue(3);self.backtest_run=QPushButton("Run backtest");self.backtest_run.setObjectName("primary");self.backtest_export=QPushButton("Export CSV");self.backtest_export.setEnabled(False);self.track_saved_btn=QPushButton("Track saved valuations");self.track_saved_btn.setToolTip("Score valuations this app saved at least 30 days ago against today's prices (no look-ahead bias)")
        b.addWidget(self.backtest_source,1);b.addWidget(QLabel("Fiscal years back"));b.addWidget(self.backtest_years);b.addWidget(self.backtest_run);b.addWidget(self.track_saved_btn);b.addWidget(self.backtest_export);l.addWidget(bar)
        self.backtest_table=QTableWidget(0,9);self.backtest_table.setHorizontalHeaderLabels(["Symbol","Fiscal year-end","As of","Price then","Fair value then","Upside then","Return since","Annualized","Below buffer"]);self._setup_table(self.backtest_table);l.addWidget(self.backtest_table,1)
        self.backtest_summary=QLabel(LOOK_AHEAD_NOTE);self.backtest_summary.setObjectName("pageSub");self.backtest_summary.setWordWrap(True);l.addWidget(self.backtest_summary)
        self.backtest_points=[];self.backtest_run.clicked.connect(self.run_backtest);self.track_saved_btn.clicked.connect(self.track_saved_valuations);self.backtest_export.clicked.connect(self.export_backtest_csv);return page
    def _safety_page(self):
        page,l=self._page("Risk, resilience & sensitivity","Review model uncertainty, reverse DCF, business quality, governance risk, and confidence before interpreting fair value.")
        row=QHBoxLayout();self.safety_metrics=[MetricCard(x) for x in ("BUSINESS QUALITY","GOVERNANCE RISK","ORDER BOOK","CONFIDENCE","REVERSE DCF","MODEL DISPERSION")]
        for c in self.safety_metrics:
            row.addWidget(c)
        l.addLayout(row)
        forensic=QHBoxLayout();self.forensic_metrics=[MetricCard(x) for x in ("PIOTROSKI F-SCORE","ALTMAN Z","BENEISH M","ROIC VS COST OF CAPITAL","CASH CONVERSION CYCLE","PROMOTER PLEDGE")]
        for c in self.forensic_metrics:
            forensic.addWidget(c)
        l.addLayout(forensic)
        split=QSplitter();card=Card();cl=QVBoxLayout(card);cl.addWidget(QLabel("Fair-value sensitivity: discount rate × terminal growth"));legend=QLabel("Green: above price  •  Amber: near price  •  Red: below price  •  Bold: base assumptions");legend.setObjectName("pageSub");cl.addWidget(legend);self.sensitivity=QTableWidget(0,6);self._setup_table(self.sensitivity);cl.addWidget(self.sensitivity);split.addWidget(card);notes=Card();nl=QVBoxLayout(notes);nl.addWidget(QLabel("Quality, governance & confidence notes"));self.safety_notes=QTextEdit();self.safety_notes.setReadOnly(True);nl.addWidget(self.safety_notes);split.addWidget(notes);split.setSizes([650,500]);l.addWidget(split,1);return page
    def _monte_carlo_page(self):
        page,l=self._page("Monte Carlo valuation","Two thousand reproducible simulations describe model uncertainty; they do not predict returns or guarantee profit.")
        row=QHBoxLayout();self.mc_metrics=[MetricCard(x) for x in ("P10 FAIR VALUE","MEDIAN FAIR VALUE","P90 FAIR VALUE","PROBABILITY > PRICE","SIMULATIONS")]
        for c in self.mc_metrics:
            row.addWidget(c)
        l.addLayout(row);card=Card();cl=QVBoxLayout(card);chart_title=QLabel("Simulated fair-value distribution");chart_title.setFixedHeight(24);cl.addWidget(chart_title);self.histogram=HistogramWidget();cl.addWidget(self.histogram,1);l.addWidget(card,1);return page
    def _assumptions_page(self):
        page,l=self._page("Assumptions review","Compare automatic sector-aware assumptions with reviewed values before recalculating the valuation.")
        toolbar=Card();tb=QHBoxLayout(toolbar);tb.addWidget(QLabel("Review preset"));self.assumption_preset=QComboBox();self.assumption_preset.addItems(["Automatic defaults","Conservative overlay","DCF emphasis","Peer balanced","Custom review"]);apply_preset=QPushButton("Apply preset");reset_btn=QPushButton("Reset unlocked");unlock_btn=QPushButton("Unlock all");tb.addWidget(self.assumption_preset);tb.addWidget(apply_preset);tb.addWidget(reset_btn);tb.addWidget(unlock_btn);tb.addStretch();l.addWidget(toolbar)
        self.assumption_review_status=QLabel("Analyze a stock to load automatic assumptions.");self.assumption_review_status.setWordWrap(True);self.assumption_review_status.setStyleSheet("padding:10px;background:#E8EEF6;border-radius:7px;font-weight:600;");l.addWidget(self.assumption_review_status)
        card=Card();layout=QVBoxLayout(card);self.assumption_table=QTableWidget(9,5);self.assumption_table.setHorizontalHeaderLabels(["Assumption","Automatic","Reviewed value","Difference","Lock"]);self.assumption_table.verticalHeader().setVisible(False);self.assumption_table.setAlternatingRowColors(True);self.assumption_table.setEditTriggers(QAbstractItemView.NoEditTriggers);self.assumption_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch);self.assumption_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents);self.assumption_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents);self.assumption_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.Stretch);self.assumption_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeToContents)
        self.assumption_defs=[("Base growth","growth",-50,50,2,"%"),("Discount rate","discount",1,50,2,"%"),("Terminal growth","terminal",0,20,2,"%"),("Forecast period","years",1,20,0," years"),("High-growth years","high_growth_years",1,15,0," years"),("Primary model weight","dcf_weight",0,100,1,"%"),("Graham/book weight","graham_weight",0,100,1,"%"),("Live-peer weight","relative_weight",0,100,1,"%"),("Minimum valuation buffer","margin",0,50,1,"%")]
        self.inputs={};self.assumption_auto_items={};self.assumption_diff_items={};self.assumption_locks={};self.auto_assumption_values={}
        for row,(label,key,mn,mx,dec,suffix) in enumerate(self.assumption_defs):
            name_item=QTableWidgetItem(label);auto_item=QTableWidgetItem("—");diff_item=QTableWidgetItem("—");self.assumption_table.setItem(row,0,name_item);self.assumption_table.setItem(row,1,auto_item);self.assumption_table.setItem(row,3,diff_item)
            widget=QSpinBox() if dec==0 else QDoubleSpinBox();widget.setRange(mn,mx);widget.setSuffix(suffix)
            if isinstance(widget,QDoubleSpinBox):widget.setDecimals(dec);widget.setSingleStep(.5)
            lock=QCheckBox("Locked");self.inputs[key]=widget;self.assumption_auto_items[key]=auto_item;self.assumption_diff_items[key]=diff_item;self.assumption_locks[key]=lock;self.assumption_table.setCellWidget(row,2,widget);self.assumption_table.setCellWidget(row,4,lock);self.assumption_table.setRowHeight(row,38);widget.valueChanged.connect(lambda _value:self.assumption_value_changed());lock.stateChanged.connect(lambda _state:self.refresh_assumption_review())
        layout.addWidget(self.assumption_table);l.addWidget(card,1)
        note_card=Card();nl=QVBoxLayout(note_card);nl.addWidget(QLabel("Reviewer note / rationale for overrides"));self.assumption_note=QTextEdit();self.assumption_note.setPlaceholderText("Optional: explain growth, discount-rate, weight, or valuation-buffer overrides. This note appears in the PDF report.");self.assumption_note.setMaximumHeight(72);self.assumption_note.textChanged.connect(self.refresh_assumption_review);nl.addWidget(self.assumption_note);l.addWidget(note_card)
        actions=QHBoxLayout();self.review_recalc_btn=QPushButton("Accept reviewed assumptions and recalculate");self.review_recalc_btn.setObjectName("primary");self.review_recalc_btn.setEnabled(False);self.override_summary=QLabel("No review loaded");self.override_summary.setObjectName("pageSub");actions.addWidget(self.review_recalc_btn);actions.addWidget(self.override_summary);actions.addStretch();l.addLayout(actions)
        apply_preset.clicked.connect(self.apply_assumption_preset);reset_btn.clicked.connect(self.reset_unlocked_assumptions);unlock_btn.clicked.connect(self.unlock_all_assumptions);self.review_recalc_btn.clicked.connect(self.recalculate);return page
    def _financial_company_page(self):
        page,l=self._page("Specialized financial-company data","Review bank, NBFC, lender, and insurer metrics that ordinary-company debt and cash-flow ratios cannot represent correctly.")
        self.financial_status=QLabel("Analyze a financial company to load available specialized metrics.");self.financial_status.setWordWrap(True);self.financial_status.setStyleSheet("padding:10px;background:#E8EEF6;border-radius:7px;font-weight:600;");l.addWidget(self.financial_status)
        card=Card();layout=QVBoxLayout(card);self.financial_table=QTableWidget(19,4);self.financial_table.setHorizontalHeaderLabels(["Specialized metric","Automatic / public","Reviewed value","Interpretation"]);self.financial_table.verticalHeader().setVisible(False);self.financial_table.setAlternatingRowColors(True);self.financial_table.setEditTriggers(QAbstractItemView.NoEditTriggers);fh=self.financial_table.horizontalHeader();fh.setSectionResizeMode(0,QHeaderView.ResizeToContents);fh.setSectionResizeMode(1,QHeaderView.ResizeToContents);fh.setSectionResizeMode(2,QHeaderView.ResizeToContents);fh.setSectionResizeMode(3,QHeaderView.Stretch)
        self.financial_defs=[("Reviewed ROE","reviewed_roe","percent",100,"ROE used by justified P/B and quality scoring"),("Net interest margin","net_interest_margin","percent",100,"Bank NIM; enter from official results"),("Financing margin","financing_margin","percent",100,"Public financing-margin series; may differ from NIM"),("Gross NPA","gross_npa","percent",100,"Gross non-performing assets / advances"),("Net NPA","net_npa","percent",100,"Net non-performing assets / advances"),("Capital adequacy","capital_adequacy","percent",100,"Regulatory capital adequacy ratio"),("CET1 ratio","cet1_ratio","percent",100,"Common Equity Tier 1 ratio"),("Provision coverage","provision_coverage","percent",100,"Provisions relative to stressed assets"),("CASA ratio","casa_ratio","percent",100,"Current and savings deposits / deposits"),("Credit cost","credit_cost","percent",100,"Annualized credit cost"),("Deposit growth","deposit_growth","percent",200,"Latest annual deposit growth"),("Loan growth","loan_growth","percent",200,"Latest annual loan/advance growth"),("Cost-to-income","cost_to_income","percent",200,"Operating efficiency; public value may be a proxy"),("Equity-to-assets proxy","equity_to_assets","percent",100,"Book equity / assets; not regulatory capital"),("Solvency ratio","solvency_ratio","multiple",10,"Insurer solvency ratio"),("Embedded value / share","embedded_value_per_share","money",1000000,"Insurer embedded value per share"),("Fair P/EV multiple","fair_price_to_embedded_value","multiple",10,"Reviewed fair price-to-embedded-value multiple"),("VNB margin","vnb_margin","percent",100,"Value of new business margin"),("Premium growth","premium_growth","percent",200,"Latest premium/revenue growth proxy")]
        self.financial_inputs={};self.financial_auto_items={};self._loading_financial_inputs=False
        for row,(label,key,kind,maximum,help_text) in enumerate(self.financial_defs):
            self.financial_table.setItem(row,0,QTableWidgetItem(label));auto_item=QTableWidgetItem("—");self.financial_table.setItem(row,1,auto_item);self.financial_auto_items[key]=auto_item;spin=QDoubleSpinBox();spin.setRange(-999,maximum);spin.setDecimals(2);spin.setSingleStep(.1);spin.setSpecialValueText("Not set")
            if kind=="percent":spin.setSuffix(" %")
            elif kind=="multiple":spin.setSuffix(" x")
            self.financial_inputs[key]=spin;self.financial_table.setCellWidget(row,2,spin);info=QTableWidgetItem(help_text);info.setToolTip(help_text);self.financial_table.setItem(row,3,info);self.financial_table.setRowHeight(row,36);spin.valueChanged.connect(lambda _value:self.financial_value_changed())
        layout.addWidget(self.financial_table);l.addWidget(card,1)
        note_card=Card();nl=QVBoxLayout(note_card);nl.addWidget(QLabel("Specialized data note / official filing reference"));self.financial_note=QTextEdit();self.financial_note.setMaximumHeight(65);self.financial_note.setPlaceholderText("Example: Gross/Net NPA and capital adequacy from FY2026 Q1 investor presentation, page 18.");self.financial_note.textChanged.connect(self.financial_value_changed);nl.addWidget(self.financial_note);l.addWidget(note_card)
        actions=QHBoxLayout();self.financial_apply_btn=QPushButton("Apply specialized data and recalculate");self.financial_apply_btn.setObjectName("primary");self.financial_apply_btn.setEnabled(False);self.financial_reset_btn=QPushButton("Reset to public values");actions.addWidget(self.financial_apply_btn);actions.addWidget(self.financial_reset_btn);actions.addStretch();l.addLayout(actions);self.financial_apply_btn.clicked.connect(self.apply_financial_company_data);self.financial_reset_btn.clicked.connect(self.reset_financial_company_data);return page
    def _external_review_page(self):
        page,l=self._page("External data review","Safely compare manually reviewed Moneycontrol or official-filing values without automated scraping or bypassing website controls.")
        toolbar=Card();tb=QGridLayout(toolbar);self.external_source=QComboBox();self.external_source.addItems(["Moneycontrol (manual review)","Official company filing","NSE/BSE filing","Other cited source"]);self.external_url=QLineEdit();self.external_url.setPlaceholderText("Paste the exact page or filing URL");self.external_period=QLineEdit();self.external_period.setPlaceholderText("Example: FY2026 or Q1 FY2027");self.external_find_btn=QPushButton("Find on Moneycontrol");tb.addWidget(QLabel("Source"),0,0);tb.addWidget(self.external_source,0,1);tb.addWidget(QLabel("Period"),0,2);tb.addWidget(self.external_period,0,3);tb.addWidget(QLabel("Citation URL"),1,0);tb.addWidget(self.external_url,1,1,1,3);tb.addWidget(self.external_find_btn,0,4,2,1);l.addWidget(toolbar)
        self.external_status=QLabel("Analyze an Indian stock, then enter only values you have verified on the cited page.");self.external_status.setWordWrap(True);self.external_status.setStyleSheet("padding:10px;background:#E8EEF6;border-radius:7px;font-weight:600;");l.addWidget(self.external_status)
        card=Card();cl=QVBoxLayout(card);self.external_table=QTableWidget(13,4);self.external_table.setHorizontalHeaderLabels(["Metric","Current app value","Reviewed value","Use in valuation"]);self.external_table.verticalHeader().setVisible(False);self.external_table.setAlternatingRowColors(True);self.external_table.setEditTriggers(QAbstractItemView.NoEditTriggers);eh=self.external_table.horizontalHeader();eh.setSectionResizeMode(0,QHeaderView.Stretch);eh.setSectionResizeMode(1,QHeaderView.ResizeToContents);eh.setSectionResizeMode(2,QHeaderView.ResizeToContents);eh.setSectionResizeMode(3,QHeaderView.Stretch)
        self.external_defs=[("Market price","market_price","money","Comparison only; official exchange price remains preferred"),("Trailing P/E","trailing_pe","multiple","Updates displayed valuation ratio"),("Book value / share","book_value_per_share","money","Updates asset, justified P/B and peer P/B models"),("ROE","return_on_equity","percent","Updates financial-company quality and justified P/B"),("Market capitalization","market_cap","money","Updates company snapshot and share-count cross-check"),("Latest revenue","revenue","money","Rescales the DCF revenue base and latest-year margin"),("Latest net profit","net_income","money","Updates reviewed EPS when shares are available"),("Latest free cash flow","free_cash_flow","money","Updates risk scores and the equity-FCF fallback; the FCFF DCF derives cash flow from operating profit, depreciation and capex"),("Verified order book","order_book","money","Outstanding executable orders; adjusts growth cautiously after comparison with annual revenue"),("Current promoter holding","promoter_current","percent","Latest promoter holding; used with the three-year comparison in governance risk"),("Promoter holding 3 years ago","promoter_three_year","percent","Historical promoter holding; verify dilution and corporate actions"),("Promoter pledge (% of promoter holding)","promoter_pledge","percent","Pledged share of promoter holding; above 10% and 25% raises governance risk"),("Listed investments (market value)","listed_investments","money","Sum of the parts: market value of listed holdings, credited after the holding-company discount")];self.external_inputs={};self.external_current_items={};self._loading_external=False
        for row,(label,key,kind,help_text) in enumerate(self.external_defs):
            self.external_table.setItem(row,0,QTableWidgetItem(label));current=QTableWidgetItem("—");self.external_table.setItem(row,1,current);self.external_current_items[key]=current;spin=QDoubleSpinBox();spin.setRange(-999,1_000_000_000_000_000);spin.setDecimals(4 if kind=="multiple" else 2);spin.setSpecialValueText("Not set");spin.setSingleStep(.1);spin.setSuffix(" %" if kind=="percent" else " x" if kind=="multiple" else "");self.external_inputs[key]=spin;self.external_table.setCellWidget(row,2,spin);info=QTableWidgetItem(help_text);info.setToolTip(help_text);self.external_table.setItem(row,3,info);self.external_table.setRowHeight(row,38);spin.valueChanged.connect(lambda _value:self.external_value_changed())
        cl.addWidget(self.external_table);l.addWidget(card,1);actions=QHBoxLayout();self.external_apply_btn=QPushButton("Apply cited values and recalculate");self.external_apply_btn.setObjectName("primary");self.external_apply_btn.setEnabled(False);self.external_reset_btn=QPushButton("Reset reviewed values");actions.addWidget(self.external_apply_btn);actions.addWidget(self.external_reset_btn);actions.addStretch();l.addLayout(actions);self.external_find_btn.clicked.connect(self.open_moneycontrol_search);self.external_apply_btn.clicked.connect(self.apply_external_review);self.external_reset_btn.clicked.connect(self.reset_external_review);self.external_url.textChanged.connect(self.external_value_changed);self.external_period.textChanged.connect(self.external_value_changed);return page
    def _database_page(self):
        page,l=self._page("Local database & cache","Use cached stock snapshots for faster repeat analysis, stale-data fallback during outages, and local valuation-history retention.")
        metrics=QHBoxLayout();self.database_metrics=[MetricCard(x) for x in ("CACHED STOCKS","STALE ENTRIES","VALUATION HISTORY","DATABASE SIZE")]
        for card in self.database_metrics:metrics.addWidget(card)
        l.addLayout(metrics)
        settings=Card();sl=QHBoxLayout(settings);sl.addWidget(QLabel("Cache lifetime"));self.cache_ttl=QDoubleSpinBox();self.cache_ttl.setRange(.5,168);self.cache_ttl.setSuffix(" hours");self.cache_ttl.setValue(self.local_database.cache_ttl_hours());self.cache_stale=QCheckBox("Stale fallback");self.cache_stale.setChecked(self.local_database.allow_stale_fallback());self.parallel_workers=QSpinBox();self.parallel_workers.setRange(1,6);self.parallel_workers.setValue(int(self.local_database.setting("parallel_workers",3)));save=QPushButton("Save");refresh=QPushButton("Refresh");expired=QPushButton("Clear expired");clear_cache=QPushButton("Clear cache");clear_history=QPushButton("Clear history");open_folder=QPushButton("Open folder");self.history_export_btn=QPushButton("Export audit");self.history_export_btn.setEnabled(False);self.recover_job_btn=QPushButton("Recover job");self.recover_job_btn.setEnabled(False);sl.addWidget(self.cache_ttl);sl.addWidget(self.cache_stale);sl.addWidget(QLabel("Workers"));sl.addWidget(self.parallel_workers);sl.addWidget(save);sl.addWidget(refresh);sl.addWidget(expired);sl.addWidget(clear_cache);sl.addWidget(clear_history);sl.addWidget(open_folder);sl.addWidget(self.history_export_btn);sl.addWidget(self.recover_job_btn);l.addWidget(settings)
        split=QSplitter(Qt.Vertical);cache_card=Card();cl=QVBoxLayout(cache_card);cl.addWidget(QLabel("Cached stock snapshots"));self.cache_table=QTableWidget(0,7);self.cache_table.setHorizontalHeaderLabels(["Symbol","Market","Age","Freshness","Source updated","Provider","Payload"]);self._setup_table(self.cache_table);cl.addWidget(self.cache_table);split.addWidget(cache_card);history_card=Card();hl=QVBoxLayout(history_card);hl.addWidget(QLabel("Valuation history (latest 1,000 analyses)"));self.history_table=QTableWidget(0,9);self.history_table.setHorizontalHeaderLabels(["Created","Symbol","Company","Price","Fair value","Upside","Confidence","Model","Analysis ID"]);self._setup_table(self.history_table);hl.addWidget(self.history_table);split.addWidget(history_card);split.setSizes([240,260]);l.addWidget(split,1);self.database_status=QLabel(str(self.local_database.path));self.database_status.setObjectName("pageSub");l.addWidget(self.database_status);self.history_ids=[];save.clicked.connect(self.save_cache_settings);refresh.clicked.connect(self.load_database_page);expired.clicked.connect(self.clear_expired_cache);clear_cache.clicked.connect(self.clear_stock_cache);clear_history.clicked.connect(self.clear_valuation_history);open_folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.local_database.path.parent))));self.history_export_btn.clicked.connect(self.export_historical_audit);self.recover_job_btn.clicked.connect(self.recover_last_background_job);self.history_table.itemSelectionChanged.connect(self.history_selection_changed);self.load_database_page();return page
    def _diagnostics_page(self):
        page,l=self._page("Error monitoring & diagnostics","Review sanitized local errors, test providers and databases, optimize SQLite, and export a support ZIP without watchlist data or credentials.")
        metrics=QHBoxLayout();self.diagnostic_metrics=[MetricCard(x) for x in ("RECORDED ERRORS","LAST ERROR","PROVIDER HEALTH","DATABASE HEALTH")]
        for card in self.diagnostic_metrics:metrics.addWidget(card)
        l.addLayout(metrics);toolbar=Card();tb=QHBoxLayout(toolbar);run_health=QPushButton("Run health checks");run_health.setObjectName("primary");check_db=QPushButton("Check databases");optimize=QPushButton("Optimize databases");export=QPushButton("Export diagnostic ZIP");copy_error=QPushButton("Copy last error");clear=QPushButton("Clear logs");open_logs=QPushButton("Open log folder");tb.addWidget(run_health);tb.addWidget(check_db);tb.addWidget(optimize);tb.addWidget(export);tb.addWidget(copy_error);tb.addWidget(clear);tb.addWidget(open_logs);tb.addStretch();l.addWidget(toolbar);self.diagnostic_status=QLabel("Diagnostics are local and sanitized. Watchlists, valuation payloads, databases, SEC email, and credentials are excluded from support ZIPs.");self.diagnostic_status.setObjectName("pageSub");self.diagnostic_status.setWordWrap(True);l.addWidget(self.diagnostic_status);self.diagnostic_table=QTableWidget(0,5);self.diagnostic_table.setHorizontalHeaderLabels(["UTC time","Level","Component","Message","Details"]);self._setup_table(self.diagnostic_table);l.addWidget(self.diagnostic_table,1);self.last_provider_health={};self.last_database_health={};run_health.clicked.connect(self.run_diagnostic_health);check_db.clicked.connect(self.check_diagnostic_databases);optimize.clicked.connect(self.optimize_diagnostic_databases);export.clicked.connect(self.export_diagnostic_zip);copy_error.clicked.connect(lambda:QApplication.clipboard().setText(self.diagnostics.last_error));clear.clicked.connect(self.clear_diagnostic_logs);open_logs.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.diagnostics.root))));self.load_diagnostics();return page
    def _settings_page(self):
        page,l=self._page("Free data source","Yahoo Finance is the primary feed. Indian stocks are cross-checked against Screener.in and NSE/BSE public website endpoints. No API key is required.")
        card=Card();form=QVBoxLayout(card)
        title=QLabel("Yahoo + Screener.in + NSE/BSE + manual Moneycontrol review");title.setStyleSheet(f"font-size:15pt;font-weight:700;color:{NAVY};");form.addWidget(title)
        status=QLabel("● Ready — Yahoo primary; Screener/NSE/BSE checks and cited external review enabled");status.setStyleSheet(f"color:{GREEN};font-weight:700;padding:8px 0;");form.addWidget(status)
        for text in ("Coverage: Yahoo Finance for US/NSE/BSE; Screener.in ratios plus NSE or BSE website quotes for Indian stocks when accessible.","Data used: Yahoo statements/history/peers; Screener.in ratios and public financial tables (including financing margin, deposits, borrowings and assets where available); NSE/BSE official-site last price.","Moneycontrol is supported through user-cited manual review, not automated scraping. Website endpoints are best-effort and may block access; availability and field definitions can change.","Coverage fallback: when positive FCF/EPS is unavailable, the app can use bounded revenue, asset/book, net-cash, and peer P/B methods with low confidence and at least a 35% valuation buffer. It never guarantees coverage where no usable public inputs exist. Always verify official filings."):
            label=QLabel(text);label.setWordWrap(True);label.setObjectName("pageSub");form.addWidget(label)
        l.addWidget(card);privacy=Card();pl=QVBoxLayout(privacy);heading=QLabel("Privacy and secure storage");heading.setStyleSheet(f"font-size:13pt;font-weight:700;color:{NAVY};");pl.addWidget(heading);self.privacy_checkbox=QCheckBox("Privacy mode — mask watchlist prices, fair values, risk values, and alert details on screen");self.privacy_checkbox.setChecked(self.privacy_mode);save_privacy=QPushButton("Save privacy setting");self.privacy_status=QLabel(f"Secrets backend: {self.secure_storage.backend} • database/log files use restrictive local permissions");self.privacy_status.setObjectName("pageSub");self.privacy_status.setWordWrap(True);pl.addWidget(self.privacy_checkbox);pl.addWidget(save_privacy,0,Qt.AlignLeft);pl.addWidget(self.privacy_status);save_privacy.clicked.connect(self.save_privacy_setting);l.addWidget(privacy)
        valuation=Card();vl=QGridLayout(valuation);title=QLabel("Valuation parameters");title.setStyleSheet(f"font-size:13pt;font-weight:700;color:{NAVY};");vl.addWidget(title,0,0,1,6);settings=valuation_settings(self.local_database)
        def percent(value,maximum,decimals=2):
            spin=QDoubleSpinBox();spin.setRange(0,maximum);spin.setDecimals(decimals);spin.setSingleStep(.1 if decimals else 5);spin.setSuffix(" %");spin.setValue(float(value)*100);return spin
        self.setting_live_rf=QCheckBox("Use the live US 10-year Treasury yield (^TNX); the value below is the fallback");self.setting_live_rf.setChecked(bool(settings["live_us_risk_free"]))
        self.setting_damodaran=QCheckBox("Use Damodaran's country-risk equity premiums (yield less sovereign default spread); premiums below are the fallback");self.setting_damodaran.setChecked(bool(settings["damodaran_erp"]))
        self.setting_rf_us=percent(settings["risk_free_us"],20);self.setting_rf_india=percent(settings["risk_free_india"],20);self.setting_erp_us=percent(settings["erp_us"],15);self.setting_erp_india=percent(settings["erp_india"],15);self.setting_holding=percent(settings["holding_discount"],90,0)
        weights=list(settings["scenario_weights"] or MARKET_PARAMETER_DEFAULTS["scenario_weights"])[:3];self.setting_weights=[percent(weight,100,0) for weight in weights]
        vl.addWidget(self.setting_live_rf,1,0,1,3);vl.addWidget(self.setting_damodaran,1,3,1,3)
        for index,(label,widget) in enumerate((("US risk-free rate",self.setting_rf_us),("India 10-year yield",self.setting_rf_india),("Holding-company discount",self.setting_holding),("US equity risk premium",self.setting_erp_us),("India equity risk premium",self.setting_erp_india))):vl.addWidget(QLabel(label),2+index//3,(index%3)*2);vl.addWidget(widget,2+index//3,(index%3)*2+1)
        vl.addWidget(QLabel("Scenario weights"),4,0)
        for index,(label,widget) in enumerate(zip(("Conservative","Base","Optimistic"),self.setting_weights)):widget.setPrefix(label+" ");vl.addWidget(widget,4,1+index)
        save_valuation=QPushButton("Save valuation parameters");self.valuation_settings_status=QLabel("Applied to the next analysis or refresh; each report and audit record keeps the values it used.");self.valuation_settings_status.setObjectName("pageSub");self.valuation_settings_status.setWordWrap(True);vl.addWidget(save_valuation,5,0,1,2);vl.addWidget(self.valuation_settings_status,5,2,1,4);save_valuation.clicked.connect(self.save_valuation_settings)
        l.addWidget(valuation);l.addStretch();return page
    def _method_page(self):
        page,l=self._page("Methodology & limitations","Transparent model rules and safeguards used by the application.")
        text=QTextEdit();text.setReadOnly(True);text.setHtml("""<h2>Professional valuation workflow</h2><p><b>Free data:</b> Yahoo Finance is primary; Screener.in and NSE/BSE public website endpoints provide best-effort Indian-market cross-checks. No API key is required.</p><h3>Valuation</h3><ul><li>Margin-based normalization: latest revenue × median multi-year margin, with stock-based compensation deducted; Indian margins blend 10-year Screener.in history, level-matched to Yahoo</li><li>Cost of capital: government bond yield less its sovereign default spread + 5-year regression beta × Damodaran's country-risk equity premium + company-specific premium; debt costs the full government yield plus a synthetic-rating spread from interest coverage, blended into WACC</li><li>R&amp;D is treated as investment amortized over five years; terminal growth is capped at the risk-free rate (halved for shrinking revenue) and initial growth ceilings tighten for very large companies</li><li>Utilities use a dividend discount model; loss-makers use growth-adjusted peer EV/Sales; REITs add their own price/FFO history; peer P/E and P/B are fitted to growth and ROE across peers when five or more peers allow it</li><li>FCFF DCF at WACC with an equity bridge (net debt, minority interest, cash, and investments); the high-growth stage lasts 3–10 years depending on how consistently ROIC beat the cost of capital, and terminal value deducts the reinvestment needed for terminal growth</li><li>Earnings power value (zero-growth value) as the secondary model; residual income and justified P/B for financial institutions</li><li>Relative value from peer P/E, forward P/E, EV/EBITDA (growth- and ROE-adjusted) blended 60/40 with the stock's own 5-year valuation history</li><li>Initial growth blends historical trend, analyst consensus, and reinvestment × ROIC; fair value is probability-weighted across conservative, base, and optimistic scenarios</li><li>Loss-making companies use a revenue DCF with margins converging to a sector target; cyclicals use mid-cycle margins; holding companies credit listed investments after a holding discount</li><li>Piotroski F, Altman Z, Beneish M, ROIC/ROCE history, margin stability, cash conversion cycle, owner earnings, capital allocation, promoter pledge, and FII/DII trend feed the risk, quality, and governance scores</li><li>Point-in-time backtest of past fiscal year-ends against subsequent total returns (up to 10 years back for US stocks with SEC history)</li><li>US listings add up to 15 years of official SEC EDGAR 10-K figures (with a saved SEC contact email) for mid-cycle margins, ROCE consistency, tax and payout history, and a fallback when Yahoo statements fail</li><li>Sector-specific profiles, dynamic valuation buffer, and three scenarios</li><li>Assumption review with automatic-versus-reviewed comparison, presets, locks, notes, validation, and PDF override disclosure</li><li>Versioned model audit trail with unique analysis ID, parent chain, Monte Carlo seed, ordered events, JSON export, and SHA-256 integrity verification</li><li>Specialized bank/NBFC/insurer metrics with residual income, justified P/B, embedded-value support, and regulatory-risk review</li><li>User-cited Moneycontrol or official-filing review without automated scraping; accepted values create lineage and child audit records</li></ul><h3>Risk analytics</h3><ul><li>Financial risk, data quality, business quality, governance risk, order-book coverage, promoter-holding trend, and confidence</li><li>Governance risk contributes to the automatic discount rate; verified order-book coverage cautiously adjusts growth, and promoter trend contributes to governance risk</li><li>Price/valuation, model comparison, fundamental trend, scenario range, and heatmap charts</li><li>Reverse DCF and 5×5 sensitivity matrix</li><li>2,000-run Monte Carlo valuation</li><li>Persistent local watchlists with valuation-buffer, custom price, upside, risk, governance, discrepancy, confidence, and fair-value-change alerts</li><li>Corporate monitoring for SEC filings, Indian announcements/documents, dividends, splits, and source-linked event history</li><li>Local SQLite stock cache, configurable TTL, stale-network fallback, and versioned valuation audit history</li><li>Bounded parallel background jobs with retry/backoff, pause/resume/cancel, partial persistence, and interrupted-job recovery</li><li>Sanitized local error monitoring, provider/database diagnostics, SQLite maintenance, and privacy-safe support ZIP export</li><li>OS-keychain/Fernet secret protection, restrictive local permissions, watchlist privacy masking, and symbol-redacted diagnostic exports</li><li>Professional PDF cover, executive summary, contents/bookmarks, vector charts, audit trail, and clickable lineage citations</li></ul><h3>Important limitation</h3><p>No model makes investing safe or guarantees returns. Provider data and automated classifications can be incomplete or wrong. Verify official SEC/NSE/BSE filings and consult an appropriately registered professional.</p>""");l.addWidget(text,1);return page
    def _setup_table(self,table):
        table.setAlternatingRowColors(True);table.setSelectionBehavior(QAbstractItemView.SelectRows);table.setEditTriggers(QAbstractItemView.NoEditTriggers);table.verticalHeader().setVisible(False);table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    def _set_row(self,table,row,values):
        if row>=table.rowCount():table.insertRow(row)
        for col,value in enumerate(values):
            item=QTableWidgetItem(str(value));item.setTextAlignment(Qt.AlignRight|Qt.AlignVCenter if col>0 else Qt.AlignLeft|Qt.AlignVCenter);table.setItem(row,col,item)
    def busy(self,on:bool,message="",total=None,controllable=False):
        if on:
            self.job_bar.setVisible(True);self.progress.setVisible(True);self.job_status.setText(message)
            if total:self.progress.setRange(0,total);self.progress.setValue(0);self.progress.setFormat("0 / %m")
            else:self.progress.setRange(0,0);self.progress.setFormat("")
            self.pause_job_btn.setEnabled(controllable);self.cancel_job_btn.setEnabled(controllable);self.pause_job_btn.setText("Pause")
        else:
            self.progress.setRange(0,100);self.progress.setValue(0);self.progress.reset();self.progress.setVisible(False);self.job_bar.setVisible(False);self.pause_job_btn.setEnabled(False);self.cancel_job_btn.setEnabled(False);self.current_control_worker=None
        self.analyze_btn.setEnabled(not on);self.batch_run.setEnabled(not on and bool(self.batch_items));self.import_btn.setEnabled(not on)
        if hasattr(self,"backtest_run"):self.backtest_run.setEnabled(not on);self.track_saved_btn.setEnabled(not on)
        if hasattr(self,"watch_refresh"):self.watch_refresh.setEnabled(not on and bool(self.watchlist_store.entries()));self.watch_add_current.setEnabled(not on)
        if hasattr(self,"corp_refresh"):self.corp_refresh.setEnabled(not on and bool(self.corporate_store.entries()));self.corp_add_current.setEnabled(not on)
        self.pdf_btn.setEnabled(not on and self.result is not None and not getattr(self,"_assumption_changes_pending",False) and not getattr(self,"_financial_changes_pending",False) and not getattr(self,"_external_changes_pending",False))
        if message:self.statusBar().showMessage(message)
    def launch_worker(self,worker):
        self._active_workers.append(worker);worker.signals.finished.connect(lambda w=worker:self.worker_finished(w));self.pool.start(worker)
    def launch_controlled_worker(self,worker,message,total):
        self.current_control_worker=worker;self.busy(True,message,total,True);worker.signals.status.connect(self.job_status.setText);self.launch_worker(worker)
    def update_controlled_progress(self,payload):
        completed,total=payload[3],payload[4];self.progress.setMaximum(total);self.progress.setValue(completed);self.progress.setFormat(f"{completed} / {total}");attempts=payload[5]
        if attempts>1:self.job_status.setText(f"Running • retry succeeded/failed after {attempts} attempts")
    def toggle_current_job_pause(self):
        worker=self.current_control_worker
        if not worker:return
        if worker.control.paused:worker.resume();self.pause_job_btn.setText("Pause")
        else:worker.pause();self.pause_job_btn.setText("Resume")
    def cancel_current_job(self):
        if self.current_control_worker:self.current_control_worker.cancel();self.cancel_job_btn.setEnabled(False)
    def worker_finished(self,worker):
        if worker in self._active_workers:self._active_workers.remove(worker)
        if not self._active_workers:self.busy(False)
    def job_running(self):
        # Pause/Cancel track a single job, so a second one (Enter key, Recover, health check) must not start.
        if self._active_workers:self.statusBar().showMessage("Another job is running • wait for it to finish or cancel it first")
        return bool(self._active_workers)
    def schedule_stock_search(self,text):
        if self._suppress_search:return
        self._search_generation+=1;query=text.strip()
        if len(query)<2:
            self.search_timer.stop();self.search_model.setStringList([]);self._search_results={};self.search_status.setText("Type at least 2 characters to search by company name or ticker.");return
        self.search_status.setText("Waiting to search…");self.search_timer.start()
    def market_search_changed(self):
        if len(self.symbol.text().strip())>=2:self.schedule_stock_search(self.symbol.text())
    def run_stock_search(self):
        query=self.symbol.text().strip();market=self.market.currentText();generation=self._search_generation
        if len(query)<2:return
        self.search_status.setText(f"Searching {market} companies…")
        worker=Worker(search_stocks,query,market,10);self._search_workers.append(worker)
        worker.signals.result.connect(lambda results,g=generation,q=query:self.apply_search_results(results,g,q))
        worker.signals.error.connect(lambda _error,g=generation:self.search_failed(g))
        worker.signals.finished.connect(lambda w=worker:self.search_worker_finished(w));self.pool.start(worker)
    def apply_search_results(self,results,generation,query):
        if generation!=self._search_generation:return
        self._search_results={result.display:result for result in results};items=list(self._search_results)
        self.search_model.setStringList(items)
        if items:
            self.search_status.setText(f"{len(items)} match{'es' if len(items)!=1 else ''} found • ↑/↓ to choose, Enter to select")
            self.completer.setCompletionPrefix(query);self.completer.complete()
        else:self.search_status.setText("No matches found. You can still enter an exact ticker.")
    def search_failed(self,generation):
        if generation==self._search_generation:self.search_status.setText("Search is temporarily unavailable. Enter an exact ticker to continue.")
    def search_worker_finished(self,worker):
        if worker in self._search_workers:self._search_workers.remove(worker)
    def apply_search_choice(self,display):
        result=self._search_results.get(display)
        if not result:return
        self._search_generation+=1;self.search_timer.stop();self._suppress_search=True;self.symbol.setText(result.symbol);self._suppress_search=False
        if self.completer.popup():self.completer.popup().hide()
        self.search_status.setText(f"Selected {result.company} • {result.exchange} • Source: {result.source}")
        self.company.setText(f"{result.company}  ·  {result.symbol}");self.company_meta.setText(f"Search selection • {result.market} • {result.exchange}")
    def analyze(self):
        if self.job_running():return
        self.search_timer.stop()
        if self.completer.popup():self.completer.popup().hide()
        item=BatchItem(self.symbol.text(),self.market.currentText());worker=BatchWorker([item],self.local_database,"single",1,self.force_refresh_check.isChecked());worker.signals.progress.connect(self.update_controlled_progress);worker.signals.result.connect(self.single_records_done);worker.signals.error.connect(self.show_error);self.launch_controlled_worker(worker,"Retrieving data and calculating valuation…",1)
    def single_records_done(self,records):
        _item,result,error=records[0]
        if result:self.analysis_done(result)
        elif error!="Cancelled":self.show_error(error)
    def analysis_done(self,result):
        self.force_refresh_check.setChecked(False);self.result=result;self.render_result();self.load_assumptions(result,reset_values=True);self.load_financial_company(result,reset_values=True);self.load_external_review(result,reset_values=True);self.pdf_btn.setEnabled(True);self.statusBar().showMessage(f"Completed • {result.data.symbol} • Review automatic assumptions before applying overrides")
    def show_error(self,message):
        self.diagnostics.error("Application",message)
        if hasattr(self,"diagnostic_table"):self.load_diagnostics()
        AccessibleMessageDialog.critical(self,"Operation failed",message);self.statusBar().showMessage("Operation failed")
    def render_result(self):
        r=self.result;d=r.data;self.company.setText(f"{d.company}  ·  {d.symbol}");self.company_meta.setText(f"{d.market} • {d.sector} • {d.industry} • {d.currency} • {d.data_provider} data")
        vals=[money(d.price,d.currency),money(r.fair_value,d.currency),f"{r.upside_pct:+.1f}%",money(r.margin_price,d.currency)]
        for card,value in zip(self.dashboard_metrics,vals):card.set_value(value,GREEN if card==self.dashboard_metrics[2] and r.upside_pct>=0 else RED if card==self.dashboard_metrics[2] else None)
        required=(r.cost_of_capital or {}).get("cost_of_equity")
        if r.implied_return is None:self.dashboard_metrics[4].set_value("—")
        else:self.dashboard_metrics[4].set_value(f"{r.implied_return:.1%}"+(f" vs {required:.1%}" if required else ""),GREEN if required is None or r.implied_return>=required else RED)
        self.dashboard_metrics[4].setToolTip(r.implied_return_note)
        self.scenario_table.setRowCount(0);headers=["Scenario","Growth","Discount","Terminal",r.model_labels.get("dcf","Primary"),r.model_labels.get("graham","Graham"),r.model_labels.get("relative","Peers"),"Blended"];self.scenario_table.setHorizontalHeaderLabels(headers)
        weights=dict(zip(("Conservative","Base","Optimistic"),r.scenario_weights or [.25,.5,.25]))
        for i,s in enumerate(r.scenarios.values()):self._set_row(self.scenario_table,i,[f"{s.name} ({weights.get(s.name,0):.0%})",f"{s.growth:.1%}",f"{s.discount_rate:.1%}",f"{s.terminal_growth:.1%}",money(s.dcf,d.currency),money(s.graham,d.currency),money(s.relative,d.currency),money(s.fair_value,d.currency)])
        self.assessment.setText(r.label);self.assessment.setStyleSheet(f"padding:12px;background:{'#E4F5EE' if r.upside_pct>=0 else '#FBE9E7'};color:{GREEN if r.upside_pct>=0 else RED};border-radius:7px;font-weight:700;")
        capital=r.cost_of_capital or {};rate_name="Cost of equity" if r.methodology_profile=="Financial institution" else "WACC"
        self.snapshot.setText(f"Profile: {r.methodology_profile}\nFair value: probability-weighted (base case {money(r.base_fair_value,d.currency)})\n{rate_name}: {capital.get('wacc',r.base_assumptions.discount_rate):.2%} • beta {capital.get('beta',1):.2f} • risk-free {capital.get('risk_free_rate',0):.2%}\nHigh-growth stage: {r.base_assumptions.high_growth_years} of {r.base_assumptions.years} years"+(f" • terminal value {r.terminal_value_share:.0%} of DCF" if r.terminal_value_share is not None else "")+"\n"+f"Valuation basis: {'Fallback / heuristic' if r.fallback_valuation else 'Standard model set'}\nConfidence: {r.confidence_score}/100\nBusiness quality: {r.business_quality_score}/100\nFinancial risk: {r.risk_score}/100\nGovernance risk: {r.governance_risk_score}/100\nData quality: {r.data_quality_score}/100\nRequired valuation buffer: {r.dynamic_margin:.0%}\nData delivery: {d.cache_status}{f' ({d.cache_age_hours:.1f}h old)' if d.cache_status!='network' else ''}\nPeers: {len(d.peer_symbols)}\nProvider: {d.data_provider} • {d.source_symbol}")
        sm=[r.business_quality_score,r.governance_risk_score,r.order_book_score,r.confidence_score];values=[f"{sm[0]}/100",f"{sm[1]}/100",f"{sm[2]}/100" if r.data.order_book is not None else "Not available",f"{sm[3]}/100",f"{r.reverse_dcf_growth:.1%}" if r.reverse_dcf_growth is not None else "Unavailable",f"{r.model_dispersion:.0%}" if r.model_dispersion is not None else "Unavailable"]
        for card,value in zip(self.safety_metrics,values):card.set_value(value)
        terms=r.sensitivity_terminal_growths;self.sensitivity.setColumnCount(6);self.sensitivity.setHorizontalHeaderLabels(["Discount"]+[f"TG {x:.1%}" for x in terms]);self.sensitivity.setRowCount(0)
        for i,(rate,row) in enumerate(zip(r.sensitivity_discount_rates,r.sensitivity_values)):
            self._set_row(self.sensitivity,i,[f"{rate:.1%}"]+[money(x,d.currency) for x in row])
            for j,value in enumerate(row,1):
                item=self.sensitivity.item(i,j)
                if item and value is not None:
                    ratio=value/d.price
                    color="#CDEEDD" if ratio>=1.2 else "#E4F4EA" if ratio>=1 else "#FFF0CC" if ratio>=.8 else "#FADBD8"
                    item.setBackground(QBrush(QColor(color)));item.setToolTip(f"Fair value {money(value,d.currency)} • {((value/d.price)-1):+.1%} vs market")
                    if i==2 and j==3:
                        font=item.font();font.setBold(True);item.setFont(font);item.setToolTip(item.toolTip()+" • Base assumptions")
        notes=[r.reverse_dcf_note,"",f"Business quality ({r.business_quality_score}/100):"]+["• "+x for x in (r.business_quality_flags or ["No material automated flags."])]+["",f"Governance risk ({r.governance_risk_score}/100; lower is better):"]+["• "+x for x in (r.governance_flags or ["No material automated flags."])]+["",f"Order book ({r.order_book_score}/100; neutral when unavailable):"]+["• "+x for x in r.order_book_flags]+self.engine_notes(r);self.safety_notes.setPlainText("\n".join(notes));self.render_forensic_metrics(r)
        mc=r.monte_carlo_percentiles;mvals=[money(mc.get("P10"),d.currency) if mc else "—",money(mc.get("P50"),d.currency) if mc else "—",money(mc.get("P90"),d.currency) if mc else "—",f"{r.monte_carlo_probability_above_price:.1%}" if r.monte_carlo_probability_above_price is not None else "—",f"{r.monte_carlo_iterations:,}"]
        for card,value in zip(self.mc_metrics,mvals):
            card.set_value(value)
        self.histogram.set_result(r);self.price_value_chart.set_result(r);self.model_chart.set_result(r);self.fundamental_chart.set_result(r);self.scenario_gauge.set_result(r);self.render_lineage(r);self.render_audit(r)
        try:self.local_database.save_valuation(r)
        except Exception:pass
        if hasattr(self,"history_table"):self.load_database_page()
    def engine_notes(self,r):
        capital=r.cost_of_capital or {};drivers=r.valuation_drivers or {};lines=["","Cost of capital:"]
        if capital:lines+=[f"• Risk-free {capital['risk_free_rate']:.2%} ({capital['risk_free_source']}); beta {capital['beta']:.2f} ({capital['beta_source']}); equity risk premium {capital['equity_risk_premium']:.2%}; company premium {capital['company_risk_premium']:.2%}.",f"• Cost of equity {capital['cost_of_equity']:.2%}; pre-tax cost of debt {capital['pre_tax_cost_of_debt']:.2%}; debt weight {capital['debt_weight']:.0%}; tax {capital['tax_rate']:.1%}; WACC {capital['wacc']:.2%}."]
        if drivers.get("basis") and drivers.get("basis")!="Residual income":
            parts=[f"basis {drivers['basis']}"]+[f"{label} {drivers[key]:.1%}" for key,label in (("fcff_margin","FCFF margin"),("nopat_margin","NOPAT margin"),("roic","ROIC"),("reinvestment_rate","reinvestment rate")) if drivers.get(key) is not None]
            lines+=["","Operating drivers:","• "+"; ".join(parts)+"."]+(["• "+drivers["margin_note"]] if drivers.get("margin_note") else [])
        if r.growth_components:lines+=["","Initial growth sources:"]+[f"• {name}: {value:.1%}" for name,value in r.growth_components.items()]
        if r.relative_components:lines+=["",f"Relative valuation ({r.model_labels.get('relative','')}):"]+[f"• {name}: {money(value,r.data.currency)}" for name,value in r.relative_components.items()]
        return lines
    def render_forensic_metrics(self,r):
        f=r.forensic_scores or {};capital=r.cost_of_capital or {};values=[]
        piotroski=f.get("piotroski");altman=f.get("altman");beneish=f.get("beneish");roic=f.get("roic_median");cycle=f.get("cash_conversion_cycle");pledge=f.get("promoter_pledge");wacc=capital.get("wacc")
        values.append((f"{piotroski['score']}/{piotroski['tested']}",GREEN if piotroski["score"]>=7 else RED if piotroski["score"]<=3 else None) if piotroski else ("—",None))
        values.append((f"{altman['score']:.2f} • {altman['zone']}",GREEN if altman["zone"]=="Safe" else RED if altman["zone"]=="Distress" else None) if altman else ("—",None))
        values.append((f"{beneish['score']:.2f}",RED if beneish["flag"] else GREEN) if beneish else ("—",None))
        values.append((f"{roic:.1%} vs {wacc:.1%}",GREEN if roic>wacc else RED) if roic is not None and wacc else ("—",None))
        values.append((f"{cycle['latest']:.0f} days ({cycle['change']:+.0f})",RED if cycle["change"]>20 else None) if cycle else ("—",None))
        values.append((f"{pledge:.1%}",RED if pledge>=.10 else GREEN if pledge==0 else None) if pledge is not None else ("Not reported",None))
        for card,(value,color) in zip(self.forensic_metrics,values):card.set_value(value,color)
    def render_lineage(self,result):
        entries=list(result.data.lineage or []);self.lineage_table.setRowCount(0);self.lineage_urls=[]
        colors_by_status={"Selected":"#E4F4EA","Verified":"#E4F4EA","Normalized":"#E6EEFF","Derived":"#E6EEFF","Received":"#EEF3F8","Unavailable":"#FADBD8"}
        for row,entry in enumerate(entries):
            self.lineage_table.insertRow(row);values=[entry.metric,entry.value,entry.source,entry.period,entry.transformation,entry.status,"Open source" if entry.source_url else "—"]
            for column,value in enumerate(values):
                item=QTableWidgetItem(value);item.setToolTip(entry.source_url if column==6 and entry.source_url else value);self.lineage_table.setItem(row,column,item)
            status_item=self.lineage_table.item(row,5);status_item.setBackground(QBrush(QColor(colors_by_status.get(entry.status,"#EEF3F8"))))
            citation=self.lineage_table.item(row,6)
            if entry.source_url:citation.setForeground(QBrush(QColor(BLUE)));font=citation.font();font.setUnderline(True);citation.setFont(font)
            self.lineage_urls.append(entry.source_url)
        normalized=sum(1 for entry in entries if entry.status in {"Normalized","Derived"});unavailable=sum(1 for entry in entries if entry.status=="Unavailable");metrics=[str(len(result.data.data_sources or [result.data.data_provider])),str(len(entries)),str(normalized),str(unavailable)]
        for card,value in zip(self.lineage_metrics,metrics):card.set_value(value,RED if card==self.lineage_metrics[3] and unavailable else None)
        self.lineage_summary.setText(f"{result.data.symbol} • retrieved {result.data.data_timestamp} • {len(result.data.source_discrepancies)} discrepancy warning(s)");self.lineage_export_btn.setEnabled(bool(entries));self.lineage_open_btn.setEnabled(False)
    def lineage_selection_changed(self):
        rows=self.lineage_table.selectionModel().selectedRows() if self.lineage_table.selectionModel() else [];url=self.lineage_urls[rows[0].row()] if rows and rows[0].row()<len(self.lineage_urls) else "";self.lineage_open_btn.setEnabled(bool(url))
    def open_selected_citation(self):
        rows=self.lineage_table.selectionModel().selectedRows() if self.lineage_table.selectionModel() else []
        if not rows:return
        row=rows[0].row();url=self.lineage_urls[row] if row<len(self.lineage_urls) else ""
        if url and QUrl(url).scheme() in {"http","https"}:QDesktopServices.openUrl(QUrl(url))
    def export_lineage_csv(self):
        if not self.result or not self.result.data.lineage:return
        path,_=QFileDialog.getSaveFileName(self,"Export data lineage",f"{self.result.data.symbol.replace('.','_')}_Data_Lineage_{datetime.now():%Y%m%d}.csv","CSV (*.csv)")
        if not path:return
        try:
            with open(path,"w",encoding="utf-8-sig",newline="") as handle:
                writer=csv.writer(handle);writer.writerow(["Metric","Value","Source","Source URL","Period","Retrieved At","Transformation","Status"])
                for entry in self.result.data.lineage:write_csv_row(writer,[entry.metric,entry.value,entry.source,entry.source_url,entry.period,entry.retrieved_at,entry.transformation,entry.status])
            AccessibleMessageDialog.information(self,"Lineage exported",path)
        except Exception as exc:self.show_error(str(exc))
    def render_audit(self,result):
        self.audit_table.setRowCount(0)
        for row,event in enumerate(result.audit_events):
            self.audit_table.insertRow(row);details=" • ".join(f"{key}={value}" for key,value in event.details.items())
            for column,value in enumerate((event.timestamp,event.stage,event.action,details)):
                item=QTableWidgetItem(value);item.setToolTip(value);self.audit_table.setItem(row,column,item)
        valid=verify_audit_hash(result);short_id=result.analysis_id.split("-")[-1] if result.analysis_id else "—";values=[short_id,result.model_version,str(len(result.audit_events)),"Valid" if valid else "FAILED"]
        for card,value in zip(self.audit_metrics,values):card.set_value(value,GREEN if card==self.audit_metrics[3] and valid else RED if card==self.audit_metrics[3] else None)
        parent=f" • parent {result.parent_analysis_id}" if result.parent_analysis_id else "";self.audit_summary.setText(f"{result.analysis_id}{parent} • created {result.created_at} • SHA-256 {result.audit_hash[:16]}…");self.audit_export_btn.setEnabled(bool(result.analysis_id));self.audit_copy_btn.setEnabled(bool(result.analysis_id));self.audit_verify_btn.setEnabled(bool(result.audit_hash))
    def export_audit_json(self):
        if not self.result or not self.result.analysis_id:return
        path,_=QFileDialog.getSaveFileName(self,"Export model audit",f"{self.result.data.symbol.replace('.','_')}_{self.result.analysis_id}_Audit.json","JSON (*.json)")
        if not path:return
        try:
            with open(path,"w",encoding="utf-8") as handle:json.dump(audit_record(self.result),handle,indent=2,ensure_ascii=False)
            AccessibleMessageDialog.information(self,"Audit exported",path)
        except Exception as exc:self.show_error(str(exc))
    def copy_analysis_id(self):
        if self.result and self.result.analysis_id:QApplication.clipboard().setText(self.result.analysis_id);self.statusBar().showMessage("Analysis ID copied to clipboard")
    def verify_current_audit(self):
        if not self.result:return
        valid=verify_audit_hash(self.result);self.render_audit(self.result)
        if valid:AccessibleMessageDialog.information(self,"Audit verification","Audit hash is valid. The current record matches its recorded SHA-256 content hash.")
        else:AccessibleMessageDialog.critical(self,"Audit verification","Audit hash verification failed. The result or audit record was modified after creation.")
    def load_database_page(self):
        stats=self.local_database.stats();values=[str(stats["cached_stocks"]),str(stats["stale_stocks"]),str(stats["history_records"]),f"{stats['database_bytes']/1024/1024:.2f} MB"]
        for card,value in zip(self.database_metrics,values):card.set_value(value)
        self.cache_table.setRowCount(0)
        for row,item in enumerate(self.local_database.cache_rows()):self._set_row(self.cache_table,row,[item["symbol"],item["market"],f"{item['age_hours']:.1f}h","Stale" if item["is_stale"] else "Fresh",item["source_updated"] or "—",item["data_provider"],f"{item['payload_bytes']/1024:.1f} KB"])
        self.history_ids=[];self.history_table.setRowCount(0)
        for row,item in enumerate(self.local_database.history_rows()):self.history_ids.append(item["analysis_id"]);self._set_row(self.history_table,row,[item["created_at"][:19],item["symbol"],item["company"],f"{item['market_price']:,.2f}",f"{item['fair_value']:,.2f}",f"{item['upside_pct']:+.1f}%",f"{item['confidence_score']}/100",item["model_version"],item["analysis_id"]])
        self.history_export_btn.setEnabled(False);recoverable=self.local_database.recoverable_jobs(1);self.recoverable_job=recoverable[0] if recoverable else None;self.recover_job_btn.setEnabled(bool(recoverable));job_text=f" • recoverable job #{self.recoverable_job['id']} {self.recoverable_job['completed']}/{self.recoverable_job['total']}" if self.recoverable_job else "";self.database_status.setText(f"{self.local_database.path} • payload {stats['payload_bytes']/1024:.1f} KB • {stats['background_jobs']} background job record(s){job_text} • WAL-backed local SQLite")
    def save_cache_settings(self):self.local_database.set_setting("cache_ttl_hours",self.cache_ttl.value());self.local_database.set_setting("allow_stale_fallback",self.cache_stale.isChecked());self.local_database.set_setting("parallel_workers",self.parallel_workers.value());self.database_status.setText(f"Settings saved • TTL {self.cache_ttl.value():.1f}h • stale fallback {'on' if self.cache_stale.isChecked() else 'off'} • {self.parallel_workers.value()} workers")
    def clear_expired_cache(self):self.local_database.clear_expired();self.load_database_page()
    def clear_stock_cache(self):
        if QMessageBox.question(self,"Clear stock cache","Delete all cached stock snapshots? Watchlists and valuation history will remain.")==QMessageBox.Yes:self.local_database.clear_cache();self.load_database_page()
    def clear_valuation_history(self):
        if QMessageBox.question(self,"Clear valuation history","Delete all locally stored valuation audit history? Cached stock data and watchlists will remain.")==QMessageBox.Yes:self.local_database.clear_history();self.load_database_page()
    def history_selection_changed(self):self.history_export_btn.setEnabled(bool(self.history_table.selectionModel().selectedRows() if self.history_table.selectionModel() else []))
    def export_historical_audit(self):
        rows=self.history_table.selectionModel().selectedRows() if self.history_table.selectionModel() else []
        if not rows:return
        row=rows[0].row();analysis_id=self.history_ids[row] if row<len(self.history_ids) else "";record=self.local_database.history_audit(analysis_id)
        if not record:return
        path,_=QFileDialog.getSaveFileName(self,"Export stored audit",f"{analysis_id}_Audit.json","JSON (*.json)")
        if path:
            try:
                with open(path,"w",encoding="utf-8") as handle:json.dump(record,handle,indent=2,ensure_ascii=False)
                AccessibleMessageDialog.information(self,"Audit exported",path)
            except Exception as exc:self.show_error(str(exc))
    def recover_last_background_job(self):
        job=getattr(self,"recoverable_job",None)
        if not job or self.job_running():return
        try:
            payload=json.loads(job["payload"]);self.batch_items=[BatchItem(item["symbol"],item["market"]) for item in payload];self.batch_records=[];self.batch_table.setRowCount(0)
            for index,item in enumerate(self.batch_items):self._set_row(self.batch_table,index,[index+1,item.symbol,item.market,"Recovered / pending","—","—","—","—"])
            self.local_database.delete_job(job["id"]);self.batch_run.setEnabled(True);self.batch_info.setText(f"Recovered {len(self.batch_items)} items from interrupted {job['job_type']} job #{job['id']}. Restarting as batch analysis.")
            batch_index=next((index for index in range(self.nav.count()) if self.nav.item(index).text().startswith("Batch analysis")),0);self.nav.setCurrentRow(batch_index);self.analyze_batch()
        except Exception as exc:self.show_error(str(exc))
    def diagnostic_database_paths(self):return [self.local_database.path,self.watchlist_store.path,self.corporate_store.path]
    def load_diagnostics(self):
        events=self.diagnostics.events(500);self.diagnostic_table.setRowCount(0)
        for row,event in enumerate(events):self._set_row(self.diagnostic_table,row,[event.get("timestamp","")[:23],event.get("level",""),event.get("component",""),event.get("message",""),event.get("details","")[:500]])
        provider_status="Not checked" if not self.last_provider_health else f"{sum(1 for value in self.last_provider_health.values() if value.get('status')=='OK')}/{len(self.last_provider_health)} OK";database_status="Not checked" if not self.last_database_health else f"{sum(1 for value in self.last_database_health.values() if value.get('status')=='OK')}/{len(self.last_database_health)} OK";errors=self.diagnostics.error_count();values=[str(errors),self.diagnostics.last_error[:24] or "None",provider_status,database_status]
        for card,value in zip(self.diagnostic_metrics,values):card.set_value(value,RED if card==self.diagnostic_metrics[0] and errors else None)
    def run_diagnostic_health(self):
        if self.job_running():return
        self.busy(True,"Testing provider connectivity…");worker=Worker(self.diagnostics.health_checks);worker.signals.result.connect(self.diagnostic_health_done);worker.signals.error.connect(self.show_error);self.launch_worker(worker)
    def diagnostic_health_done(self,results):self.last_provider_health=results;self.diagnostic_status.setText(" • ".join(f"{name}: {value['status']} ({value.get('latency_ms') or '—'} ms)" for name,value in results.items()));self.load_diagnostics()
    def check_diagnostic_databases(self):self.last_database_health=self.diagnostics.database_checks(self.diagnostic_database_paths());self.diagnostic_status.setText(" • ".join(f"{name}: {value['status']}" for name,value in self.last_database_health.items()));self.load_diagnostics()
    def optimize_diagnostic_databases(self):
        if QMessageBox.question(self,"Database maintenance","Run quick integrity checks, REINDEX, and VACUUM on local databases? Close other FairScope windows first.")!=QMessageBox.Yes:return
        results=self.diagnostics.maintain_databases(self.diagnostic_database_paths());self.diagnostic_status.setText(" • ".join(f"{name}: {status}" for name,status in results.items()));self.check_diagnostic_databases()
    def export_diagnostic_zip(self):
        path,_=QFileDialog.getSaveFileName(self,"Export diagnostic ZIP",f"FairScope_Diagnostics_{datetime.now():%Y%m%d_%H%M}.zip","ZIP (*.zip)")
        if path:
            try:
                sensitive=[entry.symbol for entry in self.watchlist_store.entries()]+[entry.symbol for entry in self.corporate_store.entries()]
                if self.result:sensitive.append(self.result.data.symbol)
                self.diagnostics.export_zip(path,self.local_database.stats(),self.last_provider_health,self.last_database_health,sensitive);AccessibleMessageDialog.information(self,"Diagnostics exported",path);self.load_diagnostics()
            except Exception as exc:self.show_error(str(exc))
    def clear_diagnostic_logs(self):
        if QMessageBox.question(self,"Clear diagnostic logs","Delete local diagnostic log files? Databases and application data remain.")==QMessageBox.Yes:self.diagnostics.clear();self.load_diagnostics()
    def assumption_display_values(self,assumptions):
        return {"growth":assumptions.growth*100,"discount":assumptions.discount_rate*100,"terminal":assumptions.terminal_growth*100,"years":assumptions.years,"dcf_weight":assumptions.dcf_weight*100,"graham_weight":assumptions.graham_weight*100,"relative_weight":assumptions.relative_weight*100,"margin":assumptions.margin_of_safety*100,"high_growth_years":assumptions.high_growth_years}
    def load_assumptions(self,result,reset_values=True):
        automatic=result.automatic_assumptions or result.base_assumptions;self.current_auto_assumptions=automatic;self.auto_assumption_values=self.assumption_display_values(automatic);self._applying_assumption_values=True
        if reset_values:
            for lock in self.assumption_locks.values():lock.setChecked(False)
            self.assumption_preset.setCurrentText("Automatic defaults");self.assumption_note.clear()
        for _label,key,_mn,_mx,dec,suffix in self.assumption_defs:
            value=self.auto_assumption_values[key];self.assumption_auto_items[key].setText(f"{value:.{dec}f}{suffix}")
            if reset_values:self.inputs[key].setValue(value)
        if not reset_values:
            self.assumption_note.setPlainText(result.assumption_note);self.assumption_preset.setCurrentText(result.assumption_preset or "Custom review")
        self._applying_assumption_values=False;self.refresh_assumption_review()
    def assumption_value_changed(self):
        if getattr(self,"_applying_assumption_values",False):return
        self.assumption_preset.setCurrentText("Custom review");self.refresh_assumption_review()
    def assumption_tolerance(self,key):
        decimals=next(dec for _label,item_key,_mn,_mx,dec,_suffix in self.assumption_defs if item_key==key)
        return .5001*(10**-decimals)
    def reviewed_assumptions(self):
        v=self.inputs;automatic=getattr(self,"current_auto_assumptions",None)
        def reviewed(key,attribute,percent=True):
            shown=float(v[key].value());automatic_shown=float(self.auto_assumption_values.get(key,shown))
            if automatic is not None and abs(shown-automatic_shown)<=self.assumption_tolerance(key):return getattr(automatic,attribute)
            return shown/100 if percent else int(shown)
        return Assumptions(reviewed("growth","growth"),reviewed("discount","discount_rate"),reviewed("terminal","terminal_growth"),reviewed("years","years",False),reviewed("dcf_weight","dcf_weight"),reviewed("graham_weight","graham_weight"),reviewed("relative_weight","relative_weight"),reviewed("margin","margin_of_safety"),high_growth_years=reviewed("high_growth_years","high_growth_years",False),scenario_weights=tuple(automatic.scenario_weights) if automatic is not None else (.25,.50,.25))
    def assumption_validation_errors(self):
        if not self.result:return ["Analyze a stock first."]
        a=self.reviewed_assumptions();errors=[];weight_total=(a.dcf_weight+a.graham_weight+a.relative_weight)*100
        if a.discount_rate<=a.terminal_growth:errors.append("Discount rate must exceed terminal growth.")
        if a.high_growth_years>a.years:errors.append("High-growth years cannot exceed the forecast period.")
        if abs(weight_total-100)>0.11:errors.append(f"Model weights must total 100% (currently {weight_total:.1f}%).")
        return errors
    def refresh_assumption_review(self):
        if not getattr(self,"auto_assumption_values",None):return
        overrides=0
        for _label,key,_mn,_mx,dec,suffix in self.assumption_defs:
            automatic=float(self.auto_assumption_values[key]);reviewed=float(self.inputs[key].value());difference=reviewed-automatic;item=self.assumption_diff_items[key]
            if abs(difference)>self.assumption_tolerance(key):
                overrides+=1;unit=" years" if key in {"years","high_growth_years"} else " pp";item.setText(f"{difference:+.{dec}f}{unit}");item.setBackground(QBrush(QColor("#FFF0CC")))
            else:item.setText("No change");item.setBackground(QBrush(QColor("#E4F4EA")))
            if self.assumption_locks[key].isChecked():item.setText(item.text()+" • locked")
        errors=self.assumption_validation_errors();weight_total=self.inputs["dcf_weight"].value()+self.inputs["graham_weight"].value()+self.inputs["relative_weight"].value();current=self.assumption_display_values(self.result.base_assumptions) if self.result else {}
        values_pending=any(abs(float(self.inputs[key].value())-float(current.get(key,self.inputs[key].value())))>self.assumption_tolerance(key) for key in self.inputs);note_pending=bool(self.result) and self.assumption_note.toPlainText().strip()!=self.result.assumption_note.strip();pending=values_pending or note_pending;self._assumption_changes_pending=pending
        if hasattr(self,"pdf_btn") and not self._active_workers:self.pdf_btn.setEnabled(self.result is not None and not pending and not getattr(self,"_financial_changes_pending",False) and not getattr(self,"_external_changes_pending",False))
        if errors:
            self.assumption_review_status.setText("Review required: "+" ".join(errors));self.assumption_review_status.setStyleSheet("padding:10px;background:#FADBD8;color:#9B2C2C;border-radius:7px;font-weight:700;")
        elif pending:
            self.assumption_review_status.setText(f"Valid review • {overrides} override{'s' if overrides!=1 else ''} • pending acceptance and recalculation • PDF export paused");self.assumption_review_status.setStyleSheet("padding:10px;background:#FFF0CC;color:#7A5700;border-radius:7px;font-weight:700;")
        elif overrides:
            self.assumption_review_status.setText(f"Accepted review • {overrides} manual override{'s' if overrides!=1 else ''} recorded in the current valuation and PDF");self.assumption_review_status.setStyleSheet("padding:10px;background:#E4F4EA;color:#146C43;border-radius:7px;font-weight:700;")
        else:
            self.assumption_review_status.setText(f"Automatic assumptions accepted unchanged • model weights {weight_total:.1f}%");self.assumption_review_status.setStyleSheet("padding:10px;background:#E4F4EA;color:#146C43;border-radius:7px;font-weight:700;")
        self.override_summary.setText(f"{overrides} override{'s' if overrides!=1 else ''} • {sum(x.isChecked() for x in self.assumption_locks.values())} locked • {'pending' if pending else 'accepted'}");self.review_recalc_btn.setEnabled(not errors and pending and self.result is not None)
    def apply_assumption_preset(self):
        if not self.result:return
        preset=self.assumption_preset.currentText();values=dict(self.auto_assumption_values)
        if preset=="Conservative overlay":values.update(growth=max(-50,values["growth"]-2),discount=values["discount"]+1,terminal=max(0,values["terminal"]-.5),margin=min(50,values["margin"]+5))
        elif preset=="DCF emphasis":values.update(dcf_weight=65,graham_weight=10,relative_weight=25)
        elif preset=="Peer balanced":values.update(dcf_weight=40,graham_weight=20,relative_weight=40)
        elif preset=="Custom review":return
        self._applying_assumption_values=True
        for key,value in values.items():
            if not self.assumption_locks[key].isChecked():self.inputs[key].setValue(value)
        self._applying_assumption_values=False;self.refresh_assumption_review()
    def reset_unlocked_assumptions(self):
        if not self.result:return
        self.assumption_preset.setCurrentText("Automatic defaults");self._applying_assumption_values=True
        for key,value in self.auto_assumption_values.items():
            if not self.assumption_locks[key].isChecked():self.inputs[key].setValue(value)
        self._applying_assumption_values=False;self.refresh_assumption_review()
    def unlock_all_assumptions(self):
        for lock in self.assumption_locks.values():lock.setChecked(False)
        self.refresh_assumption_review()
    def recalculate(self):
        if not self.result:AccessibleMessageDialog.information(self,"Analyze first","Analyze a stock before reviewing assumptions.");return
        errors=self.assumption_validation_errors()
        if errors:AccessibleMessageDialog.warning(self,"Assumption review","\n".join(errors));return
        try:
            reviewed=self.reviewed_assumptions();automatic=getattr(self,"current_auto_assumptions",None) or self.result.automatic_assumptions or self.result.base_assumptions
            previous_analysis_id=self.result.analysis_id;self.result=value_stock(self.result.data,reviewed,automatic_assumptions=automatic,assumption_note=self.assumption_note.toPlainText(),assumption_preset=self.assumption_preset.currentText(),parent_analysis_id=previous_analysis_id);self.render_result();self.load_assumptions(self.result,reset_values=False);self.load_financial_company(self.result,reset_values=False);self.load_external_review(self.result,reset_values=False);self.nav.setCurrentRow(0);self.statusBar().showMessage(f"Recalculated • {len(self.result.manual_overrides)} manual override(s) recorded")
        except Exception as exc:self.show_error(str(exc))
    def financial_value_for_widget(self,metrics,key,kind,automatic=False):
        if metrics is None:return None
        value=(metrics.automatic_values.get(key) if automatic and metrics.automatic_values else getattr(metrics,key,None))
        if value is None:return None
        return value*100 if kind=="percent" else value
    def load_financial_company(self,result,reset_values=True):
        metrics=result.data.financial_metrics;applicable=result.methodology_profile=="Financial institution";self._loading_financial_inputs=True
        if not applicable:
            for _label,key,_kind,_maximum,_help in self.financial_defs:self.financial_auto_items[key].setText("Not applicable");self.financial_inputs[key].setValue(-999);self.financial_inputs[key].setEnabled(False)
            self.financial_note.clear();self.financial_apply_btn.setEnabled(False);self.financial_reset_btn.setEnabled(False);self.financial_status.setText("This company is not classified as a bank, NBFC/lender, insurer, or other financial institution.");self.financial_status.setStyleSheet("padding:10px;background:#E8EEF6;border-radius:7px;font-weight:600;");self._financial_changes_pending=False;self._loading_financial_inputs=False;return
        if metrics is None:metrics=FinancialCompanyMetrics()
        for _label,key,kind,_maximum,_help in self.financial_defs:
            automatic=self.financial_value_for_widget(metrics,key,kind,True);current=self.financial_value_for_widget(metrics,key,kind,False);self.financial_auto_items[key].setText("—" if automatic is None else f"{automatic:,.2f}{'%' if kind=='percent' else 'x' if kind=='multiple' else ''}");self.financial_inputs[key].setEnabled(True)
            if reset_values:self.financial_inputs[key].setValue(-999 if current is None else current)
        if reset_values:self.financial_note.setPlainText(metrics.review_note)
        self.financial_reset_btn.setEnabled(True);self._loading_financial_inputs=False;self.refresh_financial_review()
    def financial_tolerance(self,kind):return .000051 if kind=="percent" else .0051
    def financial_value_changed(self):
        if not getattr(self,"_loading_financial_inputs",False):self.refresh_financial_review()
    def refresh_financial_review(self):
        if not self.result or self.result.methodology_profile!="Financial institution":return
        metrics=self.result.data.financial_metrics or FinancialCompanyMetrics();pending=False;manual=0;invalid=[];negative_allowed={"net_interest_margin","financing_margin","deposit_growth","loan_growth","premium_growth"}
        for label,key,kind,_maximum,_help in self.financial_defs:
            shown=self.financial_inputs[key].value()
            if -998<shown<0 and key not in negative_allowed:invalid.append(label)
            reviewed=None if shown<=-998 else shown/100 if kind=="percent" else shown;current=getattr(metrics,key,None)
            if (reviewed is None)!=(current is None) or reviewed is not None and current is not None and abs(reviewed-current)>self.financial_tolerance(kind):pending=True
            automatic=metrics.automatic_values.get(key) if metrics.automatic_values else current
            if (reviewed is None)!=(automatic is None) or reviewed is not None and automatic is not None and abs(reviewed-automatic)>self.financial_tolerance(kind):manual+=1
        if self.financial_note.toPlainText().strip()!=metrics.review_note.strip():pending=True
        self._financial_changes_pending=pending;self.financial_apply_btn.setEnabled(pending and not invalid)
        if hasattr(self,"pdf_btn") and not self._active_workers:self.pdf_btn.setEnabled(self.result is not None and not pending and not getattr(self,"_assumption_changes_pending",False) and not getattr(self,"_external_changes_pending",False))
        subtype=metrics.subtype;missing=sum(1 for _label,key,_kind,_maximum,_help in self.financial_defs if self.financial_inputs[key].value()<=-998)
        if invalid:self.financial_status.setText(f"Review required • negative value not allowed for: {', '.join(invalid)}");self.financial_status.setStyleSheet("padding:10px;background:#FADBD8;color:#9B2C2C;border-radius:7px;font-weight:700;")
        elif pending:self.financial_status.setText(f"{subtype} • {manual} manual field(s) • {missing} unset • pending recalculation • PDF export paused");self.financial_status.setStyleSheet("padding:10px;background:#FFF0CC;color:#7A5700;border-radius:7px;font-weight:700;")
        else:self.financial_status.setText(f"{subtype} • source: {metrics.source} • {len(metrics.manual_fields)} accepted manual field(s) • {missing} unset");self.financial_status.setStyleSheet("padding:10px;background:#E4F4EA;color:#146C43;border-radius:7px;font-weight:700;")
    def reset_financial_company_data(self):
        if not self.result or self.result.methodology_profile!="Financial institution":return
        metrics=self.result.data.financial_metrics or FinancialCompanyMetrics();self._loading_financial_inputs=True
        for _label,key,kind,_maximum,_help in self.financial_defs:
            automatic=self.financial_value_for_widget(metrics,key,kind,True);self.financial_inputs[key].setValue(-999 if automatic is None else automatic)
        self.financial_note.clear();self._loading_financial_inputs=False;self.refresh_financial_review()
    def apply_financial_company_data(self):
        if not self.result or self.result.methodology_profile!="Financial institution" or not self.financial_apply_btn.isEnabled():return
        try:
            old_metrics=self.result.data.financial_metrics or FinancialCompanyMetrics();metrics=deepcopy(old_metrics);manual_fields=[]
            for _label,key,kind,_maximum,_help in self.financial_defs:
                shown=self.financial_inputs[key].value();value=None if shown<=-998 else shown/100 if kind=="percent" else shown;setattr(metrics,key,value);automatic=metrics.automatic_values.get(key) if metrics.automatic_values else getattr(old_metrics,key,None)
                if (value is None)!=(automatic is None) or value is not None and automatic is not None and abs(value-automatic)>self.financial_tolerance(kind):manual_fields.append(key)
            metrics.manual_fields=manual_fields;metrics.review_note=self.financial_note.toPlainText().strip();base_source=old_metrics.source.replace(" + User reviewed input","").replace("User reviewed input","").strip(" +");metrics.source=(base_source+" + User reviewed input").strip(" +")
            new_data=deepcopy(self.result.data);new_data.financial_metrics=metrics;new_data.lineage=[entry for entry in new_data.lineage if entry.status!="Manual"];retrieved=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
            labels={key:label for label,key,_kind,_maximum,_help in self.financial_defs}
            for key in manual_fields:
                value=getattr(metrics,key);kind=next(kind for _label,item_key,kind,_maximum,_help in self.financial_defs if item_key==key);display="Unavailable" if value is None else f"{value:.2%}" if kind=="percent" else f"{value:,.2f}x" if kind=="multiple" else f"{new_data.currency} {value:,.2f}";new_data.lineage.append(DataLineageEntry(labels[key],display,"User reviewed input","","Current review",retrieved,"Manual specialized financial-company input; verify cited official filing in review note","Manual"))
            previous=self.result;self.result=value_stock(new_data,previous.base_assumptions,automatic_assumptions=previous.automatic_assumptions,assumption_note=previous.assumption_note,assumption_preset=previous.assumption_preset,parent_analysis_id=previous.analysis_id);self.render_result();self.load_assumptions(self.result,reset_values=False);self.load_financial_company(self.result,reset_values=True);self.load_external_review(self.result,reset_values=False);self.nav.setCurrentRow(0);self.statusBar().showMessage(f"Specialized financial data applied • {len(manual_fields)} manual field(s) • new audit ID {self.result.analysis_id}")
        except Exception as exc:self.show_error(str(exc))
    def external_current_values(self,data):
        return {"market_price":data.price,"trailing_pe":data.trailing_pe,"book_value_per_share":data.book_value_per_share,"return_on_equity":data.return_on_equity*100 if data.return_on_equity is not None else None,"market_cap":data.market_cap,"revenue":data.revenue_history[0] if data.revenue_history else None,"net_income":data.net_income_history[0] if data.net_income_history else None,"free_cash_flow":data.free_cash_flow,"order_book":data.order_book,"promoter_current":data.promoter_holding_history[0]*100 if data.promoter_holding_history else None,"promoter_three_year":data.promoter_holding_history[-1]*100 if len(data.promoter_holding_history)>=3 else None,"promoter_pledge":data.promoter_pledge*100 if data.promoter_pledge is not None else None,"listed_investments":data.listed_investments_value}
    def load_external_review(self,result,reset_values=True):
        current=self.external_current_values(result.data);self._loading_external=True
        for _label,key,kind,_help in self.external_defs:
            value=current.get(key);self.external_current_items[key].setText("—" if value is None else f"{value:,.2f}{'%' if kind=='percent' else 'x' if kind=='multiple' else ''}")
            if reset_values:self.external_inputs[key].setValue(-999)
        if reset_values:self.external_url.clear();self.external_period.clear()
        self._loading_external=False;self._external_changes_pending=False;self.external_apply_btn.setEnabled(False);count=len(result.data.external_reviews);self.external_status.setText(f"{result.data.symbol} • {count} accepted external review(s) • enter only cited values that differ or fill missing data");self.external_status.setStyleSheet("padding:10px;background:#E4F4EA;color:#146C43;border-radius:7px;font-weight:700;")
    def external_value_changed(self):
        if getattr(self,"_loading_external",False) or not self.result:return
        values_set=sum(1 for spin in self.external_inputs.values() if spin.value()>-998);pending=values_set>0 or bool(self.external_url.text().strip()) or bool(self.external_period.text().strip());self._external_changes_pending=pending;valid=values_set>0 and self.external_url.text().strip().startswith(("http://","https://")) and bool(self.external_period.text().strip());self.external_apply_btn.setEnabled(valid)
        if hasattr(self,"pdf_btn") and not self._active_workers:self.pdf_btn.setEnabled(not pending and not getattr(self,"_assumption_changes_pending",False) and not getattr(self,"_financial_changes_pending",False))
        if pending:self.external_status.setText(f"Pending external review • {values_set} value(s) entered • {'ready to apply' if valid else 'source URL and period required'} • PDF export paused");self.external_status.setStyleSheet("padding:10px;background:#FFF0CC;color:#7A5700;border-radius:7px;font-weight:700;")
    def reset_external_review(self):
        if self.result:self.load_external_review(self.result,True)
    def open_moneycontrol_search(self):
        symbol=self.result.data.symbol.split(".")[0] if self.result else self.symbol.text().strip();query=quote(f"site:moneycontrol.com {symbol} financials ratios");QDesktopServices.openUrl(QUrl(f"https://www.google.com/search?q={query}"))
    def apply_external_review(self):
        if not self.result or not self.external_apply_btn.isEnabled():return
        try:
            source=self.external_source.currentText();url=self.external_url.text().strip();period=self.external_period.text().strip();new_data=deepcopy(self.result.data);current=self.external_current_values(new_data);changed={};stamp=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
            for label,key,kind,_help in self.external_defs:
                shown=self.external_inputs[key].value()
                if shown<=-998:continue
                value=shown/100 if kind=="percent" else shown;changed[key]=value;display=f"{value:.2%}" if kind=="percent" else f"{value:.4f}x" if kind=="multiple" else f"{new_data.currency} {value:,.2f}"
                new_data.lineage.append(DataLineageEntry(label,display,source,url,period,stamp,"Manual external review; cited source retained; official exchange price remains preferred","Manual"))
                if key=="market_price":
                    if current["market_price"] and abs(value-current["market_price"])/max(value,current["market_price"])>.02:new_data.source_discrepancies.append(f"External reviewed price {value:,.2f} differs from selected price {current['market_price']:,.2f} by more than 2%.")
                elif key=="trailing_pe":new_data.trailing_pe=value
                elif key=="book_value_per_share":new_data.book_value_per_share=value
                elif key=="return_on_equity":new_data.return_on_equity=value
                elif key=="market_cap":new_data.market_cap=value
                elif key=="revenue":
                    new_data.revenue_history=([value]+new_data.revenue_history[1:]) if new_data.revenue_history else [value]
                    # The DCF revenue base and margins are read from the aligned statements, not revenue_history.
                    if new_data.statements.get("revenue"):new_data.statements["revenue"][0]=value
                elif key=="net_income":new_data.net_income=value;new_data.net_income_history=([value]+new_data.net_income_history[1:]) if new_data.net_income_history else [value];new_data.eps=value/new_data.shares if new_data.shares else new_data.eps
                elif key=="free_cash_flow":new_data.free_cash_flow=value;new_data.current_fcf=value;new_data.fcf_history=([value]+new_data.fcf_history[1:]) if new_data.fcf_history else [value]
                elif key=="order_book":new_data.order_book=value;new_data.order_book_period=period;new_data.order_book_source=source
                elif key=="promoter_current":
                    history=list(new_data.promoter_holding_history);reviewed=value
                    if history:history[0]=reviewed
                    else:history=[reviewed]
                    new_data.promoter_holding_history=history
                elif key=="promoter_three_year":
                    history=list(new_data.promoter_holding_history);reviewed=value
                    while len(history)<3:history.append(history[-1] if history else reviewed)
                    history[-1]=reviewed;new_data.promoter_holding_history=history
                elif key=="promoter_pledge":new_data.promoter_pledge=value
                elif key=="listed_investments":new_data.listed_investments_value=value
            new_data.external_reviews.append({"source":source,"url":url,"period":period,"retrieved_at":stamp,"fields":", ".join(changed)})
            previous=self.result;self.result=value_stock(new_data,previous.base_assumptions,automatic_assumptions=previous.automatic_assumptions,assumption_note=previous.assumption_note,assumption_preset=previous.assumption_preset,parent_analysis_id=previous.analysis_id);self.render_result();self.load_assumptions(self.result,False);self.load_financial_company(self.result,False);self.load_external_review(self.result,True);self.nav.setCurrentRow(0);self.statusBar().showMessage(f"External review applied • {len(changed)} field(s) • new audit ID {self.result.analysis_id}")
        except Exception as exc:self.show_error(str(exc))
    def save_valuation_settings(self):
        weights=[spin.value()/100 for spin in self.setting_weights]
        if sum(weights)<=0:AccessibleMessageDialog.warning(self,"Valuation parameters","Scenario weights must have a positive total.");return
        total=sum(weights);values={"live_us_risk_free":self.setting_live_rf.isChecked(),"damodaran_erp":self.setting_damodaran.isChecked(),"risk_free_us":self.setting_rf_us.value()/100,"risk_free_india":self.setting_rf_india.value()/100,"erp_us":self.setting_erp_us.value()/100,"erp_india":self.setting_erp_india.value()/100,"scenario_weights":[weight/total for weight in weights],"holding_discount":self.setting_holding.value()/100}
        for key,value in values.items():self.local_database.set_setting(key,value)
        self.valuation_settings_status.setText(f"Saved • scenario weights {' / '.join(f'{weight:.0%}' for weight in values['scenario_weights'])} • applied to the next analysis or refresh")
    def run_backtest(self):
        items=list(self.batch_items) or ([BatchItem(self.result.data.symbol,self.result.data.market)] if self.result else [])
        if not items:AccessibleMessageDialog.information(self,"Backtest","Import a stock list on the Batch analysis page or analyze a stock first.");return
        self.backtest_table.setRowCount(0);self.backtest_points=[];self.backtest_export.setEnabled(False);years=self.backtest_years.value()
        worker=BacktestWorker(items,years,int(self.local_database.setting("parallel_workers",3)));worker.signals.progress.connect(self.update_controlled_progress);worker.signals.result.connect(self.backtest_done);worker.signals.error.connect(self.show_error);self.launch_controlled_worker(worker,f"Backtesting {len(items)} stock(s) at up to {years} past fiscal year-end(s)…",len(items))
    def track_saved_valuations(self):
        if self.job_running():return
        self.backtest_table.setRowCount(0);self.backtest_points=[];self.backtest_export.setEnabled(False)
        self.busy(True,"Comparing saved valuations with today's prices…");worker=Worker(track_saved_valuations,self.local_database);worker.signals.result.connect(lambda payload:self.backtest_done((*payload,FORWARD_NOTE)));worker.signals.error.connect(self.show_error);self.launch_worker(worker)
    def backtest_done(self,payload):
        points,errors,*rest=payload;note=rest[0] if rest else LOOK_AHEAD_NOTE;points=sorted(points,key=lambda point:(point.symbol,point.fiscal_year_end,point.as_of));self.backtest_points=points;self.backtest_table.setRowCount(0)
        for row,point in enumerate(points):self._set_row(self.backtest_table,row,[point.symbol,point.fiscal_year_end,point.as_of,f"{point.price_then:,.2f}",f"{point.fair_value_then:,.2f}",f"{point.upside_then:+.1f}%",f"{point.forward_return:+.1f}%",f"{point.annualized_return:+.1f}%","Yes" if point.below_buffer else "No"])
        summary=summarize(points);correlation=summary.get("rank_correlation");hit=summary.get("hit_rate")
        def pct(value):return "—" if value is None else f"{value:+.1f}%"
        values=[(str(summary["observations"]),None),("—" if correlation is None else f"{correlation:+.2f}",None if correlation is None else GREEN if correlation>.1 else RED if correlation<0 else None),("—" if hit is None else f"{hit:.0%}",None),(pct(summary.get("avg_return_undervalued")),None),(pct(summary.get("avg_return_overvalued")),None)]
        for card,(value,color) in zip(self.backtest_metrics,values):card.set_value(value,color)
        for error in errors:self.diagnostics.log("WARNING","Backtest",error)
        self.backtest_summary.setText(f"{summary['observations']} point-in-time valuations across {summary.get('stocks',0)} stock(s); {len(errors)} could not be tested (see Diagnostics). Rank correlation compares modeled upside with the annualized return that followed; positive values mean higher modeled upside went with higher returns. "+(errors[0]+" " if errors and not points else "")+note)
        self.backtest_export.setEnabled(bool(points));self.statusBar().showMessage(f"Backtest completed • {summary['observations']} observation(s)")
    def export_backtest_csv(self):
        if not self.backtest_points:return
        path,_=QFileDialog.getSaveFileName(self,"Export backtest",f"FairScope_Backtest_{datetime.now():%Y%m%d}.csv","CSV (*.csv)")
        if not path:return
        try:
            records=[point_record(point) for point in self.backtest_points];summary=summarize(self.backtest_points)
            with open(path,"w",encoding="utf-8-sig",newline="") as handle:
                writer=csv.writer(handle);writer.writerow(list(records[0]))
                for record in records:writer.writerow(list(record.values()))
                writer.writerow([]);writer.writerow(["Summary"])
                for key,value in summary.items():writer.writerow([key,value])
            AccessibleMessageDialog.information(self,"Backtest exported",path)
        except Exception as exc:self.show_error(str(exc))
    def export_pdf(self):
        if not self.result:return
        path,_=QFileDialog.getSaveFileName(self,"Save valuation report",f"{self.result.data.symbol.replace('.','_')}_Fair_Value_Report_{datetime.now():%Y%m%d}.pdf","PDF (*.pdf)")
        if path:
            try:create_pdf(self.result,path);AccessibleMessageDialog.information(self,"Report saved",path)
            except Exception as exc:self.show_error(str(exc))
    def import_batch(self):
        path,_=QFileDialog.getOpenFileName(self,"Import stock list","","Stock lists (*.csv *.txt *.tsv *.xlsx *.xlsm)")
        if not path:return
        try:
            self.batch_items=import_stock_list(path,self.market.currentText());self.batch_records=[]
            self.batch_csv.setEnabled(False);self.batch_pdf.setEnabled(False);self.batch_table.setRowCount(0)
            for i,item in enumerate(self.batch_items):
                self._set_row(self.batch_table,i,[i+1,item.symbol,item.market,"Pending","—","—","—","—"])
            self.batch_run.setEnabled(True);self.batch_info.setText(f"Imported {len(self.batch_items)} unique stocks from {os.path.basename(path)}.")
        except Exception as exc:self.show_error(str(exc))
    def analyze_batch(self):
        if not self.batch_items or self.job_running():return
        self.batch_csv.setEnabled(False);self.batch_pdf.setEnabled(False);self.batch_records=[]
        worker=BatchWorker(self.batch_items,self.local_database,"batch",int(self.local_database.setting("parallel_workers",3)));worker.signals.progress.connect(self.batch_progress);worker.signals.progress.connect(self.update_controlled_progress);worker.signals.result.connect(self.batch_done);worker.signals.error.connect(self.show_error);self.launch_controlled_worker(worker,f"Analyzing {len(self.batch_items)} stocks with bounded parallel processing…",len(self.batch_items))
    def batch_progress(self,payload):
        i,r,e,completed,total,attempts,cancelled=payload;item=self.batch_items[i]
        status="Cancelled" if cancelled else "Completed" if r else "Failed";vals=[i+1,r.data.symbol if r else item.symbol,r.data.market if r else item.market,status,money(r.data.price,r.data.currency) if r else "—",money(r.fair_value,r.data.currency) if r else "—",f"{r.upside_pct:+.1f}%" if r else "—",r.label if r else e[:80]];self._set_row(self.batch_table,i,vals);self.statusBar().showMessage(f"Analyzed {completed} of {total} • attempts {attempts}")
    def batch_done(self,records):
        self.batch_records=records
        for item,result,error in records:
            if result:
                try:self.local_database.save_valuation(result)
                except Exception:pass
            elif error:self.diagnostics.error("Batch analysis",f"{item.symbol} failed",error)
        self.batch_csv.setEnabled(True);self.batch_pdf.setEnabled(True);ok=sum(1 for _,r,_ in records if r);self.batch_info.setText(f"Completed: {ok} successful, {len(records)-ok} failed. Double-click a completed row for full analysis.")
    def open_batch_result(self,index):
        row=index.row()
        if row<len(self.batch_records) and self.batch_records[row][1]:
            self.result=self.batch_records[row][1];self.render_result();self.load_assumptions(self.result,reset_values=True);self.load_financial_company(self.result,reset_values=True);self.load_external_review(self.result,reset_values=True);self.pdf_btn.setEnabled(True);self.nav.setCurrentRow(0)
    def private_text(self,value):return "••••" if self.privacy_mode else value
    def confirm_sensitive_export(self,description):
        if not self.privacy_mode:return True
        return QMessageBox.question(self,"Privacy mode",f"{description} will contain unmasked financial values. Continue?")==QMessageBox.Yes
    def save_privacy_setting(self):
        self.privacy_mode=self.privacy_checkbox.isChecked();self.local_database.set_setting("privacy_mode",self.privacy_mode);self.privacy_status.setText(f"Privacy mode {'enabled' if self.privacy_mode else 'disabled'} • secrets backend: {self.secure_storage.backend}")
        self.load_watchlist()
    def load_watchlist(self):
        entries=self.watchlist_store.entries();self.watchlist_row_ids=[];self.watchlist_table.setRowCount(0);mos_count=0
        for row,entry in enumerate(entries):
            result=self.watchlist_results.get(entry.id);self.watchlist_row_ids.append(entry.id)
            if result:
                price=money(result.data.price,result.data.currency);fair=money(result.fair_value,result.data.currency);mos=money(result.margin_price,result.data.currency);upside=f"{result.upside_pct:+.1f}%";confidence=f"{result.confidence_score}/100";risk=f"F {result.risk_score} / G {result.governance_risk_score}";company=result.data.company
                if result.data.price<=result.margin_price:mos_count+=1
            else:price="—" if entry.last_price is None else f"{entry.last_price:,.2f}";fair="—" if entry.last_fair_value is None else f"{entry.last_fair_value:,.2f}";mos=upside=confidence=risk="—";company=entry.company
            if self.privacy_mode:price=fair=mos=upside=confidence=risk="••••"
            self._set_row(self.watchlist_table,row,[entry.symbol,entry.market,company,price,fair,mos,upside,confidence,risk,(entry.last_checked[:19]+" • " if entry.last_checked else "")+entry.last_status])
        alerts=self.watchlist_store.alerts();self.alert_table.setRowCount(0)
        for row,alert in enumerate(alerts):self._set_row(self.alert_table,row,[alert.created_at[:19],alert.severity.upper(),alert.symbol,alert.kind.replace("_"," ").title(),self.private_text(alert.message),"Yes" if alert.is_read else "No"])
        unread=self.watchlist_store.unread_count();high=sum(1 for alert in alerts if not alert.is_read and alert.severity=="high");values=[str(len(entries)),str(unread),str(mos_count),str(high)]
        for card,value in zip(self.watchlist_metrics,values):card.set_value(value,RED if card==self.watchlist_metrics[3] and high else None)
        self.nav.item(1).setText(f"Watchlists & alerts ({unread})" if unread else "Watchlists & alerts");self.watch_refresh.setEnabled(bool(entries));self.watch_remove.setEnabled(False);self.watch_save_settings.setEnabled(False)
    def selected_watchlist_entry(self):
        rows=self.watchlist_table.selectionModel().selectedRows() if self.watchlist_table.selectionModel() else []
        if not rows:return None
        entry_id=self.watchlist_row_ids[rows[0].row()] if rows[0].row()<len(self.watchlist_row_ids) else None
        return next((entry for entry in self.watchlist_store.entries() if entry.id==entry_id),None)
    def add_watch_symbol(self):
        symbol=self.watch_symbol.text().strip()
        if not symbol:AccessibleMessageDialog.information(self,"Watchlist","Enter a symbol first.");return
        try:self.watchlist_store.add(symbol,self.watch_market.currentText());self.watch_symbol.clear();self.load_watchlist()
        except Exception as exc:self.show_error(str(exc))
    def add_current_to_watchlist(self):
        if not self.result:AccessibleMessageDialog.information(self,"Watchlist","Analyze a stock first.");return
        entry=self.watchlist_store.add(self.result.data.symbol,self.result.data.market,self.result.data.company);self.watchlist_results[entry.id]=self.result;self.watchlist_store.update_result(entry.id,self.result,self.result.label);self.load_watchlist()
    def refresh_watchlist(self):
        entries=self.watchlist_store.entries()
        if not entries:return
        self._watch_refresh_entries=entries;items=[BatchItem(entry.symbol,entry.market) for entry in entries];worker=BatchWorker(items,self.local_database,"watchlist",int(self.local_database.setting("parallel_workers",3)),True);worker.signals.progress.connect(self.update_controlled_progress);worker.signals.result.connect(self.watchlist_records_done);worker.signals.error.connect(self.show_error);self.launch_controlled_worker(worker,f"Refreshing {len(entries)} watchlist stocks…",len(entries))
    def watchlist_records_done(self,records):
        results=[(entry,record[1],record[2]) for entry,record in zip(self._watch_refresh_entries,records)];self.watchlist_done(results)
    def watchlist_done(self,results):
        new_alerts=[];current_ids={entry.id for entry in self.watchlist_store.entries()}
        for entry,result,error in results:
            if entry.id not in current_ids:continue
            if result:
                new_alerts.extend(self.watchlist_store.evaluate(entry,result));self.watchlist_store.update_result(entry.id,result,result.label);self.watchlist_results[entry.id]=result
                try:self.local_database.save_valuation(result)
                except Exception:pass
            else:self.watchlist_store.update_failure(entry.id,error);self.diagnostics.error("Watchlist refresh",f"{entry.symbol} failed",error)
        self.load_watchlist();self.statusBar().showMessage(f"Watchlist refresh completed • {len(new_alerts)} new alert(s)")
        if new_alerts:WatchlistAlertDialog(new_alerts[:20],self).exec()
    def remove_watchlist_entry(self):
        entry=self.selected_watchlist_entry()
        if entry:self.watchlist_store.remove(entry.id);self.watchlist_results.pop(entry.id,None);self.load_watchlist()
    def load_watchlist_settings(self):
        entry=self.selected_watchlist_entry();enabled=entry is not None;self.watch_remove.setEnabled(enabled);self.watch_save_settings.setEnabled(enabled)
        if not entry:return
        self.watch_custom_price.setValue(entry.custom_price or 0);self.watch_min_upside.setValue(entry.min_upside);self.watch_max_risk.setValue(entry.max_financial_risk);self.watch_max_governance.setValue(entry.max_governance_risk);self.watch_fv_change.setValue(entry.fair_value_change);self.watch_mos.setChecked(entry.alert_mos)
    def save_watchlist_settings(self):
        entry=self.selected_watchlist_entry()
        if not entry:return
        self.watchlist_store.update_settings(entry.id,self.watch_custom_price.value() or None,self.watch_min_upside.value(),self.watch_max_risk.value(),self.watch_max_governance.value(),self.watch_fv_change.value(),self.watch_mos.isChecked());self.load_watchlist()
    def mark_watchlist_alerts_read(self):self.watchlist_store.mark_all_read();self.load_watchlist()
    def export_watchlist_csv(self):
        if not self.confirm_sensitive_export("The watchlist CSV"):return
        path,_=QFileDialog.getSaveFileName(self,"Export",f"FairScope_Watchlist_{datetime.now():%Y%m%d}.csv","CSV (*.csv)")
        if path:
            try:self.watchlist_store.export_csv(path);AccessibleMessageDialog.information(self,"Watchlist exported",path)
            except Exception as exc:self.show_error(str(exc))
    def export_watchlist_pdf(self):
        if not self.confirm_sensitive_export("The watchlist PDF"):return
        entries=self.watchlist_store.entries();alerts=self.watchlist_store.alerts(limit=1000)
        if not entries:AccessibleMessageDialog.information(self,"Watchlist report","Add at least one watchlist stock first.");return
        path,_=QFileDialog.getSaveFileName(self,"Export colourful watchlist report",f"FairScope_Watchlist_Alerts_{datetime.now():%Y%m%d}.pdf","PDF (*.pdf)")
        if path:
            try:create_watchlist_pdf(entries,alerts,self.watchlist_results,path);AccessibleMessageDialog.success(self,"Watchlist report saved",path)
            except Exception as exc:self.show_error(str(exc))
    def load_corporate_monitor(self):
        entries=self.corporate_store.entries();self.corporate_entry_ids=[];self.corporate_company_table.setRowCount(0)
        for row,entry in enumerate(entries):self.corporate_entry_ids.append(entry.id);self._set_row(self.corporate_company_table,row,[entry.symbol,entry.market,entry.company,entry.cik or "—",entry.last_checked[:19] if entry.last_checked else "—",entry.status])
        events=self.corporate_store.events();self.corporate_event_urls=[];self.corporate_event_table.setRowCount(0)
        for row,event in enumerate(events):self._set_row(self.corporate_event_table,row,[event.event_date,event.severity.upper(),event.symbol,event.event_type,event.source,event.title,"Yes" if event.is_read else "No"]);self.corporate_event_urls.append(event.url)
        unread=self.corporate_store.unread_count();filings=sum(1 for event in events if event.event_type not in {"Dividend","Stock split","Capital gain"});actions=len(events)-filings;values=[str(len(entries)),str(unread),str(filings),str(actions)]
        for card,value in zip(self.corporate_metrics,values):card.set_value(value,RED if card==self.corporate_metrics[1] and unread else None)
        self.nav.item(2).setText(f"Filings & actions ({unread})" if unread else "Filings & actions");self.corp_refresh.setEnabled(bool(entries));self.corp_remove.setEnabled(False);self.corp_open.setEnabled(False)
    def selected_corporate_entry(self):
        rows=self.corporate_company_table.selectionModel().selectedRows() if self.corporate_company_table.selectionModel() else []
        if not rows:return None
        entry_id=self.corporate_entry_ids[rows[0].row()] if rows[0].row()<len(self.corporate_entry_ids) else None
        return next((entry for entry in self.corporate_store.entries() if entry.id==entry_id),None)
    def corporate_selection_changed(self):self.corp_remove.setEnabled(self.selected_corporate_entry() is not None)
    def corporate_event_selection_changed(self):
        rows=self.corporate_event_table.selectionModel().selectedRows() if self.corporate_event_table.selectionModel() else [];url=self.corporate_event_urls[rows[0].row()] if rows and rows[0].row()<len(self.corporate_event_urls) else "";self.corp_open.setEnabled(bool(url))
    def add_corporate_symbol(self):
        symbol=self.corp_symbol.text().strip()
        if not symbol:AccessibleMessageDialog.information(self,"Corporate monitor","Enter a symbol first.");return
        self.corporate_store.add(symbol,self.corp_market.currentText());self.corp_symbol.clear();self.load_corporate_monitor()
    def add_current_to_corporate_monitor(self):
        if not self.result:AccessibleMessageDialog.information(self,"Corporate monitor","Analyze a stock first.");return
        self.corporate_store.add(self.result.data.symbol,self.result.data.market,self.result.data.company);self.load_corporate_monitor()
    def refresh_corporate_monitor(self):
        entries=self.corporate_store.entries()
        if not entries:return
        email=self.secure_storage.get_secret("sec_contact_email");self.busy(True,f"Refreshing filings and actions for {len(entries)} companies…");worker=CorporateMonitorWorker(entries,email);worker.signals.progress.connect(lambda payload:self.statusBar().showMessage(f"Corporate monitor: checked {payload[0]+1} of {len(entries)}"));worker.signals.result.connect(self.corporate_monitor_done);worker.signals.error.connect(self.show_error);self.launch_worker(worker)
    def corporate_monitor_done(self,results):
        added=[];warning_count=0;current_ids={entry.id for entry in self.corporate_store.entries()}
        for entry,events,warnings,cik,error in results:
            if entry.id not in current_ids:continue
            if error:self.corporate_store.update_status(entry.id,"Error: "+error,cik);self.diagnostics.error("Corporate monitor",f"{entry.symbol} failed",error);continue
            for warning in warnings:self.diagnostics.log("WARNING","Corporate monitor",f"{entry.symbol}: {warning}")
            added.extend(self.corporate_store.add_events(entry,events));warning_count+=len(warnings);status=f"{len(events)} event(s)"+(f" • {len(warnings)} warning(s)" if warnings else "");self.corporate_store.update_status(entry.id,status,cik)
        self.load_corporate_monitor();self.corporate_status.setText(f"Refresh complete • {len(added)} new event(s) • {warning_count} source warning(s)")
        if added:AccessibleMessageDialog.information(self,"New corporate events","\n".join(f"{event.symbol}: {event.event_type} — {event.title}" for event in added[:8]))
    def remove_corporate_entry(self):
        entry=self.selected_corporate_entry()
        if entry:self.corporate_store.remove(entry.id);self.load_corporate_monitor()
    def mark_corporate_events_read(self):self.corporate_store.mark_all_read();self.load_corporate_monitor()
    def open_corporate_event(self):
        rows=self.corporate_event_table.selectionModel().selectedRows() if self.corporate_event_table.selectionModel() else []
        if not rows:return
        row=rows[0].row();url=self.corporate_event_urls[row] if row<len(self.corporate_event_urls) else ""
        if url and QUrl(url).scheme() in {"http","https"}:QDesktopServices.openUrl(QUrl(url))
    def save_sec_email(self):
        email=self.sec_contact_email.text().strip()
        if email and "@" not in email:AccessibleMessageDialog.warning(self,"SEC contact","Enter a valid contact email.");return
        self.secure_storage.set_secret("sec_contact_email",email);self.corporate_status.setText(f"SEC contact email {'encrypted in '+self.secure_storage.backend if email else 'cleared; US SEC monitoring unavailable'}.")
    def export_batch_csv(self):
        if not self.confirm_sensitive_export("The batch CSV"):return
        path,_=QFileDialog.getSaveFileName(self,"Save batch results",f"Stock_Fair_Value_Batch_{datetime.now():%Y%m%d}.csv","CSV (*.csv)")
        if path:
            try:export_batch_csv(self.batch_records,path);AccessibleMessageDialog.information(self,"Results saved",path)
            except Exception as exc:self.show_error(str(exc))
    def export_batch_pdf(self):
        if not self.confirm_sensitive_export("The batch PDF"):return
        path,_=QFileDialog.getSaveFileName(self,"Save batch PDF",f"Stock_Fair_Value_Batch_{datetime.now():%Y%m%d}.pdf","PDF (*.pdf)")
        if path:
            try:create_batch_pdf(self.batch_records,path);AccessibleMessageDialog.information(self,"Report saved",path)
            except Exception as exc:self.show_error(str(exc))
    def save_template(self):
        path,_=QFileDialog.getSaveFileName(self,"Save template","stock_list_template.csv","CSV (*.csv)")
        if path:
            try:
                with open(path,"w",encoding="utf-8",newline="") as f:f.write("Symbol,Market\nAAPL,US\nMSFT,US\nRELIANCE,NSE\n")
            except Exception as exc:self.show_error(str(exc))
    def closeEvent(self,event):
        for store in (self.watchlist_store,self.corporate_store):
            try:store.close()
            except Exception:pass
        super().closeEvent(event)

def main():
    app=QApplication(sys.argv);app.setApplicationName("DR. NILESH SHAH - STOCKS FAIRSCOPE");app.setOrganizationName("DR. NILESH SHAH");diagnostics=get_diagnostics()
    def exception_hook(exc_type,exc_value,exc_traceback):
        diagnostics.log("CRITICAL","Unhandled exception",str(exc_value),"".join(__import__("traceback").format_exception(exc_type,exc_value,exc_traceback)));AccessibleMessageDialog.critical(None,"Unexpected error","An unexpected error was recorded. Open Diagnostics to export a support ZIP.")
    sys.excepthook=exception_hook;window=FairScopeWindow();window.show();return app.exec()
if __name__=="__main__":raise SystemExit(main())
