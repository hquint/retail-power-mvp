# AGENTS.md — Repo conventions for automated agents (Codex)

## Objective
Implement small, incremental changes to a retail power MVP engine and dashboard.
Prefer correctness, interpretability, and minimal diffs over refactors.

## Non-goals
- Do not introduce complex architecture, heavy abstractions, or many new files.
- Do not add databases, message queues, or external services.
- Do not add frontend frameworks beyond Streamlit for the MVP.

## Project structure
- `src/powerdash/`: library code (engine, data generation, reporting)
- `scripts/`: runnable entrypoints (keep thin)
- Avoid circular imports. Keep modules small and single-purpose.

## Coding style
- Python 3.12
- Keep functions typed where reasonable, but avoid overengineering.
- Use pandas/numpy idioms; avoid unnecessary loops unless clarity demands it.
- Keep naming explicit: `*_cost_eur`, `*_pnl_eur`, `*_mwh`, `*_px_eur_per_mwh`.

## Risk / accounting conventions
- `*_cost_eur` is positive when it costs money.
- `*_pnl_eur` is positive when it makes money.
- Benchmarks must be defined explicitly and computed consistently (hourly vs daily).
- Do not mix “average price × daily load” with “hourly price × hourly load” unless clearly labeled.

## Changes policy (important)
- Make the smallest change that satisfies the spec.
- Do not rename public columns unless necessary. If you rename/remove, update reporting accordingly.
- If a change impacts output interpretation (benchmark definition, sign convention), document it in the commit message or summary.

## Dependencies
- Do not add new dependencies without a strong reason.
- Prefer built-in libraries + existing stack (pandas/numpy/pydantic/plotly/streamlit).

## Quality checks (run before concluding)
- `poetry run python scripts/run_mvp.py` must run without errors.
- If quick: `poetry run ruff check .` and `poetry run black --check .`
- If tests exist: `poetry run pytest`

## Output expectations
- Scripts should print a daily table and a comparative risk summary.
- Risk summary should compare hedged vs DA-only (forecast + imbalance) distributions.
- Scarcity mechanics (if present) should create occasional tail events.