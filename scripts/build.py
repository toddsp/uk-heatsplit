"""Build data.json: fetch feeds, regress LDZ (buildings) gas on HDD, write.

Regression target: summed LDZ offtake (excludes power stations).
NTS total retained for context. DHW sits in the flat baseline; see site
methodology panel for known biases.
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

# PLACEHOLDER: replace with sourced ECUK space-heating-only gas figure (GB).
ECUK_ANNUAL_GAS_HEAT_TWH = 300.0
ECUK_ANCHOR_STATUS = "placeholder - replace with sourced ECUK space-heating value"


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
    out = {"updated": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
           "sources": {}}

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

    try:
        gas = fetch_gas_demand(days=WINDOW_DAYS + 40)
        target = gas["ldz_sum"]
        vals = sorted(target.values())
        print(f"gas diagnostics (LDZ sum): {len(target)} days, "
              f"{min(target)} to {max(target)}, min {vals[0]} max {vals[-1]} GWh")
        out["sources"]["gas"] = {"status": "ok",
                                 "last_good": max(target) if target else None,
                                 "meta": gas["_meta"]}
    except Exception:
        traceback.print_exc()
        gas = prev.get("_gas")
        out["sources"]["gas"] = {
            "status": "stale",
            "last_good": prev.get("sources", {}).get("gas", {}).get("last_good")}
        if not gas or "ldz_sum" not in gas:
            _write(out | {"error": "no gas data available"})
            return
        target = gas["ldz_sum"]

    nts = gas.get("nts_demand_actual", {})

    dd_idx = {d: i for i, d in enumerate(dd["dates"])}
    common = sorted(set(target) & set(dd_idx))[-WINDOW_DAYS:]
    if len(common) < 90:
        _write(out | {"error": f"only {len(common)} overlapping days"})
        return

    y = [target[d] for d in common]

    best = None
    for base in HDD_BASES:
        x = [dd["hdd"][str(base)][dd_idx[d]] for d in common]
        slope, intercept, r2 = ols(x, y)
        if best is None or r2 > best["r2"]:
            best = {"base_temp": base, "slope_GWh_per_HDD": round(slope, 1),
                    "intercept_GWh": round(intercept, 1), "r2": round(r2, 3),
                    "window_days": len(common), "target": "LDZ sum (buildings)"}
    base = str(best["base_temp"])
    hdd_series = [dd["hdd"][base][dd_idx[d]] for d in common]
    space_heat = [round(max(0.0, best["slope_GWh_per_HDD"] * h), 1)
                  for h in hdd_series]

    annual_space_twh = sum(space_heat) / 1000.0
    ratio = annual_space_twh / ECUK_ANNUAL_GAS_HEAT_TWH
    calibration = {
        "model_12m_gas_space_heat_TWh": round(annual_space_twh, 1),
        "ecuk_anchor_TWh": ECUK_ANNUAL_GAS_HEAT_TWH,
        "anchor_status": ECUK_ANCHOR_STATUS,
        "ratio": round(ratio, 3),
        "within_10pct": abs(ratio - 1.0) <= 0.10,
    }

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

    # winter context for summer visitors
    peak_i = max(range(len(space_heat) - 6),
                 key=lambda i: sum(space_heat[i:i + 7]))
    peak_week = {
        "week_ending": common[peak_i + 6],
        "space_heat_GWh": round(sum(space_heat[peak_i:peak_i + 7]), 0),
    }

    out.update({
        "regression": best,
        "calibration": calibration,
        "weekly": weekly,
        "peak_week": peak_week,
        "series": {
            "dates": common,
            "gas_GWh": [round(v, 1) for v in y],
            "nts_GWh": [nts.get(d) for d in common],
            "hdd": hdd_series,
            "space_heat_GWh": space_heat,
        },
        "ni_note": {
            "hdd_15_5_latest": dd["ni"]["hdd_15_5"][-1] if dd["ni"]["hdd_15_5"] else None,
            "note": ("NI is not on the GB NTS/LDZ feed. NI heating is "
                     "estimated annually from subnational consumption "
                     "statistics, scaled by NI degree days."),
        },
        "_dd": dd,
        "_gas": gas,
    })

    print("regression:", best, "| weekly:", weekly,
          "| calibration ratio:", calibration["ratio"],
          "| peak week:", peak_week)
    _write(out)


def _write(out):
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {OUT_PATH}")
    if "error" in out:
        print("ERROR:", out["error"])
        sys.exit(1)


if __name__ == "__main__":
    main()
