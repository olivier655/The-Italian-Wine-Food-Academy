"""Productfeed voor Springest (XML, formaat product_2_6.xsd).

Live op /springest.xml, gebouwd uit dezelfde Airtable-gegevens als de site:
nieuwe startdata of prijzen staan dus vanzelf in de feed. Het wijnproefpakket
en de proefworkshops staan er bewust niet in: alleen opleidingen en cursussen.
"""
import re
from datetime import date, timedelta
from xml.sax.saxutils import escape

VIDEO = "https://vimeo.com/894952354"
MAX_DEELNEMERS = 4

_LEERMETHODE = (
    "<p>Zo leer je bij The Italian Wine &amp; Food Academy: je werkt online in je eigen tempo met "
    "instructievideo's en kook- en proefopdrachten voor thuis. Elke week is er een live les in een vaste "
    "groep van maximaal vier personen, waarin je docent je huiswerk bespreekt. Op de praktijkdag sta je "
    "met Italiaanse koks en Nederlandse sommeliers in onze kookstudio in Amsterdam of Zeist, en na afloop "
    "eet je samen wat je zelf hebt gekookt. Keuken en wijn leer je bij ons niet als twee vakken maar als één geheel.</p>"
    "<p>The Italian Wine &amp; Food Academy is NRTO-lid en CRKBO-geregistreerd; de cursus is daardoor vrijgesteld van btw.</p>"
)

_OMSCHRIJVING = {
    "opleiding-italiaanse-gastronomie": (
        "<p>De Opleiding Italiaanse Gastronomie is een volledig studiejaar van 36 lesweken waarin je Italiaanse keuken "
        "en Italiaanse wijn samen leert, zoals Italianen ze zelf benaderen: wat je drinkt hoort bij wat je eet.</p>"
        "<p>Je reist in vijf blokken door Italië, van Piemonte in het noordwesten tot Sicilië en Sardinië in het zuiden. "
        "Per streek leer je de wijnen, de druiven en de methodes, en kook je de gerechten die erbij horen, van verse pasta "
        "tot pizza napoletana. Je proeft wijnen naast elkaar, leert benoemen wat je proeft en waarom een wijn bij een "
        "gerecht past.</p>"
        "<p>De opleiding is er in drie leeropties: in je eigen tempo, met een wekelijkse live les, of volledig met "
        "maandelijkse praktijkdagen in de kookstudio, stage, eindopdracht en examen. De volledige opleiding sluit af "
        "met het diploma Opleiding Italiaanse Gastronomie.</p>"
    ),
    "italiaanse-keuken": (
        "<p>Italiaanse Keuken is het certificaatprogramma voor wie de keukenkant van de Italiaanse gastronomie wil "
        "beheersen. In vijftien weken leer je koken als een Italiaan: de technieken en signatuurgerechten van noord tot "
        "zuid, van verse pasta en risotto tot pizza napoletana uit de houtoven.</p>"
        "<p>Je werkt per blok van drie weken aan een deel van Italië. Je leert waarom een gerecht in de ene streek zo "
        "anders is dan in de andere, en hoe bloem, deeg, vulling en saus samen een bord maken. Geschikt voor de "
        "gepassioneerde thuiskok en voor professionals, bijvoorbeeld een restaurant dat zijn brigade wil bijscholen.</p>"
        "<p>Er zijn drie leeropties: in je eigen tempo, met een wekelijkse live les, of met een praktijkdag per blok in "
        "de kookstudio. Je sluit af met een CRKBO-certificaat.</p>"
    ),
    "italiaanse-wijn": (
        "<p>Italiaanse Wijn is het certificaatprogramma voor wie de wijnkant van de Italiaanse gastronomie wil beheersen. "
        "In vijftien weken reis je van Barolo en Brunello tot de Etna: streken, druiven en methodes, en proeven volgens "
        "de Klosse-smaakmethode.</p>"
        "<p>Per blok van drie weken proef je de wijnen van een deel van Italië naast elkaar. Je leert kleur, geur en "
        "smaak benoemen, begrijpt waarom een wijn smaakt zoals hij smaakt en wat je erbij eet. Geschikt voor de "
        "liefhebber en voor professionals, bijvoorbeeld in een wijnhandel of bij een importeur.</p>"
        "<p>Er zijn drie leeropties: in je eigen tempo, met een wekelijkse live les, of met een proefdag per blok. "
        "Je sluit af met een CRKBO-certificaat.</p>"
    ),
}


