# Samostatný remote pilot na Dokploy

Endpoint: `https://mcp-kataster.aittorney.online/mcp`. Zdroj je súkromný `originalmagneto/kataster-skallars`. Gateway nie je súčasťou požiadavky ani úložiska. Lokálne stdio a CLI zostávajú dostupné.

## Skúšanie cez CLI

Mariánov pilotný token expiruje 10. 1. 2027; predtým ho treba rotovať. Na tomto počítači je token v `~/.config/kataster-skallars/remote.token` s právami 0600. Hodnotu neposielaj do chatu ani do Git. Predvolená adresa je už nastavená v CLI.

```sh
sk-kataster --json remote doctor
sk-kataster --json remote tools
sk-kataster --json remote call kataster_ku '{"query":"Záhorská Bystrica"}'
sk-kataster --json remote upload '/absolutna/cesta/vypis.pdf'
sk-kataster --json remote call kataster_lv_import '{"file_id":"ID_Z_UPLOADU"}'
sk-kataster --json remote call kataster_osoba_prehlad '{"priezvisko":"Priezvisko","meno":"Meno"}'
```

`doctor` kontroluje verejný health endpoint. `tools` a `call` zároveň preveria autentifikáciu. Upload vracia náhodný identifikátor súboru. Import je predvolene súhrn; `"full":true` vráti aj vlastníkov a položky. Pred uploadom citlivého dokumentu možno použiť lokálne `lv inspect`. Príloha v chate sa na server neprenáša automaticky.

Na druhom počítači: sprístupni si súkromný repozitár, nainštaluj Python >=3.12 a uv, klonuj repo, spusti `uv sync --frozen`, potom `uv run sk-kataster ...`. Prenes svoj token bezpečnou cestou do súboru 0600. Cestu možno zadať cez `remote --token-file CESTA`. Alternatíva je premenná `SK_KATASTER_TOKEN`; URL sa dá zmeniť cez `--url` alebo `SK_KATASTER_URL`.

## Codex a Claude Code

V oboch klientoch použi Streamable HTTP URL vyššie a hlavičku `Authorization: Bearer TOKEN`. Na tomto počítači je registrácia pomenovaná `kataster-skallars-remote`; lokálna `kataster-skallars` zostáva samostatná. Skill pozná oba režimy. Po zmene konfigurácie otvor nový chat alebo obnov MCP spojenia.

