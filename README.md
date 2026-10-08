# Orbit

**České diktování do kteréhokoli okna ve Windows.** Podržíš klávesu, řekneš větu a pustíš: text se objeví tam, kde
máš kurzor, i s diakritikou a interpunkcí. Řeč rozpoznává Whisper large-v3 přímo na tvé grafice (whisper.cpp
s Vulkanem), takže zvuk nikam neodchází.

Když pracuješ s **Claude Code**, Orbit nad plovoucím mikrofonem ukazuje limity a stav relací, přečte ti hotové
odpovědi a hlasový agent ti pošle zadání do relace, až mu řekneš „jo“.

**Poznámky a úkoly:** v sešitu u panelu si vedeš úkoly se složkou, kontextem a průběžnými poznámkami (Aktivní,
V plánu, Poznámky, Hotovo, pořadí přetažením). Aktivní ti Orbit každou půlhodinu nabídne a po kliknutí na bublinu
nebo „jo“ pro ně otevře novou relaci Claude Code v jejich složce, se zadáním, kontextem i poznámkami.

Web: **https://orbit.easya.cz**

## Instalace

- **Instalátor** z https://orbit.easya.cz. Nainstaluje se jen pro tebe, bez práv správce. Při prvním spuštění
  tě provede průvodce: jméno, mikrofon, klávesa, model (stáhne se sám) a připojení Clauda.
- **Jedním příkazem v PowerShellu** (stáhne instalátor, ověří SHA-256 a nainstaluje ho; skript je
  [`web/site/install.ps1`](web/site/install.ps1)):
  ```powershell
  irm https://orbit.easya.cz/install.ps1 | iex
  ```
- **Přes Claude Code:** napiš Claudovi „Nainstaluj mi Orbit z https://orbit.easya.cz. Nejdřív si přečti
  https://orbit.easya.cz/install.ps1, řekni mi, co udělá, a pak ho spusť.“

## Co potřebuje počítač

- Windows 10 (1809+) nebo 11, 64bit.
- Grafiku s Vulkanem (NVIDIA, AMD, Intel). Na large-v3 aspoň 6 GB paměti grafiky, jinak Orbit vezme rychlejší
  turbo. Bez grafiky přepisuje procesor, jen pomalu.
- Místo na model: 3,1 GB (turbo 1,6 GB), stáhne se při prvním spuštění.
- Volitelně Claude Code s vlastním předplatným Claude (limity, relace, předčítání, hlasový agent, spouštění úkolů
  z poznámek) a Google Chrome (otevírání stránek hlasem).

## Soukromí

- Mikrofon je otevřený jen po dobu, kdy držíš klávesu (a v okně nastavení kvůli ukazateli hlasitosti).
- Přepis běží lokálně. Claude dostane jen text, a jen když to zapneš: učení slovníku z diktátů, nebo zpráva,
  kterou hlasovému agentovi potvrdíš.
- Poznámky a úkoly jsou jen v tvém počítači (`tasks.json` v datové složce Orbitu). Nová relace Claude Code dostane
  úkol, až když její spuštění potvrdíš.
- Orbit nikdy nechce heslo ani token od Clauda: přihlašuješ se v Claude Code na stránce Anthropicu.

## Přesnost

Měřeno na 150 nahrávkách z české části datasetu FLEURS (Radeon RX 9070 XT):

| Model | chybná slova | chybné znaky | přepis |
|---|---|---|---|
| large-v3 | 8,9 % | 2,5 % | 1,9 s |
| large-v3-turbo | 10,2 % | 2,9 % | 0,9 s |

## Vývoj

Potřeba Python 3.13.

```powershell
git clone https://github.com/josefkotran/orbit.git
cd orbit
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw.exe Orbit.pyw
```

Model si Orbit stáhne sám. V `whisper/` je `whisper-server.exe` (whisper.cpp 1.9.4 s Vulkanem a variantami pro
procesor). Jak ho přeložit a jak sestavit instalátor, popisuje [`build/README.md`](build/README.md). Rozhodnutí
a jejich důvody (proč co funguje tak, jak funguje) jsou v [`CLAUDE.md`](CLAUDE.md). Web je ve [`web/`](web/README.md),
úvodní video v [`video/`](video/README.md).

## Licence

Orbit je svobodný software pod licencí **GNU GPL 3.0 nebo novější** ([`LICENSE`](LICENSE)). Přibalené a stahované
součásti mají vlastní licence, přehled je v [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

Orbit není produktem společnosti Anthropic. Claude a Claude Code jsou ochranné známky společnosti Anthropic, PBC.
