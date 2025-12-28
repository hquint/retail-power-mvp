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

def risk_summary(dash: pd.DataFrame) -> pd.DataFrame:
    """
    Simple risk KPIs over the simulated period for total procurement cost and savings.
    """
    df = dash.copy()

    cost = df["total_procurement_cost_eur"]
    saving = df["procurement_saving_vs_benchmark_eur"]

    out = {
        "n_days": int(len(df)),
        "avg_cost_eur": float(cost.mean()),
        "std_cost_eur": float(cost.std(ddof=1)),
        "p95_cost_eur": float(cost.quantile(0.95)),
        "p99_cost_eur": float(cost.quantile(0.99)),
        "max_cost_eur": float(cost.max()),
        "min_saving_eur": float(saving.min()),  # worst day vs benchmark
        "p05_saving_eur": float(saving.quantile(0.05)),
        "avg_saving_eur": float(saving.mean()),
    }
    return pd.DataFrame([out])
