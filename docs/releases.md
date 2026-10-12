# Vydania a izolovaná obnova

Kataster backend/CLI má verziu 0.6.0, Auth 0.2.0. Pluginové manifesty majú
samostatný životný cyklus a táto zmena ich nemení.

CI nasadzuje iba úspešne testovaný push do main. Kataster čaká na celú OS/Python
matrix, Auth na npm testy, audit a Docker build. Release job má contents:write,
samostatnú concurrency skupinu a nevypína rozbehnuté vydanie. Image sa pushuje
do privátneho registry-mcp.aittorney.online s tagom source SHA. Z Docker inspect
sa preberá immutable digest, nikdy latest. OCI revision label obsahuje source SHA.

Oba repozitáre obsahujú bitovo rovnaký scripts/promote_release.py a jeho test.
Žiadny runtime token nepristupuje do druhého privátneho repozitára. Skript číta
presný source tree SHA cez GitHub Git Commit API, nahradí iba build za image
digest, nastaví literal SOURCE_REVISION a uloží .dokploy-release.json. Nový commit
má parent posledný dokploy-production. Ref aktualizuje cez force:false. Main
skontroluje pred prípravou aj bezprostredne pred aktualizáciou, starší job preskočí.
Production vetvu upravuje iba táto pipeline.

Dokploy sleduje dokploy-production, compose.yaml a má zapnutý Auto Deploy.
DOKPLOY_WEBHOOK je scoped compose refresh URL, nikdy plný Dokploy API kľúč.
POST má x-github-event:push, presný ref, release commit SHA a compose watch-path
payload. Prípadný GitHub App webhook smeruje na rovnaký digest. Webhook URL ani
HTTP exception s URL sa nezapisujú do logov.

Kontroly sú oddelené: health musí mať cieľovú revision, OAuth metadata správnu
resource/issuer a chránený endpoint musí odmietnuť volanie bez tokenu 401.
Kataster MCP schema a stdio handshake sú offline regresie. OAuth business smoke
vykoná správca po vydaní, pipeline ho nepredstiera. Pri chybe alebo timeout po
promotion vytvorí skript nový lineárny rollback commit na tree práve testovaného
candidate. Obnoví presný obsah predchádzajúcich compose.yaml a .dokploy-release.json,
zavolá webhook a overí predchádzajúcu revision. Pred promotion overí zhodu pôvodného
compose so šablónou jeho source SHA, literal image digest a SOURCE_REVISION, bez build.
Tým zachová starší runtime image, jeho source revision, environment a volume
konfiguráciu. Obsah databáz a volumes sa nevracia do minulosti.

Súbory workflow a nepoužívaný zdrojový kód v machine vetve zostanú z aktuálneho
candidate. Kontajnery bežia z pinovaného image s pomenovanými volumes, bez bind
mountu hostiteľského zdrojového kódu. Git tree rollback preto nie je potrebný
na runtime rollback. Natívny GITHUB_TOKEN s contents:write v izolovanej CI skúške
38302378473 odmietol návrat celého starého tree odpoveďou 403, ale obnovu dvoch
runtime súborov na aktuálnom tree povolil odpoveďou 200. Pipeline nevyžaduje širší
PAT, vlastnú GitHub App ani plný Dokploy API kľúč. Externé Dokploy environment
hodnoty zostávajú počas promotion aj rollback rovnaké. Zmena autentifikačného
režimu alebo nekompatibilná migrácia vyžaduje osobitný overený baseline.
Pri nejednoznačnej odpovedi ref PATCH sa načíta skutočný stav vetvy. Rollback
sa vykoná iba ak je candidate aktuálny; pôvodný parent sa nemení, iný alebo
nečitateľný stav vyžaduje zásah správcu. Volume názvy a konfigurácia zostávajú rovnaké. Ak zlyhá aj rollback alebo vetvu
zmení iný aktér, CI zlyhá a vyžaduje zásah správcu.

## Prvé zapojenie správcom

1. Nasadiť Auth deploy/registry.compose.yaml, TLS doménu na interný port 5000,
   bez otvoreného host portu. Init aj server používajú pinovaný registry 3.1.2.
   Init dostane iba REGISTRY_HTPASSWD, bcrypt riadok vytvorený mimo Git.
   V Dokploy dotenv jeho hodnotu uzavrieť do jednoduchých úvodzoviek, aby sa
   bcrypt dolárové segmenty neinterpolovali ako environment premenné. Uloží ho
   privátne do auth volume a nastaví vlastníctvo. Heslo na serveri nie je potrebné.
   Hlavný server má UID 10001, readonly auth mount a persistentné data volume.
2. V oboch GitHub repo nastaviť iba REGISTRY_USER, REGISTRY_PASSWORD,
   DOKPLOY_WEBHOOK. Registry credential pre Dokploy pull uložiť cez Dokploy,
   nikdy do compose. GITHUB_TOKEN dodáva job.
