"""Generate a daily Web3 report from local market and news JSON files."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_DIRECTORY = Path(__file__).resolve().parent.parent
RAW_DATA_DIRECTORY = PROJECT_DIRECTORY / "data" / "raw"
PROCESSED_DATA_DIRECTORY = PROJECT_DIRECTORY / "data" / "processed"
MAX_NEWS_ITEMS_PER_SECTION = 5

INPUT_FILE_PATTERNS = {
    "market": "crypto_market_{date}.json",
    "ai_news": "ai_news_{date}.json",
    "web3_news": "web3_news_{date}.json",
}

FOCUS_KEYWORDS = {
    "AI 基础设施与算力": ("gpu", "chip", "compute", "data center", "算力", "芯片"),
    "AI 模型与智能体": ("model", "agent", "llm", "模型", "智能体"),
    "区块链基础设施": (
        "layer 2",
        "rollup",
        "blockchain",
        "ethereum",
        "solana",
        "区块链",
    ),
    "稳定币与现实世界资产": (
        "stablecoin",
        "rwa",
        "real-world asset",
        "ondo",
        "稳定币",
    ),
    "监管与合规": ("regulation", "regulatory", "sec", "policy", "监管", "合规"),
}


class AnalysisError(RuntimeError):
    """Raised when local news analysis cannot be completed."""


def load_json(path: Path) -> dict[str, Any]:
    """Load a local JSON object with readable error messages."""
    try:
        with path.open("r", encoding="utf-8") as input_file:
            data = json.load(input_file)
    except FileNotFoundError as exc:
        raise AnalysisError(f"Required input file was not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise AnalysisError(f"Invalid JSON in {path.name}: {exc}") from exc
    except OSError as exc:
        raise AnalysisError(f"Unable to read {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise AnalysisError(f"{path.name} must contain a JSON object.")
    return data


def load_daily_inputs(date_stamp: str) -> dict[str, dict[str, Any]]:
    """Load the three required local datasets for a date."""
    return {
        name: load_json(
            RAW_DATA_DIRECTORY / filename.format(date=date_stamp)
        )
        for name, filename in INPUT_FILE_PATTERNS.items()
    }


def validate_market_data(market_data: dict[str, Any]) -> None:
    """Validate the minimum BTC and ETH fields needed by the report."""
    assets = market_data.get("assets")
    if not isinstance(assets, dict):
        raise AnalysisError("Market data is missing the assets object.")

    for symbol in ("BTC", "ETH"):
        asset = assets.get(symbol)
        if not isinstance(asset, dict):
            raise AnalysisError(f"Market data is missing {symbol}.")
        for field in ("price", "24h_change", "timestamp"):
            if asset.get(field) is None:
                raise AnalysisError(f"Market data is missing {symbol}.{field}.")
        if not isinstance(asset["price"], (int, float)):
            raise AnalysisError(f"{symbol}.price must be a number.")
        if not isinstance(asset["24h_change"], (int, float)):
            raise AnalysisError(f"{symbol}.24h_change must be a number.")


def get_articles(news_data: dict[str, Any], label: str) -> list[dict[str, Any]]:
    """Return valid normalized articles from a collector result."""
    articles = news_data.get("articles")
    if not isinstance(articles, list):
        raise AnalysisError(f"{label} data is missing the articles list.")

    valid_articles = []
    for article in articles:
        if (
            isinstance(article, dict)
            and isinstance(article.get("title"), str)
            and article["title"].strip()
        ):
            valid_articles.append(article)
    return valid_articles


def format_price(value: float) -> str:
    return f"${value:,.2f}"


def format_change(value: float) -> str:
    return f"{value:+.2f}%"


def build_market_summary(btc_change: float, eth_change: float) -> str:
    """Describe direction and volatility without making a trade recommendation."""
    if btc_change > 0 and eth_change > 0:
        direction = "BTC 与 ETH 在过去 24 小时同步上涨，市场短线表现偏强。"
    elif btc_change < 0 and eth_change < 0:
        direction = "BTC 与 ETH 在过去 24 小时同步下跌，市场短线承压。"
    else:
        direction = "BTC 与 ETH 在过去 24 小时走势分化，市场方向尚不一致。"

    largest_move = max(abs(btc_change), abs(eth_change))
    if largest_move >= 5:
        volatility = "主要资产波动较大，应优先控制风险。"
    elif largest_move >= 2:
        volatility = "主要资产存在一定波动，后续走势仍需观察。"
    else:
        volatility = "主要资产整体波动相对有限。"
    return f"{direction}{volatility}"


def format_news_items(articles: list[dict[str, Any]]) -> list[str]:
    """Format a limited number of news items as Markdown bullets."""
    if not articles:
        return ["- 今日没有可用的本地新闻记录。"]

    lines = []
    for article in articles[:MAX_NEWS_ITEMS_PER_SECTION]:
        title = article["title"].strip()
        source = str(article.get("source") or "未知来源").strip()
        url = str(article.get("url") or "").strip()
        if url:
            lines.append(f"- [{title}]({url})（{source}）")
        else:
            lines.append(f"- {title}（{source}）")
    return lines


def find_focus_areas(
    ai_articles: list[dict[str, Any]], web3_articles: list[dict[str, Any]]
) -> list[str]:
    """Identify possible research themes from headline keyword frequency."""
    searchable_text = " ".join(
        str(article.get("title", "")) + " " + str(article.get("summary", ""))
        for article in ai_articles + web3_articles
    ).lower()

    matches: list[tuple[int, str]] = []
    for topic, keywords in FOCUS_KEYWORDS.items():
        score = sum(searchable_text.count(keyword.lower()) for keyword in keywords)
        if score:
            matches.append((score, topic))

    matches.sort(key=lambda item: (-item[0], item[1]))
    if not matches:
        return ["- 暂无足够的关键词信号，建议继续积累本地新闻数据。"]
    return [
        f"- {topic}：相关关键词出现 {score} 次，建议作为信息跟踪方向。"
        for score, topic in matches[:3]
    ]


def generate_report(
    datasets: dict[str, dict[str, Any]], date_stamp: str
) -> str:
    """Generate a Markdown report from validated local datasets."""
    market_data = datasets["market"]
    validate_market_data(market_data)
    ai_articles = get_articles(datasets["ai_news"], "AI news")
    web3_articles = get_articles(datasets["web3_news"], "Web3 news")

    btc = market_data["assets"]["BTC"]
    eth = market_data["assets"]["ETH"]
    market_summary = build_market_summary(
        btc["24h_change"], eth["24h_change"]
    )
    ai_lines = format_news_items(ai_articles)
    web3_lines = format_news_items(web3_articles)
    focus_lines = find_focus_areas(ai_articles, web3_articles)

    return "\n".join(
        [
            f"# AI + Web3 每日报告｜{date_stamp}",
            "",
            "## 今日市场摘要",
            "",
            market_summary,
            "",
            "## BTC / ETH 行情变化",
            "",
            "| 资产 | 价格（USD） | 24 小时变化 | 数据时间（UTC） |",
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
            "## AI 热点整理",
            "",
            *ai_lines,
            "",
            "## Web3 热点整理",
            "",
            *web3_lines,
            "",
            "## 潜在关注方向",
            "",
            *focus_lines,
            "",
            "## 风险提示",
            "",
            (
                "本报告由本地规则根据公开新闻标题和市场快照自动整理，"
                "可能存在数据延迟、来源错误或信息遗漏。内容仅供研究参考，"
                "不构成投资建议，不应作为交易依据。"
            ),
            "",
        ]
    )


def save_report(report: str, date_stamp: str) -> Path:
    """Save the report to the ignored processed-data directory."""
    output_path = (
        PROCESSED_DATA_DIRECTORY / f"daily_web3_report_{date_stamp}.md"
    )
    try:
        PROCESSED_DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
    except OSError as exc:
        raise AnalysisError(f"Unable to save report: {exc}") from exc
    return output_path


def main() -> int:
    """Generate today's report from local UTC date-stamped files."""
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        datasets = load_daily_inputs(date_stamp)
        report = generate_report(datasets, date_stamp)
        output_path = save_report(report, date_stamp)
    except AnalysisError as exc:
        print(f"News analysis failed: {exc}", file=sys.stderr)
        return 1

    print(f"Daily Web3 report saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
