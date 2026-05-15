#!/usr/bin/env python3
"""测试全量股票今天 1 分钟 K 线拉取速度。"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Tuple

from shunplus import shun_api

SHANGHAI_TZ = timezone(timedelta(hours=8))
DEFAULT_BENCHMARK_TRADE_DATE = "2026-05-08"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="API Token")
    parser.add_argument("--trade-date", help="交易日期，格式 YYYY-MM-DD")
    parser.add_argument("--max-symbols", type=int, help="最多测试多少只股票")
    args = parser.parse_args()

    client = shun_api(token=args.token)
    info = client.entitlements()
    _print_entitlements(info)
    kline_item = _pick_item(info, "/market/kline#1m", "/market/kline")

    print(f"[{_now()}] 套餐信息:")
    print(
        f"[{_now()}] kline 1m "
        f"rpm={kline_item.requests_per_minute if kline_item else '-'} "
        f"concurrency={kline_item.max_concurrency if kline_item else '-'}"
    )

    print(f"[{_now()}] 正在拉取全量股票列表")
    started_at = perf_counter()
    symbols = client.fetch_all("symbols", format="dataframe")
    print(f"[{_now()}] 股票列表拉取完成，共 {len(symbols)} 只")

    if args.max_symbols:
        symbols = symbols.head(args.max_symbols)
        print(f"[{_now()}] 只测试前 {len(symbols)} 只股票")

    trade_date = args.trade_date or DEFAULT_BENCHMARK_TRADE_DATE
    max_workers = max(1, (kline_item.max_concurrency if kline_item else 1))
    print(f"[{_now()}] 使用并发 {max_workers}")
    print(f"[{_now()}] 开始拉取今天的 1 分钟 K 线")

    done = 0
    total = len(symbols)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_fetch_one, client, symbol, trade_date): symbol
            for symbol in symbols["symbol"].dropna().astype(str).tolist()
        }
        for future in as_completed(futures):
            symbol = futures[future]
            done += 1
            try:
                rows, elapsed = future.result()
                print(
                    f"[{_now()}] [{done}/{total}] {symbol} 完成，"
                    f"{rows} 行，耗时 {_format_seconds(elapsed)}"
                )
            except Exception as exc:
                print(f"[{_now()}] [{done}/{total}] {symbol} 失败: {exc}")

    elapsed = perf_counter() - started_at
    print(f"[{_now()}] 全部完成，总耗时 {_format_seconds(elapsed)}")
    return 0


def _fetch_one(client, symbol: str, trade_date: str) -> Tuple[int, float]:
    started_at = perf_counter()
    df = client.fetch_all(
        "kline",
        format="dataframe",
        period="1m",
        symbol=symbol,
        start_time=trade_date,
        end_time=trade_date,
    )
    return len(df), perf_counter() - started_at


def _pick_item(info, product_key: str, endpoint_key: str):
    for item in info.entitlements:
        if item.product_key == product_key:
            return item
    for item in info.entitlements:
        if item.endpoint_key == endpoint_key:
            return item
    return None


def _print_entitlements(info) -> None:
    print(f"[{_now()}] 权益快照 key_id={info.key_id}，共 {len(info.entitlements)} 条")
    for item in sorted(info.entitlements, key=lambda x: (x.endpoint_key, x.product_key)):
        print(
            f"[{_now()}] "
            f"product_key={item.product_key} "
            f"endpoint_key={item.endpoint_key} "
            f"tier={item.tier_code} rank={item.tier_rank} "
            f"rpm={item.requests_per_minute} "
            f"concurrency={item.max_concurrency} "
            f"burst={item.burst_capacity} "
            f"daily={_fmt_optional(item.daily_quota)} "
            f"monthly={_fmt_optional(item.monthly_quota)} "
            f"max_rows={_fmt_optional(item.max_rows_per_request)} "
            f"history_days={_fmt_optional(item.max_history_days)} "
            f"start={item.start_time} "
            f"end={item.end_time}"
        )


def _now() -> str:
    return datetime.now(timezone.utc).astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def _format_seconds(value: float) -> str:
    if value < 1:
        return f"{value * 1000:.0f}ms"
    return f"{value:.2f}s"


def _fmt_optional(value: object) -> str:
    return "-" if value is None else str(value)


if __name__ == "__main__":
    raise SystemExit(main())
