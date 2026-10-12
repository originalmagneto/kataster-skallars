# Kataster MCP – inicializácia a pokračovanie

## Nasadené spoločné OAuth, 12. 10. 2026

Nové výslovné zadanie deployu bolo splnené. Súkromný originalmagneto/skallars-auth je nasadený na vlastnom Dokploy, autorita https://auth.aittorney.online, code revision b9fff092c51e4deb10872fd9b7e7e431ef676e56. Kataster 0.5.0 je nasadený s OAuth metadátami a introspekciou, code revision 1833457c7de07cfd1c78340e47dbf1a847b93d69. Oba kontajnery healthy, verejné HTTPS má platný Let's Encrypt certifikát. Pri prvom deployi bola opravená health kontrola: Node fetch neodoslal požadovaný Host, native node:http kontrola ho odosiela. Nešlo o vypnutie host kontroly.

Používateľ zvolil používateľské meno alebo e-mail, e-mail nie je povinný. Osobne nastavil heslo; použitý aktivačný odkaz bol overene odmietnutý. Codex mcp login aj Claude mcp login uspeli. Pevné Authorization hlavičky boli odstránené len z Kataster registrácií; pôvodné konfigurácie sú zálohované mimo Git v ~/.config/skallars-auth. Ostatné registrácie zachované. Codex agents kompatibilita bola riešená iba overrides pre daný príkaz. Claude Code hlásil Connected aj v novom procese po reštarte autority a opätovnej readiness. Oba modelové CLI majú nezávisle problém so svojím prihlásením do modelového účtu, preto modelom iniciovaný OAuth tool call ešte nebol dokončený. OAuth callback a MCP spojenie nie sú týmto blokovaním zneplatnené.

154 offline testov a šesť CI kombinácií Katastra prešlo; auth má 10 úspešných testov, audit bez nálezov a úspešný Docker build/CI. Lokálna Safari skúška skutočného OAuth prešla. Živá obrazovka bola otvorená a absolvovaná používateľom; Safari MCP bol dočasne nedostupný (Transport closed), po obnovení prešla živá kontrola login formulára, autocomplete, konzoly a siete bez chýb. Pôvodný bearer status call proti nasadenej 0.5.0 uspel. Legacy bearer zostáva pre existujúci CLI a pri offboardingu ho treba odobrať osobitne od OAuth. Dôkazy a postup: docs/oauth.md a docs/research/oauth-deployment-verification-2026-10-12.json. Bootstrap odstránený z uloženej konfigurácie, persistentné kľúče a volume zachované. AutoDeploy vypnutý, ostatné MCP/Gateway ešte nemigrované. Plugin distribúcia, OAuth CLI a automatická aktualizácia zostávajú ďalšími etapami.

## Rozpracované spoločné prihlasovanie, 12. 10. 2026

Používateľ schválil spoločný SKALLARS formulár, osobné účty s heslom a opätovné použitie pri nových aj existujúcich MCP. Dizajn sa riadi aktuálnym `/Users/Magneto/PROJECTS/SKALLARS-DESIGN` a webom skallars.com. Samostatný lokálny projekt `/Users/Magneto/CascadeProjects/MCPs/skallars-auth` obsahuje oidc-provider, SQLite účty, spoločné formuláre a Dokploy konfiguráciu. Zatiaľ nie je nasadený ani pushnutý. Náhľad na http://127.0.0.1:4317/preview/login neodosiela prihlasovacie údaje.

Nové prihlásenie má 5-minútový access token, rotovaný refresh token s pevným limitom 90 dní a samostatnú 30-dňovú browser session. Životnosť refresh tokenu nepredlžuje každá rotácia a nezávisí od browser session. MCP klienti s refresh_token grantom dostanú obnovovací token aj bez OIDC offline_access scope. Regresný test overil obnovu na 89. deň a odmietnutie po limite. Polia podporujú správcu hesiel vrátane username pri aktivácii. Všetkých 8 lokálnych auth testov prešlo; Safari overil formulár, autocomplete, konzolu a sieť. Reštart skutočného Codex/Claude OAuth klienta a konkrétny správca hesiel ešte neboli overené.

