"""SDK 异常类型。"""

from __future__ import annotations

from typing import List, Optional


class ShunplusError(Exception):
    """SDK 基础异常。"""


class ApiError(ShunplusError):
    """服务端返回非成功业务码或 HTTP 错误。"""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[int] = None,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
        retry_after: Optional[float] = None,
        response: Optional[object] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.request_id = request_id
        self.retry_after = retry_after
        self.response = response

    def __str__(self) -> str:
        details: List[str] = []
        if self.status_code is not None:
            details.append(f"HTTP {self.status_code}")
        if self.code is not None:
            details.append(f"code={self.code}")
        if self.request_id:
            details.append(f"request_id={self.request_id}")
        if self.retry_after is not None:
            details.append(f"retry_after={self.retry_after:g}s")
        suffix = f" ({', '.join(details)})" if details else ""
        return f"{super().__str__()}{suffix}"


class AuthenticationError(ApiError):
    """认证失败或 Token 无效。"""


class PermissionDeniedError(ApiError):
    """账号无接口访问权益。"""


class RateLimitError(ApiError):
    """调用频率超限。"""


class ConcurrencyRateLimitError(RateLimitError):
    """并发请求数已达上限。"""


class MinuteRateLimitError(RateLimitError):
    """分钟限频已达上限。"""


class DailyRateLimitError(RateLimitError):
    """日限频已达上限。"""


class MonthlyRateLimitError(RateLimitError):
    """账单月限频已达上限。"""


class ValidationError(ApiError):
    """请求参数校验失败。"""


class ServerError(ApiError):
    """服务端内部错误。"""
