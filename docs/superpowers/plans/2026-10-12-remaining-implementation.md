# Dokončenie Kataster a MCP ekosystému

> For agentic workers: REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Kroky sa vykonávajú priebežne, používateľ už schválil implementáciu.

**Goal:** Dokončiť osobné prihlásenie, distribúciu, prevádzku, spoločný OAuth, Gateway a LAWOSS integráciu.
**Architecture:** Samostatný Kataster na vlastnom Dokploy je kanonický backend. Spoločná SKALLARS autorita overuje osobné účty, každý resource uplatňuje vlastné oprávnenia a tenant. Distribúcia vychádza z testovaných nemenných vydaní privátneho zdroja.
**Tech Stack:** Python 3.12+, MCP 2.3.0, Node 24, TypeScript, oidc-provider, SQLite, Dokploy, GitHub Actions.
**Spec:** docs/remaining-work-2026-10-12.md a aktuálne výslovné zadanie používateľa.

## Global Constraints

- Slovenská dokumentácia, anglické identifikátory a komentáre, bez em dash v nových textoch.
- Nikdy secrets, živé LV alebo osobné údaje do Git. Len syntetické fixtures.
- Bez dotazov na kataster portál v tejto implementácii. Zachovať CAPTCHA a globálne upstream limity.
- Zachovať stdio, individuálne tenanty, pôvodné klientské konfigurácie a osobné dáta.
- Nezasahovať do ../kataster-MCP. Zachovať už rozpracované plugin súbory v tomto checkoute.
- Testy pred pushom, HTTPS validácia bez výnimiek, žiadny spoločný osobný backendový token.
- Práce ostávajú na existujúcich codex vetvách; LAWOSS verejné zmeny cez PR.
- Osobné heslá, privátny súhlas OAuth, skúška na druhom počítači a kolegove prihlásenie vyžadujú účasť príslušného človeka.

## Review Focus

- Rotujúci refresh token: súbežné procesy nesmú zneplatniť grant ani stratiť posledný token.
- Oprávnenie k jednej službe: odobratie nesmie sprístupniť iný tenant ani zbytočne odhlásiť ostatné služby.
- Záloha: úspešné kopírovanie bez čitateľnej konzistentnej obnovy nestačí.
- Distribúcia: local profil nesmie neúmyselne používať remote ani duplikovať nástroje.
- Gateway: identita a audience backendu musia byť osobné a overené.

### Task 1: OAuth pre existujúci CLI

**Files:** src/kataster_mcp/remote_client.py, nový src/kataster_mcp/cli_auth.py, tests/test_remote_cli.py, nový tests/test_cli_auth.py, docs/cli-oauth.md.
**Interfaces:** Zachovať execute(args) -> dict a existujúce CLI envelope. Doplniť remote login/status/logout, --auth-file a --no-browser. OAuth PKCE S256, náhodný state, loopback callback 127.0.0.1, scopes mcp:tools, resource endpoint /mcp. Znovupoužiť OAuth SDK, ak bezpečne pokrýva loopback a refresh; inak existujúci httpx a stdlib. Status nikdy nevracia tokeny. Konfigurácia je viazaná na presný resource a issuer z overeného discovery. Default auth súbor ~/.config/kataster-skallars/oauth.json, adresár 0700, súbor 0600, atomické zápisy a medziprocesový zámok podporovaný Linux/macOS/Windows. Explicitný env alebo --token-file legacy naďalej funguje počas migrácie, default legacy nesmie prebíjať OAuth.
- [ ] Napísať a spustiť regresné testy PKCE/state/callback nesúlad, discovery issuer/resource nesúlad a nepovolené HTTP/redirecty.
- [ ] Implementovať bezpečný login cez prehliadač, DCR native client, token/refresh, rotáciu pod jedným zámkom, invalid_grant bez úniku hodnôt, lokálny logout s revokáciou kde podporovaná.
- [ ] Testovať súbežný refresh, atomický zápis, chybný/expirujúci token a status bez credentials.
- [ ] Spustiť uv run pytest tests/test_cli_auth.py tests/test_remote_cli.py a CLI smoke mimo checkoutu. Commit iba vlastnené súbory, nie rozpracovaný plugin.

