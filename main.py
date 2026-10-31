"""Fast Market Arbitrage Core — live terminal dashboard."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict
from datetime import datetime

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import Settings, get_settings
from core import __version__
from core.client import HttpClient
from core.engine import ArbitrageEngine

console = Console()


def _fmt_price(p: float) -> str:
    return f"{p:,.8f}".rstrip("0").rstrip(".") if p < 1 else f"{p:,.4f}"


def _fmt_vol(v: float) -> str:
    for unit, div in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if v >= div:
            return f"{v / div:.1f}{unit}"
    return f"{v:.0f}"


def render(engine: ArbitrageEngine, s: Settings) -> Layout:
    header = Text.assemble(
        ("⚡ FAST MARKET ARBITRAGE CORE ", "bold cyan"),
        (f"v{__version__}", "dim"),
        ("  │  ", "dim"),
        (f"cycle #{engine.cycles}", "bold"),
        ("  │  ", "dim"),
        (datetime.now().strftime("%H:%M:%S"), "green"),
        ("  │  ", "dim"),
        (f"fee {s.taker_fee_pct}%×2 · min net {s.min_spread_pct}% · min vol {_fmt_vol(s.min_quote_volume)}", "dim"),
    )

    venues = Table(expand=True, show_edge=False, header_style="bold magenta")
    venues.add_column("Exchange")
    venues.add_column("State")
    venues.add_column("Pairs", justify="right")
    venues.add_column("Latency", justify="right")
    for st in engine.status.values():
        state = Text("● LIVE", "green") if st.ok else Text("● DOWN", "red")
        venues.add_row(st.name.upper(), state, str(st.pairs), f"{st.latency_ms:.0f} ms")
    errors = [Text(f"{st.name}: {st.error}", "red dim") for st in engine.status.values() if st.error]

    opps = Table(expand=True, header_style="bold cyan", row_styles=["", "dim"])
    opps.add_column("#", justify="right", width=3)
    opps.add_column("Pair", style="bold")
    opps.add_column("Buy @", style="green")
    opps.add_column("Ask", justify="right")
    opps.add_column("Sell @", style="red")
    opps.add_column("Bid", justify="right")
    opps.add_column("Gross %", justify="right")
    opps.add_column("Net %", justify="right")
    opps.add_column("Min 24h Vol", justify="right")
    for i, o in enumerate(engine.opportunities[: s.top_n], 1):
        net_style = "bold green" if o.net_spread_pct >= 1 else "yellow"
        opps.add_row(
            str(i), o.symbol, o.buy_exchange, _fmt_price(o.buy_price), o.sell_exchange,
            _fmt_price(o.sell_price), f"{o.gross_spread_pct:.2f}", Text(f"{o.net_spread_pct:.2f}", net_style),
            _fmt_vol(o.min_volume),
        )
    if not engine.opportunities:
        opps.add_row("", Text("scanning… no spreads above threshold yet", "dim"), *[""] * 7)

    layout = Layout()
    layout.split_column(
        Layout(Panel(header, border_style="cyan"), size=3),
        Layout(name="body"),
    )
    layout["body"].split_row(
        Layout(Panel(Group(venues, *errors), title="Venues", border_style="magenta"), ratio=1),
        Layout(Panel(opps, title=f"Top {s.top_n} opportunities ({len(engine.opportunities)} found)",
                     border_style="green"), ratio=3),
    )
    return layout


async def run_dashboard(s: Settings) -> None:
    async with HttpClient(s) as client:
        engine = ArbitrageEngine(client, s)
        with Live(render(engine, s), console=console, refresh_per_second=4, screen=True) as live:
            while True:
                await engine.scan_once()
                live.update(render(engine, s))
                await asyncio.sleep(s.refresh_interval)


async def run_once(s: Settings, as_json: bool) -> None:
    async with HttpClient(s) as client:
        engine = ArbitrageEngine(client, s)
        opps = await engine.scan_once()
    if as_json:
        print(json.dumps([asdict(o) for o in opps[: s.top_n]], indent=2))
    else:
        console.print(render(engine, s)["body"].children[1].renderable)
        for st in engine.status.values():
            if st.error:
                console.print(f"[red]{st.name}: {st.error}[/red]")


def main() -> None:
    p = argparse.ArgumentParser(description="Real-time cross-exchange spot arbitrage scanner")
    p.add_argument("--once", action="store_true", help="run a single scan and exit")
    p.add_argument("--json", action="store_true", help="with --once: print results as JSON")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging to fma.log")
    args = p.parse_args()

    logging.basicConfig(
        filename="fma.log" if args.verbose else None,
        level=logging.DEBUG if args.verbose else logging.CRITICAL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    try:
        if args.once:
            asyncio.run(run_once(settings, args.json))
        else:
            asyncio.run(run_dashboard(settings))
    except KeyboardInterrupt:
        console.print("[dim]bye.[/dim]")


if __name__ == "__main__":
    main()
