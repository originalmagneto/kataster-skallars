# Návrh remote verzie pre Dokploy

Pracovný návrh, 12. 10. 2026. Toto nie je hotová implementácia ani deployment konfigurácia. Základ je fork upstreamu 0.2.0; stdio má zostať funkčné. Najprv odstrániť chyby významu LV, potom pridať vzdialený kontrakt a izoláciu dát.

Rozšírenie po lokálnej previerke 12. 10. 2026: [CLI, SKALLARS gateway, aktuálne SDK a LAWOSS distribúcia](distribution-and-remote-proposal-2026-10-12.md). Nový návrh overuje Python SDK 2.3.0, existujúcu gateway a konkrétne obmedzenia Python/remote balíkov v LAWOSS. Pri ďalšom rozhodovaní použiť tento rozšírený návrh; pôvodný text nižšie zachytáva východiskový stav.

## Architektúra prvého pilotu

Claude/Codex → HTTPS proxy v Dokploy → autentifikovaný Streamable HTTP `/mcp` → existujúce doménové nástroje → cache a ohraničená backend fronta. Upload/download API používa tú istú identitu; parser/fetch worker nevystavuje filesystem klientovi. Prvý pilot: jedna replika, jeden upstream fetch worker a explicitne oddelené verejné a tenantové dáta.

1. **Správnosť LV:** stavy úplnosti A/B/C, známy rozsah úplného/čiastočného dokumentu, `tarchy=unknown/none/present`, validované IČO, dátum údajov, zdroj/hash/parser verzia a transakčné poradie verzií. Neúplné LV nemôže poskytovať definitívne negatívne závery. Porovnania majú vracať štruktúrované dôkazy aj neistoty.
2. **Bezpečný upload:** autentifikované upload API vydá náhodné opaque `file_id`; väzba na tenant, hash, typ, veľkosť, expiry a stav parsovania. Remote `kataster_lv_import(file_id=...)` alebo samostatný remote tool odmietne `path`, `paths` aj ľubovoľné serverové priečinky. Inline HTML podlieha rovnakým limitom alebo sa v remote kontrakte vypne. Exporty vracajú oprávnenému klientovi identifikátor alebo krátkodobý autorizovaný download, nie `out_dir` a lokálnu cestu.
3. **Transport:** explicitná voľba stdio/Streamable HTTP nad tou istou doménovou vrstvou. Datadir, lifecycle a cleanup nesmú byť implicitne globálne pre všetkých klientov. Zvonku server nesmie odhaľovať interný `data_dir`, snapshot paths alebo cudzie cache štatistiky. Health endpoint má byť bez osobných údajov.
4. **OAuth a tenant:** existujúci identity provider, authorization code + PKCE, protected resource/authorization server metadata, overenie issuer/audience/resource/scopes/expiry. Identitu odvodzovať zo serverom validovaného `(issuer, subject)`; neprijímať autoritatívny `tenant_id` od tool klienta. Autorizácia každého file, LV, jobu a exportu sa kontroluje aj po MCP inicializácii. Nezamieňať MCP session ID s prihlásenou identitou.
5. **Docker a volumes:** image z pinovaného locku, explicitná podporovaná verzia Pythonu, non-root, read-only aplikačný filesystem, osobitné zapisovateľné temp a persistentné data volumes. Secrets cez Dokploy secret konfiguráciu mimo Git. Proxy TLS a timeouty/limity uploadu zosúladiť s app; preveriť podporu dlhších HTTP odpovedí a buffering podľa zvoleného SDK/protokolu. Zdrojový kód nemontovať ako zapisovateľný volume.

## OAuth kompatibilita je samostatná overovacia etapa

