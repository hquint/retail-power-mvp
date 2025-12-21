from __future__ import annotations

import pandas as pd


def daily_dashboard_table(daily_pnl: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare a clean table for the dashboard.
    """
    df = daily_pnl.copy()
    df["date"] = pd.to_datetime(df["delivery_date"]).dt.date
    cols = [
        "date",
        "exp_load_mwh",
        "act_load_mwh",
        "hedged_mwh",
        "hedge_fixed_price",
        "spot_base_price",
        "da_cost_eur",
        "imbalance_pnl_eur",
        "hedge_delivery_pnl_eur",
        "hedge_mtm_change_eur",
        "total_economic_pnl_eur",
    ]
    return df[cols].sort_values("date")
