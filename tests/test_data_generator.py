from __future__ import annotations

import numpy as np
import pandas as pd

from powerdash.data.generator import generate_mock_data
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


def test_generate_mock_data_shapes_and_columns() -> None:
    start_date = "2026-01-01"
    n_days_total = 10
    fwd_horizon_days = 5

    mock = generate_mock_data(
        start_date=start_date,
        n_days_total=n_days_total,
        daily_load_mwh=100.0,
        fwd_horizon_days=fwd_horizon_days,
        forecast_sigma=0.03,
        seed=7,
        scarcity_day_prob=0.06,
        scarcity_peak_multiplier=6.0,
    )

    assert list(mock.prices_da_hourly.columns) == [
        COL_DT,
        COL_PRICE_DA,
        "is_scarcity_day",
        "is_peak_hour",
    ]
    assert list(mock.load_hourly.columns) == [
        COL_DT,
        COL_LOAD_ACT,
        "is_scarcity_day",
        "is_peak_hour",
        COL_LOAD_FCST,
    ]
    assert list(mock.fwd_curves_daily.columns) == [
        COL_VAL_DATE,
        COL_DELIV_DATE,
        COL_FWD_BASE,
    ]
    assert list(mock.calendar_daily.columns)[0] == COL_DATE

    assert len(mock.prices_da_hourly) == n_days_total * 24
    assert len(mock.load_hourly) == n_days_total * 24
    assert len(mock.calendar_daily) == n_days_total
    assert len(mock.fwd_curves_daily) == n_days_total * fwd_horizon_days


def test_generate_mock_data_date_ranges_and_totals() -> None:
    start_date = "2026-01-01"
    n_days_total = 8
    fwd_horizon_days = 4

    mock = generate_mock_data(
        start_date=start_date,
        n_days_total=n_days_total,
        daily_load_mwh=100.0,
        fwd_horizon_days=fwd_horizon_days,
        forecast_sigma=0.02,
        seed=3,
        scarcity_day_prob=0.05,
        scarcity_peak_multiplier=5.0,
    )

    start = pd.Timestamp(start_date).normalize()
    end = start + pd.Timedelta(days=n_days_total - 1)

    cal = mock.calendar_daily.copy()
    cal[COL_DATE] = pd.to_datetime(cal[COL_DATE]).dt.normalize()

    assert cal[COL_DATE].min() == start
    assert cal[COL_DATE].max() == end

    fwd = mock.fwd_curves_daily.copy()
    fwd[COL_VAL_DATE] = pd.to_datetime(fwd[COL_VAL_DATE]).dt.normalize()
    fwd[COL_DELIV_DATE] = pd.to_datetime(fwd[COL_DELIV_DATE]).dt.normalize()

    assert fwd[COL_VAL_DATE].min() == start
    assert fwd[COL_VAL_DATE].max() == end
    assert fwd[COL_DELIV_DATE].min() == start + pd.Timedelta(days=1)
    assert fwd[COL_DELIV_DATE].max() == end + pd.Timedelta(days=fwd_horizon_days)

    load = mock.load_hourly.copy()
    load[COL_DT] = pd.to_datetime(load[COL_DT])
    load["date"] = load[COL_DT].dt.normalize()

    daily_actual = (
        load.groupby("date", as_index=False)[COL_LOAD_ACT]
        .sum()
        .rename(columns={"date": COL_DATE})
    )
    merged = daily_actual.merge(cal[[COL_DATE, "load_mwh_daily_true"]], on=COL_DATE)

    assert np.allclose(
        merged[COL_LOAD_ACT].to_numpy(),
        merged["load_mwh_daily_true"].to_numpy(),
        rtol=0.0,
        atol=1e-6,
    )

    assert (mock.load_hourly[COL_LOAD_ACT] >= 0.0).all()
    assert (mock.load_hourly[COL_LOAD_FCST] >= 0.0).all()
