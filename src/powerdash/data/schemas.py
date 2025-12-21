from __future__ import annotations

# Central place for column names to avoid refactor pain later.

COL_DT = "dt"                # hourly timestamp
COL_DATE = "date"            # daily date (no time)
COL_VAL_DATE = "val_date"    # curve snapshot date
COL_DELIV_DATE = "delivery_date"

COL_PRICE_DA = "price_da"
COL_FWD_BASE = "fwd_base"

COL_LOAD_ACT = "load_mwh_actual"
COL_LOAD_FCST = "load_mwh_forecast"

COL_HEDGE_MWH = "hedge_mwh"
COL_DA_MWH = "da_mwh"
COL_SCHED_MWH = "sched_mwh"
COL_IMB_MWH = "imbalance_mwh"
