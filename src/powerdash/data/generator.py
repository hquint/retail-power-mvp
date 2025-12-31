from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from powerdash.data.schemas import (
    COL_DATE,
    COL_DELIV_DATE,
    COL_DT,
    COL_FWD_BASE,
    COL_LOAD_ACT,
    COL_LOAD_FCST,
    COL_PRICE_DA,
    COL_VAL_DATE,
)
from powerdash.utils.dates import daily_index


@dataclass(frozen=True)
class MockMarketData:
    prices_da_hourly: pd.DataFrame
    load_hourly: pd.DataFrame
    fwd_curves_daily: pd.DataFrame  # snapshots: val_date x delivery_date
    calendar_daily: pd.DataFrame


def _slp_shape_24h() -> np.ndarray:
    """
    Simple SLP-like hourly weights (sum to 1).
    Night lower, evening higher. Keep deterministic.
    """
    w = np.array(
        [
            0.030,
            0.028,
            0.027,
            0.027,
            0.028,
            0.032,  # 00-05
            0.040,
            0.043,
            0.045,
            0.044,
            0.042,
            0.040,  # 06-11
            0.038,
            0.037,
            0.038,
            0.041,
            0.048,
            0.055,  # 12-17
            0.060,
            0.060,
            0.055,
            0.048,
            0.040,
            0.034,  # 18-23
        ],
        dtype=float,
    )
    return w / w.sum()


def generate_mock_data(
    start_date: str,
    n_days_total: int,
    daily_load_mwh: float,
    fwd_horizon_days: int,
    forecast_sigma: float,
    seed: int = 7,
    scarcity_day_prob: float = 0.06,
    scarcity_peak_multiplier: float = 6.0,
) -> MockMarketData:
    """
    Generates:
    - Hourly DA spot prices
    - Hourly actual load + forecast load
    - Daily forward curve snapshots (daily baseload), horizon fwd_horizon_days
    """
    rng = np.random.default_rng(seed)

    # Calendar
    d_idx = daily_index(start_date, n_days_total)
    cal = pd.DataFrame({COL_DATE: d_idx})
    cal["dow"] = cal[COL_DATE].dt.dayofweek
    cal["is_weekend"] = cal["dow"].isin([5, 6]).astype(int)

    # Temperature driver (simple seasonal + noise)
    t = np.arange(len(d_idx))
    temp = 5 + 8 * np.sin(2 * np.pi * t / 365.0) + rng.normal(0, 2.0, size=len(d_idx))
    cal["temp_c"] = temp

    # Winter proxy: cold days are more likely to see scarcity (tight system)
    cal["is_winter_like"] = (cal["temp_c"] <= 3.0).astype(int)

    # Scarcity day draw (only on winter-like days)
    scarcity_draw = rng.random(len(cal))
    cal["is_scarcity_day"] = (
        (cal["is_winter_like"] == 1) & (scarcity_draw < scarcity_day_prob)
    ).astype(int)

    # Daily load level (higher when colder), plus weekend reduction
    base_daily = daily_load_mwh * (
        1.0 + 0.015 * (10 - cal["temp_c"]).clip(-10, 20) / 10.0
    )
    base_daily *= 1.0 - 0.05 * cal["is_weekend"]
    cal["load_mwh_daily_true"] = base_daily

    # Hourly load actual from SLP weights + noise
    shape = _slp_shape_24h()

    load_rows = []
    for d in d_idx:
        day_total = float(cal.loc[cal[COL_DATE] == d, "load_mwh_daily_true"].iloc[0])
        hours = pd.date_range(d, d + pd.Timedelta(days=1), freq="h", inclusive="left")
        is_scarcity_day = int(cal.loc[cal[COL_DATE] == d, "is_scarcity_day"].iloc[0])
        # multiplicative noise (small)
        noise = rng.normal(0, 0.01, size=24)
        hourly = day_total * shape * (1.0 + noise)
        hourly = np.maximum(hourly, 0.0)
        # renormalize to keep daily totals close
        hourly *= day_total / hourly.sum()
        for dt, mwh in zip(hours, hourly):
            is_peak_hour = int(17 <= dt.hour <= 20)
            load_rows.append((dt, mwh, is_scarcity_day, is_peak_hour))

    load = pd.DataFrame(
        load_rows, columns=[COL_DT, COL_LOAD_ACT, "is_scarcity_day", "is_peak_hour"]
    )

    # Forecast = actual + error (forecast error independent-ish)
    eps = rng.normal(0, forecast_sigma, size=len(load))
    load[COL_LOAD_FCST] = np.maximum(load[COL_LOAD_ACT] * (1.0 + eps), 0.0)

    # DA prices: correlated with load level and temp (tight system when cold + high load)
    # Daily baseload price baseline:
    daily_price = (
        60
        + 0.35 * (10 - cal["temp_c"])
        + 0.15 * (cal["load_mwh_daily_true"] - daily_load_mwh)
    )
    daily_price += rng.normal(0, 5.0, size=len(cal))
    cal["price_base_daily"] = np.maximum(daily_price, -20.0)

    # Hourly DA price shape: evening higher, night lower
    price_rows = []
    for d in d_idx:
        p_base = float(cal.loc[cal[COL_DATE] == d, "price_base_daily"].iloc[0])
        hours = pd.date_range(d, d + pd.Timedelta(days=1), freq="h", inclusive="left")
        hour = np.arange(24)

        # smooth diurnal premium: evening peak bump
        premium = 8 * np.exp(-0.5 * ((hour - 19) / 3.0) ** 2) - 4 * np.exp(
            -0.5 * ((hour - 3) / 3.0) ** 2
        )

        # Scarcity: amplify evening peak premium on scarcity days (creates rare but severe spikes)
        is_scarcity = int(cal.loc[cal[COL_DATE] == d, "is_scarcity_day"].iloc[0])
        if is_scarcity == 1:
            premium = premium.copy()
            # amplify only positive part (evening peak), keep night discount similar
            premium = np.where(premium > 0, premium * scarcity_peak_multiplier, premium)

        p_hour = p_base + premium + rng.normal(0, 2.0, size=24)

        for dt, p in zip(hours, p_hour):
            is_peak_hour = int(17 <= dt.hour <= 20)
            price_rows.append((dt, float(p), is_scarcity, is_peak_hour))

    prices = pd.DataFrame(
        price_rows, columns=[COL_DT, COL_PRICE_DA, "is_scarcity_day", "is_peak_hour"]
    )

    # Forward curve snapshots (daily baseload):
    # For each val_date, create fwd price for delivery_date = val_date+1..val_date+H
    # Anchored to expected future daily baseload price + risk premium + noise.
    fwd_rows = []
    cal_map = cal.set_index(COL_DATE)["price_base_daily"].to_dict()

    for val_date in d_idx:
        for k in range(1, fwd_horizon_days + 1):
            deliv = val_date + pd.Timedelta(days=k)
            # if delivery beyond our generated horizon, extrapolate using last known base
            anchor = cal_map.get(deliv, cal_map[d_idx[-1]])
            risk_prem = 2.0 + 0.5 * np.log1p(k)  # longer tenor slightly higher
            fwd = anchor + risk_prem + rng.normal(0, 1.5)
            fwd_rows.append((val_date, deliv, float(fwd)))

    fwd = pd.DataFrame(fwd_rows, columns=[COL_VAL_DATE, COL_DELIV_DATE, COL_FWD_BASE])

    return MockMarketData(
        prices_da_hourly=prices,
        load_hourly=load,
        fwd_curves_daily=fwd,
        calendar_daily=cal,
    )
