"""Shunplus 数据 API 客户端。"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from bisect import bisect_right
from contextlib import suppress
from datetime import date, datetime, timedelta, timezone
from datetime import time as datetime_time
from email.utils import parsedate_to_datetime
from threading import Lock
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Set, Tuple, Type, Union

import httpx

from ._generated import ENDPOINT_ALIASES, ENDPOINTS, GeneratedDataMethods
from ._types import DateLike, ResultFormat
from .entitlements import (
    EndpointLimitConfig,
    EntitlementsResult,
    ProductLimiter,
    build_limit_configs,
    build_product_limit_configs,
    build_product_limiters,
)
from .exceptions import (
    ApiError,
    AuthenticationError,
    ConcurrencyRateLimitError,
    DailyRateLimitError,
    MinuteRateLimitError,
    MonthlyRateLimitError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from .models import TableResult, _parse_fields

DEFAULT_BASE_URL = "https://api.shunplus.com"
TOKEN_ENV_NAMES = ("SHUNPLUS_API_TOKEN", "SHUNPLUS_TOKEN")
TOKEN_CONFIG_FILE_ENV_NAME = "SHUNPLUS_CONFIG_FILE"
_GLOBAL_TOKEN: Optional[str] = None
_A_SHARE_PREFIX_SYMBOL_RE = re.compile(r"^(SZ|SH|BJ)(\d{6})$")
_A_SHARE_SUFFIX_SYMBOL_RE = re.compile(r"^(\d{6})\.(SZ|SH|BJ)$")
_HK_PREFIX_SYMBOL_RE = re.compile(r"^HK(\d{5})$")
_HK_SUFFIX_SYMBOL_RE = re.compile(r"^(\d{5})\.HK$")
_DATE_COMPACT_RE = re.compile(r"^\d{8}$")
_DATETIME_COMPACT_RE = re.compile(r"^(\d{8})(?:[ T]?)(\d{6})$")
_DATETIME_PARAM_NAMES = {"start_time", "end_time"}
_TIMEZONE_DATETIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$"
)
_SHANGHAI_TZ = timezone(timedelta(hours=8))
_KLINE_PERIOD_PRODUCT_SUFFIX: Dict[str, str] = {
    "1m": "1m",
    "5m": "advanced",
    "15m": "advanced",
    "30m": "mid",
    "60m": "mid",
    "120m": "mid",
    "day": "long",
    "month": "long",
    "year": "long",
}
_SPLIT_PRODUCT_ENDPOINTS = {
    "/news/stock": {"xueqiu": "xueqiu", "futu": "futu"},
    "/social/posts": {"xueqiu": "xueqiu", "eastmoney": "eastmoney"},
    "/social/comments": {"xueqiu": "xueqiu", "eastmoney": "eastmoney"},
}
_UNSPLIT_PRODUCT_ENDPOINTS = {
    "/symbols",
    "/market/factors",
    "/news/futu_flashes",
    "/news/futu_headlines",
    "/announcements",
}
_DEFAULT_TABLE_LIMIT = 200
_PROGRESS_BAR_WIDTH = 24
_PRICE_FIELD_NAMES = ("open", "high", "low", "close")
_DEFAULT_DAILY_ENRICH_FIELDS = ("adj_factor", "pre_close", "change", "pct_chg")
_DAILY_ENRICH_FIELD_ALIASES = {"factor": "adj_factor"}
_KLINE_PERIOD_DAYS_PER_ROW: Dict[str, float] = {
    "1m": 1 / 240,
    "5m": 5 / 240,
    "15m": 15 / 240,
    "30m": 30 / 240,
    "60m": 60 / 240,
    "120m": 120 / 240,
    "day": 1.8,
    "month": 32,
    "year": 370,
}

PageCallback = Callable[[int, TableResult], None]


def set_token(token: str, *, persist: bool = True) -> str:
    """设置默认 Token，并默认持久化到本地配置文件。"""

    global _GLOBAL_TOKEN
    normalized = token.strip()
    if not normalized:
        raise ValueError("token 不能为空")
    _GLOBAL_TOKEN = normalized
    if persist:
        _save_local_token(normalized)
    return token_config_path()


def get_token() -> Optional[str]:
    """返回当前默认 Token，优先读取进程内设置，其次读取本地配置和环境变量。"""

    return _GLOBAL_TOKEN or _token_from_local_config() or _token_from_env()


def clear_token(*, persist: bool = True) -> str:
    """清除当前默认 Token，并可选删除本地配置文件中的持久化 Token。"""

    global _GLOBAL_TOKEN
    _GLOBAL_TOKEN = None
    if persist:
        _clear_local_token()
    return token_config_path()


def token_config_path() -> str:
    """返回本地 Token 配置文件路径。"""

    override = os.getenv(TOKEN_CONFIG_FILE_ENV_NAME)
    if override:
        return os.path.abspath(os.path.expanduser(override))

    config_home = os.getenv("XDG_CONFIG_HOME")
    if not config_home and os.name == "nt":
        config_home = os.getenv("APPDATA")
    if not config_home:
        config_home = os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(config_home, "shunplus", "config.json")


def shun_api(
    token: Optional[str] = None,
    *,
    timeout: float = 30.0,
    default_format: ResultFormat = "dataframe",
    auto_configure_limits: bool = True,
    max_retries: int = 1,
    retry_backoff: float = 1.0,
) -> Client:
    """创建 Shunplus 数据 API 客户端。

    默认返回 DataFrame，便于 `api = shun_api(token); api.daily(...)` 的使用体验。
    如需结构化响应，可传入 `default_format="table"` 或直接使用 `Client`。
    """

    return Client(
        token=token,
        timeout=timeout,
        default_format=default_format,
        auto_configure_limits=auto_configure_limits,
        max_retries=max_retries,
        retry_backoff=retry_backoff,
    )


class Client(GeneratedDataMethods):
    """Shunplus 数据 API 客户端。"""

    def __init__(
        self,
        token: Optional[str] = None,
        *,
        timeout: float = 30.0,
        default_format: ResultFormat = "table",
        auto_configure_limits: bool = True,
        max_retries: int = 1,
        retry_backoff: float = 1.0,
    ) -> None:
        self.token = token or get_token()
        self.base_url = DEFAULT_BASE_URL
        self.timeout = timeout
        self.default_format = default_format
        self.auto_configure_limits = auto_configure_limits
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self._entitlements: Optional[EntitlementsResult] = None
        self._limit_configs: Dict[str, EndpointLimitConfig] = {}
        self._product_limit_configs: Dict[str, EndpointLimitConfig] = {}
        self._product_limiters: Dict[str, ProductLimiter] = {}
        self._limits_configured = False
        self._limits_lock = Lock()
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
        )

    @property
    def df(self) -> DataFrameClient:
        """DataFrame 输出快捷入口。"""

        return DataFrameClient(self)

    def daily(
        self,
        *,
        ts_code: str,
        trade_date: Optional[DateLike] = None,
        start_date: Optional[DateLike] = None,
        end_date: Optional[DateLike] = None,
        limit: Optional[int] = None,
        cursor: Optional[int] = None,
        cursor_id: Optional[str] = None,
        fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        format: Optional[ResultFormat] = None,
    ) -> Any:
        """查询日 K 数据，兼容 `ts_code` 与日期区间参数写法。"""

        start_time, end_time = _resolve_date_range(
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )
        return self.kline(
            period="day",
            symbol=ts_code,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            cursor=cursor,
            cursor_id=cursor_id,
            fields=fields,
            format=format,
        )

    def stk_mins(
        self,
        *,
        ts_code: str,
        freq: str = "1min",
        start_date: Optional[DateLike] = None,
        end_date: Optional[DateLike] = None,
        limit: Optional[int] = None,
        cursor: Optional[int] = None,
        cursor_id: Optional[str] = None,
        fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        format: Optional[ResultFormat] = None,
    ) -> Any:
        """查询分钟 K 线数据，兼容 `ts_code`、`freq` 与日期区间参数写法。"""

        period = _normalize_minute_freq(freq)
        start_time, end_time = _resolve_date_range(
            trade_date=None,
            start_date=start_date,
            end_date=end_date,
        )
        return self.kline(
            period=period,
            symbol=ts_code,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            cursor=cursor,
            cursor_id=cursor_id,
            fields=fields,
            format=format,
        )

    def kline_adjusted(
        self,
        *,
        period: str,
        symbol: str,
        start_time: Optional[DateLike] = None,
        end_time: Optional[DateLike] = None,
        limit: Optional[int] = None,
        cursor: Optional[int] = None,
        cursor_id: Optional[str] = None,
        adj: str = "qfq",
        include_factor: bool = False,
        fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        format: Optional[ResultFormat] = None,
    ) -> Any:
        """查询自动复权后的 K 线数据。"""

        normalized_adj = _normalize_adjustment(adj)
        normalized_fields = _normalize_helper_fields(fields)
        include_factor = include_factor or "adj_factor" in normalized_fields
        base = self.kline(
            period=period,
            symbol=symbol,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            cursor=cursor,
            cursor_id=cursor_id,
            format="table",
        )
        assert isinstance(base, TableResult)
        factor_map = self._fetch_factor_map_for_kline_rows(symbol=symbol, rows=base.to_dicts())
        adjusted = self._build_adjusted_kline_result(
            base,
            factor_map=factor_map,
            adj=normalized_adj,
            include_factor=include_factor,
        )
        if fields:
            adjusted = adjusted.select(normalized_fields)
        return self._format_result(adjusted, format)

    def daily_with_factors(
        self,
        *,
        ts_code: str,
        trade_date: Optional[DateLike] = None,
        start_date: Optional[DateLike] = None,
        end_date: Optional[DateLike] = None,
        limit: Optional[int] = None,
        cursor: Optional[int] = None,
        cursor_id: Optional[str] = None,
        factors: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        format: Optional[ResultFormat] = None,
    ) -> Any:
        """查询日线并自动补充常用因子与衍生字段。"""

        requested_fields = _parse_fields(fields)
        selected_factors = _normalize_daily_factor_fields(
            factors,
            requested_fields=requested_fields,
        )
        base = self.daily(
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            cursor=cursor,
            cursor_id=cursor_id,
            format="table",
        )
        assert isinstance(base, TableResult)
        factor_map = self._fetch_factor_map_for_kline_rows(symbol=ts_code, rows=base.to_dicts())
        enriched = self._build_daily_with_factors_result(
            base,
            factor_map=factor_map,
            selected_factors=selected_factors,
        )
        if fields:
            enriched = enriched.select(_normalize_helper_fields(fields))
        return self._format_result(enriched, format)

    def close(self) -> None:
        """关闭底层 HTTP 连接池。"""

        self._client.close()

    def set_token(self, token: str, *, persist: bool = True) -> str:
        """更新当前客户端使用的 Token，并可选持久化到本地配置。"""

        path = set_token(token, persist=persist)
        self.token = token.strip()
        return path

    def reload_token(self) -> Optional[str]:
        """从默认来源重新加载 Token 到当前客户端。"""

        self.token = get_token()
        return self.token

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def query(
        self,
        api_name: str,
        fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        *,
        format: Optional[ResultFormat] = None,
        **params: Any,
    ) -> Any:
        """按 SDK 方法名或 OpenAPI `operationId` 查询数据。"""

        endpoint = _resolve_endpoint(api_name)
        result = self._request_table(endpoint, params)
        if fields:
            result = result.select(fields)
        return self._format_result(result, format)

    def request_json(self, api_name: str, **params: Any) -> Any:
        """请求非表格型 SDK 接口并返回结构化结果。"""

        endpoint = _resolve_endpoint(api_name)
        payload = self._request_json_endpoint(endpoint, params, use_limit=False)
        if endpoint["name"] == "entitlements":
            result = EntitlementsResult.from_dict(payload)
            self._set_entitlements(result)
            return result
        return payload

    def iter_pages(
        self,
        api_name: str,
        fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        *,
        show_progress: Optional[bool] = None,
        on_page: Optional[PageCallback] = None,
        **params: Any,
    ) -> Iterator[TableResult]:
        """自动沿 `next_cursor` 和 `next_cursor_id` 逐页迭代表格结果。"""

        endpoint = _resolve_endpoint(api_name)
        next_params = dict(params)
        progress = _ConsoleProgress(api_name, enabled=show_progress)
        page_no = 0
        row_count = 0
        completed = False
        try:
            while True:
                result = self._request_table(endpoint, next_params)
                if fields:
                    result = result.select(fields)
                page_no += 1
                row_count += len(result.data)
                progress.update_total_rows(_extract_total_rows(result.query_meta))
                progress.update(page_no=page_no, row_count=row_count)
                if on_page is not None:
                    on_page(page_no, result)
                yield result
                if not result.has_more:
                    completed = True
                    break
                next_params["cursor"] = result.next_cursor
                next_params["cursor_id"] = result.next_cursor_id
        finally:
            progress.finish(page_no=page_no, row_count=row_count, completed=completed)

    def fetch_all(
        self,
        api_name: str,
        fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None,
        *,
        format: Optional[ResultFormat] = None,
        show_progress: Optional[bool] = None,
        on_page: Optional[PageCallback] = None,
        **params: Any,
    ) -> Any:
        """拉取所有分页并合并为一个结果。"""

        merged_fields: List[str] = []
        merged_rows: List[List[Any]] = []
        code = 0
        msg = "success"
        query_meta: Optional[Dict[str, Any]] = None
        raw: Dict[str, Any] = {}
        has_page = False
        for page in self.iter_pages(
            api_name,
            fields=fields,
            show_progress=show_progress,
            on_page=on_page,
            **params,
        ):
            if not has_page:
                merged_fields = list(page.fields)
                code = page.code
                msg = page.msg
                query_meta = page.query_meta
                raw = page.raw
                has_page = True
            merged_rows.extend(page.data)
        if not has_page:
            return self._format_result(TableResult(fields=[], data=[]), format)
        merged = TableResult(
            fields=merged_fields,
            data=merged_rows,
            code=code,
            msg=msg,
            query_meta=query_meta,
            raw=raw,
        )
        return self._format_result(merged, format)

    def _request_table(self, endpoint: Dict[str, Any], params: Mapping[str, Any]) -> TableResult:
        if not self.token:
            msg = (
                "缺少 API Token，请传入 token、调用 set_token()，"
                "或设置 SHUNPLUS_API_TOKEN 环境变量"
            )
            raise AuthenticationError(msg, status_code=401)

        endpoint_path = _endpoint_key_from_path(endpoint["path"])
        product_key = _product_key_for_request(endpoint_path, params)
        request_params = self._prepare_limited_params(endpoint_path, product_key, params)
        limiter = self._limiter_for(product_key)
        with limiter.wait_for_slot() if limiter is not None else _NullContext():
            response = self._send_request(
                endpoint["http_method"],
                endpoint["path"],
                params=_clean_params(request_params),
            )
        payload = _decode_response(response)
        _raise_for_http_error(response.status_code, payload, response.text, response.headers)
        _raise_for_business_error(payload, response.status_code)
        return TableResult(
            fields=list(payload.get("fields") or []),
            data=list(payload.get("data") or []),
            code=int(payload.get("code", 0)),
            msg=str(payload.get("msg", "success")),
            next_cursor=payload.get("next_cursor"),
            next_cursor_id=payload.get("next_cursor_id"),
            query_meta=payload.get("query_meta"),
            raw=payload,
        )

    def _request_json_endpoint(
        self,
        endpoint: Dict[str, Any],
        params: Mapping[str, Any],
        *,
        use_limit: bool,
    ) -> Dict[str, Any]:
        if not self.token:
            msg = (
                "缺少 API Token，请传入 token、调用 set_token()，"
                "或设置 SHUNPLUS_API_TOKEN 环境变量"
            )
            raise AuthenticationError(msg, status_code=401)

        endpoint_path = _endpoint_key_from_path(endpoint["path"])
        product_key = _product_key_for_request(endpoint_path, params)
        request_params = self._prepare_limited_params(
            endpoint_path,
            product_key,
            params,
        ) if use_limit else params
        limiter = self._limiter_for(product_key) if use_limit else None
        with limiter.wait_for_slot() if limiter is not None else _NullContext():
            response = self._send_request(
                endpoint["http_method"],
                endpoint["path"],
                params=_clean_params(request_params),
            )
        payload = _decode_response(response)
        _raise_for_http_error(response.status_code, payload, response.text, response.headers)
        _raise_for_business_error(payload, response.status_code)
        return payload

    def _fetch_factor_map_for_kline_rows(
        self,
        *,
        symbol: str,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, float]:
        trade_dates = _unique_trade_dates_from_kline_rows(rows)
        if not trade_dates:
            return {}

        factor_map: Dict[str, float] = {}
        for page in self.iter_pages("factors", symbol=symbol):
            assert isinstance(page, TableResult)
            for item in page.iter_dicts():
                trade_date = _normalize_trade_date_key(item.get("trade_date"))
                factor_value = _coerce_float(item.get("factor"))
                if trade_date is None or factor_value is None:
                    continue
                if trade_date in trade_dates and trade_date not in factor_map:
                    factor_map[trade_date] = factor_value
            if len(factor_map) >= len(trade_dates):
                break
        return factor_map

    def _build_adjusted_kline_result(
        self,
        base: TableResult,
        *,
        factor_map: Mapping[str, float],
        adj: str,
        include_factor: bool,
    ) -> TableResult:
        rows = base.to_dicts()
        if not rows:
            fields = list(base.fields)
            if include_factor and "adj_factor" not in fields:
                fields.append("adj_factor")
            return TableResult(
                fields=fields,
                data=[],
                code=base.code,
                msg=base.msg,
                next_cursor=base.next_cursor,
                next_cursor_id=base.next_cursor_id,
                query_meta=base.query_meta,
                raw=base.raw,
            )

        indexed_rows = _index_rows_with_factors(rows, factor_map)
        reference_factor = _reference_factor_for_adjustment(indexed_rows, adj)
        output_rows: List[Dict[str, Any]] = []
        for item in indexed_rows:
            row = dict(item["row"])
            factor_value = item["adj_factor"]
            if factor_value is not None:
                _apply_adjustment_to_row(
                    row,
                    factor_value=factor_value,
                    adj=adj,
                    reference=reference_factor,
                )
            if include_factor:
                row["adj_factor"] = factor_value
            output_rows.append(row)

        fields = list(base.fields)
        if include_factor and "adj_factor" not in fields:
            fields.append("adj_factor")
        return _table_result_from_dict_rows(
            fields=fields,
            rows=output_rows,
            base=base,
        )

    def _build_daily_with_factors_result(
        self,
        base: TableResult,
        *,
        factor_map: Mapping[str, float],
        selected_factors: List[str],
    ) -> TableResult:
        rows = base.to_dicts()
        if not rows:
            extra_fields = [field for field in selected_factors if field not in base.fields]
            return TableResult(
                fields=list(base.fields) + extra_fields,
                data=[],
                code=base.code,
                msg=base.msg,
                next_cursor=base.next_cursor,
                next_cursor_id=base.next_cursor_id,
                query_meta=base.query_meta,
                raw=base.raw,
            )

        indexed_rows = _index_rows_with_factors(rows, factor_map)
        chronological_rows = [
            item
            for item in sorted(
                indexed_rows,
                key=lambda item: (
                    item.get("trade_date") is None,
                    item.get("trade_date"),
                    item["index"],
                ),
            )
            if item.get("trade_date") is not None
        ]
        derived_by_index: Dict[int, Dict[str, Any]] = {}
        previous_close: Optional[float] = None
        for item in chronological_rows:
            row = dict(item["row"])
            factor_value = item["adj_factor"]
            close_value = _coerce_float(row.get("close"))
            percent_value = _coerce_float(row.get("percent"))

            if "adj_factor" in selected_factors:
                row["adj_factor"] = factor_value
            if "pre_close" in selected_factors:
                row["pre_close"] = previous_close
            if "change" in selected_factors:
                row["change"] = (
                    _round_metric(close_value - previous_close)
                    if close_value is not None and previous_close is not None
                    else None
                )
            if "pct_chg" in selected_factors:
                if percent_value is not None:
                    row["pct_chg"] = percent_value
                elif close_value is not None and previous_close not in (None, 0):
                    row["pct_chg"] = _round_metric(
                        (close_value - previous_close) / previous_close * 100.0
                    )
                else:
                    row["pct_chg"] = None
            derived_by_index[item["index"]] = row
            previous_close = close_value

        output_rows: List[Dict[str, Any]] = []
        for item in indexed_rows:
            if item["index"] in derived_by_index:
                output_rows.append(derived_by_index[item["index"]])
                continue
            row = dict(item["row"])
            if "adj_factor" in selected_factors:
                row["adj_factor"] = item["adj_factor"]
            if "pre_close" in selected_factors:
                row["pre_close"] = None
            if "change" in selected_factors:
                row["change"] = None
            if "pct_chg" in selected_factors:
                row["pct_chg"] = _coerce_float(row.get("percent"))
            output_rows.append(row)

        fields = list(base.fields)
        for field in selected_factors:
            if field not in fields:
                fields.append(field)
        return _table_result_from_dict_rows(fields=fields, rows=output_rows, base=base)

    def _prepare_limited_params(
        self,
        endpoint_path: str,
        product_key: Optional[str],
        params: Mapping[str, Any],
    ) -> Dict[str, Any]:
        self._ensure_limits_configured()
        request_params = dict(params)
        config = self._limit_config_for(endpoint_path, product_key)
        self._apply_limit_policy(request_params, config)
        if endpoint_path == "/market/kline":
            self._prepare_kline_time_range(request_params, config)
        return request_params

    def _limit_config_for(
        self,
        endpoint_path: str,
        product_key: Optional[str],
    ) -> Optional[EndpointLimitConfig]:
        if product_key is None:
            return None
        config = self._product_limit_configs.get(product_key)
        if config is not None:
            return config
        if endpoint_path in _UNSPLIT_PRODUCT_ENDPOINTS and product_key == endpoint_path:
            return self._limit_configs.get(endpoint_path)
        return None

    def _apply_limit_policy(
        self,
        params: Dict[str, Any],
        config: Optional[EndpointLimitConfig],
    ) -> None:
        limit = params.get("limit")
        max_rows = config.max_rows_per_request if config is not None else None
        if limit is None:
            if max_rows is not None:
                params["limit"] = max_rows
            return
        try:
            parsed_limit = int(limit)
        except (TypeError, ValueError) as exc:
            msg = "limit 必须是正整数"
            raise ValidationError(msg, status_code=422) from exc
        if parsed_limit <= 0:
            msg = "limit 必须是正整数"
            raise ValidationError(msg, status_code=422)
        if max_rows is not None and parsed_limit > max_rows:
            msg = f"当前商品单次最多只能拉取 {max_rows} 条记录。"
            raise ValidationError(msg, status_code=400)
        params["limit"] = parsed_limit

    def _prepare_kline_time_range(
        self,
        params: Dict[str, Any],
        config: Optional[EndpointLimitConfig],
    ) -> None:
        has_start = params.get("start_time") is not None
        has_end = params.get("end_time") is not None
        if has_start and has_end:
            return

        period = str(params.get("period") or "")
        limit = _positive_int_or_default(params.get("limit"), default=_DEFAULT_TABLE_LIMIT)

        days = _default_kline_days(period, limit)
        if config is not None and config.max_history_days is not None:
            days = min(days, config.max_history_days)

        window = timedelta(days=days)
        if has_start:
            start_time = _coerce_beijing_datetime("start_time", params["start_time"])
            end_time = start_time + window
        elif has_end:
            end_time = _coerce_beijing_datetime("end_time", params["end_time"])
            start_time = end_time - window
        else:
            end_time = _now_shanghai()
            start_time = end_time - window

        params["start_time"] = start_time.isoformat()
        params["end_time"] = end_time.isoformat()

    def _limiter_for(self, product_key: Optional[str]) -> Optional[ProductLimiter]:
        if product_key is None:
            return None
        return self._product_limiters.get(product_key)

    def _ensure_limits_configured(self) -> None:
        if not self.auto_configure_limits or self._limits_configured:
            return
        with self._limits_lock:
            if self._limits_configured:
                return
            endpoint = ENDPOINTS.get("entitlements")
            if endpoint is None:
                self._limits_configured = True
                return
            try:
                payload = self._request_json_endpoint(endpoint, {}, use_limit=False)
            except (ApiError, httpx.HTTPError):
                self._limits_configured = True
                return
            self._set_entitlements(EntitlementsResult.from_dict(payload))
            self._limits_configured = True

    def _set_entitlements(self, result: EntitlementsResult) -> None:
        self._entitlements = result
        self._limit_configs = build_limit_configs(result.entitlements)
        self._product_limit_configs = build_product_limit_configs(result.entitlements)
        next_limiters = build_product_limiters(result.entitlements)
        for product_key, limiter in next_limiters.items():
            existing = self._product_limiters.get(product_key)
            if existing is not None:
                existing.update(limiter.entitlement)
                next_limiters[product_key] = existing
        self._product_limiters = next_limiters
        self._limits_configured = True

    def _send_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any],
    ) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(
                    method,
                    path,
                    params=params,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt >= self.max_retries:
                    raise
                self._sleep_before_retry(attempt, retry_after=None)
                continue

            if (
                not _is_retryable_status(response.status_code)
                or response.status_code == 429
                or attempt >= self.max_retries
            ):
                return response

            self._sleep_before_retry(
                attempt,
                retry_after=_parse_retry_after(response.headers.get("retry-after")),
            )
        msg = "请求重试流程异常结束"
        raise RuntimeError(msg)

    def _sleep_before_retry(self, attempt: int, *, retry_after: Optional[float]) -> None:
        delay = retry_after if retry_after is not None else self.retry_backoff * (2**attempt)
        if delay > 0:
            time.sleep(delay)

    def _format_result(self, result: TableResult, format: Optional[ResultFormat]) -> Any:
        output_format = format or self.default_format
        if output_format == "table":
            return result
        if output_format == "dict":
            return result.to_dicts()
        if output_format == "dataframe":
            return result.to_dataframe()
        if output_format == "raw":
            return result.raw
        msg = f"不支持的输出格式：{output_format}"
        raise ValueError(msg)


class DataFrameClient:
    """将任意 SDK 方法转换为 DataFrame 输出的轻量代理。"""

    def __init__(self, client: Client) -> None:
        self._client = client

    def __getattr__(self, name: str) -> Any:
        def call(**params: Any) -> Any:
            endpoint_name = ENDPOINT_ALIASES.get(name, name)
            endpoint = ENDPOINTS.get(endpoint_name)
            method = getattr(self._client, name, None)
            if endpoint is not None and endpoint.get("response_kind") != "table":
                if callable(method):
                    return method(**params)
                return self._client.request_json(name, **params)
            if callable(method):
                return method(format="dataframe", **params)
            return self._client.query(name, format="dataframe", **params)

        return call


Shunplus = Client


class _NullContext:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *exc_info: object) -> None:
        return None


class _ConsoleProgress:
    _UNKNOWN_BAR_MARKER = ">"

    def __init__(self, label: str, *, enabled: Optional[bool]) -> None:
        stream = getattr(sys, "stderr", None)
        if enabled is None:
            enabled = bool(stream is not None and hasattr(stream, "isatty") and stream.isatty())
        self._enabled = bool(enabled and stream is not None)
        self._stream = stream
        self._label = label
        self._total_rows: Optional[int] = None
        self._started = False

    def update_total_rows(self, total_rows: Optional[int]) -> None:
        if total_rows is None or total_rows < 0:
            return
        self._total_rows = total_rows

    def update(self, *, page_no: int, row_count: int) -> None:
        if not self._enabled or self._stream is None:
            return
        self._started = True
        self._stream.write(self._render(page_no=page_no, row_count=row_count, completed=False))
        self._stream.flush()

    def finish(self, *, page_no: int, row_count: int, completed: bool) -> None:
        if not self._enabled or self._stream is None or not self._started:
            return
        self._stream.write(self._render(page_no=page_no, row_count=row_count, completed=completed))
        self._stream.write("\n")
        self._stream.flush()

    def _render(self, *, page_no: int, row_count: int, completed: bool) -> str:
        bar = self._build_bar(page_no=page_no, row_count=row_count, completed=completed)
        details = self._build_details(page_no=page_no, row_count=row_count, completed=completed)
        return f"\r{self._label} {bar} {details}"

    def _build_bar(self, *, page_no: int, row_count: int, completed: bool) -> str:
        if completed:
            return f"[{'#' * _PROGRESS_BAR_WIDTH}]"
        if self._total_rows is not None and self._total_rows > 0:
            ratio = min(1.0, float(row_count) / float(self._total_rows))
            filled = int(_PROGRESS_BAR_WIDTH * ratio)
            return f"[{'#' * filled}{'-' * (_PROGRESS_BAR_WIDTH - filled)}]"
        position = max(0, (page_no - 1) % _PROGRESS_BAR_WIDTH)
        bar = ["-"] * _PROGRESS_BAR_WIDTH
        bar[position] = self._UNKNOWN_BAR_MARKER
        return f"[{''.join(bar)}]"

    def _build_details(self, *, page_no: int, row_count: int, completed: bool) -> str:
        if self._total_rows is not None and self._total_rows > 0:
            row_text = f"{row_count}/{self._total_rows} rows"
        else:
            row_text = f"{row_count} rows"
        page_text = "page" if page_no == 1 else "pages"
        status = "done" if completed else "loading"
        return f"{row_text}, {page_no} {page_text}, {status}"


def _resolve_endpoint(api_name: str) -> Dict[str, Any]:
    name = ENDPOINT_ALIASES.get(api_name, api_name)
    try:
        endpoint = ENDPOINTS[name]
        return {"name": name, **endpoint}
    except KeyError as exc:
        supported = ", ".join(sorted(ENDPOINTS))
        msg = f"未知接口：{api_name}。可用接口：{supported}"
        raise ValueError(msg) from exc


def _token_from_env() -> Optional[str]:
    for name in TOKEN_ENV_NAMES:
        value = os.getenv(name)
        if value:
            return value
    return None


def _token_from_local_config() -> Optional[str]:
    payload = _load_local_config()
    token = payload.get("token")
    if isinstance(token, str):
        normalized = token.strip()
        if normalized:
            return normalized
    return None


def _save_local_token(token: str) -> None:
    payload = _load_local_config()
    payload["token"] = token
    payload["updated_at"] = datetime.now(timezone.utc).isoformat()
    payload.setdefault("version", 1)
    _write_local_config(payload)


def _clear_local_token() -> None:
    path = token_config_path()
    payload = _load_local_config()
    payload.pop("token", None)
    payload.pop("updated_at", None)
    if payload:
        _write_local_config(payload)
        return
    with suppress(FileNotFoundError):
        os.remove(path)


def _load_local_config() -> Dict[str, Any]:
    path = token_config_path()
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_local_config(payload: Mapping[str, Any]) -> None:
    path = token_config_path()
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=directory or None,
        prefix=".shunplus-config-",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp_path, path)
        with suppress(PermissionError, OSError):
            os.chmod(path, 0o600)
    except Exception:
        with suppress(OSError):
            os.remove(tmp_path)
        raise


def _clean_params(params: Mapping[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if key == "symbol":
            value = _normalize_symbol(value)
        if key in _DATETIME_PARAM_NAMES:
            clean[key] = _normalize_datetime_param(key, value)
        elif isinstance(value, (datetime, date)):
            clean[key] = value.isoformat()
        elif isinstance(value, bool):
            clean[key] = str(value).lower()
        else:
            clean[key] = value
    return clean


def _extract_total_rows(query_meta: Optional[Mapping[str, Any]]) -> Optional[int]:
    if not isinstance(query_meta, Mapping):
        return None
    for key in ("total", "total_rows", "total_count", "count"):
        value = query_meta.get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed >= 0:
            return parsed
    pagination = query_meta.get("pagination")
    if isinstance(pagination, Mapping):
        return _extract_total_rows(pagination)
    return None


def _normalize_adjustment(adj: str) -> str:
    normalized = str(adj).strip().lower()
    if normalized not in {"qfq", "hfq"}:
        raise ValidationError("adj 仅支持 qfq 或 hfq", status_code=422)
    return normalized


def _normalize_daily_factor_fields(
    factors: Optional[Union[str, List[str], Tuple[str, ...]]],
    *,
    requested_fields: Optional[List[str]] = None,
) -> List[str]:
    parsed = _parse_fields(factors)
    normalized: List[str] = []
    seen: set[str] = set()
    for name in list(parsed) + list(requested_fields or []):
        canonical = _DAILY_ENRICH_FIELD_ALIASES.get(name, name)
        if canonical in _DEFAULT_DAILY_ENRICH_FIELDS and canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    if normalized:
        return normalized
    return list(_DEFAULT_DAILY_ENRICH_FIELDS)


def _normalize_helper_fields(
    fields: Optional[Union[str, List[str], Tuple[str, ...]]],
) -> List[str]:
    normalized: List[str] = []
    for name in _parse_fields(fields):
        normalized.append(_DAILY_ENRICH_FIELD_ALIASES.get(name, name))
    return normalized


def _table_result_from_dict_rows(
    *,
    fields: List[str],
    rows: List[Dict[str, Any]],
    base: TableResult,
) -> TableResult:
    data = [[row.get(field) for field in fields] for row in rows]
    return TableResult(
        fields=fields,
        data=data,
        code=base.code,
        msg=base.msg,
        next_cursor=base.next_cursor,
        next_cursor_id=base.next_cursor_id,
        query_meta=base.query_meta,
        raw=base.raw,
    )


def _unique_trade_dates_from_kline_rows(rows: List[Dict[str, Any]]) -> set[str]:
    result: Set[str] = set()
    for row in rows:
        trade_date = _trade_date_from_kline_row(row)
        if trade_date is not None:
            result.add(trade_date)
    return result


def _trade_date_from_kline_row(row: Mapping[str, Any]) -> Optional[str]:
    if "trade_date" in row:
        return _normalize_trade_date_key(row.get("trade_date"))
    value = row.get("ts")
    if value is None:
        return None
    return _normalize_trade_date_key(value)


def _normalize_trade_date_key(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    if len(text) >= 8 and text[:8].isdigit():
        compact = text[:8]
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:8]}"
    return None


def _coerce_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_metric(value: float) -> float:
    return round(value, 4)


def _index_rows_with_factors(
    rows: List[Dict[str, Any]],
    factor_map: Mapping[str, float],
) -> List[Dict[str, Any]]:
    indexed_rows: List[Dict[str, Any]] = []
    sorted_factor_dates = sorted(factor_map)
    sorted_factor_values = [factor_map[key] for key in sorted_factor_dates]
    for index, row in enumerate(rows):
        trade_date = _trade_date_from_kline_row(row)
        factor_value = _lookup_factor_for_trade_date(
            trade_date,
            sorted_factor_dates=sorted_factor_dates,
            sorted_factor_values=sorted_factor_values,
        )
        indexed_rows.append(
            {
                "index": index,
                "trade_date": trade_date,
                "adj_factor": factor_value,
                "row": row,
            }
        )
    return indexed_rows


def _lookup_factor_for_trade_date(
    trade_date: Optional[str],
    *,
    sorted_factor_dates: List[str],
    sorted_factor_values: List[float],
) -> Optional[float]:
    if trade_date is None or not sorted_factor_dates:
        return None
    position = bisect_right(sorted_factor_dates, trade_date) - 1
    if position < 0:
        return None
    return sorted_factor_values[position]


def _reference_factor_for_adjustment(rows: List[Dict[str, Any]], adj: str) -> Optional[float]:
    dated_values = [
        (item.get("trade_date"), item["adj_factor"])
        for item in rows
        if item.get("trade_date") is not None and item.get("adj_factor") is not None
    ]
    if not dated_values:
        return None
    if adj == "hfq":
        return None
    return sorted(dated_values, key=lambda item: item[0])[-1][1]


def _apply_adjustment_to_row(
    row: Dict[str, Any],
    *,
    factor_value: float,
    adj: str,
    reference: Optional[float],
) -> None:
    for field in _PRICE_FIELD_NAMES:
        price = _coerce_float(row.get(field))
        if price is None:
            continue
        adjusted_price = price * factor_value
        if adj == "qfq":
            if reference in (None, 0):
                continue
            adjusted_price = adjusted_price / reference
        row[field] = _round_metric(adjusted_price)


def _resolve_date_range(
    *,
    trade_date: Optional[DateLike],
    start_date: Optional[DateLike],
    end_date: Optional[DateLike],
) -> Tuple[Optional[str], Optional[str]]:
    if trade_date is not None and (start_date is not None or end_date is not None):
        msg = "trade_date 不能和 start_date/end_date 同时使用"
        raise ValidationError(msg, status_code=422)
    if trade_date is not None:
        return (
            _normalize_datetime_param("start_time", trade_date),
            _normalize_datetime_param("end_time", trade_date),
        )
    if start_date is None and end_date is None:
        return None, None
    return (
        _normalize_datetime_param("start_time", start_date) if start_date is not None else None,
        _normalize_datetime_param("end_time", end_date) if end_date is not None else None,
    )


def _normalize_minute_freq(freq: str) -> str:
    normalized = str(freq).strip().lower()
    mapping = {
        "1": "1m",
        "1m": "1m",
        "1min": "1m",
        "5": "5m",
        "5m": "5m",
        "5min": "5m",
        "15": "15m",
        "15m": "15m",
        "15min": "15m",
        "30": "30m",
        "30m": "30m",
        "30min": "30m",
        "60": "60m",
        "60m": "60m",
        "60min": "60m",
        "120": "120m",
        "120m": "120m",
        "120min": "120m",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        msg = "freq 仅支持 1min、5min、15min、30min、60min、120min"
        raise ValidationError(msg, status_code=422) from exc


def _normalize_datetime_param(key: str, value: Any) -> str:
    is_end = key.startswith("end_")
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            msg = "暂不支持带时区的 datetime，请传入北京时间语义的无时区 datetime"
            raise ValidationError(msg, status_code=422)
        return value.isoformat()
    if isinstance(value, date):
        return _date_to_boundary_datetime(value, is_end=is_end).isoformat()
    if isinstance(value, str):
        return _normalize_datetime_string(value, is_end=is_end)
    msg = f"{key} 仅支持字符串、date 或无时区 datetime"
    raise ValidationError(msg, status_code=422)


def _normalize_datetime_string(value: str, *, is_end: bool) -> str:
    text = value.strip()
    if not text:
        msg = "时间参数不能为空字符串"
        raise ValidationError(msg, status_code=422)

    compact_match = _DATETIME_COMPACT_RE.fullmatch(text)
    if compact_match:
        date_part, time_part = compact_match.groups()
        parsed = datetime.strptime(f"{date_part}{time_part}", "%Y%m%d%H%M%S")
        return parsed.isoformat()

    if _DATE_COMPACT_RE.fullmatch(text):
        parsed_date = datetime.strptime(text, "%Y%m%d").date()
        return _date_to_boundary_datetime(parsed_date, is_end=is_end).isoformat()

    with suppress(ValueError):
        parsed_date = datetime.strptime(text, "%Y-%m-%d").date()
        return _date_to_boundary_datetime(parsed_date, is_end=is_end).isoformat()

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y%m%d %H:%M:%S",
        "%Y%m%d %H:%M",
    ):
        with suppress(ValueError):
            return datetime.strptime(text, fmt).isoformat()

    if _TIMEZONE_DATETIME_RE.fullmatch(text):
        return text

    parsed = _parse_basic_iso_datetime(text)
    if parsed is not None:
        return parsed.isoformat()

    msg = "时间格式不支持，请使用 YYYYMMDD、YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS"
    raise ValidationError(msg, status_code=422)


def _date_to_boundary_datetime(value: date, *, is_end: bool) -> datetime:
    boundary = datetime_time(23, 59, 59) if is_end else datetime_time()
    return datetime.combine(value, boundary)


def _parse_basic_iso_datetime(value: str) -> Optional[datetime]:
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S.%f"):
        with suppress(ValueError):
            return datetime.strptime(value, fmt)
    return None


def _coerce_beijing_datetime(key: str, value: Any) -> datetime:
    normalized = _normalize_datetime_param(key, value)
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed
    return parsed.astimezone(_SHANGHAI_TZ).replace(tzinfo=None)


def _product_key_for_request(endpoint_path: str, params: Mapping[str, Any]) -> Optional[str]:
    if endpoint_path == "/market/kline":
        suffix = _KLINE_PERIOD_PRODUCT_SUFFIX.get(str(params.get("period") or ""))
        if suffix is None:
            return None
        return f"{endpoint_path}#{suffix}"
    if endpoint_path in _SPLIT_PRODUCT_ENDPOINTS:
        source = str(params.get("source") or "").strip().lower()
        suffix = _SPLIT_PRODUCT_ENDPOINTS[endpoint_path].get(source)
        if suffix is None:
            return None
        return f"{endpoint_path}/{suffix}"
    if endpoint_path in _UNSPLIT_PRODUCT_ENDPOINTS:
        return endpoint_path
    return None


def _default_kline_days(period: str, limit: int) -> int:
    days_per_row = _KLINE_PERIOD_DAYS_PER_ROW.get(period)
    if days_per_row is None:
        return max(1, limit)
    # 乘以 1.5 给非交易日、停牌和数据稀疏留出缓冲，避免默认窗口太紧。
    return max(1, int(limit * days_per_row * 1.5) + 1)


def _positive_int_or_default(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _now_shanghai() -> datetime:
    return datetime.now(timezone.utc).astimezone(_SHANGHAI_TZ)


def _normalize_symbol(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    symbol = value.strip().upper()
    if not symbol:
        msg = "symbol 不能为空"
        raise ValidationError(msg, status_code=422)

    if _A_SHARE_PREFIX_SYMBOL_RE.fullmatch(symbol) or _HK_PREFIX_SYMBOL_RE.fullmatch(symbol):
        return symbol

    match = _A_SHARE_SUFFIX_SYMBOL_RE.fullmatch(symbol)
    if match:
        code, exchange = match.groups()
        return f"{exchange}{code}"

    match = _HK_SUFFIX_SYMBOL_RE.fullmatch(symbol)
    if match:
        (code,) = match.groups()
        return f"HK{code}"

    msg = (
        "symbol 格式不支持，请使用行情库代码格式 "
        "SZ301662、SH603626、BJ920693、HK06999，"
        "或兼容格式 301662.SZ、603626.SH、920693.BJ、06999.HK"
    )
    raise ValidationError(msg, status_code=422)


def _endpoint_key_from_path(path: str) -> str:
    prefix = "/api/v1/data"
    if path.startswith(prefix):
        return path[len(prefix) :]
    return path


def _decode_response(response: httpx.Response) -> Dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or status_code in {500, 502, 503, 504}


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    with suppress(ValueError):
        return max(0.0, float(value))
    with suppress(ValueError, TypeError):
        retry_at = parsedate_to_datetime(value)
        return max(0.0, retry_at.timestamp() - time.time())
    return None


def _raise_for_http_error(
    status_code: int,
    payload: Dict[str, Any],
    text: str,
    headers: httpx.Headers,
) -> None:
    if 200 <= status_code < 300:
        return
    code = payload.get("code")
    msg = payload.get("msg") or text or f"HTTP 请求失败：{status_code}"
    request_id = payload.get("request_id")
    retry_after = _parse_retry_after(headers.get("retry-after"))
    error_class = ApiError
    if status_code == 401:
        error_class = AuthenticationError
    elif status_code == 403:
        error_class = PermissionDeniedError
    elif status_code in {400, 422}:
        error_class = ValidationError
    elif status_code == 429:
        error_class = _rate_limit_error_class(str(msg))
    elif status_code >= 500:
        error_class = ServerError
    else:
        error_class = ApiError
    raise error_class(
        str(msg),
        code=code if isinstance(code, int) else None,
        status_code=status_code,
        request_id=request_id if isinstance(request_id, str) else None,
        retry_after=retry_after,
        response=payload or text,
    )


def _raise_for_business_error(payload: Dict[str, Any], status_code: int) -> None:
    code = payload.get("code", 0)
    if code in (0, None):
        return
    msg = str(payload.get("msg") or "业务请求失败")
    request_id = payload.get("request_id")
    raise ApiError(
        msg,
        code=code if isinstance(code, int) else None,
        status_code=status_code,
        request_id=request_id if isinstance(request_id, str) else None,
        response=payload,
    )


def _rate_limit_error_class(message: str) -> Type[RateLimitError]:
    if message == "并发请求数已达上限，请稍后再试。":
        return ConcurrencyRateLimitError
    if message == "分钟限频已达上限，请稍后再试。":
        return MinuteRateLimitError
    if message == "日限频已达上限，请稍后再试。":
        return DailyRateLimitError
    if message == "账单月限频已达上限，请稍后再试。":
        return MonthlyRateLimitError
    return RateLimitError
