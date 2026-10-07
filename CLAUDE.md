# Orbit – kontext projektu

Orbit je malý pomocník pro Windows, který běží v oznamovací oblasti a jako plovoucí tlačítko nad všemi okny:

1. **Diktování česky push-to-talk** do libovolného okna. Rozpoznávání běží lokálně na grafice (whisper.cpp s Vulkanem
   a model Whisper large-v3), zvuk nikam neodchází.
2. **Přehled limitů Clauda** v panelu nad mikrofonem: 5hodinové okno a týdenní limit (s OAuth zdrojem, který má
   Pepa, i týdenní limit Fable), přehled relací Claude Code a hlasový agent.

Projekt vznikl 24. 9. 2026 v jedné relaci Claude Code (spuštěné ve složce `C:\Users\josef\pepa`, což je nesouvisející
projekt s TWLanem). Původní název byl „Diktování“ a složka `C:\Users\josef\diktovani`, pak se přejmenoval na Orbit.

## Uživatel a prostředí

- Josef (Pepa) Kotran. Komunikuje **česky**, celé UI aplikace je česky. Často diktuje přímo přes Orbit, takže
  zprávy můžou obsahovat chyby z přepisu.
- Windows 11 Pro, Ryzen 7 5800X, 32 GB RAM, **AMD Radeon RX 9070 XT (16 GB, bez CUDA)**, Python 3.13 (`C:\Python313`).
- Mikrofon: USB **HyperX SoloCast** (`Mikrofon (HyperX SoloCast)`), dřív headset HyperX 7.1 (v MME
  `Headset Microphone (HyperX 7.1 `, zkrácené na 31 znaků), na něm se ladily prahy ticha a pauz.
- Předplatné Claude Max 20x. Claude Code je nainstalovaný přes npm (`%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe`).
- V uživatelských proměnných Windows je `ANTHROPIC_API_KEY` **bez kreditu** („Credit balance is too low“). `claude -p`
  ho upřednostní před předplatným, proto ho Orbit při spouštění Clauda z prostředí odebírá.
- GitHub účet `josefkotran`. `gh` CLI **není** nainstalované, git má přihlášení v Git Credential Manageru.
- Pracuje ve firmách HHW Hommel Hercules (nářadí) a M-tex (bytový textil), proto se ve slovníku hodí jejich názvy.

## Jeho aktuální nastavení (`config.json`, není v gitu)

Push-to-talk je **boční tlačítko myši vpřed** (`{"kind": "mouse", "code": 6}`), model `ggml-large-v3.bin`, mikrofon HyperX,
vkládání **psaním znaků** (`insert_mode: "type"`), bez mezery za textem, povely zapnuté, pípání zapnuté, panel Clauda
zapnutý, **ukládání nahrávek zapnuté** (`recordings/`), spouštění s Windows zapnuté, hlas Jirka (Piper), agent zapnutý.
Průběžný přepis, učení slovníku a předčítání artefaktů má zapnuté (výslovně v configu; noví uživatelé mají učení,
artefakty a agenta vypnuté). Slovník a opravy (`vocabulary`, `replacements`) doplňuje Claude, `learned_until`
je čas posledního přepisu z logu, který už Claude viděl. `name` (jméno pro agenta) a `about` („O mně“ pro učení
slovníku) přibyly 3. 10. a v jeho configu zatím nejsou, tedy prázdné: agent mu do té doby říká „uživatel“.
Souhlasy `claude_hooks` / `claude_statusline` a `wizard_pending` (taky od 3. 10.) v jeho configu nebyly: první start
nové verze dá `claude_hooks` = true, protože jeho hooky v `~/.claude/settings.json` už jsou
(`claude_settings.hooks_installed`), `claude_statusline` = false (stavový řádek nemá), `usage_source` = `"oauth"`
(limity dál z OAuth endpointu, i s řádkem Fable) a průvodce se mu neukáže (config.json existuje).

## Struktura

| Soubor | Co dělá |
|---|---|
| `Orbit.pyw` | vstupní bod (u Pepy přes `.venv\Scripts\pythonw.exe`, po instalaci `runtime\pythonw.exe`, bez konzole); když start spadne, okno s chybou + `crash.log`; `Orbit.pyw --cleanup` = úklid pro odinstalátor (`app/cleanup.py`) |
| `app/version.py` | `VERSION = "1.0.0"`: v patičce nastavení, v logu při startu a v názvu instalátoru |
| `app/paths.py` | kde co je: složka aplikace, datová složka, složka Claude Code (jen stdlib, importuje ho i `cc_hook.py`) |
| `app/vocab.py` | slovník a opravy: čištění, slučování se stropem 300 znaků, export a import souboru |
| `app/main.py` | třída `Dictation`: řídí stavy, Qt signály (`Bridge`) mezi vlákny, tray, menu, nastavení, polling limitů; logování a zachytávání chyb (`_setup_logging`) |
| `app/whisper_server.py` | spouští `whisper-server.exe` jako podproces (grafika, nebo jen procesor), hlídá ho a po pádu spustí znovu, přepis přes HTTP, filtry halucinací, slovník, povely |
| `app/recorder.py` | nahrávání přes sounddevice (MME, 16 kHz mono int16), detekce „zvuk opravdu teče“, prahy podle šumu mikrofonu, režim měřáku |
| `app/hotkey.py` | globální push-to-talk přes pynput low-level hooky, zachytávání nové klávesy, ztracené puštění klávesy, české názvy kláves |
| `app/inserter.py` | vložení textu: schránka + Ctrl+V (se zálohou schránky), nebo psaní přes `SendInput` Unicode; okno v popředí, okna správce |
| `app/ui.py` | `FloatingButton` (mikrofon + panel limitů), `Bubble` (oznámení), `SettingsDialog` (nastavení), kreslení ikony; společné kusy nastavení a průvodce: `KeyAndMic`, `ClaudeBox`, `DownloadRow`, `scrolling` |
| `app/onboarding.py` | průvodce prvním spuštěním (`Wizard`, 6 stránek) a dva pomocníci, které používá i nastavení: `ClaudeConnection` (stav, instalace, přihlášení) a `Downloads` (stahování na pozadí) |
| `app/claude_setup.py` | Claude Code na tomhle PC (jen stdlib): kde je `claude.exe`, verze, `claude auth status --json`, oficiální instalátor a `claude auth login` ve viditelném okně |
| `app/downloads.py` | stahování modelů a hlasů z Hugging Face (navazování, kontrola SHA-256, volné místo) a doporučení modelu podle grafiky (DXGI, Vulkan) |
| `app/theme.py` | vzhled „noční signál“: barvy a tři barevné motivy, QSS, `Toggle` přepínač, `LevelWave` živá vlna, tmavý titulek přes DWM |
| `app/claude_usage.py` | limity Clauda: ze souborů stavového řádku (výchozí), nebo z interního OAuth endpointu (jen `usage_source: "oauth"`); české texty pro odpočty |
| `app/claude_settings.py` | Orbitovy záznamy v `settings.json` Claude Code: hooky a stavový řádek, jen té své instalace (podle cesty ke skriptu), atomický zápis, záloha |
| `app/cc_status.py` | stavový řádek Claude Code (jen stdlib, rychlý): zapíše limity a kontext relace do `<data>/sessions/status/<id>.json`, ukáže původní stavový řádek uživatele (nebo vlastní řádek) |
| `app/cleanup.py` | `Orbit.pyw --cleanup`: odebere hooky, stavový řádek (vrátí původní) a položku v Run této instalace, vždy skončí 0 |
| `app/claude_cli.py` | společné volání `claude -p` (bez nástrojů, na předplatném) pro učení slovníku a souhrny artefaktů; `claude.exe` a prostředí bere z `claude_setup` |
| `app/learning.py` | učení slovníku: přepisy z logu → `claude -p` → nová slova a opravy |
| `app/artifacts.py` | předčítání artefaktů: záznam od hooku → text stránky → souhrn 7 vět od Clauda |
| `app/sessions.py` | přehled relací Claude Code: stav z hook souborů, kontext ze stavového řádku (jinak odhad z přepisu), režim oprávnění, přepnutí okna |
| `app/cc_hook.py` | hook, který Claude Code spouští (jen stdlib, rychlý): zapíše `<data>/sessions/<id>.<událost>.json` (i `permission_mode` a okno relace) |
| `app/agent.py` | hlasový agent: trvalý `claude -p` (stream-json), přehled relací pro něj, potvrzování odeslání |
| `app/agent_tools.py` | vlastní nástroje agenta jako MCP server (stdio): nová relace, hledání a otevření stránky |
| `app/browser.py` | hledání v historii Google Chromu a otevření stránky v nové kartě (s přenesením do popředí) |
| `sessions/` | stavové soubory relací od hooku, v `sessions/artifacts/` zveřejněné artefakty, v `sessions/status/` soubory stavového řádku – nejsou v gitu |
| `cache/` | vygenerované zvuky (`*.wav`) a šipka seznamů (`chevron.png`), dají se kdykoli smazat – není v gitu |
| `app/config.py` | výchozí nastavení, cesty v datové složce, kontrola hodnot při načtení, atomické ukládání, popisky modelů |
| `app/winutil.py` | jedna instance (mutex), AppUserModelID, spouštění s Windows (registry), pípání a zvuky bublin |
| `whisper/` | `whisper-server.exe` a co potřebuje: starý build je jeden exe s Vulkanem (59 MB) + `libwinpthread-1.dll`, nový (`whisper-next/`, `GGML_BACKEND_DL`) má vedle exe `ggml-*.dll` (Vulkan a varianty CPU); Orbit umí obojí. Licence whisper.cpp |
| `app/voice.py` | lokální české hlasy Piper (Jirka, Kasandra) pro předčítání místo Jakuba; Piper běží ve vlastním procesu (`_worker`) |
| `models/` | `ggml-large-v3.bin` (3,1 GB), `ggml-large-v3-turbo.bin` (1,6 GB), `piper/` (hlasy Piperu) – nejsou v gitu ani v instalátoru, stahují se (`downloads.py`); rozestažené jako `*.part` |
| `recordings/` | posledních 30 nahrávek (`.wav` + `.txt` s přepisem), když je zapnuté ukládání – nejsou v gitu |
| `orbit.log` | log aplikace včetně přepisů (jen se zapnutým učením slovníku) a časů – první místo, kam se dívat; řeč agenta, předčítání a adresy jen jako délky (`ORBIT_DEBUG=1` i s texty); vedle něj `whisper-server.log` a `crash.log` (pád v nativním kódu) |
| `whisper-next/` | whisper-server pro jakékoli PC (`GGML_BACKEND_DL`, 76 MB), z něj se dělá `whisper\` v instalátoru; Pepův běžící Orbit pořád používá starý `whisper\` |
| `build/` | `build_whisper.py` (whisper-server přes portable MSYS2), `build_installer.py` (balíček + Inno Setup), `verify_bundle.py` (kontrola balíčku jeho vlastním Pythonem), `README.md`; `cache/`, `tools/`, `dist/`, `output/` nejsou v gitu |
| `installer/` | `orbit.iss` (Inno Setup) a texty licencí GPL/LGPL, které jdou do instalace |
| `tests/` | testy (stdlib `unittest`, od 7. 10.): `test_core_*` (přepis, Piper, klávesa, vkládání, config), `test_claude_*` (nástroje agenta, hledání programů), `test_dist_*` (build, instalátor); viz Spuštění |
| `THIRD_PARTY_NOTICES.md` | licence všeho, co instalátor nese nebo Orbit stahuje |
| `web/` | stránka https://orbit.easya.cz se stažením instalátoru, `publish.py` ji sestaví a nahraje (viz `web/README.md`) |
| `video/` | úvodní video webu v Remotionu, hotové soubory jdou do `web/site/assets/video` (viz `video/README.md`) |

Závislosti: PySide6, sounddevice, numpy, pynput, requests, piper-tts s onnxruntime (`requirements.txt`; Piper je
volitelný, Orbit bez něj jen nenabízí hlasy Piperu). Venv je `.venv` (vznikl ještě ve staré
složce `diktovani`, řádek `command` v `pyvenv.cfg` je proto zastaralý, ale nevadí to).

## Klíčová rozhodnutí a proč

### Rozpoznávání řeči
- **whisper.cpp s Vulkanem**, protože Radeon nemá CUDA (faster-whisper by jel jen na CPU). Oficiální Windows buildy
  whisper.cpp v1.9.4 Vulkan nemají, proto je zkompilovaný přes portable MSYS2 (UCRT64), bez instalace do systému:
  ```
  pacman -S mingw-w64-ucrt-x86_64-{gcc,cmake,ninja,vulkan-devel,shaderc}
  cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_EXE_LINKER_FLAGS='-static-libgcc -static-libstdc++'
  cmake --build build --target whisper-server
  ```
  Vedle exe musí být `libwinpthread-1.dll` z `ucrt64/bin`. Nástroje (např. `whisper-quantize`) je nutné spouštět
  z MSYS2 shellu, jinak nenajdou DLL. Tenhle build má `vulkan-1.dll` jako statický import a instrukce Pepova
  procesoru (`GGML_NATIVE`): na PC bez Vulkanu nebo se starším procesorem by nenaběhl. Pro rozdávání je nový build
  s `GGML_BACKEND_DL` (`whisper-next/`: `ggml-vulkan.dll` se bez Vulkanu přeskočí, `ggml-cpu-*.dll` vybere variantu
  podle procesoru). `whisper_server.py` funguje s oběma, nic nečeká, že je exe samostatné.
- Server běží jako podproces na volném portu, čeká se na `GET /health`. Proces je přiřazený do **Job objectu
  s KILL_ON_JOB_CLOSE**, takže zemře i při pádu aplikace a neblokuje VRAM.
- **Tajná předpona cest** (`--request-path /<náhodný token>`): bez ní `/health`, `/load` i `/inference` vrací 404.
  Server posílá `Access-Control-Allow-Origin: *` a `POST /load` s nesmyslným souborem ho shodí, takže jinak by ho
  libovolná webová stránka uměla vypnout nebo mu podstrčit jiný model. Funguje se starým i novým buildem (ověřeno).
- **Port jen vlastnímu serveru** (od 7. 10.): zvuk, ani `/health` s tajnou předponou, jde jen na port, kde poslouchá
  PID Orbitova whisper-serveru (`whisper_server._listeners`, `GetExtendedTcpTable` pro IPv4 i IPv6, ~0,1 ms). Proč:
  port je volný jen do načtení modelu a Windows porty přiděluje popořadě, jiný program (i jiného uživatele PC) by ho
  mohl obsadit, dostat diktát a vrátit text i s „Odešli.“ (ověřeno podvrženým serverem). Při cizím posluchači start
  zkusí jiný port, `transcribe` server zabije a hlídač ho spustí jinde. `clean_text` maže řídicí znaky (Esc…).
  Když Windows tabulku nedá, rozhoduje jako dřív `/health`.
- Připravenost serveru se kontroluje po 50 ms (prvních 5 s, pak po 0,2 s) a HTTP jde až na port, který už poslouchá:
  připojení na port bez posluchače trvá ve Windows 0,5–1 s. Hotový server Orbit dřív poznal průměrně 354 ms po
  spuštění, teď za 41 ms (náhradní server, n = 15).
- **Cesta k modelu** (`_model_arg`): whisper-server dostává argumenty v ANSI kódové stránce, složka s azbukou (nebo
  „Jiří“ na západních Windows) se změní na „?“ a model se neotevře (ověřeno). Pak dostane cestu relativní ke
  `whisper\`, jinak 8.3. `cwd` zůstává `whisper\` schválně: ggml tam hledá i `ggml-*.dll`.
- **Grafika, nebo procesor** (`WhisperServer.backend`/`device`): podle výpisu serveru při startu
  (`whisper_backend_init_gpu: using Vulkan0 backend` + `ggml_vulkan: 0 = <karta>`, nebo `no GPU found`,
  `whisper_server.parse_backend`). Bez grafiky s Vulkanem (`downloads.gpus`/`vulkan`) dostane server `-t <fyzická
  jádra>` (výchozí 4 vlákna: 10 s řeči na turbu 13 s, s 8 jádry 8 s; beam 1 místo 5 na procesoru skoro nic
  neušetří, proto zůstává 5). Když start s grafikou spadne, zkusí se znovu s `-ng`; když server hlásí procesor,
  ačkoli grafika je, startuje znovu se všemi jádry. Na procesoru UI jednou za běh řekne „Přepis běží na procesoru…
  doporučuju model turbo“ (ne když je to čekané: turbo a žádná použitelná grafika, `Dictation._tell_cpu`).
- **`-t 1` na grafice** (od 7. 10.): whisper.cpp při každém tokenu (beam 5) zakládá a ukončuje vlákna, při vytíženém
  procesoru (build, render, agenti) to přepis brzdilo. Párové A/B na large-v3 s PC na 100 %: 1 vlákno = 0,68× času
  4 vláken (25,5 s řeči 17,9 → 10,2 s), text stejný (0/277 slov rozdílných); na klidném PC je asi o 4 % pomalejší.
  Na procesoru dál všechna fyzická jádra.
- Server se spouští s `SetErrorMode` (bez systémových oken, dítě ho dědí): chybějící DLL nebo pád ho ukončí potichu
  místo okna Windows, které by ho drželo naživu. Kód ukončení se přeloží do češtiny (`exit_text`: 0xC0000135
  chybí DLL, 0xC000001D procesor nezná instrukce…), do logu jde i konec `whisper-server.log`.
- **Pád za běhu** (reset ovladače grafiky, aktualizace ovladače, došla paměť): hlídací vlákno (`WhisperServer._watch`)
  to pozná, server spustí znovu po 1, 5, 20 a 60 s a UI pošle `restarting`/`restarted` (bublina jen jednou za běh,
  tlačítko ukazuje načítání). Rozpracovaný přepis počká a pošle se znovu (`transcribe` po `ConnectionError`
  zkontroluje, jestli proces skončil). Čtvrtý pád za 10 min = `failed`, stav `error`; další stisk klávesy zkusí
  server spustit znovu (dřív radil restartovat aplikaci). Timeout požadavku roste s délkou zvuku (min. 120 s, na
  grafice 30 + 4×s, na procesoru 60 + 20×s); po timeoutu se server zabije (pracoval by dál a zdržel další přepisy)
  a hlídač ho spustí znovu. Ověřeno zabitím procesu mezi požadavky i uprostřed požadavku: text přišel.
  Pokusy po 1, 5 a 20 s jsou jen s grafikou (server, který naběhne na procesoru, se zastaví), na procesor smí až
  poslední po 60 s: po resetu nebo aktualizaci ovladače by jinak large-v3 zůstal do restartu Orbitu na procesoru.
  Když grafika opravdu zmizí, přepne se na procesor až po ~86 s, diktát mezitím počká. Každá chyba obnovy (i OSError
  1455, málo paměti) skončí `failed`: dřív umřelo hlídací vlákno a diktát čekal 300 s.
- Když přepis přesto selže, nahrávka se neztratí: bublina „Přepis selhal… Klikni sem a zkusím ho znovu“ a v menu
  „Přepsat znovu poslední diktát“ (zvuk jen v paměti, přepíše se jako jeden kus; z menu jde text do schránky).
- Parametry `/inference`: `language=cs`, `beam_size=5`, `temperature=0`, `no_timestamps=false`, `prompt` = česká věta
  + slovník, `response_format=json`. Flash attention je v serveru zapnutá defaultně.
- **Časová razítka musí zůstat zapnutá** (`no_timestamps=false`), i když je nepoužíváme. Bez nich Whisper
  (a) u nahrávek nad 30 s ztratil vše za prvním oknem: 35 s řeči vrátilo jen „Titulky vytvořil Jirka Kováč“,
  filtr to smazal a nevložilo se nic; (b) při pauze 2–5 s uprostřed nahrávky zahodil celou větu i pod 30 s.
  Ověřeno na Pepových nahrávkách slepených s tichem: s razítky se ve 24 testech neztratilo nic, rychlost ~ +3 %.
  `verbose_json` (segmenty) by přidal ~0,7 s na každý přepis, proto zůstává `json`.
- **`suppress_nst` je schválně vypnuté**, protože maže `: " ( ) /` (např. „10:30“ by se změnilo na „10 30“).
- Filtry: nahrávka kratší než 0,3 s nebo s max. RMS pod 200 (≈ −44 dBFS; u šumícího mikrofonu pod 3× jeho šum,
  viz Mikrofon) se nepřepisuje. Maže se známá halucinace
  „Titulky vytvořil JohnyX“ a samostatné „Děkuji za pozornost / sledování“, „Titulky“, „Hudba“. Filtruje se po kusech
  (viz průběžný přepis), takže halucinace uprostřed nesmaže zbytek textu.
