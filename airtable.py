"""Producten, startmomenten en docenten live uit Airtable.

Bron: base Teacher portal TWFA (appkBIDLhNkylTi1x)
  - TWFA Producten: hoofdproducten (Niveau = Hoofdproduct) en varianten
    (Niveau = Variant: één startmoment op één locatie)
  - Teachers: docenten met Brand = TWFA en "On website" aan

Zet AIRTABLE_TOKEN (een personal access token met alleen leesrechten op
deze base) als omgevingsvariabele. Zonder token, of als Airtable even niet
antwoordt, valt de site terug op data/snapshot.json. De site blijft dus
altijd werken; hij toont dan de gegevens van de laatste momentopname.
"""
import json
import logging
import os
import threading
import time
from pathlib import Path

import requests

log = logging.getLogger(__name__)

BASE_ID = "appkBIDLhNkylTi1x"
PRODUCTEN = "tblqCCI1VoWyge4bi"
TEACHERS = "tblIyz614VZKPmtNj"
CACHE_SECONDS = int(os.environ.get("AIRTABLE_CACHE_SECONDS", "300"))
SNAPSHOT = Path(__file__).parent / "data" / "snapshot.json"

_lock = threading.Lock()
_cache = {"at": 0.0, "data": None, "bron": None}


def _snapshot():
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def _fetch_all(token, table, fields):
    records, offset = [], None
    while True:
        params = [("pageSize", "100")] + [("fields[]", f) for f in fields]
        if offset:
            params.append(("offset", offset))
        r = requests.get(
            f"https://api.airtable.com/v0/{BASE_ID}/{table}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=8,
        )
        r.raise_for_status()
        body = r.json()
        records += body.get("records", [])
        offset = body.get("offset")
        if not offset:
            return records


def _sel(v):
    return v.get("name") if isinstance(v, dict) else v


def _from_airtable(token):
    rows = _fetch_all(token, PRODUCTEN, [
        "Naam", "SKU", "Niveau", "Hoofd SKU", "Prijs", "Soort opleiding", "Duur",
        "Weken", "Locatie", "Startdatum", "Korte beschrijving", "URL slug",
        "Status", "Brochure",
    ])
    producten, varianten = [], []
    for rec in rows:
        f = rec.get("fields", {})
        niveau = _sel(f.get("Niveau"))
        if niveau == "Hoofdproduct":
            producten.append({
                "sku": f.get("SKU"),
                "naam": f.get("Naam"),
                "slug": f.get("URL slug"),
                "duur": f.get("Duur"),
                "weken": f.get("Weken"),
                "prijs": f.get("Prijs"),
                "soort": [_sel(s) for s in f.get("Soort opleiding", [])],
                "locatie": f.get("Locatie"),
                "status": f.get("Status"),
                "kort": f.get("Korte beschrijving"),
                "brochure": f.get("Brochure"),
            })
        elif niveau == "Variant":
            naam = f.get("Naam", "")
            locatie = "Zeist" if " Zeist " in f" {naam} " else "Amsterdam" if "Amsterdam" in naam else None
            varianten.append({
                "sku": f.get("SKU"),
                "hoofd_sku": f.get("Hoofd SKU"),
                "locatie": locatie,
                "startdatum": f.get("Startdatum"),
                "prijs": f.get("Prijs"),
                "status": f.get("Status"),
            })
    docenten = []
    for rec in _fetch_all(token, TEACHERS, ["Teachers' names", "Brand", "Bio", "On website", "Active"]):
        f = rec.get("fields", {})
        if f.get("Brand") == "TWFA" and f.get("On website") and _sel(f.get("Active")) != "Inactive":
            docenten.append({"naam": (f.get("Teachers' names") or "").strip(), "bio": f.get("Bio", "")})
    return {"producten": producten, "varianten": varianten, "docenten": docenten}


def data():
    """Gecachte gegevens: eerst Airtable, anders de momentopname."""
    token = os.environ.get("AIRTABLE_TOKEN", "").strip()
    now = time.time()
    with _lock:
        if _cache["data"] is not None and now - _cache["at"] < CACHE_SECONDS:
            return _cache["data"]
        result, bron = None, "snapshot"
        if token:
            try:
                result, bron = _from_airtable(token), "airtable"
            except (requests.RequestException, ValueError, KeyError):
                log.exception("Airtable niet bereikbaar, momentopname gebruikt")
                if _cache["data"] is not None and _cache["bron"] == "airtable":
                    # liever de vorige live-stand dan een oude momentopname
                    _cache["at"] = now - CACHE_SECONDS + 60
                    return _cache["data"]
        if result is None:
            result = _snapshot()
        _cache.update(at=now, data=result, bron=bron)
        return result


def bron():
    return _cache["bron"] or "snapshot"


def reset_cache():
    with _lock:
        _cache.update(at=0.0, data=None, bron=None)
