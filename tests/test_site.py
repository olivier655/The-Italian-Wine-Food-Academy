"""Rooktest van de hele site. Draai met: python -m pytest -q"""
import re
import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as A  # noqa: E402
import airtable  # noqa: E402
from catalog import products  # noqa: E402


class OK:
    def raise_for_status(self):
        pass


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    monkeypatch.delenv("AIRTABLE_TOKEN", raising=False)
    monkeypatch.setattr(A, "MAKE_WEBHOOK_URL", "https://example.invalid/hook")
    airtable.reset_cache()
    yield


@pytest.fixture
def c():
    return A.app.test_client()


def token(c, slug):
    h = c.get(f"/aanmelden/{slug}/").data.decode()
    return re.search(r'name="csrf" value="([^"]+)"', h).group(1)


BASE = dict(voornaam="Test", achternaam="Persoon", email="t@x.nl", telefoon="0612345678",
            straat="Straat 1", postcode="1234ab", plaats="Adam", voorwaarden="on", betaling="termijnen")


def test_pages(c):
    urls = ["/", "/opleidingen/", "/leermethode/", "/studieadvies/", "/kookstudio/", "/docenten/", "/piemonte/",
            "/lombardije/", "/ligurie/", "/toscane/", "/aanmelden/bedankt/", "/static/twfa.css", "/healthz"]
    urls += [f"/product/{s}/" for s in products()] + [f"/aanmelden/{s}/" for s in products()]
    for u in urls:
        assert c.get(u).status_code == 200, u
    assert c.get("/product/bestaatniet/").status_code == 404
    assert c.get("/product/regiocursus/").status_code == 301
    assert len(products()) == 13  # 13 gepubliceerd, Ondernemerschap staat op concept


def test_internal_links(c):
    seen, todo = set(), ["/"]
    while todo:
        u = todo.pop()
        if u in seen:
            continue
        seen.add(u)
        r = c.get(u)
        assert r.status_code in (200, 301), u
        if r.status_code == 200 and "text/html" in r.content_type:
            for href in re.findall(r'href="(/[^"#]*)', r.data.decode()):
                href = href.split("?")[0]
                if href not in seen and not href.startswith("/static"):
                    todo.append(href)
    assert len(seen) > 20


def post(c, slug, **data):
    sent = []
    with mock.patch("app.requests.post", side_effect=lambda u, json, timeout: sent.append(json) or OK()):
        r = c.post(f"/aanmelden/{slug}/", data=dict(BASE, csrf=token(c, slug), **data))
    return r, sent


def test_every_product_and_option(c):
    for slug, p in products().items():
        if p["soort"] == "opties":
            for opt in p["opties"]:
                extra = {"optie": opt["key"]}
                if opt["praktijk"]:
                    extra["start"] = p["starts"][0]["sku"]
                elif opt["cohort"]:
                    extra["startdatum"] = p["starts"][0]["datum"]
                r, sent = post(c, slug, **extra)
                assert r.status_code == 302, (slug, opt["key"], r.data[:500])
                assert sent[-1]["totaal"] == opt["prijs"]
        else:
            r, sent = post(c, slug, start=p["starts"][0]["sku"])
            assert r.status_code == 302, (slug, r.data[:500])
            s = sent[-1]
            assert s["totaal"] == p["prijs"] and s["locatie"] in ("Amsterdam", "Zeist") and s["startdatum"]


def test_exam_addon_and_validation(c):
    r, sent = post(c, "italiaanse-keuken", optie="eigen-tempo", examen="ja", examenroute="werkplek")
    assert r.status_code == 302 and sent[-1]["totaal"] == 595 + 295 and sent[-1]["examen_bijgeboekt"]
    r, _ = post(c, "italiaanse-keuken", optie="met-praktijk")  # geen startdatum gekozen
    assert r.status_code == 422
    r, _ = post(c, "pasta-fresca", start="TWFA-WIJN-GRP")  # startmoment van ander product
    assert r.status_code == 422
    r, _ = post(c, "italiaanse-keuken", optie="met-praktijk", start="x", totaal="1")
    assert r.status_code == 422


def test_csrf_honeypot_and_webhook_failure(c):
    r = c.post("/aanmelden/pasta-fresca/", data=dict(BASE, csrf="fout"))
    assert r.status_code == 400
    r, sent = post(c, "pasta-fresca", website="spam")
    assert r.status_code == 302 and not sent
    start = products()["pasta-fresca"]["starts"][0]["sku"]
    with mock.patch("app.requests.post", side_effect=requests.ConnectionError()):
        r = c.post("/aanmelden/pasta-fresca/", data=dict(BASE, csrf=token(c, "pasta-fresca"), start=start))
    assert r.status_code == 502 and 'value="Test"' in r.data.decode()


def test_airtable_live_and_fallback(monkeypatch):
    monkeypatch.setenv("AIRTABLE_TOKEN", "x")
    airtable.reset_cache()
    with mock.patch("airtable.requests.get", side_effect=requests.ConnectionError()):
        assert len(products()) == 13 and airtable.bron() == "snapshot"
    airtable.reset_cache()

    class R:
        def __init__(self, recs):
            self.recs = recs
        def raise_for_status(self):
            pass
        def json(self):
            return {"records": self.recs}

    prod = [{"fields": {"Niveau": {"name": "Hoofdproduct"}, "SKU": "TWFA-PASTA", "Naam": "Pasta Fresca",
                        "URL slug": "pasta-fresca", "Prijs": 650, "Status": "Gepubliceerd",
                        "Soort opleiding": [{"name": "Kookcursus"}], "Duur": "3 weken"}},
            {"fields": {"Niveau": {"name": "Variant"}, "SKU": "TWFA-PASTA-GRP-X", "Hoofd SKU": "TWFA-PASTA",
                        "Naam": "Pasta Fresca - Groep - Zeist - 01-04-2099", "Startdatum": "2099-04-01", "Status": "publish"}}]
    teach = [{"fields": {"Teachers' names": "Tiziano Capasso", "Brand": "TWFA", "On website": True, "Bio": "x"}}]
    with mock.patch("airtable.requests.get", side_effect=lambda url, **k: R(prod if "tblq" in url else teach)):
        p = products()
    assert airtable.bron() == "airtable"
    assert p["pasta-fresca"]["prijs"] == 650 and p["pasta-fresca"]["starts"][0]["locatie"] == "Zeist"
