"""Fetch daily GB gas demand from the National Gas Transmission REST API.

Self-resolving: walks the publication catalogue recursively (it is a nested
category tree) and matches publication names, so PUBOB IDs are never
hardcoded. Fair use: one data request per day.
Values assumed mcm/day, converted to GWh (gross CV basis).
"""

import datetime as dt
import json
import requests

BASE = "https://api.nationalgas.com/operationaldata/v1"
CATALOGUE_URL = f"{BASE}/publications/catalogue"
GASDAY_URL = f"{BASE}/publications/gasday"

TARGETS = {
    "nts_demand_actual": [["demand", "actual", "nts"],
                          ["nts", "demand"]],
    "ndm_demand_actual": [["ndm", "actual"], ["demand", "ndm"]],
    "ldz_demand_actual": [["ldz", "demand", "actual"], ["ldz", "demand"]],
}

MCM_TO_GWH = 11.056


def _harvest(node, found):
    """Recursively collect (publicationId, publicationName) pairs from any
    nesting of dicts/lists."""
    if isinstance(node, dict):
        pid = node.get("publicationId") or node.get("publicationObjectId") \
              or node.get("pubObjId") or node.get("id")
        name = node.get("publicationName") or node.get("publicationObjectName") \
               or node.get("name") or node.get("title")
        if pid and name and str(pid).upper().startswith("PUB"):
            found.append((str(pid), str(name)))
        for v in node.values():
            _harvest(v, found)
    elif isinstance(node, list):
        for v in node:
            _harvest(v, found)


def resolve_publication_ids():
    r = requests.get(CATALOGUE_URL, timeout=60)
    r.raise_for_status()
    raw = r.json()

    catalogue = []
    _harvest(raw, catalogue)
    # de-duplicate
    catalogue = sorted(set(catalogue))

    if not catalogue:
        snippet = json.dumps(raw)[:4000]
        raise RuntimeError(
            "Catalogue harvest found no PUB* ids. Raw structure sample:\n" + snippet)

    resolved, misses = {}, []
    for key, patterns in TARGETS.items():
        hit = None
        for pat in patterns:              # try patterns in priority order
            for pub_id, name in catalogue:
                low = name.lower()
                if all(s in low for s in pat):
                    hit = (pub_id, name)
                    break
            if hit:
                break
        if hit:
            resolved[key] = hit
        else:
            misses.append(key)

    if misses:
        names = "\n".join(f"{i} | {n}" for i, n in catalogue
                          if "demand" in n.lower()) or \
                "\n".join(f"{i} | {n}" for i, n in catalogue)
        raise RuntimeError(
            f"Could not resolve {misses}. Demand-related publications found:\n{names}")

    print("Resolved publications:",
          {k: v for k, v in resolved.items()})
    return resolved


def fetch_gas_demand(days=400):
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
    data =
