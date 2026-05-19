"""由 scripts/generate_sdk.py 根据 openapi.json 生成，请勿手工修改。"""
# ruff: noqa: E501

from __future__ import annotations

import json
from typing import Any, List, Optional, Tuple, Union

from ._types import DateLike, ResultFormat

ENDPOINTS = json.loads(
    '{"announcements":{"operation_id":"announcements","http_method":"GET","path":"/api/v1/data/announcements","summary":"查询公司公告","description":"查询指定标的的公司公告，并按商品权益校验条数、频率与历史访问边界。","tags":["news"],"parameters":[{"name":"symbol","required":true,"description":"标的代码，使用行情库代码格式，例如 `SZ301662`、`SH603626`。SDK 可在客户端把 `301662.SZ`、`603626.SH` 转成该格式。","schema":{"type":"string","minLength":1,"title":"Symbol"}},{"name":"start_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Start Time","type":"string","format":"date-time"}},{"name":"end_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"End Time","type":"string","format":"date-time"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"announcement_uid","type":"string","description":"公告唯一 ID。","nullable":false},{"name":"title","type":"string","description":"公告标题。","nullable":false},{"name":"published_at","type":"datetime","description":"公告发布时间。","nullable":false},{"name":"url","type":"string","description":"公告链接。","nullable":true}],"field_variants":{}},"entitlements":{"operation_id":"data_api_entitlements","http_method":"GET","path":"/api/v1/data/entitlements","summary":"查询当前 Token 权益","description":"返回当前 API Token 已开通的商品权益快照，供 SDK 自动配置并发、频率、单页条数和历史访问范围等客户端侧限制。","tags":["entitlements"],"parameters":[],"response_kind":"json","fields":[],"field_variants":{}},"factors":{"operation_id":"market_factors","http_method":"GET","path":"/api/v1/data/market/factors","summary":"查询复权因子","description":"查询指定标的的复权因子；当前只校验条数、频率、并发和额度。","tags":["market"],"parameters":[{"name":"symbol","required":true,"description":"标的代码，使用行情库代码格式，例如 `SZ301662`、`SH603626`。SDK 可在客户端把 `301662.SZ`、`603626.SH` 转成该格式。","schema":{"type":"string","minLength":1,"title":"Symbol"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"trade_date","type":"date","description":"交易日期。","nullable":false,"example":"2026-04-03"},{"name":"factor","type":"number","description":"复权因子。","nullable":false,"example":1.0}],"field_variants":{}},"kline":{"operation_id":"market_kline","http_method":"GET","path":"/api/v1/data/market/kline","summary":"查询 K 线数据","description":"按标的、周期和时间范围查询 K 线数据，并按商品权益校验条数、频率与历史访问边界。","tags":["market"],"parameters":[{"name":"period","required":true,"description":"K 线周期。日 K 统一使用 `day`。","schema":{"type":"string","title":"Period","enum":["1m","5m","15m","30m","60m","120m","day","month","year"]}},{"name":"symbol","required":true,"description":"标的代码，使用行情库代码格式，例如 `SZ301662`、`SH603626`。SDK 可在客户端把 `301662.SZ`、`603626.SH` 转成该格式。","schema":{"type":"string","minLength":1,"title":"Symbol"}},{"name":"start_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Start Time","type":"string","format":"date-time"}},{"name":"end_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"End Time","type":"string","format":"date-time"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"ts","type":"datetime","description":"K 线时间。","nullable":false,"example":"2026-04-03T00:00:00+08:00"},{"name":"open","type":"number","description":"开盘价。","nullable":false,"example":10.2},{"name":"high","type":"number","description":"最高价。","nullable":false,"example":11.0},{"name":"low","type":"number","description":"最低价。","nullable":false,"example":9.8},{"name":"close","type":"number","description":"收盘价。","nullable":false,"example":10.4},{"name":"volume","type":"number","description":"成交量。","nullable":true,"example":1020.0},{"name":"amount","type":"number","description":"成交额。","nullable":true,"example":10240.0},{"name":"turnoverrate","type":"number","description":"换手率。","nullable":true,"example":1.02},{"name":"percent","type":"number","description":"涨跌幅百分比。","nullable":true,"example":2.04}],"field_variants":{}},"news_flashes":{"operation_id":"news_flashes","http_method":"GET","path":"/api/v1/data/news/futu_flashes","summary":"查询富途快讯","description":"查询富途 7x24 快讯，并按商品权益校验条数、频率与历史访问边界。","tags":["news"],"parameters":[{"name":"start_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Start Time","type":"string","format":"date-time"}},{"name":"end_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"End Time","type":"string","format":"date-time"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"flash_id","type":"string","description":"快讯 ID。","nullable":false},{"name":"title","type":"string","description":"标题。","nullable":false},{"name":"content","type":"string","description":"内容。","nullable":true},{"name":"published_at","type":"datetime","description":"发布时间。","nullable":false},{"name":"level","type":"string","description":"重要级别。","nullable":true},{"name":"source_site","type":"string","description":"来源站点。","nullable":false}],"field_variants":{}},"news_headlines":{"operation_id":"news_headlines","http_method":"GET","path":"/api/v1/data/news/futu_headlines","summary":"查询富途要闻","description":"查询富途市场要闻，并按商品权益校验条数、频率与历史访问边界。","tags":["news"],"parameters":[{"name":"start_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Start Time","type":"string","format":"date-time"}},{"name":"end_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"End Time","type":"string","format":"date-time"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"headline_id","type":"string","description":"要闻 ID。","nullable":false},{"name":"source_site","type":"string","description":"来源站点。","nullable":false},{"name":"title","type":"string","description":"标题。","nullable":false},{"name":"description","type":"string","description":"摘要。","nullable":true},{"name":"content_html","type":"string","description":"正文 HTML。","nullable":true},{"name":"content_text","type":"string","description":"正文纯文本。","nullable":true},{"name":"published_at","type":"datetime","description":"发布时间。","nullable":false},{"name":"news_source","type":"string","description":"原始资讯来源。","nullable":true},{"name":"detail_url","type":"string","description":"详情链接。","nullable":true},{"name":"is_external_link","type":"boolean","description":"是否外部链接。","nullable":false},{"name":"is_video","type":"boolean","description":"是否视频内容。","nullable":false}],"field_variants":{}},"social_comments":{"operation_id":"social_comments","http_method":"GET","path":"/api/v1/data/social/comments","summary":"查询社媒评论","description":"按社媒来源查询评论数据，并按查询参数参与商品解析和游标历史边界校验。","tags":["social"],"parameters":[{"name":"source","required":true,"description":"社媒来源，支持 xueqiu、eastmoney。","schema":{"type":"string","description":"社媒来源，支持 xueqiu、eastmoney。","title":"Source","enum":["xueqiu","eastmoney"]}},{"name":"post_id","required":true,"description":"","schema":{"type":"string","minLength":1,"title":"Post Id"}},{"name":"tree","required":false,"description":"","schema":{"anyOf":[{"type":"boolean"},{"type":"null"}],"title":"Tree"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"comment_id","type":"string","description":"评论 ID。","nullable":false},{"name":"parent_comment_id","type":"string","description":"父评论 ID。","nullable":true},{"name":"root_comment_id","type":"string","description":"根评论 ID。","nullable":true},{"name":"comment_level","type":"integer","description":"评论层级。","nullable":true},{"name":"user_id","type":"string","description":"用户 ID。","nullable":true},{"name":"content_html","type":"string","description":"评论 HTML 内容。","nullable":true},{"name":"comment_created_at","type":"datetime","description":"评论发布时间。","nullable":false}],"field_variants":{"eastmoney":[{"name":"comment_id","type":"string","description":"评论 ID。","nullable":false},{"name":"parent_comment_id","type":"string","description":"父评论 ID。","nullable":true},{"name":"comment_level","type":"integer","description":"评论层级。","nullable":true},{"name":"author_name","type":"string","description":"作者名称。","nullable":true},{"name":"content","type":"string","description":"评论内容。","nullable":true},{"name":"like_count","type":"integer","description":"点赞数。","nullable":true},{"name":"published_at","type":"datetime","description":"发布时间。","nullable":false}]}},"social_posts":{"operation_id":"social_posts","http_method":"GET","path":"/api/v1/data/social/posts","summary":"查询社媒帖子","description":"按社媒来源查询帖子数据，并按查询参数参与商品解析和历史访问边界校验。","tags":["social"],"parameters":[{"name":"source","required":true,"description":"社媒来源，支持 xueqiu、eastmoney。","schema":{"type":"string","description":"社媒来源，支持 xueqiu、eastmoney。","title":"Source","enum":["xueqiu","eastmoney"]}},{"name":"symbol","required":true,"description":"标的代码，使用行情库代码格式，例如 `SZ301662`、`SH603626`。SDK 可在客户端把 `301662.SZ`、`603626.SH` 转成该格式。","schema":{"type":"string","minLength":1,"title":"Symbol"}},{"name":"start_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Start Time","type":"string","format":"date-time"}},{"name":"end_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"End Time","type":"string","format":"date-time"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"post_id","type":"string","description":"帖子 ID。","nullable":false},{"name":"title","type":"string","description":"标题。","nullable":true},{"name":"description","type":"string","description":"摘要。","nullable":true},{"name":"text","type":"string","description":"正文文本。","nullable":true},{"name":"user_id","type":"string","description":"用户 ID。","nullable":true},{"name":"published_at","type":"datetime","description":"发布时间。","nullable":false},{"name":"detail_url","type":"string","description":"详情链接。","nullable":true}],"field_variants":{"eastmoney":[{"name":"post_id","type":"string","description":"帖子 ID。","nullable":false},{"name":"guba_code","type":"string","description":"股吧代码。","nullable":false},{"name":"title","type":"string","description":"标题。","nullable":true},{"name":"post_content_text","type":"string","description":"帖子正文文本。","nullable":true},{"name":"author_name","type":"string","description":"作者名称。","nullable":true},{"name":"published_at","type":"datetime","description":"发布时间。","nullable":false},{"name":"view_count","type":"integer","description":"浏览数。","nullable":true},{"name":"reply_count","type":"integer","description":"回复数。","nullable":true},{"name":"post_url","type":"string","description":"帖子链接。","nullable":true}]}},"stock_news":{"operation_id":"stock_news","http_method":"GET","path":"/api/v1/data/news/stock","summary":"查询个股资讯","description":"查询指定标的的个股资讯，并按商品权益校验条数、频率与历史访问边界。","tags":["news"],"parameters":[{"name":"symbol","required":true,"description":"标的代码，使用行情库代码格式，例如 `SZ301662`、`SH603626`。SDK 可在客户端把 `301662.SZ`、`603626.SH` 转成该格式。","schema":{"type":"string","minLength":1,"title":"Symbol"}},{"name":"source","required":true,"description":"资讯来源，支持 xueqiu、futu。","schema":{"type":"string","description":"资讯来源，支持 xueqiu、futu。","title":"Source","enum":["xueqiu","futu"]}},{"name":"start_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Start Time","type":"string","format":"date-time"}},{"name":"end_time","required":false,"description":"ISO 8601 时间；未携带时区时按北京时间 `Asia/Shanghai` 解释。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"End Time","type":"string","format":"date-time"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"news_id","type":"string","description":"资讯 ID。","nullable":false,"example":"xq-news-001"},{"name":"source_site","type":"string","description":"来源站点。","nullable":false,"example":"xueqiu"},{"name":"title","type":"string","description":"标题。","nullable":false},{"name":"description","type":"string","description":"摘要。","nullable":true},{"name":"content_html","type":"string","description":"正文 HTML。","nullable":true},{"name":"content_text","type":"string","description":"正文纯文本。","nullable":true},{"name":"published_at","type":"datetime","description":"发布时间。","nullable":false},{"name":"news_source","type":"string","description":"原始资讯来源。","nullable":true},{"name":"detail_url","type":"string","description":"详情链接。","nullable":true}],"field_variants":{}},"symbols":{"operation_id":"symbols","http_method":"GET","path":"/api/v1/data/symbols","summary":"查询基础标的","description":"查询证券基础标的信息；该接口不按历史时间边界限制，只校验条数、频率、并发和额度。","tags":["market"],"parameters":[{"name":"exchange","required":false,"description":"","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Exchange"}},{"name":"limit","required":false,"description":"单页返回条数。","schema":{"anyOf":[{"type":"integer","minimum":1},{"type":"null"}],"title":"Limit","type":"integer","minimum":1,"maximum":1000,"default":200}},{"name":"cursor","required":false,"description":"分页时间游标，首次请求不传；翻页时传上一页响应的 `next_cursor`。","schema":{"anyOf":[{"type":"integer","minimum":0},{"type":"null"}],"title":"Cursor","type":"integer","minimum":0}},{"name":"cursor_id","required":false,"description":"分页去重游标，首次请求不传；翻页时传上一页响应的 `next_cursor_id`。","schema":{"anyOf":[{"type":"string"},{"type":"null"}],"title":"Cursor Id","type":"string"}}],"response_kind":"table","fields":[{"name":"symbol","type":"string","description":"标的代码，使用行情库代码格式。","nullable":false,"example":"SZ301662"},{"name":"name","type":"string","description":"标的名称。","nullable":false,"example":"平安银行"},{"name":"exchange","type":"string","description":"交易所代码。","nullable":false,"example":"SZ"},{"name":"listed_at","type":"date","description":"上市日期。","nullable":true,"example":"1991-04-03"}],"field_variants":{}}}'
)

