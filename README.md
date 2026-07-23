# UK Heat Split — a weekly estimate of how Britain heats and cools itself

Most of Britain's heat still comes from burning gas, and a material share of
every unit burned never becomes useful heat. This site turns live grid data
into a weekly estimate of the GB heating and cooling energy split — the
energy volume, what it costs, what it emits, how much of it is UK-indigenous,
who is left sweltering without cooling at all, what geothermal (deep, mine
water, and ground source) supplies today and could supply next — and, at the
foot of the page, why heat is the energy transition's biggest prize.

**Live site:** https://causewaygt.github.io/uk-heatsplit/
**Full methodology:** [UK Heat Split: data sources and estimation methodology (PDF)](docs/uk-heatsplit-methodology.pdf)

Every live figure is a model estimate, not a measurement. Every figure resting
on Causeway judgement is marked † and is open to challenge at
contact@causewaygt.com.

## What the dashboard shows

- **Headlines** — four stats: energy purchased this week; the UK-indigenous
  share of heat and cooling delivered (services basis); the national bill
  split between heating and cooling; and heating & cooling emissions —
  alongside a what-if strip answering all four with 20% of heat and cooling
  moved to geothermal.
- **Trends** — a sparkline under each headline showing its weekly history,
  with a 1-week to 12-month window selector that also re-totals the
  headline figures themselves — actuals and the 20% what-if strip alike —
  so the 12-month view states the year's purchased energy, bill, emissions
  and the cumulative what-if saving (sums over complete live weeks;
  the indigenous share as an energy-weighted average). The what-if is
  overlaid in green on each sparkline; the shaded band is the forgone
  saving. Live weeks only: each point is computed with
  the same estimators as the headline, priced at the Ofgem cap in force
  that week and carboned at that week's mean grid intensity — no modelled
  back-cast. The window is bounded by the ~13 months the National Gas feed
  serves; a longer modelled series, visually distinguished, is planned.
- **Dual bars, same scale** — energy in (fuel and electricity purchased) vs
  useful heat and cooling delivered: combustion derated by in-situ boiler
  efficiencies, heat pumps credited with their harvested ambient heat,
  cooling with its delivered multiple.
- **Daily spark gap** — wholesale cost of useful heat via a gas boiler vs a
  ground-source heat pump, updated daily from the National Gas SAP and the
  Elexon market index.
- **What heat costs** — pence per useful kWh by route at current Ofgem cap
  rates, and the national weekly bill — priced by sector: each fuel's
  domestic share (ECUK) at the Ofgem cap, its services share at
  DESNZ QEP-anchored non-domestic rates†, standing charges excluded.
- **What heat emits** — weekly emissions with a heat/cool split, and gCO2e
  per useful kWh by route: combustion at fixed DESNZ factors (natural gas
  0.18296 kgCO2e/kWh, gross CV basis), electric routes at the live GB grid
  intensity (NESO Carbon Intensity API, 7-day mean) — so the heat-pump rows
  fall as the grid decarbonises while combustion never does.
- **Geothermal — now and next** — heat and cooling from geothermal this week,
  plus annual bars for today, 2027, 2031 and 2050, each tagged to its source.
  Today's heat is anchored on the EGEC 2025 UK Country Update (~1.43 TWh/yr
  from ~55,210 GSHP units, 2023 base) plus mine-water, deep and open-loop
  district schemes; the 2027 and 2031 bars carry the EGEC Geothermal Market
  Report 2025 evidence (4,070 UK unit sales, 4 new large closed-loop systems,
  ~11 UK district systems in development). A benchmark line sets the UK
  against Europe: 2.55 million geothermal heat pumps delivering 88 TWh in
  2025 — Sweden alone sold 26,785 units to the UK's 4,070.
- **The gas engine room** — daily gas offtake to the distribution zones
  (buildings) against the regression-estimated space-heating signal, with
  total NTS shown for context. The fit reports R², the residual standard
  error (the honest daily uncertainty), and the calibration ratio against the
  ECUK anchor with its ±10% publication gate.
- **Cooling: demand vs delivery, in three tiers** —
  *Tiers 1 & 2 (the equipped fleet):* an observed cooling response curve from
  half-hourly national electricity demand (NESO, embedded solar and wind
  reconstructed, centred within month and weekend class), binned by cooling
  degree days: what installed cooling delivers, and whether it saturates.
  A reconciliation diagnostic — a year-round regression of demand on
  heating and cooling degree days jointly, with the cooling base swept so
  the data chooses where conditioning starts — decomposes the gap between
  the observed response and the ECUK cooling & ventilation anchor into
  weather-driven and weather-flat parts (published, not yet in the bill).
  *Tier 3 (the comfort deficit):* the buildings with no cooling at all —
  overheating-degree-hours above the CIBSE 26°C threshold (population-
  weighted, live from hourly ERA5) × the unequipped stock at risk (bounded
  low/central/high from EHS self-reports to the CCC's over-half-at-risk),
  with the health and productivity context (ONS/UKHSA excess deaths, ONS
  hot-day output losses). A tier bar graphic sets the unserviced deficit
  against what the fleet delivered, and a seasonal-mirror graphic shows the
  geocooling dividend: rejected summer heat banked underground and ~70%
  recovered for winter heating (UTES round-trip, literature range 50–80%).
- **Northern Ireland** — a separate estimate: NI runs on its own gas and
  electricity systems, so the live GB feeds do not cover it. If the NI DfE
  geothermal licensing proposals proceed (consultation 2026; heat below
  100 m depth), the resulting register would be the UK's first mandatory
  geothermal data source, and this dashboard is designed to ingest it.
- **WHY HEAT?** — the zoom-out. Four annual pies place heat beside transport
  and power across energy services delivered (TWh), national spend (£bn),
  imported energy (TWh) and emissions (Mt CO2e). The pattern they show: heat
  is the largest energy service in Britain, the cheapest per unit (untaxed
  fossil fuel), a major import driver, and a top-tier emitter — which is why
  it is the transition's biggest prize.

## Method in one paragraph

Daily gas offtake to Britain's local distribution zones (LDZ — the network
serving homes and most businesses, excluding directly connected power
stations) is regressed against population-weighted GB heating degree days
(ERA5 reanalysis via Open-Meteo). The temperature-sensitive component is
attributed to space heating, following the published Watson et al. / Sansom
method; the trailing 12-month total is calibrated against the DESNZ ECUK
end-use tables, GB-adjusted and weather-normalised (current ratio ~1.10,
within the ±10% publication threshold). Other fuels and cooling take their
annual levels from ECUK 2025 (calendar 2024) shaped by heating/cooling degree
days. The indigenous share is measured on a services basis — each unit of
delivered heat or cooling inherits the UK-origin share of its energy input,
with harvested ambient/ground heat counting as 100% indigenous, consistent
with Eurostat/DUKES renewable-supply accounting. **The full technical
methodology — with equations, figures and a complete bibliography — is in
[docs/uk-heatsplit-methodology.pdf](docs/uk-heatsplit-methodology.pdf).**

