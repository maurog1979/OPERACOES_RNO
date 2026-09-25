"""Datas ISO do MySQL e datas brasileiras sem inversão de dia e mês."""
import pandas as pd


def parse_dates(values):
    text = values.astype("string")
    iso = text.str.match(r"^\d{4}-\d{2}-\d{2}", na=False)
    result = pd.to_datetime(text.where(iso), format="ISO8601", errors="coerce")
    local = pd.to_datetime(text.where(~iso), format="mixed", dayfirst=True, errors="coerce")
    return result.fillna(local)
