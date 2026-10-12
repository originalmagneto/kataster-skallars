# Lokálny pilot Kataster SKALLARS 0.3.0

Súkromný zdroj: `originalmagneto/kataster-skallars`, odvodený od `braklo/kataster-mcp`, MIT. SDK je pripnuté na 2.3.0. Stdio zostalo zachované, remote endpoint zatiaľ nie je nasadený.

## Inštalácia

V clone súkromného repozitára s Pythonom >=3.12 a `uv`:

```sh
uv sync --frozen
uv run --frozen pytest -q
uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file /tmp/kataster-constraints.txt
uv tool install --editable . --constraints /tmp/kataster-constraints.txt
rm /tmp/kataster-constraints.txt
sk-kataster --json doctor
```

Ide o vývojovú editable inštaláciu: príkazy používajú tento checkout. Pri aktualizácii kódu spusti testy; pri zmene locku zopakuj inštaláciu s `--reinstall`. Produkčné verzované artefakty a automatické nasadenie na Dokploy sú ďalšia etapa. Konzolové názvy: `sk-kataster` pre CLI, `kataster-mcp` pre stdio. Pri existujúcej rovnomennej inštalácii najprv over jej pôvod, neprepisuj iný projekt naslepo.

CLI aj stdio používajú samostatný adresár `kataster-skallars` pod používateľským dátovým adresárom OS. Override je `SK_KATASTER_DATA_DIR`; CLI podporuje aj `--data-dir`. Dáta starého projektu sa nemigrujú automaticky.

## Používanie

```sh
sk-kataster --json ku resolve 'Vyšný Kubín'
sk-kataster --json lv inspect '/cesta/vypis.pdf'
sk-kataster --json lv import '/cesta/vypis.pdf' --dry-run
sk-kataster --json lv import '/cesta/vypis.pdf'
sk-kataster --json person overview --name 'Meno Priezvisko'
sk-kataster --json tools
sk-kataster --json tools kataster_lv
sk-kataster --json call kataster_lv '{"ku":"871541","lv":"1926"}'
```

`doctor`, `ku`, `lv url`, `lv inspect`, lokálny import a prehľad osoby nevolajú portál. `tools` vypíše iba názvy; s názvom jedného nástroja vráti jeho schému. Všeobecné `call` spúšťa lokálny MCP nástroj v procese a môže vykonať sieťový dotaz alebo zápis podľa vybranej operácie. Príkazy `lv inspect/import` a `person overview` používajú doménové funkcie bez spustenia MCP servera.

Výstup je JSON: predvolene odsadený, s `--json` kompaktný. Úspech: `{data, zdroje, varovania}`, exit 0. Chyba: `{chyba: {typ, sprava}, zdroje, varovania}`, nenulový exit. Napríklad `ku resolve` vráti `data.kod`; `lv inspect` vráti `data.lv`, počty položiek, `tarchy` a `uplnost`; `lv import` pridá `ulozenie.stav`; `person overview` vracia `data.osoby` a rozsah importov. Chyba neexistujúceho súboru má `chyba.typ=not_found`.

LV je predvolene súhrn bez mien vlastníkov a položiek. `--full` sprístupní celý prečítaný dokument. `uplnost` rozlišuje chýbajúcu časť (`missing`), prázdnu/neprečítanú (`unread`) a prítomný prečítaný obsah (`read`). To nie je dôkaz úplnosti časti ani celého LV. Rozsah je `partial`, ak text uvádza čiastočný výpis, inak `unverified`.

`tarchy=unknown` nevylučuje ťarchy; `none` vyžaduje explicitný text „Bez tiarch.“ a platí len pre dodaný rozsah. Iný obsah zachováva kompatibilný stav `see cast_c`; čítaj obsah, nerob automatický právny záver.

Starší, nedatovaný alebo užší import nesmie potichu nahradiť lepší uložený záznam. `preserved_existing` výslovne oznamuje, že prehľad osôb stále používa predchádzajúci import. Aj skutočný predaj alebo zmena vlastníka môže zmenšiť rozsah: táto konzervatívna ochrana potom vyžaduje preverenie. Nemenné verzie dokumentov a explicitné riešenie takých konfliktov ešte nie sú implementované. Parser hash sa mení so správaním parsera; staré importy treba znovu načítať, automatická migrácia nie je hotová.

## Codex a Claude Code

Po inštalácii možno pripojiť stdio:

```sh
codex mcp add kataster-skallars -- /absolutna/cesta/kataster-mcp
claude mcp add --scope user kataster-skallars -- /absolutna/cesta/kataster-mcp
```

Na tomto Macu je Claude Code registrácia pridaná a `claude mcp get kataster-skallars` hlási Connected. Záznam bol pridaný aj do Codex MCP konfigurácie. CLI registráciu Codexu blokuje staršie nekompatibilné nastavenie `agents` v existujúcom globálnom súbore, preto sa doplnila iba sekcia nového MCP priamo, s kontrolou zachovania ostatných nastavení. Načítanie nástroja v novej desktop session ešte treba overiť. Nezamieňať zápis konfigurácie s úspešným volaním z konkrétneho harnessu.

Skill je v `skills/kataster-skallars/SKILL.md`; na tomto Macu sú naň symbolické odkazy v `~/.codex/skills` a `~/.claude/skills`. Pre úsporu kontextu možno používať samotný CLI so skillom. Plugin/marketplace balíky pre ďalších používateľov vzniknú až vo fáze distribúcie.

## Stav ďalších etáp

Používateľ potvrdil cieľovú doménu `mcp-kataster.aittorney.online` na svojom Dokploy. Remote prevádzka potrebuje autentifikáciu nezávislú od Gateway, identitu používateľa, autorizovaný upload/export, tenantové úložisko, celkové limity dávky a parser worker. Existujúci lokálny filesystemový kontrakt sa nesmie priamo vystaviť na internet. Živé testy portálu neboli spustené.

Gateway: mapovanie konfigurácií je v `research/gateway-source-map-2026-10-12.json`; ide o 22 služieb a 135 schválených nástrojov. Existencia zodpovedajúcej Dokploy služby nepotvrdzuje totožnosť zdrojov ani bežiacich verzií. Nasleduje overenie source SHA/image digest, kontraktov a autentifikácie, dorovnanie pribalených runtime a postupné zavedenie release pipeline. Produkčné Gateway nasadenie sa v tejto etape nemenilo.

## Kontext a CI

Meranie serializovaných schém s tokenizerom `o200k_base`: 11 nástrojov má približne 4 875 tokenov, samotný zoznam názvov CLI 76, celý skill 724. Je to odhad konkrétnych textov, nie nameraná spotreba harnessu; lazy discovery môže reálnu spotrebu meniť. Profil je v `research/local-context-profile-2026-10-12.json`.

CI používa pôvodnú matrix Linux/macOS/Windows s Pythonom 3.12/3.14, offline testy, build a CLI smoke mimo checkoutu. Zdedený workflow pre publikovanie na verejné PyPI bol v súkromnej distribúcii odstránený. Deploy job ani produkčné tajomstvá zatiaľ nie sú nastavené.