ENDPOINT_ALIASES = {
    "data_api_entitlements": "entitlements",
    "market_factors": "factors",
    "market_kline": "kline",
}


class GeneratedDataMethods:
    """由 OpenAPI 生成的数据查询方法。"""

    def announcements(self, *, symbol: str, start_time: Optional[DateLike] = None, end_time: Optional[DateLike] = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询公司公告\n\n查询指定标的的公司公告，并按商品权益校验条数、频率与历史访问边界。"""

        params = {
            "symbol": symbol,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("announcements", fields=fields, format=format, **params)

    def entitlements(self) -> Any:
        """查询当前 Token 权益\n\n返回当前 API Token 已开通的商品权益快照，供 SDK 自动配置并发、频率、单页条数和历史访问范围等客户端侧限制。"""

        params = {
        }
        return self.request_json("entitlements", **params)

    def factors(self, *, symbol: str, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询复权因子\n\n查询指定标的的复权因子；当前只校验条数、频率、并发和额度。"""

        params = {
            "symbol": symbol,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("factors", fields=fields, format=format, **params)

    def kline(self, *, period: str, symbol: str, start_time: Optional[DateLike] = None, end_time: Optional[DateLike] = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询 K 线数据\n\n按标的、周期和时间范围查询 K 线数据，并按商品权益校验条数、频率与历史访问边界。"""

        params = {
            "period": period,
            "symbol": symbol,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("kline", fields=fields, format=format, **params)

    def news_flashes(self, *, start_time: Optional[DateLike] = None, end_time: Optional[DateLike] = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询富途快讯\n\n查询富途 7x24 快讯，并按商品权益校验条数、频率与历史访问边界。"""

        params = {
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("news_flashes", fields=fields, format=format, **params)

    def news_headlines(self, *, start_time: Optional[DateLike] = None, end_time: Optional[DateLike] = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询富途要闻\n\n查询富途市场要闻，并按商品权益校验条数、频率与历史访问边界。"""

        params = {
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("news_headlines", fields=fields, format=format, **params)

    def social_comments(self, *, source: str, post_id: str, tree: Optional[bool] = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询社媒评论\n\n按社媒来源查询评论数据，并按查询参数参与商品解析和游标历史边界校验。"""

        params = {
            "source": source,
            "post_id": post_id,
            "tree": tree,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("social_comments", fields=fields, format=format, **params)

    def social_posts(self, *, source: str, symbol: str, start_time: Optional[DateLike] = None, end_time: Optional[DateLike] = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询社媒帖子\n\n按社媒来源查询帖子数据，并按查询参数参与商品解析和历史访问边界校验。"""

        params = {
            "source": source,
            "symbol": symbol,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("social_posts", fields=fields, format=format, **params)

    def stock_news(self, *, symbol: str, source: str, start_time: Optional[DateLike] = None, end_time: Optional[DateLike] = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询个股资讯\n\n查询指定标的的个股资讯，并按商品权益校验条数、频率与历史访问边界。"""

        params = {
            "symbol": symbol,
            "source": source,
            "start_time": start_time,
            "end_time": end_time,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("stock_news", fields=fields, format=format, **params)

    def symbols(self, *, exchange: Any = None, limit: Optional[int] = None, cursor: Optional[int] = None, cursor_id: Optional[str] = None, fields: Optional[Union[str, List[str], Tuple[str, ...]]] = None, format: Optional[ResultFormat] = None) -> Any:
        """查询基础标的\n\n查询证券基础标的信息；该接口不按历史时间边界限制，只校验条数、频率、并发和额度。"""

        params = {
            "exchange": exchange,
            "limit": limit,
            "cursor": cursor,
            "cursor_id": cursor_id,
        }
        return self.query("symbols", fields=fields, format=format, **params)