## Estimates open to challenge

Sourced figures (Ofgem cap, ECUK anchors, DESNZ GHG factors, Energy Systems
Catapult SPFs, EGEC capacity and market data, NISRA heating shares, MCS
installations, EHS/CCC overheating prevalence, ONS/UKHSA health and
productivity data) are cited as such. Figures resting on Causeway judgement
are marked † on the site — the geothermal forecast scenario, several unit
prices, the cooling split and latent-demand extrapolation, the
comfort-deficit stock fractions and thermal-response coefficients, the UTES
round-trip, indigenous input-origin shares, the NI heat total, and the WHY
HEAT? service-level allocations. Challenge and input welcome:
**contact@causewaygt.com**.

## Data sources & licences

National Gas Transmission open data (demand and SAP publications, REST API;
derived public use and attribution confirmed with the operator, July 2026) ·
Contains BMRS data © Elexon Limited copyright and database right 2026 · NESO
Data Portal (demand) and NESO Carbon Intensity API, NESO Open Licence ·
Open-Meteo.com (CC BY 4.0) / Copernicus ERA5 (daily and hourly) · DESNZ ECUK,
DUKES and GHG conversion factors, MHCLG dwelling statistics, and NISRA
statistics, under the Open Government Licence v3.0 · EGEC 2025 UK Country
Update and EGEC Geothermal Market Report 2025, English Housing Survey, CCC
adaptation reporting, ONS/UKHSA heat mortality and productivity statistics
(cited). Full bibliography with DOIs in the methodology PDF.

## How it runs

A GitHub Actions cron (`.github/workflows/update.yml`) runs daily at 03:43
UTC: `scripts/build.py` pulls the feeds, fits the regressions, computes the
mix, costs, emissions, cooling tiers and headlines, and commits
`docs/data.json`; the static page (`docs/index.html`, Plotly) renders it.
Feed failures fall back to the last good values and are flagged on the page
(sources that publish on a lag show amber); build failures push a
notification. Site traffic is measured with GoatCounter (cookieless, no
personal data). No API keys required; fork-friendly.

The daily commit of `docs/data.json` also carries the weekly trend history
(capped at 60 weeks), so the git log doubles as its backup: each run appends
the newest complete week, recomputes the two most recent against feed
revisions, and leaves older weeks frozen as first published.

Anchor constants are refreshed on a maintenance calendar: Ofgem cap
quarterly (one row added to the cap-history table in `build.py`, so past
weeks keep the cap that was in force); ECUK/DUKES and the WHY HEAT? panel
annually; the geothermal panel annually on MCS/EGEC release.

## Repository layout

```
docs/
  index.html                      the dashboard (static; Plotly)
  data.json                       written daily by the workflow
  uk-heatsplit-methodology.pdf    full technical methodology statement
scripts/
  build.py                        pulls feeds, fits, computes, writes data.json
  fetch_*.py                      per-source fetchers
.github/workflows/update.yml      daily cron
```

## Versioning

The site carries a version (footer, `SITE_VERSION` in `docs/index.html`):
x.y.z where **x** = new data source or panel, **y** = update to an existing
source or anchor, **z** = wording or formatting. Current: **5.2.0**.
History: v1 launch (gas split, costs, spark gap, geothermal, NI) → v2 carbon
layer → v3.0–3.2 observed cooling analysis (NESO demand, response curve,
recency-aware sources) → v3.3–3.4 comfort deficit, tier graphic and UTES
dividend → v3.5 services-basis indigenous share and emissions headline →
v3.6 EGEC Geothermal Market Report 2025 refinements → v4.0 WHY HEAT?
whole-economy panel → v4.0.1–4.0.3 methodology statement, carbon basis,
residual SE and calibration ratio surfaced → v5.0 live trend layer: weekly
headline history with per-week Ofgem cap and grid intensity, sparklines and
what-if overlay → v5.1 window selector re-totals the headline figures
(12-month sums and cumulative what-if saving) → v5.2 cooling
reconciliation diagnostic (year-round HDD+CDD regression, swept base).

*A Causeway Energies public-interest tool — https://causewaygt.com*
