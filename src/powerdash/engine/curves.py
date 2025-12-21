from __future__ import annotations

import pandas as pd

from powerdash.data.schemas import COL_DELIV_DATE, COL_FWD_BASE, COL_VAL_DATE


class DailyBaseForwardCurve:
    """
    Daily baseload forward curve snapshots.
    Extend later with HPFC by adding a method that returns hourly prices.
    """

    def __init__(self, fwd_curves_daily: pd.DataFrame):
        self._df = fwd_curves_daily.copy()
        self._df[COL_VAL_DATE] = pd.to_datetime(self._df[COL_VAL_DATE]).dt.normalize()
        self._df[COL_DELIV_DATE] = pd.to_datetime(self._df[COL_DELIV_DATE]).dt.normalize()
        self._idx = self._df.set_index([COL_VAL_DATE, COL_DELIV_DATE])[COL_FWD_BASE].sort_index()

    def get_fwd_base(self, val_date: pd.Timestamp, delivery_date: pd.Timestamp) -> float:
        val = pd.Timestamp(val_date).normalize()
        d = pd.Timestamp(delivery_date).normalize()
        try:
            return float(self._idx.loc[(val, d)])
        except KeyError as e:
            raise KeyError(f"Missing fwd_base for val_date={val.date()} delivery_date={d.date()}") from e
