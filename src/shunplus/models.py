"""SDK 数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union


@dataclass(frozen=True)
class TableResult:
    """列式表格响应。

    服务端返回 `fields + data`，SDK 在这里保留原始列式结构，同时提供行字典和
    DataFrame 转换，方便在脚本、服务端和数据分析场景复用同一结果。
    """

    fields: List[str]
    data: List[List[Any]]
    code: int = 0
    msg: str = "success"
    next_cursor: Optional[int] = None
    next_cursor_id: Optional[str] = None
    query_meta: Optional[Dict[str, Any]] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def rows(self) -> List[List[Any]]:
        """二维数组行数据。"""

        return self.data

    @property
    def has_more(self) -> bool:
        """是否存在下一页。"""

        return self.next_cursor is not None or self.next_cursor_id is not None

    @property
    def empty(self) -> bool:
        """是否没有返回数据行。"""

        return not self.data

    def to_dicts(self) -> List[Dict[str, Any]]:
        """转换为字典行列表。"""

        return [dict(zip(self.fields, row)) for row in self.data]

    def iter_dicts(self) -> Iterable[Dict[str, Any]]:
        """逐行迭代字典数据。"""

        for row in self.data:
            yield dict(zip(self.fields, row))

    def select(self, fields: Union[str, Sequence[str]]) -> TableResult:
        """按字段名筛选并重排列。"""

        selected = _parse_fields(fields)
        if not selected:
            return self

        positions = {name: index for index, name in enumerate(self.fields)}
        missing = [name for name in selected if name not in positions]
        if missing:
            raise KeyError(f"响应中不存在字段：{', '.join(missing)}")

        indexes = [positions[name] for name in selected]
        return TableResult(
            fields=list(selected),
            data=[[row[index] for index in indexes] for row in self.data],
            code=self.code,
            msg=self.msg,
            next_cursor=self.next_cursor,
            next_cursor_id=self.next_cursor_id,
            query_meta=self.query_meta,
            raw=self.raw,
        )

    def to_dataframe(self) -> Any:
        """转换为 pandas DataFrame。

        pandas 是可选能力；未安装时会给出明确提示，而不是在导入 SDK 时强制依赖。
        """

        try:
            import pandas as pd
        except ImportError as exc:
            msg = "需要安装 pandas 才能使用 DataFrame 输出：uv add pandas"
            raise RuntimeError(msg) from exc
        return pd.DataFrame(self.data, columns=self.fields)


def _parse_fields(fields: Optional[Union[str, Sequence[str]]]) -> List[str]:
    if fields is None:
        return []
    if isinstance(fields, str):
        return [field.strip() for field in fields.split(",") if field.strip()]
    return [field for field in fields if field]
