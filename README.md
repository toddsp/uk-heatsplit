# UK Heat Split — a weekly estimate of how Britain heats and cools itself

Most of Britain's heat still comes from burning gas, and a material share of
every unit burned never becomes useful heat. This site turns live grid data
into a weekly estimate of the GB heating and cooling energy split — what it
costs, how much is wasted, how much is UK-indigenous, and what geothermal
(deep, mine water, and ground source) supplies today and could supply next.

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
- **Geothermal — now and next** — estimated heat and cooling from geothermal
  this week, plus annual bars for today, 2027, 2031 and 2050, each tagged to
  its source (MCS trend, CCC Seventh Carbon Budget, Project InnerSpace).
- **Northern Ireland** — a separate estimate: NI runs on its own gas and
  electricity systems, so the live GB feeds do not cover it.

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

Sourced figures (Ofgem cap, ECUK anchors, Energy Systems Catapult SPFs, NISRA
heating shares, MCS installations) are cited as such. Figures resting on
Causeway judgement are marked † on the site — geothermal actuals and the 2031
scenario, several unit prices, the cooling split, indigenous-energy shares,
the NI heat total. Challenge and input welcome: **contact@causewaygt.com**.

## Data sources & licences

National Gas Transmission open data (demand and SAP publications, REST API) ·
Contains BMRS data © Elexon Limited copyright and database right 2026 ·
Open-Meteo.com (CC BY 4.0) / Copernicus ERA5 · DESNZ ECUK and DUKES, and
NISRA statistics, under the Open Government Licence v3.0.

## How it runs

A GitHub Actions cron (`.github/workflows/update.yml`) runs daily at 06:17
UTC: `scripts/build.py` pulls the feeds, fits the regression, computes the
mix, costs and headlines, and commits `docs/data.json`; the static page
(`docs/index.html`, Plotly) renders it. Feed failures fall back to the last
good values and are flagged on the page. No API keys required; fork-friendly.

Anchor constants are refreshed on a maintenance calendar: Ofgem cap quarterly,
ECUK/DUKES annually, geothermal panel annually on MCS release.

*A Causeway Energies public-interest tool — https://causewaygt.com*
