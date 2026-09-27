import os
import secrets
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from flask import Flask, abort, redirect, render_template, request, session, url_for

from catalog import (LOCATIES, NLQF_STATUS, PRODUCTS, REGIOS, STARTMOMENTEN,
                     calculate, euro, get_option)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.jinja_env.filters["euro"] = euro

MAKE_WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK_URL", "")


@app.context_processor
def globals_for_templates():
    return {"NLQF_STATUS": NLQF_STATUS, "PRODUCTS": PRODUCTS}


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(24)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.route("/")
@app.route("/opleidingen/")
def overzicht():
    return render_template("overzicht.html")


@app.route("/product/<slug>/")
def product(slug):
    product = PRODUCTS.get(slug) or abort(404)
    return render_template("product.html", slug=slug, product=product)


def _form_context(slug, product, values, errors):
    return dict(
        slug=slug, product=product, values=values, errors=errors,
        startmomenten=STARTMOMENTEN, locaties=LOCATIES, regios=REGIOS,
    )


@app.route("/aanmelden/<slug>/", methods=["GET", "POST"])
def aanmelden(slug):
    product = PRODUCTS.get(slug) or abort(404)

    if request.method == "GET":
        values = {"optie": request.args.get("optie", "met-praktijk")}
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
    heeft_praktijk = product.get("praktijk") if option is None else option["praktijk"]
    examen_inbegrepen = bool(option and option["examen_inbegrepen"])

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
    if heeft_praktijk and f.get("locatie") not in LOCATIES:
        errors["locatie"] = "Kies waar je de praktijkdagen volgt."
    if product.get("kies_regio") and f.get("regio") not in REGIOS:
        errors["regio"] = "Kies een regio."
    if examen and not examen_inbegrepen and f.get("examenroute") not in ("werkplek", "portfolio"):
        errors["examenroute"] = "Geef aan hoe je je praktijk laat zien."
    if not f.get("voorwaarden"):
        errors["voorwaarden"] = "Ga akkoord met de algemene voorwaarden om je aan te melden."

    if errors:
        return render_template("aanmelden.html", **_form_context(slug, product, values, errors)), 422

    lines, total = calculate(slug, option_key, examen)

    payload = {
        "bron": "twfa-flask",
        "aangemeld_op": datetime.now(timezone.utc).isoformat(),
        "product_slug": slug,
        "product": product["naam"],
        "optie_nr": option_nr,
        "optie": option["naam"] if option else None,
        "examen": examen_inbegrepen or examen,
        "examen_bijgeboekt": examen and not examen_inbegrepen,
        "examenroute": f.get("examenroute") if examen and not examen_inbegrepen else None,
        "locatie": f.get("locatie") if heeft_praktijk else None,
        "startmoment": f.get("startmoment"),
        "regio": f.get("regio") if product.get("kies_regio") else None,
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

    if MAKE_WEBHOOK_URL:
        try:
            r = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=10)
            r.raise_for_status()
        except requests.RequestException:
            app.logger.exception("Make-webhook faalde")
            errors["algemeen"] = (
                "Je aanmelding is niet verstuurd door een storing. Probeer het over een "
                "paar minuten opnieuw of mail naar info@thewineandfoodacademy.com."
            )
            return render_template("aanmelden.html", **_form_context(slug, product, values, errors)), 502
    else:
        app.logger.warning("MAKE_WEBHOOK_URL ontbreekt; aanmelding voor %s niet doorgestuurd", slug)

    session["laatste_aanmelding"] = {"voornaam": payload["voornaam"], "regels": payload["prijsregels"], "totaal": total}
    return redirect(url_for("bedankt"))


@app.route("/aanmelden/bedankt/")
def bedankt():
    return render_template("bedankt.html", aanmelding=session.pop("laatste_aanmelding", None))


if __name__ == "__main__":
    app.run(debug=True)
