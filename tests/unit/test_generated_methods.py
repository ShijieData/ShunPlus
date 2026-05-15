import inspect
from typing import get_type_hints

from shunplus._generated import ENDPOINTS
from shunplus.client import Client


def test_openapi_methods_are_exposed() -> None:
    for method_name in ENDPOINTS:
        assert hasattr(Client, method_name)


def test_generated_method_signature_contains_business_params() -> None:
    signature = inspect.signature(Client.kline)

    assert "period" in signature.parameters
    assert "symbol" in signature.parameters
    assert "fields" in signature.parameters
    assert "format" in signature.parameters


def test_compat_kline_methods_are_exposed() -> None:
    daily_signature = inspect.signature(Client.daily)
    minute_signature = inspect.signature(Client.stk_mins)
    adjusted_signature = inspect.signature(Client.kline_adjusted)
    enriched_daily_signature = inspect.signature(Client.daily_with_factors)

    assert "ts_code" in daily_signature.parameters
    assert "trade_date" in daily_signature.parameters
    assert "start_date" in daily_signature.parameters
    assert "end_date" in daily_signature.parameters
    assert "ts_code" in minute_signature.parameters
    assert "freq" in minute_signature.parameters
    assert "adj" in adjusted_signature.parameters
    assert "factors" in enriched_daily_signature.parameters


def test_kline_period_signature_includes_15m() -> None:
    period_param = next(
        param for param in ENDPOINTS["kline"]["parameters"] if param["name"] == "period"
    )
    assert "15m" in period_param["schema"]["enum"]
    assert get_type_hints(Client.kline)["period"] is str


def test_non_table_generated_method_has_plain_signature() -> None:
    signature = inspect.signature(Client.entitlements)

    assert "fields" not in signature.parameters
    assert "format" not in signature.parameters


def test_stock_news_source_excludes_legacy_futunn() -> None:
    source_param = next(
        param for param in ENDPOINTS["stock_news"]["parameters"] if param["name"] == "source"
    )
    signature = inspect.signature(Client.stock_news)

    assert source_param["schema"]["enum"] == ["xueqiu", "futu"]
    assert "futunn" not in str(signature.parameters["source"].annotation)
