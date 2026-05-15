"""Token 权益与客户端限流工具。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .exceptions import PermissionDeniedError

_SHANGHAI_TZ = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class EntitlementItem:
    """当前 Token 对单个逻辑商品或接口的权益。"""

    product_key: str
    endpoint_key: str
    tier_code: str
    tier_rank: int
    requests_per_minute: int
    max_concurrency: int
    burst_capacity: int
    daily_quota: Optional[int]
    monthly_quota: Optional[int]
    max_rows_per_request: Optional[int]
    max_history_days: Optional[int]
    start_time: str
    end_time: str

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> EntitlementItem:
        """从服务端权益字典构造权益项。"""

        return cls(
            product_key=str(payload.get("product_key", "")),
            endpoint_key=str(payload.get("endpoint_key", "")),
            tier_code=str(payload.get("tier_code", "")),
            tier_rank=_int_value(payload.get("tier_rank"), default=0),
            requests_per_minute=_int_value(payload.get("requests_per_minute"), default=0),
            max_concurrency=_int_value(payload.get("max_concurrency"), default=0),
            burst_capacity=_int_value(payload.get("burst_capacity"), default=0),
            daily_quota=_optional_int(payload.get("daily_quota")),
            monthly_quota=_optional_int(payload.get("monthly_quota")),
            max_rows_per_request=_optional_int(payload.get("max_rows_per_request")),
            max_history_days=_optional_int(payload.get("max_history_days")),
            start_time=str(payload.get("start_time", "")),
            end_time=str(payload.get("end_time", "")),
        )


@dataclass(frozen=True)
class EntitlementsResult:
    """当前 Token 的权益快照。"""

    key_id: str
    entitlements: List[EntitlementItem]
    code: int = 0
    msg: str = "success"
    raw: Optional[Dict[str, Any]] = None

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> EntitlementsResult:
        """从服务端响应构造权益快照。"""

        items = payload.get("entitlements") or []
        return cls(
            key_id=str(payload.get("key_id", "")),
            entitlements=[
                EntitlementItem.from_dict(item) for item in items if isinstance(item, dict)
            ],
            code=_int_value(payload.get("code"), default=0),
            msg=str(payload.get("msg", "success")),
            raw=payload,
        )


@dataclass(frozen=True)
class EndpointLimitConfig:
    """SDK 侧可执行的接口限制配置。"""

    max_concurrency: Optional[int]
    requests_per_minute: Optional[int]
    burst_capacity: Optional[int]
    max_rows_per_request: Optional[int]
    max_history_days: Optional[int]


class ProductLimiter:
    """按 `product_key` 维度维护本地限流状态。"""

    def __init__(self, entitlement: EntitlementItem) -> None:
        self._lock = threading.Lock()
        self._item = entitlement
        self._start_time = _parse_entitlement_datetime(entitlement.start_time)
        self._end_time = _parse_entitlement_datetime(entitlement.end_time)
        self._concurrency = _ConcurrencyGate(_positive_or_none(entitlement.max_concurrency))
        self._bucket = (
            _TokenBucket(
                rate_per_minute=entitlement.requests_per_minute,
                burst_capacity=entitlement.burst_capacity,
            )
            if entitlement.requests_per_minute > 0
            else None
        )

    @property
    def entitlement(self) -> EntitlementItem:
        return self._item

    @property
    def max_rows_per_request(self) -> Optional[int]:
        return self._item.max_rows_per_request

    def update(self, entitlement: EntitlementItem) -> None:
        """更新权益快照，但保留本地限流器状态。"""

        with self._lock:
            self._item = entitlement
            self._start_time = _parse_entitlement_datetime(entitlement.start_time)
            self._end_time = _parse_entitlement_datetime(entitlement.end_time)
            self._concurrency.update(_positive_or_none(entitlement.max_concurrency))
            if entitlement.requests_per_minute > 0:
                if self._bucket is None:
                    self._bucket = _TokenBucket(
                        rate_per_minute=entitlement.requests_per_minute,
                        burst_capacity=entitlement.burst_capacity,
                    )
                else:
                    self._bucket.update(
                        rate_per_minute=entitlement.requests_per_minute,
                        burst_capacity=entitlement.burst_capacity,
                    )
            else:
                self._bucket = None

    def wait_for_slot(self) -> _LimiterLease:
        """在本地完成准入判断并占用一次并发名额。"""

        self._assert_active()
        if self._bucket is not None:
            self._bucket.wait()
        return self._concurrency.acquire()

    def _assert_active(self) -> None:
        now = _now_shanghai()
        if now < self._start_time or now > self._end_time:
            msg = "当前商品权益未生效或已过期。"
            raise PermissionDeniedError(msg, status_code=403)


class EndpointLimiter:
    """按接口权益执行并发和 RPM 限制。"""

    def __init__(
        self,
        *,
        max_concurrency: Optional[int],
        requests_per_minute: Optional[int],
        burst_capacity: Optional[int],
    ) -> None:
        self._semaphore = (
            threading.BoundedSemaphore(max_concurrency)
            if max_concurrency is not None and max_concurrency > 0
            else None
        )
        self._bucket = (
            _TokenBucket(
                rate_per_minute=requests_per_minute,
                burst_capacity=burst_capacity,
            )
            if requests_per_minute is not None and requests_per_minute > 0
            else None
        )

    def wait_for_slot(self) -> _LimiterLease:
        """等待直到允许发起一次请求，并返回并发占用句柄。"""

        if self._bucket is not None:
            self._bucket.wait()
        if self._semaphore is None:
            return _LimiterLease(None)
        self._semaphore.acquire()
        return _LimiterLease(self._semaphore)


def build_limit_configs(entitlements: List[EntitlementItem]) -> Dict[str, EndpointLimitConfig]:
    """按接口合并权益，选择最高档位作为客户端限制依据。"""

    grouped: Dict[str, List[EntitlementItem]] = {}
    for item in entitlements:
        if item.endpoint_key:
            grouped.setdefault(item.endpoint_key, []).append(item)

    configs: Dict[str, EndpointLimitConfig] = {}
    for endpoint_key, items in grouped.items():
        best = max(items, key=lambda item: item.tier_rank)
        configs[endpoint_key] = EndpointLimitConfig(
            max_concurrency=_positive_or_none(best.max_concurrency),
            requests_per_minute=_positive_or_none(best.requests_per_minute),
            burst_capacity=_positive_or_none(best.burst_capacity),
            max_rows_per_request=_positive_or_none(best.max_rows_per_request),
            max_history_days=_positive_or_none(best.max_history_days),
        )
    return configs


def build_product_limit_configs(
    entitlements: List[EntitlementItem],
) -> Dict[str, EndpointLimitConfig]:
    """按商品权益构造限制配置，用于同一接口下的细分档位。"""

    configs: Dict[str, EndpointLimitConfig] = {}
    for item in entitlements:
        if item.product_key:
            configs[item.product_key] = EndpointLimitConfig(
                max_concurrency=_positive_or_none(item.max_concurrency),
                requests_per_minute=_positive_or_none(item.requests_per_minute),
                burst_capacity=_positive_or_none(item.burst_capacity),
                max_rows_per_request=_positive_or_none(item.max_rows_per_request),
                max_history_days=_positive_or_none(item.max_history_days),
            )
    return configs


def build_product_limiters(entitlements: List[EntitlementItem]) -> Dict[str, ProductLimiter]:
    """按 `product_key` 构造本地限流器。"""

    limiters: Dict[str, ProductLimiter] = {}
    for item in entitlements:
        if item.product_key:
            limiters[item.product_key] = ProductLimiter(item)
    return limiters


class _ConcurrencyGate:
    def __init__(self, limit: Optional[int]) -> None:
        self._limit = limit
        self._in_flight = 0
        self._condition = threading.Condition()

    def update(self, limit: Optional[int]) -> None:
        with self._condition:
            self._limit = limit
            self._condition.notify_all()

    def acquire(self) -> _LimiterLease:
        with self._condition:
            while self._limit is not None and self._in_flight >= self._limit:
                self._condition.wait()
            self._in_flight += 1
        return _LimiterLease(self)

    def release(self) -> None:
        with self._condition:
            self._in_flight = max(0, self._in_flight - 1)
            self._condition.notify_all()


class _LimiterLease:
    def __init__(self, releaser: Optional[_ConcurrencyGate]) -> None:
        self._releaser = releaser

    def __enter__(self) -> _LimiterLease:
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._releaser is not None:
            self._releaser.release()


class _TokenBucket:
    def __init__(self, *, rate_per_minute: int, burst_capacity: Optional[int]) -> None:
        self._condition = threading.Condition()
        self._rate_per_minute = max(1, rate_per_minute)
        self._capacity = self._normalize_capacity(burst_capacity, self._rate_per_minute)
        self._refill_per_second = self._rate_per_minute / 60.0
        self._tokens = float(self._capacity)
        self._updated_at = time.monotonic()

    def update(self, *, rate_per_minute: int, burst_capacity: Optional[int]) -> None:
        with self._condition:
            self._refill_locked()
            self._rate_per_minute = max(1, rate_per_minute)
            self._capacity = self._normalize_capacity(burst_capacity, self._rate_per_minute)
            self._refill_per_second = self._rate_per_minute / 60.0
            self._tokens = min(self._tokens, float(self._capacity))
            self._condition.notify_all()

    def wait(self) -> None:
        with self._condition:
            while True:
                self._refill_locked()
                if self._tokens >= 1:
                    self._tokens -= 1
                    return
                wait_seconds = self._wait_seconds_locked()
                self._condition.wait(timeout=wait_seconds)

    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._updated_at
        if elapsed <= 0:
            return
        self._tokens = min(
            float(self._capacity),
            self._tokens + elapsed * self._refill_per_second,
        )
        self._updated_at = now

    def _wait_seconds_locked(self) -> float:
        if self._refill_per_second <= 0:
            return 60.0
        missing = max(0.0, 1.0 - self._tokens)
        return max(0.0, missing / self._refill_per_second)

    @staticmethod
    def _normalize_capacity(burst_capacity: Optional[int], rate_per_minute: int) -> int:
        if burst_capacity is None:
            return rate_per_minute
        return max(1, min(burst_capacity, rate_per_minute))


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return _int_value(value, default=0)


def _int_value(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _positive_or_none(value: Optional[int]) -> Optional[int]:
    if value is None or value <= 0:
        return None
    return value


def _parse_entitlement_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=_SHANGHAI_TZ)
    return parsed


def _now_shanghai() -> datetime:
    return datetime.now(timezone.utc).astimezone(_SHANGHAI_TZ)
