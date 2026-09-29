"""Aanmelding direct verwerken: inschrijving in Airtable + bevestigingsmail.

Zo hangt het aanmelden niet meer aan Make. Nodig (omgevingsvariabelen):

  AIRTABLE_WRITE_TOKEN  personal access token met data.records:write op base
                        appkBIDLhNkylTi1x (valt terug op AIRTABLE_TOKEN als die
                        schrijfrechten heeft)
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD
                        bijv. smtp.gmail.com / 587 / olivier@… / app-wachtwoord
  MAIL_FROM             afzender, bijv. "Olivier van Hees <olivier@thewineandfoodacademy.com>"
  MAIL_NOTIFY           wie een melding krijgt van elke aanmelding

Staat dit niet (volledig) ingesteld, dan gebruikt app.py de oude route via de
Make-webhook. Lukt het wegschrijven naar Airtable niet, dan ook.
"""
import html
import logging
import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import make_msgid
from zoneinfo import ZoneInfo

import requests

from airtable import BASE_ID

log = logging.getLogger(__name__)

INSCHRIJVINGEN = "tblVuh7i3F6CCUJfH"
SITE = "https://italianwineandfoodacademy.com"

# Veld-IDs in TWFA Inschrijvingen (zelfde mapping als Make-scenario 9875320).
F = {
    "naam": "fldgrCTah03XHX4Lk", "voornaam": "fld0Pu2GkiYoHLLn1", "achternaam": "fld8dKBFRapOCznux",
    "email": "fldGgv2mOXROXYHEe", "telefoon": "fldxqb6Us3A4IV9SM", "opleiding": "fldiyyoRjGDT7DsWN",
    "cohort": "fldO8H9TTKN3rSSWd", "locatie": "fldePDecZZL7Ewnqe", "startdatum": "fldPBzPr1G0gE0PNt",
    "status": "fldnPsJekI64Qiu9q", "aangemeld_op": "fldeZutnwoHAVOTdT", "totaal": "fldfzvJMyX5602sui",
    "betaling": "fldAq1LB0aGgTpQj1", "betaalstatus": "fld7fVFIyNqSTzJwP", "bron": "fldFF26YmR38twzpy",
    "notities": "fldammF7um7ELLLnJ",
}


def _token():
    return os.environ.get("AIRTABLE_WRITE_TOKEN") or os.environ.get("AIRTABLE_TOKEN")


def _smtp_ready():
    return all(os.environ.get(k) for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "MAIL_FROM"))


def direct_ready():
    """Alleen direct verwerken als zowel Airtable als mail geregeld is."""
    return bool(_token()) and _smtp_ready()


def cohort(p):
    if p.get("optie_nr") == 1:
        return "Los / eigen tempo"
    if (p.get("startdatum") or "")[:7] in ("2027-01", "2027-02", "2027-03"):
        return "Cohort 2 (jan 2027)"
    return None


def notities(p):
    examen = "ja" if p["examen"] else "nee"
    if p.get("examen_bijgeboekt"):
        examen += f" (bijgeboekt, route: {p.get('examenroute') or '–'})"
    regels = " + ".join(r["omschrijving"] for r in p["prijsregels"])
    return "\n".join([
        "Aanmelding via de nieuwe site.",
        f"Optie: {p.get('optie_nr') or ''} {p.get('optie') or ''}".rstrip(),
        f"Examen: {examen}",
        f"Startmoment: {p['startmoment']}",
        f"Variant: {p.get('variant_sku') or ''}",
        f"Factuur: {p['factuur']} {p.get('bedrijfsnaam') or ''}".rstrip(),
        f"Adres: {p['straat']}, {p['postcode']} {p['plaats']}",
        f"Prijsregels: {regels}",
        f"Opmerking: {p.get('opmerking') or ''}",
    ])


def airtable_fields(p):
    dag = datetime.fromisoformat(p["aangemeld_op"]).astimezone(ZoneInfo("Europe/Amsterdam")).date().isoformat()
    fields = {
        F["naam"]: f"{p['voornaam']} {p['achternaam']} – {p['product']}",
        F["voornaam"]: p["voornaam"], F["achternaam"]: p["achternaam"],
        F["email"]: p["email"], F["telefoon"]: p["telefoon"],
        F["opleiding"]: [p["product"]],
        F["locatie"]: p.get("locatie"), F["startdatum"]: p.get("startdatum"),
        F["cohort"]: cohort(p),
        F["status"]: "Aangemeld", F["betaalstatus"]: "Open", F["bron"]: "Website / WooCommerce",
        F["aangemeld_op"]: dag, F["totaal"]: p["totaal"],
        F["betaling"]: "Vijf termijnen" if p["betaling"] == "termijnen" else "Ineens",
        F["notities"]: notities(p),
    }
    return {k: v for k, v in fields.items() if v not in (None, "")}


