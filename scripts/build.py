"""Build data.json: fetch feeds, regress LDZ (buildings) gas on HDD, compute
the weekly GB heat & cooling mix, write output.

Gas space heating: live regression (LDZ offtake vs HDD).
Other fuels & cooling: level from ECUK 2025 End Use tables (calendar 2024,
UK, rev. 20 Apr 2026), weekly shape from HDD (heating) / CDD base 18
(cooling); DHW components flat. Cooling & ventilation split 50% flat
ventilation / 50% CDD-shaped cooling (stated assumption).

Calibration anchor: ECUK U3 domestic gas space heating 189.6 TWh + U5
services gas heating 68.5 TWh = 258.1 TWh, GB-adjusted, weather-normalised.
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
COOL_BASE = "18.0"

ECUK_UK_GAS_SPACE_HEAT_TWH_2024 = 258.1
GB_SHARE_OF_UK_GAS_HEAT = 0.985   # NI excluded from GB LDZ; estimate
ECUK_ANCHOR_STATUS = ("ECUK 2025 U3+U5, calendar 2024, UK; GB share and "
                      "weather normalisation applied")

# UK TWh, ECUK 2025 End Use tables (calendar 2024). space = HDD-shaped,
# dhw/flat = constant, cool = 50% flat + 50% CDD-shaped.
ANNUAL_TWH = {
    "gas_dhw":       64.7,   # U3 55.6 + U5 hot water 9.1
    "elec_space":    21.2,   # U3 13.7 + U5 heating 7.5
    "elec_dhw":       5.4,   # U3 3.8 + U5 1.6
    "oil_space":     45.7,   # U3 21.9 + U5 23.8
    "oil_dhw":        5.3,
    "bio_space":     23.8,   # U3 bio 12.1 + U5 'other' 11.7
    "bio_dhw":        3.5,
    "heat_networks":  6.2,   # U3 3.2 + U5 3.0
    "solid":          2.0,
    "cooling_vent":  10.4,   # U5 cooling & ventilation electricity
}


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
        dd = fetch_degree_days(days=940)  # covers calendar 2024 for anchor
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
    cdd_series = [dd["cdd"][COOL_BASE][dd_idx[d]] for d in common]

    # --- calibration (weather-normalised ECUK anchor) -------------------------
    annual_space_twh = sum(space_heat) / 1000.0
    hdd_all = dd["hdd"][base]
    hdd_2024 = sum(h for d_, h in zip(dd["dates"], hdd_all)
                   if d_.startswith("2024"))
    hdd_12m = sum(hdd_series)
    anchor_gb = ECUK_UK_GAS_SPACE_HEAT_TWH_2024 * GB_SHARE_OF_UK_GAS_HEAT
    anchor_scaled = anchor_gb * (hdd_12m / hdd_2024) if hdd_2024 else anchor_gb
    ratio = annual_space_twh / anchor_scaled
    calibration = {
        "model_12m_gas_space_heat_TWh": round(annual_space_twh, 1),
        "ecuk_anchor_TWh": round(anchor_scaled, 1),
        "anchor_raw_UK_2024_TWh": ECUK_UK_GAS_SPACE_HEAT_TWH_2024,
        "gb_share": GB_SHARE_OF_UK_GAS_HEAT,
        "hdd_2024": round(hdd_2024, 1),
        "hdd_trailing_12m": round(hdd_12m, 1),
        "anchor_status": ECUK_ANCHOR_STATUS,
        "ratio": round(ratio, 3),
        "within_10pct": abs(ratio - 1.0) <= 0.10,
    }

    # --- weekly gas headline ---------------------------------------------------
    wk = common[-7:]
    wk_i = [common.index(d) for d in wk]
    weekly = {
        "week_ending": wk[-1],
        "gas_total_GWh": round(sum(y[i] for i in wk_i), 0),
        "gas_space_heat_GWh": round(sum(space_heat[i] for i in wk_i), 0),
        "hdd_total": round(sum(hdd_series[i] for i in wk_i), 1),
        "cdd_total": round(sum(cdd_series[i] for i in wk_i), 1),
    }
    weekly["gas_baseline_GWh"] = round(
        weekly["gas_total_GWh"] - weekly["gas_space_heat_GWh"], 0)

    # --- weekly GB heat & cooling mix -----------------------------------------
    g = GB_SHARE_OF_UK_GAS_HEAT
    f_flat = 7.0 / 365.0
    f_h = (weekly["hdd_total"] / hdd_12m) if hdd_12m else 0.0
    cdd_12m = sum(cdd_series)
    f_c = (weekly["cdd_total"] / cdd_12m) if cdd_12m else 0.0
    A = {k: v * g * 1000.0 for k, v in ANNUAL_TWH.items()}  # GWh, GB

    mix = {
        "gas_space": weekly["gas_space_heat_GWh"],          # live estimate
        "gas_dhw": round(A["gas_dhw"] * f_flat, 0),
        "oil": round(A["oil_space"] * f_h + A["oil_dhw"] * f_flat, 0),
        "elec_heat": round(A["elec_space"] * f_h + A["elec_dhw"] * f_flat, 0),
        "bio_other": round(A["bio_space"] * f_h + A["bio_dhw"] * f_flat, 0),
        "heat_networks": round(A["heat_networks"] * f_h, 0),
        "solid": round(A["solid"] * f_h, 0),
        "cooling": round(A["cooling_vent"] * (0.5 * f_flat + 0.5 * f_c), 0),
    }
    combustion = (mix["gas_space"] + mix["gas_dhw"] + mix["oil"]
                  + mix["bio_other"] + mix["solid"])
    total = sum(mix.values())
    weekly_mix = {
        "components_GWh": mix,
        "total_GWh": round(total, 0),
        "combustion_share": round(combustion / total, 3) if total else None,
        "shape_factors": {"f_heating": round(f_h, 4),
                          "f_cooling": round(f_c, 4)},
        "note": ("Gas space heating is a live regression estimate; other "
                 "components are ECUK 2024 annual levels shaped by HDD/CDD. "
                 "Cooling & ventilation split 50% flat / 50% CDD-shaped "
                 "(assumption). Electric heating includes heat pump input "
                 "electricity only (ambient heat not yet counted)."),
    }

    # --- weekly useful heat & cool delivered (dual-bar basis) ------------------
    # Conversion factors, sourced/flagged:
    #  gas boiler in-situ 0.835 (RAP/field trials 82.5-85%); oil 0.82 (est.,
    #  older stock); bio 0.70 (est., stoves/boilers range 60-80%); solid 0.55
    #  (est.); heat networks 1.0 (ECUK 'heat' is delivered heat; upstream
    #  losses excluded); resistive electric 1.0.
    #  Heat pumps: domestic HP electricity 2.0 TWh/yr (ECUK 2025, 169 ktoe,
    #  2024; non-domestic HP excluded - understates). Blended SPF 2.8
    #  (Energy Systems Catapult EoH median ASHP 2.80; GSHP 3.24).
    #  Cooling: EER 3.0 (assumption) on the CDD-shaped half; ventilation
    #  counted at 1.0 (fan energy delivers a service, not multiplied).
    EFF = {"gas": 0.835, "oil": 0.82, "bio": 0.70, "solid": 0.55,
           "heat_networks": 1.0, "resistive": 1.0}
    HP_ELEC_TWH = 2.0
    HP_SPF = 2.8
    COOL_EER = 3.0

    HP_FLAT_SHARE = 0.15   # HP hot-water runs year-round (assumption)
    hp_elec_wk = HP_ELEC_TWH * g * 1000.0 * (
        (1 - HP_FLAT_SHARE) * f_h + HP_FLAT_SHARE * f_flat)
    hp_elec_wk = min(hp_elec_wk, mix["elec_heat"])       # cannot exceed segment
    resistive_wk = mix["elec_heat"] - hp_elec_wk
    hp_heat_wk = hp_elec_wk * HP_SPF
    hp_ambient_wk = hp_heat_wk - hp_elec_wk

    cool_flat = A["cooling_vent"] * 0.5 * f_flat          # ventilation, flat
    cool_shaped = A["cooling_vent"] * 0.5 * f_c           # true cooling
    cool_useful = cool_flat * 1.0 + cool_shaped * COOL_EER

    useful = {
        "gas_space": round(mix["gas_space"] * EFF["gas"], 0),
        "gas_dhw": round(mix["gas_dhw"] * EFF["gas"], 0),
        "oil": round(mix["oil"] * EFF["oil"], 0),
        "bio_other": round(mix["bio_other"] * EFF["bio"], 0),
        "solid": round(mix["solid"] * EFF["solid"], 0),
        "heat_networks": round(mix["heat_networks"] * EFF["heat_networks"], 0),
        "elec_resistive": round(resistive_wk, 0),
        "hp_electricity": round(hp_elec_wk, 0),
        "hp_ambient": round(hp_ambient_wk, 0),
        "cooling_delivered": round(cool_useful, 0),
    }
    weekly_useful = {
        "components_GWh": useful,
        "total_GWh": round(sum(useful.values()), 0),
        "wasted_GWh": round(
            (mix["gas_space"] + mix["gas_dhw"]) * (1 - EFF["gas"])
            + mix["oil"] * (1 - EFF["oil"])
            + mix["bio_other"] * (1 - EFF["bio"])
            + mix["solid"] * (1 - EFF["solid"]), 0),
        "factors": {"boiler_gas": EFF["gas"], "oil": EFF["oil"],
                    "bio": EFF["bio"], "solid": EFF["solid"],
                    "hp_spf": HP_SPF, "hp_elec_TWh_yr": HP_ELEC_TWH,
                    "cool_eer": COOL_EER},
        "note": ("Useful basis: combustion derated by in-situ efficiencies; "
                 "heat pumps multiplied by SPF with ambient harvest shown "
                 "separately; cooling multiplied by EER on the weather-driven "
                 "half. Heat-network upstream losses excluded. Non-domestic "
                 "heat pumps not yet counted (understates ambient heat)."),
    }

    # --- geothermal & ground-source panel --------------------------------------
    # All values TWh/yr useful heat, GB. Sources tagged; forecasts are
    # third-party pathways or explicitly-flagged Causeway derivations.
    GEO = {
        "today_gshp_TWh": 2.0,      # est. range 1.5-2.5: GSHP stock ~50k units
                                    # (MCS cumulative + legacy) x typical output;
                                    # consistent with ECUK 2025 HP electricity
        "today_deep_TWh": 0.05,     # Southampton + Gateshead (6 MW) + Eden etc,
                                    # capacity-derived estimates
        "f2027_TWh": 2.5,           # 12-month trend: MCS 2025 installs +34% on
                                    # 2024 record 58,176; GSHP ~2-3% share
        "f2031_TWh": 4.5,           # scenario: CCC 7th Carbon Budget pathway
                                    # (450k HP/yr by 2030) x assumed GSHP share
                                    # rising to ~5% + deep pipeline; range 3.5-6
        "f2050_TWh": 40.0,          # Project InnerSpace / REA / ARUP (Feb 2026):
                                    # 15 GWth ambition ~= ~40 TWh/yr heat
        "today_cool_TWh": 0.1,      # est. range 0.05-0.2: reversible GSHP +
                                    # ATES (mostly London Chalk); no national
                                    # statistic exists - flagged estimate
    }
    geo_today = GEO["today_gshp_TWh"] + GEO["today_deep_TWh"]
    geo_week = geo_today * g * 1000.0 * (0.85 * f_h + 0.15 * f_flat)
    geo_cool_week = GEO["today_cool_TWh"] * g * 1000.0 * f_c
    heat_week_total = (mix["gas_space"] + mix["gas_dhw"] + mix["oil"]
                       + mix["elec_heat"] + mix["bio_other"]
                       + mix["heat_networks"] + mix["solid"])
    geothermal = {
        "week_GWh": round(geo_week, 0),
        "week_cool_GWh": round(geo_cool_week, 0),
        "cool_today_TWh": GEO["today_cool_TWh"],
        "week_share_of_heat": round(geo_week / heat_week_total, 4)
                              if heat_week_total else None,
        "annual_TWh": {
            "today": geo_today,
            "today_deep_only": GEO["today_deep_TWh"],
            "forecast_2027": GEO["f2027_TWh"],
            "forecast_2031": GEO["f2031_TWh"],
            "ambition_2050": GEO["f2050_TWh"],
        },
        "tags": {
            "today": "Estimate: ~50k GSHPs + named deep/mine schemes "
                     "(Southampton, Gateshead 6 MW, Eden); ECUK 2025 / "
                     "DUKES 2025 basis",
            "forecast_2027": "Trend: MCS installs 2025 +34% on 2024 record "
                             "(58,176); GSHP ~2-3% of installs",
            "forecast_2031": "Scenario: CCC Seventh Carbon Budget pathway "
                             "(450k HP/yr by 2030) x rising GSHP share + "
                             "deep pipeline - Causeway derivation, range 3.5-6",
            "ambition_2050": "Project InnerSpace / REA / ARUP, Feb 2026: "
                             "15 GWth by 2050",
        },
    }

    # --- cost layer (4a): household p/kWh useful + national weekly bill --------
    # Ofgem price cap 1 Jul - 30 Sep 2026, GB direct-debit average, incl VAT
    # (announced 27 May 2026): electricity 26.11 p/kWh, gas 7.33 p/kWh.
    # UPDATE QUARTERLY (next: by 26 Aug 2026 for Oct-Dec).
    # Oil/bio/heat-network/solid unit prices are flagged estimates.
    PRICES_P_PER_KWH = {
        "gas": 7.33,            # Ofgem cap Q3 2026
        "elec": 26.11,          # Ofgem cap Q3 2026
        "oil": 7.2,             # est. kerosene ~75p/l / 10.35 kWh/l - confirm
        "bio": 7.5,             # est. wood pellet - confirm
        "heat_networks": 10.0,  # est. typical network tariff - confirm
        "solid": 6.0,           # est.
    }
    PRICE_TAG = ("Ofgem price cap 1 Jul-30 Sep 2026 (GB DD avg, incl VAT); "
                 "oil/bio/network/solid prices are flagged estimates")

    GSHP_SPF = 3.24   # Energy Systems Catapult in-situ GSHP average
    ASHP_SPF = 2.80   # ESC Electrification of Heat median
    PASSIVE_COOL_COP = 20.0  # illustrative mid-range of 15-30

    p = PRICES_P_PER_KWH
    household = [
        {"route": "Gas boiler", "p_per_useful_kwh":
            round(p["gas"] / EFF["gas"], 1),
         "basis": "cap gas rate / 0.835 in-situ efficiency"},
        {"route": "Oil boiler", "p_per_useful_kwh":
            round(p["oil"] / EFF["oil"], 1),
         "basis": "est. kerosene / 0.82 (estimate)"},
        {"route": "Resistive electric", "p_per_useful_kwh":
            round(p["elec"], 1),
         "basis": "cap electricity rate, COP 1"},
        {"route": "Air-source heat pump", "p_per_useful_kwh":
            round(p["elec"] / ASHP_SPF, 1),
         "basis": "cap electricity / SPF 2.80 (ESC field data)"},
        {"route": "Ground-source / geothermal", "p_per_useful_kwh":
            round(p["elec"] / GSHP_SPF, 1),
         "basis": "cap electricity / SPF 3.24 (ESC field data)"},
        {"route": "Passive ground cooling", "p_per_useful_kwh":
            round(p["elec"] / PASSIVE_COOL_COP, 1),
         "basis": "cap electricity / COP ~20 (circulation only)"},
    ]

    # national weekly bill: energy-in mix x unit prices (domestic cap as
    # proxy for all sectors - flagged simplification). GWh x p/kWh = £10k.
    def _cost_m(gwh, price):
        return gwh * price / 100.0  # GWh * p/kWh -> £m

    bill = {
        "gas": round(_cost_m(mix["gas_space"] + mix["gas_dhw"], p["gas"]), 0),
        "oil": round(_cost_m(mix["oil"], p["oil"]), 0),
        "electric_heat": round(_cost_m(mix["elec_heat"], p["elec"]), 0),
        "bio_other": round(_cost_m(mix["bio_other"], p["bio"]), 0),
        "heat_networks": round(_cost_m(mix["heat_networks"],
                                       p["heat_networks"]), 0),
        "solid": round(_cost_m(mix["solid"], p["solid"]), 0),
        "cooling": round(_cost_m(mix["cooling"], p["elec"]), 0),
    }
    cost = {
        "price_tag": PRICE_TAG,
        "household_p_per_useful_kwh": household,
        "gshp_vs_gas_boiler": {
            "gshp": round(p["elec"] / GSHP_SPF, 1),
            "gas_boiler": round(p["gas"] / EFF["gas"], 1),
            "gshp_cheaper": (p["elec"] / GSHP_SPF) < (p["gas"] / EFF["gas"]),
        },
        "national_week_Mgbp": bill,
        "national_week_total_Mgbp": round(sum(bill.values()), 0),
        "note": ("Running cost only: no capex, grants, or standing charges. "
                 "Domestic cap rates used as proxy for all sectors. "
                 "The electricity/gas price ratio embeds policy levies on "
                 "electricity; rebalancing would shift these comparisons "
                 "further toward heat pumps."),
    }

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
        "weekly_mix": weekly_mix,
        "weekly_useful": weekly_useful,
        "geothermal": geothermal,
        "cost": cost,
        "peak_week": peak_week,
        "series": {
            "dates": common,
            "gas_GWh": [round(v, 1) for v in y],
            "nts_GWh": [nts.get(d) for d in common],
            "hdd": hdd_series,
            "cdd": cdd_series,
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

    print("regression:", best)
    print("calibration:", calibration)
    print("weekly:", weekly)
    print("weekly_mix:", weekly_mix["components_GWh"],
          "total", weekly_mix["total_GWh"],
          "combustion", weekly_mix["combustion_share"])
    print("weekly_useful:", weekly_useful["components_GWh"],
          "total", weekly_useful["total_GWh"],
          "wasted", weekly_useful["wasted_GWh"])
    print("geothermal:", geothermal)
    print("cost:", {k: cost[k] for k in ("gshp_vs_gas_boiler","national_week_total_Mgbp")})
    print("peak week:", peak_week)
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
