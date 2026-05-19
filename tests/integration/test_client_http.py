from __future__ import annotations

import gzip
import inspect
import io
import json
import pathlib
import sys
from datetime import date, datetime, timezone

import httpx
import pytest

from shunplus import (
    AuthenticationError,
    Client,
    EntitlementsResult,
    MinuteRateLimitError,
    PermissionDeniedError,
    ValidationError,
    clear_token,
    get_token,
    set_token,
    shun_api,
    token_config_path,
)
from shunplus.client import DEFAULT_BASE_URL


@pytest.fixture(autouse=True)
def _isolated_local_token_config(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SHUNPLUS_CONFIG_FILE", str(tmp_path / "shunplus-config.json"))
    clear_token()
    yield
    clear_token()


def test_client_uses_current_backend_base_url_by_default() -> None:
    client = Client(token="test-token", auto_configure_limits=False)

    assert client.base_url == DEFAULT_BASE_URL
    assert DEFAULT_BASE_URL == "https://api.shunplus.com"
    assert "base_url" not in inspect.signature(Client).parameters
    assert "base_url" not in inspect.signature(shun_api).parameters


def _mocked_client(handler: httpx.MockTransport) -> Client:
    client = Client(token="test-token", auto_configure_limits=False, max_retries=0)
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=handler,
    )
    return client


def test_client_sends_bearer_token_and_returns_table_result() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers["authorization"]
        seen["url"] = str(request.url)
        payload = {
            "code": 0,
            "msg": "success",
            "fields": ["ts", "close"],
            "data": [["2026-04-03T00:00:00+08:00", 10.4]],
            "next_cursor": None,
            "next_cursor_id": None,
        }
        return httpx.Response(200, json=payload)

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.kline(
        period="day",
        symbol="SZ301662",
        start_time=datetime(2026, 4, 3),
        end_time=datetime(2026, 4, 4),
        fields=["close", "ts"],
    )

    assert seen["authorization"] == "Bearer test-token"
    assert seen["url"].startswith(f"{DEFAULT_BASE_URL}/api/v1/data/market/kline?")
    assert "start_time=2026-04-03T00%3A00%3A00" in seen["url"]
    assert "end_time=2026-04-04T00%3A00%3A00" in seen["url"]
    assert result.fields == ["close", "ts"]
    assert result.data == [[10.4, "2026-04-03T00:00:00+08:00"]]


@pytest.mark.parametrize(
    ("raw_symbol", "expected_symbol"),
    [
        ("SZ301662", "SZ301662"),
        ("301662.SZ", "SZ301662"),
        ("603626.sh", "SH603626"),
    ],
)
def test_client_normalizes_symbol_before_request(
    raw_symbol: str,
    expected_symbol: str,
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["symbol"] = request.url.params["symbol"]
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["symbol"], "data": [[seen["symbol"]]]},
        )

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.kline(period="day", symbol=raw_symbol)

    assert seen["symbol"] == expected_symbol
    assert result.to_dicts() == [{"symbol": expected_symbol}]


def test_fetch_all_follows_cursor() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            payload = {
                "code": 0,
                "fields": ["symbol"],
                "data": [["SZ301662"]],
                "next_cursor": 100,
                "next_cursor_id": "a",
            }
        else:
            assert request.url.params["cursor"] == "100"
            assert request.url.params["cursor_id"] == "a"
            payload = {
                "code": 0,
                "fields": ["symbol"],
                "data": [["SZ301663"]],
                "next_cursor": None,
                "next_cursor_id": None,
            }
        return httpx.Response(200, json=payload)

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.fetch_all("symbols")

    assert calls == 2
    assert result.to_dicts() == [{"symbol": "SZ301662"}, {"symbol": "SZ301663"}]


def test_client_decodes_gzip_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.dumps(
            {
                "code": 0,
                "fields": ["symbol", "name"],
                "data": [["SZ301662", "平安银行"]],
            },
            ensure_ascii=False,
        ).encode()
        return httpx.Response(
            200,
            content=gzip.compress(payload),
            headers={
                "content-encoding": "gzip",
                "content-type": "application/json",
            },
        )

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.symbols()

    assert result.to_dicts() == [{"symbol": "SZ301662", "name": "平安银行"}]


