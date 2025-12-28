from __future__ import annotations

import pandas as pd


def delivery_hedge_pnl(
    spot_base_price: float, hedge_fixed_price: float, hedged_mwh: float
) -> float:
    """
    Realised hedge benefit for delivered day:
      (spot/index - fixed) * volume
    Positive when spot > fixed (hedge helps).
    """
    return float((spot_base_price - hedge_fixed_price) * hedged_mwh)


def mtm_open_hedge_pnl(
    prev_curve_price: float, curr_curve_price: float, open_hedged_mwh: float
) -> float:
    """
    Daily MtM change of an open hedge position for a given delivery day.
    For MVP assume linear exposure:
      (curr - prev) * volume
    (Sign depends on being long fixed-price vs float; here we treat it as long the forward price.)
    """
    return float((curr_curve_price - prev_curve_price) * open_hedged_mwh)


def mtm_hedge_book(
    hedge_trades: pd.DataFrame,
    curve_prev,
    curve_curr,
    prev_val_date: pd.Timestamp,
    curr_val_date: pd.Timestamp,
) -> float:
    """
    MtM change from prev -> curr across all OPEN future delivery dates
    using forward snapshots.
    We mark each trade at forward price for its delivery day.
    """
    if hedge_trades.empty:
        return 0.0

    prev = pd.Timestamp(prev_val_date).normalize()
    curr = pd.Timestamp(curr_val_date).normalize()

    total = 0.0
    for _, tr in hedge_trades.iterrows():
        d = pd.Timestamp(tr["delivery_date"]).normalize()
        vol = float(tr["volume_mwh"])
        try:
            p0 = float(curve_prev.get_fwd_base(prev, d))
            p1 = float(curve_curr.get_fwd_base(curr, d))
        except KeyError:
            # If outside curve horizon, skip in MVP
            continue
        total += (p1 - p0) * vol
    return float(total)


def realised_delivery_pnl_from_trades(
    hedge_trades: pd.DataFrame,
    delivery_date: pd.Timestamp,
    spot_base_price: float,
) -> float:
    """
    Realised delivery PnL for the delivered day from all trades targeting that delivery day:
      sum( (spot - fixed_price) * volume )
    """
    if hedge_trades.empty:
        return 0.0
    d = pd.Timestamp(delivery_date).normalize()
    day_trades = hedge_trades.loc[
        pd.to_datetime(hedge_trades["delivery_date"]).dt.normalize() == d
    ]
    if day_trades.empty:
        return 0.0
    return float(
        ((spot_base_price - day_trades["fixed_price"]) * day_trades["volume_mwh"]).sum()
    )
