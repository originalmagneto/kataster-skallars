---
name: kataster-skallars
description: Zisťovanie údajov zo slovenského katastra cez Kataster MCP alebo sk-kataster CLI. Použi pri konkrétnych parcelách C/E, vlastníkoch, listoch vlastníctva (LV), ťarchách v dodanom LV, katastrálnych územiach, mapách parciel a importe HTML/PDF výpisov. Prehľad majetku osoby pokrýva iba vlastné importy. Samotný výklad katastrálneho práva bez zisťovania údajov sem nepatrí.
---

Vyber jednu dostupnú cestu podľa úlohy. Ak je nainštalovaný `sk-kataster`, preferuj úzky CLI príkaz pre úsporu kontextu. Inak použi priamo dostupný Kataster MCP; chýbajúce CLI nie je dôvod na odmietnutie úlohy. Rešpektuj používateľom zvolenú lokálnu alebo remote službu a jej cache. Rovnakú operáciu nevolaj cez obe registrácie.

Pri CLI over `command -v sk-kataster`; pri probléme použi `sk-kataster --json doctor`. Lokálne operácie nepotrebujú prihlasovanie. Remote pilot používa `sk-kataster --json remote tools` na overenie spojenia a autentifikácie; token nikdy nevypisuj. Už fungujúce spojenie netestuj opakovane pred každým dotazom.

Pri parcele najprv rozlíš katastrálne územie cez `kataster_ku`, potom použi `kataster_parcela` s číslom a registrom C/E alebo so súradnicami. Nezamieňaj obec a k.ú.; pri nejednoznačnosti si nechaj doplniť identifikátor. Vlastníkov zisťuje `kataster_vlastnici`, geometria parcely ich neobsahuje. `kataster_vrstvy` dopĺňa dostupné tematické údaje, `kataster_skupina` geometriu skupiny. Na lokálnu mapu použi `kataster_mapa`. Pred volaním si pozri schému konkrétneho nástroja; nevymýšľaj argumenty ani chýbajúce údaje. Vyžiadané konkrétne zisťovanie môže volať portál v jeho limitoch.

Začni úzkym príkazom; celé MCP schémy načítaj iba podľa potreby:

```sh
sk-kataster --json ku resolve 'Vyšný Kubín'
sk-kataster --json lv inspect '/absolutna/cesta/vypis.pdf'
sk-kataster --json lv import '/absolutna/cesta/vypis.pdf' --dry-run
```

`lv inspect` nič neukladá. Po požiadavke používateľa na import použi `lv import` bez `--dry-run`; osobné údaje sa ukladajú do lokálnej cache. Výsledok je predvolene súhrn, `--full` vracia aj vlastníkov a položky. `person overview --name 'Meno Priezvisko'` alebo `--ico 12345678` pracuje iba s importovanými LV. Nejde o úplný súpis majetku osoby.

Úspech má `{data, zdroje, varovania}`, chyba `{chyba, zdroje, varovania}` a nenulový exit code. `tarchy=unknown` znamená chýbajúcu alebo neprečítanú časť C. `none` vyžaduje explicitné „Bez tiarch.“ v prečítanom texte a platí iba pre dodaný rozsah. `see cast_c` vyžaduje prečítanie obsahu cez `--full`, nie automatický záver o druhu ťarchy. `uplnost` opisuje čitateľnosť častí, nepotvrdzuje úplnosť výpisu.

`ulozenie.stav=preserved_existing` znamená, že vstup nenahradil uložený LV. Výsledok importu opisuje nový vstup, prehľad osôb naďalej číta starý záznam. Pri zmenšenom rozsahu treba preveriť úplnosť alebo skutočnú zmenu vlastníctva; netvrď, že starší záznam predstavuje aktuálny stav.

Pre ďalšie nástroje použi `sk-kataster --json tools`, potom `tools NAZOV` a až potom `call NAZOV '{"argument":"hodnota"}'`. `call` môže volať portál, importovať údaje alebo zapisovať mapy; vyber iba operáciu vyžiadanú používateľom. Pri dostupnom MCP možno rovnaké nástroje volať priamo. Nekombinuj duplicitné importy oboma cestami.

Pre remote import použi `remote upload CESTA` a potom `remote call kataster_lv_import '{"file_id":"ID_Z_UPLOADU"}'`. Súbor sa prenesie na Dokploy, kde patrí iba danému používateľovi. Príloha v chate ani lokálna cesta nie sú remote file_id. Lokálna a remote cache sú oddelené. Pri HTTP 429 rešpektuj Retry-After; pri 401 prever prístupový token, bez hromadných opakovaní. Remote mapové exporty a OAuth zatiaľ nie sú podporované.

CAPTCHA rieši používateľ. Neobchádzaj blokáciu ani kvóty. Pri zlyhaní portálu neopakuj hromadne volania. Zdroj, dátum údajov, rozsah a varovania zahrň do záverov. Prevádzkové údaje a živé LV neukladaj do repozitára.
