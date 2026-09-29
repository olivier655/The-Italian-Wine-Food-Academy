import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

import requests
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
STREKEN = json.loads((Path(__file__).parent / "content" / "streken.json").read_text(encoding="utf-8"))

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


def product_foto(slug):
    return img(PRODUCT_FOTO.get(slug, "image00163.jpeg"))


def img(name):
    return f"{WP}/wp-content/uploads/2026/06/{name}"


def docenten():
    out = []
    for d in airtable.data().get("docenten", []):
        foto = FOTO.get(d["naam"])
        out.append({**d, "foto": img(foto) if foto else None,
                    "initialen": "".join(w[0] for w in d["naam"].split()[:2]).upper()})
    return out


@app.context_processor
def globals_for_templates():
    return {"NLQF_STATUS": NLQF_STATUS, "STUDIEADVIES": STUDIEADVIES, "WP": WP, "img": img,
            "vanaf": vanaf, "STREKEN": STREKEN,
            "product_foto": product_foto, "LOGO": img("The_Italian_Wine_and_Food_Academy_logo-scaled.png"), "STREEK_FOTO": STREEK_FOTO}


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


@app.route("/<any(piemonte, lombardije, ligurie, toscane):slug>/")
def streek(slug):
    return render_template("streek.html", slug=slug, streek=STREKEN[slug])


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

    session["laatste_aanmelding"] = {"voornaam": payload["voornaam"], "regels": payload["prijsregels"],
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
