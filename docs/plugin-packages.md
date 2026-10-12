# Lokálny a remote balík pluginu

Existujúci publikovaný `kataster-skallars` 0.1.0 zostáva remote pluginom.
Samostatný `kataster-skallars-local` 0.1.0 pribaluje Python projekt a používa
stdio. Balíky nemenia marketplace, updater ani registrácie klientov.
Každý ZIP má jeden skill a jedno MCP pripojenie. Verzia backendu je 0.5.0.

## Reprodukovateľné zostavenie

Z koreňa repozitára spusti štandardnoknižnicový skript:

```sh
python3 scripts/package_plugin.py \
  --source-ref 538935969eb56e63d1f12fc59b0f66d9709b0e00 \
  --output-dir dist/plugins
```

Výstupy sú `kataster-skallars-0.1.0.zip` a
`kataster-skallars-local-0.1.0.zip`. Skript číta výhradne obsah zvoleného
Git commitu, nie necommitnuté súbory. Oba majú `SOURCE.json` s plným source
SHA a SHA256 každého ostatného súboru. Rovnaký zdroj vytvorí rovnaké ZIP bytes,
vrátane skrytých manifestov a pevných timestamps. SHA256 inventár overuje
integritu proti dôveryhodnému inventáru, nenahrádza podpis alebo dôveryhodný
distribučný kanál.

Allowlist obsahuje presné plugin manifesty a jeden kanonický skill. Lokálny
runtime navyše obsahuje `pyproject.toml`, `uv.lock`, `README.md`, `LICENSE`,
Python moduly pod `src/kataster_mcp` a verejnú tabuľku `data/ku.json`.
Osobné dáta, databázy, fixtures, `.env`, `.git`, cache a symlinky sa nebalia.
Symlink v povolenom zdrojovom súbore zostavenie odmietne. Nepridávajú sa
závislosti, globálna CLI inštalácia ani ďalšie platformové wrappery.

## Lokálne používanie

Rozbaľ local ZIP do vlastného trvalého priečinka. Potrebné sú `uv` na PATH,
Python >=3.12 a zapisovateľný priečinok runtime pre `.venv`. Prvý štart môže
stiahnuť Python a závislosti z locku. Prístup k súkromnému Git repozitáru
príjemca ZIPu nepotrebuje. Balík obsahuje zdroj a lock, nie offline cache
závislostí ani uv/Python binárky.

Portable `mcp.json` používa `${PLUGIN_ROOT}/runtime`; kompatibilná
`.mcp.json` používa `${CLAUDE_PLUGIN_ROOT}/runtime`. Príkaz v oboch je:

```sh
uv run --frozen --no-dev --directory /absolutna/cesta/plugin/runtime kataster-mcp
```

Samostatné CLI používa rovnaký projekt bez ďalšej inštalácie:

```sh
uv run --frozen --no-dev --directory /absolutna/cesta/plugin/runtime sk-kataster doctor
```

Claude Code vie skúšobne načítať rozbalený balík cez
`claude --plugin-dir /absolutna/cesta/plugin`. Pre trvalú inštaláciu pridaj
rozbalený local plugin do vlastného lokálneho marketplace a použi
`claude plugin install kataster-skallars-local@nazov-marketplace` alebo
`codex plugin add kataster-skallars-local@nazov-marketplace`.
Podrobnosti registrácie over cez `claude plugin marketplace --help` alebo
`codex plugin marketplace --help`; tento skript používateľskú konfiguráciu
neupravuje. Remote postup existujúceho SKALLARS marketplace je v [plugin.md](plugin.md).

## Remote OAuth a duplicitné pripojenia

Remote balík zachováva `https://mcp-kataster.aittorney.online/mcp` a osobný
OAuth. Nemá tokeny, heslá ani pevné Authorization hlavičky. Po nainštalovaní
sa používateľ prihlási v MCP paneli klienta, v Claude Code cez `/mcp`.
Vyžaduje vlastný SKALLARS účet. Balík server nenasadzuje a OAuth neobnovuje.

Ak existuje priama registrácia rovnakej remote URL, Claude môže potlačiť
pluginové MCP. Zálohuj nastavenia, vypni iba túto duplicitnú registráciu,
prihlás plugin a over jeho `kataster_status`. Potom odstráň duplikát podľa
názvu cez klienta. Zachovaj ostatné služby. Local a remote majú samostatné
úložiská; pri úlohe zvoľ jeden backend a neopakuj dotaz na oboch.

## Aktualizácia, odstránenie a overenie

Nový ZIP zostav z konkrétneho schváleného SHA; zmenu pluginu vydaj s novou
verziou všetkých príslušných manifestov. Rozbaľ ho do nového priečinka,
skontroluj inventár a nahraď lokálny marketplace zdroj až po skúške.
Registrované marketplace pluginy aktualizuj cez `claude plugin update` alebo
podporovaný postup `codex plugin marketplace --help` a načítaj novú reláciu.
Existujúci denný SKALLARS updater ostáva samostatnou nezmenenou súčasťou.

Odstránenie pluginu vykoná `claude plugin uninstall` alebo `codex plugin remove`
s príslušným plugin ID. Zdrojový priečinok odstráň až po ukončení klienta.
Osobné lokálne dáta a OAuth granty spravuj osobitne; uninstall ich nie je
potvrdeným vymazaním ani odobratím prístupu.

Offline testy kontrolujú bytes oboch balíkov, inventár, allowlist a symlinky.
Rozbalený local balík v čerstvom cwd s `UV_OFFLINE=1` a samostatným
`SK_KATASTER_DATA_DIR` vykoná skutočný MCP initialize, discovery,
`kataster_status`, exit a CLI doctor. Offline úspech predpokladá dostupnú
lokálnu dependency cache. Claude manifest validator overuje oba rozbalené
profily; dostupný Codex CLI nemá samostatný validate príkaz. `${PLUGIN_ROOT}`
je doložený nainštalovanou dokumentáciou plugin-creator; skúška procesu
substituuje cestu podľa tohto kontraktu. Úplné modelové načítanie local
pluginu v oboch klientoch a prvá inštalácia na počítači bez cache zatiaľ
nie sú overené. Kontrola Safari nie je relevantná, balenie nemení web UI.
