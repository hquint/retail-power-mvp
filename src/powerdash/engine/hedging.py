from __future__ import annotations

import pandas as pd

def hedge_ratio_by_tenor_days(k: int) -> float:
    """
    Simple hedge ladder by tenor (days ahead).
    Tune later / make configurable.
    """
    if 1 <= k <= 7:
        return 0.60
    if 8 <= k <= 30:
        return 0.75
    return 0.85  # 31-60


def target_daily_hedge_book(
    val_date: pd.Timestamp,
    horizon_days: int,
    expected_daily_load_mwh: float,
) -> pd.DataFrame:
    """
    Returns target hedged MWh for each delivery date in (val_date+1 .. val_date+horizon).
    """
    val = pd.Timestamp(val_date).normalize()
    rows = []
    for k in range(1, horizon_days + 1):
        d = val + pd.Timedelta(days=k)
        hr = hedge_ratio_by_tenor_days(k)
        rows.append({"val_date": val, "delivery_date": d, "target_hedge_mwh": expected_daily_load_mwh * hr})
    return pd.DataFrame(rows)


def open_hedge_position_by_delivery(hedge_trades: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate hedge trades into net open position per delivery_date.
    Columns expected: delivery_date, volume_mwh, fixed_price.
    We keep fixed_price per trade for PnL; aggregation here is only volumes.
    """
    if hedge_trades.empty:
        return pd.DataFrame({"delivery_date": [], "open_mwh": []})
    df = hedge_trades.copy()
    df["delivery_date"] = pd.to_datetime(df["delivery_date"]).dt.normalize()
    return df.groupby("delivery_date", as_index=False)["volume_mwh"].sum().rename(columns={"volume_mwh": "open_mwh"})


def add_hedge_adjustments(
    hedge_trades: pd.DataFrame,
    curve,
    val_date: pd.Timestamp,
    targets: pd.DataFrame,
) -> pd.DataFrame:
    """
    For each delivery_date in targets, trade the difference between current open_mwh and target_hedge_mwh.
    Trade price = forward base at (val_date, delivery_date).
    """
    val = pd.Timestamp(val_date).normalize()

    current = open_hedge_position_by_delivery(hedge_trades)
    merged = targets.merge(current, on="delivery_date", how="left")
    merged["open_mwh"] = merged["open_mwh"].fillna(0.0)
    merged["delta_mwh"] = merged["target_hedge_mwh"] - merged["open_mwh"]

    new_trades = []
    for _, r in merged.iterrows():
        delta = float(r["delta_mwh"])
        if abs(delta) < 1e-9:
            continue
        d = pd.Timestamp(r["delivery_date"]).normalize()
        px = float(curve.get_fwd_base(val_date=val, delivery_date=d))
        new_trades.append(
            {
                "trade_date": val,
                "delivery_date": d,
                "volume_mwh": delta,
                "fixed_price": px,
            }
        )

    if not new_trades:
        return hedge_trades

    new_df = pd.DataFrame(new_trades)

    if hedge_trades.empty:
        return new_df.reset_index(drop=True)

    # Ensure consistent dtypes by concatenating non-empty frames
    return pd.concat([hedge_trades, new_df], ignore_index=True)


def fixed_ratio_daily_hedge_mwh(
    expected_daily_load_mwh: float, hedge_ratio: float
) -> float:
    return float(expected_daily_load_mwh * hedge_ratio)


def hedge_price_from_curve(
    curve, val_date: pd.Timestamp, delivery_date: pd.Timestamp
) -> float:
    """
    For MVP: hedge 'price' equals the daily baseload forward at time of hedge placement.
    Later: you will store executed hedge trades; here we keep it simple and deterministic.
    """
    return float(curve.get_fwd_base(val_date=val_date, delivery_date=delivery_date))
