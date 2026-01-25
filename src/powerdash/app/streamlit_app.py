from __future__ import annotations

import datetime as dt

import pandas as pd
import plotly.express as px
import streamlit as st

from powerdash.config import SimConfig
from powerdash.data.generator import generate_mock_data
from powerdash.engine.sim import run_simulation_hourly
from powerdash.reporting.metrics import (
    daily_dashboard_table,
    risk_summary_table,
    summary_row,
)


@st.cache_data(show_spinner=False)
def _run_simulation(cfg: SimConfig) -> dict[str, pd.DataFrame]:
    mock = generate_mock_data(
        start_date=cfg.start_date,
        n_days_total=cfg.n_days + cfg.fwd_horizon_days + 5,
        daily_load_mwh=cfg.daily_load_mwh,
        fwd_horizon_days=cfg.fwd_horizon_days,
        forecast_sigma=cfg.forecast_sigma,
        seed=cfg.seed,
        scarcity_day_prob=cfg.scarcity_day_prob,
        scarcity_peak_multiplier=cfg.scarcity_peak_multiplier,
    )
    res = run_simulation_hourly(
        cfg=cfg,
        prices_da_hourly=mock.prices_da_hourly,
        load_hourly=mock.load_hourly,
        fwd_curves_daily=mock.fwd_curves_daily,
    )
    dash = daily_dashboard_table(res.daily_pnl)
    return {
        "dash": dash,
        "summary": summary_row(dash),
        "risk": risk_summary_table(dash),
    }


def _sidebar_config() -> SimConfig:
    cfg = SimConfig()
    st.sidebar.header("Simulation")
    start_date = st.sidebar.date_input(
        "start_date", value=dt.date.fromisoformat(cfg.start_date)
    )
    n_days = st.sidebar.slider("n_days", min_value=14, max_value=365, value=cfg.n_days)
    seed = st.sidebar.number_input("seed", value=cfg.seed, step=1)
    daily_load_mwh = st.sidebar.number_input(
        "daily_load_mwh", value=cfg.daily_load_mwh, step=1.0
    )

    st.sidebar.header("Hedge")
    fwd_horizon_days = st.sidebar.slider(
        "hedge_horizon_days", min_value=7, max_value=180, value=cfg.fwd_horizon_days
    )
    hedge_ratio_short = st.sidebar.slider(
        "hedge_fraction_short",
        min_value=0.0,
        max_value=1.0,
        value=cfg.hedge_ratio_short,
    )
    hedge_ratio_long = st.sidebar.slider(
        "hedge_fraction_long", min_value=0.0, max_value=1.0, value=cfg.hedge_ratio_long
    )

    st.sidebar.header("Scarcity / imbalance")
    scarcity_day_prob = st.sidebar.slider(
        "scarcity_day_prob",
        min_value=0.0,
        max_value=0.2,
        value=cfg.scarcity_day_prob,
    )
    scarcity_peak_multiplier = st.sidebar.slider(
        "scarcity_peak_multiplier",
        min_value=1.0,
        max_value=10.0,
        value=cfg.scarcity_peak_multiplier,
    )
    imbalance_spread_base = st.sidebar.slider(
        "imbalance_spread_base_eur_per_mwh",
        min_value=0.0,
        max_value=30.0,
        value=cfg.imbalance_spread_base_eur_per_mwh,
    )
    imbalance_spread_scarcity_add = st.sidebar.slider(
        "imbalance_spread_scarcity_add_eur_per_mwh",
        min_value=0.0,
        max_value=200.0,
        value=cfg.imbalance_spread_scarcity_add_eur_per_mwh,
    )
    imbalance_sell_discount_factor = st.sidebar.slider(
        "imbalance_sell_discount_factor",
        min_value=0.0,
        max_value=1.0,
        value=cfg.imbalance_sell_discount_factor,
    )

    st.sidebar.header("Schedule error")
    schedule_error_sigma_base = st.sidebar.slider(
        "schedule_error_sigma_base",
        min_value=0.0,
        max_value=0.05,
        value=cfg.schedule_error_sigma_base,
        step=0.001,
    )
    schedule_error_residual_sensitivity = st.sidebar.slider(
        "schedule_error_residual_sensitivity",
        min_value=0.0,
        max_value=5.0,
        value=cfg.schedule_error_residual_sensitivity,
        step=0.1,
    )
    schedule_error_scarcity_mult = st.sidebar.slider(
        "schedule_error_scarcity_mult",
        min_value=0.0,
        max_value=20.0,
        value=cfg.schedule_error_scarcity_mult,
        step=0.5,
    )
    da_only_schedule_error_mult = st.sidebar.slider(
        "da_only_schedule_error_mult",
        min_value=1.0,
        max_value=3.0,
        value=cfg.da_only_schedule_error_mult,
        step=0.1,
    )

    return SimConfig(
        start_date=start_date.isoformat(),
        n_days=int(n_days),
        fwd_horizon_days=int(fwd_horizon_days),
        seed=int(seed),
        daily_load_mwh=float(daily_load_mwh),
        hedge_ratio_short=float(hedge_ratio_short),
        hedge_ratio_long=float(hedge_ratio_long),
        scarcity_day_prob=float(scarcity_day_prob),
        scarcity_peak_multiplier=float(scarcity_peak_multiplier),
        imbalance_spread_base_eur_per_mwh=float(imbalance_spread_base),
        imbalance_spread_scarcity_add_eur_per_mwh=float(imbalance_spread_scarcity_add),
        imbalance_sell_discount_factor=float(imbalance_sell_discount_factor),
        schedule_error_sigma_base=float(schedule_error_sigma_base),
        schedule_error_residual_sensitivity=float(schedule_error_residual_sensitivity),
        schedule_error_scarcity_mult=float(schedule_error_scarcity_mult),
        da_only_schedule_error_mult=float(da_only_schedule_error_mult),
    )


