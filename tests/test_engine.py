from config import Settings
from core.client import _split
from core.engine import find_opportunities
from core.models import Ticker


def S(**kw):
    base = dict(exchanges=["binance", "bybit"], min_spread_pct=0.0, min_quote_volume=0, taker_fee_pct=0.1)
    base.update(kw)
    return Settings(_env_file=None, **base)


def T(ex, base, bid, ask, vol=1e6):
    return Ticker(ex, base, "USDT", bid, ask, vol)


def test_detects_cross_exchange_spread():
    opps = find_opportunities([T("binance", "BTC", 99, 100), T("bybit", "BTC", 102, 103)], S())
    assert len(opps) == 1
    o = opps[0]
    assert (o.buy_exchange, o.sell_exchange) == ("binance", "bybit")
    assert round(o.gross_spread_pct, 4) == 2.0
    assert round(o.net_spread_pct, 4) == 1.8


def test_no_opportunity_when_books_overlap():
    assert find_opportunities([T("binance", "ETH", 99, 100), T("bybit", "ETH", 99.5, 100.5)], S()) == []


def test_volume_and_outlier_filters():
    ticks = [T("binance", "X", 1, 1.01, vol=10), T("bybit", "X", 1.5, 1.6)]
    assert find_opportunities(ticks, S(min_quote_volume=100)) == []
    assert find_opportunities([T("binance", "Y", 1, 1.01), T("bybit", "Y", 2, 2.1)], S()) == []


def test_symbol_allow_list():
    ticks = [T("binance", "BTC", 99, 100), T("bybit", "BTC", 102, 103),
             T("binance", "SOL", 9, 10), T("bybit", "SOL", 11, 12)]
    assert [o.symbol for o in find_opportunities(ticks, S(symbols=["sol"]))] == ["SOL/USDT"]


def test_split_symbols():
    assert _split("BTCUSDT", "USDT") == "BTC"
    assert _split("ETH-USDT", "USDT", "-") == "ETH"
    assert _split("ETH-BTC", "USDT", "-") is None
    assert _split("USDT", "USDT") is None
