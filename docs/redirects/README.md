# Oude domein doorverwijzen (voor Jenny)

Doel: thewineandfoodacademy.com stuurt bezoekers met een **301** door naar italianwineandfoodacademy.com. De leeromgeving (LearnDash/BuddyBoss), het betalen (WooCommerce/Mollie) en WordPress zelf blijven op het oude domein werken.

## Wat blijft op het oude domein

`/wp-admin`, `/wp-login.php`, `/wp-json`, `/wp-content` (ook brochures en PDF's), `/wp-includes`, `/mijn-profiel`, `/my-account`, `/checkout`, `/cart`, `/courses`, `/groups`, `/members`, `/activity`, `/quizzes`, `/certificates`, `/feedback`, `/edu-dex-xml-files` (feed), de wijnproefpakketten (`/product/wijnproefpakket-…`) en de eventpagina's (`/the-wine-food-academy-event`, `/bestel-kaarten-event`). Ook de `/en/`-varianten daarvan. POST-verzoeken en WooCommerce-/LearnDash-parameters (`wc-ajax`, `add-to-cart`, `ld_…`) worden niet doorgestuurd.

## De rest

- **Specifieke adressen** (stadspagina's, docentposts, oude blogposts, voorwaarden, examen, SLIM): zie `overzicht.csv`.
- **Vangnet**: alles wat overblijft gaat naar hetzelfde pad op het nieuwe domein (bv. `/product/pasta-fresca/`, `/piemonte/`, `/opleidingen/`). Engelse `/en/…`-pagina's gaan naar de Nederlandse pagina.

## Twee manieren (kies er één)

1. **Redirection-plugin in WordPress** (makkelijkst bij managed hosting): Tools → Redirection → Import/Export → importeer `redirection-import.csv` (regex aan, 301). De volgorde telt: specifieke regels eerst, vangnet als laatste.
2. **nginx bij Nexcess** (sneller, WordPress hoeft er niet voor te draaien): `nginx-oud-domein.conf` in de server-blok van het oude domein, boven de WordPress-regels. Eerst op staging testen.

## Daarna

1. In WordPress: Instellingen → Lezen → "Zoekmachines ontmoedigen" **aan** (noindex voor de leeromgeving). **Géén** `Disallow` in robots.txt, anders ziet Google de 301's niet.
2. Testen: inloggen, een les openen, een groepspagina, afrekenen van een wijnproefpakket, `/wp-admin`, en een paar oude adressen uit `overzicht.csv`.
3. Search Console: property voor italianwineandfoodacademy.com (DNS-TXT bij Hostnet), sitemap `https://italianwineandfoodacademy.com/sitemap.xml` indienen. Change of Address kan geprobeerd worden zodra de homepage doorverwijst.
4. Redirects **permanent laten staan** en het oude domein blijven verlengen.