def test_http_error_maps_to_specific_exception() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {"code": 429001, "msg": "分钟限频已达上限，请稍后再试。", "request_id": "req-1"}
        return httpx.Response(429, json=payload)

    client = _mocked_client(httpx.MockTransport(handler))

    with pytest.raises(MinuteRateLimitError) as exc_info:
        client.symbols()

    assert exc_info.value.code == 429001
    assert exc_info.value.request_id == "req-1"


def test_rate_limit_error_exposes_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = {"code": 429001, "msg": "分钟限频已达上限，请稍后再试。", "request_id": "req-1"}
        return httpx.Response(429, json=payload, headers={"retry-after": "3"})

    client = _mocked_client(httpx.MockTransport(handler))

    with pytest.raises(MinuteRateLimitError) as exc_info:
        client.symbols()

    assert exc_info.value.retry_after == 3
    assert "retry_after=3s" in str(exc_info.value)


def test_client_does_not_retry_rate_limit_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            429,
            json={"code": 429001, "msg": "分钟限频已达上限，请稍后再试。"},
            headers={"retry-after": "0"},
        )

    client = Client(
        token="test-token",
        auto_configure_limits=False,
        max_retries=1,
        retry_backoff=0,
    )
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(MinuteRateLimitError):
        client.symbols()

    assert calls == 1


def test_client_does_not_retry_permission_error() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(403, json={"code": 403001, "msg": "无接口权益"})

    client = Client(
        token="test-token",
        auto_configure_limits=False,
        max_retries=2,
        retry_backoff=0,
    )
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(PermissionDeniedError):
        client.symbols()

    assert calls == 1


def test_client_retries_transport_error_once_and_then_succeeds() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("连接失败", request=request)
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["symbol"], "data": [["SZ301662"]]},
        )

    client = Client(
        token="test-token",
        auto_configure_limits=False,
        max_retries=1,
        retry_backoff=0,
    )
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    result = client.symbols()

    assert calls == 2
    assert result.to_dicts() == [{"symbol": "SZ301662"}]


def test_missing_token_is_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHUNPLUS_API_TOKEN", raising=False)
    monkeypatch.delenv("SHUNPLUS_TOKEN", raising=False)
    clear_token()
    client = Client(
        token=None,
        auto_configure_limits=False,
    )

    with pytest.raises(AuthenticationError, match="缺少 API Token"):
        client.symbols()


