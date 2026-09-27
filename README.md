# TWFA-site in Flask

Product- en aanmeldpagina's van The Italian Wine & Food Academy, zonder WordPress.
De leeromgeving blijft op WordPress/LearnDash.

## Wat erin zit

| Route | Wat |
|---|---|
| `/opleidingen/` | Overzicht van het aanbod |
| `/product/<slug>/` | Productpagina, met de drie opties voor Gastronomie, Keuken en Wijn |
| `/aanmelden/<slug>/?optie=...` | Aanmeldformulier, stuurt naar Make |
| `/aanmelden/bedankt/` | Bevestiging met prijsoverzicht |

De slugs zijn dezelfde als op de huidige site (`/product/opleiding-italiaanse-gastronomie/` enz.),
zodat bestaande links en Google-posities blijven werken na de overstap.

## Prijzen en aanbod aanpassen

Alles staat in `catalog.py`: producten, opties, kenmerken, prijzen, examen-add-on,
startmomenten en regio's. De server rekent de prijs zelf uit; het bedrag uit de
browser wordt nooit vertrouwd.

## Lokaal draaien

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # vul SECRET_KEY en MAKE_WEBHOOK_URL in
    flask --app app run --debug

Productie: `gunicorn app:app`.

## Make-koppeling

Maak in Make een scenario met trigger *Webhooks > Custom webhook* en zet de URL in
`MAKE_WEBHOOK_URL`. Per aanmelding komt er één JSON binnen met deze velden:

`bron, aangemeld_op, product_slug, product, optie_nr, optie, examen, examen_bijgeboekt,
examenroute (werkplek|portfolio), locatie, startmoment, regio, voornaam, achternaam, email,
telefoon, factuur (particulier|zakelijk), bedrijfsnaam, straat, postcode, plaats,
betaling (ineens|termijnen), opmerking, prijsregels[], totaal`

Map die in Make naar de inschrijvingentabel in Airtable, en laat Make ook de
bevestigingsmail sturen. De bedanktpagina belooft die mail binnen een paar minuten.

Werkt de webhook niet, dan krijgt de bezoeker een foutmelding met het mailadres
en blijft het ingevulde formulier staan. Er wordt geen persoonsgegeven gelogd.

## Nog te doen

- Echte startmomenten invullen in `catalog.py` (nu alleen "Januari 2027").
- Factuur en termijnen: nu gaat alles via Make. Online betalen (Mollie) kan later.
- LearnDash-toegang na betaling koppelen via Make.
- Redirects van het oude domein zodra de nieuwe site live gaat.