3. Pred prvým vydaním vytvoriť production baseline z overeného aktuálneho image
   digestu a source SHA. Vetva obsahuje compose s image a literal revision
   a .dokploy-release.json s source (40 hex), image (registry digest),
   service (kataster alebo auth), origin (presná produkčná HTTPS origin).
   Baseline musí zodpovedať skutočne healthy prevádzke. Bez baseline skript
   odmietne promotion pred zmenou ref, pretože nemá overiteľný rollback.
4. Overiť GitHub workflow permissions, machine branch update a Dokploy
   branch/watch-path konfiguráciu. Potom vykonať dve automatické vydania a
   riadenú rollback skúšku. To sú živé prevádzkové kontroly správcu.

Registry má vypnuté mazanie. Retencia image musí zachovať aktuálne a aspoň dve
predchádzajúce production vydania, ich manifesty aj bloby. Pred čistením správca
zosúladí production históriu oboch repo s registry digestmi. Garbage collection
len v servisnom okne po tomto výbere, bez mazania volumes. Sledovať disk, upozorniť
pri 80 % zaplnení a rozšíriť ho pred ďalším pushom pri 90 %. Automatické mazanie
nie je zavedené, tým sú rollback obrazy zachované.

Oficiálne kontrakty overené 12. 10. 2026:
[GitHub refs API](https://docs.github.com/en/rest/git/refs),
[GitHub Git trees API](https://docs.github.com/en/rest/git/trees),
[Dokploy Auto Deploy](https://docs.dokploy.com/docs/core/auto-deploy).
Scoped compose payload navyše overený v handleri nasadenej verzie Dokploy 0.30.8,
/api/deploy/compose/[refreshToken].

## Kataster backup CLI

```sh
sk-kataster --json --data-dir /data backup snapshot --public-key /data/backup-public.pem --directory /data/backups --retain-days 7
sk-kataster --json backup restore --input /private/backups/kataster-TIMESTAMP.enc.json --private-key /private/recovery-private.pem --destination /private/isolated-restore
```

RSA privátny recovery kľúč s aspoň 3072 bitmi zostáva na Macu. Server dostane iba
verejný kľúč. AES-256-GCM a RSA-OAEP SHA256 používajú AAD/label
skallars-backup:v1:kataster. Vonkajší envelope má rovnaké polia ako Auth:
format, service, iv, tag, key, ciphertext. Config a SHA256 manifest sú šifrované.
Snapshot zahrnie relevantné SK_KATASTER_* env nastavenia vrátane privátnej
service konfigurácie, bez otvoreného výpisu do logu.

SQLite backup API zachová commitnuté WAL dáta, samotné WAL/shm sa nearchivujú.
Privátny staging je v backup adresári na persistentnom disku, vylúčený zo zdroja,
preto nezávisí od produkčného 32 MiB /tmp. SQLite page count/page size, progress
callback a výsledný súbor sa kontrolujú proti zostávajúcemu 128 MiB budgetu
ešte pred bounded čítaním.
Snapshot odmietne symlinky, viac než 4096 súborov alebo 128 MiB zdrojových dát.
Backups adresáre, zvolený výstupný adresár a encrypted snapshots sú vylúčené.
Koreňové config.json a manifest.json sú vyhradené na obnovu, snapshot takého
zdroja odmietne. Retencia 1 až 30 dní maže iba vlastné expirované súbory priamo
v backup adresári, nikdy vnorené adresáre alebo symlinky. Výstup sa publikuje
atomicky s 0600, privátny adresár má 0700.

Obnova overí AEAD, manifest, bezpečné relatívne cesty a SQLite quick_check.
Cieľ nesmie existovať. Súbory sú pripravené v privátnom dočasnom adresári a do
rezervovaného nového cieľa sa prenesú atomicky po súboroch. Produkcia sa neprepisuje.
Starší snapshot nevie potvrdiť zostávajúcu kvótu alebo neskoršiu CAPTCHA blokáciu,
preto obnova v známych provider SQLite tabuľkách vyčerpá dnešnú kvótu a nastaví
konzervatívnu 24-hodinovú ESKN pauzu. Pôvodné quota/cache záznamy zostávajú.
Manifest zachová pôvodné snapshot SHA256 a restoredFilesSha256 výsledku s touto
bezpečnostnou úpravou. Prevádzková obnova vyžaduje izolovaný smoke a presun správcom,
nikdy zníženie kvóty alebo blokácie aktívnej služby. Zálohy nepatria do Git.

Existujúci Auth snapshot/restore a daily schedule sú samostatné mechanizmy.
Scheduled snapshot a skutočnú obnovu overuje správca.

Lokálny registry verifier používa verejné syntetické credentials, dočasné Docker
volumes a loopback port, po skončení ich odstráni:

```sh
python3 ../skallars-auth/deploy/verify_registry.py
python3 scripts/test_promote_release.py
uv run --frozen pytest
uv build
```
