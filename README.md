# UK Heat Split — a weekly estimate of how Britain heats and cools itself

Most of Britain's heat still comes from burning gas, and a material share of
every unit burned never becomes useful heat. This site turns live grid data
into a weekly estimate of the GB heating and cooling energy split — the
energy volume, what it costs, what it emits, how much of it is UK-indigenous,
who is left sweltering without cooling at all, and what geothermal (deep,
mine water, and ground source) supplies today and could supply next.

**Live site:** https://causewaygt.github.io/uk-heatsplit/

## What the dashboard shows

- **Headlines** — four stats: energy purchased this week; the UK-indigenous
  share of heat and cooling delivered (services basis); the national bill
  split between heating and cooling; and heating & cooling emissions —
  alongside a what-if strip answering all four with 20% of heat and cooling
  moved to geothermal.
- **Dual bars, same scale** — energy in (fuel and electricity purchased) vs
  useful heat and cooling delivered: combustion derated by in-situ boiler
  efficiencies, heat pumps credited with their harvested ambient heat,
  cooling with its delivered multiple.
- **Daily spark gap** — wholesale cost of useful heat via a gas boiler vs a
  ground-source heat pump, updated daily from the National Gas SAP and the
  Elexon market index.
- **What heat costs** — pence per useful kWh by route at current Ofgem cap
  rates, and the national weekly bill.
- **What heat emits** — weekly emissions with a heat/cool split, and gCO2e
  per useful kWh by route: combustion at fixed DESNZ factors, electric routes
  at the live GB grid intensity (NESO Carbon Intensity API, 7-day mean) — so
  the heat-pump rows fall as the grid decarbonises while combustion never
  does.
- **Geothermal — now and next** — heat and cooling from geothermal this week,
  plus annual bars for today, 2027, 2031 and 2050, each tagged to its source.
  Today's heat is anchored on the EGEC 2025 UK Country Update (1,430 GWhth/yr
  from ~55,210 GSHP units, 847–861 MWth installed, 2023 base) plus
  mine-water, deep and open-loop district schemes; no national register or
  metering of ground-source systems exists.
- **The gas engine room** — daily gas offtake to the distribution zones
  (buildings) against the regression-estimated space-heating signal, with
  total NTS shown for context.
- **Cooling: demand vs delivery, in three tiers** —
  *Tiers 1 & 2 (the equipped fleet):* an observed cooling response curve from
  half-hourly national electricity demand (NESO, embedded solar and wind
  reconstructed, demeaned within month and weekend class), binned by cooling
  degree days: what installed cooling delivers, and whether it saturates.
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

## Method in one paragraph

Daily gas offtake to Britain's local distribution zones (LDZ — the network
serving homes and most businesses, excluding directly connected power
stations) is regressed against population-weighted GB heating degree days
(ERA5 reanalysis via Open-Meteo). The temperature-sensitive component is
attributed to space heating, following the published Watson/Sansom method;
the trailing 12-month total is calibrated against the DESNZ ECUK end-use
tables, GB-adjusted and weather-normalised (current ratio ~1.10, within the
±10% publication threshold). Other fuels and cooling take their annual levels
from ECUK 2025 (calendar 2024) shaped by heating/cooling degree days. The
indigenous share is measured on a services basis — each unit of delivered
heat or cooling inherits the UK-origin share of its energy input, with
harvested ambient/ground heat counting as 100% indigenous, consistent with
Eurostat/DUKES renewable-supply accounting. **Every live figure is a model
estimate, not a measurement** — caveats are stated on the site.

## Estimates open to challenge

Sourced figures (Ofgem cap, ECUK anchors, DESNZ GHG factors, Energy Systems
Catapult SPFs, EGEC capacity data, NISRA heating shares, MCS installations,
EHS/CCC overheating prevalence, ONS/UKHSA health and productivity data) are
cited as such. Figures resting on Causeway judgement are marked † on the
site — the geothermal forecast scenario, several unit prices, the cooling
split and latent-demand extrapolation, the comfort-deficit stock fractions
and thermal-response coefficients, the UTES round-trip, indigenous
input-origin shares, the NI heat total. Challenge and input welcome:
**contact@causewaygt.com**.

## Data sources & licences

National Gas Transmission open data (demand and SAP publications, REST API) ·
Contains BMRS data © Elexon Limited copyright and database right 2026 ·
NESO Data Portal (demand) and NESO Carbon Intensity API, NESO Open Licence ·
Open-Meteo.com (CC BY 4.0) / Copernicus ERA5 (daily and hourly) · DESNZ ECUK,
DUKES and GHG conversion factors, MHCLG dwelling statistics, and NISRA
statistics, under the Open Government Licence v3.0 · EGEC 2025 UK Country
Update, English Housing Survey, CCC adaptation reporting, ONS/UKHSA heat
mortality and productivity statistics (cited).

## How it runs

A GitHub Actions cron (`.github/workflows/update.yml`) runs daily at 03:43
UTC: `scripts/build.py` pulls the feeds, fits the regressions, computes the
mix, costs, emissions, cooling tiers and headlines, and commits
`docs/data.json`; the static page (`docs/index.html`, Plotly) renders it.
Feed failures fall back to the last good values and are flagged on the page
(sources that publish on a lag show amber); build failures push a
notification. No API keys required; fork-friendly.

Anchor constants are refreshed on a maintenance calendar: Ofgem cap
quarterly, ECUK/DUKES annually, geothermal panel annually on MCS/EGEC
release.

## Versioning

The site carries a version (footer, `SITE_VERSION` in `docs/index.html`):
x.y.z where **x** = new data source or panel, **y** = update to an existing
source or anchor, **z** = wording or formatting. Current: **3.5.2**.
History: v1 launch (gas split, costs, spark gap, geothermal, NI) → v2 carbon
layer → v3.0–3.2 observed cooling analysis (NESO demand, response curve,
recency-aware sources) → v3.3–3.4 comfort deficit, tier graphic and UTES
dividend → v3.5 services-basis indigenous share and emissions headline.

*A Causeway Energies public-interest tool — https://causewaygt.com*