def test_set_token_persists_to_local_json_config(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "shunplus-config.json"
    monkeypatch.setenv("SHUNPLUS_CONFIG_FILE", str(config_path))
    clear_token()

    saved_path = set_token("  local-token  ")

    assert saved_path == str(config_path)
    assert token_config_path() == str(config_path)
    assert get_token() == "local-token"
    assert json.loads(config_path.read_text(encoding="utf-8"))["token"] == "local-token"


def test_client_reads_token_from_local_config(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "shunplus-config.json"
    monkeypatch.setenv("SHUNPLUS_CONFIG_FILE", str(config_path))
    monkeypatch.delenv("SHUNPLUS_API_TOKEN", raising=False)
    monkeypatch.delenv("SHUNPLUS_TOKEN", raising=False)
    clear_token()
    set_token("persisted-token")

    client = Client(auto_configure_limits=False)

    assert client.token == "persisted-token"


def test_client_can_update_and_reload_token(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "shunplus-config.json"
    monkeypatch.setenv("SHUNPLUS_CONFIG_FILE", str(config_path))
    clear_token()
    client = Client(token="initial-token", auto_configure_limits=False)

    client.set_token("rotated-token")
    assert client.token == "rotated-token"

    clear_token()
    set_token("reloaded-token")

    assert client.reload_token() == "reloaded-token"
    assert client.token == "reloaded-token"


def test_clear_token_removes_persisted_token(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "shunplus-config.json"
    monkeypatch.setenv("SHUNPLUS_CONFIG_FILE", str(config_path))
    set_token("to-be-cleared")

    clear_token()

    assert get_token() is None
    if config_path.exists():
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        assert "token" not in payload


def test_iter_pages_can_render_console_progress(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            payload = {
                "code": 0,
                "fields": ["symbol"],
                "data": [["SZ301662"]],
                "next_cursor": 100,
                "next_cursor_id": "a",
                "query_meta": {"total": 2},
            }
        else:
            payload = {
                "code": 0,
                "fields": ["symbol"],
                "data": [["SZ301663"]],
                "next_cursor": None,
                "next_cursor_id": None,
                "query_meta": {"total": 2},
            }
        return httpx.Response(200, json=payload)

    client = _mocked_client(httpx.MockTransport(handler))
    fake_stderr = io.StringIO()
    monkeypatch.setattr(sys, "stderr", fake_stderr)

    pages = list(client.iter_pages("symbols", show_progress=True))

    assert len(pages) == 2
    output = fake_stderr.getvalue()
    assert "symbols" in output
    assert "2/2 rows" in output
    assert "done" in output


def test_fetch_all_calls_on_page_for_each_page() -> None:
    calls = 0
    seen_pages: list[tuple[int, list[dict[str, str]]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            payload = {
                "code": 0,
                "fields": ["symbol"],
                "data": [["SZ301662"]],
                "next_cursor": 100,
                "next_cursor_id": "a",
            }
        else:
            payload = {
                "code": 0,
                "fields": ["symbol"],
                "data": [["SZ301663"]],
                "next_cursor": None,
                "next_cursor_id": None,
            }
        return httpx.Response(200, json=payload)

    def on_page(page_no: int, page: object) -> None:
        assert hasattr(page, "to_dicts")
        seen_pages.append((page_no, page.to_dicts()))

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.fetch_all("symbols", on_page=on_page)

    assert result.to_dicts() == [{"symbol": "SZ301662"}, {"symbol": "SZ301663"}]
    assert seen_pages == [
        (1, [{"symbol": "SZ301662"}]),
        (2, [{"symbol": "SZ301663"}]),
    ]


def test_kline_adjusted_merges_factors_and_applies_qfq() -> None:
    factor_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal factor_calls
        if request.url.path == "/api/v1/data/market/kline":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["ts", "open", "high", "low", "close", "volume"],
                    "data": [
                        ["2026-05-09T00:00:00+08:00", 20.0, 22.0, 19.0, 21.0, 1000],
                        ["2026-05-08T00:00:00+08:00", 10.0, 12.0, 9.0, 11.0, 900],
                    ],
                },
            )
        if request.url.path == "/api/v1/data/market/factors":
            factor_calls += 1
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["trade_date", "factor"],
                    "data": [
                        ["2026-05-09", 2.0],
                        ["2026-05-08", 1.0],
                    ],
                },
            )
        raise AssertionError(str(request.url))

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.kline_adjusted(
        period="day",
        symbol="SZ301662",
        adj="qfq",
        include_factor=True,
        format="dict",
    )

    assert factor_calls == 1
    assert result == [
        {
            "ts": "2026-05-09T00:00:00+08:00",
            "open": 20.0,
            "high": 22.0,
            "low": 19.0,
            "close": 21.0,
            "volume": 1000,
            "adj_factor": 2.0,
        },
        {
            "ts": "2026-05-08T00:00:00+08:00",
            "open": 5.0,
            "high": 6.0,
            "low": 4.5,
            "close": 5.5,
            "volume": 900,
            "adj_factor": 1.0,
        },
    ]


def test_kline_adjusted_supports_factor_alias_in_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/data/market/kline":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["ts", "open", "close"],
                    "data": [["2026-05-09T00:00:00+08:00", 20.0, 21.0]],
                },
            )
        if request.url.path == "/api/v1/data/market/factors":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["trade_date", "factor"],
                    "data": [["2026-05-09", 2.0]],
                },
            )
        raise AssertionError(str(request.url))

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.kline_adjusted(
        period="day",
        symbol="SZ301662",
        fields=["ts", "factor"],
        format="dict",
    )

    assert result == [{"ts": "2026-05-09T00:00:00+08:00", "adj_factor": 2.0}]


