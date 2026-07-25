"""Generate local crypto content from a saved CoinGecko market snapshot."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
RAW_DATA_DIRECTORY = PROJECT_DIRECTORY / "data" / "raw"
PROCESSED_DATA_DIRECTORY = PROJECT_DIRECTORY / "data" / "processed"
REQUIRED_ASSETS = ("BTC", "ETH")
REQUIRED_FIELDS = ("price", "24h_change", "timestamp")


class ContentGenerationError(RuntimeError):
    """Raised when local market content cannot be generated."""


def load_market_data(date_stamp: str) -> dict[str, Any]:
    """Load and validate a local date-stamped market JSON file."""
    input_path = RAW_DATA_DIRECTORY / f"crypto_market_{date_stamp}.json"

    try:
        with input_path.open("r", encoding="utf-8") as input_file:
            market_data = json.load(input_file)
    except FileNotFoundError as exc:
        raise ContentGenerationError(
            f"Market data file was not found: {input_path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContentGenerationError(
            f"Market data file contains invalid JSON: {exc}"
        ) from exc
    except OSError as exc:
        raise ContentGenerationError(f"Unable to read market data: {exc}") from exc

    if not isinstance(market_data, dict):
        raise ContentGenerationError("Market data must be a JSON object.")

    assets = market_data.get("assets")
    if not isinstance(assets, dict):
        raise ContentGenerationError("Market data is missing the assets object.")

    for symbol in REQUIRED_ASSETS:
        asset_data = assets.get(symbol)
        if not isinstance(asset_data, dict):
            raise ContentGenerationError(f"Market data is missing {symbol}.")

        missing_fields = [
            field for field in REQUIRED_FIELDS if asset_data.get(field) is None
        ]
        if missing_fields:
            raise ContentGenerationError(
                f"{symbol} is missing fields: {', '.join(missing_fields)}"
            )

        for field in ("price", "24h_change"):
            if not isinstance(asset_data[field], (int, float)):
                raise ContentGenerationError(
                    f"{symbol}.{field} must be a number."
                )

    return market_data


def format_price(value: float) -> str:
    """Format a USD price for human-readable content."""
    return f"${value:,.2f}"


def format_change(value: float) -> str:
    """Format a percentage change with an explicit sign."""
    return f"{value:+.2f}%"


def build_market_summary(btc_change: float, eth_change: float) -> str:
    """Create a neutral rule-based summary from BTC and ETH changes."""
    average_change = (btc_change + eth_change) / 2

    if btc_change > 0 and eth_change > 0:
        direction = "BTC 与 ETH 过去 24 小时同步上涨，市场短线表现偏强。"
    elif btc_change < 0 and eth_change < 0:
        direction = "BTC 与 ETH 过去 24 小时同步下跌，市场短线承压。"
    else:
        direction = "BTC 与 ETH 过去 24 小时走势分化，市场方向暂不一致。"

    if abs(average_change) >= 5:
        volatility = "当前波动幅度较大，需要关注价格快速变化风险。"
    elif abs(average_change) >= 2:
        volatility = "当前市场存在一定波动，建议继续观察后续走势。"
    else:
        volatility = "当前整体波动相对有限，但短期走势仍可能变化。"

    return f"{direction}{volatility}"


def generate_content(market_data: dict[str, Any], date_stamp: str) -> tuple[str, str]:
    """Generate an X post and a detailed Markdown market report."""
    btc = market_data["assets"]["BTC"]
    eth = market_data["assets"]["ETH"]
    summary = build_market_summary(btc["24h_change"], eth["24h_change"])
    risk_notice = (
        "风险提示：加密资产价格波动较大，以上内容仅为市场数据摘要，"
        "不构成任何投资建议。"
    )

    x_post = "\n".join(
        [
            f"加密市场日报｜{date_stamp}",
            "",
            f"BTC：{format_price(btc['price'])}（24H {format_change(btc['24h_change'])}）",
            f"ETH：{format_price(eth['price'])}（24H {format_change(eth['24h_change'])}）",
            "",
            summary,
            "",
            risk_notice,
            "",
        ]
    )

    market_report = "\n".join(
        [
            f"# 加密市场日报｜{date_stamp}",
            "",
            "## 市场数据",
            "",
            "| 资产 | 当前价格（USD） | 24 小时涨跌 | 数据时间（UTC） |",
            "| --- | ---: | ---: | --- |",
            (
                f"| BTC | {format_price(btc['price'])} | "
                f"{format_change(btc['24h_change'])} | {btc['timestamp']} |"
            ),
            (
                f"| ETH | {format_price(eth['price'])} | "
                f"{format_change(eth['24h_change'])} | {eth['timestamp']} |"
            ),
            "",
            "## 市场摘要",
            "",
            summary,
            "",
            "## 风险提示",
            "",
            risk_notice,
            "",
            f"数据来源：{market_data.get('source', '本地行情文件')}",
            "",
        ]
    )

    return x_post, market_report


def save_content(x_post: str, market_report: str, date_stamp: str) -> tuple[Path, Path]:
    """Save generated content to date-stamped Markdown files."""
    try:
        PROCESSED_DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        x_post_path = PROCESSED_DATA_DIRECTORY / f"x_post_{date_stamp}.md"
        report_path = PROCESSED_DATA_DIRECTORY / f"market_report_{date_stamp}.md"
        x_post_path.write_text(x_post, encoding="utf-8")
        report_path.write_text(market_report, encoding="utf-8")
    except OSError as exc:
        raise ContentGenerationError(f"Unable to save generated content: {exc}") from exc

    return x_post_path, report_path


def main() -> int:
    """Read today's local market data and generate content files."""
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        market_data = load_market_data(date_stamp)
        x_post, market_report = generate_content(market_data, date_stamp)
        output_paths = save_content(x_post, market_report, date_stamp)
    except ContentGenerationError as exc:
        print(f"Content generation failed: {exc}", file=sys.stderr)
        return 1

    for output_path in output_paths:
        print(f"Content saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
