# Zálohy a obnova

Používateľ zvolil zatiaľ šifrovanú lokálnu zálohu a návod na externý cieľ. Na Dokploy nebol 12. 10. 2026 nastavený žiadny backup destination ani volume backup/schedule pre Kataster a Auth. Toto je odlišné od dostupnosti persistentných volumes: samotný volume nie je záloha.

## Overená lokálna záloha

Šifrované súbory sú mimo Git v `/Users/Magneto/.config/skallars-auth/backups/`, práva adresára 0700 a súborov 0600. Každý snapshot má náhodný AES-256-GCM kľúč, nonce a autentifikačný tag. Kľúč je zabalený pomocou verejného RSA-3072 kľúča, OAEP SHA-256, s väzbou na službu. Privátny recovery key sa na Dokploy neposielal.

Auth snapshot obsahuje konzistentnú SQLite cez VACUUM INTO a persistentnú konfiguráciu vrátane podpisových/cookie kľúčov. Kataster snapshot používa SQLite backup API, obsahuje súbory tenantov, globálnu kvótu poskytovateľa a konfiguráciu. Nezálohuje otvorené WAL/shm ako samostatné nekonzistentné súbory. Pri obnove sa kontroluje AEAD, SHA256, bezpečné relatívne cesty a SQLite integrity_check.

Reálna skúšobná obnova oboch snapshotov do samostatného dočasného adresára prešla. Auth mal jednu existujúcu osobu a zachované kľúče; Kataster obnovil šesť súborov, z toho päť SQLite. Dočasný nešifrovaný restore bol po kontrole odstránený. Produkčné volumes sa neprepisovali. Plný obnovený server s OAuth business call ešte nie je týmto testom potvrdený. Snapshot vznikol pred pozvánkou kolegu.

Dôkazy: [backup-verification-2026-10-12.json](research/backup-verification-2026-10-12.json).

## Recovery key

Privátny kľúč `recovery-key.pem` chráň osobitne od záloh. Strata tohto kľúča znamená stratu možnosti obnovy. Kópia zálohy aj kľúča na jedinom Macu nechráni pred stratou tohto počítača. Kľúč patrí aj do vlastného bezpečného správcu tajomstiev alebo iného používateľom spravovaného chráneného miesta. Neprikladaj ho do Git, chatu ani marketplace balíka.

## Externý cieľ

Po výbere S3/B2/R2/NAS vytvor samostatný súkromný bucket alebo cestu, povoľ iba potrebné read/write oprávnenia a nastav TLS. Prenášaj šifrované snapshoty, nie pôvodnú SQLite alebo recovery key. Nastav ohraničenú retenciu, pre Kataster najviac sedem dní záloh, a upozornenie na zlyhanie. Záloha môže dočasne uchovávať už vymazané osobné dáta do svojej expirácie; retencia prevádzky a záloh nie sú totožné.

Samotný Dokploy tar živého SQLite volume bez zastavenia alebo konzistentného snapshotu nie je náhrada aplikačného backup API. Po nastavení cieľa prever prenos, poškodený alebo cudzí snapshot, obnovu do izolovaného priestoru a následný štart služby. Automatické zálohovanie sa má označiť za hotové až po overení bežiacej úlohy a obnovy jej výsledku.