- Opravy (`replacements`, „comgit“ → „Comgate“) se aplikují na celý text diktátu: celá slova, bez ohledu na velikost
  písmen. Pak hlasové povely.

### Průběžný přepis (`live_transcribe`, měřeno na 30 Pepových nahrávkách)
- Během držení `Recorder._cut_at_pause` odřízne hotový kus v půlce pauzy a ten se hned přepisuje. Po puštění zbývá
  jen poslední kus, text se vkládá **najednou po puštění** (Pepa nechtěl psaní během mluvení). Kusy jedné nahrávky
  jdou za sebou v jednom vlákně (`Take`); do promptu každého jde konec předchozího textu (150 znaků).
- Parametry: pauza = bloky 30 ms s RMS < 150 (HyperX v tichu 1–11, řeč 150–800; u šumícího mikrofonu víc, viz
  Mikrofon) aspoň 0,5 s, kus aspoň 6 s. Pepovy pauzy mezi větami mají 0,4–1,3 s, s prahem 0,6 s se 35 s diktát
  vůbec nerozdělil.
- Výsledek: průměrné čekání po puštění 1,99 → 1,62 s, 35 s diktát 6,0 → 1,4 s, 31 s bez pauz v druhé půlce 5,3 → 4,0 s.
  Nejhorší zpomalení +0,9 s: dělení těsně před puštěním, zbytek pak čeká na grafiku (každý požadavek má ~0,9 s
  pevné režie, whisper-server přepisuje jen jeden naráz). Proto minimum 6 s; s 3 s bylo víc chyb na hranicích.
- Cena: ~5 % slov se liší od přepisu celé nahrávky, většinou nevadí („teďka/teď“), občas horší na krátkém konci
  („obrať pořadí“ → „Obratíš po řadě“), občas lepší. Proto je to přepínač v nastavení.

### Učení slovníku (`learn_vocabulary`)
- Pepa chtěl, aby se slovník „vylepšoval sám podle logu“. Orbit sám nepozná, co je chyba (naučil by se i chyby),
  proto po každých 10 nových přepisech v logu pošle jejich **text (ne zvuk)** Claudovi, s Pepovým souhlasem.
- `claude -p --safe-mode --model sonnet --tools "" --no-session-persistence --output-format json --json-schema ...`
  bez `ANTHROPIC_API_KEY` a proměnných, které Claude Code nastavuje svým podprocesům (`CLAUDECODE`,
  `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_SESSION*`, `CLAUDE_CODE_MESSAGING*`, `CLAUDE_PID`…; `claude_cli.environment`),
  takže poběží na předplatném a nebude si myslet, že je vnořený v Claude Code. Uživatelovy vlastní (`CLAUDE_CONFIG_DIR`,
  `CLAUDE_CODE_GIT_BASH_PATH`) zůstávají (dřív se mazalo všechno `CLAUDE*`). Spouští se jen skutečný `claude.exe`
  (npm, `~/.local/bin`, WinGet, PATH, `node_modules` vedle npm shimu), nikdy `.cmd`/`.bat`: cmd.exe by víceřádkový
  `--system-prompt` usekl na prvním řádku (Pepa má na PATH `WindowsApps\claude.BAT`). Výsledek je
  v `structured_output`, běh trvá ~16 s. Při chybě se to hodinu nezkouší.
- Prompt nezná Pepovy firmy: bere jméno (`name`) a jednu větu „O mně“ (`about`) z nastavení, obojí může být prázdné.
- Slovník má strop 300 znaků: whisper.cpp z promptu drží ~224 tokenů a při přetečení zahazuje začátek. Nastavení
  ukazuje počet znaků (`41/300`) a nad limitem varuje; učení i import přidávají jen to, co se vejde.
- Opravy jen pro fráze, které v češtině nemůžou být správně („cloud“ → „Claude“ ne, cloud je slovo).
  Obojí je vidět a upravitelné v nastavení, v menu je „Naučit slovník z nových diktátů“.

### Volba modelu (měřeno, ne odhadem)
Test: česká část FLEURS (test split, 723 nahrávek, vzato každé 4., tedy 150 vzorků), WER/CER přes `jiwer`
po normalizaci (malá písmena, bez interpunkce), přes `whisper-server` na RX 9070 XT:

| Model / varianta | WER | CER | průměr |
|---|---|---|---|
| **large-v3, beam 5, s promptem** (zvoleno) | 8,91 % | 2,47 % | 1,89 s |
| large-v3 bez promptu | 8,84 % | 2,56 % | 1,87 s |
| large-v3 greedy (beam 1) | 9,24 % | 2,64 % | 1,82 s |
| large-v3 q8_0 | 9,06 % | 2,52 % | 1,87 s |
| large-v3-turbo | 10,16 % | 2,92 % | 0,92 s |
| mikr/whisper-large-v3-czech-cv13 (q5_0 od icoach) | 11,30 % | 4,75 % | 1,87 s |

Závěry: prompt přesnost neovlivní (nechává se kvůli slovníku), kvantizace ani greedy na Vulkanu nezrychlí,
doladěný český model je horší (smazán). Latence large-v3 podle délky nahrávky: 2 s → 0,9 s, 4,5 s → 1,4 s,
10 s → 1,9 s (turbo 0,2–0,35 s). S turbem měl Pepa chyby typu „rozpozdává“, „pozdal“, „vypolišovat“; na testovací
řeči je large-v3 napsal správně. Přidání ticha na začátek nahrávky nepomáhá (ověřeno).

### Mikrofon – soukromí má přednost
- **Mikrofon je otevřený jen při držení push-to-talk** (a v okně nastavení kvůli živé vlně). Zkoušel jsem „stále
  připravený“ mikrofon s 0,4 s pre-rollem, aby se neusekla první slabika, ale **Pepa to výslovně odmítl**
  (nechce, aby aplikace poslouchala pořád). Takové řešení už nenavrhovat.
- Místo toho: headset po otevření chvíli posílá přesné nuly (jednou naměřeno ~0,18 s, teď obvykle 50–70 ms). Pípnutí
  a červené tlačítko přijdou až s prvním nenulovým vzorkem (`Recorder` → `on_live`). Úvodní nuly se zahazují.
  Záloha: když přijdou jen nuly (ztlumený mic), po 600 ms (`LIVE_FALLBACK_MS`) se pokračuje i tak.
- Po puštění se nahrává ještě 250 ms (`TAIL_MS`), lidé pouštějí klávesu během posledního slova.
- Šum HyperXu v tichu má amplitudu jen 1–3, proto je detekce „živého“ zvuku `np.any(chunk)`, ne práh.
- **Bluetooth sluchátka (Pepa má i AirPods Max)**: jejich mikrofon jede jen v profilu hands-free, takže při jeho
  otevření Windows přepne sluchátka z hudby (A2DP) do režimu hovoru – hudba zhorší kvalitu a po zavření mikrofonu
  „přeskočí“ zpět. V softwaru to obejít nejde (u AirPods Max ani LE Audio). Nahrávky z AirPods jsou 8 kHz
  (nad 4 kHz nulová energie, HyperX 7–12 %), což Whisperu v češtině škodí (sykavky). Nastavení proto u takového
  mikrofonu ukáže oranžové varování (`is_bluetooth_handsfree`: WASAPI dvojče MME zařízení má ≤ 16 kHz).
- Seznam zařízení PortAudio je v cache a čísla zařízení si PortAudio spáruje s Windows jen při načtení. Před každým
  otevřením mikrofonu proto `Recorder` porovná seznam Windows (winmm, ~0,3 ms, jména zkrácená na 31 znaků jako
  v MME) s tím svým a při rozdílu (zapojeno, odpojeno) ho obnoví (~30 ms); jinak by po přepojení otevřel jiný
  mikrofon (třeba AirPods v režimu hovoru). Když zvolený mikrofon chybí, obnoví seznam a vezme výchozí, když otevření
  selže, obnoví a zkusí znovu. „Výchozí mikrofon Windows“ (`mic: null`) otevírá **Sound Mapper** (první vstup MME,
  pojmenovaný jazykem Windows, proto podle pozice, ne jména): ten nahrává z toho, co je výchozí teď, ne při startu
  Orbitu. Bez mikrofonu „Windows teď nevidí žádný mikrofon“.
- Obnovit seznam (`Pa_Terminate`) jde jen bez jiného streamu PortAudio v procesu Orbitu. Dokud Piper hrál v něm,
  uvolnil by i jeho stream pod jeho vláknem (pád v nativním kódu). Od 7. 10. hraje Piper ve vlastním procesu, takže
  `PiperSpeaker.release` vrací vždy True; `Recorder.may_refresh` = `Dictation._release_sound_card` předčítání dál
  zastaví (main.py se neměnil).
- **Prahy podle šumu**: konstanty výš jsou naladěné na tiché mikrofony. Analogový mikrofon s +20 dB zesílením nebo
  hlučný větrák šumí nad 150, pak by se nenašla pauza a agent by poslouchal celých 30 s. `Recorder.noise` = nejtišší
  30ms blok posledních ~3 s, odhad začíná na 50 a roste nejvýš o 2 % za blok (klesá hned), takže řeč bez jediné
  tiché chvilky za šum neprojde. Pauza/ticho pro hands-free je pod `max(150, 3 × šum)`, ticho celé nahrávky
  (`is_silent`) pod `max(200, 3 × šum)`. Prahy jdou jen nahoru: na všech 30 Pepových nahrávkách vyšly řezy, konec
  hands-free i rozhodnutí o tichu přesně jako dřív (ověřeno přehráním).
