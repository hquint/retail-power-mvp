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
        "spot_base_price",
        "hedge_fixed_cost_eur",
        "da_cost_eur",
        "imbalance_cost_eur",
        "hedge_delivery_pnl_eur",
        "hedge_mtm_change_eur",
        "total_procurement_cost_eur",
        "benchmark_cost_eur",
        "procurement_saving_vs_benchmark_eur",
    ]
    return df[cols].sort_values("date")
