# Audit upstream 0.2.0 – 12. 10. 2026

Rozsah: commit `32115f0526c12bfffad1fb6501b1f00bb7693c83`, čerstvo overený cez `upstream/main`. Ide o statický audit s úzkou syntetickou offline reprodukciou, nie penetračný test, plnú testovaciu sadu alebo validáciu konkrétneho živého LV.

Najprv treba opraviť význam neúplného LV a identitu subjektu. Súčasný lokálny stdio server sa nesmie bez úprav zverejniť ako zdieľaná služba: dôveruje lokálnemu filesystemu a používa jednu osobnú cache pre proces/OS používateľa. Závažnosť rizík filesystemu a tenantov nižšie je podmienená budúcim remote nasadením.

## P0 – integrita LV a podmienky zdieľanej služby

### 1. Prázdna/neprečítaná časť C sa zamieňa s neprítomnosťou tiarch

`src/kataster_mcp/parsers/lv.py:169` až `271`: parser inicializuje `cast_c=[]`, nekontroluje, či časť C bola prítomná a úplne prečítaná, a na riadku 271 vracia `none` aj pre `[]`. Vstup stačí identifikovať ako výpis a nájsť číslo LV; chýbajúce časti A/B/C ho samy neodmietnu. PDF parser používa rovnaký `parse_rows`; analogické správanie náhľadu je v `parsers/nahlad.py:88` až `99`.

**Dôkaz:** syntetická HTML hlavička bez časti C a hlavička s prázdnou časťou C obe vrátili `tarchy=none`. Explicitný text „Bez tiarch.“ tiež vracia `none`. To dokazuje nerozlíšenie stavov v parseri, nie skutočnú ťarchu na konkrétnom LV.

**Dopad:** klient môže dostať nesprávne uistenie „bez tiarch“ pri nedostatočnom vstupe. Návrh: `unknown/none/present`, dôkaz explicitného negatívneho textu, úplnosť každej časti, rozlíšenie úplného a čiastočného výpisu a upozornenie na OCR/parser drift.

### 2. Osobná cache nemá identitu používateľa remote služby

`server.py:55` až `69`, `cache.py:119` až `121`, `osoba.py:58` až `62`: App drží jedno `osoby.sqlite`, kľúč je `(zdroj, ver, kluc)` a prehľad číta všetky aktuálne importy. Dnešný adresár je oddelený podľa OS účtu (`cache.py:32` až `43`); POSIX práva 0700/0600 sú už implementované.

**Dopad pri shared remote:** údaje jedného prihláseného používateľa môžu byť sprístupnené inému, ak sa všetci napoja na túto App. OAuth samotné izoláciu dát nepridáva. Pred remote prevádzkou treba serverom určený tenant z overeného tokenu, autorizáciu každého importu/file/job/exportu a tenantové úložisko. Zdieľať možno iba schválenú verejnú geometriu, nie osobné LV cache alebo ich existenciu cez globálny dedup lookup.

### 3. Nástroje dôverujú lokálnym cestám

`lv.py:68` až `74`, `138` až `141`, `161` až `173`: vstup umožňuje cestu k súboru/priečinku v serverovom filesysteme, vrátane symlinkov bez kontroly koreňa. Obsah sa musí úspešne parsovať ako LV; audit netvrdí univerzálnu exfiltráciu každého súboru. `mapa.py:34`, `50` až `70`: `out_dir` dovoľuje vytvoriť/zapísať mapu do klientom zadanej cesty s právami servera. Výstupy obsahujú lokálne cesty (`lv.py:198`, `mapa.py:71`, `server.py:208`).

**Dopad pri remote:** klient riadi čítanie/zápis ciest servera a dostáva jeho interné cesty. Remote kontrakt má prijímať iba serverom vydané `file_id` a vracať autorizované exporty; lokálne cesty ponechať len pre stdio. Pri čítaní uploadov chrániť aj symlinky, TOCTOU a vlastníctvo objektu.

## P1 – opraviť pred remote pilotom

### 4. Nečíselné IČO môže zodpovedať osobe bez IČO

`osoba.py:51` až `55`: pri pravdivom `ico` sa porovnajú iba číslice. `ico='abc'` a vlastník `ico=None` sa oba zmenia na prázdny reťazec a porovnanie je True. `osoba.py:172` až `177` neplatné IČO pred volaním neodmietne a pri jeho zadaní vynechá kontrolu mena.

**Dôkaz:** presná čistá upstream funkcia `fits`, extrahovaná cez AST bez importu aplikácie, vrátila pre syntetický príklad True; platné osemmiestne IČO pre rovnakého vlastníka vrátilo False. Návrh: normalizovať a validovať ešte pred výberom osôb, zakázať prázdny výsledok a podľa požadovaného kontraktu skontrolovať formát/kontrolnú číslicu. Normalizácia má byť jednotná pre query aj uložený subjekt.

### 5. Import môže prepísať novší alebo úplnejší LV

`lv.py:77` až `82`, `175` až `197`: `_rank` porovná dátum a typ výpisu iba medzi súbormi aktuálnej dávky. Pred `app.osoby.put` sa už uložený LV nečíta. `cache.py:146` až `154` používa `INSERT OR REPLACE`. Poradie nezahŕňa úplnosť ani filtrovaný rozsah parciel. `kataster_lv` pritom explicitne vie generovať čiastočný výpis (`lv.py:101`, `124` až `131`).

**Dôkaz:** staticky overené miesto importu a synteticky overená vlastnosť cache: po zápise obsahu s dátumom 2026 a následne 2025 ostane obsah 2025. Celý MCP import cez tool v tomto audite spustený nebol.

