# Kataster: najprv samostatný súkromný projekt

Potvrdená remote doména: `mcp-kataster.aittorney.online` na používateľovom Dokploy.

Implementačný stav po schválenom pokračovaní: [lokálny pilot 0.3.0](../local-pilot.md). Nižšie je pôvodný návrh a audit; tvrdenie o nevytvorenom private repozitári zachytáva stav pred implementáciou.

Aktualizácia smerovania podľa používateľa z 12. 10. 2026. Tento dokument má prednosť pred odporúčaním použiť SKALLARS gateway už v prvom pilote v `distribution-and-remote-proposal-2026-10-12.md`. Technické zistenia pôvodného návrhu zostávajú použiteľné.

## Rozhodnutie o poradí

Najprv samostatný súkromný repozitár s Python jadrom, CLI, lokálnym MCP, skillom a vlastným remote MCP na používateľovom Dokploy. Priame pripojenie do Codexu a Claude Code, praktické zlepšovanie a až následne voliteľné zaradenie do SKALLARS gateway. Gateway nebude závislosťou prvého nasadenia ani podmienkou používania Katastra.

Budúce publikovanie local/remote balíkov v LAWOSS zostáva samostatnou etapou. Súkromný kód ani prevádzkové údaje sa nesmú automaticky kopírovať do verejného katalógu.

## Overený vzťah existujúcich služieb

Read-only Dokploy kontrola 12. 10. 2026:

| Služba | Nastavený zdroj v Dokploy | AutoDeploy |
|---|---|---|
| Samostatný Slov-Lex | `originalmagneto/slov-lex-mcp-deploy`, `main`, GitHub | true |
| Samostatný ORSR | `originalmagneto/orsr-mcp`, `main`, GitHub | true |
| Samostatné Judikáty | `originalmagneto/judikaty-mcp`, `main`, GitHub | true |
| SKALLARS gateway | raw Compose, bez pripojeného GitHub repozitára/vetvy | true, ale tento príznak sám osebe neznamená synchronizáciu zdrojových MCP |

Tieto nastavenia nedokazujú, že každý posledný commit zdroja už úspešne beží v kontajneri. Na úplný audit aktuálnosti treba pre každý server porovnať source SHA, image digest a runtime version. V tejto úlohe sa overovala distribučná cesta, nie všetky funkcie všetkých serverov.

Gateway má v Dokploy nakonfigurovaný image `skallars-mcp-gateway:b231022cfa49646a`; najnovší vrátený deployment record má stav done a čas `2026-09-12T17:05:06.021Z`. Ide o evidenciu riadiacej vrstvy, nie introspekciu bežiaceho kontajnera.

Zdrojový `gateway/catalog-release.json` pripína verejný `Omni-Legal-Products/lawoss-marketplace` na `a012fab7ea6ab49bc65009a2a335d7669941eb03`. Dnešný GitHub `main` bol pri kontrole `8a0b699ecc40de1fec702fec2131b92e9071ab97`; compare API vrátilo ahead_by=118, behind_by=0. Nie sú to verzie SDK ani počet zmien jedného registra. Skorší lokálny checkout marketplace `491cd0f` preto tiež nemožno označovať za aktuálny vzdialený main.

Zdroj gateway obsahuje 22 služieb: CRZ, osem českých služieb, DISQ, EUR-Lex, FS, Judikáty, kalkulačky, ORSR, OV, RPO, RPVS, RU, RUZ, Slov-Lex a UVO. Účto+ a HITL Forms z používateľovho Dokploy v tomto katalógu nie sú. Rovnaký názov registra v gateway a v samostatnom Dokploy projekte neznamená rovnaký runtime alebo jeho verziu.

## Ako sa gateway dnes aktualizuje

Overené v `gateway/update.py` a `docs/updating-hosted.md` súkromného repozitára:

1. Operátor poskytne čistý checkout verejného LAWOSS katalógu na schválenom commite.
2. Updater stiahne jeho archív pre presný SHA, overí hash a bezpečnosť archívu.
3. Z prenosných runtime launcherov načíta schémy. Nové neschválené tools iba nahlási; nezverejní ich automaticky.
4. Pripraví deployment artefakt. Nasadenie vyžaduje explicitný `--deploy`.

