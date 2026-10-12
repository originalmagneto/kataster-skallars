# Prehľad zostávajúcich prác, 12. 10. 2026

Živo overené: Kataster 0.5.0 a SKALLARS Auth 0.1.0 odpovedajú cez HTTPS 200. Dokploy oba deploymenty označuje done a autoDeploy je false. Oba pracovné repozitáre boli pred vytvorením tohto prehľadu čisté. Základ funguje, zostáva dokončiť distribúciu, prevádzku a širšie overovanie.

Hotové sú súkromné repozitáre, aktualizované Python MCP SDK, lokálne MCP/CLI, compact výstupy, hlavný skill, samostatný remote Kataster, oddelené používateľské úložiská, upload API, spoločný SKALLARS OAuth a brandované formuláre. Osobný účet možno označiť používateľským menom alebo e-mailom; e-mail nie je povinný. OAuth login Codexu aj Claude Code prešiel, Claude obnovil spojenie aj po reštarte autority. Predchádzajúce testy: 154 Kataster + 10 Auth, úspešné CI a Safari. Tento prehľad testy znova nespúšťal.

| Priorita | Oblasť | Čo zostáva a aký je stav |
|---|---|---|
| P1 | Dokončenie praktického overenia | OAuth callback a MCP spojenie prešli. Konkrétne modelom iniciované volanie nástroja cez nové OAuth nebolo dokončené; posledné pokusy zastavili prihlásenia modelových CLI. Doplniť druhý počítač a konkrétneho kolegu, syntetický upload/import a izoláciu/revokáciu cez OAuth v produkčnom toku. |
| P1 | OAuth pre sk-kataster CLI | CLI je hotový, ale remote používa pôvodný osobný bearer. Implementovať login, bezpečné uloženie, refresh a logout. Potom vyradiť pôvodný bearer. Jeho odobratie je dnes samostatné od OAuth disable. |
| P1 | Private Kataster plugin | Pripraviť inštalovateľný balík MCP + CLI + skill s local/remote voľbou. Overiť čistú inštaláciu, výber profilu a odstránenie duplicít. Zatiaľ ide o priamu MCP registráciu a lokálny skill, nie hotový publikovaný plugin. |
| P1 | CI riadené aktualizácie | Testy sa spúšťajú automaticky. Release, build nemenného image, úspešným CI podmienený Dokploy deploy, smoke kontrola a rollback ešte nie sú zapojené. Osobitne verzovať a aktualizovať plugin/CLI/skilly. |
| P1 | Zálohy a obnova | Je zdokumentované, čo zálohovať. Automatické zálohovanie nových volumes a kľúčov nie je potvrdené a reálna obnova zo zálohy nebola vykonaná. Overiť existujúce Dokploy zálohy a doplniť chýbajúce pokrytie. |
| P2 | Spoločný OAuth pre ostatné MCP | Zatiaľ je pripojený Kataster. Staré MCP stále používajú pôvodné brány. Migrovať jednotlivo a doplniť správu oprávnení k službám: existujúcemu účtu pridávať/odoberať konkrétne služby. Aktuálny admin CLI má invite/list/disable, nie plnú správu týchto väzieb. |
| P2 | Aktualizácia existujúcich MCP v Gateway | Existuje mapovanie 22 služieb, ale nie úplné overenie nasadených verzií. Porovnať kanonický repo, source SHA, image a runtime, dorovnať vydania a nastaviť ich aktualizáciu z privátnych zdrojov. |
| P2 | Kataster v Gateway | Implementovať remote adaptér a dôveryhodné prenášanie používateľskej identity. Kataster ešte nie je pridaný. Spoločný backendový token pre všetkých používateľov nie je vhodná náhrada osobnej identity. |
| P2 | SKALLARS marketplace | Zaradiť otestovaný private Kataster plugin, pripraviť návod pre kolegov a aktualizačnú cestu. Plugin môže používať priamy remote endpoint ešte pred integráciou do Gateway. |
| P2 | LAWOSS marketplace | Pripraviť local aj remote MCP/CLI/skill ponuku. Doterajší audit identifikoval potrebu úprav importéra/validátora pre Python a remote balíky. Overiť aktuálny kontrakt, implementovať zmeny, otestovať inštaláciu a vydať sanitizované artefakty oddelené od privátneho zdroja. |
| P2 | Skill, kontext a kompatibilita | Skill existuje a je pripojený v Codexe/Claude Code. Doplniť test prirodzeného výberu a správneho použitia MCP alebo CLI, reálny kontextový benchmark a ďalšie harnesses. Statický profil textov už existuje. Cloudové klienty potrebujú vlastné callbacky a integračné overenie. |
| P3 | Grafické Kataster UI | Lokálne HTML/PNG mapové exporty existujú. Remote mapové exporty, autorizované sťahovanie a interaktívna mapa ako MCP App ešte nie sú implementované. |

P1 odporúčam dokončiť pred širším sprístupnením kolegom. P2 rieši ekosystém a distribúciu; P3 je ďalšie rozšírenie používateľského rozhrania.

Poradie: dokončiť praktický pilot a OAuth CLI, zabaliť private plugin a overiť kolegu/druhý počítač, nastaviť vydávanie a obnovu, migrovať ostatné OAuth brány, dorovnať Gateway a jeho aktualizácie, dokončiť LAWOSS distribúciu, potom mapové UI.

Voliteľné ďalšie doménové práce z pôvodného návrhu: nemenné verzie LV, explicitné riešenie konfliktov importov, automatická migrácia/reparse cache a porovnávanie LV či príloh zmluvy. Konzervatívna ochrana existujúceho lepšieho importu už funguje; úplná história ešte nie.

Upratať aj dokumentáciu: staršie návrhy a remote-pilot.md obsahujú historické tvrdenia o chýbajúcom OAuth. Aktuálny postup je docs/oauth.md a najnovšia sekcia PROJECT_HANDOFF.md. Pred verejným vydaním zladiť návody ku konečným balíkom.

Najdôležitejšia aktuálna hranica: OAuth deaktivácia používateľa neodoberie jeho samostatný legacy CLI bearer. Do vyradenia tohto prístupu treba pri offboardingu odobrať oba.

Podklady: [aktuálny OAuth návod](oauth.md), [dôkazy nasadenia](research/oauth-deployment-verification-2026-10-12.json), [standalone-first a Gateway plán](architecture/standalone-first-2026-10-12.md). Gateway ani LAWOSS runtime sa pri tomto prehľade znova neauditovali.