- **Nahrávka bez řeči už nezmizí potichu** (v Pepově logu 14 s „ticho“ a pak „Haló, haló, slyšíš mě?“): od 1,5 s
  bublina (u agenta řádek v panelu). Jen nuly = „Mikrofon posílá jen ticho. Není ztlumený? … Soukromí › Mikrofon“
  (`Recorder.got_signal`), něco jako řeč, jen moc potichu (aspoň 0,5 s nad `max(50, 3 × šum)`, `voiced_s`) = „mikrofon
  je moc potichu“. Jen šum = nic neřekl, nic se neukáže.

### Push-to-talk
- pynput `Listener(win32_event_filter=...)`, zvolená klávesa/tlačítko se **potlačí** (`SystemHook.SuppressException`),
  aby ji ostatní aplikace nedostaly. Injektované události (naše vlastní Ctrl+V) se ignorují.
- AltGr na české klávesnici posílá falešný levý Ctrl se scan kódem 0x21D, ten se při zachytávání ignoruje.
- Myší hook se instaluje jen když je potřeba (vazba na myš nebo zachytávání), protože vidí každý pohyb myši.
- Hooky ignorují simulovaný vstup, proto se testuje přímo `PushToTalk._handle(...)`.
- **Ztracené puštění klávesy**: hook ho neuvidí na zabezpečené ploše (UAC, zamčení, Ctrl+Alt+Del), v okně správce
  ani když Windows pomalý hook potichu vyřadí; mikrofon by pak nahrával dál a celý pokoj se přepsal do okna.
  Při nahrávání proto každou sekundu `Dictation._watch_recording`: zabezpečená plocha (`winutil.on_user_desktop`,
  `OpenInputDesktop` ≠ „Default“; jen když na začátku nahrávky platila) = nahrávka se zahodí; nahrávka nad 5 min
  (`MAX_RECORDING_S`) se ukončí a přepíše s bublinou; u klávesy `PushToTalk.check_stuck`: držená klávesa opakuje
  key-down každých ~30–50 ms, takže 1,5 s bez opakování (když už nějaké přišlo a mezitím nebyla stisknutá jiná
  klávesa) = puštěná. Tlačítka myši se neopakují, u nich platí jen limit 5 min (Pepa má myš).
  Po ukončení limitem nebo zabezpečenou plochou (`PushToTalk.reset()`) se u pořád držené klávesy její opakování
  spolknou, dokud ji Pepa nepustí (nebo dokud 1,5 s nepřijde žádné, `STUCK_S`): dřív další opakování za 30 ms
  otevřelo mikrofon znovu.

### Plovoucí tlačítko a vkládání
- Okno má `WS_EX_NOACTIVATE` (a `Qt.WindowDoesNotAcceptFocus`), takže klik nebere fokus cílovému oknu. Ověřeno testem.
- Levé tlačítko držet = push-to-talk, tažení (> 6 px) nahrávání zruší a přesune tlačítko, pravé = menu.
  Pozice se ukládá jako levý horní roh oblasti tlačítka (`button_pos`), panel limitů se zarovnává podle polohy
  na obrazovce (vlevo/střed/vpravo, nad/pod).
- Vkládání přes schránku obnoví původní obsah po 700 ms a vloží formáty, které vyřadí text z historie schránky
  (Win+V). V režimu psaní se nový řádek posílá jako **Shift+Enter** (aby chat zprávu neodeslal).
- Záloha schránky bere všechny formáty (buňky Excelu, objekty Office, soubory vyjmuté v Průzkumníku), kromě větších
  než 20 MB, a po 0,5 s skončí (Excel vyrábí formáty až na požádání). Když schránka nejde nastavit (drží ji jiný
  program), Ctrl+V se nepošle (vložilo by starý obsah, třeba heslo) a text se napíše po znacích. U vzdálené plochy
  a virtuálek (`TscShellContainerClass`, `RAIL_WINDOW`, VMware, Citrix) se schránka nevrací, ty si ji berou později.
  Vrácený obsah dostane značky „ne do historie a cloudu“ (ve schránce už byl, Windows ho jednou viděl) a záloha drží
  i prázdné značky správce hesel (`ExcludeClipboardContentFromMonitorProcessing`, `Clipboard Viewer Ignore`): heslo se
  jinak po diktátu objevilo ve Win+V.
- **Text jde jen do okna, které bylo v popředí při puštění klávesy** (`Take.target`, porovnání podle vlastníka okna):
  když se mezitím přepnulo jinam, text skončí ve schránce s bublinou a Enter z „Odešli“ se nepošle (dřív šel do
  jiného chatu nebo terminálu). Do oken spuštěných jako správce Windows vkládat nedovolí (UIPI) a ani neřekne, že
  ne: `inserter.runs_as_admin` (token procesu s `TokenElevation`, nebo přístup odepřen) → text do schránky
  a bublina „Okno běží jako správce…“. Stejně, když `SendInput` nevezme všechny události.
- Po 3 s nečinnosti (stav idle, myš mimo, žádné menu) tlačítko i panel zprůhlední na 30 % (`windowOpacity`,
  animace), Pepa chtěl, aby bylo vidět „jen malinko“ (10 % i 20 % byly moc průhledné, 30 % schválil). Najetí myší, nahrávání nebo
  přepis ho hned vrátí.

### Relace Claude Code (`show_sessions`, `speak_answers`)
- Pepa pouští Claude Code přes `cmd.exe` z Průzkumníka, **každá relace má vlastní okno Windows Terminalu**
  (defterm handoff). Proces: `claude.exe ← cmd.exe ← explorer.exe`. Konzole relace je skryté `PseudoConsoleWindow`,
  jeho vlastník (`GetAncestor(..., GA_ROOTOWNER)`) je okno WT → klik na řádek přepne přesně na tu relaci.
  Titulek okna nastavuje Claude Code: téma relace se spinnerem (`◐ Katalog z Německa překlad`, `✳` = v klidu).
  Pepa má často víc relací ve stejné složce (třeba 4× `m-tex`), proto se relace jmenují podle tématu.
- Hooky v `~/.claude/settings.json` (Pepa souhlasil): SessionStart, UserPromptSubmit, Notification, Stop,
  StopFailure, SessionEnd a PostToolUse s `"matcher": "Artifact"` → `"command": "<python.exe vedle Orbitova>",
  "args": ["<absolutní cesta>/app/cc_hook.py"], "async": true` (exec forma bez shellu, u Pepy
  `C:/Users/josef/orbit/.venv/Scripts/python.exe`). Orbit je přidá (se souhlasem `claude_hooks`), když je zapnutý
  přehled relací nebo předčítání artefaktů, jinak odebere (`claude_settings.set_hooks`). Běžící relace si změněné
  hooky načtou samy (ověřeno 30. 9. s Claude Code 2.1.28x).
- **Vlastnictví (od 3. 10.)**: Orbit pozná svůj hook jen podle cesty ke **svému** `cc_hook.py` (porovnání bez ohledu
  na lomítka, velikost písmen a krátká jména 8.3, `claude_settings.same_path`), v `args` i v příkazové řádce.
  Hooky jiné kopie Orbitu (vývojová složka vedle nainstalované) i cizí hooky zůstanou; ze skupiny vyřadí jen svůj
  hook, cizí hook ve stejné skupině zůstane. Nečitelný `settings.json` (neplatný JSON, ne objekt, `hooks` jako seznam)
  nepřepíše (`SettingsError` → bublina), BOM nevadí, zápis je atomický (dočasný soubor + `os.replace`), a když
  Claude Code soubor mezitím změní, začne znovu od nového obsahu. Jen první změna uloží
  `settings.json.orbit-backup`. Pepovy hooky jsou po restartu beze změny (ověřeno na kopii jeho `settings.json`).
- **Které relace běží**, bere Orbit ze seznamu, který si vede sám Claude Code: `~/.claude/sessions/<pid>.json`
  (`sessionId`, `cwd`, `status` busy/idle, `startedAt` v ms, `kind` interactive). Relace jsou tak v přehledu hned,
  i bez jediné události z hooku (dřív se objevila až po první události). Složka relace je `cwd` z tohoto seznamu
  (složka, kde relace začala), ne z hooku: hook hlásí aktuální složku, která se po `cd www` změní na `www`. Přepis se dohledá jako
  `~/.claude/projects/*/<sessionId>.jsonl`. Neoficiální formát, stejně jako přepis.
- Hook píše jeden soubor na relaci a událost (souběžné async hooky se tak nepřepisují), s `pid` (předek `claude.exe`),
  `permission_mode` a `hwnd` (okno relace). Async hooky mají konzoli **bez okna** (`GetConsoleWindow` = 0, a proto
  i `AttachConsole` selhal: proces už ke konzoli připojený je – tak u Pepy hook zapisoval `hwnd` 0). Hook teď svou
  konzoli nejdřív pustí (`FreeConsole`), pak se na chvíli připojí ke konzoli `claude.exe` (`AttachConsole` → okno →
  `FreeConsole`) a vezme jejího vlastníka (`GA_ROOTOWNER`), jen když je viditelný (WT, klasická konzole). Jinak
  (terminál ve VS Code, Cursoru) vezme hlavní okno nejbližšího předka `claude.exe`, který nějaké má (s více okny
  to, jehož titulek obsahuje složku relace; u `explorer.exe` hledání končí). U relací bez okna se hledá podle titulku
  (třída `CASCADIA_HOSTING_WINDOW_CLASS` nebo `ConsoleWindowClass`, titulek bez spinneru = název relace), jinak
  klik na řádek nedělá nic. Víc relací v jednom okně (karty WT): `Session.shared`, za „v popředí“ se počítá jen ta,
  jejíž téma je v titulku okna; klik přenese okno, kartu si uživatel vybere. Orbit čte vše každou sekundu. Stav =
  nejnovější událost; Notification jen typů `permission_prompt`/`elicitation_dialog` = „čeká na tebe“. Z „čeká“
  zpět na „pracuje“ pozná podle změny souboru s přepisem. **Přerušený tah** (Esc, „Stop.“, zamítnuté oprávnění)
  Stop hook nespustí: „pracuje“ se změní na „v klidu“, když seznam relací hlásí `idle` (víc než 2 s po zadání) nebo
  přišlo `idle_prompt` po zadání. Novinka se oznamuje jen jednou (`Session.announced`), krátké „busy“ (`/compact`)
  tak neopakuje staré „Hotovo“. Bez událostí stav z `status` seznamu. Mrtvý `claude.exe` (nebo jiný proces se
  stejným PID) = soubory smaže.
- **Režim oprávnění relace** (`Session.mode`, `mode_class`): z hooku (`permission_mode`), jinak z přepisu
  (`"permissionMode"` u záznamů uživatele). Třída jako u Claude Code: „bypass“ = `bypassPermissions`, nebo `plan`
  u relace, která někdy běžela v bypass (`bypass_seen`); jinak „prompting“. `sessions.bypass_in_use()` = rozhodne
  nejnovější relace se známým režimem, bez nich `skipDangerousModePermissionPrompt` / `permissions.defaultMode`
  v `settings.json` (u Pepy `true`). Tooltip relace ukáže „Běží bez ptaní na oprávnění.“
- **Pozor na automatickou aktualizaci Claude Code**: běžícímu procesu přejmenuje exe na `claude.exe.old.<číslo>`.
  Kontrola živosti proto bere jméno souboru začínající `claude.exe`. Dřív to Orbit bral jako ukončenou relaci a mazal
  její soubory, takže po aktualizaci (30. 9. i třikrát za den) byla v přehledu jen část relací.
- **Název relace** = `aiTitle` z přepisu (záznam `{"type":"ai-title","aiTitle":"Analýza ceníků a katalogů
  Profodu"}`, opakuje se v přepisu, čte se z konce, celý soubor jen napoprvé). Bez něj název složky. Stejný text dává
  Claude Code do titulku okna. Používá se v panelu, v bublinách i v hlasu („Hotovo: …“). V panelu je za názvem
  tlumeně i složka (Pepa chtěl vidět, kde relace pracuje), proto je panel široký 440 px (s 320 px se názvy
  ořezávaly). Relace jsou seřazené podle složky a začátku relace (pořadí neskáče se změnou stavu).
- **Loop v relaci** (od 7. 10., `Session.loop`, `sessions._LoopScan`): za názvem relace ikona smyčky (E8EE) a „do 23:00“
  (bez konce v zadání „loop“) v barvě akcentu, v tooltipu jak často a kdy je další kolo, totéž dostane agent. Joby
  `/loop` žijí jen v procesu relace, proto se čtou z přepisu (čte se dál od posledního místa, poprvé celý):
  `CronCreate` (opakovaný; id jobu z `toolUseResult.id`, konec `CronDelete` nebo po 7 dnech), `ScheduleWakeup`
  (loop bez intervalu, sám si plánuje kola; `stop` = konec, víc než 5 min po plánovaném kole a relace v klidu =
  skončil) a samotné spuštění (`Skill` `loop` nebo `<command-name>/loop`) jen během jeho prvního tahu. Joby z doby
  před startem procesu (obnovená relace) se nepočítají. Konec se čte z textu zadání („do 23:00“, „pokud je 23:00 nebo
  později“, „do 23 hodin“, „until 23:00“), nejbližší takový čas po spuštění loopu.
- `claude -p --safe-mode` (učení slovníku) hooky nespouští a jeho záznam v seznamu (`entrypoint` `sdk-cli`)
  Orbit vynechá, v přehledu se neobjeví.
- Stop hook nese `last_assistant_message` → bublina a předčítání. Oznamuje se jen když okno relace není v popředí
  a tah trval ≥ 20 s (`NOTIFY_TURN_S`). Dokud nějaká relace čeká na Pepu, panel se nezprůhlední.
- **Bubliny jsou Orbitovy, ne Windows** (Pepa chtěl hezčí vzhled i zvuk): `ui.Bubble` je tmavá karta ve stylu
  panelu s ocáskem k tlačítku mikrofonu (na straně ke středu obrazovky, horní hranou u horní hrany kruhu, aby
  nezakryla panel). Barevná ikona podle druhu: hotovo zeleně ✓, čeká oranžově ?, chyba červeně !, info modře.
  U relací je nadpis název relace, vpravo stav, text jsou první 2 věty odpovědi (max. 4 řádky). Klik = přepnutí
  do relace, pravý klik = zavřít, najetí myší ji podrží. Zmizí po 7 s (čeká 12 s, chyba 10 s), naráz je jen jedna.
  Tlačítko se po dobu bubliny nezprůhlední. Když je tlačítko skryté, bublina je vpravo dole bez ocásku.
- Zvuky bublin (`winutil._chime`, měkké tóny jako kalimba): hotovo G5 → C6, čeká C6 C6 (zaklepání), chyba
  C6 → G5, info A5. Při hře/prezentaci na celou obrazovku (`SHQueryUserNotificationState`) se místo bubliny použije
  bublina Windows (ta počká). Režim Nerušit ve Windows 11 se tak nepozná. Bubliny nejsou v Centru oznámení.
  Soubory `cache/*.wav` (v datové složce) vznikají při prvním použití, po změně zvuku je smazat. Chyba zvuku
  (`winutil.play`) se jen zaloguje, nikdy nesmí zahodit diktát; pípnutí na konci jde až po zařazení nahrávky.