V tomto repozitári sú necommitnuté OAuth protected-resource metadata, fail-closed introspekcia s audience/issuer/scope/tenant kontrolou a dynamické tenantové lifecycles. Celá offline sada má 153 úspešných testov a build wheel/sdist prešiel. Doterajší bearer prístup zostáva funkčný. Nasadený remote je stále pôvodná 0.4.0 bez novej OAuth autority; nižšie uvedený deployment SHA sa nemenil. Pred deployom dokončiť bootstrap a skutočný browser OAuth test, prevádzkový návod, kontrolu chybového štartu dynamického tenanta, potom nasadiť autoritu a až následne resource server. Pluginy, automatické aktualizácie a migrácia ďalších MCP zostávajú rozpracovaným rozsahom, nie hotovou funkciou.

## Kontrola prístupu a distribúcie, 12. 10. 2026

Živý POST /mcp bez tokenu opäť overene vracia 401. Prihlasovacie okno/OAuth ani inštalovateľný Kataster plugin ešte neexistujú. Skill má rozšírený opis pre parcely, vlastníkov a mapy, smerovanie medzi CLI a dostupným MCP a pravidlo proti duplicitným volaniam. Validácia skill-creator a git diff --check prešli; prirodzený výber skillu modelom nebol meraný. Symlinky oboch lokálnych klientov smerujú na tento skill.

Aktuálne GitHub HEAD: skallars-marketplace 8a121922, lawoss-marketplace 8a0b699e. SKALLARS gateway plugin používa HTTP endpoint, takže samostatný Kataster plugin môže cieliť priamo na vlastný Dokploy. Verejný LAWOSS validator aj na aktuálnom HEAD povoľuje pre MCP iba schválené lokálne Node runtime balíky. Python local a remote distribúcia potrebujú rozšírenie kontraktu a integračné testy. Žiadny marketplace ani Gateway sa pri tejto kontrole nemenil. Návrh poradia: osobný onboarding/OAuth, private remote plugin + skill, CI riadené vydania a Dokploy deploy, LAWOSS remote/local kontrakt a balíky, potom voliteľná mapa ako MCP App. Lokálny HTML/PNG export už existuje, remote mapové exporty a MCP Apps UI nie.

## Remote implementácia 0.4.0, 12. 10. 2026

Používateľ výslovne požiadal implementáciu a skúšanie. Implementovaný samostatný HTTP pilot, CLI remote upload/tools/call a osobné tokeny s expiráciou. Per-user SQLite, upload file_id, obmedzený parser subprocess, periodický purge aj pre odobratých používateľov, spoločné provider limity. Doména mcp-kataster.aittorney.online. Konkrétne hranice a postup v [remote návode](docs/remote-pilot.md). OAuth, remote mapové exporty a Gateway auto-update nie sú hotové.

Dokploy projekt Kataster SKALLARS (YHYVENJmOuc68caY78CnS), compose hR1vGslIGKJEntXc667AS. Remote endpoint bol nasadený a HTTPS, syntetický import, cross-user odmietnutie aj revokácia skúšobného tokenu boli overené cez internet. Codex desktop priamo zavolal remote kataster_ku a kataster_status. Objavené a regresne pokryté blokovanie discovery streamom subscriptions/listen z MCP 2026; lokálny Claude Code už hlási Connected. Finálny commit 4a5d1d5 je nasadený, kontajner healthy, Codex remote nástroj zavolaný a Claude Code cez verejné HTTPS hlási Connected. CI 38274612177 prešlo vo všetkých 6 kombináciách OS/Python. Aktuálny dôkaz: docs/research/remote-pilot-verification-2026-10-12.json. 151 offline testov prešlo. AutoDeploy zostáva vypnutý, Gateway sa nemenil.

Registrácia v oboch klientoch: kataster-skallars-remote. Lokálna registrácia zostáva kataster-skallars. Token je iba v chránených lokálnych konfiguračných súboroch, na serveri sú hashe; platnosť Mariánovho tokenu do 10. 1. 2027. Dočasný druhý testovací používateľ bol odobratý a jeho token overene dostáva 401.

## Implementačný stav po schválenom pokračovaní

