from unittest.mock import patch

import pytest

import data_provider
from data_provider import DataProviderError, fetch_stock


@pytest.fixture(autouse=True)
def offline_market_lookups():
    """Peer screening and the index series call Yahoo directly; keep this offline suite off the network."""
    empty_peers={"pe":None,"pb":None,"forward_pe":None,"ev_ebitda":None,"roe":None,"growth":None,"symbols":()}
    with patch.object(data_provider,"_fetch_peers",return_value=empty_peers),patch.object(data_provider,"_index_monthly",return_value={}),patch.object(data_provider,"_live_us_risk_free",return_value=None),patch.object(data_provider,"_damodaran_country_premiums",return_value=None):
        yield

def test_fetch_stock_success():
    with patch('yfinance.Ticker') as mock_ticker:
        ticker_instance = mock_ticker.return_value
        # Mock history
        import pandas as pd
        mock_history = pd.DataFrame({
            'Close': [150.0],
            'Adj Close': [150.0],
            'Low': [140.0],
            'High': [160.0]
        }, index=pd.to_datetime(['2023-01-01']))
        ticker_instance.history.return_value = mock_history

        # Mock info
        ticker_instance.info = {
            'longName': 'Apple Inc.',
            'symbol': 'AAPL',
            'sharesOutstanding': 1000000,
            'marketCap': 150000000,
            'sector': 'Technology',
            'industry': 'Consumer Electronics',
            'currency': 'USD'
        }

        # Mock other calls
        ticker_instance.cashflow = None
        ticker_instance.income_stmt = None
        ticker_instance.balance_sheet = None

        data = fetch_stock('AAPL', 'US', force_refresh=True)
        assert data.symbol == 'AAPL'
        assert data.company == 'Apple Inc.'
        assert data.price == 150.0

def test_fetch_stock_not_found():
    with patch('yfinance.Ticker') as mock_ticker:
        ticker_instance = mock_ticker.return_value
        import pandas as pd
        ticker_instance.history.return_value = pd.DataFrame() # Empty

        with pytest.raises(DataProviderError, match="No market data found"):
            fetch_stock('INVALID', 'US', force_refresh=True)