### Task 2: Oprávnenia a konzistentné zálohy Auth

**Files:** /Users/Magneto/CascadeProjects/MCPs/skallars-auth/src/admin.ts, src/store.ts, test/, docs/, scripts/backup.mjs podľa existujúcich konvencií.
**Interfaces:** Osobný člen má resources väzby. Admin grant/revoke-resource musí pridávať/odoberať len danú službu, validovať tenant a existujúci resource, odmietnuť zdieľaný tenant. Revoke ruší príslušné granty/tokeny; ostatné služby ostávajú. disable zruší všetko. Záloha konzistentná cez SQLite backup/VACUUM INTO, zahŕňa persistentné kľúče a konfiguráciu mimo Git, manifest SHA256 a private práva; restore do samostatnej testovacej cesty.
- [ ] Regresné testy dvoch resources, izolácie a odobratie jednej služby vrátane už vydaných tokenov.
- [ ] Implementovať admin príkazy a prevádzkový návod bez admin UI navyše.
- [ ] Vytvoriť backup a restore self-check s aktívnym SQLite WAL; poškodený manifest musí odmietnuť obnovu.
- [ ] npm test a npm run build s Node 24, commit iba tejto úlohy. Bez produkčných mutácií.

### Task 3: Private plugin local/remote

**Files:** Existujúce plugin.json, mcp.json, .mcp.json, .codex-plugin/, .claude-plugin/, skills/, tests/test_plugin.py, nové scripts/package_plugin.py, docs/plugin.md.
**Interfaces:** Kanonický remote https://mcp-kataster.aittorney.online/mcp. Dva samostatné artefakty local a remote, každý obsahuje jeden skill a jeden MCP backend. Local spúšťa pinovaný vydaný Python balík bez hardcoded checkout path. Remote bez secret alebo auth headers. Znovupoužiť existujúce manifesty; CLI inštalácia samostatne zdokumentovaná. Balík sa dá reprodukovateľne zostaviť a validovať offline.
- [ ] Overiť aktuálne formáty lokálnymi validačnými nástrojmi a klientom, upraviť minimalne.
- [ ] Test balíku z čistého temp priečinka, žiadne secrets/osobné fixture, skill iba raz.
- [ ] Návody pre inštaláciu, OAuth, odstránenie duplicitnej ručnej registrácie, update a uninstall.
- [ ] Spustiť relevantné offline testy a commit.

### Task 4: Vydania, Dokploy aktualizácie a obnova

**Files:** Kataster/Auth workflows, Dockerfile/compose, deployment scripts, docs; privátne prevádzkové konfigurácie mimo Git.
**Interfaces:** Testovaný commit -> nemenný image digest -> autorizovaný Dokploy deploy -> health aj MCP smoke -> automatický návrat na predchádzajúci digest pri zlyhaní. Žiadne priame latest zmeny bez CI. Zdroj SHA a verzia dostupné v health. Automatické zálohy Auth/Kataster na existujúci vhodný chránený Dokploy cieľ, retencia rešpektuje osobné dáta.
- [ ] Overiť aktuálne možnosti Dokploy CLI, registry a backup destination bez úniku secrets.
- [ ] Implementovať release workflow, private obrazy, smoke/rollback a update návod pre lokálny CLI/plugin.
- [ ] Overiť skutočnú obnovu syntetického aj chráneného snapshotu do izolovaného priestoru; nič neprepisovať v produkcii.
- [ ] Nasadiť testované Auth/Kataster, prakticky OAuth CLI status a syntetický import, potom vyradiť legacy bearer.

### Task 5: Existujúce MCP a spoločný OAuth

