"""Application settings loaded from environment variables / .env file."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_EXCHANGES = ("binance", "bybit", "okx", "kucoin", "gateio")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="FMA_",
        extra="ignore",
    )

    # Which venues to poll
    exchanges: list[str] = Field(default_factory=lambda: list(SUPPORTED_EXCHANGES))
    # Quote asset used to normalise symbols (BTC/USDT, ETH/USDT, ...)
    quote_asset: str = "USDT"
    # Optional allow-list of base assets; empty = all common symbols
    symbols: list[str] = Field(default_factory=list)

    # Opportunity filters
    min_spread_pct: float = Field(0.3, ge=0)
    max_spread_pct: float = Field(15.0, gt=0)  # anything above is almost always a delisted / stale pair
    min_quote_volume: float = Field(50_000, ge=0)  # 24h volume in quote asset, per venue
    taker_fee_pct: float = Field(0.1, ge=0)  # applied on both legs

    # Network
    refresh_interval: float = Field(5.0, gt=0)
    request_timeout: float = Field(10.0, gt=0)
    max_concurrency: int = Field(10, ge=1)
    max_retries: int = Field(3, ge=0)
    proxies: list[str] = Field(default_factory=list)  # http://user:pass@host:port, rotated round-robin

    # UI
    top_n: int = Field(20, ge=1)

    @field_validator("exchanges", "symbols", "proxies", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v

    @field_validator("exchanges")
    @classmethod
    def _check_exchanges(cls, v: list[str]) -> list[str]:
        v = [e.lower() for e in v]
        unknown = set(v) - set(SUPPORTED_EXCHANGES)
        if unknown:
            raise ValueError(f"Unsupported exchanges: {sorted(unknown)}. Supported: {SUPPORTED_EXCHANGES}")
        if len(v) < 2:
            raise ValueError("At least two exchanges are required for arbitrage")
        return v

    @field_validator("quote_asset")
    @classmethod
    def _upper_quote(cls, v: str) -> str:
        return v.upper()

    @field_validator("symbols")
    @classmethod
    def _upper_symbols(cls, v: list[str]) -> list[str]:
        return [s.upper() for s in v]


@lru_cache
def get_settings() -> Settings:
    return Settings()
