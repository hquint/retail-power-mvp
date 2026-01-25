from __future__ import annotations
import pandas as pd


def to_date(x: str | pd.Timestamp) -> pd.Timestamp:
    ts = pd.Timestamp(x)
    return pd.Timestamp(ts.date())


def hourly_index(start_date: str, n_days: int) -> pd.DatetimeIndex:
    start = pd.Timestamp(start_date)
    end = start + pd.Timedelta(days=n_days)
    return pd.date_range(start=start, end=end, freq="h", inclusive="left")


def daily_index(start_date: str, n_days: int) -> pd.DatetimeIndex:
    start = pd.Timestamp(start_date).normalize()
    end = start + pd.Timedelta(days=n_days)
    return pd.date_range(start=start, end=end, freq="d", inclusive="left")
