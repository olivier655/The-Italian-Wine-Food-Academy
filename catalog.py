"""Het TWFA-aanbod: één plek voor producten, opties en prijzen.

Prijzen aanpassen? Alleen hier. De productpagina's, het aanmeldformulier
en de prijsberekening op de server lezen allemaal uit deze file.
Alle bedragen zijn btw-vrij (CRKBO).
"""

NLQF_STATUS = (
    "De inschaling van het diploma op NLQF niveau 4 is aangevraagd "
    "en in behandeling bij het NCP NLQF."
)

# TODO Olivier: echte startmomenten invullen.
STARTMOMENTEN = ["Januari 2027"]
LOCATIES = ["Amsterdam", "Zeist"]

REGIOS = [
    "Italiaanse Wijn & Spijs · Piemonte",
    "Wijn uit Piemonte",
    "Wijn & Spijs Veneto",
    "Wijn uit Veneto",
    "Pasta Fresca",
    "Wijn uit Toscane",
    "Romeinse Pasta's",
    "Wijn uit Midden-Italië",
    "Pizza Napoletana",
    "Wijn uit Zuid-Italië",
]

_ONLINE_BASIS = [
    "Toegang tot de online leeromgeving",
    "Instructievideo's per techniek en per regio",
    "Kook- en proefopdrachten voor thuis",
    "Begeleiding van je docent wanneer jij die nodig hebt",
]
_WEKELIJKS = [
    "Elke week een live les via Google Meet",
    "Vaste groep van maximaal vier personen",
    "Je docent bespreekt je huiswerk met de groep",
]


def _tiers(prijs1, prijs2, prijs3, praktijk, afsluiting):
    return [
        {
            "key": "eigen-tempo",
            "naam": "In je eigen tempo",
            "voor_wie": "Voor wie zelf oefent en de docent erbij haalt wanneer dat nodig is.",
            "prijs": prijs1,
            "praktijk": False,
            "examen_inbegrepen": False,
            "plus_label": None,
            "kenmerken": _ONLINE_BASIS,
        },
        {
            "key": "wekelijkse-les",
            "naam": "Met wekelijkse les",
            "voor_wie": "Voor wie leert met een vast ritme, een vaste docent en een kleine groep.",
            "prijs": prijs2,
            "praktijk": False,
            "examen_inbegrepen": False,
            "plus_label": "Alles uit optie 1, plus:",
            "kenmerken": _WEKELIJKS,
        },
        {
            "key": "met-praktijk",
            "naam": "De volledige opleiding",
            "voor_wie": "Voor wie het vak ook met de handen wil leren, in de keuken én aan tafel.",
            "prijs": prijs3,
            "praktijk": True,
            "examen_inbegrepen": True,
            "plus_label": "Alles uit optie 2, plus:",
            "kenmerken": praktijk + [afsluiting],
        },
    ]


PRODUCTS = {
    "opleiding-italiaanse-gastronomie": {
        "naam": "Opleiding Italiaanse Gastronomie",
        "soort": "opties",
        "kort": "Keuken én wijn, alle zestien regio's, in één studiejaar.",
        "duur": "36 weken",
        "afsluiting": "Diploma Opleiding Italiaanse Gastronomie",
        "nlqf": True,
        "examen_addon": 495,
        "opties": _tiers(
            995, 1795, 3450,
            [
                "Elke maand een praktijkdag in onze kookstudio in Amsterdam of Zeist",
                "Alle wijnen en ingrediënten op de praktijkdagen",
                "Samen lunchen met wat je zelf hebt gekookt",
                "Koks- én sommelierstarterspakket",
                "Stage en eindopdracht",
            ],
            "Examen en Diploma Opleiding Italiaanse Gastronomie",
        ),
    },
    "italiaanse-keuken": {
        "naam": "Italiaanse Keuken",
        "soort": "opties",
        "kort": "Koken als een Italiaan, van verse pasta tot pizza napoletana uit de houtoven.",
        "duur": "15 weken",
        "afsluiting": "CRKBO-certificaat",
        "nlqf": False,
        "examen_addon": 295,
        "opties": _tiers(
            595, 995, 1950,
            [
                "Een praktijkdag per blok, vijf in totaal",
                "Alle ingrediënten op de praktijkdagen",
                "Koks starterspakket",
                "Eindopdracht",
            ],
            "Examen en CRKBO-certificaat",
        ),
    },
    "italiaanse-wijn": {
        "naam": "Italiaanse Wijn",
        "soort": "opties",
        "kort": "Van Barolo en Brunello tot de vulkanische hellingen van de Etna.",
        "duur": "15 weken",
        "afsluiting": "CRKBO-certificaat",
        "nlqf": False,
        "examen_addon": 295,
        "opties": _tiers(
            595, 995, 1950,
            [
                "Een praktijkdag per blok, vijf in totaal",
                "Zes wijnen per praktijkdag",
                "Sommelier starterspakket",
                "Eindopdracht",
            ],
            "Examen en CRKBO-certificaat",
        ),
    },
    "regiocursus": {
        "naam": "Regiocursus",
        "soort": "enkel",
        "kort": "Eén regio in drie weken: twee weken online en één praktijkdag in de studio.",
        "duur": "3 weken",
        "afsluiting": "CRKBO-certificaat",
        "nlqf": False,
        "prijs": 595,
        "praktijk": True,
        "kies_regio": True,
    },
    "gastronomie-en-ondernemerschap": {
        "naam": "Gastronomie & Ondernemerschap",
        "soort": "enkel",
        "kort": "Zes weken een-op-een begeleiding bij je eigen businessplan. Start wanneer je wilt.",
        "duur": "6 weken",
        "afsluiting": "Certificaat",
        "nlqf": False,
        "prijs": 595,
        "praktijk": False,
        "kies_regio": False,
    },
}


def get_option(product, key):
    for i, opt in enumerate(product.get("opties", []), start=1):
        if opt["key"] == key:
            return i, opt
    return None, None


def calculate(product_slug, option_key=None, examen=False):
    """Prijs op de server berekenen. Nooit het bedrag uit het formulier vertrouwen."""
    product = PRODUCTS[product_slug]
    lines = []
    if product["soort"] == "enkel":
        lines.append((product["naam"], product["prijs"]))
    else:
        nr, opt = get_option(product, option_key)
        if opt is None:
            raise ValueError("Onbekende optie")
        lines.append((f"{product['naam']} · optie {nr}: {opt['naam']}", opt["prijs"]))
        if examen and not opt["examen_inbegrepen"]:
            lines.append((f"Examen en {product['afsluiting']}", product["examen_addon"]))
    return lines, sum(p for _, p in lines)


def euro(value):
    return "€" + f"{value:,.0f}".replace(",", ".")
