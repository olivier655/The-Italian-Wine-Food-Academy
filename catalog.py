"""Het TWFA-aanbod.

Wat live uit Airtable komt (via airtable.py): welke producten er zijn, hun
naam, korte beschrijving, duur, prijs, status en de startmomenten per
locatie (de varianten). Prijs aanpassen, startdatum toevoegen of een product
offline halen doe je dus in Airtable, tabel TWFA Producten.

Wat hier in de code staat, omdat Airtable er (nog) geen velden voor heeft:
de drie leeropties van Gastronomie, Keuken en Wijn (de prijs van optie 3 is
de Airtable-prijs, optie 1 en 2 staan hieronder), de examen-add-on, en de
lange productteksten in content/producten.json.

Alle bedragen zijn btw-vrij (CRKBO).
"""
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import airtable

NLQF_STATUS = (
    "De inschaling van het diploma op NLQF niveau 4 is aangevraagd "
    "en in behandeling bij het NCP NLQF."
)
LOCATIES = ["Amsterdam", "Zeist"]
TZ = ZoneInfo("Europe/Amsterdam")

CONTENT = json.loads((Path(__file__).parent / "content" / "producten.json").read_text(encoding="utf-8"))

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

# Leeropties per product: prijs optie 1, prijs optie 2, examen-add-on, praktijkpunten.
# De prijs van optie 3 komt uit Airtable.
TIERS = {
    "opleiding-italiaanse-gastronomie": dict(
        p1=995, p2=1795, examen_addon=495, nlqf=True,
        afsluiting="Diploma Opleiding Italiaanse Gastronomie",
        praktijk=[
            "Elke maand een praktijkdag in onze kookstudio in Amsterdam of Zeist",
            "Alle wijnen en ingrediënten op de praktijkdagen",
            "Samen lunchen met wat je zelf hebt gekookt",
            "Koks- én sommelierstarterspakket",
            "Stage en eindopdracht",
        ],
        slot="Examen en Diploma Opleiding Italiaanse Gastronomie",
    ),
    "italiaanse-keuken": dict(
        p1=595, p2=995, examen_addon=295, nlqf=False, afsluiting="CRKBO-certificaat",
        praktijk=[
            "Een praktijkdag per blok, vijf in totaal",
            "Alle ingrediënten op de praktijkdagen",
            "Koks starterspakket",
            "Eindopdracht",
        ],
        slot="Examen en CRKBO-certificaat",
    ),
    "italiaanse-wijn": dict(
        p1=595, p2=995, examen_addon=295, nlqf=False, afsluiting="CRKBO-certificaat",
        praktijk=[
            "Een praktijkdag per blok, vijf in totaal",
            "Zes wijnen per praktijkdag",
            "Sommelier starterspakket",
            "Eindopdracht",
        ],
        slot="Examen en CRKBO-certificaat",
    ),
}

# Volgorde en groepen op het overzicht
GROEPEN = [
    ("opleiding", "De opleiding", "Keuken én wijn, met een erkend diploma."),
    ("certificaat", "Certificaatprogramma's", "Italiaanse keuken óf Italiaanse wijn, vijftien weken, met een CRKBO-certificaat."),
    ("kook", "Kookcursussen", "Eén streek, drie weken, één praktijkdag in de kookstudio."),
    ("wijn", "Wijncursussen", "Eén wijnstreek, drie weken, één proefdag."),
    ("wijnspijs", "Wijn & spijs", "Leren combineren, drie weken, één praktijkdag."),
    ("los", "Losse modules", "Individueel, start wanneer je wilt."),
]
_GROEP_VAN_SKU = {
    "TWFA-DIPL": "opleiding", "TWFA-KEUKEN": "certificaat", "TWFA-WIJN": "certificaat",
    "TWFA-ONDERNEMEN": "los",
}

MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli",
           "augustus", "september", "oktober", "november", "december"]
DAGEN = ["ma", "di", "wo", "do", "vr", "za", "zo"]


def vandaag():
    return datetime.now(TZ).date()


def datum_lang(iso):
    d = date.fromisoformat(iso)
    return f"{DAGEN[d.weekday()]} {d.day} {MAANDEN[d.month - 1]} {d.year}"