- Kontext: přesně ze stavového řádku Orbitu (`context_window.used_percentage` a `context_window_size` v
  `sessions/status/<id>.json`), když tam je a není o víc než 10 min starší než přepis (`STATUS_FRESH_S`). Jinak
  (Pepa nemá stavový řádek) odhad: `input + cache_creation + cache_read` z posledního `usage` hlavní větve
  (`isSidechain` false) na konci přepisu (čte se jen posledních 512 KB, podle mtime), velikost okna 1 mil. když má
  `settings.json` model s `[1m]` (Pepa má `opus[1m]`) nebo tokenů je přes 200 tis., jinak 200 tis. Formát přepisu
  není oficiálně stabilní – když se změní, procento prostě zmizí.
- Předčítání: `QTextToSpeech("winrt")`, hlas **Microsoft Jakub** (cs_CZ, jediný český ve Windows, OneCore; SAPI ho
  nevidí). Při začátku nahrávání se okamžitě zastaví (i s frontou). `sessions.summary` čistí Markdown na první 2 věty.
  Texty jdou přes vlastní frontu (`Dictation._speech`), ne `QTextToSpeech.enqueue`: winrt při dvou `enqueue` těsně
  po sobě (než začne mluvit) první text zahodí – ověřeno. Další text se posílá až po stavu Ready přes
  `QTimer.singleShot(0)`: `say()` přímo v obsluze Ready po `stop()` winrt ignoruje (ověřeno). Při hře/prezentaci na
  celou obrazovku se nečte.
- **Hlas pro předčítání** (`voice`, od 1. 10.): Jakub zní roboticky, Pepa chtěl zkusit jiný. Windows 11 nemá český
  „přirozený“ hlas (jen en/zh/es/ja/fr/pt/de/ko), cloudové Antonín/Vlasta (edge-tts, Azure) by posílaly text
  odpovědí ven, proto **Piper** (`piper-tts`, ONNX na CPU, úplně lokálně): `cs_CZ-jirka-medium` (mužský) a
  `cs_CZ-kasandra-medium` (ženský) v `models/piper/` (63 MB každý, z huggingface.co/rhasspy/piper-voices).
  `voice.PiperSpeaker`: model se načte hned při volbě (~1,8 s), pak ~0,1 s na větu, hraje se po větách přes
  `sounddevice.OutputStream` po 0,1 s, takže `stop()` utne do ~0,1 s (větu, která se zrovna syntetizuje, nejdřív
  dodělá). Stejná fronta jako Jakub (`finished` místo Ready, jednou za každé `say()`, i za zastavený text). V nastavení
  „Hlas pro předčítání“ + „Poslechnout“ (ukázková věta; bez uložení se volba vrátí). Výchozí je Jakub, Pepa si
  vybral Jirku.
- **Piper běží ve vlastním procesu** (od 7. 10.): `PiperSpeaker` spustí `pythonw -I -c …` → `voice._worker` (stejný
  Python jako Orbit, v Job objectu, skončí i se zavřeným stdin). Proč: načtení hlasu drží GIL 1,6–6 s a v procesu
  Orbitu stálo UI i háčky klávesnice a myši celého systému (celý `Dictation` s Jirkou: smyčka stála 6,8 s, teď nejvýš
  31 ms; start dřív čekal s kontrolou Clauda i whisperem na „Piper načten“). Pád espeaku nebo onnxruntime shodí jen
  ten proces, další `say()` ho spustí znovu (max. 3× za běh). Protokol: na stdin `say <JSON>` / `stop`, na stdout
  `loaded <s>` / `done` / `error <JSON>`. Naráz běží jen jeden (nový hlas zavře starý proces).
- Worker čte stdin jen přes `PeekNamedPipe`: blokující čtení stdin a současný import numpy v jiném vlákně = zamrznutí
  navždy (DLL s vlastním CRT volá `GetFileType` na stdin; ověřeno výpisem zásobníku).
- onnxruntime v něm běží bez memory areny, bez spinningu vláken a s max. 4 vlákny: proces má ~125 MB místo +626 MB
  v Orbitu po delším textu a syntéza stojí ~10,6 s CPU místo ~19 s (měřeno na PC na 100 %). Je asi 1,5× pomalejší,
  pořád ~9× rychlejší než realtime.
- espeak-ng neotevře svá data v cestě s jediným znakem mimo ASCII (`C:\Users\Tomáš\…`) a ukončí celý proces
  (exit 1, bez výjimky; 1.0.0 tak u takového uživatele zmizel při prvním předčítání). Proto dostává cestu 8.3
  (`voice._ascii_path`); když 8.3 jméno není, `piper_installed()` je False a Piper se nenabízí.
- Pro stažený hlas Piperu se `voice.effective` Windows na Jakuba neptá: `QTextToSpeech("winrt")` by při startu
  načetl FFmpeg a Media Foundation (~25 MB, 84 ms).

### Předčítání artefaktů (`read_artifacts`)
- Pepa chtěl: když kterákoli relace Claude Code zveřejní artefakt (nástroj Artifact), udělá se souhrn toho
  nejdůležitějšího v 7 větách a přečte se z reproduktorů.
- Hook PostToolUse (matcher `Artifact`) zapíše `sessions/artifacts/<relace>.<tool_use_id>.json`, jen pro publikování
  stránky (`file_path`, bez `asset`, akce publish). `tool_response` je slovník `{url, path, title, updated, seq, …}`
  (zjištěno z Pepových přepisů), URL se pro jistotu hledá i regexem v textu. Záznamy starší 5 min se zahodí.
  Záznam se maže až po dokončení souhrnu (`artifacts.done`), ne při převzetí: jeden artefakt se ztratil, protože
  se Orbit restartoval uprostřed souhrnu. Teď ho po startu převezme nový Orbit.
- Text se bere z **lokálního souboru**, který relace publikovala (kopie na claude.ai by chtěla přihlášení):
  viditelný text HTML a za ním obsah vložených skriptů, protože data tabulek a grafů bývají v `const D = {…}`
  (u stránky o zdražení PROFOD bylo viditelného textu 1,8 tis. znaků ze 100 KB). Max 60 tis. znaků.
- Souhrn: `claude -p` se Sonnetem, JSON `{title, sentences}`, česky, tykání, věty pro poslech (bez Markdownu, URL).
  Trvá ~7–8 s. Pak bublina (klik otevře artefakt v prohlížeči) a Jakub přečte „Artefakt z relace m-tex: …“.
  Čte se vždy, i když je okno relace v popředí. Během diktování počká, až Pepa pustí klávesu.
- Znovu publikovaný artefakt (oprava překlepu) se nečte, pokud je text z ≥ 80 % stejný (`difflib` po slovech);
  při větší změně „Aktualizovaný artefakt…“. Paměť jen do restartu Orbitu. V menu „Přečíst znovu poslední artefakt“.
- **Tlačítko reproduktoru** vlevo od mikrofonu, stejně velké (Pepa chtěl nejdřív ikonu vedle mikrofonu, malý
  satelit 24 px mu byl malý). `button_pos` je dál levý horní roh čtverce mikrofonu, reproduktor je v pruhu vlevo
  (`_slot`), bublina míří na oba kruhy. **Od 1. 10. je to ztlumení celého Orbitu** (Pepa chtěl, aby po zmáčknutí
  nebylo slyšet nic): klik přepne `muted`, bílý reproduktor (E767) = zvuky jdou, šedý přeškrtnutý (E74F) = ticho,
  kruh v barvě akcentu = právě čte (tlačítko se mezitím nezprůhlední). Ztlumení vypne pípání start/stop, zvuky
  bublin i předčítání (odpovědi i artefakty) a hned utne, co se čte. Bubliny se dál ukazují, souhrny artefaktů se
  dál dělají. Výjimka: „Přečíst znovu poslední artefakt“ z menu čte i ztlumeně (výslovná žádost).
  `read_artifacts` je teď jen v nastavení; jeho vypnutí utne čtený souhrn, odpověď relace ve frontě se přečte.
- Neumí artefakty z chatu na claude.ai / v aplikaci Claude (tam hook není) ani dokumenty přes konektor Claude Docs.

### Hlasový agent (`agent`, od 1. 10.)
- Pepa chtěl „kamaráda vedle sebe“: hlasem se ptát na relace a nechat ho do nich psát prompty. **Boční tlačítko
  myši zpět** (`agent_ptt`, X1): držet = push-to-talk, kliknout (pustit do 0,35 s, `CLICK_S`) = poslouchá, dokud
  se neodmlčí (1,4 s ticha po řeči, `END_SILENCE_S`; nic neřekl 6 s = konec; max 30 s; druhý klik ukončí). Totéž
  klik na ikonu agenta. Mikrofon je tak pořád otevřený jen po výslovné akci. Diktovací klávesa nahrávku agenta
  neukončí a naopak (`stop_recording(for_agent)`).
- Mozek = jeden trvalý `claude -p --input-format stream-json --output-format stream-json --verbose
  --setting-sources "" --strict-mcp-config --mcp-config … --no-session-persistence --model sonnet --effort low
  --tools ListAgents,SendMessage --allowedTools <jeho nástroje> --permission-mode default
  [--allow-dangerously-skip-permissions] --name Orbit --system-prompt …` (`agent.VoiceAgent`). Start 0,9 s (spouští
  se při stisku, zatímco Pepa mluví), odpověď Sonnetu ~2 s. Po 30 min bez řeči nový rozhovor (`IDLE_RESET_S`),
  nikdy ale uprostřed tahu ani když čeká potvrzení (`_pending`; i tah, který sám začala zpráva od relace, je
  `busy`). Nový proces místo starého pošle událost „reset“ (main zapomene staré potvrzení).
- Každá Pepova věta jde agentovi s aktuálním přehledem relací (`agent.context`): adresa (`name` z
  `~/.claude/sessions/<pid>.json`, např. `m-tex-41`), téma, složka, stav, poslední zadání (hook teď ukládá i
  `prompt`, max 1000 znaků) a poslední odpověď. Do promptu Whisperu jdou názvy složek relací.
- **Posílání = vestavěné zprávy mezi relacemi** (SendMessage, named pipe `messagingSocketPath` + `.key`),
  ne simulace kláves. Ověřeno: zpráva dorazí jako `<cross-session-message from-name="Orbit" from-mode="bypass">`.
- **Režim oprávnění agenta (od 3. 10.)**: Claude Code (2.1.288, kód v `claude.exe`) dělí relace na třídu „bypass“
  (`bypassPermissions`, nebo `plan` s povoleným bypass) a „prompting“ (vše ostatní). Odesílatel třídu přiloží
  (`from_mode`, počítá se v okamžiku odeslání z jeho **aktuálního** režimu), příjemce zprávu z jiné třídy **zadrží**
  („Held peer message … permission mode class doesn't match“, schválit ji jde jen v jeho okně;
  `"crossSessionInbound": "accept"` by to vypnulo, ale Orbit nastavení uživatele nemění). Řešení: agent běží
  v režimu `default` a těsně před odesláním potvrzené zprávy se přepne do třídy cílové relace (`control_request`
  `set_permission_mode`, CLI zpracuje stdin popořadě, takže režim platí dřív, než nástroj pokračuje; ověřeno bez
  přihlášení). Do `bypassPermissions` se přepnout smí jen s `--allow-dangerously-skip-permissions`, a ten agent
  dostane, jen když relace uživatele samy běží bez ptaní (`Dictation._sessions_bypass`: nějaká relace má třídu
  bypass, nebo `sessions.bypass_in_use()`); když se taková relace objeví později, další stisk začne nový rozhovor
  s tímhle přepínačem. Jeho nástroje jsou v obou režimech stejné a „jo“ je hlídá stejně, bezpečnost relací se tím
  nesnižuje. Když přepnout nejde, Orbit to řekne v otázce („…zpráva tam počká, až ji v jejím okně schválíš“)
  a výsledek „held for … approval“ ukáže jako „čeká na schválení v relaci“. Výzvy `can_use_tool` (default režim)
  agent povolí jen pro své nástroje, jiné zamítne. Ověřeno jedním během s haiku: MCP nástroj běží, hook u
  SendMessage zastaví odeslání i v default režimu.
- **Potvrzení vynucené kódem**: Orbit při `initialize` zaregistruje PreToolUse hook callback (`hookCallbackIds`,
  `timeout` 600 s) na SendMessage a `open_session` a na `control_request` `hook_callback` odpoví až po Pepově
  odpovědi (`permissionDecision` allow/deny + důvod). Ověřeno, že CLI čeká i 75 s. Orbit návrh ukáže a přečte
  **celý** („Pošlu do relace …, složka …: … Mám to poslat?“; adresa se čte jako server, Markdown se vynechá,
  v panelu je zpráva celá až na 10 řádků). Zprávu s blokem kódu, delší než 500 znaků nebo s víc než 6 řádky vrátí
  agentovi, ať ji zkrátí (`_unreadable`), a novou relaci jen ve složce ze seznamu `project_folders`
  (`agent.known_folder`, dvě stejně pojmenované složky se čtou i s nadřazenou). Odpověď platí jen pro otázku, která
  **byla v panelu aspoň 1 s před začátkem nahrávky** (`Take.confirm_id`, `_confirm["shown"]`, `CONFIRM_SEEN_S`):
  co uživatel začal říkat dřív, agent dostane jako důvod zamítnutí a zeptá se znovu. Dočtení otázky se nečeká:
  dřív platilo jen „dozněla celá“, jenže zadání nové relace (451 znaků) se čte ~35 s, Pepa si ho přečetl v panelu,
  čtení přerušil svým „jo“ a Orbit každé „jo“ zahodil (7. 10. třikrát po sobě, nová relace nešla založit).
  Odpověď (`agent.confirmation`, max 5 slov): ano jen když jsou všechna slova „ano“ nebo výplň („jo, pošli to“),
  ne když je tam ne/počkej/zruš nebo slovo na „ne…“ delší než 3 písmena („není to ono“), cokoli jiného („ano, ale
  do jiné“) = zamítne s jeho slovy jako důvodem a agent zprávu upraví. Bez odpovědi do 2 min se zahodí.
- Zpráva začíná „<jméno> (hlasem přes Orbit):“ (bez jména „Uživatel (hlasem přes Orbit):“), ať příjemce ví, čí jsou
  to slova (v panelu a hlasu se vynechá, `agent.without_prefix` pozná prefix s jakýmkoli jménem).
- UI: ikona agenta (planeta s prstencem a měsícem, 30 px) vlevo od teček barev (tooltip jmenuje jeho skutečné
  tlačítko z `agent_ptt`, dřív tam bylo natvrdo „boční tlačítko myši zpět“). Modrá = klid, červená =
  poslouchá (halo podle hlasitosti), měsíc obíhá = přepis/přemýšlí, pulzuje = mluví, oranžová = čeká na „jo“.
  Dole v panelu „Agent Orbit“ se stavem, „Ty: …“, odpověď (max 3 řádky) a u odeslání „→ téma relace, složka,
  stav (čeká na tvoje „jo“ / odesláno ✓ / zrušeno …)“ a text zprávy s pruhem v barvě akcentu. Klik na zprávu
  přepne do té relace. Zmizí 90 s po poslední aktivitě. Odpovědi čte Jakub (ztlumení platí i pro agenta).
