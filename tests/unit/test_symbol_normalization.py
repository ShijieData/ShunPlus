import pytest

from shunplus import ValidationError
from shunplus.client import _normalize_symbol


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SZ301662", "SZ301662"),
        ("sz301662", "SZ301662"),
        (" 301662.SZ ", "SZ301662"),
        ("603626.SH", "SH603626"),
        ("920693.BJ", "BJ920693"),
        ("HK06999", "HK06999"),
        ("hk06999", "HK06999"),
        ("06999.HK", "HK06999"),
    ],
)
def test_normalize_symbol_to_backend_market_code(raw: str, expected: str) -> None:
    assert _normalize_symbol(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "000001",
        "00700",
        "HK6999",
        "6999.HK",
        "AAPL",
        "aapl.us",
        "SZ30166",
        "301662",
    ],
)
def test_normalize_symbol_rejects_unsupported_symbol(raw: str) -> None:
    with pytest.raises(ValidationError):
        _normalize_symbol(raw)