**Files:** Kanonické súkromné repos jednotlivých MCP, spoločná Auth resources konfigurácia, integračný návod.
**Interfaces:** Inventár Dokploy endpoint -> git repo/SHA -> image digest. Resource používa protected-resource metadata a fail-closed osobnú introspekciu, žiadne trust client tenant. Malý spoločný Node adaptér pre existujúce HTTP servery, nie refaktor doménovej logiky.
- [ ] Audit všetkých aktuálne nasadených MCP a ich zdrojov; evidovať unknown miesto predstierania aktuálnosti.
- [ ] Migrovať brány jednotlivo, testy bez dát portálu, zachovať autorizované existujúce prístupy počas prechodu.
- [ ] Nasadiť po testoch a preveriť metadata, 401, osobnú identitu/revokáciu a rollback.

### Task 6: Gateway a SKALLARS marketplace

**Files:** originalmagneto/skallars-marketplace gateway/, plugin catalog, workflows a docs.
**Interfaces:** Kanonické private zdroje sa pinujú na schválené testované SHA, updater nepreberá náhodný public catalog ako najnovšie private runtime. Remote Kataster musí prenášať serverom overenú individuálnu identitu, presné audience a autorizované oprávnenie; žiadny shared Kataster token.
- [ ] Fresh audit gateway runtime a 22 zdrojových mapovaní, vytvoriť reproducible release manifest.
- [ ] Implementovať bezpečný osobný remote adaptér a integračné testy tenantov, Kataster direct plugin v katalógu.
- [ ] CI-gated canonical source updates, smoke a rollback, nasadiť overené runtime.

### Task 7: LAWOSS marketplace local/remote

**Files:** Overené aktuálne LAWOSS app/importer a lawoss-marketplace checkout, validator/runtime contract/tests, sanitizované Kataster balíky.
**Interfaces:** Podporovať local Python MCP a remote HTTP OAuth ako explicitné kontrakty. Zachovať privacy, native Integrations, existujúce Node pluginy a SK/CZ/EN. Verejný distribučný artefakt neodhaľuje súkromný repo ani secrets; zachovať MIT atribúciu.
- [ ] Fresh AGENTS a marketplace audit, rozšíriť úzky kontrakt s odmietnutím nebezpečných ciest/config.
- [ ] Test install/update/uninstall oboch profilov, existujúce Node regresie, predložiť PR s konkrétnymi artefaktmi.

### Task 8: Remote mapy a doménové zostávajúce funkcie

**Files:** remote.py, mapa.py, LV cache/import, nové úzke tests a autorizovaný mapový UI asset.
**Interfaces:** Remote export iba opaque export_id autorizovaný tenantom, bounded TTL/size, žiadna cesta servera. MCP App iba podporovaný otestovaný kontrakt, web mapa funguje aj samostatne. Nemenné verzie LV podľa tenant/hash/parser, explicitný výber konfliktu a porovnanie dvoch importovaných LV; porovnanie zmluvy len nad explicitným štruktúrovaným/parsing vstupom s neistotou.
- [ ] Regresné testy export izolácie, expiry/purge a mapy so syntetickou geometriou, Safari DOM/console/network/responsive.
- [ ] Minimálne remote exporty a mapové UI nad existujúcim renderom, zachovať lokálne exporty.
- [ ] Nemenná história importu a porovnania s unknown pri chýbajúcej časti C, parser provenance a konzervatívnou migráciou.

### Task 9: Harnesse, kontext a záverečné overenie

**Files:** docs/research/, skill references, PROJECT_HANDOFF.md, README a návody.
**Interfaces:** Merateľný tools/schema context verzus CLI skill; prírodné invocation príklady, nepredstierať garantované každé použitie skillu. Praktické OAuth volanie, revokácia, refresh/reštart, synthetic import, druhý PC a kolega sú samostatné evidence.
- [ ] Celé offline sady, CI, plugin validator a relevantné Safari checks.
- [ ] Kontext benchmark a zrozumiteľné odporúčania podľa klienta, konsolidovať staré návody s historickým stavom.
- [ ] Záverečný broad review, opravy a presný prehľad hotové/neoverené/ľudská aktivácia.