def schrijf_airtable(p):
    """Maakt de inschrijving aan en geeft het record-ID terug."""
    r = requests.post(
        f"https://api.airtable.com/v0/{BASE_ID}/{INSCHRIJVINGEN}",
        headers={"Authorization": f"Bearer {_token()}"},
        json={"records": [{"fields": airtable_fields(p)}], "typecast": True},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()["records"][0]["id"]


# ---------- mail ----------

def _e(x):
    return html.escape(str(x)) if x not in (None, "") else "–"


def _eur(n):
    return f"€{n:,.0f}".replace(",", ".")


HANDTEKENING = (
    '<p style="margin-top:24px">Olivier van Hees<br>'
    '<span style="color:#1F3F2A;font-weight:bold">The Italian Wine &amp; Food Academy</span><br>'
    f'<a href="{SITE}" style="color:#8A3B43">italianwineandfoodacademy.com</a></p>'
)


def bevestiging_html(p):
    rij = '<tr><td style="color:#5d5d5d;width:40%">{}</td><td>{}</td></tr>'
    rijen = "".join([
        rij.format("Opleiding", f"<strong>{_e(p['product'])}</strong>"),
        rij.format("Leeroptie", _e(p.get("optie"))),
        rij.format("Examen", "Ja" if p["examen"] else "Nee"),
        rij.format("Start", _e(p["startmoment"])),
        rij.format("Praktijkdagen", _e(p.get("locatie"))),
        rij.format("Betaling", "In vijf termijnen" if p["betaling"] == "termijnen" else "In één keer"),
    ])
    totaal = (f'<tr><td style="border-top:2px solid #1F3F2A"><strong>Totaal, btw-vrij</strong></td>'
              f'<td style="border-top:2px solid #1F3F2A"><strong>{_eur(p["totaal"])}</strong></td></tr>')
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#1A1A1A;max-width:600px">'
        f"<p>Beste {_e(p['voornaam'])},</p>"
        f"<p>Grazie voor je aanmelding voor de {_e(p['product'])}. We hebben hem goed ontvangen. "
        "Hieronder staat wat je hebt gekozen.</p>"
        f'<table cellpadding="8" cellspacing="0" style="border-collapse:collapse;width:100%;background:#F9F2E5">{rijen}{totaal}</table>'
        "<p>Wat er nu gebeurt: we kijken je aanmelding na en sturen je daarna de factuur en de toegang tot de leeromgeving.</p>"
        "<p>Heb je een vraag, of klopt er iets niet? Beantwoord deze mail, dan kijk ik ernaar.</p>"
        f"<p>Tot snel in de keuken,</p>{HANDTEKENING}</div>"
    )


def melding_html(p, record_id):
    return (
        '<div style="font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6">'
        "<p>Er is een nieuwe aanmelding binnen via de site.</p>"
        f"<p><strong>{_e(p['voornaam'])} {_e(p['achternaam'])}</strong><br>{_e(p['email'])} · {_e(p['telefoon'])}</p>"
        f"<p>{_e(p['product'])}<br>Optie: {_e(p.get('optie'))}<br>"
        f"Examen: {'ja' if p['examen'] else 'nee'} {_e(p.get('examenroute')) if p.get('examenroute') else ''}<br>"
        f"Start: {_e(p['startmoment'])}<br>Locatie: {_e(p.get('locatie'))}<br>"
        f"Betaling: {_e(p['betaling'])} · factuur {_e(p['factuur'])} {_e(p.get('bedrijfsnaam')) if p.get('bedrijfsnaam') else ''}<br>"
        f"Totaal: {_eur(p['totaal'])}</p><p>Opmerking: {_e(p.get('opmerking'))}</p>"
        f'<p><a href="https://airtable.com/{BASE_ID}/{INSCHRIJVINGEN}/{record_id}">Open de inschrijving in Airtable</a></p></div>'
    )


def _bericht(to, subject, body, reply_to=None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = os.environ["MAIL_FROM"], to, subject
    m["Message-ID"] = make_msgid(domain="italianwineandfoodacademy.com")
    if reply_to:
        m["Reply-To"] = reply_to
    m.set_content("Deze mail is in HTML opgemaakt. Open hem in een mailprogramma dat HTML toont.")
    m.add_alternative(body, subtype="html")
    return m


def verstuur_mails(p, record_id):
    """Bevestiging naar de cursist en melding naar TWFA, in één SMTP-sessie."""
    port = int(os.environ.get("SMTP_PORT", "587"))
    notify = os.environ.get("MAIL_NOTIFY") or os.environ["SMTP_USER"]
    berichten = [
        _bericht(p["email"], f"Je aanmelding voor de {p['product']}", bevestiging_html(p)),
        _bericht(notify, f"Nieuwe aanmelding: {p['voornaam']} {p['achternaam']} – {p['product']} ({_eur(p['totaal'])})",
                 melding_html(p, record_id), reply_to=p["email"]),
    ]
    with smtplib.SMTP(os.environ["SMTP_HOST"], port, timeout=15) as s:
        s.starttls()
        s.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"].replace(" ", ""))
        for m in berichten:
            s.send_message(m)