Návrh: nemenné verzie dokumentov, hash v rámci tenantov, dátum platnosti oddelený od času importu, explicitný scope a úplnosť; transakčný výber aktuálnej verzie. Neznámy dátum a čiastočný dokument nesmú potichu nahradiť plný aktuálny LV. Zmena parsera dnes mení verziu cache a staré importy prestanú byť čitateľné pre prehľad – navrhnúť reparse, migráciu alebo jasné oznámenie.

### 6. Limity existujú, ale nekryjú celý upload/parser workload

`lv.py:24` až `25`, `158` až `173`: lokálne súbory max 20 MiB a dávka max 300 súborov. Inline HTML túto kontrolu obchádza; všetky bytes dávky sa načítajú do `items` pred parsovaním. Horný súčet povolených súborov je približne 5,86 GiB pred ďalšími alokáciami. PDF spracúva všetky stránky/runs (`parsers/lv_pdf.py:33` až `49`) bez explicitného aplikačného časového/stránkového limitu.

Návrh: streamovaný upload, spoločný body/batch limit na proxy aj app, limit počtu strán/textu, izolovaný parser worker, CPU/RAM/timeout, ohraničená fronta, per-tenant storage a job kvóty. Defaulty sa majú zvoliť podľa anonymizovaných vzoriek; samotný limit veľkosti súboru nevylučuje expanziu PDF.

### 7. TTL nie je samostatný časovač fyzického vymazania

`cache.py:86`, `105` až `133`, `146` až `153`: osobné riadky sa fyzicky čistia pri otvorení a zápise; pri otvorení s vymazaním navyše VACUUM, `secure_delete=ON` je už implementované. Čítanie uplatňuje TTL, ale neplánuje purge. `server.py:59` a `owners.py:39` až `48`: snapshots sa čistia pri štarte alebo novom parser-drift snapshote. Neaktívny server preto môže mať staré bytes na disku aj po siedmich dňoch. Mapové exporty samostatnú retenciu v kontrolovanom kóde nemajú.

Návrh: periodický backend purge pre uploads, normalizované LV, snapshots, job výsledky a exporty; explicitná politika pre backups, svedectvo posledného purge a manuálne vymazanie používateľových dát. Neprezentovať TTL ako garantované fyzické vymazanie presne v čase expirácie. Reimport obnoví čas uloženia aj starých obsahových dát.

### 8. Súbežnosť a kvóta sa nedajú preniesť na viac workerov bez návrhu

`http.py:34`, `79` až `105`: `asyncio.Lock` a pacing sú na jednej inštancii klienta, nie medzi procesmi. `owners.py:60` až `81` oddelene číta stav a zapisuje kvótu, bez spoločnej atomickej rezervácie limitu. `cache.py:116` vypína thread check, ale to samo nezabezpečuje prácu so zdieľanou connection. Cache miss nemá deduplikáciu práve bežiaceho fetchu. Stráž blokácie sa volá pred získaním HTTP locku; čakajúce požiadavky treba po zistení blokácie znovu skontrolovať.

Ide o statické riziká pre viac requestov/workerov; prekročenie kvóty alebo SQLite race nebolo reprodukované. Súčasná synchrónna kvóta v jedinom event loope môže vykonať kontrolu bez preemptívneho prerušenia, preto audit netvrdí automatickú chybu dnešného stdio servera.

Návrh: jeden fetch worker v prvom pilote, spoločné backend limity a blokácia pre poskytovateľa, atomická rezervácia kvóty, in-flight dedup a idempotentné joby. Pri škálovaní koordinované transakcie/fronta; limity nemultiplikovať počtom používateľov alebo replík.

## Overené vlastnosti a hranice

- MIT, Python >=3.12, MCP SDK 1.x (lock 1.30.0), entrypoint `create_server(PUBLIC_POLICY).run()` (`server.py:219`). 11 decorators `mcp.tool` potvrdených AST; Dockerfile a remote OAuth kód nie sú v tomto clone.
- Geometria C/E ide podľa kódu cez INSPIRE WFS (`sources/wfs.py:10` až `22`). Vlastníci idú cez neoficiálne ESKN identify/detail HTML (`owners.py:104` až `140`). Úplný LV je používateľom získaný manuálny HTML/PDF import; server negeneruje plný výpis sieťovým dotazom.
- Politika autora: 3 s + jitter na ESKN, 50 parciel denne, spoločný procesový HTTP lock a uložená blokácia pri WAF/CAPTCHA. Je to ochranná implementačná kvóta, nie oficiálne povolenie scrapingov alebo potvrdenie podmienok poskytovateľa. V tomto audite sa na kataster neposlal dotaz.
- Nie sú vyslovené nové právne závery zo staršieho susedného projektu. Licencia kódu MIT nerieši podmienky dát a osobných údajov.
- Upstream obsahuje anonymizované fixtures a offline/live rozlíšenie v pytest konfigurácii. Plná pytest sada nebola spustená a nehlásime ju ako úspešnú.

## Reprodukcia a dôkazy

Z koreňa clone možno opakovať `python3 -B docs/research/verify_audit.py`. Skript spúšťa iba prečítaný štandardnoknižnicový LV parser/cache a presnú čistú funkciu `fits` extrahovanú AST; zapisuje len susedný syntetický `audit-evidence.json` a dočasnú SQLite v temp adresári. Neinštaluje závislosti, neštartuje server a nevolá sieť.

Pri audite skončil s exit code 0. [Výsledok](audit-evidence.json) zachytáva tri scenáre časti C, dva scenáre IČO, last-write-wins cache a názvy 11 tools. Nepoužíva živé LV ani mená vlastníkov.
