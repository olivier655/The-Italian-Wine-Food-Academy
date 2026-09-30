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
        self.status = self.status_code = status
    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(str(self.status))
    def json(self):
        return {"records": [{"id": "recTEST1234567890"}]}
    @property
    def ok(self):
        return self.status < 400
    text = "fout"


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


def test_juridisch_faq_contact_seo(c, monkeypatch):
    for u in ["/algemene-voorwaarden/", "/privacy-policy/", "/klachtenprocedure/", "/gedragscode-nrto/", "/faq/", "/contact/"]:
        r = c.get(u)
        assert r.status_code == 200, u
        h = r.data.decode()
        assert 'rel="canonical" href="https://italianwineandfoodacademy.com' + u in h
        assert "GTM-NZ5XSCC" in h and "gtag/js" not in h and "gtag('consent', 'default'" in h and 'id="cookie"' in h
    for oud, nieuw in [("/inschrijf-voorwaarden/", "/algemene-voorwaarden/"), ("/faqs/", "/faq/")]:
        r = c.get(oud)
        assert r.status_code == 301 and r.headers["Location"].endswith(nieuw)
    assert "FAQPage" in c.get("/faq/").data.decode()
    assert '"@type": "Course"' in c.get("/product/pasta-fresca/").data.decode()
    sm = c.get("/sitemap.xml").data.decode()
    assert "/product/pasta-fresca/" in sm and "/algemene-voorwaarden/" in sm and "/aanmelden/" not in sm
    assert "Sitemap:" in c.get("/robots.txt").data.decode()
    assert 'name="robots" content="noindex"' in c.get("/aanmelden/pasta-fresca/").data.decode()

    # contactformulier
    h = c.get("/contact/").data.decode()
    csrf = re.search(r'name="csrf" value="([^"]+)"', h).group(1)
    assert c.post("/contact/", data={"csrf": csrf, "naam": ""}).status_code == 422
    sent = []
    monkeypatch.setattr(A.inschrijving, "verstuur_contact", lambda *a: sent.append(a))
    r = c.post("/contact/", data={"csrf": csrf, "naam": "Test", "email": "t@x.nl", "vraag": "Hallo"})
    assert r.status_code == 302 and sent and sent[0][0] == "Test"
    assert "je vraag is binnen" in c.get("/contact/?verstuurd=1").data.decode()


def test_alle_fotos_lokaal(c):
    """Elke foto op de site komt uit static/img en bestaat echt."""
    paginas = ["/", "/opleidingen/", "/kookstudio/", "/docenten/", "/leermethode/", "/streken/"] + [f"/{k}/" for k in A.STREKEN]
    paginas += [f"/product/{s}/" for s in products()]
    gezien = set()
    for u in paginas:
        h = c.get(u).data.decode()
        assert not re.search(r"""(?:<img[^>]+src="|url\(')https?://[^"']*wp-content""", h), u
        for src in re.findall(r"""(?:src="|url\(')(/static/img/[^"']+)""", h):
            gezien.add(src)
    assert len(gezien) > 25
    for src in gezien:
        assert c.get(src).status_code == 200, src


def _fake_api(monkeypatch):
    import leads
    calls = []

    class R:
        def __init__(self, data): self.data = data; self.content = b"x"
        def raise_for_status(self): pass
        def json(self): return self.data

    def fake(method, url, **kw):
        calls.append((method, url, kw.get("json"), kw.get("params")))
        if url.endswith("/contact/sync"): return R({"contact": {"id": "42"}})
        if url.endswith("/tags") and method == "GET": return R({"tags": [{"id": "7", "tag": kw["params"]["search"]}]})
        if "persons/search" in url: return R({"data": {"items": []}})
        if url.endswith("/persons"): return R({"data": {"id": 11}})
        if url.endswith("/deals") and method == "GET": return R({"data": []})
        if url.endswith("/deals"): return R({"data": {"id": 99}})
        return R({"data": {}})

    monkeypatch.setattr(leads, "AC_API_URL", "https://x.api-us1.com")
    monkeypatch.setattr(leads, "AC_API_KEY", "test")
    monkeypatch.setattr(leads, "PD_API_TOKEN", "test")
    monkeypatch.setattr(leads.requests, "request", fake)
    return calls


def test_nieuwsbrief_naar_activecampaign_en_pipedrive(monkeypatch):
    import app as site
    calls = _fake_api(monkeypatch)
    c = site.app.test_client()
    assert c.get("/nieuwsbrief/").status_code == 200
    with c.session_transaction() as s:
        s["csrf"] = "t"
    r = c.post("/nieuwsbrief/", data={"csrf": "t", "email": "a@b.nl", "voornaam": "Ann"})
    assert r.status_code == 302 and "verstuurd=1" in r.headers["Location"]
    assert calls[0][2] == {"contact": {"email": "a@b.nl", "firstName": "Ann"}}
    assert calls[1][2] == {"contactList": {"list": "5", "contact": "42", "status": 1}}
    deal = [c for c in calls if c[0] == "POST" and c[1].endswith("/deals")][0][2]
    assert deal["pipeline_id"] == 15 and deal["stage_id"] == 94 and deal["person_id"] == 11
    assert c.post("/nieuwsbrief/", data={"csrf": "t", "email": "fout"}).status_code == 422


def test_downloads(monkeypatch):
    import app as site
    calls = _fake_api(monkeypatch)
    c = site.app.test_client()
    for slug in ("opleidingsbrochure", "proefkit"):
        assert c.get(f"/download/{slug}/").status_code == 200
    with c.session_transaction() as s:
        s["csrf"] = "t"
    r = c.post("/download/proefkit/", data={"csrf": "t", "email": "a@b.nl", "naam": "Ann de Vries"}, follow_redirects=True)
    assert b"twfa-proefkit.pdf" in r.data
    assert {"contactTag": {"contact": "42", "tag": "7"}} in [x[2] for x in calls]
    assert c.get("/static/downloads/twfa-proefkit.pdf").status_code == 200


def test_wijnartikelen_en_kruimelpad():
    import app as site
    c = site.app.test_client()
    t = c.get("/barbera-dasti/").get_data(as_text=True)
    assert "BreadcrumbList" in t and 'href="/piemonte/"' in t and 'class="kort"' in t
    assert 'href="/barbera-dasti/"' in c.get("/piemonte/").get_data(as_text=True)