def _weken(duur):
    m = re.search(r"(\d+)\s*(?:les)?weken", duur or "")
    return int(m.group(1)) if m else 3


def _html_uit_content(c):
    delen = []
    for key in ("verwachten", "programma"):
        blok = c.get(key) or {}
        if blok.get("lead"):
            delen.append(f"<p>{escape(blok['lead'])}</p>")
        if blok.get("punten"):
            delen.append("<ul>" + "".join(f"<li>{escape(p)}</li>" for p in blok["punten"]) + "</ul>")
    if c.get("leerdoelen"):
        delen.append("<p><b>Na de cursus:</b></p><ul>" + "".join(f"<li>{escape(p)}</li>" for p in c["leerdoelen"]) + "</ul>")
    if c.get("inbegrepen"):
        delen.append("<p><b>Inbegrepen:</b></p><ul>" + "".join(f"<li>{escape(p)}</li>" for p in c["inbegrepen"]) + "</ul>")
    return "".join(delen)


def omschrijving(slug, product):
    kern = _OMSCHRIJVING.get(slug) or (f"<p>{escape(product['kort'])}</p>" + _html_uit_content(product["content"]))
    return kern + _LEERMETHODE


def woorden(html):
    return len(re.sub(r"<[^>]+>", " ", html).split())


def _el(naam, waarde):
    return f"<{naam}>{escape(str(waarde))}</{naam}>"


def product_xml(slug, p, site, foto_url):
    weken = _weken(p["duur"])
    prijs = p["opties"][-1]["prijs"] if p["soort"] == "opties" else p["prijs"]
    url = f"{site}/product/{slug}/"
    starts = "".join(
        "<StartingDatePlace>"
        + _el("ID", s["sku"]) + _el("Startdate", s["datum"]) + _el("Place", s["locatie"])
        + "<StartdateIsMonthOnly>false</StartdateIsMonthOnly>"
        + _el("Enddate", (date.fromisoformat(s["datum"]) + timedelta(weeks=weeks_or(weken)) - timedelta(days=1)).isoformat())
        + "<EnddateIsMonthOnly>false</EnddateIsMonthOnly>"
        + _el("MaxNumberOfSeats", MAX_DEELNEMERS)
        + "</StartingDatePlace>"
        for s in p["starts"])
    extra = ""
    if p["soort"] == "opties":
        extra = ("<AdditionalCost><Type>examination</Type>" + _el("Price", p["examen_addon"])
                 + "<VatIncluded>exempt</VatIncluded><VatAmount>0</VatAmount><Mandatory>false</Mandatory></AdditionalCost>")
    return (
        "<Product>"
        + _el("ID", p["sku"])
        + f"<Description><![CDATA[{omschrijving(slug, p)}]]></Description>"
        + _el("Name", p["naam"])
        + f"<Images><ImageUrl>{escape(foto_url)}</ImageUrl></Images>"
        + _el("VideoEmbed", VIDEO)
        + _el("Language", "nl")
        + _el("Price", prijs)
        + "<VatIncluded>exempt</VatIncluded><VatAmount>0</VatAmount><PricePeriod>all</PricePeriod>"
        + f"<AdditionalCosts>{extra}</AdditionalCosts>"
        + "<PriceComplete>true</PriceComplete>"
        + _el("CourseType", "opleiding" if p.get("nlqf") else "course")
        + _el("Duration", weken) + "<DurationUnit>weeks</DurationUnit>"
        + _el("StudyLoad", weken) + "<StudyLoadUnit>weeks</StudyLoadUnit>"
        + _el("Completion", p["afsluiting"])
        + _el("MaxParticipants", MAX_DEELNEMERS)
        + _el("WebAddress", url)
        + _el("ProductType", "classroom" if p["starts"] else "elearning")
        + "<AllowedSites/>"
        + ("<Level>MBO</Level>" if p.get("nlqf") else "")
        + "<PriceDiscounts/>"
        + "<Moments><Moment><Name>saturday</Name></Moment><Moment><Name>evening</Name></Moment></Moments>"
        + f"<StartingDatePlaces>{starts}</StartingDatePlaces>"
        + "<customLtiParams/>"
        + "</Product>"
    )


def weeks_or(n):
    return n or 3


def feed(products, site, foto):
    items = "".join(product_xml(slug, p, site, foto(slug)) for slug, p in products.items() if p["groep"] != "los")
    return f'<?xml version="1.0" encoding="UTF-8"?><Products>{items}</Products>'
