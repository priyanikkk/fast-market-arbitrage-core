from __future__ import annotations

from dataclasses import dataclass, field
from time import time


@dataclass(slots=True, frozen=True)
class Ticker:
    exchange: str
    base: str
    quote: str
    bid: float
    ask: float
    quote_volume: float
    ts: float = field(default_factory=time)

    @property
    def symbol(self) -> str:
        return f"{self.base}/{self.quote}"


@dataclass(slots=True, frozen=True)
class Opportunity:
    symbol: str
    buy_exchange: str
    buy_price: float  # best ask on the cheap venue
    sell_exchange: str
    sell_price: float  # best bid on the expensive venue
    gross_spread_pct: float
    net_spread_pct: float
    min_volume: float


@dataclass(slots=True)
class ExchangeStatus:
    name: str
    ok: bool = False
    pairs: int = 0
    latency_ms: float = 0.0
    error: str | None = None
    last_update: float = 0.0
