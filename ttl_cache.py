"""Thread-safe, time-limited memoization for public-website lookups."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from functools import wraps


def ttl_cache(seconds:float,maxsize:int=256,cache_if=None):
    """Like functools.lru_cache, but entries expire so long sessions see fresh quotes and retry failed lookups.

    cache_if optionally receives the result and returns False for values that must not be stored (for example failures).
    """
    def decorator(function):
        entries=OrderedDict();lock=threading.Lock()
        @wraps(function)
        def wrapper(*args,**kwargs):
            key=(args,tuple(sorted(kwargs.items())));now=time.monotonic()
            with lock:
                hit=entries.get(key)
                if hit is not None and hit[0]>now:entries.move_to_end(key);return hit[1]
            value=function(*args,**kwargs)
            if cache_if is None or cache_if(value):
                with lock:
                    entries[key]=(now+seconds,value);entries.move_to_end(key)
                    while len(entries)>maxsize:entries.popitem(last=False)
            return value
        def cache_clear():
            with lock:entries.clear()
        wrapper.cache_clear=cache_clear
        return wrapper
    return decorator
