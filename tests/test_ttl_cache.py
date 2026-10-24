import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
import ttl_cache


class TtlCacheTests(unittest.TestCase):
    def test_entries_expire_and_failures_are_not_cached(self):
        calls=[];clock=[100.0]
        @ttl_cache.ttl_cache(60,cache_if=lambda value:value is not None)
        def quote(symbol):calls.append(symbol);return None if len(calls)==1 else len(calls)
        with patch.object(ttl_cache.time,"monotonic",side_effect=lambda:clock[0]):
            self.assertIsNone(quote("TEST"));self.assertEqual(quote("TEST"),2);self.assertEqual(quote("TEST"),2)
            clock[0]+=61;self.assertEqual(quote("TEST"),3)
        quote.cache_clear();self.assertEqual(quote("TEST"),4)
    def test_maxsize_evicts_oldest_entry(self):
        calls=[]
        @ttl_cache.ttl_cache(60,maxsize=2)
        def square(value):calls.append(value);return value*value
        square(1);square(2);square(3);square(1)
        self.assertEqual(calls,[1,2,3,1])

if __name__=="__main__":unittest.main()
