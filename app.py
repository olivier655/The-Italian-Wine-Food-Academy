import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

import requests

import leads
from dotenv import load_dotenv
from flask import Flask, abort, redirect, render_template, request, session, url_for

import airtable
import inschrijving
from catalog import (LOCATIES, NLQF_STATUS, calculate, cohort_dates, euro, get_option,
                     grouped, products, vanaf)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.jinja_env.filters["euro"] = euro

MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "")
MAKE_FOLLOWUP_URL = os.environ.get("MAKE_FOLLOWUP_URL", "")

WP = "https://thewineandfoodacademy.com"
STUDIEADVIES = "/studieadvies/"
CALENDLY = "https://calendly.com/olivier-thewineandfoodacademy/30min"
CONTENT = Path(__file__).parent / "content"
STREKEN = json.loads((CONTENT / "streken.json").read_text(encoding="utf-8"))
JURIDISCH = json.loads((CONTENT / "juridisch.json").read_text(encoding="utf-8"))
FAQ = json.loads((CONTENT / "faq.json").read_text(encoding="utf-8"))
SITE = os.environ.get("SITE_URL", "https://italianwineandfoodacademy.com").rstrip("/")
GTM_ID = os.environ.get("GTM_ID", "GTM-NZ5XSCC")
GA_ID = os.environ.get("GA_ID", "G-N1JD18XQ5T")  # alleen gebruikt als GTM_ID leeg is
ADS_ID = os.environ.get("ADS_ID", "AW-11208459250")
CONTACT = {"telefoon": "085 080 6445", "tel": "+31850806445", "email": "klantenservice@thewineandfoodacademy.com",
           "adres": "Steynlaan 44, 3701 EH Zeist"}

# Portretten van de docenten staan (nog) in de mediabibliotheek van WordPress.
FOTO = {
    "Tiziano Capasso": "twfa-docent-tiziano-capasso.jpg",
    "Roberto Santilli": "twfa-docent-roberto-santilli.jpg",
    "Wilco van den Baar": "twfa-docent-wilco-van-den-baar.jpg",
    "Hugo Bos": "twfa-docent-hugo-bos.jpg",
    "Gina Botta": "twfa-docent-gina-botta.jpg",
    "Liseth Aling": "twfa-docent-liseth-aling.jpg",
    "Olav Meyknecht": "twfa-docent-olav-meyknecht.jpg",
    "Olivier": "twfa-docent-olivier-van-hees.jpg",
    "Olivier van Hees": "twfa-docent-olivier-van-hees.jpg",
}


# Sfeerfoto per product en streek (mediabibliotheek WordPress, map 2026/06).
PRODUCT_FOTO = {
    "opleiding-italiaanse-gastronomie": "image00163.jpeg",
    "italiaanse-keuken": "image00112.jpeg",
    "italiaanse-wijn": "image00176.jpeg",
    "italiaanse-wijn-en-spijs": "image00143.jpeg",
    "wijn-en-spijs-veneto": "image00148.jpeg",
    "pasta-fresca": "image00055.jpeg",
    "romeinse-pastas": "image00069.jpeg",
    "pizza-napoletana": "image00023.jpeg",
    "wijn-uit-piemonte": "image00018.jpeg",
    "wijn-uit-veneto": "image00020-1.jpeg",
    "wijn-uit-toscane": "image00015.jpeg",
    "wijn-uit-midden-italie": "image00160.jpeg",
    "wijn-uit-zuid-italie": "image00017-2.jpeg",
    "gastronomie-en-ondernemerschap": "image00170.jpeg",
}
STREEK_FOTO = {
    "piemonte": "image00169.jpeg",
    "lombardije": "image00147.jpeg",
    "ligurie": "image00138.jpeg",
    "toscane": "twfa-hero-toscane.jpg",
}


_STREEK_RESERVE = ["image00176.jpeg", "image00143.jpeg", "image00148.jpeg", "image00160.jpeg", "image00015.jpeg",
                   "image00018.jpeg", "image00020-1.jpeg", "image00017-2.jpeg", "image00163.jpeg", "image00170.jpeg"]


def streek_foto(slug):
    if slug in STREEK_FOTO:
        return img(STREEK_FOTO[slug])
    return img(_STREEK_RESERVE[list(STREKEN).index(slug) % len(_STREEK_RESERVE)])


