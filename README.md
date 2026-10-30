# Wishly 1.6 — GitHub Pages + eigen API

**GitHub Pages host alleen de frontend.** Inloggen, cadeaus, foto's en reserveringen blijven op je eigen server in SQLite. Publiceer nooit `data/`, `.env` of de SQLite-databank op GitHub.

## 1. GitHub Pages
1. Maak een repository `wishly` aan op GitHub. Upload de inhoud van **deze map**, inclusief de verborgen map `.github` (niet alleen `docs`).
2. Wijzig `docs/config.js`: zet `window.WISHLY_API_ORIGIN` op `https://api.jouwdomein.be`.
3. Ga naar **Settings > Pages** en kies **GitHub Actions** bij *Build and deployment*.
4. Push naar `main`. De workflow `.github/workflows/pages.yml` publiceert de map `docs`.
5. Configureer bij voorkeur een eigen domein `wishly.jouwdomein.be` bij GitHub Pages en je DNS-provider. Maak in `docs/` een bestand `CNAME` met alleen de domeinnaam (kopieer `CNAME.example`). Activeer *Enforce HTTPS* zodra het beschikbaar is.

**Belangrijk:** `gebruikersnaam.github.io/wishly/` is geschikt als weergavetest, maar voor werkende login op een API onder een ander domein is een eigen frontend-domein onder **hetzelfde hoofddomein** nodig. Cookies van andere sites worden door browsers vaak geblokkeerd.

## 2. API op eigen server (Linux + Docker)
1. Kopieer `server.py`, `Dockerfile`, `compose.yaml`, `Caddyfile`, `backup.py`, `.env.example` naar je server. Maak `data/` aan en kopieer indien nodig je bestaande `wishly.sqlite3` naar `data/wishly.sqlite3`.
2. `cp .env.example .env` en stel je echte API-host en frontend-URL in.
3. Zorg dat DNS `api.jouwdomein.be` naar de server verwijst en poorten 80/443 bereikbaar zijn.
4. `docker compose config` en `docker compose up -d --build`.
5. Test `https://api.jouwdomein.be/api/me` (antwoord met `user: null` zolang je niet ingelogd bent).
6. Maak een account door registratie **tijdelijk** aan te zetten (`WISHLY_ALLOW_REGISTRATION=1`), voer `docker compose up -d` uit; maak jouw account aan en zet registratie weer op `0`.
7. Test login, toevoegen, wijzigen, delen, reserveren als gast en afmelden. Controleer op verschillende apparaten dat de eigenaar geen reserveringen kan zien.
8. Plan een dagelijkse SQLite-back-up met `backup.py` en kopieer die naar een tweede locatie. Test minstens één herstel.

## 3. Nog te controleren voor publiek gebruik
- Verifieer de exacte server/hosting, DNS, TLS en firewall.
- Verifieer cookiegedrag op iOS Safari en Android Chrome.
- Stel reverse-proxy rate limits en monitoring in; de bestaande limiter gebruikt procesgeheugen en is niet robuust achter gedeelde proxy-IP's.
- Implementeer wachtwoordherstel en accountbeheer, of documenteer een handmatige herstelprocedure.
- Voeg logging en hersteltests toe en voer een onafhankelijke beveiligingsreview uit.
- Webshopimport staat in productie bewust uit wegens SSRF-/netwerkrisico's; handmatige invoer en upload blijven werken.
- GitHub Pages is **niet privé**: alle code in `docs/` is publiek opvraagbaar.
- De `?w=` deellink is een geheim: deel hem alleen met vertrouwde personen.

Geen automatische deployment van backend vanuit GitHub Actions: hiervoor is nog een server-authenticatie en beveiligde deploymentprocedure nodig.
