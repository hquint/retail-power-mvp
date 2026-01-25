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
        "da_only_total_cost_eur",
        "procurement_saving_vs_da_only_eur",
        "benchmark_perfect_da_cost_eur",
        "procurement_saving_vs_perfect_da_eur",
    ]
    return df[cols].sort_values("date")


def risk_summary(dash: pd.DataFrame) -> pd.DataFrame:
    """
    Compare hedged strategy vs DA-only (forecast + imbalance) benchmark.
    """
    df = dash.copy()

    hedged = df["total_procurement_cost_eur"]
    da_only = df["da_only_total_cost_eur"]
    saving = df[
        "procurement_saving_vs_da_only_eur"
    ]  # positive = hedge saves vs DA-only

    out = {
        "n_days": int(len(df)),
        # Hedged distribution
        "hedged_avg_cost_eur": float(hedged.mean()),
        "hedged_std_cost_eur": float(hedged.std(ddof=1)),
        "hedged_p95_cost_eur": float(hedged.quantile(0.95)),
        "hedged_p99_cost_eur": float(hedged.quantile(0.99)),
        "hedged_max_cost_eur": float(hedged.max()),
        # DA-only distribution
        "da_only_avg_cost_eur": float(da_only.mean()),
        "da_only_std_cost_eur": float(da_only.std(ddof=1)),
        "da_only_p95_cost_eur": float(da_only.quantile(0.95)),
        "da_only_p99_cost_eur": float(da_only.quantile(0.99)),
        "da_only_max_cost_eur": float(da_only.max()),
        # Risk reduction (positive = hedge improves)
        "delta_std_eur": float(da_only.std(ddof=1) - hedged.std(ddof=1)),
        "delta_p95_eur": float(da_only.quantile(0.95) - hedged.quantile(0.95)),
        "delta_p99_eur": float(da_only.quantile(0.99) - hedged.quantile(0.99)),
        "delta_max_eur": float(da_only.max() - hedged.max()),
        # Savings distribution (positive = hedge saves)
        "avg_saving_eur": float(saving.mean()),
        "p05_saving_eur": float(saving.quantile(0.05)),
        "min_saving_eur": float(saving.min()),
    }

    return pd.DataFrame([out])