- Záznamy headless běhů (`entrypoint` `sdk-cli`: agent, učení slovníku, souhrny) se v přehledu relací
  nezobrazují (`sessions._running`). Dřív se tam učení slovníku na chvíli objevovalo.
- **Otevírání stránek v Chromu** (od 1. 10.): „Otevři mi v Google Chrome objednávku 82“ → agent zavolá
  `find_pages("objednávka 82")` a pak `open_page(url, title)` (nástroje MCP serveru `agent_tools.py`, kód
  v `app/browser.py`). Hledá se v historii Chromu (`User Data/*/History`, SQLite, čte se z kopie, protože ji Chrome
  drží otevřenou; ~0,6 s). Čísla musí sedět jako celá čísla, slova podle kmene bez diakritiky („objednávku“ najde
  „Objednávka #82“). Výsledek: `m-tex.cz/admin/order-detail.php?id=82`. **Bez potvrzení „jo“** (jen ukazuje
  stránku), proto se odkazy, které něco dělají (`logout`, `delete`, `storno`, `zrus`, `confirm`, `checkout`,
  `.pdf`…, a parametry `?do=`, `?action=`, `?status=`…) a odkazy s tajnými údaji (`token`, `sid`, `password`,
  `code`+`state`…) ve výsledcích vůbec neukážou a `open_page` je odmítne (`browser.ACTION`, `browser._secret`).
  `open_page` otevře jen adresu, kterou v tomhle procesu vrátil `find_pages`, nebo stejnou stránku s jiným číslem
  (`agent_tools._shape`) – adresu vymyšlenou nebo vyčtenou z odpovědi relace odmítne. Čísla se mění jen v cestě
  a dotazu, server a port musí sedět (od 7. 10.; dřív platilo 192.168.1.1 = 10.0.0.5 a localhost:3000 = :3001,
  shop2.cz = shop3.cz). Prompt: brát detail, ne
  úpravu/PDF; když číslo v historii chybí, zaměnit číslo u stejné stránky. Chrome se spouští jako
  `chrome.exe --profile-directory=<profil, kde se stránka našla> <url>` (nová karta), Orbit ho pak přenese do
  popředí (`sessions.focus_window`, z pozadí to Windows samo nedovolí). Bez Chromu agent řekne, že tu Chrome není.
  V panelu „→ název stránky · Chrome · otevřeno ✓“ a adresa. Ověřeno: věta → otevřená karta za ~4,5 s.
- **Nová relace** (`open_session`): `claude.exe` z `claude_setup.find_exe`, `--dangerously-skip-permissions` jen
  když ho relace uživatele používají (`sessions.bypass_in_use`); bez zadání okno, se zadáním minimalizovaná, ale
  ne když se Claude Code nejdřív zeptá na běh bez oprávnění (`skipDangerousModePermissionPrompt` chybí). Cesta ke
  `claude.exe` i zadání jdou do `cmd.exe /s /v:on /k` jen jako proměnné (`!ORBIT_CLAUDE!`, `!ORBIT_TASK!`),
  složka jako pracovní adresář: nic z nich nejde spustit jako příkaz (ověřeno s `& | > ^ % !VAR! "`). Zadání vždy
  začíná prefixem se jménem (MCP server ho dostane v `ORBIT_USER_NAME`), takže nikdy nezačne „-“ jako přepínač.
  Síťové složky (`\\server\…`) odmítne (cmd by začal v `C:\Windows`). `cmd.exe` se spouští plnou cestou ze System32.
- **Pojistka v `agent_tools.open_session`** (od 7. 10.): MCP server už jen neprovede, co pustí hook, sám kontroluje:
  relaci otevře jen ve složce ze seznamu (`agent.known_folder`, ta je i pracovní složkou) a ze zadání ubere jen přesný
  prefix „<jméno> (hlasem přes Orbit):“ nebo „Uživatel (…)“ a vrátí ho jednou. Odmítne zadání s dalším
  „(hlasem přes Orbit)“ kdekoli (`without_prefix` by text před ním při čtení vynechal: útok = příkaz před značkou),
  odkaz v Markdownu `[text](adresa)` (adresa se nečte) a neviditelné znaky (kategorie Unicode C: řídicí, nulové
  šířky, bidi, tag znaky U+E00xx). Odmítnutí přijde agentovi až po „jo“ jako chyba nástroje, hlavní kontrola patří
  do `main._ask_confirm` ještě před otázkou (zatím chybí, stejně jako u SendMessage, vestavěného nástroje, který
  `agent_tools` nechrání).

### Hlasové povely pro terminál
- Věta „Odešli.“ (nebo „Odeslat.“) na konci diktátu = Enter; diktát jen „Stop.“ / „Zastav.“ = Esc (přeruší Clauda).
  Jen jako samostatná věta, „…tak mu to odešli.“ zůstane textem. Patří pod přepínač „Hlasové povely“.
- Enter jde po textu se zpožděním 300 ms + 1 ms na znak (max 1,5 s): terminál vkládá asynchronně a Claude Code bere
  klávesu ve stejné dávce jako psaný text za součást vložení.
- Enter i Esc jdou jen do okna, které bylo v popředí při vložení (od 7. 10., `Inserter.press(…, on_skipped)`): když
  se během zpoždění přepne jinam, klávesa se nepošle (jen řádek v logu). Main zatím `on_skipped` nepředává, bublina
  „povel jsem neprovedl“ chybí.

### Limity Clauda
- **Dva zdroje** (`usage_source` v `config.json`, v nastavení není): `"statusline"` (výchozí pro nové uživatele) a
  `"oauth"`. Starší `config.json` bez klíče dostane `"oauth"` (`main`), **Pepa má tedy limity jako dřív** (i s řádkem
  Fable) a stavový řádek nemá.
- **Stavový řádek (od 3. 10.)**: oficiální rozhraní Claude Code (code.claude.com/docs/en/statusline). Po každé
  odpovědi (debounce 300 ms) spustí příkaz ze `statusLine` v `settings.json` s JSONem na stdin; na Windows přes Git
  Bash, když je (`CLAUDE_CODE_GIT_BASH_PATH`, `C:\Program Files\Git\bin\bash.exe`, vedle `git` na PATH), jinak přes
  PowerShell. `rate_limits.five_hour`/`seven_day` = `{used_percentage, resets_at}` (**Unix sekundy**, ne ISO), jen
  u Pro a Max a až po první odpovědi relace; okno po `resets_at` Claude Code vynechá. Týdenní limit modelu (Fable)
  tam není, řádek zmizí. Orbitův skript `app/cc_status.py` zapíše `sessions/status/<session_id>.json` (limity –
  chybějící okno zůstane z minula –, `context_window`, model, složka, čas) a vytiskne stavový řádek: **původní
  uživatelův** (uložený v `<data>/statusline-previous.json`, spustí se stejným shellem se stejným stdin, max 5 s;
  `ORBIT_STATUSLINE_CHAINED` zabrání smyčce mezi dvěma kopiemi Orbitu), jinak vlastní „Opus · kontext 34 % · 5 h
  23 % · týden 41 %“. Nikdy nespadne viditelně, vždy kód 0.
- Příkaz musí znamenat totéž v Bashi i v PowerShellu (`claude_settings.statusline_command`): slova bez uvozovek
  s lomítky, cesta s mezerou nebo diakritikou jako krátké jméno 8.3 (`GetShortPathNameW`); jen když není, uvozovky
  (a pro PowerShell bez Gitu `& ` na začátku). Ověřeno přes Git Bash i PowerShell i ze složky `Jan Novák`.
  `padding`, `refreshInterval`, `hideVimModeIndicator` původního řádku zůstanou. Vypnutí vrátí původní řádek
  přesně; cizí stavový řádek, který mezitím nahradil Orbitův, nechá; řádek jiné (odinstalované) kopie Orbitu, jejíž
  skript chybí, nevrací. Projektový `statusLine` má přednost před uživatelským, tam pak Orbit data nedostane.
- Souhlas `claude_statusline` (průvodce: „Limity Clauda nad tlačítkem“, nastavení: přepínač Využití Clauda; jen se
  zdrojem `statusline`). Bez souhlasu panel ukáže „Limity Orbit čte ze stavového řádku Claude Code. Zapnout →“
  (klik = souhlas, `Dictation._enable_statusline`). Orbit čte soubory každých 5 s (`STATUS_REFRESH_MS`): pro každé
  okno nejnovější hlášení, jehož `resets_at` ještě nenastal. Nic = „Limity se ukážou po první zprávě v Claude Code.“,
  odpovědi bez limitů = „Claude Code limity tvého účtu nehlásí…“. Soubory starší 8 dní maže. Tooltip říká, z kdy
  čísla jsou (práce v prohlížeči nebo mobilu se ukáže až s další zprávou v Claude Code).
- **OAuth (jen `usage_source: "oauth"`)**: `GET https://api.anthropic.com/api/oauth/usage`, hlavičky
  `Authorization: Bearer <token>` a `anthropic-beta: oauth-2025-04-20`. Token je `claudeAiOauth.accessToken`
  z `.credentials.json` ve složce Claude Code. Endpoint je interní (našel jsem ho v `claude.exe`), může se změnit.
  Čte se pole `limits`: `session` → „5 h“, `weekly_all` → „Týden“, `weekly_scoped` → název modelu ze
  `scope.model.display_name` („Fable“). Starší tvar (`five_hour`, `seven_day`) je jako záloha.
- Obnova OAuth každé 2 minuty (`USAGE_REFRESH_MS`) plus položka v menu. **Token se jen čte, nikdy neobnovuje** (refresh by
  rotoval refresh token a mohl rozbít přihlášení Claude Code). Když vyprší, panel zešedne a ukáže „neaktuální“.
- Bubliny potřebují `Qt.WA_AlwaysShowToolTips`, jinak se u neaktivního okna nezobrazí.
- Předpověď: z odběrů 5h okna za posledních 30 min (aspoň 10 min a +1 bod) se spočítá, kdy dojde. Když dřív než
  se okno obnoví, hlavička ukáže oranžově „dojde v 14:20“ a jednou za okno přijde bublina, pokud zbývá < 60 min.
- Endpoint vrací 429, když se ptá moc často (např. několik restartů Orbitu za sebou; v Pepově logu ~20×). Po 429 se
  Orbit neptá aspoň 5 min (nebo podle `Retry-After`, max 1 h).

### Vzhled „noční signál“
- Barvy: pozadí `#121826`, pole `#1A2233`, linky `#2A3550`, text `#E7ECF5`, tlumený `#8B96AD`, akcent `#5B9DFF`
  (stejný jako pruhy limitů), červená `#E5484D` jen pro „poslouchám“ (nahrávání, zachytávání klávesy, clipping).
- **Tři barvy vzhledu** (`theme.THEMES`, volba v `config.json` jako `theme`): modrá `#5B9DFF` (původní), fialová
  `#A78BFA`, tyrkysová `#2DD4BF`. Vybírají se tečkami v malé pilulce nad pravým horním rohem panelu, mimo něj
  (Pepa chtěl „nahoru doprava nad ikonku reload, úplně mimo div“); když je panel pod tlačítkem, je pilulka pod
  panelem. Bez panelu tečky nejsou. Motiv mění akcent (pruhy limitů, přepínače, vlna, tlačítka) a tmavé plochy
  dostanou jeho odstín (`theme.tint` otočí odstín modrého návrhu, sytost a jas nechá; modrá je přesně původní).
  Stavové barvy zůstávají: oranžová/červená u limitů, tečky relací, ikony bublin, červené nahrávání.
- Písma: Bahnschrift (nadpisy, keycap), Segoe UI Variable Text (text), Segoe Fluent Icons (ikony: mikrofon E720,
  obnovit E72C, klávesnice E765, myš E962, šipka E70D). Znak „↻“ vypadal špatně, proto glyph E72C.
- Aplikace používá styl Fusion a jeden stylesheet (`theme.apply`), který stylizuje i menu, bubliny a message boxy.
  Titulek okna se barví přes `DwmSetWindowAttribute` (atributy 20, 34, 35, 36).
- Nastavení: nahoře „Drž a mluv“ s keycapem (klik = zachytávání) a živou vlnou mikrofonu (`ui.KeyAndMic`, stejný
  kus je v průvodci), dole sloupce „Přepis“ a „Chování“ + „Claude“, místo zaškrtávátek přepínače. Sloupce jsou
  v průhledném `QScrollArea` (`ui.scrolling`), hlavička a Uložit/Zrušit mimo něj: okno je vysoké jako obsah
  (`ui.fit_to_screen`, u Pepy ~1180 px), na menší obrazovce se sloupce posouvají a tlačítka zůstanou vidět
  (dřív okno potřebovalo ~960 px a na notebooku byly Uložit/Zrušit pod lištou). Rozbalovací seznamy jsou
  `ui._combo()`, aby dlouhý název mikrofonu nebo modelu nerozšířil sloupec.
- Ikony: „Segoe Fluent Icons“ má jen Windows 11, Windows 10 má stejné znaky v „Segoe MDL2 Assets“
  (`theme.icon_font()` vybere, co je nainstalované). `cache/chevron.png` se vyrábí při každém startu znovu.

### Datová složka a přenositelnost (od 3. 10.)
- Orbit se chystá i pro kamarády a později k rozdávání, proto nic nesmí předpokládat Pepův počítač. Nainstalovaný
  Orbit je v `%LOCALAPPDATA%\Programs\Orbit` (jen ke čtení), všechno, co Orbit zapisuje, je v **datové složce**.
