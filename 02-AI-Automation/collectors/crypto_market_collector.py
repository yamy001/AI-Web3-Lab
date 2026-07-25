"""Collect BTC and ETH market data from CoinGecko's public API."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = "https://api.coingecko.com/api/v3/simple/price"
COIN_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
}
OUTPUT_DIRECTORY = Path(__file__).resolve().parent.parent / "data" / "raw"
REQUEST_TIMEOUT_SECONDS = 15


class MarketDataError(RuntimeError):
    """Raised when market data cannot be fetched or validated."""


def fetch_market_data() -> dict[str, Any]:
    """Fetch and normalize BTC and ETH market data in USD."""
    query = urlencode(
        {
            "ids": ",".join(COIN_IDS.values()),
            "vs_currencies": "usd",
            "include_market_cap": "true",
            "include_24hr_change": "true",
            "include_last_updated_at": "true",
        }
    )
    request = Request(
        f"{API_URL}?{query}",
        headers={
            "Accept": "application/json",
            "User-Agent": "AI-Web3-Lab/1.0",
        },
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except HTTPError as exc:
        raise MarketDataError(
            f"CoinGecko returned HTTP {exc.code}: {exc.reason}"
        ) from exc
    except URLError as exc:
        raise MarketDataError(f"Unable to reach CoinGecko: {exc.reason}") from exc
    except (TimeoutError, json.JSONDecodeError) as exc:
        raise MarketDataError(f"Invalid or timed-out CoinGecko response: {exc}") from exc

    if not isinstance(payload, dict):
        raise MarketDataError("CoinGecko returned an unexpected response format.")

    assets: dict[str, dict[str, Any]] = {}
    for symbol, coin_id in COIN_IDS.items():
        coin_data = payload.get(coin_id)
        if not isinstance(coin_data, dict):
            raise MarketDataError(f"CoinGecko response is missing {coin_id} data.")

        required_fields = (
            "usd",
            "usd_market_cap",
            "usd_24h_change",
            "last_updated_at",
        )
        missing_fields = [
            field for field in required_fields if coin_data.get(field) is None
        ]
        if missing_fields:
            raise MarketDataError(
                f"{coin_id} data is missing fields: {', '.join(missing_fields)}"
            )

        timestamp = datetime.fromtimestamp(
            coin_data["last_updated_at"], tz=timezone.utc
        ).isoformat()
        assets[symbol] = {
            "price": coin_data["usd"],
            "market_cap": coin_data["usd_market_cap"],
            "24h_change": coin_data["usd_24h_change"],
            "timestamp": timestamp,
        }

    return {
        "source": "CoinGecko",
        "currency": "USD",
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "assets": assets,
    }


def save_market_data(market_data: dict[str, Any]) -> Path:
    """Save market data to a date-stamped JSON file."""
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = OUTPUT_DIRECTORY / f"crypto_market_{date_stamp}.json"

    try:
        with output_path.open("w", encoding="utf-8") as output_file:
            json.dump(market_data, output_file, ensure_ascii=False, indent=2)
            output_file.write("\n")
    except OSError as exc:
        raise MarketDataError(f"Unable to save market data: {exc}") from exc

    return output_path


def main() -> int:
    """Fetch market data and save it locally."""
    try:
        market_data = fetch_market_data()
        output_path = save_market_data(market_data)
    except MarketDataError as exc:
        print(f"Market data collection failed: {exc}", file=sys.stderr)
        return 1

    print(f"Market data saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
