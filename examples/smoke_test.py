"""真实 API 冒烟测试脚本。"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict

from shunplus import Client, ShunplusError, TableResult


def main() -> int:
    parser = argparse.ArgumentParser(description="验证 Shunplus SDK 是否能正常请求 API")
    parser.add_argument("--api", default="symbols", help="SDK 接口名，默认 symbols")
    parser.add_argument("--params", default='{"limit":1}', help="JSON 格式查询参数")
    parser.add_argument("--token", default=None, help="API Token，默认读取 SHUNPLUS_API_TOKEN")
    args = parser.parse_args()

    token = args.token or os.getenv("SHUNPLUS_API_TOKEN")
    params = _load_params(args.params)
    client = Client(token=token)

    try:
        result = client.query(args.api, **params)
    except ShunplusError as exc:
        print(f"请求失败：{exc}")
        return 1

    _print_result(result)
    return 0


def _load_params(value: str) -> Dict[str, Any]:
    try:
        params = json.loads(value)
    except json.JSONDecodeError as exc:
        msg = f"--params 不是合法 JSON：{exc}"
        raise SystemExit(msg) from exc
    if not isinstance(params, dict):
        raise SystemExit("--params 必须是 JSON object")
    return params


def _print_result(result: TableResult) -> None:
    print("请求成功")
    print(f"字段：{', '.join(result.fields)}")
    print(f"行数：{len(result.data)}")
    if result.data:
        print("第一行：")
        print(json.dumps(result.to_dicts()[0], ensure_ascii=False, indent=2))
    print(f"下一页游标：{result.next_cursor}")
    print(f"下一页去重游标：{result.next_cursor_id}")


if __name__ == "__main__":
    raise SystemExit(main())
