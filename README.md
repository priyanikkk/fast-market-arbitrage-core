<div align="center">

# ⚡ Fast Market Arbitrage Core

**Real-time, asynchronous cross-exchange spot arbitrage scanner with a live terminal dashboard.**

[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![asyncio](https://img.shields.io/badge/async-aiohttp-2C5BB4?logo=aiohttp&logoColor=white)](https://docs.aiohttp.org/)
[![Rich](https://img.shields.io/badge/TUI-rich-FF6F00)](https://github.com/Textualize/rich)
[![Pydantic](https://img.shields.io/badge/config-pydantic%20v2-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED?logo=docker&logoColor=white)](#-docker)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

Fast Market Arbitrage Core polls the public order-book tickers of **Binance, Bybit, OKX, KuCoin and Gate.io** concurrently, normalises thousands of spot pairs into a single view, and surfaces price gaps between venues **after trading fees**, ranked live in your terminal.

It is **read-only by design**: no API keys, no order placement, no custody. It's a market-intelligence engine you can run on its own or use as the detection layer of your own execution stack.

## ✨ Features

| | |
|---|---|
| 🚀 **Fully async** | One `aiohttp` session, every venue fetched in parallel via `asyncio.gather`, bounded by a concurrency semaphore. |
| 🌐 **Proxy rotation** | Round-robin HTTP(S) proxy pool with automatic failover on each retry. |
| 🔁 **Resilient networking** | Exponential backoff with jitter on timeouts, `429` and `5xx`; one failing venue never stalls the others. |
| 🧮 **Fee-aware engine** | Best ask vs. best bid across all venues, net spread = gross − 2 × taker fee. |
| 🧹 **Noise filters** | Minimum 24h quote volume per leg, minimum net spread, and a max-spread guard that drops stale or delisted markets and ticker collisions. |
| 📊 **Live Rich dashboard** | Full-screen TUI with venue health (status, pair count, latency) and a ranked opportunity board. |
| 🧾 **Headless mode** | `--once --json` for cron jobs, bots, and piping into other tools. |
| ⚙️ **Typed config** | Pydantic v2 settings from environment variables or `.env`, validated at startup. |
| 🐳 **Docker-ready** | Slim, non-root image. |

## 🏗 Architecture

```
                         ┌──────────────────────────────┐
                         │   config.py  (Pydantic v2)   │
                         │   .env  →  Settings          │
                         └──────────────┬───────────────┘
                                        │
┌────────────────┐   scan_once()   ┌────▼──────────────────┐    asyncio.gather    ┌──────────────────────┐
│    main.py     │ ──────────────▶ │   core/engine.py      │ ───────────────────▶ │   core/client.py     │
│  Rich Live TUI │ ◀────────────── │   ArbitrageEngine     │ ◀─────────────────── │  HttpClient          │
│  --once/--json │  opportunities  │   find_opportunities  │    list[Ticker]      │  ProxyPool · retries │
└────────────────┘                 └───────────────────────┘                      │  exchange adapters   │
                                                                                  └──────────┬───────────┘
                                                                                             │ HTTPS (public REST)
                                              ┌──────────┬──────────┬──────────┬────────────┼──────────┐
                                              ▼          ▼          ▼          ▼            ▼
                                           Binance     Bybit       OKX       KuCoin      Gate.io
```

**Pipeline per cycle**

1. **Fetch:** each adapter pulls the full spot ticker snapshot from one venue in a single request.
2. **Normalise:** symbols are mapped to `BASE/QUOTE`; zero or crossed books are discarded.
3. **Filter:** legs below `MIN_QUOTE_VOLUME` and bases outside the optional allow-list are dropped.
4. **Detect:** for each pair listed on 2+ venues, *buy at the lowest ask* and *sell at the highest bid*.
5. **Rank:** results are sorted by net spread and rendered.

## 📁 Project layout

```
fast-market-arbitrage-core/
├── main.py              # Rich dashboard + CLI entrypoint
├── config.py            # Pydantic settings (.env)
├── core/
│   ├── client.py        # aiohttp client, proxy pool, retry logic, exchange adapters
│   ├── engine.py        # filtering + arbitrage detection
│   └── models.py        # Ticker / Opportunity / ExchangeStatus dataclasses
├── tests/               # pytest suite for the engine
├── requirements.txt
├── .env.example
└── Dockerfile
```

## 🚀 Quick start

```bash
git clone https://github.com/priyanikkk/fast-market-arbitrage-core.git
cd fast-market-arbitrage-core

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # optional: tweak filters, proxies, venues
python main.py            # live dashboard (Ctrl+C to quit)
```

### CLI

```bash
python main.py                 # full-screen live dashboard
python main.py --once          # single scan, print table, exit
python main.py --once --json   # single scan, machine-readable output
python main.py -v              # debug logging to fma.log
```

Sample JSON output:

```json
[
  {
    "symbol": "TRX/USDT",
    "buy_exchange": "binance",
    "buy_price": 0.3181,
    "sell_exchange": "kucoin",
    "sell_price": 0.3257,
    "gross_spread_pct": 2.39,
    "net_spread_pct": 2.19,
    "min_volume": 12800000.0
  }
]
```

## 🐳 Docker

```bash
docker build -t fast-market-arbitrage-core .
docker run --rm -it --env-file .env fast-market-arbitrage-core
docker run --rm --env-file .env fast-market-arbitrage-core --once --json
```

## ⚙️ Configuration

All settings are read from the environment (prefix `FMA_`) or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `FMA_EXCHANGES` | `binance,bybit,okx,kucoin,gateio` | Venues to scan (min. 2) |
| `FMA_QUOTE_ASSET` | `USDT` | Quote currency used to match pairs |
| `FMA_SYMBOLS` | *(empty)* | Optional base-asset allow-list, e.g. `BTC,ETH,SOL` |
| `FMA_MIN_SPREAD_PCT` | `0.3` | Minimum **net** spread to display |
| `FMA_MAX_SPREAD_PCT` | `15` | Gross spreads above this are treated as bad data |
| `FMA_MIN_QUOTE_VOLUME` | `50000` | Minimum 24h quote volume on **each** leg |
| `FMA_TAKER_FEE_PCT` | `0.1` | Taker fee applied to both legs |
| `FMA_REFRESH_INTERVAL` | `5` | Seconds between scan cycles |
| `FMA_REQUEST_TIMEOUT` | `10` | Per-request timeout (s) |
| `FMA_MAX_CONCURRENCY` | `10` | Max in-flight HTTP requests |
| `FMA_MAX_RETRIES` | `3` | Retries on timeout / 429 / 5xx |
| `FMA_PROXIES` | *(empty)* | Comma-separated proxy URLs, rotated round-robin |
| `FMA_TOP_N` | `20` | Rows shown in the dashboard |

## 🧩 Adding an exchange

Write an adapter in `core/client.py` that returns `list[Ticker]`, register it in `FETCHERS`, and add its name to `SUPPORTED_EXCHANGES` in `config.py`:

```python
async def fetch_myexchange(c: HttpClient, quote: str) -> list[Ticker]:
    data = await c.get_json("https://api.myexchange.com/spot/tickers")
    return [
        Ticker("myexchange", base, quote, float(t["bid"]), float(t["ask"]), float(t["quoteVol"]))
        for t in data
        if (base := _split(t["symbol"], quote, "-"))
    ]
```

## 🧪 Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

## ⚠️ Disclaimer

A displayed spread is **not** guaranteed profit. Real-world execution depends on order-book depth, withdrawal and network fees, transfer times, deposit/withdrawal suspensions, and tickers that share a name but refer to different assets. This software is provided for research and educational purposes. It is not financial advice.

## 📄 License

[MIT](LICENSE)
