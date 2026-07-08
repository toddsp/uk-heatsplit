"""Fetch daily GB gas demand from the National Gas Transmission REST API.

Self-resolving: queries the publication catalogue at runtime and matches
publication names, so PUBOB IDs are never hardcoded (they may change during
the SOAP->REST transition, H1 2026).

Fair use: one data request per day; <= 2 MB / ~3,600 records per request.
Values are assumed to be mcm/day and converted to GWh (gross CV basis).
"""

import datetime as dt
import json
import requests

BASE = "https://api.nationalgas.com/operationaldata/v1"
CATALOGUE_URL = f"{BASE}/publications/catalogue"
GASDAY_URL = f"{BASE}/publications/gasday"

# Name patterns (case-insensitive substring sets) -> our internal keys.
# All substrings in a set must appear in the publication name.
TARGETS = {
    "nts_demand_actual": [["demand", "actual", "nts"]],
    "ndm_demand_actual": [["ndm", "actual"], ["demand", "actual", "ndm"]],
    "ldz_demand_actual": [["ldz", "demand", "actual"]],
}

MCM_TO_GWH = 11.056  # ~39.8 MJ/m3 gross CV (DUKES); revisit against DESNZ annual CV


def resolve_publication_ids():
    """Fetch the catalogue and match names -> {key: (id, name)}.
    Raises with the full candidate list if a target cannot be matched,
    so the workflow log shows exactly what names exist."""
    r = requests.get(CATALOGUE_URL, timeout=60)
    r.raise_for_status()
    items = r.json()
    # Catalogue shape may be a list or {"publications": [...]} - handle both.
    if isinstance(items, dict):
        items = items.get("publications", items.get("data", []))
    catalogue = [(it.get("publicationId") or it.get("id"),
                  (it.get("publicationName") or it.get("name") or ""))
                 for it in items]

    resolved, misses = {}, []
    for key, patterns in TARGETS.items():
        hit = None
        for pub_id, name in catalogue:
            low = name.lower()
            if any(all(s in low for s in pat) for pat in patterns):
                hit = (pub_id, name)
                break
        if hit:
            resolved[key] = hit
        else:
            misses.append(key)

    if misses:
        names = "\n".join(sorted(n for _, n in catalogue))
        raise RuntimeError(
            f"Could not resolve {misses} in National Gas catalogue. "
            f"Adjust TARGETS patterns. Available publication names:\n{names}")
    return resolved


def fetch_gas_demand(days=400):
    """Returns {key: {date: value_GWh}} for each resolved series."""
    resolved = resolve_publication_ids()
    end = dt.date.today()
    start = end - dt.timedelta(days=days)

    body = {
        "fromDate": start.isoformat(),
        "toDate": end.isoformat(),
        "publicationIds": [pid for pid, _ in resolved.values()],
        "latestValue": "Y",
    }
    r = requests.post(GASDAY_URL, json=body,
                      headers={"Content-Type": "application/json"}, timeout=120)
    r.raise_for_status()
    payload = r.json()

    id_to_key = {pid: key for key, (pid, _) in resolved.items()}
    out = {key: {} for key in resolved}
    blocks = payload if isinstance(payload, list) else payload.get("data", [])
    for block in blocks:
        key = id_to_key.get(block.get("publicationId"))
        if key is None:
            continue
        for rec in block.get("publications", []):
            date = rec.get("applicableFor")
            try:
                val_mcm = float(rec.get("value"))
            except (TypeError, ValueError):
                continue
            out[key][date] = round(val_mcm * MCM_TO_GWH, 1)

    out["_meta"] = {k: {"publicationId": pid, "publicationName": name}
                    for k, (pid, name) in resolved.items()}
    return out


if __name__ == "__main__":
    data = fetch_gas_demand(days=14)
    print(json.dumps(data["_meta"], indent=2))
    nts = data["nts_demand_actual"]
    for d in sorted(nts)[-5:]:
        print(d, nts[d], "GWh")
