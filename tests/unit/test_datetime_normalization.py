from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from shunplus import ValidationError
from shunplus.client import (
    _normalize_datetime_param,
    _normalize_minute_freq,
    _resolve_date_range,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20260510", "2026-05-10T00:00:00"),
        ("2026-05-10", "2026-05-10T00:00:00"),
        ("2026-05-10 10:00:00", "2026-05-10T10:00:00"),
        ("20260510100000", "2026-05-10T10:00:00"),
        ("20260510 10:00:00", "2026-05-10T10:00:00"),
        (date(2026, 5, 10), "2026-05-10T00:00:00"),
        (datetime(2026, 5, 10, 10, 0, 0), "2026-05-10T10:00:00"),
    ],
)
def test_normalize_start_time_accepts_common_beijing_time_inputs(
    raw: object,
    expected: str,
) -> None:
    assert _normalize_datetime_param("start_time", raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20260510", "2026-05-10T23:59:59"),
        ("2026-05-10", "2026-05-10T23:59:59"),
        (date(2026, 5, 10), "2026-05-10T23:59:59"),
    ],
)
def test_normalize_end_time_expands_date_to_day_end(raw: object, expected: str) -> None:
    assert _normalize_datetime_param("end_time", raw) == expected


def test_normalize_datetime_rejects_timezone_aware_datetime() -> None:
    with pytest.raises(ValidationError, match="暂不支持带时区"):
        _normalize_datetime_param("start_time", datetime(2026, 5, 10, tzinfo=timezone.utc))


def test_resolve_trade_date_to_full_day_range() -> None:
    assert _resolve_date_range(
        trade_date="20260510",
        start_date=None,
        end_date=None,
    ) == ("2026-05-10T00:00:00", "2026-05-10T23:59:59")


def test_resolve_date_range_rejects_mixed_trade_date_and_range() -> None:
    with pytest.raises(ValidationError, match="trade_date"):
        _resolve_date_range(
            trade_date="20260510",
            start_date="20260501",
            end_date=None,
        )


def test_resolve_date_range_accepts_start_date_only() -> None:
    assert _resolve_date_range(
        trade_date=None,
        start_date="20260501",
        end_date=None,
    ) == ("2026-05-01T00:00:00", None)


def test_resolve_date_range_accepts_end_date_only() -> None:
    assert _resolve_date_range(
        trade_date=None,
        start_date=None,
        end_date="20260510",
    ) == (None, "2026-05-10T23:59:59")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", "1m"),
        ("1min", "1m"),
        ("5min", "5m"),
        ("15m", "15m"),
        ("30MIN", "30m"),
        ("60", "60m"),
        ("120min", "120m"),
    ],
)
def test_normalize_minute_freq(raw: str, expected: str) -> None:
    assert _normalize_minute_freq(raw) == expected


def test_normalize_minute_freq_rejects_unsupported_value() -> None:
    with pytest.raises(ValidationError, match="freq"):
        _normalize_minute_freq("2min")
