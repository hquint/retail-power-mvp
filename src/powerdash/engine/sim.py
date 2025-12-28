from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from powerdash.config import SimConfig
from powerdash.data.schemas import (
    COL_DELIV_DATE,
    COL_DT,
    COL_LOAD_ACT,
    COL_LOAD_FCST,
    COL_PRICE_DA,
    COL_VAL_DATE,
)
from powerdash.engine.curves import DailyBaseForwardCurve

from powerdash.engine.hedging import (
    add_hedge_adjustments,
    open_hedge_position_by_delivery,
    target_daily_hedge_book,
)
from powerdash.engine.pnl import mtm_hedge_book, realised_delivery_pnl_from_trades


@dataclass(frozen=True)
class SimResult:
    daily_pnl: pd.DataFrame
    daily_positions: pd.DataFrame


def run_simulation_hourly(
    cfg: SimConfig,
    prices_da_hourly: pd.DataFrame,
    load_hourly: pd.DataFrame,
    fwd_curves_daily: pd.DataFrame,
) -> SimResult:
    """
    MVP simulation:
    - Each day t (decision date):
        - Determine expected daily load from hourly forecast for day t+1
        - Hedge ratio applied (daily baseload hedge for delivery day t+1), fixed at fwd_base(t, t+1)
        - Procure residual in DA for day t+1 at hourly DA prices
    - Delivery day d:
        - Compute realised hedge pnl vs daily avg DA as proxy for index
        - Compute DA cost
        - Compute simple imbalance penalty based on forecast error (hourly)
    - Also compute hedge MtM changes across forward curve snapshots for open future deliveries (next 60 days)
      For MVP we track only the single "next-day hedge" as open until delivery day (one-day open).
    """
    prices = prices_da_hourly.copy()
    load = load_hourly.copy()

    prices[COL_DT] = pd.to_datetime(prices[COL_DT])
    load[COL_DT] = pd.to_datetime(load[COL_DT])

    prices["date"] = prices[COL_DT].dt.normalize()
    load["date"] = load[COL_DT].dt.normalize()

    curve = DailyBaseForwardCurve(fwd_curves_daily=fwd_curves_daily)
    # create hedge book
    hedge_trades = pd.DataFrame(
        columns=["trade_date", "delivery_date", "volume_mwh", "fixed_price"]
    )

    # Decide dates
    start = pd.Timestamp(cfg.start_date).normalize()
    decision_days = pd.date_range(
        start=start, periods=cfg.n_days, freq="D", inclusive="left"
    )

    pnl_rows = []
    pos_rows = []

    # For MVP: hedge is placed on day t for delivery t+1 and "open" only until delivery.
    # So MtM is simply (fwd(t+1,t+1) - fwd(t,t+1)) * volume if you mark it at next day's curve before delivery.
    # We compute MtM change from t -> t+1 for the delivery day t+1.

    for t in decision_days:
        delivery = t + pd.Timedelta(days=1)

        # Slice tomorrow
        tomorrow_load = load.loc[
            load["date"] == delivery, [COL_DT, COL_LOAD_ACT, COL_LOAD_FCST]
        ].copy()
        tomorrow_prices = prices.loc[
            prices["date"] == delivery, [COL_DT, COL_PRICE_DA]
        ].copy()
        if tomorrow_load.empty or tomorrow_prices.empty:
            break

        # Expected vs actual daily load
        exp_daily = float(tomorrow_load[COL_LOAD_FCST].sum())
        act_daily = float(tomorrow_load[COL_LOAD_ACT].sum())

        # -------------------------
        # 1) Rolling hedge book update at decision day t
        # -------------------------
        # MVP assumption: use tomorrow's expected daily load as proxy for all future days in horizon
        targets = target_daily_hedge_book(
            val_date=t,
            horizon_days=cfg.fwd_horizon_days,
            expected_daily_load_mwh=exp_daily,
        )

        # Trade deltas to reach targets using today's forward curve snapshot
        hedge_trades = add_hedge_adjustments(
            hedge_trades=hedge_trades,
            curve=curve,
            val_date=t,
            targets=targets,
        )

        # Open hedge volume for tomorrow (delivery day)
        open_pos = open_hedge_position_by_delivery(hedge_trades)
        open_tomorrow = open_pos.loc[open_pos["delivery_date"] == delivery, "open_mwh"]
        hedged_mwh = float(open_tomorrow.iloc[0]) if not open_tomorrow.empty else 0.0
        hedge_per_hour = hedged_mwh / 24.0

        # -------------------------
        # 2) DA procurement for tomorrow (physical)
        # -------------------------
        tomorrow = tomorrow_load.merge(tomorrow_prices, on=COL_DT, how="inner")
        tomorrow["hedge_mwh_h"] = hedge_per_hour
        tomorrow["residual_mwh_h"] = np.maximum(
            tomorrow[COL_LOAD_FCST] - tomorrow["hedge_mwh_h"], 0.0
        )

        da_cost = float((tomorrow["residual_mwh_h"] * tomorrow[COL_PRICE_DA]).sum())

        # Schedule: hedge + DA = hedge_per_hour + residual
        tomorrow["sched_mwh_h"] = tomorrow["hedge_mwh_h"] + tomorrow["residual_mwh_h"]

        # Imbalance proxy: actual - schedule, penalise at (DA + spread) for positive shortfall
        # (This is simplified; we’ll replace with reBAP series later.)
        tomorrow["imbalance_mwh_h"] = tomorrow[COL_LOAD_ACT] - tomorrow["sched_mwh_h"]
        # Short imbalance (need to buy): positive imbalance
        buy_imb = tomorrow["imbalance_mwh_h"].clip(lower=0.0)
        sell_imb = (-tomorrow["imbalance_mwh_h"]).clip(lower=0.0)

        imb_buy_cost = float(
            (
                buy_imb * (tomorrow[COL_PRICE_DA] + cfg.imbalance_spread_eur_per_mwh)
            ).sum()
        )
        imb_sell_value = float(
            (
                sell_imb * (tomorrow[COL_PRICE_DA] - cfg.imbalance_spread_eur_per_mwh)
            ).sum()
        )
        imbalance_pnl = -(imb_buy_cost) + (imb_sell_value)  # negative is cost net

        # Settlement proxy for delivery day (daily avg DA)
        spot_base = float(tomorrow[COL_PRICE_DA].mean())

        # -------------------------
        # 3) Realised hedge delivery PnL from all hedge trades targeting this delivery day
        # -------------------------
        hedge_delivery_pnl = realised_delivery_pnl_from_trades(
            hedge_trades=hedge_trades,
            delivery_date=delivery,
            spot_base_price=spot_base,
        )

        # -------------------------
        # 4) Hedge MtM change across ALL open positions from curve(t) -> curve(t+1)
        # -------------------------

        # We mark all open future deliveries using forward snapshots.
        # Note: requires that fwd_curves contain points for (t, d) and (t+1, d). For d=t+1, (t+1,d) may not exist
        # in our generator; that's ok because the longer-dated positions dominate MtM and missing points are skipped.
        t_next = t + pd.Timedelta(days=1)
        hedge_mtm = mtm_hedge_book(
            hedge_trades=hedge_trades,
            curve_prev=curve,
            curve_curr=curve,
            prev_val_date=t,
            curr_val_date=t_next,
        )

        # Drop trades for the delivered day (they are now realised/expired). This prevents “double counting” hedge PnL.
        if not hedge_trades.empty:
            dd = pd.Timestamp(delivery).normalize()
            hedge_trades = hedge_trades.loc[
                pd.to_datetime(hedge_trades["delivery_date"]).dt.normalize() != dd
            ].copy()

        # Convert imbalance PnL (negative = cost) into a positive cost number
        imbalance_cost_eur = -imbalance_pnl

        total_procurement_cost_eur = da_cost + imbalance_cost_eur - hedge_delivery_pnl
        benchmark_cost_eur = act_daily * spot_base
        procurement_saving_vs_benchmark_eur = (
            benchmark_cost_eur - total_procurement_cost_eur
        )

        # Total procurement economics for that delivery day:
        # Physical cost (DA) + imbalance cost + hedge effect (delivery pnl offsets spot economics)
        # For dashboard attribution, keep components separate.
        pnl_rows.append(
            {
                COL_VAL_DATE: t,
                COL_DELIV_DATE: delivery,
                "exp_load_mwh": exp_daily,
                "act_load_mwh": act_daily,
                "hedged_mwh": hedged_mwh,
                "spot_base_price": spot_base,
                "da_cost_eur": da_cost,
                "imbalance_pnl_eur": imbalance_pnl,
                "hedge_delivery_pnl_eur": hedge_delivery_pnl,
                "hedge_mtm_change_eur": hedge_mtm,
                "total_procurement_cost_eur": total_procurement_cost_eur,
                "benchmark_cost_eur": benchmark_cost_eur,
                "procurement_saving_vs_benchmark_eur": procurement_saving_vs_benchmark_eur,
            }
        )

        pos_rows.append(
            {
                COL_VAL_DATE: t,
                COL_DELIV_DATE: delivery,
                "hedge_per_hour_mwh": hedge_per_hour,
                "da_total_mwh": float(tomorrow["residual_mwh_h"].sum()),
                "sched_total_mwh": float(tomorrow["sched_mwh_h"].sum()),
                "imbalance_total_mwh": float(tomorrow["imbalance_mwh_h"].sum()),
            }
        )

    daily_pnl = pd.DataFrame(pnl_rows)
    daily_positions = pd.DataFrame(pos_rows)
    return SimResult(daily_pnl=daily_pnl, daily_positions=daily_positions)
