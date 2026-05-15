# ShunPlus SDK (顺盈数据接口 SDK)

本 SDK 专为接入**顺盈**（深圳势界数据科技有限公司旗下平台）的数据接口而设计，旨在帮助开发者更便捷地实现数据的访问与项目集成。它既支持兼容常见量化脚本参数的快捷调用方式，也支持更清晰的结构化结果和 DataFrame 输出，适合脚本分析、研究任务、服务端抓取和批量数据处理。

了解更多详情或获取 API Token，欢迎访问顺盈官方开放平台：[https://api.shunplus.com](https://api.shunplus.com)

## SDK 特色

- 上手简单：`set_token()` 配一次 Token，后续直接 `shun_api()` 或 `Client()`
- 两种使用方式：既能使用兼容常见量化脚本参数的快捷接口，也能直接使用更通用的行情、资讯、社媒、公告接口
- DataFrame 开箱即用：安装 SDK 时会自动安装 `pandas`
- 依赖自动兼容：会按 Python 版本自动选择兼容的 `pandas` 版本，不需要手动处理
- 输入更省心：自动识别常见股票代码格式和时间格式
- 自动识别 Token 能力：会自动按当前 Token 权益调整单次条数、请求节奏和并发
- K 线更好用：只传 `period + symbol + limit` 也能查，SDK 会自动补齐合适时间范围
- 兼容性好：最低支持 Python 3.8，并保持良好兼容性
- 网络处理更省事：自动处理 gzip 压缩响应，并对少量临时失败做克制重试

## 安装

```bash
pip install shunplus
```

如果你使用 `uv`：

```bash
uv add shunplus
```

安装完成后，SDK 会直接带上 DataFrame 能力，不需要额外安装 `pandas`。

## 快速开始

```python
from shunplus import set_token, shun_api

set_token("你的 API Token")

api = shun_api()
df = api.daily(
    ts_code="301662.SZ",
    start_date="20260501",
    end_date="20260510",
    fields=["ts", "open", "high", "low", "close"],
)

print(df.head())
```

如果你更喜欢结构化结果：

```python
from shunplus import Client

client = Client()
result = client.symbols(exchange="SZ", limit=5)

print(result.fields)
print(result.to_dicts())
```

## Token 配置

推荐第一次运行时先保存 Token，后续 `Client()` 和 `shun_api()` 会自动读取。

```python
from shunplus import set_token

set_token("你的 API Token")
```

也可以使用环境变量：

```bash
export SHUNPLUS_API_TOKEN="你的 API Token"
```

如果需要更新或清除 Token：

```python
from shunplus import clear_token, set_token

set_token("新的 API Token")
clear_token()
```

如果你已经创建了客户端对象，也可以直接更新当前客户端：

```python
from shunplus import Client

client = Client()
client.set_token("新的 API Token")
client.reload_token()
```

## 选择使用方式

### 1. `shun_api()`: 默认返回 DataFrame

适合分析脚本、Notebook、和已经习惯 pandas 的场景。

```python
from shunplus import shun_api

api = shun_api()
df = api.kline(period="day", symbol="SZ301662", limit=20)
print(df.head())
```

### 2. `Client()`: 默认返回结构化结果

适合服务端、批处理、翻页抓取和希望保留分页信息的场景。

```python
from shunplus import Client

client = Client()
result = client.kline(period="day", symbol="SZ301662", limit=20)

print(result.fields)
print(result.data)
print(result.to_dicts())
print(result.has_more)
```

### 3. `client.df`: 随时切到 DataFrame 输出

```python
from shunplus import Client

client = Client()
df = client.df.symbols(exchange="HK", limit=20)
print(df.head())
```

## 返回格式

表格类接口都支持 `format` 参数：

- `table`：返回 `TableResult`
- `dict`：返回字典列表
- `dataframe`：返回 pandas DataFrame

```python
from shunplus import Client

client = Client()

table = client.symbols(exchange="SZ", format="table")
rows = client.symbols(exchange="SZ", format="dict")
df = client.symbols(exchange="SZ", format="dataframe")
```

如果你只是做数据分析，推荐 `shun_api()` 或 `client.df`。
如果你要写服务、做翻页抓取或保留分页游标，推荐 `Client()`。

## 输入格式与自动处理

### 股票代码

SDK 会自动识别并规范这些常见写法：

- `SZ301662` -> `SZ301662`
- `301662.SZ` -> `SZ301662`
- `603626.SH` -> `SH603626`
- `920693.BJ` -> `BJ920693`
- `HK06999` -> `HK06999`
- `06999.HK` -> `HK06999`

不建议传纯数字代码，例如 `301662` 或 `06999`，SDK 不会替你猜市场。

### 时间参数

常见时间写法都可以直接使用：

- `20260510`
- `2026-05-10`
- `2026-05-10 09:30:00`
- `datetime.date`
- 无时区的 `datetime.datetime`

例如：

```python
client.kline(
    period="1m",
    symbol="301662.SZ",
    start_time="2026-05-10 09:30:00",
    end_time="2026-05-10 15:00:00",
)
```

### 字段筛选

大部分表格接口都支持 `fields`，只返回你关心的列：

```python
df = api.daily(
    ts_code="301662.SZ",
    start_date="20260501",
    end_date="20260510",
    fields=["ts", "close", "volume"],
)
```

## 方法说明与示例

### 行情数据

#### `daily`

兼容型日线接口。查单日可以用 `trade_date`，查区间用 `start_date` 和 `end_date`。

```python
from shunplus import shun_api

api = shun_api()
df = api.daily(
    ts_code="301662.SZ",
    start_date="20260501",
    end_date="20260510",
    fields=["ts", "open", "high", "low", "close"],
)
```

如果只查某一天：

```python
df = api.daily(
    ts_code="301662.SZ",
    trade_date="20260510",
    fields=["ts", "close"],
)
```

说明：

- `daily()` 更适合对接既有的 `ts_code / trade_date / start_date / end_date` 脚本参数
- 返回字段仍以 Shunplus 接口定义为准，时间列通常是 `ts`

#### `stk_mins`

兼容型分钟线接口。`freq` 支持 `1min`、`5min`、`15min`、`30min`、`60min`、`120min`。

```python
df = api.stk_mins(
    ts_code="301662.SZ",
    freq="5min",
    start_date="2026-05-10 09:30:00",
    end_date="2026-05-10 15:00:00",
    fields=["ts", "open", "close", "volume"],
)
```

#### `kline`

更通用的 K 线接口，适合新项目直接使用。`period` 支持：

- `1m`
- `5m`
- `15m`
- `30m`
- `60m`
- `120m`
- `day`
- `month`
- `year`

```python
from shunplus import Client

client = Client()
rows = client.kline(
    period="day",
    symbol="301662.SZ",
    limit=20,
    format="dict",
)

print(rows[:2])
```

如果你只想查最近一段数据，很多时候只传 `period + symbol + limit` 就够了，SDK 会自动补时间范围。

#### `kline_adjusted`

查询自动复权后的 K 线。`adj` 支持：

- `qfq`：前复权
- `hfq`：后复权

```python
rows = client.kline_adjusted(
    period="day",
    symbol="301662.SZ",
    start_time="2026-05-01",
    end_time="2026-05-10",
    adj="qfq",
    include_factor=True,
    format="dict",
)
```

#### `daily_with_factors`

在日线结果上自动补充常用因子和衍生字段，适合日线分析直接使用。

默认可补的字段包括：

- `adj_factor`
- `pre_close`
- `change`
- `pct_chg`

```python
rows = client.daily_with_factors(
    ts_code="301662.SZ",
    start_date="20260501",
    end_date="20260510",
    fields=["ts", "close", "adj_factor", "pre_close", "change", "pct_chg"],
    format="dict",
)
```

如果你只想补少量字段，也可以写：

```python
rows = client.daily_with_factors(
    ts_code="301662.SZ",
    factors=["pct_chg"],
    fields=["ts", "close", "pct_chg"],
    format="dict",
)
```

#### `symbols`

查询基础标的信息。

```python
rows = client.symbols(
    exchange="SZ",
    limit=10,
    format="dict",
)
```

常见 `exchange` 可以传 `SZ`、`SH`、`BJ`、`HK`。

#### `factors`

查询复权因子。

```python
rows = client.factors(
    symbol="301662.SZ",
    limit=20,
    format="dict",
)
```

### 资讯与公告

#### `stock_news`

查询个股资讯。`source` 支持 `xueqiu` 和 `futu`。

```python
rows = client.stock_news(
    symbol="06999.HK",
    source="xueqiu",
    start_time="2026-05-01",
    end_time="2026-05-10",
    limit=20,
    format="dict",
)
```

#### `news_flashes`

查询富途快讯。

```python
rows = client.news_flashes(
    start_time="2026-05-10 00:00:00",
    limit=50,
    format="dict",
)
```

#### `news_headlines`

查询富途要闻。

```python
rows = client.news_headlines(
    start_time="2026-05-10",
    limit=20,
    format="dict",
)
```

#### `announcements`

查询公司公告。

```python
rows = client.announcements(
    symbol="601318.SH",
    start_time="2026-05-01",
    end_time="2026-05-10",
    limit=20,
    format="dict",
)
```

### 社媒数据

#### `social_posts`

查询社媒帖子。`source` 支持 `xueqiu` 和 `eastmoney`。

```python
rows = client.social_posts(
    source="xueqiu",
    symbol="301662.SZ",
    start_time="2026-05-01",
    end_time="2026-05-10",
    limit=20,
    format="dict",
)
```

#### `social_comments`

查询帖子评论。`post_id` 需要传你已经拿到的帖子 ID。

```python
rows = client.social_comments(
    source="xueqiu",
    post_id="帖子ID",
    tree=True,
    limit=50,
    format="dict",
)
```

### 查看当前 Token 权益

一般情况下不需要你自己处理权益，SDK 会自动识别并应用。  
如果你想主动查看当前 Token 的能力，可以调用：

```python
entitlements = client.entitlements()

print(entitlements.key_id)
for item in entitlements.entitlements:
    print(item.endpoint_key, item.max_rows_per_request)
```

## 分页

大多数列表型接口都支持 `limit`，并通过 `next_cursor` 和 `next_cursor_id` 翻页。  
通常不需要你手动处理游标，直接用下面两个方法即可。

### `iter_pages()`

适合大数据量边拉边处理。

```python
for page in client.iter_pages(
    "stock_news",
    symbol="06999.HK",
    source="xueqiu",
    limit=100,
    show_progress=True,
):
    for row in page.iter_dicts():
        print(row["title"])
```

### `fetch_all()`

适合结果量不大、希望一次性拿全的时候使用。

```python
rows = client.fetch_all(
    "symbols",
    exchange="SZ",
    format="dict",
    show_progress=True,
)

print(len(rows))
```

如果你希望每一页到达时自己处理，也可以用 `on_page`：

```python
def handle_page(page_no, page):
    print("page", page_no, "rows", len(page.data))


result = client.fetch_all(
    "symbols",
    exchange="SZ",
    on_page=handle_page,
)
```

建议：

- 数据量大时优先用 `iter_pages()`
- 结果本身就不大时用 `fetch_all()` 更方便

## 异常处理

```python
from shunplus import AuthenticationError, RateLimitError, ShunplusError

client = Client()

try:
    rows = client.kline(
        period="day",
        symbol="SZ301662",
        limit=20,
        format="dict",
    )
except AuthenticationError:
    print("Token 缺失、写错或已过期")
except RateLimitError as exc:
    print("请求过快，请稍后再试")
    print("建议等待秒数：", exc.retry_after)
except ShunplusError as exc:
    print("请求失败：", exc)
```

## 推荐用法

- 做 pandas 分析、Notebook、研究脚本：优先用 `shun_api()`
- 写服务、批处理、翻页采集：优先用 `Client()` 或 `format="dict"`
- 只查最近 K 线：先试 `period + symbol + limit`
- 需要精确时间窗口：显式传 `start_time` 和 `end_time`
- 需要控制返回列：加上 `fields`
- 数据量大：优先 `iter_pages()`

## 方法一览

| 方法 | 用途 |
| --- | --- |
| `daily` | 兼容型日线查询 |
| `stk_mins` | 兼容型分钟线查询 |
| `kline` | 通用 K 线查询 |
| `kline_adjusted` | 前复权 / 后复权 K 线 |
| `daily_with_factors` | 日线增强结果，自动补因子和常用指标 |
| `symbols` | 基础标的信息 |
| `factors` | 复权因子 |
| `stock_news` | 个股资讯 |
| `news_flashes` | 富途快讯 |
| `news_headlines` | 富途要闻 |
| `social_posts` | 社媒帖子 |
| `social_comments` | 社媒评论 |
| `announcements` | 公司公告 |
| `entitlements` | 查看当前 Token 权益 |
