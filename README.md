# Wishly 2.0 — GitHub Pages + Supabase

Een minimalistische mobiele verlanglijst. **GitHub Pages host de interface**; Supabase verzorgt accounts, cadeaus, foto-opslag en gastreserveringen. Geen eigen Python-server of Docker nodig.

Lees eerst **INSTALLATIE.md** voor de complete stappen.

## Onderdelen
- `docs/` — publiceerbare statische website (Syne + Plus Jakarta Sans).
- `supabase/schema.sql` — tabellen, RLS, storage en functies voor gedeelde links.
- `supabase/functions/product-metadata/` — **optionele** Edge Function voor productinformatie van toegelaten webshops.
- `.github/workflows/pages.yml` — GitHub Actions om `docs/` op Pages te zetten.

## Belangrijke veiligheidsgrenzen
- Gebruik in `docs/config.js` uitsluitend de **publishable** (of legacy `anon`) key. Een publieke sleutel is normaal in een browser, **mits RLS correct ingesteld is**.
- Gebruik **nooit** `service_role`, secret keys of databasewachtwoorden in GitHub of de browser.
- De eigenaar kan via de normale API geen reserveringsnamen of reserveringsstatus opvragen. Bezoekers met de geheime link zien wel **of** een cadeau gereserveerd is. Een eigenaar die zelf de publieke link opent kan dat dus ook zien; volledige geheimhouding tegenover de eigenaar is onmogelijk bij anonieme gedeelde toegang.
- Foto's in de publieke storage-bucket zijn voor wie de bestands-URL kent opvraagbaar; upload geen privéfoto's.
- Gastreservering via een geheime link heeft **geen sterke bot-/spamprotectie**. De Edge Function met webshopimport is optioneel, wordt per webshop beperkt en kan worden geblokkeerd.
- Dit is geen onafhankelijke productie-audit. Test RLS en e-mailflows vóór je de link deelt.

Bestaande gegevens in een lokale `wishly.sqlite3` worden niet automatisch gemigreerd.