- Nový samostatný repozitár `originalmagneto/kataster-skallars` je overene private, bez fork väzby. `origin` smeruje naň, verejný fork je remote `public-fork`, upstream zostáva `braklo/kataster-mcp`. Lokálna vetva `codex/standalone-foundation`.
- Lokálny pilot 0.3.0: MCP SDK 2.3.0, stdio a CLI `sk-kataster`, zdieľaný importný servis, compact výstupy a skill. CLI nainštalované cez uv editable s constraints exportovanými z locku.
- Opravy: chýbajúca/prázdna C je unknown; čitateľnosť/rozsah sa označujú bez tvrdenia úplnosti; IČO musí mať 8 ASCII číslic (validácia formátu, nie potvrdenie pridelenia či kontrolnej číslice); novší/širší cache záznam sa chráni pred slabším importom; zdroj dávky ukazuje na zvolený dokument. Konflikty sa oznamujú, nemenné verzie ešte nie sú implementované.
- Overenie: 142 offline testov prešlo, vrátane reálneho stdio handshake, chybového výsledku a CLI subprocessov mimo checkoutu. Wheel aj sdist sa zostavili. Live volania na portál neboli vykonané. Safari kontrola nie je relevantná, nemenilo sa web UI.
- Claude Code registrácia `kataster-skallars` hlási Connected. Codex MCP sekcia bola pridaná priamo, pretože jeho CLI odmieta existujúce nastavenie agents. Ostatné nastavenia zachované; nové desktop načítanie a volanie zatiaľ neoverené. Skill je symbolicky pripojený v oboch harnesses. Nová dátová cesta je samostatná.
- Gateway: vytvorené sanitizované JSON mapovanie 22 služieb/135 tools na Dokploy konfigurácie. Runtime SHA/digest a kanonický zdroj ešte neoverené. Gateway backendy ani deployment sa nemenili, auto-update pipeline ešte nie je nasadená.
- GitHub CI rozširuje upstream matrix Linux/macOS/Windows a Python 3.12/3.14 o build a CLI smoke. Duplicitný workflow bol zlúčený; zdedené publikovanie na verejné PyPI bolo odstránené. Lokálne testy používajú Python 3.13. Remote Kataster potrebuje doménu, samostatnú autentifikáciu, izoláciu dát a upload kontrakt. Používateľ potvrdil doménu mcp-kataster.aittorney.online na vlastnom Dokploy. Autentifikačný provider a jeho konkrétne pripojenie ešte nie sú implementované.
- Návod a hranice: [lokálny pilot](docs/local-pilot.md). Staršie sekcie nižšie sú historická evidencia, tvrdenia o neprítomnej implementácii alebo nezmenenom origin už neplatia.

## Historická inicializácia

Overené pri inicializácii 12. 10. 2026. Nasledujúca tabuľka zachytáva pôvodný stav.

| Položka | Overený stav |
|---|---|
| Priečinok MCP | `/Users/Magneto/CascadeProjects/MCPs` |
| Nový clone | `/Users/Magneto/CascadeProjects/MCPs/kataster-braklo-mcp` |
| GitHub účet (`gh api user`) | `originalmagneto` |
| Fork | https://github.com/originalmagneto/kataster-braklo-mcp |
| Parent forku | `braklo/kataster-mcp` |
| Pracovná lokálna vetva | `design/remote-dokploy` |
| origin (fetch/push) | `https://github.com/originalmagneto/kataster-braklo-mcp.git` |
| upstream (fetch/push) | `https://github.com/braklo/kataster-mcp.git` |
| Východiskový upstream/main | `32115f0526c12bfffad1fb6501b1f00bb7693c83` |
| Dátum upstream commitu | `2026-10-11T23:12:01+02:00` |
| Verzia / licencia / Python | 0.2.0 / MIT / >=3.12 |
| SDK / transport / nástroje | `mcp[cli]>=1.2.0,<2`, lock 1.30.0 / stdio / 11 |

Názov forku bol zvolený zámerne: `originalmagneto/kataster-MCP` už existuje a nie je fork od braklo. Rovnako lokálny `../kataster-MCP` je starší odlišný projekt. Pôvodná vetva, commit a obsah jeho 31 Git evidovaných/neignorovaných súborov boli zaznamenané a porovnané; existujúca zmena ` D .claude/scheduled_tasks.lock` sa zachováva. Nijaký existujúci projekt sa neprepisoval.

## Podklady

- [Statický audit a offline dôkazy](docs/research/upstream-audit-2026-10-12.md)
- [Návrh remote verzie a poradie prác](docs/architecture/remote-dokploy.md)
- [Výsledok syntetických kontrol](docs/research/audit-evidence.json)
- [Reprodukovateľné úzke offline kontroly](docs/research/verify_audit.py)

`git status` po odovzdaní má obsahovať iba nové `AGENTS.md`, tento súbor a `docs/`. Podklady sú úmyselne necommitnuté a pracovná vetva nepushnutá; GitHub fork má pôvodný upstream obsah. Nasledujúca session môže začať priamo v tomto clone.