Codex konfigurácia podporuje `url` a `http_headers`, prípadne `bearer_token_env_var`, ak proces Codexu danú premennú skutočne zdedí. Claude Code podporuje `claude mcp add --transport http --scope user NAZOV URL --header 'Authorization: Bearer TOKEN'`. Do dokumentácie ani terminálovej histórie nevpisuj skutočný token. [Codex dokumentácia](https://developers.openai.com/codex/mcp), [Claude Code dokumentácia](https://code.claude.com/docs/en/mcp).

Toto je autentifikovaný súkromný pilot s osobnými tokenmi, nie OAuth authorization server. Google login, refresh, CIMD/DCR a prihlásenie cez cloudový Claude/ChatGPT konektor nie sú implementované. Nesmie sa distribuovať ako hotová OAuth integrácia.

## Kolega a správa tokenov

Každý kolega dostane vlastný náhodný token a stabilný názov používateľa. Neposielaj mu Mariánov token. Backend ukladá len SHA-256 tokenu, názov používateľa a unixovú expiráciu. Konfigurácia `SK_KATASTER_TOKENS` je JSON pole s kľúčmi `tenant`, `sha256`, `expires`; najviac 16 záznamov. Neodvodzuje identitu z argumentov MCP ani zo session ID.

Správca pridá záznam do Dokploy environment, zachová existujúce záznamy a redeployne túto službu. Použi 48 náhodných bajtov (`secrets.token_urlsafe(48)`), SHA-256 UTF-8 tokenu a napríklad 90-dňovú expiráciu. Token ulož do súboru 0600 mimo repo. Po rotácii alebo odobratí hash zmeň/odstráň a redeployni. Pri nasadení cez konfiguračný súbor sa kontrola obnovuje pri každom requeste, pri environment konfigurácii sa zmena uplatní reštartom kontajnera. Nový používateľ vždy potrebuje reštart. Samotná expirácia sa overuje pri každom requeste a nepotrebuje restart.

## Limity a dáta

- Jedna replika, jedno aktívne volanie nástroja alebo upload a najviac 8 takýchto požiadaviek vrátane čakajúcich. Až naplnená fronta vracia HTTP 429 s Retry-After 3 s. Discovery a notifikačné streamy MCP 2026 subscriptions/listen bežia mimo provider zámku; celková HTTP súbežnosť procesu je ohraničená na 64. Legacy GET stream vracia 405. Zdieľaný Http klient, blokácie poskytovateľov aj denná kvóta 50 parciel bránia násobeniu limitov počtom používateľov.
- Upload HTML/PDF najviac 5 MiB, najviac 50 súborov na používateľa; originály expirujú po 24 hodinách. Parser: vlastný proces, 20 s wall time, na Linuxe 15 s CPU a 512 MiB adresného priestoru, PDF do 100 strán, normalizovaný výsledok do 2 MiB.
- Importovaná osobná cache má TTL 7 dní a limit SQLite 64 MiB na používateľa. Každý má vlastnú databázu. Purge beží každých 60 s aj bez requestov a zahŕňa už odobratých používateľov. Reimport môže obnoviť retenčný čas. SQLite secure_delete nie je záruka vymazania zo snapshotov/backupov hostiteľa.
- Kontajner beží ako UID 10001, read-only root, bez capabilities, no-new-privileges, 1 GiB RAM, 1 CPU, 64 procesov. Dáta sú na pomenovanom lokálnom volume, temp je obmedzený tmpfs. Žiadne hostiteľské porty sa nepublikujú; HTTPS smeruje cez Dokploy Traefik.
- Remote neprijíma `path`, `paths`, `html` ani `out_dir`. Mapový export je v pilote dostupný iba lokálne. Na remote je 10 nástrojov.
- Neúplný LV nesmie viesť k záveru „bez tiarch“. Zmena rozsahu alebo vlastníkov môže byť odmietnutá konzervatívnou ochranou cache; vtedy sa vráti `preserved_existing`. Nemenná história verzií a riešenie konfliktov ešte nie sú implementované.

## Nasadenie a aktualizácie

Dokploy projekt `Kataster SKALLARS`, projectId `YHYVENJmOuc68caY78CnS`, composeId `hR1vGslIGKJEntXc667AS`, služba `kataster`, compose súbor `./compose.yaml`. GitHub zdroj používa súkromný origin main. Docker base images sú pinované digestom, Python dependencies cez uv.lock.

Priamy Dokploy autoDeploy je vypnutý. Nasadzuj až po úspešných testoch konkrétneho commitu a nastav `SOURCE_REVISION` na tento SHA. Health endpoint vracia nakonfigurovaný SHA, sám osebe však nedokazuje obsah image. Deployment log a zdrojový commit treba kontrolovať spolu. Kompletná pipeline testy -> image digest -> deploy -> rollback ešte nie je implementovaná. Automatické aktualizácie Gateway sú samostatný ďalší pracovný celok, nie vedľajší účinok tohto deployu.

Obnova: pred zmenou deploymentu zachovaj pôvodný image/source SHA a osobitne volume. Tento pilot nenastavuje zálohy osobných dát ani nepreukazuje obnovu zo záloh. Pri strate cache možno znova importovať používateľom uchované originály. Nikdy nepouži `down -v` na produkčnej službe.

## Overenie

Nasadené 12. 10. 2026: commit `4a5d1d545445e55aceb95a430387d7735912e881`, verzia 0.4.0. 151 offline testov; všetkých 6 CI kombinácií Linux/macOS/Windows a Python 3.12/3.14 prešlo. Codex zavolal remote nástroj, Claude Code cez HTTPS hlási Connected vrátane načítania nástrojov. Syntetický LV bol importovaný skúšobným používateľom a iný používateľ k nemu nemal prístup. Skúšobný token bol následne odobratý a vracia 401. [Sanitizovaný záznam](research/remote-pilot-verification-2026-10-12.json).

Offline testy pokrývajú token, expiráciu/revokáciu, Host/Origin, nečitateľný a príliš veľký upload, cudzí file_id, zakázané cesty, izoláciu osôb, TTL aj po odobratí používateľa, zabitie parsera a reálny HTTP subprocess klienta CLI. Živé katastrové portály sa v týchto testoch nevolajú. Web UI nevzniklo, Safari test sa preto neuplatňuje.