Updater neťahá súkromné zdrojové MCP repozitáre a neaktualizuje samostatné MCP služby na Dokploy. Súčasná cesta je približne:

```text
schválená organizačná verzia MCP
    -> pribalený runtime vo verejnom LAWOSS katalógu
    -> pripnutý archív katalógu v SKALLARS gateway
    -> pripravenie a nasadenie gateway

súkromný MCP GitHub repo
    -> jeho samostatná Dokploy služba
```

Zdroje: [postup aktualizácie gateway](https://github.com/originalmagneto/skallars-marketplace/blob/8a1219227b6dff2d41a36c715866b07225e9b60b/docs/updating-hosted.md), [pripnutý katalóg](https://github.com/originalmagneto/skallars-marketplace/blob/8a1219227b6dff2d41a36c715866b07225e9b60b/gateway/catalog-release.json), [porovnanie katalógu](https://github.com/Omni-Legal-Products/lawoss-marketplace/compare/a012fab7ea6ab49bc65009a2a335d7669941eb03...8a0b699ecc40de1fec702fec2131b92e9071ab97).

## Upravený postup pre Kataster

1. **Súkromný zdroj.** Aktuálny `originalmagneto/kataster-braklo-mcp` je podľa GitHub API public fork. Pripraviť nový samostatný private repozitár s dohodnutým názvom, zachovať upstream históriu a MIT atribúciu. Starý `../kataster-MCP` nechať oddelený. Pred ďalším pushom jednoznačne nastaviť súkromný cieľ; žiadne osobné údaje do Git ani tam.
2. **Správnosť a lokálna použiteľnosť.** Regresné opravy LV/IČO/importov, SDK migrácia, spoločné doménové služby, CLI a compact výsledky, hlavný skill. Priame stdio a CLI overiť v Codexe a Claude Code na syntetických údajoch.
3. **Vlastný remote na používateľovom Dokploy.** Vlastná HTTPS adresa a kontajner, používateľské úložisko, upload API, kvóta a retencia. Autentifikácia musí fungovať nezávisle od gateway. Pri výbere použiť overenú OAuth knižnicu/provider a konkrétny kontrakt identity, nie kopírovať heslovú bránu registrov ako údajný viacpoužívateľský systém. Poskytovateľa/doménu vybrať pred HTTP pilotom. Pre prvý vývoj postačí loopback so syntetickými dátami, vzdialené súkromné dokumenty až s autentifikáciou.
4. **Priame harness testovanie.** Codex a Claude Code sa pripájajú priamo na Kataster endpoint. Overiť druhý počítač, OAuth refresh, upload/download, chyby, context benchmark a update/rollback. Pri rozšírení kolegovi doplniť jeho samostatné konto a test izolácie a revokácie.
5. **Automatická aktualizácia z kanonického súkromného zdroja.** Nastaviť pipeline až po úspešnom pilote. Stabilná vetva/release spustí testy, build a vydanie nemenného image; deployment používa jeho digest a zaznamená source SHA. Pri zlyhaní testov alebo health/smoke ostáva predchádzajúca verzia. Migrácie dát musia umožniť bezpečný rollback/restore. Nevystavovať deploy webhook každému neoverenému pushu pred CI.
6. **Gateway neskôr.** Preferovať remote adaptér, ktorý volá už nasadený Kataster backend, aby sa nedržala druhá nezávislá kópia parserov. Vyžaduje delegovanú používateľskú identitu a autorizáciu; nepoužiť jeden spoločný token pre všetkých členov. Gateway a priamy prístup musia mapovať toho istého používateľa na rovnakú identitu iba po dôveryhodnom overení.
7. **LAWOSS distribúcia.** Zo schváleného vydania vyrobiť sanitizovaný local/remote balík s manifestmi, skillom a návodom. Zachovať samostatnú hranicu medzi privátnym zdrojom a verejnými artefaktmi. Python packaging/importer zmeny riešiť v tejto etape.

## Čo sa môže aktualizovať automaticky

- **Remote backend:** úspešné schválené vydanie -> CI image -> Dokploy. Klientom zostáva rovnaká URL.
- **CLI a skilly:** samostatný verzovaný balík. Nový remote image automaticky nevymení lokálny executable ani skill. Použiť explicitný updater/verziovanie pluginu a kontrolu kompatibility.
- **Gateway katalóg:** po úspešnom vydaní overiť schémy. Kompatibilné zmeny môžu prejsť automatizovaným kontraktovým testom; nové tools, rozšírené oprávnenia a zmeny významu musia zostať pod release kontrolou.
- **Upstream braklo:** sledovanie/review zmien samostatne; aktualizácia nášho servera neznamená automatický merge ľubovoľného upstream commitu.

## Schválený doplnok: aktualizácie existujúcich MCP v Gateway

Používateľ schválil standalone-first smerovanie a doplnil aktualizáciu existujúcich MCP v Gateway a automatické nadviazanie na svoje zdrojové repozitáre. Obnova Gateway je samostatný pracovný celok a neblokuje lokálny pilot Katastra.

1. **Zmapovať všetkých 22 služieb.** Pre každú overiť kanonický repozitár, release vetvu/tag, samostatnú Dokploy službu, runtime v Gateway a posledné otestované vydanie. Neprisudzovať každej službe súkromný zdroj bez overenia. Porovnať source SHA, image digest a skutočne bežiacu verziu; samotný GitHub HEAD alebo `autoDeploy=true` nestačia.
2. **Dorovnať verzie.** Najprv aktualizovať a otestovať existujúce pribalené runtime. Prechod na vzdialené backendy robiť následne po službách. Overiť schémy, reprezentatívne čítacie volanie podľa pravidiel služby, autentifikáciu a rollback. Pre Kataster naďalej platí konkrétne zadanie pred živým volaním portálu.
3. **Prepojiť Gateway so samostatnými backendmi, kde je to vhodné.** Preferovaný tok je súkromný zdroj -> úspešné CI -> verzovaný nemenný image -> vlastný Dokploy -> Gateway volá tento backend. Kompatibilná oprava potom nevyžaduje pribalenie druhej kópie kódu do Gateway. HTTP adaptér dnes nie je hotový; treba implementovať aj autorizáciu, delegovanie identity, limity a správanie pri výpadku. Používateľské dáta nesmú zdieľať jednu identitu len preto, že požiadavky idú cez Gateway.
4. **Automatizovať aj zostávajúce pribalené runtime.** Kde samostatný vhodný backend nie je, vydanie v kanonickom repozitári spustí aktualizáciu súkromného manifestu Gateway, kontraktové testy a build Gateway image. Súkromná distribúcia nemá byť povinne závislá od vydania vo verejnom LAWOSS katalógu. Verejný release LAWOSS zostáva samostatnou cestou.
5. **Nasadzovať otestované vydania.** Kompatibilné opravy automaticky; nové tools, širšie oprávnenia a nekompatibilné zmeny cez kontrolu release. Najprv overiť kandidáta, potom prepnúť prevádzku. Pri zlyhaní zachovať alebo obnoviť predchádzajúcu verziu. Migrácie dát potrebujú vlastný overený postup obnovy. Schémy Gateway aktualizovať koordinovane s backendom.
6. **Evidovať a kontrolovať aktuálnosť.** Každé nasadenie zaznamená source SHA, release, image digest a výsledok kontroly. Budúca pipeline má porovnávať požadovanú a nasadenú verziu a hlásiť odchýlku či zlyhanie vrátane zmeškaného triggera. Lokálne CLI/skilly majú vlastné verzie a aktualizačný mechanizmus. Nejde o vytvorenie automatizácie tohto chatu.

[Dokploy podporuje deployment cez webhook alebo API](https://docs.dokploy.com/docs/core/auto-deploy). Trigger naviazať na úspešné CI, aby priamy push hook neobišiel testy. Pri implementácii odstrániť konkurenčné deploy cesty a serializovať nasadenia. Overiť GitHub oprávnenia a prístup k súkromnému registry; tajomstvá patria do CI/Dokploy konfigurácie.

Nie je vytvorený nový repozitár, deploy pipeline ani časovaná automatizácia. Smerovanie je používateľom schválené; táto aktualizácia dokumentu nemení bežiace služby.
