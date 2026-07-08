"""Build data.json: fetch feeds, run the gas->heat regression, write output.

Method (Watson/Sansom-style): OLS of daily NTS gas demand on HDD across a
trailing 365-day window, per candidate base temperature; the best-R2 base is
selected. The HDD-driven component is space heating; the intercept is the
non-weather baseline (water heating, cooking, industrial, power-station gas).

Calibration: the running 12-month space-heat total is compared against the
ECUK-derived annual anchor; the ratio is reported (and flagged) but NOT yet
applied automatically - Phase 1 go/no-go requires it within +/-10%.

Fallback: on any feed failure the previous data.json values are retained and
that source is marked "stale".
"""

import datetime as dt
import json
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(__file__))
from fetch_degree_days import fetch_degree_days, HDD_BASES  # noqa: E402
from fetch_gas import fetch_gas_demand                       # noqa: E402

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")
WINDOW_DAYS = 365

# --- ECUK anchor (UPDATE each September on ECUK release) ---------------------
# ECUK 2025 (2024 data), end-use tables: GB domestic + services gas used for
# space + water heating. PLACEHOLDER pending exact Table U3 extraction -
# order of magnitude ~300 TWh. Status flag forces the caveat onto the site
# until a sourced value is entered.
ECUK_ANNUAL_GAS_HEAT_TWH = 300.0
ECUK_ANCHOR_STATUS = "placeholder - replace with sourced ECUK Table U3 value"


def ols(x, y):
    n = len(x)
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((xi - mx) ** 2 for xi in x)
    sxy = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    slope = sxy / sxx if sxx else 0.0
    intercept = my - slope * mx
    ss_tot = sum((yi - my) ** 2 for yi in y)
    ss_res = sum((yi - (intercept + slope * xi)) ** 2 for xi, yi in zip(x, y))
    r2 = 1 - ss_res / ss_tot if ss_tot else 0.0
    return slope, intercept, r2


def load_previous():
    try:
        with open(OUT_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    prev = load_previous()
    out = {
        "updated": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "sources": {},
    }

    # --- degree days ---------------------------------------------------------
    try:
        dd = fetch_degree_days(days=WINDOW_DAYS + 40)
        out["sources"]["degree_days"] = {"status": "ok",
                                         "last_good": dd["dates"][-1]}
    except Exception:
        traceback.print_exc()
        dd = prev.get("_dd")
        out["sources"]["degree_days"] = {
            "status": "stale",
            "last_good": prev.get("sources", {}).get("degree_days", {}).get("last_good")}
        if not dd:
            _write(out | {"error": "no degree-day data available"})
            return

    # --- gas -----------------------------------------------------------------
    try:
        gas = fetch_gas_demand(days=WINDOW_DAYS + 40)
        nts = gas["nts_demand_actual"]
        vals = sorted(nts.values())
        print(f"gas diagnostics: {len(nts)} days, {min(nts)} to {max(nts)}, "
              f"min {vals[0]} max {vals[-1]} GWh, {len(set(vals))} distinct values")
        out["sources"]["gas"] = {"status": "ok",
                                 "last_good": max(nts) if nts else None,
                                 "publications": gas["_meta"]}
    except Exception:
        traceback.print_exc()
        gas = prev.get("_gas")
        out["sources"]["gas"] = {
            "status": "stale",
            "last_good": prev.get("sources", {}).get("gas", {}).get("last_good")}
        if not gas:
            _write(out | {"error": "no gas data available"})
            return
        nts = gas["nts_demand_actual"]

    # --- align series --------------------------------------------------------
    dd_idx = {d: i for i, d in enumerate(dd["dates"])}
    common = sorted(set(nts) & set(dd_idx))[-WINDOW_DAYS:]
    if len(common) < 90:
        _write(out | {"error": f"only {len(common)} overlapping days"})
        return

    y = [nts[d] for d in common]

    # --- regression, best base ----------------------------------------------
    best = None
    for base in HDD_BASES:
        x = [dd["hdd"][str(base)][dd_idx[d]] for d in common]
        slope, intercept, r2 = ols(x, y)
        if best is None or r2 > best["r2"]:
            best = {"base_temp": base, "slope_GWh_per_HDD": round(slope, 1),
                    "intercept_GWh": round(intercept, 1), "r2": round(r2, 3),
                    "window_days": len(common)}
    base = str(best["base_temp"])
    hdd_series = [dd["hdd"][base][dd_idx[d]] for d in common]
    space_heat = [round(max(0.0, best["slope_GWh_per_HDD"] * h), 1)
                  for h in hdd_series]

    # --- calibration check (12-month space-heat vs ECUK anchor) --------------
    annual_space_twh = sum(space_heat) / 1000.0
    ratio = annual_space_twh / ECUK_ANNUAL_GAS_HEAT_TWH
    calibration = {
        "model_12m_gas_space_heat_TWh": round(annual_space_twh, 1),
        "ecuk_anchor_TWh": ECUK_ANNUAL_GAS_HEAT_TWH,
        "anchor_status": ECUK_ANCHOR_STATUS,
        "ratio": round(ratio, 3),
        "within_10pct": abs(ratio - 1.0) <= 0.10,
    }

    # --- weekly headline ------------------------------------------------------
    wk = common[-7:]
    wk_i = [common.index(d) for d in wk]
    weekly = {
        "week_ending": wk[-1],
        "gas_total_GWh": round(sum(y[i] for i in wk_i), 0),
        "gas_space_heat_GWh": round(sum(space_heat[i] for i in wk_i), 0),
        "hdd_total": round(sum(hdd_series[i] for i in wk_i), 1),
    }
    weekly["gas_baseline_GWh"] = round(
        weekly["gas_total_GWh"] - weekly["gas_space_heat_GWh"], 0)

    out.update({
        "regression": best,
        "calibration": calibration,
        "weekly": weekly,
        "series": {
            "dates": common,
            "gas_GWh": [round(v, 1) for v in y],
            "hdd": hdd_series,
            "space_heat_GWh": space_heat,
        },
        "ni_note": {
            "hdd_15_5_latest": dd["ni"]["hdd_15_5"][-1] if dd["ni"]["hdd_15_5"] else None,
            "note": ("NI is not on the GB NTS feed. NI heating is estimated "
                     "annually from subnational consumption statistics, "
                     "scaled by NI degree days."),
        },
        # raw caches for stale-fallback on next run
        "_dd": dd,
        "_gas": {k: v for k, v in gas.items()},
    })
    _write(out)


def _write(out):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    if "regression" in out:
        print("regression:", out["regression"], "| weekly:", out["weekly"], "| calibration ratio:", out["calibration"]["ratio"])
    print(f"wrote {OUT_PATH}")
    if "error" in out:
        print("ERROR:", out["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
