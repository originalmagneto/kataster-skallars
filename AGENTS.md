# Pracovné pravidlá pre kataster-braklo-mcp

Tento repozitár je fork `braklo/kataster-mcp`. Susedný `../kataster-MCP` je odlišný existujúci projekt; nemeníme ho a neprenášame sem automaticky jeho architektúru ani historické právne závery.

Pred pokračovaním prečítaj `PROJECT_HANDOFF.md`, `docs/research/upstream-audit-2026-10-12.md` a `docs/architecture/remote-dokploy.md`.

- Dokumentácia a komunikácia po slovensky, identifikátory kódu po anglicky.
- Používateľ schválil pokračovanie implementácie standalone-first: súkromný repozitár, opravy, CLI, skill a priame lokálne pripojenie. Používateľ následne výslovne schválil implementáciu a testovanie remote na vlastnom Dokploy, doména mcp-kataster.aittorney.online. Konkrétny pilot používa osobné expirovateľné tokeny, oddelené databázy a upload; OAuth a aktualizácie Gateway zostávajú ďalšou etapou.
- Zachovaj stdio a upstream ochranné limity. Neobchádzaj CAPTCHA alebo blokáciu portálu.
- Nevyvodzuj neprítomnosť tiarch z neprečítanej časti C. Rozlišuj neúplný/čiastočný LV od úplného výpisu.
- Žiadne poverenia, živé LV alebo osobné údaje do Git. Používaj syntetické/anonymizované fixtures.
- Pred zmenou správania priprav regresný test. Pred commitom over relevantné offline testy; živé testy proti portálu spúšťaj iba po konkrétnom zadaní.
- Lokálne memory a dokumenty susedného projektu sú historický kontext, nie overenie aktuálnych rozhraní alebo povolenie scrapingov.