## Čo bolo vykonané a overené

GitHub účet a parent forku boli overené cez existujúce `gh` prihlásenie; nové poverenia neboli vytvorené. Čerstvý fetch upstreamu potvrdil vyššie uvedený commit. Statické čítanie a AST kontrola potvrdili 11 nástrojov a neprítomnosť Dockerfile, HTTP entrypointu a OAuth implementácie. README v sekcii Stav stále píše „Verzia 0.1“, hoci pyproject a modul majú 0.2.0.

Skript s vlastnými syntetickými dátami reprodukoval prázdnu/chýbajúcu časť C → `tarchy=none`, nečíselné IČO → zhodu s vlastníkom bez IČO a posledný zápis do cache → prepísanie staršieho záznamu bez kontroly dátumu obsahu. Toto je úzke offline overenie; nebol spustený MCP server, inštalácia závislostí, upstream skripty, plná pytest sada ani živé dotazy na LV. Nie je preukázaná chyba konkrétneho živého LV.

Prečítané lokálne pokyny: v rodičovských adresároch nového clone nebol nájdený AGENTS.md; upstream nemá AGENTS.md/CLAUDE.md. Pokyny a úvodné research dokumenty staršieho projektu boli prečítané pre kontext. Použité skills: `dokploy-server`, `security-best-practices`, `verification-before-completion`; bezpečnostný skill nemá špecifickú referenciu pre FastMCP, preto audit vychádza z konkrétneho kódu a oficiálnych MCP materiálov.

## Najbližší krok

Používateľ schválil standalone-first smerovanie a doplnil požiadavku na dorovnanie existujúcich MCP v Gateway a automatické aktualizácie z kanonických repozitárov. Doplnený postup je na konci dokumentu `docs/architecture/standalone-first-2026-10-12.md`. Gateway zostáva samostatným pracovným celkom; Kataster naň nečaká. Ide o schválenie smerovania, nie dôkaz vykonaného deploymentu. Staršia poznámka o neschválenom návrhu nižšie zachytáva predchádzajúci stav.

**Najnovšie smerovanie používateľa:** [samostatný private MCP/CLI/skills projekt, gateway neskôr](docs/architecture/standalone-first-2026-10-12.md). Najprv priame Codex/Claude Code pripojenie a vlastná remote služba na používateľovom Dokploy; automatická aktualizácia z kanonického súkromného zdroja sa navrhne po pilote. Pozor: existujúci `originalmagneto/kataster-braklo-mcp` je overene public fork, súkromný cieľ ešte nebol vytvorený. Podrobný mechanizmus dnešných aktualizácií gateway a rozdiel oproti samostatným Dokploy službám je v novom dokumente. Implementácia ani zmena vzdialených repozitárov sa touto previerkou nevykonala.

### Lokálne pokračovanie 12. 10. 2026

Na žiadosť používateľa vznikol [rozšírený návrh implementácie a distribúcie](docs/architecture/distribution-and-remote-proposal-2026-10-12.md). Pokrýva existujúcu SKALLARS gateway, SDK 2.3.0, CLI, úsporu kontextu, súkromné dokumenty, Dokploy a local/remote balíky pre LAWOSS. Obsahuje konkrétne zistenia v gateway a LAWOSS importéri a navrhnuté poradie prác. Návrh zatiaľ nie je schválenou implementáciou. Vznikol aj statický profil opisov nástrojov v `docs/research/context-profile-2026-10-12.json`; nejde o tokenový benchmark. `CLAUDE.md` bol doplnený ako presná kópia `AGENTS.md`. Pôvodný zoznam necommitnutých súborov vyššie sa tým rozširuje o `CLAUDE.md` a nové podklady v `docs/`.

Začať malým offline change setom pre správnosť LV: explicitná úplnosť častí A/B/C, `unknown` pri chýbajúcej alebo neprečítanej časti C, validácia IČO a ochrana uloženého úplného/novšieho LV pred starším alebo čiastočným importom. Najprv regresné fixtures a testy, potom implementácia. Až následne navrhnúť a prototypovať autentifikovaný upload cez `file_id` a HTTP transport.

Inicializácia nemá zostávajúci blocker. Remote prevádzka zostáva návrhom: nie sú zvolené doména a OAuth provider ani overená integrácia uploadu v konkrétnych klientoch. Production deploy, persistentné MCP registrácie a OAuth granty sa nevykonali.
