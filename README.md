> SKALLARS fork: [lokálny pilot](docs/local-pilot.md), [remote na Dokploy](docs/remote-pilot.md), [spoločné OAuth prihlásenie](docs/oauth.md). Verzia 0.14.0, upstream autorstvo a MIT licencia zachované.

# Kataster SKALLARS

Distribúcia MCP + CLI odvodená od `braklo/kataster-mcp` (MIT).

## Inštalácia (SKALLARS)

| Kde | Ako |
|---|---|
| Claude Code, Codex | plugin `kataster-skallars` z marketplace `originalmagneto/skallars-marketplace` (remote MCP + skill) |
| aplikácia Claude, Cowork | vlastný konektor `https://mcp-kataster.aittorney.online/mcp` |
| CLI `sk-kataster` (raz na počítač) | `uv tool install git+https://github.com/originalmagneto/kataster-skallars`, potom `sk-kataster --json remote login` |

V Claude Code ho nainštaluješ príkazom `/plugin install kataster-skallars --marketplace originalmagneto/skallars-marketplace`.

Remote MCP má rovnakých 11 nástrojov ako lokálny server. CLI je potrebné na nahratie lokálneho LV súboru
(HTML/PDF) na remote server (`sk-kataster --json remote upload CESTA`); ostatné funguje aj bez neho.
Prihlásenie je spoločný SKALLARS účet na `auth.aittorney.online`.

## Lokálne CLI a import LV

```sh
sk-kataster --json doctor
sk-kataster --json lv import '/cesta/priecinok-s-vypismi'
sk-kataster --json person overview --surname 'Priezvisko' --first-name 'Meno'
```

`doctor` ukáže dnešnú spoločnú kvótu CLI a lokálneho MCP. Prehľad osoby vychádza z vlastných importov. Pri chybe nástroja vráti CLI nenulový návratový kód a JSON s poľami `chyba`, `zdroje` a `varovania`. Dôvod zistíš z `chyba.typ` a `chyba.sprava`.

Pri importe priečinka má každý záznam v `data.lv` vlastné `tarchy`, `uplnost`, `varovania` a `ulozenie`. Prázdna alebo chýbajúca časť C dáva `unknown`. Hodnota `none` vyžaduje výslovné „Bez tiarch.“ a platí pre rozsah dodaného výpisu.

Ak z nového vstupu ubudnú položky, `ulozenie.stav` zostane `preserved_existing` aj pri novšom dátume. Pole `ulozenie.ubudlo` uvedie počty chýbajúcich vlastníckych záznamov, parciel, stavieb, jednotiek a predtým prečítaných častí, pri ktorých nastal úbytok. Prehľad osôb ďalej používa pôvodný výpis. Úbytok sám osebe nepreukazuje zmenu vlastníctva.

Ďalšie príklady obsahuje [návod pre lokálne CLI](docs/local-pilot.md). Nasleduje dokumentácia pôvodného upstreamu. Jej inštalačné URL smerujú na upstream.

# kataster-mcp

