# Wishly publiceren — stap voor stap

Dit is voor **GitHub Free + Supabase Free**. Je hebt geen eigen server nodig.

## 1. Supabase-project aanmaken
1. Open https://supabase.com/dashboard, maak een nieuw project `Wishly` op een Europese regio.
2. Onder **Security** bij aanmaken: **Enable Data API AAN**, **Automatically expose new tables UIT**, **Enable automatic RLS AAN** (veilig als extra standaard; ons SQL-script schakelt RLS ook expliciet in).
3. Wacht op de projectconfiguratie. Ga naar **SQL Editor → New query**.
4. Kopieer de **volledige** inhoud van `supabase/schema.sql` en voer eenmaal uit met **Run**. Controleer op fouten.
5. Ga naar **Authentication → Providers → Email**: schakel e-mail/wachtwoord in en houd **Confirm email** ingeschakeld. Zet indien mogelijk na registratie van je eigen account **Allow new users to sign up UIT** (Authentication → Settings) om open registratie te stoppen. Vrienden hebben geen account nodig om een cadeau te reserveren.

## 2. GitHub-repository
1. Maak op https://github.com/new een repository `wishly` met **Public** als je GitHub Free gebruikt. GitHub Pages is op GitHub Free niet beschikbaar voor een private repository.
2. Upload **de inhoud** van deze map in de root van je repo, inclusief `.github/workflows/pages.yml` (makkelijkst via Git of GitHub Desktop; webupload kan verborgen `.github` lastiger maken).
3. Ga naar **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. Onder **Actions** controleer je of de workflow `Publish Wishly frontend` geslaagd is.
5. De site staat daarna doorgaans op `https://GITHUBNAAM.github.io/wishly/` (let op hoofdletters in de repo-naam).

## 3. Supabase aan GitHub koppelen
1. In Supabase Dashboard: **Project Settings → API Keys**. Kopieer **Project URL** en **Publishable key** (of legacy `anon` key). Niet je secret/service_role key.
2. Open in je repository `docs/config.js` en vervang beide placeholders.
3. Commit de wijziging. De GitHub Action publiceert de nieuwe versie.
4. Ga naar **Authentication → URL Configuration**. Zet **Site URL** op `https://GITHUBNAAM.github.io/wishly/`. Voeg dezelfde exacte URL toe onder **Redirect URLs**. Dit is nodig voor bevestigings- en resetmails.
5. Open de website, maak jouw account aan, bevestig je e-mail en log in.

## 4. Testen vóór delen
- Voeg handmatig een cadeau met foto toe en vernieuw de pagina: het moet bewaard blijven.
- Controleer prijsfilters (`< 30`, `30–<100`, `100–200`, `>200`) en categorieën.
- Open **Delen**, kopieer de link en open deze in een privé-/incognitovenster.
- Reserveer een cadeau met een voornaam. Een tweede reservering voor hetzelfde cadeau moet falen.
- Log opnieuw als eigenaar in: daar mag **geen** reserveringsnaam/status verschijnen. In de gedeelde link mag wél 'Gereserveerd' staan.
- Test wachtwoordherstel en e-mailbevestiging via de ingestelde Site URL.
- Controleer in **Database → Tables** dat Row Level Security actief is en **anonieme rollen geen rechtstreeks recht op wishly_reservations** hebben.

## 5. Webshoplink automatisch uitlezen (optioneel)
De knop **Ophalen** werkt pas met de Edge Function. De link wordt wel gewoon bewaard als deze niet geïnstalleerd is.
1. Installeer de Supabase CLI volgens https://supabase.com/docs/guides/local-development/cli/getting-started.
2. In deze projectmap: `supabase login`, `supabase link --project-ref PROJECT_REF`.
3. Publiceer met `supabase functions deploy product-metadata` (JWT-verificatie **niet uitschakelen**).
4. Alleen een beperkte lijst vertrouwde webshops is toegestaan in de functie; sommige blokkeren scraping. Coolblue werkt dus niet gegarandeerd. De functie is bewust beperkt om SSRF-risico's te verkleinen.

## 6. Beheer en beveiliging
- Plaats **geen** privégegevens, wachtwoorden of database-export in GitHub. De repo en website zijn publiek.
- Zet in Supabase **automatische backups** of plan regelmatige exports naar een veilige plaats; gratis back-upmogelijkheden verschillen per plan. Controleer zelf welke beschikbaar zijn.
- Auth heeft abuse-limieten; overweeg CAPTCHA of aanvullende beperking voordat de link verder wordt verspreid. De publieke `wishly_reserve`-functie is toegankelijk aan iedereen die de geheime link heeft en heeft geen per-bezoeker rate limiting.
- Maak geen publieke opslag van gevoelige foto's. Wie de opslag-URL heeft, kan de foto zien.
- **Bestaande lokale cadeaus zijn niet automatisch overgezet** vanuit `wishly.sqlite3`.
- Wijzigingen aan `docs` zijn na commit doorgaans snel online; cache verwijderen is normaal niet nodig. Als je een oude PWA/serviceworker had, verwijder die eenmalig via browser-sitegegevens.

## Probleemoplossing
- 'Bijna klaar': `docs/config.js` bevat nog placeholders, of browser heeft oude versie.
- 'permission denied': SQL-script niet volledig uitgevoerd, Data API uit, of grants ontbreken.
- E-mail-link gaat verkeerd: check Site URL en Redirect URLs.
- 'Automatisch ophalen lukte niet': Edge Function niet gepubliceerd of shop blokkeert uitlezen.
- Foto upload fout: controleer `wishly-images` bucket en limiet van 3 MB.
- Lege publieke lijst: controleer of de gehele `?w=...`-link gekopieerd is.

## Technische beperking
De eigenaar ziet op het **eigen dashboard** geen reserveringen. De gedeelde link is voor iedereen met die link toegankelijk — inclusief de eigenaar als die bewust de gastlink opent. We kunnen niet cryptografisch verhinderen dat dezelfde persoon de gastweergave bezoekt.
