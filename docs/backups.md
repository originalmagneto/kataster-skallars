# Zálohy a obnova

Používateľ zvolil zatiaľ šifrovanú lokálnu zálohu a návod na externý cieľ. Externý Dokploy backup destination zatiaľ nie je nastavený. Auth už má denný aplikačný snapshot; Kataster 0.6.0 už má tiež denný aplikačný snapshot. Toto je odlišné od dostupnosti persistentných volumes: samotný volume nie je záloha.

## Overená lokálna záloha

Šifrované súbory sú mimo Git v `/Users/Magneto/.config/skallars-auth/backups/`, práva adresára 0700 a súborov 0600. Každý snapshot má náhodný AES-256-GCM kľúč, nonce a autentifikačný tag. Kľúč je zabalený pomocou verejného RSA-3072 kľúča, OAEP SHA-256, s väzbou na službu. Privátny recovery key sa na Dokploy neposielal.

Auth snapshot obsahuje konzistentnú SQLite cez VACUUM INTO a persistentnú konfiguráciu vrátane podpisových/cookie kľúčov. Kataster snapshot používa SQLite backup API, obsahuje súbory tenantov, globálnu kvótu poskytovateľa a konfiguráciu. Nezálohuje otvorené WAL/shm ako samostatné nekonzistentné súbory. Pri obnove sa kontroluje AEAD, SHA256, bezpečné relatívne cesty a SQLite integrity_check.

Reálna skúšobná obnova oboch snapshotov do samostatného dočasného adresára prešla. Auth mal jednu existujúcu osobu a zachované kľúče; Kataster obnovil šesť súborov, z toho päť SQLite. Dočasný nešifrovaný restore bol po kontrole odstránený. Produkčné volumes sa neprepisovali. Tento prvý snapshot vznikol pred pozvánkou kolegu. Jeho vnútorný formát nemá nový manifest; pre CLI restore používaj novšie plánované snapshoty.

Dôkazy: [backup-verification-2026-10-12.json](research/backup-verification-2026-10-12.json).

## Plánovaný Auth snapshot a plná obnova

Auth na Dokploy vykonáva snapshot denne o 02:15 Europe/Bratislava. Server má iba
verejný RSA kľúč a ponecháva šifrované súbory sedem dní. Dve manuálne spustenia
skutočného Dokploy schedule prešli. Výsledný snapshot bol prenesený do chráneného
lokálneho adresára na Macu.

Obnova tohto plánovaného snapshotu cez dodané restore API do nového izolovaného
adresára prešla. Obnovený Auth sa spustil, poskytol OAuth metadáta a introspekciu
skutočného opaque tokenu. Podpisové aj cookie kľúče ostali zhodné. Produkčný volume
sa neprepisoval a nešifrovaný dočasný restore bol odstránený. Denná úloha zatiaľ
vytvára súbory na serveri; automatický prenos mimo servera nie je nakonfigurovaný.

## Plánovaný Kataster snapshot a plná obnova

Kataster vykonáva snapshot denne o 02:30 Europe/Bratislava s rovnakou sedemdňovou
retenciou. Skutočné manuálne spustenie Dokploy schedule prešlo. Šifrovaný súbor
277151 bytes bol skopírovaný na Mac a jeho SHA256 bol overený.

Restore CLI obnovil snapshot do nového privátneho adresára. Obnovená služba sa
spustila iba na localhoste, poskytla správne OAuth metadáta a cez skutočný opaque
token vykonala kataster_status aj import obnoveného syntetického uploadu. Portál
sa nedopytoval. Produkcia sa neprepisovala a plaintext restore bol odstránený.
Obnova zachováva konzervatívny provider guard podľa docs/releases.md.

## Recovery key

Privátny kľúč `recovery-key.pem` chráň osobitne od záloh. Strata tohto kľúča znamená stratu možnosti obnovy. Kópia zálohy aj kľúča na jedinom Macu nechráni pred stratou tohto počítača. Kľúč patrí aj do vlastného bezpečného správcu tajomstiev alebo iného používateľom spravovaného chráneného miesta. Neprikladaj ho do Git, chatu ani marketplace balíka.

## Externý cieľ

Po výbere S3/B2/R2/NAS vytvor samostatný súkromný bucket alebo cestu, povoľ iba potrebné read/write oprávnenia a nastav TLS. Prenášaj šifrované snapshoty, nie pôvodnú SQLite alebo recovery key. Nastav ohraničenú retenciu, pre Kataster najviac sedem dní záloh, a upozornenie na zlyhanie. Záloha môže dočasne uchovávať už vymazané osobné dáta do svojej expirácie; retencia prevádzky a záloh nie sú totožné.

Samotný Dokploy tar živého SQLite volume bez zastavenia alebo konzistentného snapshotu nie je náhrada aplikačného backup API. Po nastavení cieľa prever prenos, poškodený alebo cudzí snapshot, obnovu do izolovaného priestoru a následný štart služby. Automatické zálohovanie sa má označiť za hotové až po overení bežiacej úlohy a obnovy jej výsledku.