def test_daily_with_factors_enriches_rows_in_original_order() -> None:
    factor_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal factor_calls
        if request.url.path == "/api/v1/data/market/kline":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["ts", "close", "percent", "turnoverrate"],
                    "data": [
                        ["2026-05-09T00:00:00+08:00", 21.0, 90.9091, 3.2],
                        ["2026-05-08T00:00:00+08:00", 11.0, None, 2.1],
                    ],
                },
            )
        if request.url.path == "/api/v1/data/market/factors":
            factor_calls += 1
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["trade_date", "factor"],
                    "data": [
                        ["2026-05-09", 2.0],
                        ["2026-05-08", 1.0],
                    ],
                },
            )
        raise AssertionError(str(request.url))

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.daily_with_factors(
        ts_code="301662.SZ",
        fields=["ts", "close", "adj_factor", "pre_close", "change", "pct_chg", "turnoverrate"],
        format="dict",
    )

    assert factor_calls == 1
    assert result == [
        {
            "ts": "2026-05-09T00:00:00+08:00",
            "close": 21.0,
            "adj_factor": 2.0,
            "pre_close": 11.0,
            "change": 10.0,
            "pct_chg": 90.9091,
            "turnoverrate": 3.2,
        },
        {
            "ts": "2026-05-08T00:00:00+08:00",
            "close": 11.0,
            "adj_factor": 1.0,
            "pre_close": None,
            "change": None,
            "pct_chg": None,
            "turnoverrate": 2.1,
        },
    ]


def test_daily_with_factors_computes_pct_chg_when_percent_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/data/market/kline":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["ts", "close"],
                    "data": [
                        ["2026-05-09T00:00:00+08:00", 21.0],
                        ["2026-05-08T00:00:00+08:00", 11.0],
                    ],
                },
            )
        if request.url.path == "/api/v1/data/market/factors":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "fields": ["trade_date", "factor"],
                    "data": [
                        ["2026-05-09", 2.0],
                        ["2026-05-08", 1.0],
                    ],
                },
            )
        raise AssertionError(str(request.url))

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.daily_with_factors(
        ts_code="301662.SZ",
        factors=["pct_chg"],
        fields=["ts", "pct_chg"],
        format="dict",
    )

    assert result == [
        {"ts": "2026-05-09T00:00:00+08:00", "pct_chg": 90.9091},
        {"ts": "2026-05-08T00:00:00+08:00", "pct_chg": None},
    ]


def test_shun_api_defaults_to_dataframe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(
                {"code": 0, "fields": ["symbol"], "data": [["SZ301662"]]},
                ensure_ascii=False,
            ).encode(),
            headers={"content-type": "application/json"},
        )

    client = shun_api(
        "test-token",
        default_format="dataframe",
        auto_configure_limits=False,
    )
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    dataframe = client.symbols()

    assert list(dataframe["symbol"]) == ["SZ301662"]


def test_shun_api_is_only_public_convenience_entrypoint() -> None:
    import shunplus

    assert hasattr(shunplus, "shun_api")
    assert not hasattr(shunplus, "pro_api")


@pytest.mark.parametrize(
    ("start_time", "end_time", "expected_start", "expected_end"),
    [
        ("20260510", "20260510", "2026-05-10T00:00:00", "2026-05-10T23:59:59"),
        ("2026-05-10", "2026-05-10", "2026-05-10T00:00:00", "2026-05-10T23:59:59"),
        (
            "2026-05-10 10:00:00",
            "2026-05-10 15:00:00",
            "2026-05-10T10:00:00",
            "2026-05-10T15:00:00",
        ),
        (
            date(2026, 5, 10),
            date(2026, 5, 10),
            "2026-05-10T00:00:00",
            "2026-05-10T23:59:59",
        ),
    ],
)
def test_kline_accepts_common_beijing_time_formats(
    start_time: object,
    end_time: object,
    expected_start: str,
    expected_end: str,
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["start_time"] = request.url.params["start_time"]
        seen["end_time"] = request.url.params["end_time"]
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["symbol"], "data": [["SZ301662"]]},
        )

    client = _mocked_client(httpx.MockTransport(handler))

    client.kline(
        period="day",
        symbol="SZ301662",
        start_time=start_time,
        end_time=end_time,
    )

    assert seen["start_time"] == expected_start
    assert seen["end_time"] == expected_end


