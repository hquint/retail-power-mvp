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

---

# Patch V2: remove scarcity forecast error + add schedule error mechanism

## Objective
Break the identity where `procurement_saving_vs_da_only_eur == hedge_delivery_pnl_eur` by making imbalance exposure differ between strategies.

We will:
1) REMOVE the scarcity forecast-error amplification (it affects both strategies equally and adds complexity).
2) ADD a schedule-error mechanism that scales with DA residual reliance and is amplified in scarcity peak hours.
This creates realistic operational imbalance risk and allows hedging to reduce tail risk vs DA-only.

---

## V2-A) Remove scarcity forecast error changes

### Files
- src/powerdash/config.py
- src/powerdash/data/generator.py
- scripts/run_mvp.py

### Required removals
1) In SimConfig (config.py):
   - Remove `forecast_sigma_scarcity_mult`.

2) In generator.py:
   - Remove the function parameter `scarcity_forecast_sigma_mult`.
   - Remove any logic that scales forecast noise by scarcity / peak hours.
   - Keep only: `hourly_forecast = max(hourly_actual + Normal(0, forecast_sigma), 0)` (your existing baseline logic).
   - KEEP the columns:
     - `is_scarcity_day`
     - `is_peak_hour`
     in hourly load and price rows (used for reBAP and schedule error).

3) In run_mvp.py:
   - Remove passing `scarcity_forecast_sigma_mult=...`.

After removal, `generate_mock_data(...)` should no longer accept that parameter.

---

## V2-B) Add schedule error mechanism

### Add config knobs
File: src/powerdash/config.py (SimConfig)

Add:
- schedule_error_sigma_base: float = 0.004
- schedule_error_residual_sensitivity: float = 1.5
- schedule_error_scarcity_mult: float = 4.0

Interpretation:
- schedule error is an operational nomination/position management error (MWh).
- it increases as the residual (DA reliance) increases.
- it is amplified on scarcity *peak hours*.

### Implement schedule error in sim.py (hedged strategy)
File: src/powerdash/engine/sim.py

After computing:
- `tomorrow["hedge_mwh_h"]`
- `tomorrow["residual_mwh_h"]`

Compute a schedule error per hour:

1) Define residual share:
   residual_share = residual_mwh_h / max(load_fcst_mwh_h, eps)
   clipped to [0, 1].

2) Define sigma for schedule error per hour:
   sigma_h = schedule_error_sigma_base
             * (1 + schedule_error_residual_sensitivity * residual_share)
             * scarcity_multiplier

Where scarcity_multiplier = 1 + schedule_error_scarcity_mult * (is_scarcity_day * is_peak_hour)

3) Sample error:
   sched_error_mwh_h ~ Normal(0, sigma_h * load_fcst_mwh_h)

4) Define schedule for hedged strategy:
   sched_mwh_h = hedge_mwh_h + residual_mwh_h + sched_error_mwh_h

Keep DA-only benchmark schedule as:
- forecast (no hedge) + schedule error with residual_share = 1
OR (even simpler) apply the same schedule error formula but set residual_share=1 for DA-only.

Important: Use the same random generator (np.random.default_rng with a deterministic seed) so runs are reproducible. Prefer deriving the RNG from the simulation seed.

### DA-only benchmark schedule error
In the DA-only benchmark block:
- compute sched_error_da_only using the same formula but residual_share=1 for all hours
- da_only_sched = load_fcst + sched_error_da_only
- da_only_imbalance_mwh_h = act - da_only_sched
Then compute imbalance costs using `imb_buy_px` / `imb_sell_px` as already implemented.

### Acceptance criteria for V2
1) `poetry run python scripts/run_mvp.py` runs cleanly.
2) `procurement_saving_vs_da_only_eur` is NOT identically equal to `hedge_delivery_pnl_eur` anymore.
3) Comparative risk summary typically shows improved tails for hedged vs DA-only:
   - delta_p95_eur > 0
   - delta_max_eur > 0
   (Not guaranteed every run, but should occur frequently.)