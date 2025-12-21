from __future__ import annotations

import pandas as pd


def fixed_ratio_daily_hedge_mwh(expected_daily_load_mwh: float, hedge_ratio: float) -> float:
    return float(expected_daily_load_mwh * hedge_ratio)


def hedge_price_from_curve(curve, val_date: pd.Timestamp, delivery_date: pd.Timestamp) -> float:
    """
    For MVP: hedge 'price' equals the daily baseload forward at time of hedge placement.
    Later: you will store executed hedge trades; here we keep it simple and deterministic.
    """
    return float(curve.get_fwd_base(val_date=val_date, delivery_date=delivery_date))
