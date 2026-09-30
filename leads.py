"""Aanmeldingen van de site doorzetten naar ActiveCampaign en Pipedrive.

Elke aanmelding (nieuwsbrief, download, contact) komt op de ActiveCampaign-lijst
en als deal in Pipedrive-pipeline 15. Sleutels staan alleen in de Render-omgeving.
"""
import logging
import os

import requests

log = logging.getLogger(__name__)

AC_API_URL = os.environ.get("AC_API_URL", "").rstrip("/")
AC_API_KEY = os.environ.get("AC_API_KEY", "")
AC_LIST_ID = os.environ.get("AC_LIST_ID", "5")

PD_API_TOKEN = os.environ.get("PIPEDRIVE_API_TOKEN", "")
PD_API_URL = os.environ.get("PIPEDRIVE_API_URL", "https://api.pipedrive.com").rstrip("/")
PD_PIPELINE_ID = int(os.environ.get("PIPEDRIVE_PIPELINE_ID", "15"))
PD_STAGE_ID = os.environ.get("PIPEDRIVE_STAGE_ID", "94")  # 94 = eerste fase (SQL) van pipeline 15
PD_OWNER_ID = os.environ.get("PIPEDRIVE_OWNER_ID", "17841611")

TIMEOUT = 10


# --- ActiveCampaign -------------------------------------------------------

def _ac(method, path, **kw):
    r = requests.request(method, f"{AC_API_URL}/api/3/{path}", timeout=TIMEOUT,
                         headers={"Api-Token": AC_API_KEY, "Content-Type": "application/json"}, **kw)
    r.raise_for_status()
    return r.json() if r.content else {}


def _ac_tag_id(naam):
    for t in _ac("GET", "tags", params={"search": naam}).get("tags", []):
        if t.get("tag", "").lower() == naam.lower():
            return t["id"]
    return _ac("POST", "tags", json={"tag": {"tag": naam, "tagType": "contact"}})["tag"]["id"]


def ac_aanmelden(email, voornaam="", achternaam="", telefoon="", tag=None):
    """Contact aanmaken of bijwerken, op de nieuwsbrieflijst zetten en eventueel taggen."""
    if not (AC_API_URL and AC_API_KEY):
        raise RuntimeError("AC_API_URL/AC_API_KEY ontbreken")
    contact = {"email": email}
    if voornaam:
        contact["firstName"] = voornaam
    if achternaam:
        contact["lastName"] = achternaam
    if telefoon:
        contact["phone"] = telefoon
    cid = _ac("POST", "contact/sync", json={"contact": contact})["contact"]["id"]
    _ac("POST", "contactLists", json={"contactList": {"list": AC_LIST_ID, "contact": cid, "status": 1}})
    if tag:
        _ac("POST", "contactTags", json={"contactTag": {"contact": cid, "tag": _ac_tag_id(tag)}})
    return cid


# --- Pipedrive ------------------------------------------------------------

def _pd(method, path, **kw):
    params = kw.pop("params", {})
    params["api_token"] = PD_API_TOKEN
    r = requests.request(method, f"{PD_API_URL}/{path}", params=params, timeout=TIMEOUT, **kw)
    r.raise_for_status()
    return r.json().get("data")


def _pd_stage_id():
    if PD_STAGE_ID:
        return int(PD_STAGE_ID)
    stages = _pd("GET", "api/v2/stages", params={"pipeline_id": PD_PIPELINE_ID, "sort_by": "order_nr"}) or []
    return stages[0]["id"]


def pipedrive_lead(email, naam, bron, telefoon="", notitie=""):
    """Persoon zoeken of aanmaken; open deal in de pipeline hergebruiken of een nieuwe maken."""
    if not PD_API_TOKEN:
        raise RuntimeError("PIPEDRIVE_API_TOKEN ontbreekt")
    naam = naam or email.split("@")[0]
    gevonden = _pd("GET", "api/v2/persons/search",
                   params={"term": email, "fields": "email", "exact_match": "true"}) or {}
    items = gevonden.get("items") or []
    if items:
        pid = items[0]["item"]["id"]
    else:
        persoon = {"name": naam, "emails": [{"value": email, "primary": True, "label": "work"}],
                   "owner_id": int(PD_OWNER_ID)}
        if telefoon:
            persoon["phones"] = [{"value": telefoon, "primary": True, "label": "mobile"}]
        pid = _pd("POST", "api/v2/persons", json=persoon)["id"]

    open_deals = _pd("GET", "api/v2/deals", params={"person_id": pid, "pipeline_id": PD_PIPELINE_ID,
                                                    "status": "open", "limit": 1}) or []
    if open_deals:
        did = open_deals[0]["id"]
    else:
        did = _pd("POST", "api/v2/deals", json={
            "title": f"{naam} · {bron}", "person_id": pid, "pipeline_id": PD_PIPELINE_ID,
            "stage_id": _pd_stage_id(), "owner_id": int(PD_OWNER_ID)})["id"]
    tekst = f"<p><b>Via de website: {bron}</b></p>"
    if notitie:
        tekst += "<p>" + notitie.replace("&", "&amp;").replace("<", "&lt;").replace("\n", "<br>") + "</p>"
    _pd("POST", "v1/notes", json={"content": tekst, "deal_id": did, "person_id": pid})
    return did


def lead(email, naam="", bron="Website", tag=None, telefoon="", notitie=""):
    """Beide kanalen. ActiveCampaign is leidend (fout = melding aan de bezoeker),
    Pipedrive is best effort (fout wordt gelogd)."""
    delen = (naam or "").strip().split(" ", 1)
    ac_aanmelden(email, delen[0], delen[1] if len(delen) > 1 else "", telefoon, tag)
    try:
        pipedrive_lead(email, naam, bron, telefoon, notitie)
    except Exception:
        log.exception("Pipedrive-lead niet aangemaakt voor %s (%s)", email, bron)
