"""Filtering and cross-exchange arbitrage detection."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Iterable

from config import Settings
from core.client import HttpClient, fetch_exchange
from core.models import ExchangeStatus, Opportunity, Ticker


def find_opportunities(tickers: Iterable[Ticker], settings: Settings) -> list[Opportunity]:
    """For every symbol listed on 2+ venues, buy at the lowest ask and sell at the highest bid."""
    allow = set(settings.symbols)
    by_symbol: dict[str, list[Ticker]] = defaultdict(list)
    for t in tickers:
        if t.quote_volume < settings.min_quote_volume:
            continue
        if allow and t.base not in allow:
            continue
        by_symbol[t.symbol].append(t)

    fee = settings.taker_fee_pct
    result: list[Opportunity] = []
    for symbol, group in by_symbol.items():
        if len(group) < 2:
            continue
        buy = min(group, key=lambda t: t.ask)
        sell = max(group, key=lambda t: t.bid)
        if buy.exchange == sell.exchange:
            continue
        gross = (sell.bid - buy.ask) / buy.ask * 100
        if gross > settings.max_spread_pct:
            continue  # likely a different asset sharing a ticker, or a suspended market
        net = gross - 2 * fee
        if net < settings.min_spread_pct:
            continue
        result.append(
            Opportunity(
                symbol=symbol,
                buy_exchange=buy.exchange,
                buy_price=buy.ask,
                sell_exchange=sell.exchange,
                sell_price=sell.bid,
                gross_spread_pct=gross,
                net_spread_pct=net,
                min_volume=min(buy.quote_volume, sell.quote_volume),
            )
        )
    result.sort(key=lambda o: o.net_spread_pct, reverse=True)
    return result


class ArbitrageEngine:
    def __init__(self, client: HttpClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings
        self.status = {name: ExchangeStatus(name) for name in settings.exchanges}
        self.opportunities: list[Opportunity] = []
        self.cycles = 0

    async def scan_once(self) -> list[Opportunity]:
        results = await asyncio.gather(
            *(
                fetch_exchange(self.client, name, self.settings.quote_asset, self.status[name])
                for name in self.settings.exchanges
            )
        )
        tickers = [t for batch in results for t in batch]
        self.opportunities = find_opportunities(tickers, self.settings)
        self.cycles += 1
        return self.opportunities