def main() -> None:
    st.set_page_config(page_title="PowerDash MVP", layout="wide")
    st.title("PowerDash MVP")

    cfg = _sidebar_config()
    run = st.sidebar.button("Run simulation")

    if not run and "last_result" not in st.session_state:
        st.info("Set parameters and click Run simulation.")
        return

    if run:
        st.session_state["last_result"] = _run_simulation(cfg)

    result = st.session_state["last_result"]
    dash = result["dash"]
    summary = result["summary"]
    risk = result["risk"]

    st.subheader("Daily dashboard")
    st.dataframe(dash, width="stretch")
    st.subheader("Summary")
    st.dataframe(summary, width="stretch")

    st.subheader("Risk summary")
    st.dataframe(risk, width="stretch")

    csv = dash.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download daily table (CSV)",
        data=csv,
        file_name="daily_dashboard.csv",
        mime="text/csv",
    )

    st.subheader("Costs over time")
    fig_costs = px.line(
        dash,
        x="date",
        y=["total_procurement_cost_eur", "da_only_total_cost_eur"],
        labels={"value": "cost_eur", "variable": "series"},
    )
    st.plotly_chart(fig_costs, width="stretch")

    st.subheader("Savings vs DA-only")
    fig_savings = px.bar(
        dash,
        x="date",
        y="procurement_saving_vs_da_only_eur",
        labels={"procurement_saving_vs_da_only_eur": "saving_eur"},
    )
    st.plotly_chart(fig_savings, width="stretch")

    st.subheader("Cost distribution")
    dist = dash.melt(
        id_vars=["date"],
        value_vars=["total_procurement_cost_eur", "da_only_total_cost_eur"],
        var_name="series",
        value_name="cost_eur",
    )
    fig_dist = px.histogram(dist, x="cost_eur", color="series", barmode="overlay")
    st.plotly_chart(fig_dist, width="stretch")

    if {"hedged_variable_cost_eur", "da_only_variable_cost_eur"}.issubset(dash.columns):
        st.subheader("Variable cost distribution")
        var_dist = dash.melt(
            id_vars=["date"],
            value_vars=["hedged_variable_cost_eur", "da_only_variable_cost_eur"],
            var_name="series",
            value_name="cost_eur",
        )
        fig_var = px.histogram(
            var_dist, x="cost_eur", color="series", barmode="overlay"
        )
        st.plotly_chart(fig_var, width="stretch")


if __name__ == "__main__":
    main()