- Kterou složku, rozhoduje `app/paths.py` (jen stdlib): 1. `ORBIT_DATA_DIR`, 2. složka aplikace, když v ní je
  `config.json` nebo soubor `portable` (**Pepův checkout**: má `config.json`, takže se nic nestěhuje a vše zůstává,
  kde bylo), 3. `%LOCALAPPDATA%\Orbit`. Uvnitř: `config.json`, `orbit.log`, `whisper-server.log`, `crash.log`,
  `recordings\`, `models\` (+ `piper\`), `sessions\` (+ `artifacts\`, `status\`), `cache\`,
  `statusline-previous.json` (původní stavový řádek uživatele, když je Orbitův zapnutý). Ve složce aplikace zůstává
  jen kód, `assets\` (statické) a `whisper\`.
- Složka Claude Code: `ORBIT_CLAUDE_DIR`, jinak `CLAUDE_CONFIG_DIR` (Claude Code ji tak umí přesunout, `.claude.json`
  je pak v ní), jinak `~/.claude` a `~/.claude.json`. Všechno, co Orbit čte nebo zapisuje u Claude Code (hooky,
  seznam relací, přepisy, `.claude.json`, přihlášení pro limity), jde přes `paths.claude_dir()`/`claude_json()`
  a počítá se při každém volání.
- **Testy**: `ORBIT_DATA_DIR` a `ORBIT_CLAUDE_DIR` na dočasné složky, pak nic nesahá na Pepova data ani na jeho
  Claude Code. `claude_cli.environment()` s `ORBIT_CLAUDE_DIR` nastaví spuštěnému `claude` i `CLAUDE_CONFIG_DIR`.
- Hook dostává prostředí Claude Code, ne Orbitu: když Orbit běží s `ORBIT_DATA_DIR`, přidá do hooku
  `["…/cc_hook.py", "--data", "<složka>"]`. Bez té proměnné má hook přesně Pepův dosavadní tvar (jen skript),
  takže se jeho `settings.json` nemění. Příkaz hooku je `python.exe` vedle běžícího interpretu (`sys.executable`:
  `.venv\Scripts` u Pepy, `runtime\` po instalaci), stejně MCP server agenta (`pythonw.exe`) a hodnota `Run` pro
  spouštění s Windows. Vestavěný Python v instalaci nedává složku skriptu do `sys.path`, proto si ji `cc_hook.py`
  přidá sám, než naimportuje `paths`.
- Spouštění s Windows (`winutil`) bere za své jen hodnotu, která spouští **tenhle `Orbit.pyw`** (kterýkoli Python,
  přepínače, uvozovky; porovnání cest bez ohledu na velikost písmen, lomítka a 8.3, `starts_this_copy`). Když
  `Orbit` patří jiné kopii, zapíše se jako `Orbit (<složka>)`, cizí se nemaže. Co se změní, spočítá čistá funkce
  `winutil.autostart_plan` (testuje se bez registru).
- `config.json` se ukládá atomicky (`config.json.tmp` + `os.replace`). Nečitelný soubor se zkopíruje do
  `config.json.bad-<čas>` (kopie, ne přejmenování: `config.json` ve složce aplikace určuje datovou složku) a bublina
  to řekne. Hodnoty špatného typu (ruční úprava, jiná verze) se zahodí a platí výchozí, opravy se čistí
  (`vocab.clean_replacements`): jedna vadná dřív potichu shodila každý diktát.
- Zamčený `config.json` (antivir, zálohovací program) Orbit čte až 3 s (`READ_TRIES`). Když nejde přečíst ani
  zkopírovat do `.bad-*`, zapne `config.readonly`: do restartu nic neukládá a bublina řekne, ať Orbit restartuje.
  Proč: dřív výchozí hodnoty při prvním uložení přepsaly slovník (ověřeno zámkem bez sdílení). Hooky a stavový řádek
  main v tom stavu zatím odebere (do restartu chybí; oprava patří do main.py).
- Výchozí hodnoty pro nové uživatele: agent, učení slovníku a předčítání artefaktů **vypnuté** (agent by jinak hned
  zabral tlačítko myši zpět, ostatní posílají text Claudovi). Pepa je má v `config.json` výslovně, nic se mu nemění.
- `Orbit.pyw`: když start spadne (chybějící DLL, nezapisovatelná složka), zapíše `crash.log` do datové složky
  (jinak do `%TEMP%`) a ukáže okno s chybou, pythonw by jinak nic neukázal.
- `Orbit.pyw` importuje numpy s `OPENBLAS_NUM_THREADS=1` a proměnnou pak smaže (od 7. 10.). Proč: OpenBLAS jinak
  založí vlákno na každý logický procesor a commitne ~490 MB, ačkoli Orbit matice nenásobí (měřeno 499 → 17 MB
  soukromé paměti, o 15 vláken míň). Relace a programy spuštěné Orbitem mají nastavení uživatele, Piper ho dostane
  zvlášť.
- **Programy podle jména nikdy z aktuální složky**: `Orbit.pyw`, `cc_status.py` (běží ve složce relace, třeba
  v cizím repu) a `agent_tools.py` nastaví `NoDefaultCurrentDirectoryInExePath=1` (jako Claude Code), jinak
  `shutil.which('pwsh'/'git')` vrátil podstrčený `.\pwsh.CMD` (ověřeno). `claude_setup._candidates` bere jen
  absolutní cesty: z `.\claude.cmd` dřív vznikl relativní `node_modules\…\claude.exe`.
- `whisper-server` se volá přes `requests.Session` s `trust_env = False`: na 127.0.0.1 nikdy přes proxy
  z prostředí nebo nastavení Windows (zvuk nesmí odejít).

### Chyby a log (od 3. 10.)
- `main._setup_logging`: výjimka ve slotu Qt (`sys.excepthook`, Orbit běží dál), ve vlákně (`threading.excepthook`),
  „nepředatelná“ (`sys.unraisablehook`) i varování Qt (`qInstallMessageHandler`, úroveň debug) jdou do `orbit.log`.
  Úlohy vlákna přepisu jdou přes `Dictation._submit`, chyba v nich se zaloguje (ve `Future` by zmizela).
  Pád v nativním kódu (PortAudio, Qt, ovladač) zapíše `faulthandler` se zásobníky všech vláken do `crash.log`.
- Co lidé řekli, co se četlo nahlas a kam agent co poslal nebo otevřel, se loguje jen jako délky, složky a servery
  (log se může posílat při podpoře). Přepisy diktátů s textem jen se zapnutým učením slovníku (to je z logu čte).
  `ORBIT_DEBUG=1` v prostředí přepne log na úroveň debug, i s těmi texty.

### Jméno uživatele (od 3. 10.)
- `name` v `config.json`, v nastavení pole „Jméno“ (max 40 znaků, bez dvojtečky). Agent ho dostane v system promptu
  (`agent.system_prompt(name)`, staví se při startu procesu; nové jméno = nový rozhovor) a podepisuje jím zprávy.
  Prázdné = „uživatel“. Texty pro model mluví o „uživateli“ (gramaticky v pořádku pro kohokoli) a agent má pokyn
  nepoužívat tvary, které prozrazují rod („Chceš…?“ místo „Chtěl jsi…?“). Souhrny artefaktů taky.
- `about` („O mně“, jedna věta, max 200 znaků): kontext pro učení slovníku místo natvrdo zapsaných Pepových firem.
- Ukázka hlasu už jméno neříká: český vokativ („Pepo“, „Jano“, „Petře“) se z libovolného jména spolehlivě udělat nedá.
- Bez českého hlasu ve Windows (anglická Windows bez řečového balíčku) by Jakub četl česky anglickým hlasem, proto
  `voice.effective()` vezme Piper, a když žádný není, nečte se a jednou přijde bublina, jak český hlas přidat.
  Bez balíčku `piper` (GPL, build bez něj) se hlasy Piperu nenabízejí.

### První spuštění, připojení Clauda a stahování modelů (od 3. 10.)
- **Průvodce** (`onboarding.Wizard`) se ukáže, jen když v datové složce není `config.json` (Pepa ho nikdy neuvidí).
  První start hned uloží config s `wizard_pending: true`, zavření průvodce (dokončení i křížek) ho smaže: když Orbit
  spadne uprostřed, průvodce přijde znovu. Znovu ho spustí menu „Průvodce nastavením…“ a odkaz „Připojit Clauda →“
  v panelu (otevře se rovnou na stránce Claude). Stránky: Vítej (jméno, O mně) → Mikrofon a klávesa (mikrofon je
  otevřený jen na téhle stránce, signál `monitor`) → Model → Claude → Co smí Orbit → Hotovo (jak na to + pole na
  vyzkoušení). Průvodce jen sbírá hodnoty, uplatní je `Dictation._apply_values` (stejně jako Uložit v nastavení).
  Model se do hodnot dá jen ze stránky, kde byla vidět velikost. Souhlasy (a spouštění s Windows) jen když uživatel
  stránku souhlasů opustil tlačítkem **Další** (`Wizard._consented`): přepínače jsou po připojení Clauda předem
  zapnuté a zavřít okno křížkem není „ano“ (dřív to stačilo a do `settings.json` se zapsaly hooky i stavový řádek).
- **Souhlasy** v configu: `claude_hooks` (hooky Orbitu v `settings.json` Claude Code: přehled relací, artefakty)
  a `claude_statusline` (stavový řádek pro limity a přesný kontext relací, viz Limity Clauda).
  Obojí výchozí false. Hooky se přidají jen se souhlasem, jen když je Claude připojený a jen když složka Claude Code
  existuje (Orbit ji nikdy nevytváří). Bez připojení se hooky nemění vůbec (ani neodebírají) a nic se nepolluje.
  Starý config bez `claude_hooks`: true, když tahle kopie hooky už má (Pepa), jinak false (`config.missing`).
- **Co potřebuje Clauda** (limity, přehled relací, artefakty, učení slovníku, agent a jeho tlačítko myši) běží jen při
  `ClaudeConnection.connected`. Ta se zjistí při startu na pozadí (`claude --version` souběžně s `claude auth status
  --json`, medián 805 → 622 ms, bez `ANTHROPIC_API_KEY`), pak při otevření nastavení/průvodce a každých 5 minut,
  dokud připojený není. Když první kontrola za běhu skončí chybou nebo `claude.exe` chybí (pomalý start Windows,
  Claude Code se zrovna aktualizuje), zkusí se znovu za 15, 30 a 60 s (`QUICK_RECHECK_MS`), pak po 5 min;
  „nepřihlášený“ čeká rovnou 5 min. Chyba kontroly (třeba při aktualizaci Claude Code) nechá poslední dobrý stav.
  Bez Clauda panel místo prázdných pruhů ukáže „Limity uvidíš, až připojíš Claude Code. Připojit Clauda →“
  (klik = průvodce na stránce Claude).
- **Připojení = jen oficiální cesta Anthropicu** (podmínky zakazují aplikacím sbírat nebo předávat přihlášení
  Claude.ai): Orbit nikdy nechce heslo, e-mail ani token. `claude_setup.install()` pustí v **viditelném** okně
  PowerShellu oficiální `irm https://claude.ai/install.ps1 | iex` (nativní instalace do `~/.local/bin`, bez práv
  správce, sama se aktualizuje; Git for Windows je podle dokumentace jen volitelný), `login()` pustí
  `claude auth login --claudeai` (předplatné, ne Console) taky ve viditelném okně, prohlížeč otevře stránku
  Anthropicu. Orbit každé 2 s kontroluje stav, dokud není hotovo nebo se okno nezavře. Skripty jdou přes
  `-EncodedCommand` (žádné uvozovky, čeština projde). E-mail účtu se ukazuje jen v okně, do logu ne.
- Hledání `claude.exe` (`claude_setup.find_exe`, používá ho i `claude_cli.claude_exe`): npm (`%APPDATA%\npm\…`),
  nativní `~/.local/bin/claude.exe`, WinGet Links, `claude.exe` v PATH, npm s jiným prefixem; nikdy `.cmd`/`.bat`.
  `claude -p` bez přihlášení vrací „Not logged in“ → česká hláška, ať se přihlásí v nastavení.
- **Stahování** (`downloads.py`, správce `onboarding.Downloads`): modely z `huggingface.co/ggerganov/whisper.cpp`, hlasy
  z `rhasspy/piper-voices`, obojí na **pevné revizi** repozitáře a s velikostí a SHA-256 v kódu. HEAD na resolve URL
  vrací v `X-Linked-Etag` SHA-256 velkých (LFS) souborů a git SHA-1 malých (`.onnx.json`): obojí se ověří, nesoulad
  se zapsanými hodnotami stahování zastaví. Stahuje se do `<soubor>.part` (navazuje přes `Range`, CDN to umí), hash
  se počítá průběžně, na konci se ověří a teprve pak `os.replace` na skutečné jméno, takže soubor pod svým jménem je
  vždy celý. Přerušené spojení se 3× naváže samo, předem se kontroluje volné místo (+300 MB). Zrušení i ukončení
  Orbitu nechá `.part` na příště. Velikosti v UI jsou v tisících jako na Hugging Face (3,1 GB).
- **Bez modelu Orbit normálně naběhne**: `server_state` = `nomodel`, tlačítko šedé „Stahuji model… 45 %“ nebo
  červené „Chybí model“, diktát mikrofon vůbec neotevře a bublina řekne, že se model stahuje. Po stažení se Whisper
  sám spustí. Každý start serveru má číslo (`_server_gen`), výsledek staršího startu se zahodí, a
  `WhisperServer.start` pozná, že ho nový start nahradil (nejdřív `_proc = None`, pak kill), takže výměna modelu
  při načítání už nehlásí falešnou chybu.
- **Doporučení modelu** (`downloads.advise`): grafiky přes DXGI (`CreateDXGIFactory1` → `EnumAdapters1` → `GetDesc1`,
  `DedicatedVideoMemory`, bez softwarového adaptéru) a jestli jde načíst `vulkan-1.dll` ze System32. Aspoň 5,5 GiB
  vyhrazené paměti („6 GB“ karta hlásí o kousek míň) = large-v3, méně = turbo, bez grafiky s Vulkanem turbo
  a varování, že na procesoru to bude pomalé. Pepův RX 9070 XT hlásí 15,9 GiB → „16 GB“, large-v3.
- **Nastavení**: sekce „Claude“ (stav, Nainstalovat / Přihlásit se / Zkontrolovat znovu – `ui.ClaudeBox`, stejný
  jako v průvodci), přepínače, které Clauda potřebují, jsou bez něj šedé a jejich hodnoty se při Uložit nemění.
  Přehled relací a artefakty ukazují hodnotu včetně souhlasu (`show_sessions and claude_hooks`), zapnutí = souhlas.
  Seznam modelů ukazuje všechny známé („ke stažení“, „doporučeno“), pod ním řádek stahování; vybraný a nestažený
  model se po Uložit stáhne sám. Hlasy Piperu jsou v seznamu i nestažené („stáhnout 63 MB“), Poslechnout až po stažení;
  Kasandra má v tooltipu autora a licenci (CC BY 4.0 to chce, `voice.CREDITS`). V patičce verze Orbitu a „Složka
  s daty“ (otevře datovou složku v Průzkumníku: pro podporu, když data jsou v `%LOCALAPPDATA%\Orbit`).
- **Tlačítko agenta** jde v nastavení změnit („Tlačítko agenta“ pod přepínačem agenta). Zachytává ho vlastní
  dočasný hook (`main._capture_agent_key`), který se zastaví, až spolkne i puštění klávesy (`PushToTalk.released`),
  jinak by „Zpět“ došlo do prohlížeče. Agent nesmí mít klávesu diktování a naopak (odmítne se s hláškou, při shodě
  agent zůstane vypnutý). Během zachytávání klávesy diktování je hook agenta vypnutý: jako novější by stisk viděl
  první a začal poslouchat. Agent a jeho tlačítko jsou aktivní jen s připojeným Claudem; průvodce ho nabízí s tím,
  které tlačítko zabere.
- **Hlas bez Jakuba**: když Windows český hlas nemá a Piper je v Orbitu, bublina „Klikni a stáhnu hlas Jirka“
  (klik = `voice` = Jirka + stažení), jinak rada, jak češtinu přidat ve Windows. Sám od sebe se nic nestahuje.
- Tlačítko se umisťuje podle obou kruhů (`FloatingButton.button_rect`), ne podle jednoho bodu: když by trčelo z
  obrazovky (jiné rozlišení, měřítko, monitory), přitáhne se dovnitř. Totéž při odpojení monitoru nebo změně lišty
  za běhu (`_watch_screens`), tehdy se nová poloha neukládá.
