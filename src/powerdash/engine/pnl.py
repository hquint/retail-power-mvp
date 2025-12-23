from __future__ import annotations


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
