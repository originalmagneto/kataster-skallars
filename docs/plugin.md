# Kataster SKALLARS plugin

Privátny plugin `kataster-skallars` je balík existujúceho skillu a priameho
OAuth MCP pripojenia `https://mcp-kataster.aittorney.online/mcp`.
Portál, osobné úložiská a CAPTCHA majú rovnaké hranice ako pri priamom MCP.
CLI nie je automaticky nainštalované pluginom; skill použije dostupné CLI
alebo zabalené MCP. Lokálna a remote cache zostávajú oddelené.

Kanonický zdroj pluginu je tento súkromný repozitár. SKALLARS marketplace
odkazuje na jeho `main`; nekopíruje skill. `plugin.json`, `.codex-plugin`
a `.claude-plugin` majú spoločnú verziu pluginu, nezávislú od Python balíka.
Pri zmene skillu alebo manifestu zvýš všetky tri verzie. Pred pushom musí
prejsť offline pytest a validácia Claude pluginu. Zmena MCP backendu
vyžaduje vlastné nasadenie; vydanie pluginu samo server nenasadzuje.

```sh
claude plugin marketplace add originalmagneto/skallars-marketplace
claude plugin install kataster-skallars@skallars

codex plugin marketplace add originalmagneto/skallars-marketplace
codex plugin add kataster-skallars@skallars
```

Používateľ potrebuje Git prístup k obom súkromným repozitárom a vlastný
SKALLARS OAuth účet. Poverenia sa do balíka nevkladajú. Existujúce priame
MCP pripojenie odstráň až po overení pluginového pripojenia; lokálne stdio
môže zostať pre lokálnu cache. Pri súbehu registrácií volaj vždy iba jednu.

Legal plugin poskytuje smerovací skill `kataster`, ktorý načíta tento
aktuálny skill. Nevytvára druhé Kataster MCP pripojenie. Automatické
aktualizácie klientov rieši `scripts/update_plugins.py` v SKALLARS marketplace;
na Mariánovom Macu ho spúšťa denný používateľský LaunchAgent. Zmeny balíkov
sa načítajú v novej relácii klienta. CAPTCHA vždy dokončuje používateľ.
