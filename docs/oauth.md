# Spoločné SKALLARS prihlásenie

Nasadené 12. 10. 2026 na vlastnom Dokploy. Kataster 0.5.0 používa `https://auth.aittorney.online` ako samostatnú OAuth autoritu. MCP URL zostáva `https://mcp-kataster.aittorney.online/mcp`. Používateľské meno alebo e-mail je identifikátor osobného účtu; e-mail nie je povinný. Heslo si každý používateľ nastavuje osobne cez jednorazový odkaz.

## Pripojenie

Na ďalšom počítači bez uloženého pripojenia:

```sh
codex mcp add kataster-skallars-remote --url https://mcp-kataster.aittorney.online/mcp
codex mcp login kataster-skallars-remote --scopes mcp:tools

claude mcp add --transport http --scope user kataster-skallars-remote https://mcp-kataster.aittorney.online/mcp
claude mcp login kataster-skallars-remote
```

Nepridávaj pevnú Authorization hlavičku k OAuth pripojeniu. Pri migrácii ju odstráň iba z tohto servera po zálohe konfigurácie. Pri skúške Codexu spôsobila stará hlavička odmietnutie výmeny OAuth tokenu. Klient potom otvorí spoločný SKALLARS formulár a súhlas s prístupom k službe. Heslo neposielaj do chatu ani do konfigurácie MCP.

Klient uchová OAuth tokeny vo svojom úložisku. Access token má 5 minút, rotovaný refresh token pevný limit 90 dní. Browser session má 30 dní a jej expirácia neruší platný refresh token. Nová aplikácia alebo počítač autorizuje svoje vlastné pripojenie. Správca hesiel môže uložiť používateľské meno a heslo; formuláre podporujú autocomplete a paste.

## Kolegovia a prevádzka

Súkromný zdroj autority: `originalmagneto/skallars-auth`. Jej README obsahuje CLI `invite`, `list`, `disable`, správu jednorazových odkazov a návrh zálohy. Každý kolega musí mať vlastný účet a vlastný tenant. Samotná znalosť MCP URL alebo inštalácia pluginu nedáva prístup k službe. Verejná registrácia OAuth klienta nevytvára používateľský účet.

Dokploy: projekt SKALLARS Auth `XdEgERwJNPBEYIeQWWhkE`, compose `c9xkbD7L-nooXbqJW1PlI`, service auth, port 3000, volume auth-data. Kataster zostáva compose `hR1vGslIGKJEntXc667AS`, port 8000. Oba majú jednu repliku. Pri deployi zachovaj volume aj podpisové/cookie kľúče; readiness a OAuth/MCP spojenie over po dokončení štartu, nie počas krátkeho výpadku proxy. Bootstrap pozvánka bola po aktivácii odstránená z uloženého Dokploy prostredia. AutoDeploy zostáva vypnutý.

Pôvodný osobný bearer zostáva v serverovom pilote pre existujúci `sk-kataster remote` CLI. Codex a Claude Code už používajú OAuth. Tento legacy token má vlastnú expiráciu a nespadá pod odobratie OAuth grantov: pri odobratí jeho držiteľa treba odstrániť aj príslušný hash zo SK_KATASTER_TOKENS. Pred úplným vyradením legacy prístupu doplniť samostatné OAuth prihlasovanie/obnovu do CLI. Nespoliehať sa iba na OAuth disable pri offboardingu existujúceho legacy používateľa.

## Overený rozsah

- Platné verejné HTTPS, health verzie/revision oboch služieb, protected-resource aj authorization-server metadata a 401 challenge.
- Osobné nastavenie hesla a následné odmietnutie použitého aktivačného odkazu.
- Skutočný Codex a Claude Code OAuth callback a uloženie tokenov. Claude Code v novom procese hlásil Connected aj po reštarte autority a obnovení readiness.
- 154 offline testov Katastra a jeho CI v šiestich kombináciách OS/Python; 10 testov autority, audit závislostí bez nálezov a Docker build/CI.
- Safari lokálne overil skutočné prihlásenie, súhlas, PKCE callback a obnovovací token. Živú obrazovku používateľ absolvoval cez prehliadač; neskoršia kontrola produkcie cez Safari MCP bola nedostupná, nástroj vrátil Transport closed.

Samostatné modelové CLI skúšky sa zastavili na existujúcich prihláseniach do OpenAI/Anthropic. Ide o prihlásenie modelového klienta, osobitné od úspešnej MCP OAuth autentifikácie. Živé modelom iniciované kataster_status cez OAuth tak ešte nie je potvrdené; pôvodný bearer status v produkcii prešiel. Prirodzený výber skillu, webové harnesses s ďalšími callbackmi, marketplace/plugin balíky a migrácia ostatných MCP zostávajú samostatnými etapami. Neboli volané živé cadastral/LV rozhrania.

Poznámka pre túto pracovnú stanicu: desktopová konfigurácia agents je nekompatibilná s bundled Codex CLI. Pre jeho mcp login boli použité iba dočasné overrides starých agents kľúčov; globálne agents nastavenie sa nemenilo.

Oficiálne rozhranie Codex MCP: [Developer commands](https://learn.chatgpt.com/docs/developer-commands#codex-mcp). Konkrétne lokálne CLI boli overené aj cez ich aktuálne help.
