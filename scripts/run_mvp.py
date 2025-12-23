from __future__ import annotations

from powerdash.config import SimConfig
from powerdash.data.generator import generate_mock_data
from powerdash.engine.sim import run_simulation_hourly
from powerdash.reporting.metrics import daily_dashboard_table


def main() -> None:
    cfg = SimConfig(start_date="2026-01-01", n_days=30, seed=7)

    # Generate a bit more history than you simulate (for fwd anchoring)
    mock = generate_mock_data(
        start_date=cfg.start_date,
        n_days_total=cfg.n_days + cfg.fwd_horizon_days + 5,
        daily_load_mwh=cfg.daily_load_mwh,
        fwd_horizon_days=cfg.fwd_horizon_days,
        forecast_sigma=cfg.forecast_sigma,
        seed=cfg.seed,
    )

    res = run_simulation_hourly(
        cfg=cfg,
        prices_da_hourly=mock.prices_da_hourly,
        load_hourly=mock.load_hourly,
        fwd_curves_daily=mock.fwd_curves_daily,
    )

    dash = daily_dashboard_table(res.daily_pnl)
    print(dash.head(10).to_string(index=False))
    print("\nSummary:")
    print(
        dash[
            [
                "da_cost_eur",
                "imbalance_pnl_eur",
                "hedge_delivery_pnl_eur",
                "hedge_mtm_change_eur",
                "total_economic_pnl_eur",
            ]
        ]
        .sum()
        .to_string()
    )


if __name__ == "__main__":
    main()