def test_kline_rejects_timezone_aware_datetime_without_guessing_business_semantics() -> None:
    client = _mocked_client(httpx.MockTransport(lambda request: httpx.Response(500)))

    with pytest.raises(ValidationError, match="暂不支持带时区"):
        client.kline(
            period="day",
            symbol="SZ301662",
            start_time=datetime(2026, 5, 10, tzinfo=timezone.utc),
            end_time=datetime(2026, 5, 11),
        )


def test_daily_maps_compat_params_to_day_kline() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["period"] = request.url.params["period"]
        seen["symbol"] = request.url.params["symbol"]
        seen["start_time"] = request.url.params["start_time"]
        seen["end_time"] = request.url.params["end_time"]
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["ts"], "data": [["2026-05-10"]]},
        )

    client = _mocked_client(httpx.MockTransport(handler))

    client.daily(ts_code="301662.SZ", trade_date="20260510")

    assert seen == {
        "period": "day",
        "symbol": "SZ301662",
        "start_time": "2026-05-10T00:00:00",
        "end_time": "2026-05-10T23:59:59",
    }


def test_stk_mins_maps_compat_freq_and_time_range() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["period"] = request.url.params["period"]
        seen["symbol"] = request.url.params["symbol"]
        seen["start_time"] = request.url.params["start_time"]
        seen["end_time"] = request.url.params["end_time"]
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["ts"], "data": [["2026-05-10"]]},
        )

    client = _mocked_client(httpx.MockTransport(handler))

    client.stk_mins(
        ts_code="301662.SZ",
        freq="5min",
        start_date="2026-05-10 09:30:00",
        end_date="2026-05-10 15:00:00",
    )

    assert seen == {
        "period": "5m",
        "symbol": "SZ301662",
        "start_time": "2026-05-10T09:30:00",
        "end_time": "2026-05-10T15:00:00",
    }


def test_dataframe_proxy_returns_dataframe() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/data/symbols"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "fields": ["symbol", "name"],
                "data": [["SZ301662", "新莱福"]],
            },
        )

    client = _mocked_client(httpx.MockTransport(handler))

    dataframe = client.df.symbols(exchange="SZ")

    assert list(dataframe.columns) == ["symbol", "name"]
    assert dataframe.iloc[0].to_dict() == {"symbol": "SZ301662", "name": "新莱福"}


def test_entitlements_returns_structured_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/data/entitlements"
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "key_id": "key-demo",
                "entitlements": [
                    {
                        "product_key": "/symbols#base",
                        "endpoint_key": "/symbols",
                        "tier_code": "symbols-basic",
                        "tier_rank": 1,
                        "requests_per_minute": 120,
                        "max_concurrency": 4,
                        "burst_capacity": 20,
                        "daily_quota": 1000,
                        "monthly_quota": 30000,
                        "max_rows_per_request": 50,
                        "max_history_days": None,
                        "start_time": "2026-05-04T20:55:48+08:00",
                        "end_time": "2027-05-04T20:55:48+08:00",
                    }
                ],
            },
        )

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.entitlements()

    assert isinstance(result, EntitlementsResult)
    assert result.key_id == "key-demo"
    assert result.entitlements[0].endpoint_key == "/symbols"
    assert result.entitlements[0].max_rows_per_request == 50


