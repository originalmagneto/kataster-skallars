# OAuth pre sk-kataster CLI

CLI používa rovnaké osobné SKALLARS prihlásenie ako MCP klienti. Prihlasovanie otvorí prehliadač; používateľ zadáva heslo iba na stránke autority. CLI heslo nečíta.

```sh
sk-kataster --json remote login
sk-kataster --json remote status
sk-kataster --json remote tools
sk-kataster --json remote call kataster_status '{}'
sk-kataster --json remote logout
```

Voľby remote patria pred názov akcie:

```sh
sk-kataster --json remote --no-browser login
sk-kataster --json remote --url https://mcp-kataster.aittorney.online --auth-file ~/.config/kataster-skallars/oauth.json status
```

`--no-browser` vypíše prihlasovací odkaz na stderr a čaká najviac päť minút na callback. Odkaz otvor manuálne na tom istom počítači. Všetky odpovede na stdout zachovávajú JSON envelope `data`, `zdroje`, `varovania`. Status nezobrazuje žiadny token ani client ID; oznamuje iba lokálny stav, expiráciu a možnosť obnovy. Neoveruje účet na serveri. Doctor kontroluje verejný health bez prihlasovania.

Predvolený súbor je `~/.config/kataster-skallars/oauth.json`. Obsahuje osobné poverenia, preto ho nezdieľaj ani nepridávaj do Git. Linux/macOS používajú adresár 0700, súbor a zámok 0600; zápis je atomický. Windows používa zámok `msvcrt` a atomické nahradenie súboru, prístupové práva závisia od ACL používateľského profilu. Vlastný `--auth-file` musí byť v samostatnom súkromnom adresári, nie priamo v domovskom priečinku. Súbor `.lock` zostáva po odhlásení zámerne: jeho odstránenie by umožnilo súbežným procesom zamknúť odlišné objekty.

Token je viazaný na presnú resource URL zakončenú `/mcp` a issuer získaný z HTTPS discovery. Discovery a HTTP token požiadavky nesledujú redirecty, endpoints musia patriť origin autority. Pri zmene autority alebo resource sa uložené poverenia nepoužijú. Výnimkou z HTTPS je iba explicitné `http://127.0.0.1` resource pre lokálne testovanie. HTTPS resource nesmie objaviť HTTP loopback autoritu ani endpoint. CLI používa native DCR klienta, PKCE S256 zo SDK 2.3.0, náhodný state a callback na `127.0.0.1` s náhodným portom. Požaduje scope `mcp:tools`.

Obnova aj zápis rotovaného refresh tokenu prebiehajú pod jedným medziprocesovým zámkom. Pri access tokene s menej než 30 sekundami zostávajúcej platnosti sa token obnoví. Pri `invalid_grant` CLI vymaže neplatné lokálne poverenia a vyžiada nové login; žiadna odpoveď autority ani credential sa nedostane do chybového výstupu. Logout sa pokúsi odobrať refresh aj access token na revocation endpoint a vždy vymaže lokálny súbor. `revoked: false` znamená, že serverové odobratie sa nepotvrdilo, napríklad autorita bola nedostupná. Lokálny logout neodoberá legacy bearer token.

## Migrácia legacy prístupu

Explicitný `SK_KATASTER_TOKEN` má prednosť, potom explicitný `--token-file`. Bez nich CLI použije OAuth. Predvolený historický `remote.token` sa automaticky nečíta a nemôže prebíjať OAuth.

```sh
sk-kataster --json remote --token-file ~/.config/kataster-skallars/remote.token tools
```

Po migrácii odstráň `SK_KATASTER_TOKEN` z prostredia. Legacy token odober na serveri samostatne podľa prevádzkového návodu; OAuth logout ho neruší. Automatický prechod po 401 na iný spôsob prihlásenia sa nevykonáva.

## Overenie

`uv run pytest tests/test_cli_auth.py tests/test_remote_cli.py` používa syntetické discovery, DCR, PKCE callback, obnovu a revokáciu, vrátane odmietnutia nesúladov a súbežného refreshu. CLI subprocess test beží aj mimo checkoutu. Živé OAuth login, registrácia klienta ani dotazy na portál sa pri implementácii nespúšťajú. Táto zmena je backend/CLI, Safari kontrola nie je relevantná.
