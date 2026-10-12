# Kataster MCP – inicializácia a pokračovanie

## Implementačný stav po schválenom pokračovaní

- Nový samostatný repozitár `originalmagneto/kataster-skallars` je overene private, bez fork väzby. `origin` smeruje naň, verejný fork je remote `public-fork`, upstream zostáva `braklo/kataster-mcp`. Lokálna vetva `codex/standalone-foundation`.
- Lokálny pilot 0.3.0: MCP SDK 2.3.0, stdio a CLI `sk-kataster`, zdieľaný importný servis, compact výstupy a skill. CLI nainštalované cez uv editable s constraints exportovanými z locku.
- Opravy: chýbajúca/prázdna C je unknown; čitateľnosť/rozsah sa označujú bez tvrdenia úplnosti; IČO musí mať 8 ASCII číslic (validácia formátu, nie potvrdenie pridelenia či kontrolnej číslice); novší/širší cache záznam sa chráni pred slabším importom; zdroj dávky ukazuje na zvolený dokument. Konflikty sa oznamujú, nemenné verzie ešte nie sú implementované.
- Overenie: 141 offline testov prešlo, vrátane reálneho stdio handshake, chybového výsledku a CLI subprocessov mimo checkoutu. Wheel aj sdist sa zostavili. Live volania na portál neboli vykonané. Safari kontrola nie je relevantná, nemenilo sa web UI.
- Claude Code registrácia `kataster-skallars` hlási Connected. Codex MCP sekcia bola pridaná priamo, pretože jeho CLI odmieta existujúce nastavenie agents. Ostatné nastavenia zachované; nové desktop načítanie a volanie zatiaľ neoverené. Skill je symbolicky pripojený v oboch harnesses. Nová dátová cesta je samostatná.
- Gateway: vytvorené sanitizované JSON mapovanie 22 služieb/135 tools na Dokploy konfigurácie. Runtime SHA/digest a kanonický zdroj ešte neoverené. Gateway backendy ani deployment sa nemenili, auto-update pipeline ešte nie je nasadená.
- GitHub CI rozširuje upstream matrix Linux/macOS/Windows a Python 3.12/3.14 o build a CLI smoke. Duplicitný workflow bol zlúčený; zdedené publikovanie na verejné PyPI bolo odstránené. Lokálne testy používajú Python 3.13. Remote Kataster potrebuje doménu, samostatnú autentifikáciu, izoláciu dát a upload kontrakt. Navrhnutá doména je mcp-kataster.aittorney.online, používateľská odpoveď ešte čaká.
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
