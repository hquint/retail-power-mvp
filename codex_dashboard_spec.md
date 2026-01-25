# Streamlit Dashboard MVP (PowerDash)

## Goal
Create a Streamlit app that:
1) runs the simulation (using existing engine + generator),
2) shows daily KPI tables and risk summaries,
3) provides interactive controls for key config knobs,
4) provides simple charts: cost time series + distribution comparison,
5) stays MVP: minimal files, no new dependencies beyond streamlit/plotly/pandas already present.

## Non-goals
- No auth, no database, no real market data, no deployment.
- No heavy refactors of engine code.

---

## A) Files to add

### A1) Streamlit entrypoint
Create: `src/powerdash/app/streamlit_app.py`

The app must:
- Set page config (title "PowerDash MVP", wide layout).
- Provide sidebar controls (see Section B).
- On "Run simulation" button: run simulation once and cache results.
- Display:
  - Daily dashboard table (existing `daily_dashboard_table` if available).
  - Risk summaries (total cost and variable cost if present; else show what exists).
  - Plots (Section C).
- Provide a download button for the daily table as CSV.
- Use `st.cache_data` for simulation output keyed by config parameters.

Also add a thin launcher script:
Create: `scripts/run_streamlit.sh` (optional but useful) that runs:
`poetry run streamlit run src/powerdash/app/streamlit_app.py`

---

## B) Controls (sidebar)

Group "Simulation" controls:
- start_date (date input) default: today - 10 days (or fixed like 2026-01-01)
- n_days (slider) default: 60, range 14..365
- seed (number input) default from SimConfig
- daily_load_mwh (number input) default from SimConfig / generator if exists; if not, just keep fixed at 100

Group "Hedge" controls:
- hedge_horizon_days (slider) default 60, range 7..180
- hedge_fraction_short (slider 0..1) default existing ladder start
- hedge_fraction_long (slider 0..1) default existing ladder end
- (If ladder params differ in code, map to your actual config fields.)

Group "Scarcity / imbalance" controls:
- scarcity_day_prob (slider 0..0.2)
- scarcity_peak_multiplier (slider 1..10)
- imbalance_spread_base_eur_per_mwh (slider 0..30)
- imbalance_spread_scarcity_add_eur_per_mwh (slider 0..200)
- imbalance_sell_discount_factor (slider 0..1)

Group "Schedule error" controls:
- schedule_error_sigma_base (slider 0..0.05, step 0.001)
- schedule_error_residual_sensitivity (slider 0..5.0, step 0.1)
- schedule_error_scarcity_mult (slider 0..20, step 0.5)
- da_only_schedule_error_mult (slider 1..3, step 0.1) if exists

Notes:
- The app should construct a `SimConfig` instance from these inputs (use pydantic model).
- The app should call the existing generator and engine runner exactly as `scripts/run_mvp.py` does.
- Keep all defaults aligned with current SimConfig defaults.

---

## C) Visuals

Use plotly (already installed). Provide:

1) Line chart (daily):
- y series: total_procurement_cost_eur vs da_only_total_cost_eur
- x: date

2) Bar or line chart (daily):
- procurement_saving_vs_da_only_eur

3) Distribution comparison (histogram overlay):
- total_procurement_cost_eur (hedged) vs da_only_total_cost_eur

4) If variable cost columns exist (hedged_variable_cost_eur / da_only_variable_cost_eur):
- Add a second distribution plot for variable costs.

---

## D) Tables

Show:
- Daily table (sorted by date)
- Summary row (sum columns where appropriate)
- Risk summary table (the one printed in CLI), as a Streamlit dataframe.

If risk summary currently returned as a dict or df, display it directly.
If it is only printed in CLI, implement a helper in reporting to return a DataFrame without changing printed output.

---

## E) Minimal refactors / helper additions allowed

If needed for the app:
- Add `powerdash.reporting.metrics.risk_summary_table(...)` that returns a DataFrame (not printing).
- Add `powerdash.reporting.metrics.summary_row(...)` that returns a 1-row DataFrame.
- Keep existing functions intact; add new ones.

---

## F) Acceptance criteria

1) Running:
`poetry run streamlit run src/powerdash/app/streamlit_app.py`
opens the app without exceptions.

2) Clicking "Run simulation" shows:
- daily table,
- risk summary,
- charts.

3) Changing any sidebar control and re-running changes outputs.
