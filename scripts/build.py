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
from fetch_prices import fetch_gas_sap, fetch_elec_mid        # noqa: E402
from fetch_carbon import fetch_carbon_intensity               # noqa: E402
from fetch_electricity import fetch_daily_underlying_demand   # noqa: E402
from fetch_odh import fetch_odh                               # noqa: E402

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "docs", "data.json")
WINDOW_DAYS = 365
EST = " \u2020"   # marks a Causeway estimate - see site footnote


def _recency(status, last_good, lag_ok_days=7):
    """Downgrade an 'ok' source to 'lagging' if last_good is old.
    Fetch health and data recency are different facts."""
    if status == "ok" and last_good:
        try:
            age = (dt.date.today() - dt.date.fromisoformat(
                str(last_good)[:10])).days
            if age > lag_ok_days:
                return "lagging"
        except ValueError:
            pass
    return status
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
                 "electricity only (ambient heat not yet counted)." + EST),
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
                 "heat pumps not yet counted (understates ambient heat)." + EST),
    }

    # --- geothermal & ground-source panel --------------------------------------
    # All values TWh/yr useful heat, GB. Sources tagged; forecasts are
    # third-party pathways or explicitly-flagged Causeway derivations.
    # Revised Jul 2026 from capacity research. GSHP heat anchored on EGEC 2025
    # UK Country Update / Gonzalez Quiros et al. 2024: 1,430 GWhth/yr from
    # ~55,210 units, 847-861 MWth installed (2023 base year, sales-derived,
    # no later data published). Deep + mine water + open-loop district adds
    # ~0.05-0.1 TWh/yr (Gateshead 6 MWth, Eden 1.4 MWth ~1 GWh/yr,
    # Lanchester 3.6 MWth, Southampton no current data). EA 2024 note: only
    # ~30-38k of the ~55k units may be operational - hence range floor.
    GEO = {
        "today_gshp_TWh": 1.43,     # EGEC 2025 (2023 base); range 1.4-2.0
        "today_deep_TWh": 0.07,     # mine water + deep + open-loop district;
                                    # mid of 0.05-0.1 estimate
        "f2027_TWh": 1.7,           # 12-month trend: GSHP now ~1.3% of MCS HP
                                    # installs (413 of 30.6k H1 2025); modest
                                    # unit growth + Langarth/United Downs heat
        "f2031_TWh": 4.5,           # scenario: CCC 7th Carbon Budget pathway
                                    # (450k HP/yr by 2030) x assumed GSHP share
                                    # rising to ~5% + deep pipeline; range 3.5-6
        "f2050_TWh": 40.0,          # Project InnerSpace / REA / ARUP (Feb 2026):
                                    # 15 GWth ambition ~= ~40 TWh/yr heat
        "today_cool_TWh": 0.08,     # ATES ~8 MWth cold (11 systems, Jackson
                                    # et al. 2024) + Southampton hist. 7-8 GWh
                                    # + unmeasured reversible GSHP; range
                                    # 0.05-0.1 - no national statistic exists
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
        "benchmark": ("Benchmark (EGEC Geothermal Market Report 2025): "
                      "Europe's 2.55 million geothermal heat pumps "
                      "delivered 88 TWh of heat in 2025. Sweden alone sold "
                      "26,785 units last year - the UK sold 4,070, with "
                      "twelve times Sweden's population."),
        "tags": {
            "today": "GSHP 1.43 TWh/yr: EGEC 2025 UK Country Update "
                     "(~55,210 units, 847-861 MWth, 2023 base) + ~0.07 "
                     "TWh/yr deep/mine/open-loop district (Gateshead 6 MWth, "
                     "Eden 1.4 MWth, Lanchester; Southampton no current "
                     "data). Range 1.4-2.0" + EST,
            "forecast_2027": "Trend: 4,070 UK GHP units sold in 2025 + 4 "
                             "new large closed-loop systems commissioned "
                             "(EGEC GMR 2025; MCS-certified subset far "
                             "smaller) + Langarth/United Downs pipeline" + EST,
            "forecast_2031": "Scenario: CCC Seventh Carbon Budget pathway "
                             "(450k HP/yr by 2030) x rising GSHP share + "
                             "deep pipeline (~11 UK geothermal DH systems in "
                             "development, EGEC GMR 2025) - Causeway "
                             "derivation, range 3.5-6" + EST,
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
                 "oil/bio/network/solid prices are estimates" + EST)

    GSHP_SPF = 3.24   # Energy Systems Catapult in-situ GSHP average
    ASHP_SPF = 2.80   # ESC Electrification of Heat median
    PASSIVE_COOL_COP = 20.0  # illustrative mid-range of 15-30
    GEO_NETWORK_SCOP = 5.0   # networked geothermal (shared ambient loop)

    p = PRICES_P_PER_KWH
    household = [
        {"route": "Gas boiler", "p_per_useful_kwh":
            round(p["gas"] / EFF["gas"], 1),
         "basis": "cap gas rate / 0.835 in-situ efficiency"},
        {"route": "Oil boiler", "p_per_useful_kwh":
            round(p["oil"] / EFF["oil"], 1),
         "basis": "est. kerosene / 0.82" + EST},
        {"route": "Resistive electric", "p_per_useful_kwh":
            round(p["elec"], 1),
         "basis": "cap electricity rate, COP 1"},
        {"route": "Air-source heat pump", "p_per_useful_kwh":
            round(p["elec"] / ASHP_SPF, 1),
         "basis": "cap electricity / SPF 2.80 (ESC field data)"},
        {"route": "Ground-source / geothermal", "p_per_useful_kwh":
            round(p["elec"] / GSHP_SPF, 1),
         "basis": "cap electricity / SPF 3.24 (ESC field data)"},
        {"route": "Geothermal heat/cool network", "p_per_useful_kwh":
            round(p["elec"] / GEO_NETWORK_SCOP, 1),
         "basis": "cap electricity / SCOP 5.0 (networked ambient loop, "
                  "shared boreholes/aquifer)" + EST},
        {"route": "Passive ground cooling", "p_per_useful_kwh":
            round(p["elec"] / PASSIVE_COOL_COP, 1),
         "basis": "cap electricity / COP ~20 (circulation only)" + EST},
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
    bill_heat = round(bill["gas"] + bill["oil"] + bill["electric_heat"]
                      + bill["bio_other"] + bill["heat_networks"]
                      + bill["solid"], 0)
    bill_cool = bill["cooling"]

    # 3) what-if: same useful heat & cool delivered via geothermal networks
    useful_heat_wk = (useful["gas_space"] + useful["gas_dhw"] + useful["oil"]
                      + useful["bio_other"] + useful["solid"]
                      + useful["heat_networks"] + useful["elec_resistive"]
                      + useful["hp_electricity"] + useful["hp_ambient"])
    whatif_heat_m = _cost_m(useful_heat_wk / GEO_NETWORK_SCOP, p["elec"])
    whatif_cool_m = _cost_m(useful["cooling_delivered"] / PASSIVE_COOL_COP,
                            p["elec"])
    whatif = {
        "useful_heat_GWh": round(useful_heat_wk, 0),
        "useful_cool_GWh": useful["cooling_delivered"],
        "cost_Mgbp": round(whatif_heat_m + whatif_cool_m, 0),
        "heat_Mgbp": round(whatif_heat_m, 0),
        "cool_Mgbp": round(whatif_cool_m, 0),
        "assumptions": ("Illustrative Causeway what-if: identical useful heat "
                        "and cooling delivered via geothermal networks - heat "
                        "at SCOP 5.0, cooling passively at COP ~20, current "
                        "capped electricity price. Running cost only; no "
                        "capex, network build, or price feedbacks." + EST),
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
        "national_week_heat_Mgbp": bill_heat,
        "national_week_cool_Mgbp": bill_cool,
        "national_week_total_Mgbp": round(sum(bill.values()), 0),
        "whatif_geothermal": whatif,
        "note": ("Running cost only: no capex, grants, or standing charges. "
                 "Domestic cap rates used as proxy for all sectors. "
                 "The electricity/gas price ratio embeds policy levies on "
                 "electricity; rebalancing would shift these comparisons "
                 "further toward heat pumps."),
    }

    # --- headline stats: indigenous share + 20% geothermal what-if -------------
    # Indigenous (UK-origin) shares of purchased energy - flagged estimates:
    #  gas ~38% UKCS (DUKES supply balance); oil ~30%; bio ~80% (domestic
    #  wood); solid ~20%; heat networks ~40% (gas-driven); electricity ~75%
    #  (net imports ~10% + imported-gas share of CCGT). Ambient/ground heat
    #  is 100% indigenous but is not purchased energy.
    INDIG = {"gas": 0.38, "oil": 0.30, "bio": 0.80, "solid": 0.20,
             "heat_networks": 0.40, "elec": 0.75}

    def _indig_pct(gas_gwh, oil_gwh, bio_gwh, solid_gwh, hn_gwh, elec_gwh,
                   total_gwh):
        if not total_gwh:
            return None
        e = (gas_gwh * INDIG["gas"] + oil_gwh * INDIG["oil"]
             + bio_gwh * INDIG["bio"] + solid_gwh * INDIG["solid"]
             + hn_gwh * INDIG["heat_networks"] + elec_gwh * INDIG["elec"])
        return round(100.0 * e / total_gwh, 0)

    total_in = sum(mix.values())
    # purchased basis (retained for methods note / continuity)
    indig_now = _indig_pct(mix["gas_space"] + mix["gas_dhw"], mix["oil"],
                           mix["bio_other"], mix["solid"],
                           mix["heat_networks"],
                           mix["elec_heat"] + mix["cooling"], total_in)

    # services basis: indigenous share of useful heat & cool DELIVERED.
    # Each service inherits the indigenous share of its energy input;
    # harvested ambient/ground heat counts at 100% (Eurostat/DUKES treat
    # it as renewable supply). Cooling's delivered multiple is leverage,
    # not input - it inherits its electricity's share.
    def _services_indig(u):
        total_u = sum(u.values()) - u["wasted_GWh"] if "wasted_GWh" in u             else sum(u.values())
        e = (u["gas_space"] * INDIG["gas"] + u["gas_dhw"] * INDIG["gas"]
             + u["oil"] * INDIG["oil"] + u["bio_other"] * INDIG["bio"]
             + u["solid"] * INDIG["solid"]
             + u["heat_networks"] * INDIG["heat_networks"]
             + u["elec_resistive"] * INDIG["elec"]
             + u["hp_electricity"] * INDIG["elec"]
             + u["hp_ambient"] * 1.0
             + u["cooling_delivered"] * INDIG["elec"])
        tot = (u["gas_space"] + u["gas_dhw"] + u["oil"] + u["bio_other"]
               + u["solid"] + u["heat_networks"] + u["elec_resistive"]
               + u["hp_electricity"] + u["hp_ambient"]
               + u["cooling_delivered"])
        return (round(100.0 * e / tot, 0), tot) if tot else (None, 0)

    indig_services_now, useful_total = _services_indig(useful)

    # what-if: 20% of heat & cooling service moved to geothermal networks
    R = 0.20
    heat_repl_elec = (useful_heat_wk * R) / GEO_NETWORK_SCOP
    cool_repl_elec = (useful["cooling_delivered"] * R) / PASSIVE_COOL_COP
    adj = {
        "gas": (mix["gas_space"] + mix["gas_dhw"]) * (1 - R),
        "oil": mix["oil"] * (1 - R),
        "bio": mix["bio_other"] * (1 - R),
        "solid": mix["solid"] * (1 - R),
        "hn": mix["heat_networks"] * (1 - R),
        "elec": (mix["elec_heat"] * (1 - R) + mix["cooling"] * (1 - R)
                 + heat_repl_elec + cool_repl_elec),
    }
    new_total = sum(adj.values())
    indig_20 = _indig_pct(adj["gas"], adj["oil"], adj["bio"], adj["solid"],
                          adj["hn"], adj["elec"], new_total)

    # services-basis what-if: the shifted fifth of heat is delivered as
    # (1/SCOP) grid electricity + (1-1/SCOP) harvested ground heat; the
    # shifted fifth of cooling as near-passive (1/COP elec + leverage
    # treated as ground-enabled, indigenous)
    heat_services = (useful["gas_space"] + useful["gas_dhw"] + useful["oil"]
                     + useful["bio_other"] + useful["solid"]
                     + useful["heat_networks"] + useful["elec_resistive"]
                     + useful["hp_electricity"] + useful["hp_ambient"])
    cool_services = useful["cooling_delivered"]
    kept = {k: useful[k] * (1 - R) for k in
            ("gas_space", "gas_dhw", "oil", "bio_other", "solid",
             "heat_networks", "elec_resistive", "hp_electricity",
             "hp_ambient", "cooling_delivered")}
    e_kept = (kept["gas_space"] * INDIG["gas"] + kept["gas_dhw"] * INDIG["gas"]
              + kept["oil"] * INDIG["oil"] + kept["bio_other"] * INDIG["bio"]
              + kept["solid"] * INDIG["solid"]
              + kept["heat_networks"] * INDIG["heat_networks"]
              + kept["elec_resistive"] * INDIG["elec"]
              + kept["hp_electricity"] * INDIG["elec"]
              + kept["hp_ambient"] * 1.0
              + kept["cooling_delivered"] * INDIG["elec"])
    shifted_heat = heat_services * R
    shifted_cool = cool_services * R
    e_shift = (shifted_heat * ((1 / GEO_NETWORK_SCOP) * INDIG["elec"]
                               + (1 - 1 / GEO_NETWORK_SCOP) * 1.0)
               + shifted_cool * ((1 / PASSIVE_COOL_COP) * INDIG["elec"]
                                 + (1 - 1 / PASSIVE_COOL_COP) * 1.0))
    tot_services = heat_services + cool_services
    indig_services_20 = round(100.0 * (e_kept + e_shift) / tot_services, 0)         if tot_services else None
    bill_20 = (_cost_m(adj["gas"], p["gas"]) + _cost_m(adj["oil"], p["oil"])
               + _cost_m(adj["bio"], p["bio"])
               + _cost_m(adj["solid"], p["solid"])
               + _cost_m(adj["hn"], p["heat_networks"])
               + _cost_m(adj["elec"], p["elec"]))
    headlines = {
        "purchased_GWh": round(total_in, 0),
        "indigenous_pct": indig_services_now,        # services basis (hero)
        "indigenous_basis": "services",
        "indigenous_purchased_pct": indig_now,       # purchased basis (methods)
        "whatif_20pct_geothermal": {
            "purchased_GWh": round(new_total, 0),
            "indigenous_pct": indig_services_20,     # services basis (hero)
            "indigenous_purchased_pct": indig_20,
            "bill_Mgbp": round(bill_20, 0),
        },
        "indig_note": ("Indigenous share is measured on a SERVICES basis: "
                       "the UK-origin share of useful heat and cooling "
                       "delivered. Each service inherits the origin of its "
                       "energy input (gas ~38% UKCS, electricity ~75%, "
                       "others flagged estimates" + EST + "); harvested "
                       "ambient/ground heat counts as 100% indigenous, "
                       "consistent with Eurostat/DUKES renewable-supply "
                       "accounting. Cooling's delivered multiple inherits "
                       "its electricity's share - thermodynamic leverage is "
                       "not an energy origin. On the purchased-energy basis "
                       "the shares are lower and barely move with "
                       "geothermal, because ground heat is never purchased: "
                       "that is the point. 20% what-if: one-fifth of heat "
                       "via SCOP-5 networks (80% ground heat), one-fifth of "
                       "cooling near-passive at COP 20" + EST + "."),
    }

    # --- daily heat spark gap (wholesale basis; optional feeds) ----------------
    spark = None
    try:
        sap = fetch_gas_sap()
        mid = fetch_elec_mid()
        gas_heat = sap["gbp_per_mwh"] / EFF["gas"]
        hp_heat = mid["gbp_per_mwh"] / GSHP_SPF
        spark = {
            "date": max(sap["date"], mid["date"]),
            "gas_boiler_heat_gbp_mwh": round(gas_heat, 1),
            "gshp_heat_gbp_mwh": round(hp_heat, 1),
            "gap_gbp_mwh": round(gas_heat - hp_heat, 1),
            "basis": ("Wholesale daily: gas SAP / 0.835 boiler efficiency vs "
                      "electricity market index / SPF 3.24. Commodity cost "
                      "only - excludes network, policy and supply costs."),
        }
        out["sources"]["prices"] = {"status": "ok", "last_good": spark["date"]}
    except Exception:
        traceback.print_exc()
        spark = (prev.get("spark") or None)
        out["sources"]["prices"] = {
            "status": "stale" if spark else "unavailable",
            "last_good": spark.get("date") if spark else None}

    # --- Northern Ireland summary ----------------------------------------------
    # NI is on separate gas (mutual networks, no GB LDZ) and electricity (SEM)
    # systems - the live GB feeds above do not cover it.
    NI_ANNUAL_HEAT_TWH = 14.0   # Causeway estimate - refine from DfE
                                # 'Energy in Northern Ireland'
                                # Oil share sourced: NISRA CHS 2024/25
    ni_hdd = dd["ni"]["hdd_15_5"]
    ni_wk_hdd = round(sum(ni_hdd[-7:]), 1) if len(ni_hdd) >= 7 else None
    ni_12m = sum(ni_hdd[-365:]) if len(ni_hdd) >= 300 else None
    ni_f = (sum(ni_hdd[-7:]) / ni_12m) if ni_12m else 0.0
    ni_week_heat = NI_ANNUAL_HEAT_TWH * 1000.0 * (0.8 * ni_f + 0.2 * f_flat)
    ni_panel = {
        "week_hdd": ni_wk_hdd,
        "week_heat_GWh_est": round(ni_week_heat, 0),
        "annual_TWh_est": NI_ANNUAL_HEAT_TWH,
        "est_mark": True,
        "oil_share_note": ("just over 60% of NI homes heat with oil, "
                           "gas 36% and rising (NISRA CHS 2024/25)"),
        "why_separate": ("NI runs on separate gas and electricity systems "
                         "(no GB LDZ, SEM market), so the live GB feeds "
                         "on this page do not cover it - NI is estimated "
                         "from annual statistics shaped by NI degree days."),
    }

    # --- carbon layer -----------------------------------------------------------
    # Combustion factors: DESNZ GHG conversion factors 2025, gross CV,
    # gCO2e/kWh fuel: natural gas ~183, kerosene ~247, coal ~345.
    # Bioenergy combustion counted at 0 (biogenic convention) - supply-chain
    # emissions excluded and noted. Heat networks assumed gas-fired (†).
    # Electricity: live GB grid intensity (NESO Carbon Intensity API,
    # trailing-7-day mean of half-hourly actuals).
    CF = {"gas": 183.0, "oil": 247.0, "solid": 345.0, "bio": 0.0,
          "heat_networks": 183.0}
    carbon = None
    try:
        ci = fetch_carbon_intensity(days=7)
        grid_ci = ci["g_per_kwh"]
        out["sources"]["carbon"] = {"status": "ok", "last_good": ci["to"]}
    except Exception:
        traceback.print_exc()
        prev_c = prev.get("carbon") or {}
        grid_ci = prev_c.get("grid_ci_g_per_kwh")
        out["sources"]["carbon"] = {
            "status": "stale" if grid_ci else "unavailable",
            "last_good": prev.get("sources", {}).get("carbon", {}).get("last_good")}
    if grid_ci:
        # weekly emissions, tonnes CO2e = GWh x g/kWh
        em = {
            "gas": (mix["gas_space"] + mix["gas_dhw"]) * CF["gas"],
            "oil": mix["oil"] * CF["oil"],
            "bio_other": mix["bio_other"] * CF["bio"],
            "solid": mix["solid"] * CF["solid"],
            "heat_networks": mix["heat_networks"] * CF["heat_networks"],
            "elec_heat": mix["elec_heat"] * grid_ci,
            "cooling": mix["cooling"] * grid_ci,
        }
        em_heat = sum(v for k, v in em.items() if k != "cooling")
        em_total = sum(em.values())
        # what-if: same 20% shift as the cost what-if
        em_removed = R * (em["gas"] + em["oil"] + em["bio_other"]
                          + em["solid"] + em["heat_networks"]
                          + em["elec_heat"] + em["cooling"])
        em_added = (heat_repl_elec + cool_repl_elec) * grid_ci
        # per useful kWh, g:
        routes = [
            {"route": "Gas boiler", "g_per_useful_kwh":
                round(CF["gas"] / EFF["gas"], 0)},
            {"route": "Oil boiler", "g_per_useful_kwh":
                round(CF["oil"] / EFF["oil"], 0)},
            {"route": "Resistive electric", "g_per_useful_kwh":
                round(grid_ci, 0)},
            {"route": "Air-source heat pump", "g_per_useful_kwh":
                round(grid_ci / ASHP_SPF, 0)},
            {"route": "Ground-source / geothermal", "g_per_useful_kwh":
                round(grid_ci / GSHP_SPF, 0)},
            {"route": "Geothermal heat/cool network", "g_per_useful_kwh":
                round(grid_ci / GEO_NETWORK_SCOP, 0)},
        ]
        carbon = {
            "grid_ci_g_per_kwh": grid_ci,
            "week_kt": round(em_total / 1000.0, 0),
            "week_heat_kt": round(em_heat / 1000.0, 0),
            "week_cool_kt": round(em["cooling"] / 1000.0, 0),
            "whatif_20pct_kt": round((em_total - em_removed + em_added)
                                     / 1000.0, 0),
            "whatif_saving_kt": round((em_removed - em_added) / 1000.0, 0),
            "routes_g_per_useful_kwh": routes,
            "note": ("Combustion factors: DESNZ GHG conversion factors 2025 "
                     "(gas ~183, kerosene ~247, coal ~345 gCO2e/kWh). "
                     "Bioenergy counted at zero combustion emissions "
                     "(biogenic convention; supply chain excluded). Heat "
                     "networks assumed gas-fired" + EST + ". Electricity at "
                     "the live GB grid intensity (NESO Carbon Intensity API, "
                     "7-day mean) - so the heat-pump rows fall every year "
                     "the grid decarbonises, while combustion never does."),
        }

    # --- observed cooling: demand vs delivery (CDD saturation analysis) --------
    # Summer daily underlying electricity demand (NESO ND + embedded solar +
    # wind reconstructed) binned by CDD(18). Low-bin slope extrapolated
    # linearly = latent cooling demand; observed bin means = delivered.
    # Divergence = installed-capacity saturation, measured not assumed.
    # DOES NOT yet replace the ECUK-shaped cooling in the bill/carbon chain -
    # reconciliation over a full summer first.
    cooling_observed = None
    try:
        this_year = dt.date.today().year
        elec = fetch_daily_underlying_demand([this_year - 1, this_year])
        out["sources"]["electricity"] = {
            "status": _recency("ok", max(elec), lag_ok_days=7),
            "last_good": max(elec),
            "note": "NESO demand publishes on a lag; historic file "
                    "refreshed periodically, update feed ~daily"}
        # summer subset (May-Sep), weekend-adjusted
        cdd_by_date = {d_: dd["cdd"][COOL_BASE][dd_idx[d_]]
                       for d_ in elec if d_ in dd_idx}
        summer = [d_ for d_ in cdd_by_date
                  if 5 <= int(d_[5:7]) <= 9]
        if len(summer) >= 60:
            # demean within (month, weekend-class) cells: hot-vs-cool
            # contrasts are made within the same month, removing the
            # holiday/seasonal baseline confound (Aug demand is depressed
            # exactly when CDD is highest)
            cells = {}
            for d_ in summer:
                dtd = dt.date.fromisoformat(d_)
                key = (d_[5:7], dtd.weekday() >= 5)
                cells.setdefault(key, []).append(d_)
            anomaly = {}
            for key, days in cells.items():
                if len(days) < 4:
                    continue
                mean = sum(elec[d_] for d_ in days) / len(days)
                for d_ in days:
                    anomaly[d_] = elec[d_] - mean
            # bin anomalies by CDD
            bins = {}
            for d_, v in anomaly.items():
                c = cdd_by_date[d_]
                b = 0 if c == 0 else min(5, int(c) + 1)
                bins.setdefault(b, []).append(v)
            bin_mean = {b: sum(v) / len(v) for b, v in bins.items()
                        if len(v) >= 3}
            if 0 in bin_mean and len(bin_mean) >= 3:
                base = bin_mean[0]
                curve = {b: round(m - base, 1)
                         for b, m in sorted(bin_mean.items()) if b > 0}
                bin_n = {b: len(v) for b, v in bins.items()}
                # low-CDD slope for the latent line; guard against a noisy
                # or negative first bin by using the best-fit through the
                # first two populated bins forced through the origin
                lows = [(b - 0.5, curve[b]) for b in sorted(curve)[:2]]
                num = sum(x * y for x, y in lows)
                den = sum(x * x for x, y in lows)
                slope = num / den if den else 0.0
                slope_ok = slope > 0
                wk_deliv = 0.0
                wk_latent = 0.0
                for d_ in wk:
                    c = dd["cdd"][COOL_BASE][dd_idx[d_]]
                    b = 0 if c == 0 else min(5, int(c) + 1)
                    wk_deliv += max(0.0, curve.get(
                        b, curve.get(max(curve), 0.0))) if b > 0 else 0.0
                    wk_latent += slope * c if slope_ok else 0.0
                cooling_observed = {
                    "response_curve_GWh_per_day": curve,
                    "bin_days": {str(b): bin_n.get(b, 0)
                                 for b in sorted(bin_mean)},
                    "latent_slope_GWh_per_CDD": round(slope, 1),
                    "latent_slope_reliable": slope_ok,
                    "week_delivered_GWh": round(wk_deliv, 0),
                    "week_latent_GWh": round(max(wk_latent, wk_deliv), 0),
                    "week_unmet_GWh": round(max(0.0, wk_latent - wk_deliv), 0)
                        if slope_ok else None,
                    "summer_days_used": len(anomaly),                    "summer_days_used": len(summer),
                    "note": ("Observed cooling electricity from summer daily "
                             "underlying demand (NESO ND + embedded solar/"
                             "wind reconstructed), demeaned within month and "
                             "weekend class to remove the holiday/seasonal "
                             "baseline, then binned by cooling degree days. "
                             "Flattening at high CDD indicates capacity and "
                             "behavioural saturation. Latent demand "
                             "extrapolates the low-CDD slope linearly" + EST +
                             ". Not yet used in the bill or carbon figures, "
                             "which remain ECUK-anchored pending a full "
                             "summer of reconciliation."),
                }
    except Exception:
        traceback.print_exc()
        cooling_observed = prev.get("cooling_observed")
        out["sources"]["electricity"] = {
            "status": "stale" if cooling_observed else "unavailable",
            "last_good": prev.get("sources", {}).get("electricity", {}).get("last_good")}

    # --- tier 3: the comfort deficit (latent cooling in unequipped stock) ------
    # The observed curve above only sees buildings that HAVE cooling. This
    # tier estimates the sweltering remainder. Anchors (sourced): <5% of UK
    # homes have AC (CCC; NESO ~3%); EHS 2022-23 ~11% of households report
    # overheating (low case); CCC "over half at risk" (high case); ~90% of
    # England's hospital buildings vulnerable to overheating (UKHACC); ONS
    # 3,271 excess deaths in the 2022 heat-periods; ONS hot-day productivity
    # loss ~GBP 1.2bn/yr average (GBP 5.3bn peak 2020).
    # Judgement constants (all †): central overheating fraction, per-dwelling
    # and per-m2 thermal response per degree-hour, uncooled non-domestic area.
    UK_DWELLINGS_M = 29.9          # MHCLG-derived UK total, millions
    AC_PENETRATION = 0.05          # CCC/NESO: <5% of homes
    F_OVERHEAT = {"low": 0.11, "central": 0.25, "high": 0.50}  # EHS / † / CCC
    KWH_PER_DWELLING_ODH = 0.2     # † kWh thermal per degC.h per dwelling
                                   #   (~UA 200 W/K effective cooled zone)
    NONDOM_UNCOOLED_MM2 = 190.0    # † Mm2 comfort space uncooled: education
                                   #   ~72 + health ~45 + share of offices/
                                   #   other (BEES floor areas x † fractions)
    WH_PER_M2_ODH = 3.0            # † Wh thermal per m2 per degC.h
    GROUND_COOL_COP = 20.0         # passive/free ground cooling †
    AIR_COOL_EER = 3.5             # typical air-con delivery

    comfort_deficit = None
    try:
        odh = fetch_odh(days=14)
        odh_days = sorted(odh["daily"])[-7:]
        odh_week = round(sum(odh["daily"][d_] for d_ in odh_days), 1)
        out["sources"]["overheating"] = {"status": "ok",
                                         "last_good": odh_days[-1]}
        scen = {}
        for name, f in F_OVERHEAT.items():
            n_dw = UK_DWELLINGS_M * 1e6 * f * (1 - AC_PENETRATION)
            dom_gwh = n_dw * KWH_PER_DWELLING_ODH * odh_week / 1e6
            nd_gwh = (NONDOM_UNCOOLED_MM2 * 1e6 * WH_PER_M2_ODH
                      * odh_week / 1e9)
            scen[name] = {
                "dwellings_M": round(n_dw / 1e6, 1),
                "latent_thermal_GWh": round(dom_gwh + nd_gwh, 0),
            }
        central = scen["central"]["latent_thermal_GWh"]
        comfort_deficit = {
            "odh26_week_degC_h": odh_week,
            "threshold_c": odh["threshold_c"],
            "scenarios": scen,
            "elec_if_ground_GWh": round(central / GROUND_COOL_COP, 1),
            "elec_if_air_GWh": round(central / AIR_COOL_EER, 1),
            "context": {
                "ac_penetration_note": "fewer than 5% of UK homes have air "
                    "conditioning (CCC; NESO ~3%)",
                "hospitals_note": "~90% of England's hospital buildings are "
                    "vulnerable to overheating (UKHACC); NHS overheating "
                    "incidents 5,554 in 2021-22",
                "health_note": "3,271 excess deaths in the England & Wales "
                    "2022 heat-periods (ONS/UKHSA)",
                "productivity_note": "hot days cost GB ~GBP 1.2bn/yr in lost "
                    "output on average, GBP 5.3bn in 2020 (ONS)",
            },
            "tier_bars": ({
                "t1_delivered_th_GWh": round(
                    cooling_observed["week_delivered_GWh"] * AIR_COOL_EER, 0),
                "t2_unmet_th_GWh": round(
                    (cooling_observed.get("week_unmet_GWh") or 0)
                    * AIR_COOL_EER, 0),
                "t3_low_GWh": scen["low"]["latent_thermal_GWh"],
                "t3_central_GWh": scen["central"]["latent_thermal_GWh"],
                "t3_high_GWh": scen["high"]["latent_thermal_GWh"],
            } if cooling_observed else None),
            "utes": {
                # if the central tier-3 load were ground-served, the rejected
                # heat (load + pump input) banks in the store; UTES round-trip
                # thermal recovery ~70% (ATES literature range 50-80%) †
                "round_trip": 0.7,
                "summer_banked_GWh": round(
                    central * (1 + 1 / GROUND_COOL_COP), 0),
                "winter_recovered_GWh": round(
                    central * (1 + 1 / GROUND_COOL_COP) * 0.7, 0),
            },
            "note": ("The observed curve above only sees buildings that have "
                     "cooling. This tier estimates the sweltering remainder: "
                     "overheating-degree-hours above the CIBSE 26 degC "
                     "threshold (population-weighted, all hours - no "
                     "occupancy model" + EST + ") x the unequipped stock at "
                     "risk (low: EHS 11% self-reported; central 25%" + EST +
                     "; high: CCC over-half-at-risk) x per-dwelling and "
                     "per-m2 thermal response" + EST + ". Meeting the "
                     "central load via passive ground cooling would draw "
                     "~1/6 the electricity of air-source compressors - and "
                     "the rejected heat recharges the ground for winter."),
        }
    except Exception:
        traceback.print_exc()
        comfort_deficit = prev.get("comfort_deficit")
        out["sources"]["overheating"] = {
            "status": "stale" if comfort_deficit else "unavailable",
            "last_good": prev.get("sources", {}).get("overheating", {}).get("last_good")}

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
        "headlines": headlines,
        "spark": spark,
        "ni_panel": ni_panel,
        "why_heat": {
            # Annual, UK, calendar 2024. Sourced anchors: ECUK 2025 (final
            # energy 128.1 mtoe = ~1,490 TWh; transport 54.0 mtoe = 628 TWh,
            # 42%, 93% petroleum); DESNZ 2024 provisional GHG by sector
            # (transport the largest emitting sector); DUKES import
            # dependency; dashboard INDIG origin shares. Service-level
            # allocations are Causeway derivations - all daggered.
            "year": 2024,
            "services_TWh": {"heat": 630, "transport": 628,
                             "power_other": 235},
            "cost_bn": {"heat": 42, "transport": 70, "power_other": 60},
            "imported_TWh": {"heat": 233, "transport": 415,
                             "power_other": 59},
            "emissions_Mt": {"heat": 125, "transport": 115,
                             "power_other": 30},
            "note": ("Annual, calendar 2024. Sourced: UK final energy "
                     "consumption 1,490 TWh and transport 628 TWh (42%, 93% "
                     "petroleum) - DESNZ ECUK 2025; transport the largest "
                     "emitting sector - DESNZ 2024 provisional. Derived" +
                     EST + ": heat = heat end uses across homes, services "
                     "and industry (~630 TWh - the largest single use of "
                     "energy in Britain); power = non-heat electricity; "
                     "costs from typical 2024 retail/pump prices x volumes; "
                     "imports allocate each service's inputs by the origin "
                     "shares used site-wide (gas ~38% UK, electricity ~75%, "
                     "petroleum ~30%); emissions allocate combustion by "
                     "service and grid CO2 by electricity use. Non-energy "
                     "emissions (agriculture, waste, F-gases) excluded. "
                     "The pattern the four pies show: heat is the biggest "
                     "energy service, the cheapest per unit (untaxed "
                     "fossil fuel), a major import driver, and a top-tier "
                     "emitter - which is why it is the transition's "
                     "biggest prize."),
        },
        "carbon": carbon,
        "cooling_observed": cooling_observed,
        "comfort_deficit": comfort_deficit,
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
    print("headlines:", headlines)
    print("spark:", spark)
    print("ni_panel:", ni_panel)
    print("carbon:", carbon)
    print("cooling_observed:", cooling_observed)
    print("comfort_deficit:", comfort_deficit)
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
