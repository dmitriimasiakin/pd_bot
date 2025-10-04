import os
import pandas as pd
from core.document_loader import DocumentLoader

def test_loader_with_dataframe():
    df = pd.DataFrame({"col1": ["Выручка 1000", "Себестоимость 500"]})
    loader = DocumentLoader()
    result = loader.load(df)
    assert "analysis" in result
    assert any("1000" in str(x) for x in result["analysis"]["amounts"]["all"])