def product_foto(slug):
    return img(PRODUCT_FOTO.get(slug, "image00163.jpeg"))


def img(name):
    """Foto uit static/img (WebP, verkleind). Namen blijven die uit de oude mediabibliotheek."""
    return "/static/img/" + re.sub(r"\.(jpe?g|png)$", "", name) + ".webp"


def abs_url(path):
    return path if path.startswith("http") else SITE + path


def docenten():
    out = []
    for d in airtable.data().get("docenten", []):
        foto = FOTO.get(d["naam"])
        out.append({**d, "foto": img(foto) if foto else None,
                    "initialen": "".join(w[0] for w in d["naam"].split()[:2]).upper()})
    return out


def faq_schema(faq):
    return [{"@type": "Question", "name": q["v"],
             "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"<[^>]+>", "", q["a"])}}
            for blok in faq for q in blok["vragen"]]


def course_schema(slug, product):
    """Schema.org Course, zodat Google prijs en startdata kan tonen."""
    org = {"@type": "Organization", "name": "The Italian Wine & Food Academy", "sameAs": SITE}
    prijs = vanaf(product)
    data = {"@context": "https://schema.org", "@type": "Course", "name": product["naam"],
            "description": re.sub(r"\s+", " ", product.get("kort") or "")[:500], "provider": org,
            "url": f"{SITE}/product/{slug}/", "image": abs_url(product_foto(slug)),
            "offers": {"@type": "Offer", "price": prijs, "priceCurrency": "EUR", "category": "Paid",
                       "availability": "https://schema.org/InStock", "url": f"{SITE}/aanmelden/{slug}/"}}
    if product.get("starts"):
        data["hasCourseInstance"] = [{
            "@type": "CourseInstance", "courseMode": "Blended", "startDate": s["datum"],
            "location": {"@type": "Place", "name": f"Kookstudio {s['locatie']}",
                         "address": {"@type": "PostalAddress", "addressLocality": s["locatie"], "addressCountry": "NL"}},
            "offers": {"@type": "Offer", "price": prijs, "priceCurrency": "EUR", "category": "Paid"}}
            for s in product["starts"][:10]]
    return data


@app.context_processor
def globals_for_templates():
    return {"NLQF_STATUS": NLQF_STATUS, "STUDIEADVIES": STUDIEADVIES, "WP": WP, "img": img,
            "vanaf": vanaf, "abs_url": abs_url, "STREKEN": STREKEN, "faq_schema": faq_schema, "course_schema": course_schema,
            "product_foto": product_foto, "streek_foto": streek_foto, "SITE": SITE, "GTM_ID": GTM_ID, "GA_ID": GA_ID, "ADS_ID": ADS_ID, "CONTACT": CONTACT,
            "canonical": SITE + request.path, "LOGO": img("The_Italian_Wine_and_Food_Academy_logo-scaled.png"), "STREEK_FOTO": STREEK_FOTO}


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


# ---------- pagina's ----------

@app.route("/")
def home():
    prods = products()
    uitgelicht = [(s, prods[s]) for s in ("opleiding-italiaanse-gastronomie", "italiaanse-keuken",
                                          "italiaanse-wijn", "italiaanse-wijn-en-spijs") if s in prods]
    return render_template("home.html", uitgelicht=uitgelicht, docenten=docenten()[:6])


@app.route("/opleidingen/")
def overzicht():
    return render_template("overzicht.html", groepen=grouped())


@app.route("/leermethode/")
def leermethode():
    return render_template("leermethode.html")


@app.route("/studieadvies/")
def studieadvies():
    return render_template("studieadvies.html", calendly=CALENDLY)


@app.route("/kookstudio/")
def kookstudio():
    return render_template("kookstudio.html")


@app.route("/docenten/")
def docenten_pagina():
    return render_template("docenten.html", docenten=docenten())


@app.route("/<any(%s):slug>/" % ", ".join(f'"{k}"' for k in STREKEN))
def streek(slug):
    s = STREKEN[slug]
    regio = s.get("streek")
    if regio:
        wijnen = [(k, w) for k, w in STREKEN.items() if w.get("streek") == regio and k != slug]
        crumbs = [("Streken", "/streken/"), (STREKEN[regio]["naam"], f"/{regio}/"), (s["naam"], None)]
    else:
        wijnen = [(k, w) for k, w in STREKEN.items() if w.get("streek") == slug]
        crumbs = [("Streken", "/streken/"), (s["naam"], None)]
    return render_template("streek.html", slug=slug, streek=s, regio=regio, wijnen=wijnen, crumbs=crumbs)


BLOKKEN = {1: "Het noordwesten", 2: "Het noordoosten", 3: "Het midden", 4: "Rond Rome", 5: "Het zuiden en de eilanden"}


@app.route("/streken/")
def streken():
    blokken = [(n, BLOKKEN[n], [(k, s) for k, s in STREKEN.items() if s.get("blok") == n]) for n in BLOKKEN]
    artikelen = [(r, STREKEN[r], [(k, s) for k, s in STREKEN.items() if s.get("streek") == r])
                 for r in STREKEN if STREKEN[r].get("blok")]
    artikelen = [a for a in artikelen if a[2]]
    return render_template("streken.html", blokken=blokken, artikelen=artikelen)


@app.route('/<any("algemene-voorwaarden", "privacy-policy", "klachtenprocedure", "gedragscode-nrto"):slug>/')
def juridisch(slug):
    return render_template("pagina.html", pagina=JURIDISCH[slug])


# Oude WordPress-adressen die op de nieuwe site een ander adres hebben.
OUD_NAAR_NIEUW = {
    "inschrijf-voorwaarden": "/algemene-voorwaarden/",
    "algemene-voorwaarden-consumenten-voor-particulier-onderwijs-en-opleidingen": "/algemene-voorwaarden/",
    "faqs": "/faq/",
}


@app.route('/<any("inschrijf-voorwaarden", "algemene-voorwaarden-consumenten-voor-particulier-onderwijs-en-opleidingen", "faqs"):oud>/')
def oud_adres(oud):
    return redirect(OUD_NAAR_NIEUW[oud], code=301)


@app.route("/faq/")
def faq():
    return render_template("faq.html", faq=FAQ)


@app.route("/nieuwsbrief/", methods=["GET", "POST"])
def nieuwsbrief():
    if request.method == "GET":
        return render_template("nieuwsbrief.html", values={}, errors={}, verstuurd=request.args.get("verstuurd"))
    f = request.form
    values, errors = f.to_dict(), {}
    if f.get("csrf") != session.get("csrf"):
        abort(400)
    if f.get("website"):
        return redirect(url_for("nieuwsbrief", verstuurd=1))
    email = f.get("email", "").strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Vul een geldig e-mailadres in."
    if not errors:
        try:
            leads.lead(email, f.get("voornaam", "").strip(), "Nieuwsbrief", tag="nieuwsbrief-website")
            return redirect(url_for("nieuwsbrief", verstuurd=1))
        except Exception:
            app.logger.exception("Nieuwsbriefaanmelding niet verwerkt")
            errors["algemeen"] = f"Aanmelden lukte niet door een storing. Probeer het later nog eens of mail {CONTACT['email']}."
    return render_template("nieuwsbrief.html", values=values, errors=errors, verstuurd=None), 422


DOWNLOADS = {
    "opleidingsbrochure": {
        "titel": "Download de brochure 2026-2027",
        "kort": "Opleidingsbrochure",
        "lead": "Alles over de Opleiding Italiaanse Gastronomie en de losse cursussen op een rij: programma per blok, docenten, praktijkdagen in de kookstudio, startdata en prijzen.",
        "punten": ["Het programma van 36 weken, blok voor blok", "Wie je docenten zijn, van Italiaanse koks tot Nederlandse sommeliers",
                   "Startdata, praktijkdagen en wat een lesweek je kost aan tijd", "Prijzen, termijnen en scholingsbudget"],
        "bestand": "downloads/twfa-brochure-2026-2027.pdf", "tag": "download-brochure",
        "beschrijving": "Download gratis de brochure van The Italian Wine & Food Academy: programma, docenten, startdata en prijzen van de Opleiding Italiaanse Gastronomie.",
    },
    "proefkit": {
        "titel": "Gratis proefkit: zo proef je wijn als een sommelier",
        "kort": "Proefkit",
        "lead": "Het materiaal dat onze cursisten in de eerste les gebruiken: het smaakwiel, een proefformulier voor acht wijnen en de drie stappen van kijken, ruiken en proeven. Print het uit en open een fles.",
        "punten": ["Het smaakwiel: van rood fruit tot aards, zo benoem je wat je ruikt", "Proefformulier om acht wijnen naast elkaar te beoordelen",
                   "Wijnproeven in drie stappen: kijken, ruiken, proeven", "Hoe smaak werkt, en waarom wijn smaakt zoals hij smaakt"],
        "bestand": "downloads/twfa-proefkit.pdf", "tag": "download-proefkit",
        "beschrijving": "Download gratis de proefkit van The Italian Wine & Food Academy: smaakwiel, proefformulier en wijnproeven in drie stappen.",
    },
}


@app.route("/download/<any(%s):slug>/" % ", ".join(f'"{k}"' for k in DOWNLOADS), methods=["GET", "POST"])
def download(slug):
    d = DOWNLOADS[slug]
    if request.method == "GET":
        return render_template("download.html", slug=slug, d=d, values={}, errors={}, verstuurd=request.args.get("verstuurd"))
    f = request.form
    values, errors = f.to_dict(), {}
    if f.get("csrf") != session.get("csrf"):
        abort(400)
    if f.get("website"):
        return redirect(url_for("download", slug=slug, verstuurd=1))
    email = f.get("email", "").strip()
    if not f.get("naam", "").strip():
        errors["naam"] = "Vul je naam in."
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        errors["email"] = "Vul een geldig e-mailadres in."
    if not errors:
        try:
            leads.lead(email, f.get("naam", "").strip(), f"Download {d['kort']}", tag=d["tag"])
            return redirect(url_for("download", slug=slug, verstuurd=1))
        except Exception:
            app.logger.exception("Download-aanmelding niet verwerkt")
            errors["algemeen"] = f"Er ging iets mis. Probeer het later nog eens of mail {CONTACT['email']}."
    return render_template("download.html", slug=slug, d=d, values=values, errors=errors, verstuurd=None), 422


@app.route("/contact/", methods=["GET", "POST"])
def contact():
    if request.method == "GET":
        return render_template("contact.html", values={}, errors={}, verstuurd=request.args.get("verstuurd"))
    f = request.form
    values, errors = f.to_dict(), {}
    if f.get("csrf") != session.get("csrf"):
        abort(400)
    if f.get("website"):
        return redirect(url_for("contact", verstuurd=1))
    for field, message in [("naam", "Vul je naam in."), ("email", "Vul je e-mailadres in."), ("vraag", "Schrijf je vraag.")]:
        if not f.get(field, "").strip():
            errors[field] = message
    if f.get("email") and "@" not in f.get("email", ""):
        errors["email"] = "Dit e-mailadres klopt niet."
    if not errors:
        try:
            inschrijving.verstuur_contact(f.get("naam", "").strip(), f.get("email", "").strip(),
                                          f.get("telefoon", "").strip(), f.get("vraag", "").strip())
            try:
                leads.lead(f.get("email", "").strip(), f.get("naam", "").strip(), "Contactformulier",
                           tag="contactformulier", telefoon=f.get("telefoon", "").strip(), notitie=f.get("vraag", "").strip())
            except Exception:
                app.logger.exception("Contact niet naar ActiveCampaign/Pipedrive")
            return redirect(url_for("contact", verstuurd=1))
        except Exception:
            app.logger.exception("Contactformulier niet verstuurd")
            errors["algemeen"] = f"Je bericht is niet verstuurd door een storing. Mail ons op {CONTACT['email']}."
    return render_template("contact.html", values=values, errors=errors, verstuurd=None), 422


@app.route("/robots.txt")
def robots():
    body = f"User-agent: *\nDisallow: /aanmelden/\nDisallow: /static/downloads/\nSitemap: {SITE}/sitemap.xml\n"
    return body, 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/sitemap.xml")
def sitemap():
    paden = ["/", "/opleidingen/", "/streken/", "/leermethode/", "/kookstudio/", "/docenten/", "/studieadvies/", "/faq/", "/contact/"]
    paden += ["/nieuwsbrief/"] + [f"/download/{k}/" for k in DOWNLOADS] + [f"/{s}/" for s in STREKEN] + [f"/product/{s}/" for s in products()]
    paden += [f"/{s}/" for s in JURIDISCH]
    urls = "".join(f"<url><loc>{SITE}{p}</loc></url>" for p in paden)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return xml, 200, {"Content-Type": "application/xml; charset=utf-8"}


@app.route("/product/regiocursus/")
def oude_regiocursus():
    return redirect(url_for("overzicht") + "#kook", code=301)


@app.route("/product/<slug>/")
def product(slug):
    prods = products()
    product = prods.get(slug) or abort(404)
    team = {d["naam"]: d for d in docenten()}
    namen = product["content"].get("docenten", [])
    return render_template("product.html", slug=slug, product=product,
                           team=[team.get(n) or {"naam": n, "bio": "", "foto": img(FOTO[n]) if n in FOTO else None,
                                                 "initialen": n[:1]} for n in namen])


@app.route("/healthz")
def healthz():
    prods = products()
    return {"ok": True, "bron": airtable.bron(), "producten": len(prods)}


# ---------- aanmelden ----------

def _form_context(slug, product, values, errors):
    return dict(slug=slug, product=product, values=values, errors=errors,
                locaties=LOCATIES, cohortdata=cohort_dates(product) if product["soort"] == "opties" else [])


def _naar_make(url, payload):
    try:
        requests.post(url, json=payload, timeout=10).raise_for_status()
        return True
    except requests.RequestException:
        app.logger.exception("Make-webhook faalde")
        return False


def verwerk(payload):
    """Aanmelding vastleggen. Geeft False als hij nergens terechtkwam.

    1. Direct: inschrijving in Airtable + mails vanuit de site (zonder Make).
    2. Lukt Airtable niet, of is direct nog niet ingesteld: de oude Make-route,
       die zelf het record aanmaakt en de mails stuurt.
    MAKE_FOLLOWUP_URL (optioneel) krijgt na een directe verwerking een seintje
    met het record-ID, voor vervolgstappen als Pipedrive of LearnDash.
    """
    if inschrijving.direct_ready():
        try:
            record_id = inschrijving.schrijf_airtable(payload)
        except requests.RequestException:
            app.logger.exception("Airtable-inschrijving faalde; val terug op Make")
        else:
            try:
                inschrijving.verstuur_mails(payload, record_id)
            except Exception:  # record staat er; een mislukte mail mag de aanmelding niet blokkeren
                app.logger.exception("Mail voor %s niet verstuurd", record_id)
            if MAKE_FOLLOWUP_URL:
                _naar_make(MAKE_FOLLOWUP_URL, {**payload, "airtable_record_id": record_id})
            return True
    if MAKE_WEBHOOK_URL:
        return _naar_make(MAKE_WEBHOOK_URL, payload)
    app.logger.error("Aanmelding niet verwerkt: geen Airtable/SMTP-instellingen en geen MAKE_WEBHOOK_URL")
    return False


@app.route("/aanmelden/<slug>/", methods=["GET", "POST"])
def aanmelden(slug):
    product = products().get(slug) or abort(404)

    if request.method == "GET":
        values = {"optie": request.args.get("optie", "met-praktijk"), "start": request.args.get("start", "")}
        return render_template("aanmelden.html", **_form_context(slug, product, values, {}))

    f = request.form
    values = f.to_dict()
    errors = {}

    if f.get("csrf") != session.get("csrf"):
        abort(400)
    if f.get("website"):  # honeypot: echte mensen laten dit veld leeg
        return redirect(url_for("bedankt"))

    option_key, option_nr, option = None, None, None
    if product["soort"] == "opties":
        option_key = f.get("optie")
        option_nr, option = get_option(product, option_key)
        if option is None:
            errors["optie"] = "Kies een van de drie opties."

    examen = f.get("examen") == "ja"
    examen_inbegrepen = bool(option and option["examen_inbegrepen"])
    heeft_praktijk = product.get("praktijk") if product["soort"] == "enkel" else bool(option and option["praktijk"])
    wil_cohort = heeft_praktijk or bool(option and option["cohort"])

    # Startmoment: bij praktijk een variant (datum + locatie), bij optie 2 alleen een datum.
    variant, startdatum, locatie, startmoment = None, None, None, "Start wanneer je wilt"
    if heeft_praktijk:
        if product["starts"]:
            variant = next((s for s in product["starts"] if s["sku"] == f.get("start")), None)
            if variant is None:
                errors["start"] = "Kies een startdatum en locatie."
            else:
                startdatum, locatie, startmoment = variant["datum"], variant["locatie"], variant["label"]
        else:
            locatie = f.get("locatie")
            if locatie not in LOCATIES:
                errors["locatie"] = "Kies waar je de praktijkdagen volgt."
            startmoment = "Nog in te plannen"
    elif wil_cohort:
        data = dict(cohort_dates(product))
        if data:
            startdatum = f.get("startdatum")
            if startdatum not in data:
                errors["startdatum"] = "Kies een startdatum."
            else:
                startmoment = data[startdatum]
        else:
            startmoment = "Nog in te plannen"

    for field, message in [
        ("voornaam", "Vul je voornaam in."),
        ("achternaam", "Vul je achternaam in."),
        ("email", "Vul je e-mailadres in."),
        ("telefoon", "Vul je telefoonnummer in."),
        ("straat", "Vul je straat en huisnummer in."),
        ("postcode", "Vul je postcode in."),
        ("plaats", "Vul je woonplaats in."),
    ]:
        if not f.get(field, "").strip():
            errors[field] = message
    if f.get("email") and "@" not in f.get("email", ""):
        errors["email"] = "Dit e-mailadres klopt niet."
    if f.get("factuur") == "zakelijk" and not f.get("bedrijfsnaam", "").strip():
        errors["bedrijfsnaam"] = "Vul de bedrijfsnaam voor de factuur in."
    if examen and not examen_inbegrepen and f.get("examenroute") not in ("werkplek", "portfolio"):
        errors["examenroute"] = "Geef aan hoe je je praktijk laat zien."
    if not f.get("voorwaarden"):
        errors["voorwaarden"] = "Ga akkoord met de algemene voorwaarden om je aan te melden."

    if errors:
        return render_template("aanmelden.html", **_form_context(slug, product, values, errors)), 422

    lines, total = calculate(product, option_key, examen)

    payload = {
        "bron": "twfa-flask",
        "aangemeld_op": datetime.now(timezone.utc).isoformat(),
        "product_slug": slug,
        "product_sku": product["sku"],
        "product": product["naam"],
        "optie_nr": option_nr,
        "optie": option["naam"] if option else None,
        "examen": examen_inbegrepen or examen,
        "examen_bijgeboekt": examen and not examen_inbegrepen,
        "examenroute": f.get("examenroute") if examen and not examen_inbegrepen else None,
        "variant_sku": variant["sku"] if variant else None,
        "startdatum": startdatum,
        "startmoment": startmoment,
        "locatie": locatie,
        "voornaam": f.get("voornaam", "").strip(),
        "achternaam": f.get("achternaam", "").strip(),
        "email": f.get("email", "").strip().lower(),
        "telefoon": f.get("telefoon", "").strip(),
        "factuur": f.get("factuur", "particulier"),
        "bedrijfsnaam": f.get("bedrijfsnaam", "").strip() or None,
        "straat": f.get("straat", "").strip(),
        "postcode": f.get("postcode", "").strip().upper(),
        "plaats": f.get("plaats", "").strip(),
        "betaling": f.get("betaling", "ineens"),
        "opmerking": f.get("opmerking", "").strip() or None,
        "prijsregels": [{"omschrijving": d, "bedrag": b} for d, b in lines],
        "totaal": total,
    }

    if not verwerk(payload):
        errors["algemeen"] = (
            "Je aanmelding is niet verstuurd door een storing. Probeer het over een "
            "paar minuten opnieuw of mail naar info@thewineandfoodacademy.com."
        )
        return render_template("aanmelden.html", **_form_context(slug, product, values, errors)), 502

    session["laatste_aanmelding"] = {"voornaam": payload["voornaam"], "regels": payload["prijsregels"], "product": payload["product"],
                                     "totaal": total, "startmoment": startmoment}
    return redirect(url_for("bedankt"))


@app.route("/aanmelden/bedankt/")
def bedankt():
    return render_template("bedankt.html", aanmelding=session.pop("laatste_aanmelding", None))


@app.errorhandler(404)
def niet_gevonden(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(debug=True)
