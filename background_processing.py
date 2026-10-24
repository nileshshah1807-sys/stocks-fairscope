"""Cancellation, pause/resume, retry/backoff, and bounded parallel analysis helpers."""
from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Optional

from batch_import import BatchItem
from data_provider import fetch_stock, is_transient_error
from logger import get_logger
from valuation import ValuationResult, value_stock

logger = get_logger("BackgroundProcessing")


@dataclass
class ItemOutcome:
    index:int
    item:BatchItem
    result:Optional[ValuationResult]
    error:str=""
    attempts:int=1
    cancelled:bool=False

class JobControl:
    def __init__(self):self._cancel=threading.Event();self._pause=threading.Event();self._pause.set()
    @property
    def cancelled(self):return self._cancel.is_set()
    @property
    def paused(self):return not self._pause.is_set()
    def cancel(self):self._cancel.set();self._pause.set()
    def pause(self):self._pause.clear()
    def resume(self):self._pause.set()
    def checkpoint(self):
        while not self._pause.wait(.2):
            if self.cancelled:return False
        return not self.cancelled

def analyze_with_retry(index:int,item:BatchItem,control:JobControl,retries:int=3,force_refresh:bool=False)->ItemOutcome:
    attempts=0;last_error=""
    while attempts<max(1,retries):
        if not control.checkpoint():return ItemOutcome(index,item,None,"Cancelled",attempts or 1,True)
        attempts+=1
        try:return ItemOutcome(index,item,value_stock(fetch_stock(item.symbol,item.market,force_refresh=force_refresh)),"",attempts,False)
        except Exception as exc:
            last_error=str(exc)
            if attempts>=retries or not is_transient_error(last_error):break
            delay=min(8.0,.8*(2**(attempts-1)))+random.uniform(0,.35)
            deadline=time.monotonic()+delay
            while time.monotonic()<deadline:
                if control.cancelled:return ItemOutcome(index,item,None,"Cancelled",attempts,True)
                if not control.checkpoint():return ItemOutcome(index,item,None,"Cancelled",attempts,True)
                time.sleep(min(.2,max(0,deadline-time.monotonic())))
    return ItemOutcome(index,item,None,last_error,attempts,False)
