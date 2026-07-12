# UK Heat Split — a weekly estimate of how Britain heats and cools itself

Most of Britain's heat still comes from burning gas, and a material share of
every unit burned never becomes useful heat. This site turns live grid data
into a weekly estimate of the GB heating and cooling energy split — what it
costs, what it emits, how much is wasted, how much is UK-indigenous, and what
geothermal (deep, mine water, and ground source) supplies today and could
supply next.

**Live site:** https://causewaygt.github.io/uk-heatsplit/

## What the dashboard shows

- **Headlines** — energy purchased this week, estimated UK-indigenous share,
  and the national bill split between heating and cooling, alongside a
  what-if: the same week with 20% of heat and cooling moved to geothermal.
- **Dual bars, same scale** — energy in (fuel and electricity purchased) vs
  useful heat and cooling delivered: combustion derated by in-situ boiler
  efficiencies, heat pumps credited with their harvested ambient heat,
  cooling with its delivered multiple.
- **Daily spark gap** — wholesale cost of useful heat via a gas boiler vs a
  ground-source heat pump, updated daily from the National Gas SAP and the
  Elexon market index.
- **The gas engine room** — daily gas offtake to the distribution zones
  (buildings) against the regression-estimated space-heating signal, with
  total NTS shown for context.
- **What heat costs** — pence per useful kWh by route at current Ofgem cap
  rates, and the national weekly bill.
- **What heat emits** — weekly emissions with a heat/cool split, and gCO2e
  per useful kWh by route: combustion at fixed DESNZ factors, electric routes
  at the live GB grid intensity (NESO Carbon Intensity API, 7-day mean) — so
  the heat-pump rows fall as the grid decarbonises while combustion never
  does.
- **Cooling: demand vs delivery** — an observed cooling response curve from
  half-hourly national electricity demand (NESO, with embedded solar and wind
  reconstructed, demeaned within month and weekend class), binned by cooling
  degree days. The low-CDD slope extrapolated linearly is latent demand; the
  curve is what the installed fleet delivers; divergence indicates capacity
  and behavioural saturation. Not yet used in the bill or carbon figures,
  which stay ECUK-anchored pending a full summer of reconciliation.
- **Geothermal — now and next** — heat and cooling from geothermal this week,
  plus annual bars for today, 2027, 2031 and 2050, each tagged to its source.
  Today's heat is anchored on the EGEC 2025 UK Country Update (1,430 GWhth/yr
  from ~55,210 GSHP units, 847–861 MWth installed, 2023 base) plus mine-water,
  deep and open-loop district schemes; cooling is anchored only on 11 ATES
  systems and historic Southampton data — no national register or metering of
  ground-source systems exists.
- **Northern Ireland** — a separate estimate: NI runs on its own gas and
  electricity systems, so the live GB feeds do not cover it. If the NI DfE
  geothermal licensing proposals proceed (consultation 2026; heat below 100 m
  depth), the resulting register would be the UK's first mandatory geothermal
  data source, and this dashboard is designed to ingest it.

## Method in one paragraph

Daily gas offtake to Britain's local distribution zones (LDZ — the network
serving homes and most businesses, excluding directly connected power
stations) is regressed against population-weighted GB heating degree days
(ERA5 reanalysis via Open-Meteo). The temperature-sensitive component is
attributed to space heating, following the published Watson/Sansom method;
the trailing 12-month total is calibrated against the DESNZ ECUK end-use
tables, GB-adjusted and weather-normalised (current ratio ~1.10, within the
±10% publication threshold). Other fuels and cooling take their annual levels
from ECUK 2025 (calendar 2024) shaped by heating/cooling degree days. **Every
live figure is a model estimate, not a measurement** — caveats are stated on
the site.

## Estimates open to challenge

Sourced figures (Ofgem cap, ECUK anchors, DESNZ GHG factors, Energy Systems
Catapult SPFs, EGEC capacity data, NISRA heating shares, MCS installations)
are cited as such. Figures resting on Causeway judgement are marked † on the
site — the geothermal forecast scenario, several unit prices, the cooling
split and latent-demand extrapolation, indigenous-energy shares, the NI heat
total. Challenge and input welcome: **contact@causewaygt.com**.

## Data sources & licences

National Gas Transmission open data (demand and SAP publications, REST API) ·
Contains BMRS data © Elexon Limited copyright and database right 2026 ·
NESO Data Portal (demand) and NESO Carbon Intensity API, NESO Open Licence ·
Open-Meteo.com (CC BY 4.0) / Copernicus ERA5 · DESNZ ECUK, DUKES and GHG
conversion factors, and NISRA statistics, under the Open Government Licence
v3.0 · EGEC 2025 UK Country Update (cited).

## How it runs

A GitHub Actions cron (`.github/workflows/update.yml`) runs daily at 03:43
UTC: `scripts/build.py` pulls the feeds, fits the regressions, computes the
mix, costs, emissions and headlines, and commits `docs/data.json`; the static
page (`docs/index.html`, Plotly) renders it. Feed failures fall back to the
last good values and are flagged on the page; build failures push a
notification. No API keys required; fork-friendly.

Anchor constants are refreshed on a maintenance calendar: Ofgem cap
quarterly, ECUK/DUKES annually, geothermal panel annually on MCS/EGEC
release.

## Versioning

The site carries a version (footer, `SITE_VERSION` in `docs/index.html`):
x.y.z where **x** = new data source or panel, **y** = update to an existing
source or anchor, **z** = wording or formatting. Current: **3.1.0**
(v1 launch → v2 carbon layer → v3 observed cooling analysis, with the
geothermal base revised to sourced EGEC figures at 2.1).

*A Causeway Energies public-interest tool — https://causewaygt.com*
