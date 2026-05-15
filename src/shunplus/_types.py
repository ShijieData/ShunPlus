"""SDK 内部类型定义。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Union

DateLike = Union[str, date, datetime]
ResultFormat = Literal["table", "dict", "dataframe", "raw"]