def _tiers(slug, prijs3):
    t = TIERS[slug]
    return [
        {"key": "eigen-tempo", "naam": "In je eigen tempo",
         "voor_wie": "Voor wie zelf oefent en de docent erbij haalt wanneer dat nodig is.",
         "prijs": t["p1"], "praktijk": False, "cohort": False, "examen_inbegrepen": False,
         "plus_label": None, "kenmerken": _ONLINE_BASIS},
        {"key": "wekelijkse-les", "naam": "Met wekelijkse les",
         "voor_wie": "Voor wie leert met een vast ritme, een vaste docent en een kleine groep.",
         "prijs": t["p2"], "praktijk": False, "cohort": True, "examen_inbegrepen": False,
         "plus_label": "Alles uit optie 1, plus:", "kenmerken": _WEKELIJKS},
        {"key": "met-praktijk", "naam": "De volledige opleiding",
         "voor_wie": "Voor wie het vak ook met de handen wil leren, in de keuken én aan tafel.",
         "prijs": prijs3, "praktijk": True, "cohort": True, "examen_inbegrepen": True,
         "plus_label": "Alles uit optie 2, plus:", "kenmerken": t["praktijk"] + [t["slot"]]},
    ]


def _groep(p):
    if p["sku"] in _GROEP_VAN_SKU:
        return _GROEP_VAN_SKU[p["sku"]]
    soort = p.get("soort") or []
    if "Wijn spijs" in soort:
        return "wijnspijs"
    if "Kookcursus" in soort:
        return "kook"
    return "wijn"


def products(include_concept=False):
    """Alle producten, op volgorde, als dict slug -> product."""
    d = airtable.data()
    today = vandaag().isoformat()
    starts = {}
    for v in d["varianten"]:
        if v.get("status") != "publish" or not v.get("startdatum") or v["startdatum"] < today:
            continue
        if v.get("locatie") not in LOCATIES:
            continue
        starts.setdefault(v["hoofd_sku"], []).append({
            "sku": v["sku"], "datum": v["startdatum"], "locatie": v["locatie"],
            "label": f"{datum_lang(v['startdatum'])} · {v['locatie']}",
        })
    out = {}
    for p in d["producten"]:
        if not p.get("slug") or p.get("prijs") is None:
            continue
        if p.get("status") != "Gepubliceerd" and not include_concept:
            continue
        slug = p["slug"]
        groep = _groep(p)
        prod = {
            "sku": p["sku"], "naam": p["naam"], "kort": p.get("kort") or "",
            "duur": p.get("duur") or "", "brochure": p.get("brochure"),
            "groep": groep, "content": CONTENT.get(slug, {}),
            "starts": sorted(starts.get(p["sku"], []), key=lambda s: (s["datum"], s["locatie"])),
        }
        if slug in TIERS:
            t = TIERS[slug]
            prod.update(soort="opties", afsluiting=t["afsluiting"], nlqf=t["nlqf"],
                        examen_addon=t["examen_addon"], opties=_tiers(slug, p["prijs"]))
        else:
            prod.update(soort="enkel", prijs=p["prijs"], nlqf=False,
                        afsluiting="Certificaat" if groep == "los" else "CRKBO-certificaat",
                        praktijk=groep != "los")
        out[slug] = prod
    order = {g[0]: i for i, g in enumerate(GROEPEN)}
    return dict(sorted(out.items(), key=lambda kv: order[kv[1]["groep"]]))


def grouped():
    prods = products()
    return [(key, titel, uitleg, [(s, p) for s, p in prods.items() if p["groep"] == key])
            for key, titel, uitleg in GROEPEN
            if any(p["groep"] == key for p in prods.values())]


def cohort_dates(product):
    """Unieke startdata (voor optie 2: wel een groep, geen locatie)."""
    seen = {}
    for s in product["starts"]:
        seen.setdefault(s["datum"], datum_lang(s["datum"]))
    return list(seen.items())


def get_option(product, key):
    for i, opt in enumerate(product.get("opties", []), start=1):
        if opt["key"] == key:
            return i, opt
    return None, None


def vanaf(product):
    return product["opties"][0]["prijs"] if product["soort"] == "opties" else product["prijs"]


def calculate(product, option_key=None, examen=False):
    """Prijs op de server berekenen. Nooit het bedrag uit het formulier vertrouwen."""
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