- Před obnovením seznamu mikrofonů (`Pa_Terminate`) Orbit zastaví předčítání (dřív i čekal, až Piper pustí zvukovou
  kartu; od 7. 10. hraje Piper ve vlastním procesu a `release()` vrací hned True, viz Mikrofon).
- Ukončit: kusy přepisu ve frontě se zahodí (`executor.shutdown(cancel_futures=True)`) a `WhisperServer.stop` nastaví
  chybu, takže čekající `transcribe` hned skončí. Dřív Orbit po Ukončit žil neviditelně až 3 minuty a držel mutex.
- Nastavení je „vždy navrchu“; když se z něj instaluje nebo přihlašuje, tuhle vlastnost ztratí (`SetWindowPos`
  `HWND_NOTOPMOST`), jinak by zakrylo okno PowerShellu a prohlížeč. Průvodce navrchu není nikdy.
- Tažení tlačítka mikrofonu už neruší nahrávání pro agenta (tlačítko spouští jen diktát).

### Export a import slovníku (od 3. 10.)
- Pepa chtěl přenést svůj slovník na jiný počítač. V nastavení u „Slovník“ jsou tlačítka „Exportovat…“
  a „Importovat…“ (plní pole dialogu, projeví se po Uložit), v menu Orbitu (ikona u hodin i pravý klik na tlačítko)
  „Exportovat slovník…“ a „Importovat slovník…“ (import rovnou uloží; když je nastavení otevřené, jde do jeho polí,
  jinak by ho Uložit přepsalo).
- Soubor `orbit-slovnik.json`: `{"app": "Orbit", "kind": "vocabulary", "version": 1, "vocabulary": "…",
  "replacements": [[špatně, správně], …]}`. `learned_until` se nepřenáší (je to čas z logu tohoto počítače). Import
  bere i obyčejný `.txt`: co řádek (nebo čárka), to slovo, řádek „špatně → správně“ je oprava; kódování UTF-8, jinak
  ANSI (starší Poznámkový blok).
- Při importu otázka **Sloučit** (výchozí) / Nahradit / Zrušit, když už nějaký slovník je. Sloučení přeskočí slova,
  která už tam jsou (bez ohledu na velikost písmen), a opravy pro frázi, která už opravu má. Co se nevejde do 300
  znaků, se nepřidá a uživatel dostane seznam (v nastavení oranžově, z menu v okně), nic se neusekne potichu.
- Vadný soubor (jiný JSON, poškozený, novější verze, oprava v jiném tvaru) = okno s českou chybou, nic se nezmění.

## Instalátor a distribuce (od 3. 10.)

- Pepa chce Orbit dát kamarádům a později ho rozdávat ve velkém, proto jeden soubor **`Orbit-Setup-<verze>.exe`**
  (~82 MB), který funguje na čistých Windows 10 (1809+) / 11 x64 bez práv správce a bez čehokoli předinstalovaného.
  Podrobnosti stavby, verzí a ověřování jsou v `build/README.md`.
- **Stavba** (z `.venv`, poprvé stahuje MSYS2, Python, wheely a Inno Setup do `build/cache` a `build/tools`):
  ```
  .venv\Scripts\python.exe build\build_whisper.py        # jednou (a při nové verzi whisper.cpp): whisper-next\
  .venv\Scripts\python.exe build\build_installer.py --whisper-dir whisper-next [--without-piper] [--no-installer]
  ```
  Výstup `build\output\Orbit-Setup-<app/version.py>.exe`. Skript balíček zkontroluje (chybějící DLL proti čistým
  Windows, `verify_bundle.py` jeho vlastním Pythonem: importy, dialog nastavení offscreen, hlasy, hook) a teprve pak
  zavolá Inno Setup. Před vydáním zvednout `VERSION` v `app/version.py`.
- **Balíčky Pythonu jsou zamčené** (od 7. 10.): `BUNDLE_LOCK` v `build/build_installer.py` má všech 21 wheelů
  s SHA-256 (win_amd64, cp313), pip je instaluje s `--require-hashes --no-deps`. Proč: `requirements.txt` hlídá jen
  přímé závislosti, urllib3, idna, certifi, protobuf… by šly do instalátoru v té verzi, kterou PyPI zrovna má. Po
  změně `requirements.txt` build skončí s hláškou, pak `.venv\Scripts\python.exe build\build_installer.py
  --update-lock` (přepíše blok ve skriptu) a zkontrolovat git diff. Zámek ze 7. 10. dává přesně balíčky verze 1.0.0
  (stejný `licenses\python-packages.txt`), „piper“ u balíčku = jen pro Piper, `--without-piper` ho vynechá.
- `verify_bundle.py` zkouší i předčítání Piperem s balíčkem ve složce `Jiří Nový` (junction na balíček, hlas
  z `models\piper` zkopírovaný do tempu, text „.“: espeak naběhne, nic není slyšet). Verze 1.0.0 tam padala. Bez
  staženého hlasu se kontrola přeskočí.
- **whisper-server pro cizí PC** (`whisper-next/`): starý `whisper\` je přeložený pro Pepův procesor (`GGML_NATIVE`)
  a s Vulkanem jako povinnou DLL, jinde by nenaběhl. Nový: whisper.cpp 1.9.4, `GGML_BACKEND_DL` +
  `GGML_CPU_ALL_VARIANTS` (14 `ggml-cpu-*.dll`, vybere se podle procesoru), `ggml-vulkan.dll` se bez Vulkanu přeskočí
  (pak procesor). Na Pepových nahrávkách stejný text i rychlost jako starý (6/6, large-v3 i turbo). Repo `whisper\`
  zůstává starý, dokud ho Pepa nevymění (běžící Orbit ho drží otevřený).
- **Co instalátor dělá** (`installer/orbit.iss`): instalace jen pro uživatele do `%LOCALAPPDATA%\Programs\Orbit`
  (pevné `AppId`, česky, na anglických Windows anglicky): `runtime\` (Python 3.13.7 embeddable + balíčky, PySide6
  zmenšený z 640 MB na 46 MB jen na moduly, které `app\` importuje), `app\`, `Orbit.pyw`, `assets\`, `whisper\`
  (= `whisper-next`), `licenses\`, `THIRD_PARTY_NOTICES.md`; celkem ~294 MB (bez Piperu ~198 MB). Modely v něm
  nejsou, stahuje je průvodce do datové složky `%LOCALAPPDATA%\Orbit` (`paths.py`). Zástupce v nabídce Start,
  na ploše jen na přání, po instalaci „Spustit Orbit“ (ne při tiché instalaci). Aktualizace nejdřív smaže
  `runtime\Lib`, `app\`, `assets\`, `whisper\`, ať nezůstanou soubory, které nová verze nemá. Data zůstávají.
- **Aktualizace nemaže celý `runtime\`** (od 7. 10.): každá relace Claude Code spouští `runtime\python.exe` pro hooky
  a stavový řádek (stačí jim stdlib vedle něj), dřív během aktualizace selhávaly. Soubor, který běžící hook zrovna
  drží, instalátor přejmenuje na `*.orbit-old` a vedle zapíše nový (`MoveAsideIfInUse`; běžící exe a DLL smazat
  nejde, přejmenovat ano, ověřeno), jinak by tichá instalace z `install.ps1` (`/SUPPRESSMSGBOXES`) skončila na Abort.
  `restartreplace` bez práv správce nic nedělá. Zbytky smaže další aktualizace nebo odinstalace; nová menší verze
  Pythonu by tam nechala staré soubory (nepoužité). **Spuštěním instalátoru zatím neověřeno** (jen ISCC ho přeloží):
  před další verzí vyzkoušet testovací variantou `.iss` (viz Spuštění) se smyčkou, která během tiché aktualizace
  pouští `runtime\python.exe` po 100 ms; aktualizace musí skončit kódem 0 a `python.exe` tam musí být.
- **Spouští se `runtime\pythonw.exe -s Orbit.pyw`.** `runtime\python313._pth` nastaví `sys.path` jen na balíček
  a schválně **nemá `import site`**: s ním by Python přidal uživatelovo `%APPDATA%\Python\Python313\site-packages`
  (u Pepy jiný numpy a PySide6) i u spuštění, která Orbit dělá sám bez `-s` (klíč Run, hooky, stavový řádek,
  MCP server agenta). Balíček žádné `.pth` nemá, `verify_bundle.py` to hlídá a běží bez `-s`.
- **Běžící Orbit**: instalátor i odinstalátor ho poznají podle mutexu `Local\Orbit-single-instance` (stejný má
  každá kopie, takže Pepův vývojový Orbit a nainstalovaný nepoběží naráz – schválně, bojovaly by o klávesu
  a mikrofon) a řeknou, ať ho uživatel zavře.
- **Odinstalace**: nejdřív `runtime\python.exe -s Orbit.pyw --cleanup` (hooky a stavový řádek *této* instalace pryč,
  původní stavový řádek zpět, jen její hodnota v Run; jiná kopie Orbitu zůstane, viz Spuštění), pak otázka, jestli
  smazat i `%LOCALAPPDATA%\Orbit` (nastavení, slovník, nahrávky, modely); výchozí Ne, tichá odinstalace data vždy nechá.
- Tichá instalace: `Orbit-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER` (Orbit se po ní nespustí),
  odinstalace `unins000.exe /VERYSILENT /SUPPRESSMSGBOXES`.
- **Podpis**: instalátor je nepodepsaný, SmartScreen ukáže „neznámý vydavatel“. Pro rozdávání ve velkém je potřeba
  certifikát; build ho umí přes `ORBIT_SIGN_THUMBPRINT`, `ORBIT_SIGN_COMMAND` (Azure Trusted Signing) nebo
  `ORBIT_SIGN_PFX` bez hesla, podepíše whisper-server a jeho DLL, instalátor i odinstalátor. `ORBIT_SIGN_PFX`
  + `ORBIT_SIGN_PASSWORD` build odmítne (od 7. 10.): heslo by bylo v příkazové řádce signtoolu a ISCC, kterou čte
  každý proces uživatele. PFX naimportovat do `Cert:\CurrentUser\My` (`Import-PfxCertificate`, bez `-Exportable`)
  a podepisovat přes otisk.
- **Rozhodnuto 7. 10. 2026** (Pepa: „udělej to jako opensource; slib potvrzuji, nechci na tom nic vydělávat“):
  Orbit je **GPL-3.0-or-later** (`LICENSE`, v instalaci `LICENSE.txt`, úvod `THIRD_PARTY_NOTICES.md`), repozitář
  https://github.com/josefkotran/orbit je **veřejný**, Piper zůstává v instalátoru. Písemnou nabídku zdrojáků na 3 roky
  Pepa potvrdil, žádosti přes GitHub Issues. Instalátor je na webu (viz Web). Body níž jsou původní rozbor.
- **Licence – rozhodnout před rozdáváním** (podrobně `THIRD_PARTY_NOTICES.md`):
  - **Orbit sám nemá licenci** (žádný `LICENSE`), to je potřeba vyřešit i pro kamarády.
  - **Piper (piper-tts) a espeak-ng jsou GPL-3.0**: Orbit Piper načítá do svého procesu, takže build s Piperem smí
    ven jen pod licencí slučitelnou s GPL a se zdrojákem Orbitu. Jinak `--without-piper` (předčítá jen Windows hlas;
    bez českého hlasu ve Windows pak nečte nic).
  - **Hlas Jirka** je doladěný z anglického hlasu lessac, který má data Blizzard 2013 jen pro výzkum a výslovně ne
    pro komerční použití hlasové syntézy. Do placeného produktu ne, u rozdávání zdarma šedá zóna.
  - **Hlas Kasandra**: CC BY 4.0 (Ondřej Šimek, uvedený v tooltipu v nastavení), ale autor na Hugging Face prodává
    balíček „včetně licenčních podmínek“: než ho Orbit nabídne všem, zeptat se ho.
  - **Qt/PySide6 (LGPL-3.0)** a pynput (LGPL-3.0): nezměněné a vyměnitelné, texty licencí jsou v `licenses\`.
    `THIRD_PARTY_NOTICES.md` obsahuje písemnou nabídku zdrojáků na 3 roky **jménem Josefa Kotrana** – Pepa ji musí
    potvrdit, nebo zdrojové archivy vystavit vedle instalátoru.
  - Inno Setup je zdarma i komerčně, ale komerční uživatele autor žádá o koupi licence. Modely Whisper jsou MIT.
- Ověřeno 3. 10. na finálním buildu: skutečný instalátor se při běžícím Pepově Orbitu tiše ukončil (mutex, kód 1,
  nic nenainstaloval). Celé kolo pak s **testovací variantou** stejného `.iss` a stejného balíčku (jiné `AppId`,
  mutex a jména zástupců, jinak by kolidovala s běžícím Orbitem a přepsala Pepův `Orbit.lnk` v nabídce Start):
  tichá instalace do `%TEMP%` s `ORBIT_DATA_DIR`/`ORBIT_CLAUDE_DIR` na dočasných složkách; nainstalovaný
  `runtime\python.exe` bez `-s` má `sys.path` jen v instalaci, naimportuje všechny moduly a vykreslí průvodce;
  nainstalovaný whisper-server běží na grafice a přepíše Pepovu nahrávku modelem turbo; příkazy hooku a stavového
  řádku ze `settings.json` fungují tak, jak je spouští Claude Code (stavový řádek přes Git Bash ukáže původní);
  tichá odinstalace smaže složku, zástupce i položku v Odinstalovat a `--cleanup` odebral jen hooky a stavový
  řádek té instalace ve falešné složce Claude Code (cizí hook i hook Pepova checkoutu zůstaly, původní stavový
  řádek se vrátil). Pepův `settings.json`, hodnota Run a zástupci beze změny.

## Spuštění, restart, testování

- Běžící instance: procesy `pythonw.exe`, jejichž příkazová řádka obsahuje `Orbit.pyw` (přes venv launcher jsou dva).
  Restart v PowerShellu:
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ? { $_.CommandLine -like '*Orbit.pyw*' } | % { Stop-Process -Id $_.ProcessId -Force }
  Start-Process C:\Users\josef\orbit\.venv\Scripts\pythonw.exe -ArgumentList '"C:\Users\josef\orbit\Orbit.pyw"' -WorkingDirectory C:\Users\josef\orbit
  ```
  Whisper server při zabití aplikace skončí sám (Job object).
- Kontrola kódu: `.venv\Scripts\python.exe -m pyflakes app Orbit.pyw tests`.
- **Testy** (od 7. 10., stdlib `unittest`, 63 testů, ~45 s): `.venv\Scripts\python.exe -m unittest discover -s tests`
  (jen část: `-p "test_core*.py"`, `test_claude*`, `test_dist*`). Samy si nastaví `ORBIT_DATA_DIR`/`ORBIT_CLAUDE_DIR`
  na dočasné složky a uklidí po sobě. Nespouští `claude` ani whisper-server (místo něj malý server v Pythonu), klávesy
  a schránka jsou nahrazené; model Jirky čtou na místě a Piper hraje do náhradního výstupu (nic není slyšet), ISCC
  jen přeloží malý falešný balíček do tempu. `ORBIT_TEST_ROOT=<jiná kopie>` pustí testy `test_core_*` proti jiné
  verzi (porovnání před a po).
