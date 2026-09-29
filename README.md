# TWFA-site in Flask

De publieke site van The Italian Wine & Food Academy, zonder WordPress: producten, aanmelden en de belangrijkste contentpagina's. De leeromgeving blijft op WordPress/LearnDash. Draait op Render (`twfa-site`), met italianwineandfoodacademy.com als domein.

## Pagina's

| Route | Wat |
|---|---|
| `/` | Homepage |
| `/opleidingen/` | Overzicht, per groep (opleiding, certificaten, kook, wijn, wijn & spijs) |
| `/product/<slug>/` | Productpagina, zelfde slugs als de oude site |
| `/aanmelden/<slug>/` | Aanmeldformulier: schrijft direct naar Airtable en mailt (Make als reserve) |
| `/leermethode/`, `/kookstudio/`, `/docenten/` | Contentpagina's |
| `/piemonte/`, `/lombardije/`, `/ligurie/`, `/toscane/` | Streekpagina's uit het contentplan |
| `/healthz` | Laat zien of de gegevens live uit Airtable komen (`"bron": "airtable"`) |

`/product/regiocursus/` stuurt door naar het overzicht.

## Waar wat staat

- **Airtable** (base Teacher portal TWFA) is leidend voor producten, prijzen, korte beschrijvingen, status en startmomenten (tabel TWFA Producten: hoofdproducten + varianten), en voor de docenten (tabel Teachers, Brand = TWFA, On website aan). Wijzig je daar iets, dan staat het binnen vijf minuten op de site.
  - Alleen hoofdproducten met status *Gepubliceerd* komen online.
  - Alleen varianten met status *publish* en een startdatum vanaf vandaag worden startmomenten; de locatie komt uit de naam (Amsterdam/Zeist).
- **`catalog.py`**: de drie leeropties van Gastronomie, Keuken en Wijn. De prijs van optie 3 is de Airtable-prijs; optie 1, 2 en de examen-add-on staan hier.
- **`content/producten.json`**: de lange productteksten (verwachtingen, programma per week, wat erbij zit, leerdoelen, docenten).
- **`content/streken.json`**: de streekpagina's.
- **`data/snapshot.json`**: momentopname van Airtable. Wordt gebruikt als `AIRTABLE_TOKEN` ontbreekt of Airtable niet antwoordt, zodat de site altijd blijft werken.

## Omgevingsvariabelen (Render → Environment)

| Naam | Waarde |
|---|---|
| `SECRET_KEY` | lange willekeurige tekst |
| `AIRTABLE_TOKEN` | personal access token, scope `data.records:read`, alleen base Teacher portal TWFA |
| `AIRTABLE_WRITE_TOKEN` | personal access token, scope `data.records:write`, alleen base Teacher portal TWFA |
| `SMTP_HOST` / `SMTP_PORT` | `smtp.gmail.com` / `587` |
| `SMTP_USER` / `SMTP_PASSWORD` | Google-account + app-wachtwoord |
| `MAIL_FROM` / `MAIL_NOTIFY` | afzender van de bevestiging / wie de melding krijgt |
| `MAKE_WEBHOOK_URL` | reserve: webhook van Make-scenario 9875320 |
| `MAKE_FOLLOWUP_URL` | optioneel: seintje met record-ID na directe verwerking |

## Lokaal draaien en testen

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt -r requirements-dev.txt
    cp .env.example .env
    flask --app app run --debug
    python -m pytest -q

Productie: `gunicorn app:app`.

## Aanmelding

De server rekent de prijs zelf uit en controleert dat het gekozen startmoment bij het product hoort. Daarna (`verwerk()` in `app.py`, code in `inschrijving.py`):

1. **Direct**, als `AIRTABLE_WRITE_TOKEN` en de SMTP-variabelen gevuld zijn: record in TWFA Inschrijvingen (zelfde velden als het Make-scenario), bevestigingsmail naar de cursist en een melding naar `MAIL_NOTIFY`. Een mislukte mail blokkeert de aanmelding niet; het record staat er dan al.
2. **Reserve**: lukt Airtable niet, of is direct nog niet ingesteld, dan gaat de aanmelding naar `MAKE_WEBHOOK_URL` (scenario 9875320 doet dan record + mails).

Payload (ook naar Make): `bron, aangemeld_op, product_slug, product_sku, product, optie_nr, optie, examen, examen_bijgeboekt, examenroute, variant_sku, startdatum, startmoment, locatie, voornaam, achternaam, email, telefoon, factuur, bedrijfsnaam, straat, postcode, plaats, betaling (ineens|termijnen), opmerking, prijsregels[], totaal`.

Hoe het daarna verder moet lopen (orders, controle, Moneybird, LearnDash) staat in het plan *Orderdatabase TWFA*.
