import pandas as pd
from core.parser_opu import OPUParser
from core.parser_balance import BalanceParser

def test_opu_parser_basic():
    df = pd.DataFrame({"data": ["Выручка 1000", "Себестоимость 600", "Чистая прибыль 200"]})
    parser = OPUParser()
    result = parser.parse(df)
    assert result["values"]["revenue"] == 1000.0
    assert result["values"]["cogs"] == 600.0
    assert result["values"]["net_profit"] == 200.0

def test_balance_parser_basic():
    df = pd.DataFrame({"data": ["Оборотные активы 500", "Краткосрочные обязательства 250", "Капитал 300"]})
    parser = BalanceParser()
    result = parser.parse(df)
    assert result["values"]["current_assets"] == 500.0
    assert result["values"]["short_term_liabilities"] == 250.0
    assert result["values"]["capital"] == 300.0