def test_auto_entitlements_uses_max_rows_as_default_limit() -> None:
    seen_limits: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/data/entitlements":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "key_id": "key-demo",
                    "entitlements": [
                        {
                            "product_key": "/symbols",
                            "endpoint_key": "/symbols",
                            "tier_code": "symbols-basic",
                            "tier_rank": 1,
                            "requests_per_minute": 60000,
                            "max_concurrency": 2,
                            "burst_capacity": 60000,
                            "daily_quota": None,
                            "monthly_quota": None,
                            "max_rows_per_request": 50,
                            "max_history_days": None,
                            "start_time": "2026-05-04T20:55:48+08:00",
                            "end_time": "2027-05-04T20:55:48+08:00",
                        }
                    ],
                },
            )

        seen_limits.append(request.url.params.get("limit"))
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "fields": ["symbol"],
                "data": [["SZ301662"]],
            },
        )

    client = Client(token="test-token")
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    result = client.symbols()

    assert result.to_dicts() == [{"symbol": "SZ301662"}]
    assert seen_limits == ["50"]


def test_auto_entitlements_rejects_limit_above_max_rows() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/data/entitlements":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "key_id": "key-demo",
                    "entitlements": [
                        {
                            "product_key": "/symbols",
                            "endpoint_key": "/symbols",
                            "tier_code": "symbols-basic",
                            "tier_rank": 1,
                            "requests_per_minute": 60000,
                            "max_concurrency": 2,
                            "burst_capacity": 60000,
                            "daily_quota": None,
                            "monthly_quota": None,
                            "max_rows_per_request": 50,
                            "max_history_days": None,
                            "start_time": "2026-05-04T20:55:48+08:00",
                            "end_time": "2027-05-04T20:55:48+08:00",
                        }
                    ],
                },
            )
        raise AssertionError("超限请求不应发到服务端")

    client = Client(token="test-token")
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ValidationError, match="当前商品单次最多只能拉取 50 条记录。"):
        client.symbols(limit=100)


def test_auto_entitlements_does_not_track_daily_or_monthly_quota_locally() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/api/v1/data/entitlements":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "key_id": "key-demo",
                    "entitlements": [
                        {
                            "product_key": "/symbols",
                            "endpoint_key": "/symbols",
                            "tier_code": "symbols-basic",
                            "tier_rank": 1,
                            "requests_per_minute": 60000,
                            "max_concurrency": 2,
                            "burst_capacity": 60000,
                            "daily_quota": 1,
                            "monthly_quota": 1,
                            "max_rows_per_request": 50,
                            "max_history_days": None,
                            "start_time": "2026-05-04T20:55:48+08:00",
                            "end_time": "2027-05-04T20:55:48+08:00",
                        }
                    ],
                },
            )

        calls += 1
        return httpx.Response(
            200,
            json={
                "code": 0,
                "msg": "success",
                "fields": ["symbol"],
                "data": [["SZ301662"]],
            },
        )

    client = Client(token="test-token")
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    first = client.symbols()
    second = client.symbols()

    assert first.to_dicts() == [{"symbol": "SZ301662"}]
    assert second.to_dicts() == [{"symbol": "SZ301662"}]
    assert calls == 2


def test_kline_auto_fills_time_range_and_uses_period_product_limit() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/data/entitlements":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "key_id": "key-demo",
                    "entitlements": [
                        {
                            "product_key": "/market/kline#long",
                            "endpoint_key": "/market/kline",
                            "tier_code": "market-kline-long",
                            "tier_rank": 1,
                            "requests_per_minute": 60000,
                            "max_concurrency": 2,
                            "burst_capacity": 60000,
                            "daily_quota": None,
                            "monthly_quota": None,
                            "max_rows_per_request": 800,
                            "max_history_days": 1460,
                            "start_time": "2026-05-04T20:55:48+08:00",
                            "end_time": "2027-05-04T20:55:48+08:00",
                        },
                        {
                            "product_key": "/market/kline#1m",
                            "endpoint_key": "/market/kline",
                            "tier_code": "market-kline-1m",
                            "tier_rank": 1,
                            "requests_per_minute": 60000,
                            "max_concurrency": 2,
                            "burst_capacity": 60000,
                            "daily_quota": None,
                            "monthly_quota": None,
                            "max_rows_per_request": 10,
                            "max_history_days": 3,
                            "start_time": "2026-05-04T20:55:48+08:00",
                            "end_time": "2027-05-04T20:55:48+08:00",
                        },
                    ],
                },
            )

        seen["limit"] = request.url.params.get("limit")
        seen["start_time"] = request.url.params.get("start_time")
        seen["end_time"] = request.url.params.get("end_time")
        seen["period"] = request.url.params.get("period")
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["symbol"], "data": [["SZ301662"]]},
        )

    client = Client(token="test-token")
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    result = client.kline(period="1m", symbol="SZ301662")

    assert result.to_dicts() == [{"symbol": "SZ301662"}]
    assert seen["period"] == "1m"
    assert seen["limit"] == "10"
    assert seen["start_time"] is not None
    assert seen["end_time"] is not None

    start_time = datetime.fromisoformat(seen["start_time"])
    end_time = datetime.fromisoformat(seen["end_time"])
    assert 0 < (end_time - start_time).total_seconds() <= 3 * 24 * 60 * 60


