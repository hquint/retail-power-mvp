from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SimConfig:
    start_date: str = "2026-01-01"  # decision day starts here
    n_days: int = 60  # how many delivery days to simulate
    fwd_horizon_days: int = 60  # forward curve snapshot horizon
    seed: int = 7

    # Portfolio sizing (MWh/day)
    daily_load_mwh: float = 100.0
    hedge_ratio: float = 0.70  # hedge fraction of expected daily load

    # Forecast error (relative)
    forecast_sigma: float = 0.03  # ~3% hourly-ish error aggregated

    # Imbalance proxy (state-dependent reBAP-style spread vs DA)
    imbalance_spread_base_eur_per_mwh: float = 6.0  # base spread always applied
    imbalance_spread_scarcity_add_eur_per_mwh: float = (
        45.0  # scarcity add applies only in scarcity peak hours
    )
    imbalance_sell_discount_factor: float = (
        0.35  # sell widens less than buy via discount factor
    )

    # Scarcity regime (mock realism)
    scarcity_day_prob: float = 0.06  # ~6% of days are scarcity days in winter
    scarcity_peak_multiplier: float = 6.0  # multiplies the evening peak premium
    forecast_sigma_scarcity_mult: float = (
        2.5  # forecast sigma increases on scarcity days (more in peak hours)
    )
