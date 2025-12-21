from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SimConfig:
    start_date: str = "2026-01-01"     # decision day starts here
    n_days: int = 60                  # how many delivery days to simulate
    fwd_horizon_days: int = 60        # forward curve snapshot horizon
    seed: int = 7

    # Portfolio sizing (MWh/day)
    daily_load_mwh: float = 100.0
    hedge_ratio: float = 0.70         # hedge fraction of expected daily load

    # Forecast error (relative)
    forecast_sigma: float = 0.03      # ~3% hourly-ish error aggregated

    # Imbalance proxy (for now: simple penalty spread vs DA)
    imbalance_spread_eur_per_mwh: float = 50.0  # placeholder, will improve later