def test_kline_15m_uses_advanced_period_product_limit() -> None:
    seen: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/data/entitlements":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "msg": "success",
                    "key_id": "key-demo",
                    "entitlements": [
                        {
                            "product_key": "/market/kline#advanced",
                            "endpoint_key": "/market/kline",
                            "tier_code": "market-kline-advanced",
                            "tier_rank": 1,
                            "requests_per_minute": 60000,
                            "max_concurrency": 2,
                            "burst_capacity": 60000,
                            "daily_quota": None,
                            "monthly_quota": None,
                            "max_rows_per_request": 12,
                            "max_history_days": 5,
                            "start_time": "2026-05-04T20:55:48+08:00",
                            "end_time": "2027-05-04T20:55:48+08:00",
                        },
                    ],
                },
            )

        seen["limit"] = request.url.params.get("limit")
        seen["start_time"] = request.url.params.get("start_time")
        seen["end_time"] = request.url.params.get("end_time")
        seen["period"] = request.url.params.get("period")
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["symbol"], "data": [["SZ301662"]]},
        )

    client = Client(token="test-token")
    client._client = httpx.Client(
        base_url=DEFAULT_BASE_URL,
        transport=httpx.MockTransport(handler),
    )

    result = client.kline(period="15m", symbol="SZ301662")

    assert result.to_dicts() == [{"symbol": "SZ301662"}]
    assert seen["period"] == "15m"
    assert seen["limit"] == "12"
    assert seen["start_time"] is not None
    assert seen["end_time"] is not None

    start_time = datetime.fromisoformat(seen["start_time"])
    end_time = datetime.fromisoformat(seen["end_time"])
    assert 0 < (end_time - start_time).total_seconds() <= 5 * 24 * 60 * 60


def test_kline_fills_missing_end_time_from_start_time() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["start_time"] = request.url.params["start_time"]
        seen["end_time"] = request.url.params["end_time"]
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["symbol"], "data": [["SZ301662"]]},
        )

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.kline(
        period="day",
        symbol="SZ301662",
        start_time="2026-04-01",
        limit=1,
    )

    assert result.to_dicts() == [{"symbol": "SZ301662"}]
    assert seen["start_time"] == "2026-04-01T00:00:00"
    assert seen["end_time"] == "2026-04-04T00:00:00"


def test_kline_fills_missing_start_time_from_end_time() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["start_time"] = request.url.params["start_time"]
        seen["end_time"] = request.url.params["end_time"]
        return httpx.Response(
            200,
            json={"code": 0, "msg": "success", "fields": ["symbol"], "data": [["SZ301662"]]},
        )

    client = _mocked_client(httpx.MockTransport(handler))

    result = client.kline(
        period="day",
        symbol="SZ301662",
        end_time="2026-04-10",
        limit=1,
    )

    assert result.to_dicts() == [{"symbol": "SZ301662"}]
    assert seen["start_time"] == "2026-04-07T23:59:59"
    assert seen["end_time"] == "2026-04-10T23:59:59"
