from shunplus import TableResult


def test_table_result_to_dicts_and_select() -> None:
    result = TableResult(
        fields=["symbol", "close", "volume"],
        data=[["SZ301662", 10.4, 1020]],
        next_cursor=123,
    )

    assert result.has_more is True
    assert result.to_dicts() == [{"symbol": "SZ301662", "close": 10.4, "volume": 1020}]

    selected = result.select("close,symbol")

    assert selected.fields == ["close", "symbol"]
    assert selected.data == [[10.4, "SZ301662"]]


def test_table_result_to_dataframe() -> None:
    result = TableResult(fields=["symbol", "close"], data=[["SZ301662", 10.4]])

    dataframe = result.to_dataframe()

    assert list(dataframe.columns) == ["symbol", "close"]
    assert dataframe.iloc[0].to_dict() == {"symbol": "SZ301662", "close": 10.4}
