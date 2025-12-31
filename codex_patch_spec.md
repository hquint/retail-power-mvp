# Patch Spec: state-dependent reBAP + scarcity forecast error (MVP)

## Goal
Introduce two mechanics to make risk metrics meaningful:
1) State-dependent imbalance settlement (reBAP proxy): spreads widen sharply in scarcity peak hours, buy side widens more than sell side.
2) Scarcity forecast error: forecast noise increases on scarcity days, especially in peak hours.

The changes MUST be minimal and must preserve existing outputs unless fields are renamed/added explicitly.

After implementing, run:
- poetry run python scripts/run_mvp.py

and ensure it prints:
- the daily table (dash)
- the comparative risk summary row

---

## A) config.py changes

File: src/powerdash/config.py

In SimConfig, add the following fields (keep existing ones):

- imbalance_spread_base_eur_per_mwh: float = 6.0
- imbalance_spread_scarcity_add_eur_per_mwh: float = 45.0
- imbalance_sell_discount_factor: float = 0.35
- forecast_sigma_scarcity_mult: float = 2.5

These should have docstring/comments indicating:
- base spread is always applied
- scarcity add applies only in scarcity *peak* hours
- sell widens less than buy via discount factor
- forecast sigma increases on scarcity days (and more in peak hours)

---

## B) generator.py changes

File: src/powerdash/data/generator.py

### B1) generate_mock_data signature
Add parameters (with defaults):
- scarcity_forecast_sigma_mult: float = 2.5

So signature includes:
scarcity_day_prob, scarcity_peak_multiplier, scarcity_forecast_sigma_mult

### B2) Calendar flags
Assumes generator already creates:
- cal["temp_c"]
- cal["is_scarcity_day"] (already implemented earlier)

If not present, implement:
- cal["is_winter_like"] = (temp_c <= 3.0)
- cal["is_scarcity_day"] drawn with scarcity_day_prob on winter-like days

### B3) Hourly rows must include flags
When creating hourly LOAD rows and hourly DA PRICE rows, add:
- is_scarcity_day (0/1)
- is_peak_hour (0/1) where peak hours are 17..20 inclusive

These columns must appear in both hourly tables so that after merging in sim.py, tomorrow has them.

### B4) Scarcity forecast error
When building hourly forecast from hourly actual, modify forecast noise:
- On non-scarcity days: sigma = forecast_sigma for all hours.
- On scarcity days: base sigma = forecast_sigma * scarcity_forecast_sigma_mult
  - For peak hours (17..20): multiply that sigma by 1.6
  - For non-peak hours: keep as base sigma

Implement via an hour_sigma vector of length 24.

Forecast must remain non-negative.

---

## C) sim.py changes

File: src/powerdash/engine/sim.py

### C1) Compute state-dependent imbalance prices per hour
After `tomorrow = tomorrow_load.merge(tomorrow_prices, ...)` and before computing imbalance costs, compute:

base = cfg.imbalance_spread_base_eur_per_mwh
scar_add = cfg.imbalance_spread_scarcity_add_eur_per_mwh
scar_factor = (tomorrow["is_scarcity_day"] * tomorrow["is_peak_hour"]).astype(float)

buy_spread  = base + scar_add * scar_factor
sell_spread = base + (cfg.imbalance_sell_discount_factor * scar_add) * scar_factor

tomorrow["imb_buy_px"]  = tomorrow[COL_PRICE_DA] + buy_spread
tomorrow["imb_sell_px"] = tomorrow[COL_PRICE_DA] - sell_spread

### C2) Use these prices for imbalance settlement (hedged strategy)
Replace any usage of (DA +/- constant spread) with:
- imb_buy_cost = sum(imb_buy * imb_buy_px)
- imb_sell_value = sum(imb_sell * imb_sell_px)

Define:
- imbalance_cost_eur = imb_buy_cost - imb_sell_value (positive cost)
- imbalance_pnl_eur kept as -(buy_cost) + sell_value (optional, for debugging)

### C3) Use the same imbalance prices in DA-only benchmark (forecast + imbalance)
Where DA-only benchmark computes imbalance buy/sell value, use:
- tomorrow["imb_buy_px"] and tomorrow["imb_sell_px"]

The DA-only benchmark should remain:
- da_only_da_cost_eur = sum(DA * forecast)
- da_only_total_cost_eur = da_only_da_cost_eur + da_only_imbalance_cost_eur

### C4) No other logic changes
Do NOT change hedging logic, hedge book, MtM, or fixed cost logic beyond what’s needed to integrate these prices/flags.

---

## D) run_mvp.py wiring

File: scripts/run_mvp.py

When calling generate_mock_data, pass:
- scarcity_forecast_sigma_mult=cfg.forecast_sigma_scarcity_mult

Keep existing scarcity_day_prob and scarcity_peak_multiplier wiring.

---

## E) reporting remains compatible

If daily_dashboard_table currently expects columns, ensure it includes the columns you already show:
- total_procurement_cost_eur
- da_only_total_cost_eur
- procurement_saving_vs_da_only_eur
and that risk_summary compares hedged vs da_only distributions.

No new reporting columns are required beyond the scarcity flags, which should not be displayed by default.

---

## Acceptance criteria

1) `poetry run python scripts/run_mvp.py` runs without exceptions.
2) The comparative Risk summary shows:
- da_only_p95_cost_eur > hedged_p95_cost_eur (often, not guaranteed every run)
- da_only_max_cost_eur > hedged_max_cost_eur (often, not guaranteed every run)
3) The daily table contains `procurement_saving_vs_da_only_eur` that is not identically equal to hedge_delivery_pnl anymore (i.e., the identity is broken by state-dependent imbalance + forecast error).