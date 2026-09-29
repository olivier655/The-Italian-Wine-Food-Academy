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
    for k in ("AIRTABLE_TOKEN", "AIRTABLE_WRITE_TOKEN", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"):
        monkeypatch.delenv(k, raising=False)
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


class AT:
    def __init__(self, status=200):
        self.status = status
    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))
    def json(self):
        return {"records": [{"id": "recTEST1234567890"}]}


def direct_env(monkeypatch):
    for k, v in dict(AIRTABLE_WRITE_TOKEN="w", SMTP_HOST="smtp.x", SMTP_USER="o@x.nl",
                     SMTP_PASSWORD="p", MAIL_FROM="TWFA <o@x.nl>").items():
        monkeypatch.setenv(k, v)


def test_direct_airtable_and_mail(c, monkeypatch):
    direct_env(monkeypatch)
    calls, mails = [], []

    class SMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self): pass
        def login(self, u, p): pass
        def send_message(self, m): mails.append(m)

    def fake_post(url, json, timeout, **k):
        calls.append((url, json))
        return AT()

    slug = "italiaanse-keuken"
    start = products()[slug]["starts"][0]["sku"]
    with mock.patch("inschrijving.requests.post", side_effect=fake_post), mock.patch("inschrijving.smtplib.SMTP", SMTP):
        r = c.post(f"/aanmelden/{slug}/", data=dict(BASE, csrf=token(c, slug), optie="met-praktijk", start=start))
    assert r.status_code == 302
    assert len(calls) == 1 and "api.airtable.com" in calls[0][0]  # geen Make
    f = calls[0][1]["records"][0]["fields"]
    assert f["fld0Pu2GkiYoHLLn1"] == "Test" and f["fldiyyoRjGDT7DsWN"] == ["Italiaanse Keuken"]
    assert f["fldAq1LB0aGgTpQj1"] == "Vijf termijnen" and f["fldnPsJekI64Qiu9q"] == "Aangemeld"
    assert f["fldePDecZZL7Ewnqe"] in ("Amsterdam", "Zeist") and f["fldfzvJMyX5602sui"] > 0
    assert [m["To"] for m in mails] == ["t@x.nl", "o@x.nl"]
    body = mails[0].get_body(("html",)).get_content()
    assert "Beste Test" in body and "italianwineandfoodacademy.com" in body and "**" not in body
    assert "recTEST1234567890" in mails[1].get_body(("html",)).get_content()


def test_direct_falls_back_to_make(c, monkeypatch):
    direct_env(monkeypatch)
    calls = []

    def fake_post(url, json, timeout, **k):
        calls.append(url)
        return AT(422) if "airtable" in url else OK()

    start = products()["pasta-fresca"]["starts"][0]["sku"]
    with mock.patch("app.requests.post", side_effect=fake_post):
        r = c.post("/aanmelden/pasta-fresca/", data=dict(BASE, csrf=token(c, "pasta-fresca"), start=start))
    assert r.status_code == 302 and calls[-1] == "https://example.invalid/hook"
