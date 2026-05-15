#!/usr/bin/env python3
"""测试 SZ000001 历史全部 1 分钟 K 线拉取速度。"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from time import perf_counter

from shunplus import shun_api

SHANGHAI_TZ = timezone(timedelta(hours=8))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", help="API Token")
    parser.add_argument(
        "--start-date",
        help="起始日期，格式 YYYY-MM-DD；不传时先从 symbols 里查上市日期",
    )
    parser.add_argument("--end-date", help="结束日期，格式 YYYY-MM-DD")
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

    start_date = args.start_date or _listed_at(client, "SZ000001")
    end_date = args.end_date or _today()

    print(f"[{_now()}] 开始拉取 SZ000001 历史 1 分钟 K 线")
    print(f"[{_now()}] 时间范围: {start_date} -> {end_date}")
    print(f"[{_now()}] 正在使用 fetch_all 一次性拉取并合并成 DataFrame")

    started_at = perf_counter()
    df = client.fetch_all(
        "kline",
        format="dataframe",
        period="1m",
        symbol="SZ000001",
        start_time=start_date,
        end_time=end_date,
    )
    elapsed = perf_counter() - started_at

    print(f"[{_now()}] 拉取完成")
    print(f"[{_now()}] 行数: {len(df)}")
    print(f"[{_now()}] 耗时: {_format_seconds(elapsed)}")
    return 0


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


def _listed_at(client, symbol: str) -> str:
    print(f"[{_now()}] 正在查询 symbols，获取 {symbol} 的上市日期")
    df = client.fetch_all("symbols", format="dataframe")
    row = df[df["symbol"] == symbol]
    if row.empty:
        raise ValueError(f"找不到 {symbol}")
    listed_at = str(row.iloc[0]["listed_at"])
    print(f"[{_now()}] 上市日期: {listed_at}")
    return listed_at


def _today() -> str:
    return datetime.now(timezone.utc).astimezone(SHANGHAI_TZ).strftime("%Y-%m-%d")


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
