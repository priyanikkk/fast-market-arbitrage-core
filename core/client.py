"""Async HTTP client with proxy rotation, retries and per-exchange ticker adapters.

All endpoints used are public, unauthenticated market-data endpoints. No API keys,
no order placement.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import random
from collections.abc import Callable, Iterable
from time import perf_counter
from typing import Any

import aiohttp

from config import Settings
from core.models import ExchangeStatus, Ticker

log = logging.getLogger(__name__)


class ProxyPool:
    """Round-robin proxy rotation. Empty pool means direct connection."""

    def __init__(self, proxies: Iterable[str]) -> None:
        self._proxies = list(proxies)
        self._cycle = itertools.cycle(self._proxies) if self._proxies else None

    def next(self) -> str | None:
        return next(self._cycle) if self._cycle else None

    def __len__(self) -> int:
        return len(self._proxies)


class HttpClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._proxies = ProxyPool(settings.proxies)
        self._sem = asyncio.Semaphore(settings.max_concurrency)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> HttpClient:
        timeout = aiohttp.ClientTimeout(total=self._settings.request_timeout)
        connector = aiohttp.TCPConnector(limit=self._settings.max_concurrency * 2, ttl_dns_cache=300)
        self._session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"User-Agent": "fast-market-arbitrage-core/1.0", "Accept": "application/json"},
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._session:
            await self._session.close()

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        assert self._session is not None, "HttpClient must be used as an async context manager"
        last_exc: Exception | None = None
        for attempt in range(self._settings.max_retries + 1):
            proxy = self._proxies.next()
            try:
                async with self._sem, self._session.get(url, params=params, proxy=proxy) as resp:
                    if resp.status == 429 or resp.status >= 500:
                        raise aiohttp.ClientResponseError(
                            resp.request_info, resp.history, status=resp.status, message=resp.reason or ""
                        )
                    resp.raise_for_status()
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exc = exc
                if isinstance(exc, aiohttp.ClientResponseError) and 400 <= exc.status < 500 and exc.status != 429:
                    break  # non-retryable
                backoff = min(2**attempt, 8) * 0.25 + random.uniform(0, 0.25)
                log.debug("GET %s failed (%s), retry in %.2fs", url, exc, backoff)
                await asyncio.sleep(backoff)
        raise RuntimeError(f"GET {url} failed: {last_exc}") from last_exc


# --------------------------------------------------------------------------- adapters

def _f(x: Any) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _split(symbol: str, quote: str, sep: str = "") -> str | None:
    """Return base asset if `symbol` is quoted in `quote`, else None."""
    if sep:
        parts = symbol.split(sep)
        return parts[0] if len(parts) == 2 and parts[1] == quote else None
    return symbol[: -len(quote)] if symbol.endswith(quote) and len(symbol) > len(quote) else None


def _valid(bid: float, ask: float) -> bool:
    return bid > 0 and ask > 0 and ask >= bid


async def fetch_binance(c: HttpClient, quote: str) -> list[Ticker]:
    data = await c.get_json("https://api.binance.com/api/v3/ticker/24hr")
    out = []
    for t in data:
        base = _split(t["symbol"], quote)
        bid, ask = _f(t.get("bidPrice")), _f(t.get("askPrice"))
        if base and _valid(bid, ask):
            out.append(Ticker("binance", base, quote, bid, ask, _f(t.get("quoteVolume"))))
    return out


async def fetch_bybit(c: HttpClient, quote: str) -> list[Ticker]:
    data = await c.get_json("https://api.bybit.com/v5/market/tickers", {"category": "spot"})
    out = []
    for t in data.get("result", {}).get("list", []):
        base = _split(t["symbol"], quote)
        bid, ask = _f(t.get("bid1Price")), _f(t.get("ask1Price"))
        if base and _valid(bid, ask):
            out.append(Ticker("bybit", base, quote, bid, ask, _f(t.get("turnover24h"))))
    return out


async def fetch_okx(c: HttpClient, quote: str) -> list[Ticker]:
    data = await c.get_json("https://www.okx.com/api/v5/market/tickers", {"instType": "SPOT"})
    out = []
    for t in data.get("data", []):
        base = _split(t["instId"], quote, "-")
        bid, ask = _f(t.get("bidPx")), _f(t.get("askPx"))
        if base and _valid(bid, ask):
            # volCcy24h is quote-currency volume for SPOT
            out.append(Ticker("okx", base, quote, bid, ask, _f(t.get("volCcy24h"))))
    return out


async def fetch_kucoin(c: HttpClient, quote: str) -> list[Ticker]:
    data = await c.get_json("https://api.kucoin.com/api/v1/market/allTickers")
    out = []
    for t in data.get("data", {}).get("ticker", []):
        base = _split(t["symbol"], quote, "-")
        bid, ask = _f(t.get("buy")), _f(t.get("sell"))
        if base and _valid(bid, ask):
            out.append(Ticker("kucoin", base, quote, bid, ask, _f(t.get("volValue"))))
    return out


async def fetch_gateio(c: HttpClient, quote: str) -> list[Ticker]:
    data = await c.get_json("https://api.gateio.ws/api/v4/spot/tickers")
    out = []
    for t in data:
        base = _split(t["currency_pair"], quote, "_")
        bid, ask = _f(t.get("highest_bid")), _f(t.get("lowest_ask"))
        if base and _valid(bid, ask):
            out.append(Ticker("gateio", base, quote, bid, ask, _f(t.get("quote_volume"))))
    return out


FETCHERS: dict[str, Callable[[HttpClient, str], Any]] = {
    "binance": fetch_binance,
    "bybit": fetch_bybit,
    "okx": fetch_okx,
    "kucoin": fetch_kucoin,
    "gateio": fetch_gateio,
}


async def fetch_exchange(c: HttpClient, name: str, quote: str, status: ExchangeStatus) -> list[Ticker]:
    """Fetch one venue, updating its status in place. Never raises."""
    start = perf_counter()
    try:
        tickers = await FETCHERS[name](c, quote)
        status.ok, status.pairs, status.error = True, len(tickers), None
        return tickers
    except Exception as exc:  # noqa: BLE001 - surface any adapter failure in the dashboard
        status.ok, status.error = False, str(exc)[:120]
        log.warning("%s fetch failed: %s", name, exc)
        return []
    finally:
        status.latency_ms = (perf_counter() - start) * 1000
        status.last_update = asyncio.get_running_loop().time()