Oficiálna dokumentácia k 12. 10. 2026 opisuje HTTP remote MCP a OAuth pre Claude a Codex. [Claude Code](https://code.claude.com/docs/en/mcp) a [Claude remote OAuth](https://claude.com/docs/connectors/building/authentication) treba overiť oddelene pre Code a cloudový klient, vrátane callbackov a registrácie klientov. [Codex MCP](https://developers.openai.com/codex/mcp) opisuje OAuth registráciu a login pre Streamable HTTP. Žiadna registrácia ani login neboli vykonané.

[MCP autorizácia 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) uvádza protected resource metadata, resource audience, PKCE a registráciu vrátane CIMD; DCR ponecháva pre spätnú kompatibilitu. [Transporty](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports) rozlišujú stdio a Streamable HTTP. Upstream je však pinovaný na SDK 1.x. Netvrdíme, že jeho SDK implementuje celú najnovšiu revíziu: pred prototypom treba zistiť podporovanú protokolovú revíziu a auth API konkrétneho SDK, zvoliť kompatibilný pin a až potom navrhnúť upgrade. Zmeny protokolu sa nemajú robiť naslepo spolu s opravou LV.

Pilot má overiť: discovery/401 challenge, PKCE, callbacky skutočných klientov, issuer/resource/audience, refresh/expiráciu/revokáciu, chybné scopes a odmietnutie krížového tenantového prístupu. CIMD alebo DCR zvoliť podľa klientov a poskytovateľa; OAuth podporu nemožno považovať za hotovú samotným spustením HTTP transportu.

Upload z prílohy v Claude/Codex nie je automatickou vlastnosťou MCP: `file_id` musí vydať náš backend po skutočnom prenose súboru. Pred UX implementáciou rozhodnúť medzi malým upload web formulárom, podporovaným MCP upload nástrojom alebo inou klientsky overenou cestou. Cudzí client file ID bez potvrdeného konektora nedáva serveru prístup k prílohe.

## Cache, deduplikácia a retencia

- Verejná cache geometrie podľa `(provider, parser_version, ku, register, parcel)` môže byť spoločná. Pri zmene parsovania kontrolovať invalidáciu a možnosť reparse.
- LV/uploads/snapshots/exports/job výsledky majú tenantové namespace alebo samostatné úložisko. Hash deduplikácia osobných dokumentov prebieha v rámci tenanta; iný používateľ nesmie cez hash zistiť existenciu cudzieho LV.
- Idempotentný job podľa `(tenant, operation, normalized_input, document_hashes, parser_version)`, `single-flight` pre súbežné identické požiadavky a krátky výsledok s provenance. Výsledok hotovej operácie sa opakovane neprepočítava LLM volaním.
- Backend vykoná dávku a čakajúce dotazy zlúči; `job_id`/stav je na obnovu prerušenej práce, nie na neustále LLM polling. Krátke úlohy možno dokončiť v jednom tool call, dlhšie uložiť s ohraničeným status retrieval alebo notifikáciou podľa skutočne podporovaného MCP klienta. Opakované budúce sledovanie nebolo používateľom objednané.
- Limity poskytovateľa a jeho blokácia musia byť spoločné pre celú službu. OAuth užívatelia a repliky nesmú každý obnoviť vlastnú kvótu 50 dotazov a tým znásobiť tlak na portál.
- Periodický purge nezávislý od requestov, limit diskového priestoru, explicitná retencia vstupov a výsledkov, postup mazania a záloh. Pre osobné dáta začať najviac upstream siedmimi dňami a pred prevádzkou upresniť požadovanú politiku; automaticky nepredlžovať retenciu každým čítaním.
- SQLite môže postačiť jednej replike pri explicitných transakciách a ohraničenej súbežnosti. Viac replík potrebuje vhodné spoločné úložisko/frontu a koordináciu; neurčujeme PostgreSQL/Redis ako povinné ešte pred meraním. SQLite súbory nezdieľať ľubovoľne cez sieťový volume.

## Ďalšie doménové funkcie

| Funkcia | Backend práca a výsledok | Podmienka |
|---|---|---|
| Balíková previerka parciel | Normalizovaný zoznam, dedup, cache-first plán, jednotlivé nálezy a chyby, krátky celkový súhrn | Zachovať celkovú kvótu, coverage a dátum každého zdroja; `kataster_skupina` už robí geometriu skupiny, rozšíriť bez duplicity |
| LV vs. príloha zmluvy | Porovnať normalizované k.ú./register/číslo parcely, výmeru a podiely; vrátiť chýbajúce/nadbytočné/nezhodné záznamy a dôkazy | Obe prílohy autorizovane nahrané; neisté čítanie zmluvy nesmie byť tichá zhoda; porovnanie nie je automatický právny záver |
| Dva LV | Nemenné dokumenty, zmeny parciel, vlastníkov/podielov, časti C/plômb a dátumov s referenciou na oba zdroje | Porovnávať zhodný scope; chýbajúca časť je unknown, nie vymazaná ťarcha; rešpektovať parser drift |

## Poradie malých change setov

1. Regresné syntetické fixtures pre chýbajúcu/prázdnu C, poškodenú tabuľku, nečíselné IČO, starší import po novšom a čiastočný po úplnom; opraviť doménový model a import bez zmeny transportu.
2. Tenantový storage kontrakt a bezpečný `file_id`; body/batch limity, parser worker, retencia a offline testy cross-tenant access, expirácie, symlinkov a idempotencie.
3. Lokálny HTTP/OAuth prototyp so zachovaným stdio a explicitným SDK/protocol pinom; integračné overenie Claude aj Codex. Vyžaduje nový pokyn pre granty/registrácie.
4. Docker build a súkromný Dokploy staging s volumes a restore testom až po odsúhlasení konkrétnej konfigurácie; žiadny production deploy v tejto fáze.
5. Balíková previerka a oba typy porovnania nad tou istou cache/job/provenance vrstvou.

Otvorené rozhodnutia pre ďalšie zadanie: používateľský rozsah (súkromný Marián vs. viac účtov), OAuth provider a doména, konkrétne Claude/Codex klienty, klientsky upload, limity anonymizovaných vzoriek, retencia/zálohy a podmienky prístupu poskytovateľov. Žiadne z nich nebránilo dokončeniu inicializácie.
