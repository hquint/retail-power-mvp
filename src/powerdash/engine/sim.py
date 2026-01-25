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

from powerdash.engine.pnl import (
    hedge_fixed_cost_for_delivery,
    mtm_hedge_book,
    realised_delivery_pnl_from_trades,
)


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

    rng = np.random.default_rng(cfg.seed)

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
            load["date"] == delivery,
            [COL_DT, COL_LOAD_ACT, COL_LOAD_FCST, "is_scarcity_day", "is_peak_hour"],
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

        # Schedule: hedge + DA + operational schedule error
        load_fcst = tomorrow[COL_LOAD_FCST].to_numpy()
        residual = tomorrow["residual_mwh_h"].to_numpy()
        residual_share = residual / np.maximum(load_fcst, 1e-9)
        residual_share = np.clip(residual_share, 0.0, 1.0)
        scarcity_mult = 1.0 + cfg.schedule_error_scarcity_mult * (
            tomorrow["is_scarcity_day"].to_numpy() * tomorrow["is_peak_hour"].to_numpy()
        )
        sigma_h = (
            cfg.schedule_error_sigma_base
            * (1.0 + cfg.schedule_error_residual_sensitivity * residual_share)
            * scarcity_mult
        )
        sched_error_mwh_h = rng.normal(0.0, sigma_h * load_fcst)
        tomorrow["sched_mwh_h"] = (
            tomorrow["hedge_mwh_h"] + tomorrow["residual_mwh_h"] + sched_error_mwh_h
        )

        # Imbalance proxy: actual - schedule, state-dependent spreads in scarcity peak hours.
        tomorrow["imbalance_mwh_h"] = tomorrow[COL_LOAD_ACT] - tomorrow["sched_mwh_h"]
        # Short imbalance (need to buy): positive imbalance
        buy_imb = tomorrow["imbalance_mwh_h"].clip(lower=0.0)
        sell_imb = (-tomorrow["imbalance_mwh_h"]).clip(lower=0.0)

        base = cfg.imbalance_spread_base_eur_per_mwh
        scar_add = cfg.imbalance_spread_scarcity_add_eur_per_mwh
        scar_factor = (tomorrow["is_scarcity_day"] * tomorrow["is_peak_hour"]).astype(
            float
        )

        buy_spread = base + scar_add * scar_factor
        sell_spread = (
            base + (cfg.imbalance_sell_discount_factor * scar_add) * scar_factor
        )
        tomorrow["imb_buy_px"] = tomorrow[COL_PRICE_DA] + buy_spread
        tomorrow["imb_sell_px"] = tomorrow[COL_PRICE_DA] - sell_spread

        imb_buy_cost = float((buy_imb * tomorrow["imb_buy_px"]).sum())
        imb_sell_value = float((sell_imb * tomorrow["imb_sell_px"]).sum())
        imbalance_pnl = -(imb_buy_cost) + (imb_sell_value)  # negative is cost net

        # Settlement proxy for delivery day (daily avg DA)
        spot_base = float(tomorrow[COL_PRICE_DA].mean())

        # Perfect DA benchmark: DA-only procurement with perfect forecast (hourly DA * actual hourly load)
        benchmark_perfect_da_cost_eur = float(
            (tomorrow[COL_PRICE_DA] * tomorrow[COL_LOAD_ACT]).sum()
        )
        # -----------------------
        # DA-only benchmark (forecast + imbalance)
        # -----------------------
        # DA buy = forecast volume each hour (no hedge)
        da_only_da_cost_eur = float(
            (tomorrow[COL_PRICE_DA] * tomorrow[COL_LOAD_FCST]).sum()
        )

        # Imbalance if DA-only schedule = forecast + schedule error (residual_share=1)
        da_only_sigma_h = (
            cfg.schedule_error_sigma_base
            * (1.0 + cfg.schedule_error_residual_sensitivity)
            * scarcity_mult * cfg.da_only_schedule_error_mult
        )
        da_only_sched_error = rng.normal(0.0, da_only_sigma_h * load_fcst)
        da_only_sched_mwh_h = tomorrow[COL_LOAD_FCST] + da_only_sched_error
        da_only_imbalance_mwh_h = tomorrow[COL_LOAD_ACT] - da_only_sched_mwh_h
        da_only_buy_imb = da_only_imbalance_mwh_h.clip(lower=0.0)
        da_only_sell_imb = (-da_only_imbalance_mwh_h).clip(lower=0.0)

        da_only_imb_buy_cost_eur = float(
            (da_only_buy_imb * tomorrow["imb_buy_px"]).sum()
        )
        da_only_imb_sell_value_eur = float(
            (da_only_sell_imb * tomorrow["imb_sell_px"]).sum()
        )

        da_only_imbalance_cost_eur = float(
            da_only_imb_buy_cost_eur - da_only_imb_sell_value_eur
        )
        # main benchmark
        da_only_total_cost_eur = float(da_only_da_cost_eur + da_only_imbalance_cost_eur)

        # --------------------------
        # Absolute fixed cost for the hedged energy delivered today
        hedge_fixed_cost_eur = hedge_fixed_cost_for_delivery(
            hedge_trades=hedge_trades,
            delivery_date=delivery,
        )

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

        # Total procurement cost for that delivery day
        imbalance_cost_eur = float(
            imb_buy_cost - imb_sell_value
        )  # positive means net cost
        total_procurement_cost_eur = hedge_fixed_cost_eur + da_cost + imbalance_cost_eur

        procurement_saving_vs_da_only_eur = (
            da_only_total_cost_eur - total_procurement_cost_eur
        )

        procurement_saving_vs_perfect_da_eur = (
            benchmark_perfect_da_cost_eur - total_procurement_cost_eur
        )

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
                "hedge_fixed_cost_eur": hedge_fixed_cost_eur,
                "da_cost_eur": da_cost,
                "imbalance_cost_eur": imbalance_cost_eur,
                "imbalance_pnl_eur": imbalance_pnl,  # keep for debugging (negative if cost)
                "hedge_delivery_pnl_eur": hedge_delivery_pnl,
                "hedge_mtm_change_eur": hedge_mtm,
                "total_procurement_cost_eur": total_procurement_cost_eur,
                "da_only_da_cost_eur": da_only_da_cost_eur,
                "da_only_imbalance_cost_eur": da_only_imbalance_cost_eur,
                "da_only_total_cost_eur": da_only_total_cost_eur,
                "benchmark_perfect_da_cost_eur": benchmark_perfect_da_cost_eur,
                "procurement_saving_vs_da_only_eur": procurement_saving_vs_da_only_eur,
                "procurement_saving_vs_perfect_da_eur": procurement_saving_vs_perfect_da_eur,
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