MCP server pre kataster nehnuteľností Slovenskej republiky. Umožňuje AI asistentovi alebo jazykovému modelu
v ľubovoľnom klientovi s podporou [Model Context Protocol](https://modelcontextprotocol.io) zistiť o konkrétnom pozemku
čo najviac z verejných zdrojov: hranice a výmeru parcely, list vlastníctva a vlastníkov,
bonitu pôdy, úradnú hodnotu, LPIS, záplavové územia, ochranu prírody, les, sklon terénu, siete a mapu.

*English: an MCP server for the Slovak land registry. An English README is in preparation.*

Údaje majú informatívny charakter. Nie sú výpisom z listu vlastníctva a nedajú sa použiť na právne úkony.

## Čo vie

| Nástroj | Čo vráti |
|---|---|
| `kataster_ku` | katastrálne územie podľa názvu alebo kódu (obec, okres) |
| `kataster_parcela` | parcelu registra C alebo E podľa čísla alebo súradníc: výmera, hranica, referenčný bod |
| `kataster_vlastnici` | vlastníkov a podiely parcely, jej LV a súpisné čísla stavieb. S `detail_stavieb: true` aj samostatný LV stavby, jej druh a vlastníkov. Každý nový detail stavby čerpá dennú kvótu |
| `kataster_vrstvy` | tematické údaje o parcele (zoznam nižšie), pri plošných vrstvách aj podiel na výmere |
| `kataster_skupina` | rozbor viacerých parciel: celková výmera, spoločné hranice, súvislé celky, susedia |
| `kataster_mapa` | mapu parcely ako PNG, HTML (Leaflet), GeoJSON alebo KML, bez osobných údajov |
| `kataster_lv` | odkaz na výpis z listu vlastníctva na portáli ESKN (výpis si otvoríte sami) |
| `kataster_osoba_navod` | postup krok za krokom, ako si v oficiálnom vyhľadávaní portálu ESKN nájsť listy vlastníctva osoby a uložiť ich náhľady (server pri tom na portál nevolá). Uvádza aj názvy a kódy ostatných katastrálnych území tej istej obce |
| `kataster_lv_import` | načítanie výpisu LV alebo náhľadu LV, ktorý ste si uložili (HTML alebo PDF); aj celý priečinok naraz |
| `kataster_osoba_prehlad` | prehľad parciel a podielov jednej osoby zložený z náhľadov LV, ktoré ste si uložili; bez dotazu na portál |
| `kataster_status` | verziu, limity a dnešné využitie kvóty |

Pri historickej mape zadajte nástroju `kataster_mapa` parameter `"cyklus": "2017-2019"` alebo `"cyklus": "2020-2022"`, formát PNG alebo HTML a podklad `orto` alebo `orto+kn`. Bez parametra sa použije súčasný podklad. Hranice parciel a voliteľná vrstva KN sú vždy súčasné. Mapa uvádza zdroj GKÚ Bratislava, NLC a dátum snímkovania pre zobrazenú plochu. Pri viacerých dátumoch ukáže najstarší a najnovší, pri neúplných údajoch „nezistený“. Podrobné výrezy v HTML majú vlastné dátumy. Vzdialený export má spoločný limit 8 MiB pre všetky súbory.

Vrstvy v `kataster_vrstvy`: bonitovaná pôdnoekologická jednotka (BPEJ), úradná hodnota pôdy, LPIS, užívateľ pôdy,
záplavy, chránené územia, nadmorská výška, sklon terénu, zastavané územie obce, zakreslené ťarchy, pozemkové úpravy
v katastrálnom území, les a siete (cesty, železnice, elektrické vedenia).

Každá odpoveď uvádza zdroj, čas a to, či údaj prišiel z lokálnej cache. Neoficiálne rozhrania sú označené.

## Čo zámerne nerobí

- **Sám nehľadá podľa osoby.** Vlastníkov zistí len pre parcelu, ktorú zadáte. Ak chcete parcely konkrétnej osoby, vyhľadáte
  ju sami v oficiálnom vyhľadávaní portálu ESKN („Fyzické osoby“), server vás tým prevedie a uložené náhľady listov
  vlastníctva potom načíta a zloží do prehľadu.
- **Nenahrádza súpis nehnuteľností podľa § 69 ods. 9 zákona č. 162/1995 Z. z.**, ktorý vydáva úrad len samotnej osobe.
  Prehľad zložený z náhľadov je informatívny.
- **Neprechádza celé katastrálne územia** kvôli vlastníkom.
- **Neobchádza CAPTCHA.** Keď portál CAPTCHA vyžiada, alebo keď je denná kvóta vyčerpaná, server vám poradí presný ručný
  postup v prehliadači a uložený výpis či náhľad potom načíta.
- **Nezaťažuje portál.** Medzi dotazmi na kataster.skgeodesy.sk čaká aspoň 3 sekundy a nikdy sa nepýta paralelne.
  Vlastníkov zistí najviac pre 50 parciel denne. Tieto limity sa nedajú vypnúť nastavením.

## Inštalácia

Potrebujete [uv](https://docs.astral.sh/uv/getting-started/installation/) (Linux, macOS aj Windows). Server sa spúšťa
ako lokálny proces cez stdio, takže ho pridáte do každého MCP klienta rovnako: príkaz `uvx` s argumentmi
`--from git+https://github.com/braklo/kataster-mcp kataster-mcp`. Väčšina klientov to zapisuje do JSON konfigurácie
v tomto tvare (presné miesto a názov kľúča nájdete v dokumentácii svojho klienta):

```json
{
  "mcpServers": {
    "kataster": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/braklo/kataster-mcp", "kataster-mcp"]
    }
  }
}
```

Napríklad v Claude Code jedným príkazom:

```bash
claude mcp add kataster -- uvx --from git+https://github.com/braklo/kataster-mcp kataster-mcp
```

Potom sa stačí opýtať, napríklad: *„Čo je za pozemok E 503 v katastrálnom území Vyšný Kubín a kto ho vlastní?“*

## Osobné údaje

Mená, dátumy narodenia a adresy vlastníkov sa ukladajú len lokálne, do súboru `osoby.sqlite` v dátovom adresári
servera, a po 7 dňoch sa pri ďalšom dotaze načítajú znova. Dátový adresár (presnú cestu vypíše `kataster_status`):

| Systém | Adresár | Ochrana |
|---|---|---|
| Linux | `~/.local/share/kataster-mcp` (alebo `$XDG_DATA_HOME/kataster-mcp`) | práva 0700 / 0600 |
| macOS | `~/Library/Application Support/kataster-mcp` | práva 0700 / 0600 |
| Windows | `%LOCALAPPDATA%\kataster-mcp` | prístup len pre používateľa (predvolené nastavenie Windows) |

Server ich neposiela nikam inam než do odpovede vášmu AI asistentovi; ak model beží v cloude, dostane ich aj jeho
poskytovateľ. Za to, ako ich použijete, zodpovedáte vy (GDPR, katastrálny zákon).

## Zdroje dát

Úrad geodézie, kartografie a katastra SR (INSPIRE, ESKN, ZBGIS, výškový model), Výskumný ústav pôdoznalectva a ochrany
pôdy, Národné lesnícke centrum, Ministerstvo pôdohospodárstva a rozvoja vidieka SR, Slovenský vodohospodársky podnik,
Štátna ochrana prírody SR. Podmienky ich použitia platia aj pri použití cez tento server; zdroj uvádzajte.

## Stav

Testy SKALLARS bežia na Linuxe, macOS a Windowse s Pythonom 3.12 a 3.14. História zmien je v [prehľade vydaní](docs/releases.md).

## Chyby a návrhy

[Issues](https://github.com/braklo/kataster-mcp/issues), po slovensky aj po anglicky. Do issue nedávajte mená
vlastníkov ani výpisy z listu vlastníctva.

## Licencia

Kód: [MIT](LICENSE). Licencia kódu sa nevzťahuje na údaje, ktoré server sprostredkúva.