- Testy, které něco zapisují, pouštět s `ORBIT_DATA_DIR` a `ORBIT_CLAUDE_DIR` na dočasné složky (viz Datová složka),
  hook zkoušet rourou: `echo {…json…} | python app\cc_hook.py` se stejnými proměnnými, stavový řádek stejně
  (`app\cc_status.py --data <složka>`, vzorový JSON z dokumentace).
- **`Orbit.pyw --cleanup`** (od 3. 10.; odinstalátor ho spouští jako `runtime\python.exe -s Orbit.pyw --cleanup`
  a čeká): bez okna, bez Qt, bez kontroly jedné instance. Odebere hooky a stavový řádek této instalace (vrátí původní
  stavový řádek) a její hodnotu v `HKCU\…\Run` (`winutil.set_autostart(False)`: jen hodnotu, která spouští tento
  `Orbit.pyw`, `winutil.starts_this_copy`), co udělal, zapíše do `orbit.log` v datové složce (když existuje)
  a na stdout, vždy skončí 0. Záznamy jiné kopie Orbitu nechá. Testováno na dočasné kopii Orbitu s falešným
  registrem a falešnou složkou Claude Code – **nikdy nespouštět na Pepově checkoutu bez falešného `winreg`**, smazal
  by mu spouštění s Windows (jeho hodnota `Orbit` patří právě téhle kopii).
- Snímky oken: `QWidget.grab()` bez `show()` na normální platformě má skutečná písma (Segoe UI Variable), okno se
  nikde neukáže. S `QT_QPA_PLATFORM=offscreen` jsou bez `QT_QPA_FONTDIR=C:/Windows/Fonts` místo písmen čtverečky
  a i s ním jiná náhradní písma. Celý `Dictation` jde vyzkoušet jen s nahrazeným `hotkey.PushToTalk` (jinak
  globální hook spolkne klávesu), `Recorder.start/set_monitor`, `winutil.set_autostart/play`, `WhisperServer.start`
  a `downloads.download` – průvodce a stahování se tak dají projít celé bez mikrofonu a bez 3 GB.
- **Instalátor na Pepově PC** zkoušet jen tiše do dočasné složky (`/VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER
  /DIR=… /MERGETASKS="!desktopicon"`), se `ORBIT_DATA_DIR`/`ORBIT_CLAUDE_DIR` na dočasných složkách (odinstalátor
  je zdědí, `--cleanup` pak sahá jen tam) a s variantou `.iss` s jiným `AppId`, mutexem a jmény zástupců (skutečný
  instalátor by při běžícím Orbitu skončil a jinak by přepsal Pepův `Orbit.lnk`). Pak tiše `unins000.exe`.
- Nepouštět v testech `claude auth login/logout`, instalátor Claude Code ani `claude update` (mění Pepovo přihlášení
  a instalaci); `claude_setup.install(…, visible=False)` / `login(exe=<falešný .cmd>, visible=False)` zkouší jen
  spouštění.
- Testy se dělaly skripty po částech: přepis přes `WhisperServer` na vygenerované české řeči (`edge-tts`, hlasy
  `cs-CZ-AntoninNeural` / `cs-CZ-VlastaNeural`), vkládání do testovacího okna v jiném procesu, vzhled přes screenshot
  (`System.Drawing` nebo `QWidget.grab()` mimo obrazovku). **Klávesy posílat jen tehdy, když je testovací okno opravdu
  v popředí** (`GetForegroundWindow`), jinak by text skončil v Pepově okně.
- Nahrávky v `recordings/` jsou jeho skutečný hlas. Až jich bude ~30, porovnat na nich modely a nastavení (stejnou
  metodou jako FLEURS výše).
- Zástupci: `Orbit.lnk` na ploše a v nabídce Start (→ `.venv\Scripts\pythonw.exe "…\Orbit.pyw"`, ikona
  `assets\orbit.ico`). Spouštění s Windows: `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, hodnota `Orbit`.

## Na co si dát pozor

- PowerShell 5.1 `Out-File -Encoding utf8` zapisuje BOM. `config.load` proto čte `utf-8-sig`, ale soubory raději
  zapisovat z Pythonu nebo nástrojem Write.
- Úpravy Pythonu přes bash heredoc rozbíjely `\n` a `\b` v řetězcích. Pro úpravy kódu používat Edit/Write.
- Na PowerShell here-string `git commit -F -` nefunguje, zprávu dát do souboru.
- `config.json` obsahuje osobní slovník, `orbit.log` a `recordings/` obsahují přepisy a hlas. Nikdy je necommitovat
  (hlídá `.gitignore`).
- `app/cc_hook.py` spouští každá běžící relace Claude Code při každé události. Měnit ho jedním zápisem (ne po kouscích)
  a nový modul, který importuje, vytvořit dřív než ten import. Hned potom ho vyzkoušet rourou s `ORBIT_DATA_DIR`.

## Web orbit.easya.cz (od 3. 10. 2026)

- Pepa chtěl „luxusní“ stránku s vesmírným tématem a stažením instalátoru. Statická stránka v `web/site/`
  (`index.html`, `assets/site.css`, `assets/site.js`, GSAP + ScrollTrigger + Lenis v `assets/vendor/`), běží na
  Blueboardu ve složce `easya_cz/orbit` stejného FTP účtu jako m-tex.cz (hosting dělá ze složky v `easya_cz/` subdoménu,
  ověřeno: `easya_cz/easya/` = easya.easya.cz), před tím Cloudflare s wildcard DNS. Na účtu jsou i m-tex a další weby,
  proto stránka nesmí spouštět žádný kód (`.htaccess` PHP zakazuje).
- **První verzi (Bodoni Moda + Barlow, zlatá na tmavě modré) Pepa odmítl jako „AI slob“**: chtěl designérskou práci,
  jiné písmo, hodně pohybu, hover efektů a JavaScriptu. Teď: nadpisy **Anybody** (variabilní šířka 50–150, tloušťka
  100–900, jen od 48 px), text **Mona Sans**; barvy aplikace (akcent `#5B9DFF`, přepínatelný na fialovou/tyrkysovou
  tečkami v menu jako v Orbitu) na `#04060C`, žádná zlatá. Efekty: hvězdné pole na canvasu (letí podle rychlosti
  scrollu, nad hlavním tlačítkem hyperprostor, při podržení nadpisu se seřadí do hlasové vlny), písmena nadpisu
  reagují na kurzor a „hlas“, vlastní kurzor se štítky, magnetická tlačítka, pás povelů tlačený scrollem, diktát
  odvíjený scrollem (připnutý, obří obrysové hodiny), věta o soukromí rozsvěcovaná po slovech, tok paketů ve schématu,
  panel Clauda hrající scénu ke každé funkci, pravítko instalace. Vše respektuje `prefers-reduced-motion`.
- Posudek nezávislého agenta „art director“ pomohl: odhalení písmen přes vlasový řez vypadalo rozbitě (teď jen
  průhlednost + rozmazání), všechny sekce měly stejnou šablonu a tři mřížky stejných karet (teď každá jinak), Anybody
  v malých velikostech působilo jako e-sportovní písmo. Kontrola: Playwright v `scratchpad`, snímky desktop + 390 px.
- Písma jsou přímo na webu (žádné Google Fonts) a stránka nic neměří, protože slibuje „Ani tahle stránka nic neměří“.
  CSP + `Permissions-Policy: microphone=()`.
- **Úvodní video** (Remotion, viz níže) je ve `web/site/assets/video/` (`orbit.mp4`, `orbit.webm`, `poster.jpg`),
  hraje ztlumeně ve smyčce, tlačítko pustí od začátku se zvukem. Bez `orbit.mp4` (nebo s `--no-video`) je místo něj
  animovaný orrery. Hudba „Mountains“ (Andrew Ev, Mixkit) je uvedená v patičce.
- Tlačítko „Stáhnout pro Windows“ na konci videa nejde kliknout (Pepa: „je na hovno“), proto na něj v čase
  64,15–74,8 s přiletí shora skutečné tlačítko a levituje přesně nad ním (`#stageCta`; ve videu je 490×76 px se
  středem na 818, 855 v 1920×1080, velikost přes `cqw`, o kousek větší, aby to nakreslené při levitaci nevykouklo).
  Časy jsou z `video/src/scenes/Outro.tsx` (takt 33): když se konec videa přestříhá, musí se změnit
  `CTA_IN`/`CTA_OUT` v `site.js`. Se zvukem video nehraje ve smyčce: po konci skočí na záběr v 70 s, tlačítko
  zůstane a objeví se „Přehrát znovu“. Dokud není instalátor, tlačítko říká „Instalátor už brzy“ a vede na instalaci.
- **Hosting gzipuje všechno**, i video: pak nefungují rozsahy bajtů (iPhone video nepřehraje, stahování bez velikosti).
  `.htaccess` proto pro mp4/webm/exe/obrázky/písma kompresi vypíná (`no-gzip`). Cloudflare si soubory drží rok:
  zlou kopii vyřeší jen změna `?v=`, tedy `ASSET_SALT` v `publish.py`.
- Ukázka diktování na stránce je jen simulace (k mikrofonu nesahá), věrná aplikaci: červená při držení, oranžová při
  přepisu, kratší než 0,3 s se nepřepisuje. Čísla na stránce jsou změřená (FLEURS, průměr 1,6 s po puštění).
- **Instalátor**: `python web\publish.py --installer <cesta k exe>` ho nahraje jako `download/Orbit-Setup-<verze>.exe`
  a zapíše `web/release.json` (na webu i jako `download/latest.json`); stránka pak místo „Instalátor dokončujeme“
  ukáže tlačítko, verzi, velikost a SHA-256. Novou verzi = zvednout `VERSION`, sestavit, `publish.py --installer`.
- **Instalace přes Clauda / jedním příkazem** (Pepa chtěl, „aby si to mohl každý nainstalovat v Claude sám“):
  `irm https://orbit.easya.cz/install.ps1 | iex` (`web/site/install.ps1`): přečte `download/latest.json`, stáhne
  instalátor, ověří SHA-256, nainstaluje `/SILENT /CURRENTUSER` a Orbit spustí (při tiché instalaci by ho Inno
  nespustil). `ORBIT_INSTALL_DRYRUN=1` skončí po kontrole součtu. Na stránce je zadání pro Claude Code ke zkopírování:
  nejdřív si skript přečíst a říct, co udělá, pak ho spustit přes `powershell -NoProfile -Command "…"`. Soubor
  stažený skriptem nemá značku z internetu, SmartScreen se tak neozve; ochranou je kontrolní součet.
- Stránka odkazuje na GitHub (menu, instalace, otázka „Kolik Orbit stojí?“, patička).
  Bez `--installer` se nahrají jen změněné soubory stránky. Podrobnosti a FTP (FTPS přes `ftp.m-tex.cz`, heslo
  v `~/m-tex/private/ftp.netrc`, Windows curl useknul soubory) v `web/README.md`.

## Úvodní video (od 3. 10. 2026)

- Pepa chtěl „nejkrásnější Remotion video“ o Orbitu úplně nahoru na web: screeny, benefity, hudba, výzva ke stažení.
  Projekt `video/` (podrobnosti v `video/README.md`), 1920×1080, 76 s, stříhané na takty hudby.
- Vzhled sleduje web (barvy, písma Anybody + Mona Sans, „dýchající“ nadpisy z `site.js`). Když se změní web, změnit
  `video/src/lib/theme.ts`, písma v `video/public/fonts` a vyrenderovat znovu. Aplikace ve videu je replika
  `app/ui.py` v Reactu (`video/src/components/OrbitWidget.tsx`, `Bubble.tsx`); po změně vzhledu aplikace ji upravit.
  Ověřené proti skutečnému renderu z Qt (`video/capture/grab.py`, ukázková data, 3× rozlišení).
- Hudba: „Mountains“ (Andrew Ev, Mixkit, licence bez uvádění autora, nesmí se šířit samostatně, proto není v gitu).
- Video má být srozumitelné i ztlumené (na webu hraje bez zvuku), proto je všechno řečené i v obraze.
- Render: `npx remotion render Orbit out/orbit-master.mp4 --crf 14`, pak `node scripts/export-web.mjs` (2 průchody,
  MP4 ~22 MB a WebM ~19 MB, limit webu ~25 MB). Na nahrání webu je `web/publish.py`.
- **Pozor na barevný rozsah**: master z Remotionu je „full range“ (yuvj420p). Takové VP9 hardwarový dekodér Chromu na
  Pepově Radeonu odmítne (`PIPELINE_ERROR_DECODE`) a Chrome pak nepřepne na MP4, video na webu stojí (3. 10. se to
  stalo). Bez grafiky (headless) to hrálo, proto test jen s `--disable-gpu` nestačí. `export-web.mjs` proto převádí
  na „limited range“ BT.709. Kontrola: Chrome s grafikou (Playwright `headless: false`), `video.error` musí být null.

## GitHub

Repozitář **https://github.com/josefkotran/orbit**, větev `main`, **od 7. 10. 2026 veřejný** (GPL-3.0). Nic osobního
do něj nepatří: `config.json`, `orbit.log`, `recordings/`, `sessions/` a hudba videa hlídá `.gitignore`.
7. 10. vracel `git push` asi 10 minut „remote: Internal Server Error“ (i pro prázdný commit, zápis přes API přitom
fungoval, githubstatus.com hlásil vše v pořádku), pak prošel sám. Git Data API soubory nad ~50 MB nepřijme
(`ggml-vulkan.dll` má 53 MB), takže velké binárky jdou jen pushem. Vytvořen přes GitHub API s tokenem
z Git Credential Manageru (`git credential fill`, `GCM_INTERACTIVE=never`), protože `gh` chybí. Push funguje normálně.
**Přispěvatel má být jen účet `josefkotran`** (Pepa, 7. 10.): autor commitů `Josef Kotran
<235639876+josefkotran@users.noreply.github.com>` (nastavené v `git config` repozitáře; `josef.kotran@seznam.cz` patří
jinému jeho účtu `joseKot`) a **commity bez řádku `Co-Authored-By`** ani jiné zmínky o Claudovi jako autorovi. Historie
se kvůli tomu 7. 10. přepsala (záloha lokálně ve větvi `backup/before-author-rewrite`).
`whisper-server.exe` má 59 MB, GitHub jen varuje (limit 100 MB);
ve `whisper-next/` je největší `ggml-vulkan.dll` (56 MB). Výstupy buildu (`build/cache`, `tools`, `dist`, `output`)
v gitu nejsou.

## Nápady na další práci (Pepa zatím nevybral)

1. Historie posledních ~10 diktátů v menu, kliknutím znovu vložit. (Bublina u nahrávky bez řeči a „Přepsat znovu
   poslední diktát“ po selhání přepisu už jsou.)
2. Volitelná úprava textu Claudem (podržet klávesu s Ctrl, vyčistit „ten, to“ nebo udělat e-mail). Text by odcházel
   na internet, proto jen volitelně.
3. Hlasový povel „smaž to“, který vrátí poslední diktát.
4. Doladění na jeho hlas z `recordings/`.
5. Vlastní ikona pro Orbit (teď je to pořád ikona mikrofonu).
