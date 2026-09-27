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

Het scenario staat al klaar in Make: *TWFA — Aanmelding site → Inschrijvingen + bevestiging*
(scenario 9875320, webhook `https://hook.eu2.make.com/pbg7fedww8h8odbt67ovohrc2lpm422x`).
Het maakt een regel in Airtable › Teacher portal TWFA › TWFA Inschrijvingen, stuurt de cursist een
bevestiging vanaf olivier@thewineandfoodacademy.com en stuurt Olivier een seintje. Per aanmelding komt er één JSON binnen met deze velden:

`bron, aangemeld_op, product_slug, product, optie_nr, optie, examen, examen_bijgeboekt,
examenroute (werkplek|portfolio), locatie, startmoment, regio, voornaam, achternaam, email,
telefoon, factuur (particulier|zakelijk), bedrijfsnaam, straat, postcode, plaats,
betaling (ineens|termijnen), opmerking, prijsregels[], totaal`

De bedanktpagina belooft de bevestigingsmail binnen een paar minuten, dus zet het scenario aan
voordat de site live gaat.

Werkt de webhook niet, dan krijgt de bezoeker een foutmelding met het mailadres
en blijft het ingevulde formulier staan. Er wordt geen persoonsgegeven gelogd.

## Nog te doen

- Echte startmomenten invullen in `catalog.py` (nu alleen "Januari 2027").
- Factuur en termijnen: nu gaat alles via Make. Online betalen (Mollie) kan later.
- LearnDash-toegang na betaling koppelen via Make.
- Redirects van het oude domein zodra de nieuwe site live gaat.
