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
artefakty a agenta vypnuté). Od 8. 10. barevná okna relací zapnutá (`tint_sessions`, noví uživatelé vypnuté) a barvy
složek `folder_colors`: hommel-portal (HHW) zelená, m-tex a mtex-portal oranžová, orbit modrá, ostatní automaticky;
zprůhlednění tlačítka `fade_after_s` 3 s (výchozí). Od 8. 10. (večer) úpravy textu hlasem zapnuté (`voice_edit`, noví
uživatelé vypnuté), historie diktátů (`keep_history`, výchozí zapnutá) a hudba při diktování úplně ztlumená
(`duck_audio: "mute"`, noví uživatelé `"keep"`). Od 9. 10. oblíbené složky pod pluskem `favorite_folders`:
hommel-portal a ondra (ty zmínil, noví uživatelé prázdné). Od 13. 10. Autopilot (`autopilot_phone`, `autopilot_key`
šifrovaný DPAPI, `autopilot_voice`, `autopilot_quiet`): dokud je Pepa v okně Autopilot nevyplní, jsou prázdné
(noční klid zapnutý). Slovník a opravy (`vocabulary`, `replacements`) doplňuje Claude, `learned_until`
je čas posledního přepisu z logu, který už Claude viděl. `name` (jméno pro agenta) a `about` („O mně“ pro učení
slovníku) přibyly 3. 10. a v jeho configu zatím nejsou, tedy prázdné: agent mu do té doby říká „uživatel“.
Souhlasy `claude_hooks` / `claude_statusline` a `wizard_pending` (taky od 3. 10.) v jeho configu nebyly: první start
nové verze dá `claude_hooks` = true, protože jeho hooky v `~/.claude/settings.json` už jsou
(`claude_settings.hooks_installed`), `claude_statusline` = false (stavový řádek nemá), `usage_source` = `"oauth"`
(limity dál z OAuth endpointu, i s řádkem Fable; od 10. 10. 5 h a týden z relací přes mod `orbit-mozek`, endpoint
jen nad tím, viz Limity Clauda) a průvodce se mu neukáže (config.json existuje). Od 24. 10. kontrola přepisu
zapnutá (`check_transcripts`) i s druhým rozpoznávačem Canary (`second_opinion`; noví uživatelé obojí vypnuté)
a vkládáním až opraveného textu (`check_first`, výchozí zapnuté, Pepa to chtěl po prvním testu), model
Canary zkopírovaný z měření do `models\canary-1b-v2` (sedí SHA-256); z oprav vyřazená chybně naučená „Naslal jsem →
Našel jsem“ (viz Učení slovníku) a stejně tak „Daytona git → Commitni a pushni“ (učení ji 24. 10. odpoledne odvodilo
z „Daytona Git, Pushnitona Git“, Pepa řekl „Dej to na git, pushni to na git“; „Pushnitona Git → Pushni to na git“
zůstala). Nahrávek se drží 1000 (dřív 30).

## Struktura

| Soubor | Co dělá |
|---|---|
| `Orbit.pyw` | vstupní bod (u Pepy přes `.venv\Scripts\pythonw.exe`, po instalaci `runtime\pythonw.exe`, bez konzole); když start spadne, okno s chybou + `crash.log`; `Orbit.pyw --cleanup` = úklid pro odinstalátor (`app/cleanup.py`) |
| `app/version.py` | `VERSION = "1.3.0"`: v patičce nastavení, v logu při startu a v názvu instalátoru |
| `app/paths.py` | kde co je: složka aplikace, datová složka, složka Claude Code (jen stdlib, importuje ho i `cc_hook.py`) |
| `app/vocab.py` | slovník a opravy: čištění, slučování se stropem 300 znaků, export a import souboru |
| `app/main.py` | třída `Dictation`: řídí stavy, Qt signály (`Bridge`) mezi vlákny, tray, menu, nastavení, polling limitů; logování a zachytávání chyb (`_setup_logging`) |
| `app/whisper_server.py` | spouští `whisper-server.exe` jako podproces (grafika, nebo jen procesor), hlídá ho a po pádu spustí znovu, přepis přes HTTP, filtry halucinací, slovník, povely |
| `app/recorder.py` | nahrávání přes sounddevice (MME, 16 kHz mono int16), detekce „zvuk opravdu teče“, prahy podle šumu mikrofonu, režim měřáku; `trim_tail` (poslední kus bez ticha za posledním slovem) |
| `app/hotkey.py` | globální push-to-talk přes pynput low-level hooky, zachytávání nové klávesy, ztracené puštění klávesy, české názvy kláves |
| `app/inserter.py` | vložení textu: schránka + Ctrl+V (se zálohou schránky), nebo psaní přes `SendInput` Unicode; okno v popředí, okna správce; mazání a označení napsaného (Backspace, Shift+←), čtení výběru (Ctrl+Insert), čekání na puštěný Ctrl/Shift |
| `app/editing.py` | co Orbit napsal naposledy (`Trail`: kdy je bezpečné to vzít zpět) a povely nad tím: „Smaž to“, „Vyber to“, „Vlož to znovu“, „Nahraď X za Y“; hledání přeslechnutého slova, rozdíly pro opravy (jen stdlib) |
| `app/history.py` | historie diktátů: `<data>/history.json`, posledních 1000, kam text šel, nahrávka, oprava, co udělala kontrola přepisu (`unchecked`, `checked`, `second`) (bez Qt) |
| `app/historyview.py` | okno Historie diktátů (ikona bubliny vedle Poznámek, menu Orbitu): kopírování jedním klikem, hledání, vložit znovu, přehrát nahrávku, přepsat znovu, opravit, smazat |
| `app/pastsessions.py` | minulé relace Claude Code jako u `claude --resume`: přepisy z `projects/*/<id>.jsonl`, název, složka, první a poslední zadání, čte jen začátek a konec přepisu a jen změněné (bez Qt) |
| `app/pastsessionsview.py` | okno Historie relací (ikona hodin vedle agenta): hledání, filtr složky, „Pokračovat v relaci“ (`claude --resume` ve složce relace, model jako naposledy nebo jiný), běžící relace = přepnutí do jejího okna |
| `app/models.py` | modely relací: názvy a rodiny (Fable, Opus, Sonnet, Haiku), výchozí model Claude Code, `--model` nové relace, žádosti o přepnutí běžící relace pro mod `orbit-mozek` a vrácení výchozího modelu (bez Qt) |
| `app/rewrite.py` | úpravy textu hlasem přes `claude -p` (Ctrl/Shift + klávesa diktování): pokyn + označený text nebo poslední diktát, Claude spuštěný už během mluvení |
| `app/ducking.py` | hudba a zvuk ostatních programů ztlumené nebo ztišené, dokud je otevřený mikrofon (Core Audio přes ctypes, vlastní vlákno, `<data>/ducked.json` pro návrat po pádu) |
| `app/ui.py` | `FloatingButton` (mikrofon + panel limitů), `Bubble` (oznámení), `StatusChip` (slovy, co se po puštění klávesy děje), `SettingsDialog` (nastavení), kreslení ikony; společné kusy nastavení a průvodce: `KeyAndMic`, `ClaudeBox`, `DownloadRow`, `scrolling` |
| `app/foldfx.py` | animace zbalení do ikonky a rozbalení (`FoldFx`: vlastní průhledné okno nad tlačítkem, propouští myš), jen se zapnutými animacemi Windows |
| `app/onboarding.py` | průvodce prvním spuštěním (`Wizard`, 6 stránek) a dva pomocníci, které používá i nastavení: `ClaudeConnection` (stav, instalace, přihlášení) a `Downloads` (stahování na pozadí) |
| `app/claude_setup.py` | Claude Code na tomhle PC (jen stdlib): kde je `claude.exe`, verze, `claude auth status --json`, oficiální instalátor a `claude auth login` ve viditelném okně, nejnovější verze na kanálu a `claude update` na pozadí |
| `app/downloads.py` | stahování modelů a hlasů z Hugging Face (navazování, kontrola SHA-256, volné místo) a doporučení modelu podle grafiky (DXGI, Vulkan) |
| `app/theme.py` | vzhled „noční signál“: barvy a tři barevné motivy, QSS, `Toggle` přepínač, `LevelWave` živá vlna, tmavý titulek přes DWM |
| `app/claude_usage.py` | limity Clauda: ze souborů stavového řádku (výchozí), nebo z interního OAuth endpointu (jen `usage_source: "oauth"`); české texty pro odpočty |
| `app/claude_settings.py` | Orbitovy záznamy v `settings.json` Claude Code: hooky a stavový řádek, jen té své instalace (podle cesty ke skriptu), atomický zápis, záloha |
| `app/cc_status.py` | stavový řádek Claude Code (jen stdlib, rychlý): zapíše limity a kontext relace do `<data>/sessions/status/<id>.json`, ukáže původní stavový řádek uživatele (nebo vlastní řádek) |
| `app/cleanup.py` | `Orbit.pyw --cleanup`: odebere hooky, stavový řádek (vrátí původní) a položku v Run této instalace, vždy skončí 0 |
| `app/claude_cli.py` | společné volání `claude -p` (bez nástrojů, na předplatném) pro učení slovníku, souhrny artefaktů, úpravy textu a kontrolu přepisu (`Prepared`: proces spuštěný dřív, než je známé zadání, zadání pak jako stream-json); `claude.exe` a prostředí bere z `claude_setup` |
| `app/learning.py` | učení slovníku: přepisy z logu + opravy uživatele (`<data>/corrections.json`) → `claude -p` → nová slova a opravy |
| `app/check.py` | kontrola přepisu: prompt pro Claude Haiku (text, druhý přepis, předchozí diktát), pojistky, že odpověď je oprava (`accept`), co se změnilo (`changes`), `Checker` spuštěný už při stisku (bez Qt) |
| `app/canary.py` | druhý rozpoznávač pro kontrolu: NVIDIA Canary-1B-v2 (onnx-asr, procesor) ve vlastním procesu s nižší prioritou (`SecondOpinion` → `_worker`), stav modelu (bez Qt) |
| `app/artifacts.py` | předčítání artefaktů: záznam od hooku → text stránky → souhrn 7 vět od Clauda |
| `app/sessions.py` | přehled relací Claude Code: stav z hook souborů, kontext ze stavového řádku (jinak odhad z přepisu), režim oprávnění, příkazy na pozadí (`shells.py`), přepnutí okna |
| `app/tasks.py` | vlastní úkoly uživatele (poznámky): `tasks.json` v datové složce, co nabídnout ke spuštění, zadání pro relaci, spuštění relace v samostatném procesu (bez Qt) |
| `app/notebook.py` | okno Poznámky: sekce Aktivní / V plánu / Poznámky / Hotovo, úkol s názvem, složkou, kontextem a poznámkami, přetahování a šipky |
| `app/favorites.py` | oblíbené složky pod pluskem nad panelem: seznam, názvy, nové repo (složka + `git init`), otevření relace v samostatném procesu (bez Qt) |
| `app/favoritesview.py` | okna „Vybrat složky a barvy…“ (přepínač a barevná tečka u každé složky) a „Nové repo…“ |
| `app/autopilot.py` | Autopilot: relace pracuje po kolech, po každém hovor na telefon, odpověď z hovoru = další kolo; stav v `<data>/autopilot.json`, zadání relaci přes mod (`<data>/sessions/prompt/`) (bez Qt) |
| `app/autopilotview.py` | okno Autopilot (ikona telefonu vlevo od plusu): číslo, klíč Bland AI, běžící relace, cíl a interval, hlášení a poslední hovor |
| `app/bland.py` | hovory přes Bland AI (`api.bland.ai/v1`): založení hovoru, výsledek a přepis, kontrola klíče; klíč šifrovaný DPAPI, telefonní čísla E.164 (jen stdlib + requests) |
| `app/colors.py` | barvy relací podle složky (jména jako `/color` v Claude Code): proužek v panelu a obarvení pozadí terminálu relace (OSC 11, jen stdlib) |
| `app/shells.py` | příkazy na pozadí relací (modré „2 shells“ v Claude Code): najde jejich procesy, pozná, jestli pracují, čekají, jsou to nepoužívané servery nebo visí; zastavení přes mod `orbit-mozek` (jen stdlib) |
| `app/cc_hook.py` | hook, který Claude Code spouští (jen stdlib, rychlý): zapíše `<data>/sessions/<id>.<událost>.json` (i `permission_mode` a okno relace) |
| `app/agent.py` | hlasový agent: trvalý `claude -p` (stream-json), přehled relací pro něj, potvrzování odeslání |
| `app/agent_tools.py` | vlastní nástroje agenta jako MCP server (stdio): nová relace, hledání a otevření stránky |
| `app/browser.py` | hledání v historii Google Chromu a otevření stránky v nové kartě (s přenesením do popředí) |
| `sessions/` | stavové soubory relací od hooku, v `sessions/artifacts/` zveřejněné artefakty, v `sessions/status/` soubory stavového řádku – nejsou v gitu |
| `cache/` | vygenerované zvuky (`*.wav`), šipka seznamů (`chevron.png`) a poslední limity z OAuth (`usage-oauth.json`), dají se kdykoli smazat – není v gitu |
| `app/config.py` | výchozí nastavení, cesty v datové složce, kontrola hodnot při načtení, atomické ukládání, popisky modelů |
| `app/winutil.py` | jedna instance (mutex), AppUserModelID, spouštění s Windows (registry), pípání a zvuky bublin |
| `whisper/` | `whisper-server.exe` a co potřebuje: od 3. 10. (commit 0f7a5c2) build pro jakékoli PC (`GGML_BACKEND_DL`, 76 MB), vedle exe `ggml-*.dll` (Vulkan a varianty CPU); Orbit umí i starý build (jeden exe s Vulkanem, 59 MB). Z něj je `whisper\` v instalátoru. Licence whisper.cpp |
| `app/voice.py` | lokální české hlasy Piper (Jirka, Kasandra) pro předčítání místo Jakuba; Piper běží ve vlastním procesu (`_worker`) |
| `models/` | `ggml-large-v3.bin` (3,1 GB), `ggml-large-v3-turbo.bin` (1,6 GB), `piper/` (hlasy Piperu), `canary-1b-v2/` (druhý rozpoznávač, 4 GB, jen když je zapnutý) – nejsou v gitu ani v instalátoru, stahují se (`downloads.py`); rozestažené jako `*.part` |
| `recordings/` | posledních 1000 nahrávek (`.wav` + `.txt` s přepisem, asi 250 MB; do 24. 10. jen 30), když je zapnuté ukládání – nejsou v gitu |
| `orbit.log` | log aplikace včetně přepisů (jen se zapnutým učením slovníku) a časů – první místo, kam se dívat; řeč agenta, předčítání a adresy jen jako délky (`ORBIT_DEBUG=1` i s texty); vedle něj `whisper-server.log` a `crash.log` (pád v nativním kódu) |
| `whisper-next/` | jen výstup `build_whisper.py` (nová verze whisper.cpp), pak nahradí `whisper\`; 13. 10. neexistovala |
| `build/` | `build_whisper.py` (whisper-server přes portable MSYS2), `build_installer.py` (balíček + Inno Setup), `verify_bundle.py` (kontrola balíčku jeho vlastním Pythonem), `eval_dictation.py` (přesnost na vlastním hlase: diktáty opravené v historii), `README.md`; `cache/`, `tools/`, `dist/`, `output/` nejsou v gitu |
| `installer/` | `orbit.iss` (Inno Setup) a texty licencí GPL/LGPL, které jdou do instalace |
| `tests/` | testy (stdlib `unittest`, od 7. 10.): `test_core_*` (přepis, Piper, klávesa, vkládání, config, povely a opravy, historie, oblíbené složky, Autopilot, kontrola přepisu, Canary a ořez ticha), `test_claude_*` (nástroje agenta, hledání programů), `test_dist_*` (build, instalátor), `test_ui_*` (potvrzování agenta, překreslování, relace, „Smaž to“ a úpravy na falešném textovém poli, plusko a jeho okna, tlačítko reproduktoru a předpověď limitu, verze a aktualizace Claude Code, hluchý mikrofon, Autopilot, zbalení a jeho animace, tlačítko za okny jiných programů, diktát do okna pod myší, kontrola přepisu na falešném textovém poli, pilulka „Přepisuji…“ vedle tlačítka); viz Spuštění |
| `THIRD_PARTY_NOTICES.md` | licence všeho, co instalátor nese nebo Orbit stahuje |
| `web/` | stránka https://orbit.easya.cz se stažením instalátoru a její vlastní statistiky návštěv (`/admin/`, PHP v `site/api`, `site/lib`, `site/admin`), `publish.py` ji sestaví a nahraje (viz `web/README.md`) |
| `video/` | úvodní video webu v Remotionu, hotové soubory jdou do `web/site/assets/video` (viz `video/README.md`) |
| `mods/` | mody pro Claude Code: `orbit-mozek` (panel `/mozek`, limity, zastavení příkazů, zadání z Autopilota) a `orbit-ukoly` (úkol z Poznámek v jeho relaci), viz `mods/README.md`; `.claude-plugin/marketplace.json` v kořeni z repozitáře dělá marketplace `orbit` |

Závislosti: PySide6, sounddevice, numpy, pynput, requests, piper-tts s onnxruntime, onnx-asr (`requirements.txt`; Piper
je volitelný, Orbit bez něj jen nenabízí hlasy Piperu; onnx-asr spouští na onnxruntime druhý rozpoznávač Canary, bez
onnxruntime se nenabízí). Venv je `.venv` (vznikl ještě ve staré
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
  s `GGML_BACKEND_DL` (od 3. 10. ve `whisper/`: `ggml-vulkan.dll` se bez Vulkanu přeskočí, `ggml-cpu-*.dll` vybere variantu
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
  „Titulky vytvořil JohnyX“ a samostatné „Děkuji / Děkujeme za pozornost / sledování“, „Titulky“, „Hudba“; od 24. 10.
  i „Děkujeme za pozornost / sledování.“ jako poslední věta za řečí (v Pepově historii 3×: dvakrát jako celý diktát,
  jednou za 21 s diktátem do Claude Code). „Děkuji za pozornost.“ za větou zůstává, e-mail tak může končit. Filtruje
  se po kusech (viz průběžný přepis), takže halucinace uprostřed nesmaže zbytek textu.
- **Bez ticha za posledním slovem** (od 24. 10., `recorder.trim_tail`): poslední kus (od posledního řezu do puštění
  a `TAIL_MS` po něm) jde Whisperu jen do 0,3 s za posledním 30ms blokem nad prahem pauzy (`max(150, 3 × šum)`).
  V tom tichu (u Pepy 0,5–0,9 s) Whisper „slyšel“ „Titulky vytvořil JohnyX“, „Děkujeme za pozornost“ nebo
  „www.hradeckralove.org“. Měřeno: na Pepových 30 nahrávkách obě takové konce zmizely, nic řečeného neubylo a pár
  slov se zlepšilo („od kým jeho“ → „od Kimiho“, „Někde to“ → „Nejde to“, „kyber bezpečnost“ → „kyberbezpečnost“);
  na FLEURS 9,26 → 9,20 % (zlepšeno 9, zhoršeno 8 vět), na VoxPopuli beze změny. Nahrávka v `recordings/` zůstává
  celá, ořez je jen pro přepis (i „Přepsat znovu“ a přepis z historie).
- **Prompt se musí vejít do 224 tokenů** (whisper.cpp jich vezme z konce `n_text_ctx/2`, zbytek začátku zahodí).
  Spočítáno Whisperovým tokenizérem (`multilingual.tiktoken`) 24. 10.: věta o diktování 40 tokenů, Pepův slovník
  296 znaků = 123 tokenů, celý prompt 170; s 150 znaky kontextu průběžného přepisu (~65 tokenů) to bylo 235 a ořízl se
  začátek věty. Proto `CONTEXT_CHARS = 100`. Čeština s diakritikou má ~2,4 znaku na token (`prozkoumej` = 5 tokenů).
- Opravy (`replacements`, „comgit“ → „Comgate“) se aplikují na celý text diktátu: celá slova, bez ohledu na velikost
  písmen; velké písmeno, které Whisper napsal, zůstane („Proskoumej to“ → „Prozkoumej to“, do 24. 10. „prozkoumej
  to“: 5 diktátů v historii začínalo malým písmenem). Pak hlasové povely.

### Průběžný přepis (`live_transcribe`, měřeno na 30 Pepových nahrávkách)
- Během držení `Recorder._cut_at_pause` odřízne hotový kus v půlce pauzy a ten se hned přepisuje. Po puštění zbývá
  jen poslední kus, text se vkládá **najednou po puštění** (Pepa nechtěl psaní během mluvení). Kusy jedné nahrávky
  jdou za sebou v jednom vlákně (`Take`); do promptu každého jde konec předchozího textu (100 znaků, viz prompt výš).
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
- **Opravy skoro nefungují dopředu** (rozbor 24. 10.): ze 105 se jich ve 377 diktátech od 8. 10. objevilo jen 44
  a jen 5 víc než jednou, protože Whisper stejné slovo komolí pokaždé jinak („sešun“, „sešen“, „sesion“, „section“,
  „sešnu“). V době diktování opravily 12 diktátů, kontrola přepisu Claudem by jich opravila 72. A nevidí kontext:
  „Naslal jsem → Našel jsem“ se 13. 10. naučila z věty „Naslal jsem Profodu, ať to pošle…“ (myšleno „Napsal“), takže
  by tu větu příště pokazila (z Pepova configu 24. 10. vyřazena, prompt učení teď říká, že fráze, která může znamenat
  víc slov, opravou není). Opravy zůstávají pro to, co se opakuje přesně stejně; zbytek dělá kontrola přepisu.
- Rozbor 105 Pepových oprav: asi třetina anglické a technické termíny psané podle výslovnosti („Kometopuš“, „kron“,
  „clode md“), pětina jména a domény („HOMEL“, „Frankenstozl“, „orbit.easia.cz“), třetina špatně slyšená česká slova
  („Otehři“, „plošťáře“, „zákaž znínka“), desetina pravopis podle výslovnosti („proskoumej“, „Pust“).

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

**Měření 24. 10.** (Pepa: „rozkoumej, jak co nejlépe vylepšit rozpoznávání češtiny“): FLEURS cs znovu (každá 4. ze
723, tedy 181 vět, 37 min), k tomu VoxPopuli cs (každý 7. ze 1123 úseků, 161 úseků, 27 min, 44 řečníků Evropského
parlamentu: spontánní řeč, různé hlasy a mikrofony, bližší „lidem“ než předčítané FLEURS). Whisper přes Orbitův
`whisper-server` s jeho parametry a promptem (bez Pepova slovníku), ostatní přes onnx-asr na procesoru, normalizace
jako výš. Párové srovnání s bootstrapem (95% interval rozdílu WER):

| Varianta | FLEURS | VoxPopuli |
|---|---|---|
| **Whisper large-v3** (Orbit) | 9,26 % | 12,65 % |
| Whisper large-v3-turbo | 10,37 % | 14,14 % |
| Parakeet-TDT-0.6B-v3 (int8) | 23,37 % | 19,83 % |
| Canary-1B-v2 (int8) | 9,38 % | – |
| Canary-1B-v2 (fp32) | 8,45 % (−0,8; interval −2,1 … +0,4) | **9,10 %** (−3,6; −6,0 … −1,8) |
| Whisper + kontrola Haiku | 6,89 % (lepší 60 vět, horší 0) | 11,53 % |
| Whisper + kontrola Sonnet | 5,18 % | – |
| **Whisper + Canary fp32 + kontrola Haiku** | **4,73 %** (lepší 89, horší 1) | 9,36 % |
| Whisper + Canary int8 + kontrola Haiku | 5,12 % | – |
| Whisper + Canary fp32 + kontrola Sonnet | 4,47 % (lepší 92, horší 3) | – |
| Whisper + Canary fp32 + Gemma 4 12B (lokálně, llama.cpp Vulkan) | 6,95 % (lepší 60, horší 10) | – |
| vždy lepší z Whisper/Canary (strop výběru) | 5,99 % | 8,33 % |

- Kde se Whisper a Canary shodnou (29 % vět FLEURS), je jen 2,5 % chyb; rozcházejí se jinde, proto druhý názor
  pomáhá. NVIDIA (arXiv 2509.14128) uvádí FLEURS cs Canary 7,86 % proti Whisperu 11,33 %, jenže Whisper bez beam
  search a promptu; s Orbitovým nastavením je náskok Canary na předčítané řeči na hraně průkaznosti, na spontánní
  řeči jasný (Whisper tam vynechává slova: 158 vynechaných proti 104).
- Věty FLEURS jsou z Wikipedie (FLoRes), jazykový model je mohl vidět: zisk kontroly na FLEURS může být nadsazený,
  VoxPopuli a Pepova historie jsou důvěryhodnější. Kontrola samotného textu na VoxPopuli: −1,1 bodu (lepší 33,
  horší 0), s Canary −3,3.
- Nedoporučeno: turbo (o 1,1–1,5 bodu horší), Parakeet v3 (int8 v onnx-asr, NVIDIA uvádí 11 %), Qwen3-ASR-cs-1.7B
  (podle autorů FLEURS 12,37 % proti jejich 12,10 % pro Whisper), české doladění Whisperu BuzzASR/czech (FLEURS 12,07 %),
  cloudové služby (zvuk nesmí ven). Lokální Gemma 4 12B jako kontrola: na Pepově hovorové češtině asi třetina zásahů
  špatně („údole“ → „URL“, „Čtyrkunech“ → „Čtvrtek“) a 3 z 30 odpovědí nesmysl, i když trvá jen 1,2 s (medián,
  52 tokenů/s) a 7,4 GB grafiky.
- Canary na grafice přes DirectML (onnxruntime-directml): enkodér istupakova na DML padá, export Masterx/canary-1b-v2-onnx
  (TorchScript) běží, ale dekodér na DML je pomalejší než na procesoru (2–5 s na větu). Proto procesor.
- Měřicí skripty a výsledky jsou v scratchpadu relace (ne v gitu); osobní měření na Pepově hlase půjde až s opravami
  v historii (`build/eval_dictation.py`).

### Kontrola přepisu (od 24. 10., `check_transcripts`, `second_opinion`; `app/check.py`, `app/canary.py`)
- Pepa: „všechno uprav jak říkáš, ať je to 10/10“. Po vložení diktátu Claude Haiku přečte jeho text (s druhým
  přepisem z Canary, předchozím diktátem do stejného místa a jménem programu) a opraví jen slova, která Whisper
  špatně slyšel; Orbit je v okně přepíše (`Dictation._checked` → `_retype`: Backspace k prvnímu rozdílu, i přes
  diktáty napsané po něm, a zbytek znovu), jen když je to bezpečné jako u „Smaž to“ (stejné okno, od vložení žádná
  klávesa ani klik uživatele, `editing.Trail`; v terminálu jen do 800 znaků a 3 řádků). **Mezerník je výjimka**
  (`hotkey.PushToTalk(on_space=…)` → `Trail.space_seen`): samotný mezerník (bez Ctrl, Alt, Shift, Win) hned za
  posledním diktátem se připíše k jeho textu a stopa pokračuje. Proč: Pepa má mezeru za textem vypnutou a píše ji
  mezi diktáty sám; při prvním skutečném testu 24. 10. tak každá oprava („Pouští“ → „Pushni“) skončila jen v bublině
  a „Smaž to“ by po mezeře taky nešlo. Tichá bublina (bez zvuku,
  `_notify(quiet=True)`) „Opraveno: čas → část. Klikni sem a vrátím původní“ (`_revert_check`). Když bezpečné není:
  text v okně zůstane, oprava jde do historie (`checked`, `Entry.best` ji pak vkládá a kopíruje) a bublina „Opravil
  bych…“ ji na klik dá do schránky. Čistě interpunkční změny se nepromítají.
- **Nejdřív kontrola, pak vložení** (`check_first`, od 24. 10., výchozí zapnuté; Pepa po prvním testu: „funguje to,
  oprava se udělá, ale chtěl bych, aby se to rovnou napsalo opravené, a ne první špatně“): když jsou oba přepisy
  hotové, `Dictation._precheck` je porovná (`check.same_words`: stejná slova bez ohledu na velikost písmen
  a interpunkci, diakritika se počítá). **Shodnou se** (u čistě řečených vět skoro vždy; v Pepově testu 3 ze 6) =
  text jde do okna hned a kontrola běží po vložení jako dřív (oprava, kterou by našla, je pak vzácná). **Liší se**
  (tam bývají chyby Whisperu) = Orbit počká na Clauda (`PRECHECK_WAIT_S` 8 s) a do okna jde rovnou opravený text
  (historie: `unchecked` = text Whisperu, tichá bublina „Opraveno: … Klikni sem a vrátím, co napsal Whisper“,
  `_tell_fixed`). Nestihne-li to Claude, jde do okna text Whisperu (`Take.late`) a oprava se přepíše po příchodu
  (`_checked`). Diktáty a povely řečené mezitím čekají za ním (`_held_takes`, `_release_held`), pořadí v okně
  zůstává. Tlačítko po dobu čekání ukazuje přepis. Bez druhého rozpoznávače se čeká na Clauda vždy.
- **Co se děje, i slovy** (od 24. 10., Pepa: oranžový mikrofon je fajn, „ale chápu, že to někomu nemusí docvaknout“):
  po puštění klávesy je vedle kruhů pilulka ve stylu panelu s měsíčkem, který obíhá svou dráhu (jako agent, když
  přemýšlí), a textem fáze (`ui.StatusChip`, `FloatingButton.set_status`, text dává `Dictation.refresh`):
  „Přepisuji…“ (Whisper a Canary), „Claude kontroluje přepis…“ (rozpoznávače se liší a čeká se na Clauda:
  `Take.asking`, signál `Bridge.asking` z `_precheck`), „Přepisuji pokyn…“ a „Claude upravuje text…“ (úpravy hlasem).
  Kontrola po vložení (rozpoznávače se shodly) ji nemá: na nic se nečeká. Ukáže se až po 300 ms (`DELAY_MS`, rychlý
  přepis by jen bliknul), na straně ke středu obrazovky, svisle na středu kruhů (i u zbalené ikonky), jde s tlačítkem
  a mizí s ním. Je pod kartou bubliny (`GAP` = ocásek bubliny, nejvýš tak široká jako bublina) a bublinu, která už
  je vidět, vrátí nad sebe (`_put_on_top`, bez aktivace): starší „Opraveno…“ nepřekryje. Okno nebere fokus ani myš.
  Barva mikrofonu se neměnila. Tooltip tlačítka a ikony v oznamovací oblasti při kontrole vysvětluje proč. Testy
  `tests/test_ui_status.py`, fáze v `tests/test_ui_check.py`. Neověřeno: jak to Pepa vidí při skutečném diktátu.
- **Rychlost:** přepis je v logu 0,5–1,6 s po puštění; kontrola (Haiku přes `claude -p`, proces spuštěný už při
  stisku klávesy, `Take.checker`) trvá 2,3–5 s, v Pepově prvním testu 2,3–5,0 s. S vypnutým `check_first` se text
  vkládá hned a oprava přijde ~3–5 s po puštění; „Odešli“ pak Enterem počká na opravu (nejvýš `CHECK_SEND_WAIT_MS`
  12 s, `_release_key`), ať odejde opravený text. Pepa „Odešli“ za 377 diktátů nepoužil.
- **Proč Haiku:** rychlejší a opatrnější. Sonnet opraví o něco víc (známé chyby 32/54 proti 23/54, FLEURS 4,47 %
  proti 4,73 %), ale „opravuje“ i to, co Pepa opravdu řekl („Založte“ → „Založ“, „Otevřu“ → „Otevři“). Claude
  dostává jen text (souhlas jako u učení slovníku, noví uživatelé vypnuté), zvuk nikdy; v logu jen počet změn
  (slova jen se zapnutým učením slovníku).
- **Kolik to stojí** (měřeno 24. 10. skutečným Orbitovým příkazem na 8 Pepových diktátech, `usage` z události
  `result`): vstup 2 060–2 380 tokenů, z toho 1 341 z mezipaměti (začátek, který přidává Claude Code) a 386–1 033
  nově do hodinové mezipaměti (system prompt se slovníkem a diktát; system prompt mezipaměť zpravidla nezasáhne);
  výstup 116–661 tokenů, z toho 0–511 přemýšlení (Haiku 5.5 bez `--effort`). Celkem ~2 400–3 000 tokenů, podle ceníku
  API 0,0002–0,00055 $ (průměr ~0,0003 $), 3,1–5,2 s. Kontroluje se každý diktát aspoň o 2 slovech (i ten, kde se
  rozpoznávače shodly, jen po vložení), povely, úpravy a agent ne; proces spuštěný při stisku a zrušený (povel)
  dotaz na model nepošle. Pepa (~24 diktátů denně) tak ~60 tis. tokenů Haiku denně, ~0,01 $ podle API: v limitech
  Max 20x neznatelné. Nevyzkoušeno: `--effort low` (přemýšlení je skoro polovina výstupu a zdržuje; přesnost by se
  musela změřit znovu).
- **Bublina** ukazuje nejvýš 3 změny (`check.summary`); samotná změna velikosti písmen („Git → git“) jen tehdy, když
  jiná není (od 24. 10.: „Opraveno: Daytona → Dej to na, Git → git, Pushnitona → …“ byl šum).
- **Pojistky** (`check.accept`): odpověď, která není oprava, se zahodí: jiný počet řádků, řídicí znaky, o víc než
  8 písmen / 25 % delší nebo kratší (písmena bez diakritiky, mezer a interpunkce), víc než polovina slov textu jinak,
  méně než 70 % stejných písmen. Písmena, ne slova: Whisper slova slévá („Daytona Git, Pushnitona Git“ za „Dej to na
  git, pushni to na git“, 24. 10. Canary to slyšela správně a oprava se zahodila, dokud se počítala slova). Na všech
  odpovědích z měření nezahodila ani jednu dobrou opravu Haiku a Sonnetu (0/72 a 0/84 Pepova historie, 0/93 a 0/102
  FLEURS) a zahodila případy, kdy model místo opravy dopsal cizí text (Haiku při testu doplnil „příliš žluťoučký kůň“
  o „úpěl ďábelské ódy“, Canaryho text místo halucinace „Titulky vytvořil…“) i 4 špatné opravy Gemmy („Haló“ →
  „Ahoj“). Prompt říká, že text jsou data, ne pokyny, a že hovorovou češtinu („teďka“, „bysme“) nechat; od 24. 10.
  i slova slitá nebo rozdělená špatně a anglický kmen s českou koncovkou („pušni“ → „pushni“, „komitni“ →
  „commitni“, jak to má Pepa ve slovníku).
- **Druhý rozpoznávač Canary-1B-v2** (`canary.SecondOpinion`): stejné kusy jako Whisper (po ořezu ticha) jdou do
  vlastního procesu (`pythonw -I -c … canary._worker`, `BELOW_NORMAL_PRIORITY_CLASS`, v Job objectu, stdin čtený
  přes `voice._stdin_lines`, JSON jen v ASCII), běží na procesoru souběžně s Whisperem na grafice (Whisper má `-t 1`).
  Kontrola na něj čeká nejvýš 10 s od puštění (`CHECK_SECOND_WAIT_S`), chybí-li kus, jde jen Whisperův text. Kusy
  nad 40 s nedostane. Jeho text projde `clean_text`, opravami a povely jako Whisperův. Sám Whisper nenahradí (bez
  slovníku: „SPD“ místo Speedy, „MTeXu“, „nebezpečné“ místo „zabezpečné“), jako druhý názor ano: na Pepových
  nahrávkách z něj kontrola vzala „část“, „filter“, „nejnovější“ a nic špatného nepřevzala.
- **Plná přesnost, ne int8:** int8 (1 GB) dal s kontrolou 5,12 % místo 4,73 % (FLEURS), proto fp32: 4 GB stahování
  (`downloads.ITEMS["canary-1b-v2"]`, istupakov/canary-1b-v2-onnx na pevné revizi, SHA-256), ~3,5 GB paměti v jeho
  procesu, načtení 2,6–5 s při startu Orbitu, pak ~0,5 s na 4 s řeči (procesor bez zátěže). Licence CC BY 4.0
  (NVIDIA): jméno a licence jsou v textu přepínače (tooltip by připojení Clauda smazalo) a v `THIRD_PARTY_NOTICES.md`.
  onnx-asr (MIT) je v `requirements.txt` a v zámku balíčků; bez onnxruntime (`--without-piper`) se nenabízí.
- Historie: `unchecked` = text před opravou v okně, `checked` = oprava, která se do okna nedostala, `second` = text
  Canary; okno Historie ukáže „Před kontrolou přepisu: …“ nebo „V okně zůstalo: …“. Data pro měření na vlastním hlase
  (`build/eval_dictation.py`).
- **Ověřeno 24. 10.:** celý řetězec se skutečným Orbitovým whisper-serverem, Canary a Claude Haiku na 7 Pepových
  nahrávkách („čas“ → „část“, „fliter“ → „filter“, „největší PHP“ → „nejnovější PHP“, „zabezpečné“ → „zabezpečené“;
  „návštěvy, ne boti“ nespravil ani jeden). Po restartu Pepova Orbitu: Canary načten za 5,1 s, bez chyb. Průběh
  v okně (oprava, vrácení, klávesa mezitím, další diktát, „Odešli“, terminál) testy `tests/test_ui_check.py` na
  falešném poli, jádro `tests/test_core_check.py`.
- **První skutečný test 24. 10. odpoledne** (Pepa: „Zatím to mluvení vypadá moc dobře. Přepsalo se to přesně“):
  kontrola běžela u každého diktátu (2,3–5 s, s Canary), u „Dej to na git, pushni to na git“ (Whisper: „Daytona Git,
  Pushnitona Git“) odpověď zahodily pojistky a „Pouští“ / „Půjšně“ → „Pushni“ se do okna nedostaly kvůli mezerníku
  (viz výš). Po opravě obou na stejných nahrávkách skutečným řetězcem: „Dej to na Git, pushni to na Git,“, „Pushni
  to na git.“, „Pushni to na git.“. **Neověřeno:** přepis opravy v živém okně (hooky injected vstup nevidí).

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
  je moc potichu“. Něco krátce nad šumem (pípnutí, klik, odkašlání) = nic neřekl, nic se neukáže.
- **Hluchý mikrofon** (od 13. 10., Pepa: „diktoval jsem, udělalo to i zvuky, ale žádný text a nic v historii“):
  13. 10. v 10:08 (9,9 s) a 10:12 (5,2 s) nahrávka se `signál: True`, ale nic nad šumem, takže potichu zahozená
  (pravidlo „jen šum = nic neřekl“). Totéž v logu 26. 9., 29. 9. (4× za sebou), 1. 10., 3. 10. a 8. 10. (agent):
  vždy SoloCast, delší nahrávka a hned potom „Haló, haló, slyšíš mě?“, které už prošlo. Ve Windows se v tu chvíli
  nic nezměnilo (Audio/Operational bez událostí, mikrofon nepoužíval žádný jiný program). Nejpravděpodobněji ztlumení
  přímo na mikrofonu (SoloCast má dotykový senzor nahoře; ztlumený posílá svůj šum, ne nuly, proto `got_signal`),
  neověřeno. Na Pepově SoloCastu přes reproduktory je ve **všech** uložených nahrávkách blok nad 50 do 0,12 s
  (zachycené startovní pípnutí), takže nahrávka, kde `DEAF_WARN_S` (2 s) nepřijde nic nad šumem (`voiced_s == 0`),
  znamená hluchý mikrofon: Orbit to řekne **už během držení** („Mikrofon nic neslyší. Není ztlumený přímo na
  mikrofonu (tlačítkem nebo dotykem) nebo ve Windows?“, jednou za nahrávku, `Take.warned_deaf`) a po puštění znovu
  („…nic nezachytil, nahrávka je jen ticho…“), obojí jako chyba (červená bublina, u agenta řádek v panelu). Text
  v historii není, protože žádný nevznikl. Řádek „Nahrávka … je ticho“ v logu má teď i nejhlasitější blok
  (`Recorder.peak`) a čas nad šumem. Testy `tests/test_ui_silence.py`.

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
- Nahrávka (`recordings/`) se ukládá až po odeslání textu do okna (od 7. 10.): zápis WAV trval 11 ms, někdy až 50 ms
  čekání navíc.
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
- **Tlačítko myši pro diktování funguje jako klik** (17. 10., Pepa: „kde mám myš, tam to [má] mluvit, musím na to
  úplně kliknout“): relace „rege“ ovládala Chrome přes Claude in Chrome (akce každých ~8 s) a Chrome se tím dostával
  do popředí; třikrát za sebou šel diktát do Chromu místo do terminálu pod myší a Pepa ho po kliknutí do terminálu
  řekl znovu (historie: chrome → WindowsTerminal). Vlastní klik tlačítka okno neaktivuje (hook ho spolkne). Proto
  s vazbou na myš (`ptt.kind == "mouse"`) `Dictation._follow_pointer` při stisku a znovu při konci nahrávky
  (`_finish_recording`, před `take.target`) dá do popředí okno pod myší (`inserter.pointed`: `WindowFromPoint` →
  `GA_ROOT`; ne hlavní panel a plocha, menu, okna bez aktivace a nástrojová okna jako Orbitovo tlačítko a bubliny,
  zakázané okno), když to není to v popředí (`sessions.focus_window`). Klávesa pro diktování nic nemění. V logu
  „Diktát jde do okna pod myší (WindowsTerminal), v popředí bylo chrome“. Když Chrome okno vezme až během přepisu,
  platí dál pravidlo výš (schránka a bublina). Testy `tests/test_ui_pointer.py`. Neověřeno: fyzickým tlačítkem myši
  v živém Orbitu.
- Po 3 s nečinnosti (stav idle, myš mimo, žádné menu) tlačítko i panel zprůhlední na 30 % (`windowOpacity`,
  animace), Pepa chtěl, aby bylo vidět „jen malinko“ (10 % i 20 % byly moc průhledné, 30 % schválil). Najetí myší, nahrávání nebo
  přepis ho hned vrátí. Od 8. 10. jde čas zvolit v nastavení („Zprůhlednit tlačítko“: 3 s, 5 s, 10 s, 30 s, minuta,
  nikdy; `fade_after_s`, 0 = nikdy, `FloatingButton.set_fade_after`).
- **Tlačítko za okny jiných programů** (17. 10., Pepa: „pole Orbit se dává za prohlížeč, se dvěma Chromy Orbit
  nevidím“): Windows tlačítko odsunuly pod obyčejná okna (Chrome, terminály) a nechaly mu `WS_EX_TOPMOST`, takže Qt
  si myslí, že je navrchu, a nic neopraví. Stejně odsunutý byl i hlavní panel druhého monitoru (Explorer, bez okna
  přes celou obrazovku), příčinu se nepodařilo zjistit ani vyvolat (`HWND_BOTTOM` příznak smaže, vložení za obyčejné
  okno Windows u topmost okna ignorují, `SetWindowLongPtr` příznak nastavit neumí). Proto `Dictation._keep_button_on_top`
  každou sekundu (`ON_TOP_CHECK_MS`): viditelné, nezakryté (cloaked) a neminimalizované obyčejné okno nad tlačítkem
  (`winutil.windows_above`, ~0,1 ms), nebo ztracený příznak (`HWND_NOTOPMOST` zvenku; Qt ho po skrytí a ukázání
  nevrátí) = `SetWindowPos(HWND_TOPMOST)` bez aktivace (`winutil.put_on_top`). Ne během hry, videa nebo prezentace
  přes celou obrazovku (`accepts_notifications`), po jejím konci se tlačítko vrátí. V logu „Tlačítko bylo za okny
  jiných programů (chrome, …)“, nejvýš jednou za minutu. Ověřeno na Pepově odsunutém tlačítku (vrátilo se) a na
  odsunutém panelu druhého monitoru (detekce), testy `tests/test_ui_on_top.py` se skutečnými okny mimo obrazovku.

### Relace Claude Code (`show_sessions`, `speak_answers`)
- Pepa pouští Claude Code přes `cmd.exe` z Průzkumníka, **každá relace má vlastní okno Windows Terminalu**
  (defterm handoff). Proces: `claude.exe ← cmd.exe ← explorer.exe`. Konzole relace je skryté `PseudoConsoleWindow`,
  jeho vlastník (`GetAncestor(..., GA_ROOTOWNER)`) je okno WT → klik na řádek přepne přesně na tu relaci.
  Titulek okna nastavuje Claude Code: téma relace se spinnerem (`◐ Katalog z Německa překlad`, `✳` = v klidu).
  Pepa má často víc relací ve stejné složce (třeba 4× `m-tex`), proto se relace jmenují podle tématu.
- Hooky v `~/.claude/settings.json` (Pepa souhlasil): SessionStart, UserPromptSubmit, Notification, Stop,
  StopFailure, SessionEnd a PostToolUse s `"matcher": "Artifact"` → `"command": "<python.exe vedle Orbitova>",
  "args": ["<absolutní cesta>/app/cc_hook.py"], "async": true` (exec forma bez shellu, u Pepy
  `C:/Users/josef/orbit/.venv/Scripts/python.exe`). Od 16. 10. i PreModelSwitch, jako jediný **bez `async`**
  (`claude_settings.SYNC_EVENTS`: Claude Code čeká na jeho odpověď; viz Model relací); u Pepy ho přidá první start
  Orbitu po té změně. Orbit je přidá (se souhlasem `claude_hooks`), když je zapnutý
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
- **Práce na pozadí není „hotovo“** (od 8. 10., Pepa: relace pustila podagenty a příkazy na pozadí, tah skončil
  a Orbit psal „hotovo“, i když pracovala dál). Stop hook Claude Code nese `background_tasks` (běžící podagenti,
  příkazy na pozadí, monitory, workflowy; přesně k rozlišení „hotovo“ a „čeká na práci na pozadí“), hook z nich
  ukládá `background` (`type`, `what`). Stop s nějakou = stav „pracuje“, žádné oznámení ani předčítání, pravidlo
  „seznam relací hlásí idle = přerušeno“ se nepoužije; tooltip řádku „Na pozadí běží: příkaz, 2× podagent“ + popisy,
  agent to má v přehledu. Práce na pozadí se relaci ohlásí a ta dělá další tah; teprve Stop bez práce na pozadí
  ohlásí „Hotovo“. Výjimka od 11. 10.: servery a visící příkazy (viz další bod) relaci ve stavu „pracuje“ nedrží.
- **Příkazy na pozadí: pracují, nebo běží zbytečně?** (od 11. 10., `app/shells.py`; Pepa: „dole modře třeba dva
  shell, ale ve skutečnosti nic nedělají“, v relaci m-tex hodinu stál náhled PHP a MariaDB a Orbit ji hodinu ukazoval
  jako „pracuje“). Hook od Stopu ukládá u každé úlohy i `id` a `command`. `shells.Watch` každých 5 s (`SAMPLE_S`,
  ~11 ms, výpis procesů ~5 ms jednou pro všechny relace) najde shell mezi dětmi `claude.exe` relace: Git Bash podle
  příkazu v `bash -c "… eval '<příkaz>' …"` (`'` je tam `'"'"'`, `"` je `\"`, `command_of` přes `CommandLineToArgvW`),
  PowerShell podle výstupního souboru v příkazové řádce `cmd /c "powershell … > …\tasks\<id>.output"` (skript je
  v proměnné prostředí). Příkazová řádka cizího procesu přes `NtQueryInformationProcess` (třída 60). Sleduje celý
  strom procesů: čas procesoru (víc než 20 ms za 5 s = něco dělá; nečinné `php -S` i `mysqld` mají 0 ms za 30 s),
  výstupní soubor (`%TEMP%\claude\<projekt>\<relace>\tasks\<id>.output`, `php -S` do něj loguje požadavky), porty, na
  kterých poslouchá, a připojené klienty (`GetExtendedTcpTable`). Verdikt (`Shell.kind`): pracuje, čeká (sleep nebo
  smyčka se sleep: skončí a relaci ohlásí), server (`server (php) na :8770, používá se` / `nikdo ho nepoužil 48
  min`), teď nic nedělá, nic nedělá (15 min, `IDLE_S`: visí, třeba `git push` čekající na heslo), proces nenalezen.
  **Nepotřebný** = nic nedělá, nebo server nepoužitý 30 min (`SERVER_IDLE_S`). Program, který nic nepíše (mysqld), je
  nečinný až od chvíle, kdy ho Orbit poprvé viděl, ne od startu. Servery a visící příkazy relaci nedrží ve stavu
  „pracuje“ (nikdy samy neskončí): Stop jen s nimi = „hotovo“ i s oznámením (`SessionTracker._look_at_shells`).
- V panelu je za názvem relace s nepotřebným příkazem oranžová ikona příkazového řádku (E756) a počet, když je jich víc;
  tooltip má u každé úlohy, co dělá. **Pravý klik na relaci** nabídne „Zastavit: <popis> (<co dělá>)“ u každého
  příkazu a „Zastavit nepotřebné (N)“. Agent to má v přehledu (zastavit sám neumí, řekne, ať pravý klik).
- **Zastavení jde přes Claude Code** (ověřeno 11. 10.): příkaz ukončený zvenku Claude Code ohlásí relaci jako
  „failed with exit code 1“ a relace začne nový tah (může ho třeba pustit znovu), kdežto `TaskStop` ji neprobudí
  (úloha „stopped“, žádný tah). Orbit proto zapíše `<data>/sessions/stop/<relace>.<úloha>.json` a mod `orbit-mozek`
  (od 0.3.0) v té relaci ho do 2 s najde, zavolá `$.tool.call({tool: 'TaskStop'})` a odpoví `….done.json`
  (`shells.Stopper`, Orbit oba soubory smaže). Ověřeno se skutečným `claude -p` (haiku) a modem 0.3.0: server
  `python -m http.server` byl rozpoznán jako server, zastaven za 1,2–2 s, procesy i port do 1 s pryč, relace bez
  nového tahu. Bez odpovědi do 6 s (relace bez modu 0.3, třeba spuštěná před aktualizací) bublina nabídne ukončení
  natvrdo (`Watch.kill`, celý strom od programu po shell, s kontrolou času startu proti recyklovaným PID).
  Zastavené úlohy si Orbit pamatuje (`Watch.stopped`): Claude Code o nich další Stop neposílá.
- **Režim oprávnění relace** (`Session.mode`, `mode_class`): z hooku (`permission_mode`), jinak z přepisu
  (`"permissionMode"` u záznamů uživatele). Třída jako u Claude Code: „bypass“ = `bypassPermissions`, nebo `plan`
  u relace, která někdy běžela v bypass (`bypass_seen`); jinak „prompting“. `sessions.bypass_in_use()` = rozhodne
  nejnovější relace se známým režimem, bez nich `skipDangerousModePermissionPrompt` / `permissions.defaultMode`
  v `settings.json` (u Pepy `true`). Tooltip relace ukáže „Běží bez ptaní na oprávnění.“
- **Pozor na automatickou aktualizaci Claude Code**: běžícímu procesu přejmenuje exe na `claude.exe.old.<číslo>`.
  Kontrola živosti proto bere jméno souboru začínající `claude.exe`. Dřív to Orbit bral jako ukončenou relaci a mazal
  její soubory, takže po aktualizaci (30. 9. i třikrát za den) byla v přehledu jen část relací.
- **Název relace** = `aiTitle` z přepisu (záznam `{"type":"ai-title","aiTitle":"Analýza ceníků a katalogů
  Profodu"}`, opakuje se v přepisu, čte se z konce; bez ai-title v posledních 512 KB se hledá od konce po 1 MB,
  `sessions._title_lines`: 1–2 ms místo 44–181 ms u přepisů 19–88 MB). Bez něj (nová relace, ještě bez zadání)
  ukazuje řádek panelu tlumeně „Nová relace“ (`ui.UNTITLED`) a složku ve vlastním sloupci jako u ostatních (od 16. 10.,
  Pepa: u nové relace s Haiku „se neukazuje složka“, když byla na místě názvu); bubliny a hlas ji dál jmenují podle
  složky (`Session.name`). Stejný text dává
  Claude Code do titulku okna. Používá se v panelu, v bublinách i v hlasu („Hotovo: …“). V panelu je za názvem
  tlumeně i složka (Pepa chtěl vidět, kde relace pracuje), proto je panel široký 440 px (s 320 px se názvy
  ořezávaly). Relace jsou seřazené podle složky a začátku relace (pořadí neskáče se změnou stavu).
- Panel relací se překreslí jen při změně toho, co řádky ukazují (`FloatingButton._sessions_look`, od 7. 10.), ikona
  a tooltip v oznamovací oblasti se nastavují jen při změně. Proč: dřív se panel překresloval každou sekundu
  (~19 ms, polovina CPU Orbitu v klidu). Co řádky ukazují, si panel pamatuje (`_sessions_shown`): tracker mění
  objekty `Session` na místě, takže porovnání se `self._sessions` vycházelo vždy stejně. Do 9. 10. tak panel
  ukazoval „hotovo“ u pracující relace a šroubovák u hotové, dokud ho nepřekreslilo něco jiného (myš, limity).
  Test to proto zkouší se stejnými objekty, ne s novými.
- **Stavy v panelu** (od 8. 10., Pepa: jen „hotovo“ a „pracuje“, poznat „na první dobrou“, ne křiklavé barvy):
  „v klidu“ (`idle`) se ukazuje jako „hotovo“ (`STATE_LABELS`, zelená tečka; vnitřní stav `idle` zůstává kvůli
  oznámením). Před stavem ikonka: u „pracuje“ kreslený šroubováček s modrou rukojetí, který se kroutí jako při
  šroubování (`ui._screwdriver`, `_work_timer` po 80 ms jen dokud nějaká relace pracuje), u „hotovo“ zelená fajfka
  (E73E). „Pracuje“ má světlý text, „hotovo“ tlumený. „Čeká na tebe“ a „chyba“ zůstaly (chtějí uživatele). Animace
  překresluje jen čtverečky 16 px se šroubováky (`_only_work_icons`/`_paint_work_icons`: pozadí panelu
  `CompositionMode_Source` + šroubovák), 0,12 ms místo ~2 ms celého panelu.
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
- Orbitovo obnovení seznamu zařízení (`Recorder`) na worker nedosáhne, proto worker před každým textem znovu načte
  zvuková zařízení (`voice._fresh_output`: `sd._terminate()` + `sd._initialize()`, ~30 ms, mezi texty nemá otevřený
  žádný stream). Bez toho by celý běh četl do reproduktorů, které byly výchozí při startu Orbitu: zapojená
  sluchátka by mlčela a po odpojení zařízení by se čísla MME posunula (jiné zařízení, nebo ticho až do restartu).
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
  nebylo slyšet nic): klik přepne `muted`, bílý reproduktor (E767) = zvuky jdou, šedý přeškrtnutý (E74F) = ticho.
  Ztlumení vypne pípání start/stop, zvuky bublin i předčítání (odpovědi i artefakty) a hned utne, co se čte.
  Bubliny se dál ukazují, souhrny artefaktů se dál dělají. Výjimka: „Přečíst znovu…“ z menu čte i ztlumeně
  (výslovná žádost). `read_artifacts` je teď jen v nastavení; jeho vypnutí utne čtený souhrn, odpověď relace ve
  frontě se přečte.
- **Od 10. 10. tlačítko reproduktoru jako každý čeká** (Pepa: „ať funguje tak, jak si každý myslí, že má“):
  - **Klik během čtení jen zastaví čtení** (`stop_reading` → `Dictation._stop_reading`: `_stop_speech`, fronta
    pryč), zvuky zůstanou zapnuté. Dřív klik během čtení Orbit ztlumil natrvalo: kdo chtěl utnout jednu odpověď,
    neslyšel pak pípání ani další odpovědi, dokud nekliknul znovu. Rozhoduje, co tlačítko ukazovalo při stisku
    (`_press_reading`), ne při puštění.
  - **Čtení ukazuje všechno**, co Orbit čte (odpovědi relací, artefakty, agent, otázky), ne jen artefakty
    (`_say_next` → `set_reading`): kruh v barvě akcentu a vlny, které rostou (E993 → E994 → E995 po 320 ms, kreslené
    od stejného místa jako E767, jinak by reproduktor poskakoval). Pod myší místo vln bílý čtvereček stop.
  - Pod myší světlejší kruh se světlým obrysem, při stisku tmavší (`setMouseTracking`, `_speaker_hover`,
    `_speaker_down`). Po kliku se hned ukáže tooltip s novým stavem („Klikni a zvuky zapneš“…). Zapnutí zvuků zazní
    tichým tónem „info“ (je slyšet, že zvuk jde), ztlumení je potichu.
  - **Pravý klik na reproduktor = jeho menu** (`speaker_menu_requested` → `Dictation._show_speaker_menu`; jinde
    v panelu dál menu Orbitu): Zastavit čtení (jen při čtení), Přečíst znovu poslední (`_last_speech`: poslední
    přečtený text kromě otázek „Mám to poslat?“ a ukázky hlasu, čte i ztlumeně), Ztlumit Orbit, Pípnout při
    nahrávání (`sounds`), Předčítat hotové odpovědi relací (`speak_answers`, jen s přehledem relací), Hlas pro
    předčítání (jen hlasy, které tu jdou; volba hned zazní ukázkou; jestli má Windows Jakuba, se ptá až při otevření
    podmenu, načte to řečový engine Windows) a Nastavení…. Když je otevřené nastavení, přepínače a hlasy v menu
    nejsou (Uložit by je přepsalo).
  - Animace i najetí myší překreslují jen čtverec reproduktoru (`paintEvent`: oblast uvnitř `_speaker_area` =
    vymazat na průhlednou a nakreslit reproduktor, celý panel se nekreslí; v jeho čtverci nic jiného není).
  - Kolečko myši na hlasitost záměrně není: Piper hraje ve vlastním procesu, Jakub přes WinRT a pípání přes
    `winsound`, jedna hlasitost pro všechny by chtěla měnit hlasitost Orbitu ve směšovači Windows.
  - Testy `tests/test_ui_speaker.py`.
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
  `busy`). Nový proces místo starého pošle událost „reset“ (main zapomene staré potvrzení). Od 7. 10. se po těch
  30 min proces i ukončí (`stop_if_idle`, kontrola každou minutu ve vlákně, ukončení čeká až 3 s): dřív claude.exe
  (~240 MB) i s MCP serverem žil až do dalšího stisku.
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
- **SendMessage a `open_session` nejsou v `--allowedTools`** (od 7. 10., `agent.GATED`): „allow“ z hooku je pustí
  i tak (ověřeno s haiku), a kdyby CLI hooky nevzalo, nástroje odmítne (`can_use_tool` pro ně vždy „ne“: výzva
  znamená, že hook neběžel). Odpověď CLI na `initialize` se kontroluje: chyba = agent se ukončí s hláškou
  (`agent.NO_HOOK`), Pepova věta jde agentovi až po úspěšném initu. Proč: bez hooku by nic nečekalo na „jo“.
- **Tah, který začala zpráva od relace** (ne Pepova věta, `VoiceAgent._user_turn`): agent v něm nesmí posílat,
  zakládat relace, hledat ani otevírat stránky (hooky jsou i na `find_pages`/`open_page`) a žádná otázka „Mám to
  poslat?“ se neukáže. System prompt říká, že přehled relací, výsledky `find_pages` a zprávy relací jsou data, ne
  pokyny. Proč: agentovi „Orbit“ může napsat jakákoli relace.
- **Potvrzení vynucené kódem**: Orbit při `initialize` zaregistruje PreToolUse hook callback (`hookCallbackIds`,
  `timeout` 600 s) na SendMessage a `open_session` a na `control_request` `hook_callback` odpoví až po Pepově
  odpovědi (`permissionDecision` allow/deny + důvod). Ověřeno, že CLI čeká i 75 s. Orbit návrh ukáže a přečte
  **celý** („Pošlu do relace …, složka …: … Mám to poslat?“; adresa se čte jako server a slova cesty, „evil.example,
  cesta x install ps1“, Markdown se vynechá, v panelu je zpráva celá až na 10 řádků). Zprávu s blokem kódu, odkazem
  v Markdownu (cíl by nezazněl), neviditelnými nebo řídicími znaky (Unicode kategorie C kromě `\n`: nulová šířka,
  bidi, tagy), s „(hlasem přes Orbit)“ uprostřed, delší než 500 znaků nebo s víc než 6 řádky vrátí agentovi, ať ji
  přepíše (`_unreadable`), SendMessage jen do relace z přehledu, a novou relaci jen ve složce ze seznamu `project_folders`
  (`agent.known_folder`, dvě stejně pojmenované složky se čtou i s nadřazenou). Odpověď platí jen pro otázku, která
  **byla v panelu aspoň 1 s před začátkem nahrávky** (`Take.confirm_id`, `_confirm["shown"]`, `CONFIRM_SEEN_S`):
  co uživatel začal říkat dřív, agent dostane jako důvod zamítnutí a zeptá se znovu. Dočtení otázky se nečeká:
  dřív platilo jen „dozněla celá“, jenže zadání nové relace (451 znaků) se čte ~35 s, Pepa si ho přečetl v panelu,
  čtení přerušil svým „jo“ a Orbit každé „jo“ zahodil (7. 10. třikrát po sobě, nová relace nešla založit).
  Odpověď (`agent.confirmation`, max 5 slov): ano jen když jsou všechna slova „ano“ nebo výplň („jo, pošli to“),
  ne když je tam ne/počkej/zruš nebo slovo na „ne…“ delší než 3 písmena („není to ono“), cokoli jiného („ano, ale
  do jiné“) = zamítne s jeho slovy jako důvodem a agent zprávu upraví. Bez odpovědi do 2 min se zahodí.
- **Co se přečte, to se pošle** (od 7. 10.): na „jo“ Orbit v odpovědi hooku vrací `updatedInput`. U SendMessage je
  zpráva prefix + přesně text, který zazněl a byl v panelu, u `open_session` známá složka + přečtené zadání, takže
  agentův původní text neodchází nikdy. Ověřeno s haiku (PostToolUse vidí upravený vstup), u vestavěného
  SendMessage jen stejnou cestou protokolu, ne odesláním do živé relace.
- Zpráva začíná „<jméno> (hlasem přes Orbit):“ (bez jména „Uživatel (hlasem přes Orbit):“), ať příjemce ví, čí jsou
  to slova (v panelu a hlasu se vynechá). `agent.without_prefix(text, jméno)` maže **jen přesný** prefix se jménem
  z nastavení nebo „Uživatel“ (od 7. 10.): dřív mazal až 60 libovolných znaků před „(hlasem přes Orbit):“, a schovaný
  pokyn před značkou tak nezazněl, ale odešel.
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
  ne když se Claude Code nejdřív zeptá na běh bez oprávnění (`skipDangerousModePermissionPrompt` chybí).
  **Minimalizuje se až po startu** (od 8. 10., `agent_tools._minimize`): konzoli spuštěnou minimalizovaně (SW 2, 6
  i 7) Windows nikdy nepředá Windows Terminalu a nechá ji ve starém okně konzole (Pepa: „otevírá to v nějakým starým
  CMD“). WT minimalizovaně ani na pozadí spustit nejde (`wt.exe` ani předání konzole SW_SHOWNOACTIVATE/SHOWNA
  neposlouchá, přepínač nemá). Proto normální start (okno jako u jeho relací) a okno (`AttachConsole` → `GA_ROOTOWNER`)
  se minimalizuje, jakmile se ukáže (~0,1 s). WT ho ještě 1–2× obnoví a po ~0,35 s ho aktivuje i minimalizované
  (psaní by šlo do skryté relace), proto smyčka hlídá, dokud 1,5 s nezůstane dole a mimo fokus, a fokus vrací do okna,
  kde uživatel byl (`sessions.focus_window`). Měřeno: okno vidět ~0,2 s, fokus pryč celkem ~0,1 s. Cesta ke
  `claude.exe` i zadání jdou do `cmd.exe /s /v:on /k` jen jako proměnné (`!ORBIT_CLAUDE!`, `!ORBIT_TASK!`),
  složka jako pracovní adresář: nic z nich nejde spustit jako příkaz (ověřeno s `& | > ^ % !VAR! "`). Zadání vždy
  začíná prefixem se jménem (MCP server ho dostane v `ORBIT_USER_NAME`), takže nikdy nezačne „-“ jako přepínač.
  Síťové složky (`\\server\…`) odmítne (cmd by začal v `C:\Windows`). `cmd.exe` se spouští plnou cestou ze System32.
- **Prostředí nové relace = uživatelovo** (od 8. 10., `agent_tools._user_environment`, `CreateEnvironmentBlock`
  z registru, jako program spuštěný z plochy; bez `ANTHROPIC_API_KEY`). Proč: MCP server dědí prostředí agentova
  `claude.exe` a ten svým nástrojům dává `NO_COLOR=1`, `CLAUDE_PROJECT_DIR` (jeho prázdná složka), `GCM_INTERACTIVE=never`,
  `GIT_TERMINAL_PROMPT=0`, `GIT_EDITOR=true`, `PSEXECUTIONPOLICYPREFERENCE`…: relace od agenta byla celá bílá (Pepa:
  „všechno bílý, není tam žádná barva“) a git by se v ní nezeptal na přihlášení. Ověřeno porovnáním s relací
  z Průzkumníka (liší se jen proměnné, které si nastaví Claude Code a Průzkumník sám).
- **Poslední screenshot k zadání** (od 8. 10., parametr `screenshot` u `open_session`): Pepa chtěl „vlož tam
  nejnovější screenshot“ (navrhoval Alt+V). Alt+V by chtělo okno relace v popředí a klávesy do něj (relace běží
  minimalizovaná), proto Orbit k zadání připíše „Přiložený snímek obrazovky: <cesta>“ a relace si obrázek otevře sama
  (Read; ověřeno s haiku, i s diakritikou a mezerami a mimo složku projektu). Snímek vybírá Orbit, ne agent:
  nejnovější `.png/.jpg` ve složce Snímky obrazovky (`FOLDERID_Screenshots`, kam ukládají Výstřižky a Win+PrtScn;
  `agent.latest_screenshot`), v otázce zazní jeho čas („A přiložím poslední snímek obrazovky z 8:35.“), do
  `updatedInput` jde jeho cesta a `agent_tools` přiloží jen soubor přímo v té složce (`agent.is_screenshot`).
  Ke zprávě do běžící relace (SendMessage) přiložit nejde, agent to řekne. Schránka se nečte.
- **Pojistka v `agent_tools.open_session`** (od 7. 10.): MCP server už jen neprovede, co pustí hook, sám kontroluje:
  relaci otevře jen ve složce ze seznamu (`agent.known_folder`, ta je i pracovní složkou) a ze zadání ubere jen přesný
  prefix „<jméno> (hlasem přes Orbit):“ nebo „Uživatel (…)“ a vrátí ho jednou. Odmítne zadání s dalším
  „(hlasem přes Orbit)“ kdekoli (`without_prefix` by text před ním při čtení vynechal: útok = příkaz před značkou),
  odkaz v Markdownu `[text](adresa)` (adresa se nečte) a neviditelné znaky (kategorie Unicode C: řídicí, nulové
  šířky, bidi, tag znaky U+E00xx). Odmítnutí přijde agentovi až po „jo“ jako chyba nástroje; hlavní kontrola je
  od 7. 10. i v `main._ask_confirm` ještě před otázkou (platí i pro SendMessage, který `agent_tools` nechrání).

### Barvy relací (od 8. 10., `app/colors.py`)
- Pepa chtěl každou relaci „v jiné barvě“ a stejně v panelu: HHW zeleně, M-tex oranžově, Orbit modře. Barva patří
  složce (`colors.key` = jméno složky malými písmeny). Volba uživatele je v `folder_colors` (pravý klik na relaci
  v panelu → „Barva složky …“, v menu i celé menu Orbitu), ostatní složky dostanou stálou barvu ze zbylých (podle CRC
  jména, nikdy červenou: ta je u Orbitu chyba a poslech). Jména barev jsou jako `/color` v Claude Code (red, blue,
  green, yellow, purple, orange, pink, cyan).
- Panel: proužek vlevo u relace a název složky v její barvě. Okno relace (`tint_sessions`, v nastavení „Barevná okna
  relací“): pozadí terminálu tmavý odstín barvy (`colors.shade`, 15 % barvy do `#0C0C0C`) přes **OSC 11** zapsané do
  konzole `claude.exe` (`AttachConsole` + `CONOUT$`). Ověřeno: Windows Terminal ho vezme od jiného procesu, obarví celé
  okno i lištu karty a Claude Code ho nepřepíše. Jen okno, jehož konzole má viditelného vlastníka (WT, klasická
  konzole), terminál v IDE ne. Zápis dělá malý proces `pythonw -I -c … colors._main` (`colors.tint_sessions`): Orbit
  sám se ke konzoli nepřipojuje, jinak by ji zdědilo, co zrovna spouští. Orbit obarví každou relaci jednou na barvu
  (`Dictation._tinted`, PID → barva), novou do sekundy, po restartu Orbitu všechny znovu; vypnutí (nebo vypnutý
  přehled relací) vrátí pozadí OSC 111. Hook se kvůli tomu neměnil.
- Barvu lišty zadávání v Claude Code (`/color`) zvenku nastavit nejde: umí to jen control protokol SDK (`set_color`)
  a ručně `/color` (ukládá se do přepisu jako `{"type":"agent-color"}`), obyčejná relace v terminálu ho nemá.

### Poznámky a úkoly (od 8. 10., `app/tasks.py`, `app/notebook.py`)
- Pepa chtěl ikonku prázdného sešitu vlevo nad „Claude“ a v ní vlastní úkoly s kontextem a poznámkami, které přesouvá
  do „Aktivní“ nebo „V plánu“ a řadí nahoru a dolů; aktivní má „bot každou půlhodinu čekovat“ a nový začít v nové
  relaci ve správné složce, po jeho schválení.
- Panel: kruh se sešitem (kroužková vazba, prázdný) ve stejném pruhu jako tečky barev, u levého konce panelu, číslo =
  počet aktivních (`FloatingButton._paint_notes_chip`, `notes_clicked`). Okno `Notebook` (QDialog `#notebook`, styly
  v `theme.stylesheet`): vlevo strom sekcí (Aktivní, V plánu, Poznámky, Hotovo sbalené), přetažení přesouvá i mezi
  sekcemi (`_Tree.dropEvent` → `_dropped` přečte pořadí ze stromu), šipky ↑↓; vpravo název, stav (4 tlačítka),
  složka (seznam `agent.project_folders`), kontext, poznámky s časem (Enter přidá, pravý klik smaže), „Začít teď“,
  „Smazat úkol“. Všechno se ukládá hned (psaní po 0,5 s) do `<data>/tasks.json` (atomicky; nečitelný soubor se
  zkopíruje do `tasks.json.bad-*`). Pořadí v souboru = pořadí v sekci.
- Kontrola (`Dictation._check_tasks`, `tasks_timer`: 2 min po startu Orbitu, pak každých 30 min; po založení nebo
  odmítnutí úkolu další za minutu, nezodpovězená otázka znovu za 10 min, `tasks.FIRST_CHECK_MS`/`NEXT_SOON_MS`/
  `RETRY_MS`; dřív jen po 30 min od startu, takže restart Orbitu i nezodpovězená otázka odsunuly úkol o půl hodiny
  a Pepa si 8. 10. stěžoval, že se aktivní úkol vůbec nezačal dělat): první aktivní úkol se složkou,
  který ještě neběžel a nebyl odmítnut (`tasks.next_to_offer`). Otázka jako u agenta: řádek v panelu „→ Úkol: …“,
  bublina („Klikni sem a začnu“) a hlas („Aktivní úkol: … Otevřu pro něj novou relaci ve složce … Mám?“). Odpověď
  kliknutím na bublinu nebo „jo“ přes tlačítko agenta (`_confirm` s `kind: "task"`, stejné `CONFIRM_SEEN_S`
  a vypršení po 2 min; agentovo potvrzení ani konec agenta otázku úkolu neruší chybně, `_drop_confirm`). „Ne“ =
  `declined`, sám se už nenabídne (jen „Začít teď“, nebo přesun jinam a zpátky do Aktivních); jiná věta jde agentovi.
- Spuštění (`tasks.start_session`): `python -I -c …` → `agent_tools.open_session(folder, prompt,
  source="úkol z poznámek Orbitu")` ve vlastním procesu (minimalizace se připojuje ke konzoli, Orbitův proces nesmí),
  čeká i na minimalizaci, výsledek JSONem (~2 s). První zpráva: „Pepa (úkol z poznámek Orbitu): Úkol: … Kontext: …
  Poznámky: 9:30 … | …“ (`tasks.prompt_for`: odkaz v Markdownu jako „text (adresa)“, bez neviditelných znaků;
  nad 6000 znaků jde celé zadání do `<data>/tasks/<id>.md` a zpráva na něj odkáže). Úspěch = `started` a úkol jde
  **rovnou do Hotovo** (Pepa 8. 10.: když na něm už pracuje relace, má z Aktivních zmizet; starší spuštěné přesune
  `tasks.settle_started` při startu Orbitu). Přesun zpět do Aktivních vynuluje `started` i `declined`: nabídne se
  znovu. „Hotovo“ v `tasks.json` tak neznamená dokončeno, to si mod `orbit-ukoly` drží sám (`isReported`). Ověřeno
  s falešným `claude.exe` (kopie `timeout.exe`) v dočasné složce Claude Code: okno ve WT, minimalizované, správné
  zadání; špatná složka = česká chyba.
- **Zprávy od relace úkolu** (od 8. 10.): relace dostane v prostředí `ORBIT_TASK_ID` a `ORBIT_TASK_DATA` (datová
  složka; `agent_tools.open_session(task_id=…)`, jen hex id). Mod `orbit-ukoly` z ní píše do `<data>/tasks/inbox/`
  po jednom JSONu na zprávu, Orbit je každé 3 s převezme (`Dictation._check_inbox` → `tasks.read_inbox`/`apply_inbox`):
  poznámka (od Clauda s „Claude:“ na začátku, max 2000 znaků, bez neviditelných znaků), „done“ = Hotovo a bublina
  „Hotovo: …“ (klik otevře Poznámky). Neúplný soubor (mod zrovna píše) počká 10 s, pak se zahodí; zpráva k úkolu,
  který už není, se zahodí. `tasks.json` dál zapisuje jen Orbit (drží úkoly v paměti a celý soubor přepisuje).
- **Všude, kde se Orbit ukazuje** (Pepa 8. 10.: „aby byla zmíněná a zahrnutá konzistentně“): v menu Orbitu je
  „Poznámky…“ (bez panelu by na sešit jinak nebylo kde kliknout), průvodce je zmiňuje na stránce Claude i v „Hotovo“,
  instalátor v popisu zástupce a v otázce na smazání dat (`tasks.json` je v datové složce), `verify_bundle.py`
  otevře okno Poznámek a zkusí uložit a načíst úkol. Web, README a video viz jejich sekce. Texty pro všechny bez
  rodu („Spuštění bylo odmítnuto“, ne „jsi odmítl“). Když se funkce změní, opravit i tyhle popisy.

### Oblíbené složky a nová relace (od 9. 10., `app/favorites.py`, `app/favoritesview.py`)
- Pepa chtěl plusko vedle ikony historie: v něm oblíbená repa (třeba ondra, hommel-portal), klik = nová relace Claude
  Code v té složce „rovnou v tom dobrém cmd“, ať nemusí psát `cd ondra` a `claude`; složky si vybírá sám a nová repa
  zakládá tamtéž.
- Panel: kruh s „+“ (E710) vlevo od hodin historie (`FloatingButton._new_center`), jen s připojeným Claudem. Klik
  (`new_session_clicked`) otevře nabídku směrem od panelu (nahoru, když je pruh nad panelem): nadpis, oblíbené složky
  podle jména s tečkou v barvě složky (`colors.color_for`, stejně jako proužek relací), tooltip celá cesta, složky,
  které už neexistují, se vynechají; dole „Nové repo…“ a „Vybrat složky a barvy…“. Stejná nabídka je v menu Orbitu
  jako „Nová relace Claude Code“ (bez panelu by nebylo kde kliknout; plní se při otevření,
  `Dictation._fill_favorites`). Bez Clauda jen „Připojit Clauda…“.
- `favorite_folders` v configu = celé cesty (`favorites.clean`: každá jednou bez ohledu na velikost písmen, jen
  absolutní). „Vybrat složky a barvy…“ (`FavoritesDialog`): oblíbené nahoře, pod nimi „Další složky, ve kterých běžel
  Claude Code“ (`agent.project_folders`), u každé přepínač, „Přidat složku…“ vezme kteroukoli místní (síťovou odmítne).
- **Barva složky** (Pepa chtěl měnit barvu i tady): klik na tečku v okně, nebo pravý klik na složku v nabídce plusku
  (`ui.FolderMenu`: položka se složkou v `data()` pravým klikem nespustí relaci). Barvy se otevřou **nad** nabídkou
  plusku (`QMenu(owner)`), ta zůstane otevřená a po výběru se překreslí s novou tečkou. První verze nabídku plusku
  zavřela a barvy otevřela samostatně: Qt na Windows takovou nabídku hned zavřel (otevřená ještě během zpracování
  pravého kliku), barvy se vůbec neukázaly (Pepa 9. 10.). Offscreen se to nestane, ověřeno přes skutečná okna
  (`QTest` na `windowHandle()`). Je to tatáž `folder_colors` jako pravý klik na relaci v panelu (společné `ui.fill_color_menu`), platí hned
  (`Dictation._set_folder_color`: panel, obarvení oken relací, tečky otevřeného okna `set_colors`), nečeká na Uložit.
  Barva patří jménu složky, dvě složky „web“ ji sdílejí.
- „Nové repo…“ (`NewRepoDialog`): název (Windows ho musí vzít: bez `<>:"/\|?*`, tečky na konci, CON/NUL/COM1…,
  `favorites.name_problem`), kde (výchozí složka, ve které je nejvíc oblíbených, `default_parent`, u Pepy
  `C:\Users\josef`), přepínač git (`git init`, bez gitu šedý). Existující složku nezaloží. Po založení ji přidá do
  oblíbených a hned v ní otevře relaci; když `git init` selže, složka zůstane a bublina to řekne.
- Otevření: `favorites.start_session` → `python -I -c` → `agent_tools.open_folder` (samostatný proces, protože se
  připojuje ke konzoli nové relace; Orbitův proces nesmí). Spouští se stejně jako relace agenta (`agent_tools._launch`:
  `cmd.exe /k` s `claude.exe` jako proměnnou, prostředí uživatele, `--dangerously-skip-permissions` jen když ho jeho
  relace používají), bez zadání a neminimalizovaně. Na rozdíl od `open_session` bere kteroukoli místní složku: vybral
  ji uživatel svým klikem, agent na `open_folder` nedosáhne (není v `TOOLS`). `_bring_up` okno počká (~0,13 s) a když
  není vepředu, přenese ho (nejvýš 3×, ať klik jinam vyhraje). Ověřeno 9. 10. s `timeout.exe` místo Clauda: okno
  Windows Terminalu (`CASCADIA_HOSTING_WINDOW_CLASS`) bylo vepředu samo. Chyba = bublina „Relace ve složce … se
  neotevřela“.
- Neudělané (Pepa nežádal): zmínka v průvodci, na webu, v README a ve videu (u Poznámek to Pepa chtěl všude).

### Historie relací (od 10. 10., `app/pastsessions.py`, `app/pastsessionsview.py`)
- Pepa chtěl pod ikonou hodin (mezi pluskem a agentem) místo Historie diktátů „Historii sessions“: najít svou minulou
  relaci a pokračovat v ní jako s `claude --resume`. Ikona (`FloatingButton.sessions_history_clicked`) je jen
  s připojeným Claudem (jako plusko), v menu Orbitu je „Historie relací…“, Historie diktátů zůstala jen v menu.
- Zdroj = přepisy Claude Code `projects/*/<id>.jsonl` (u Pepy ~150 relací, 3 GB, Claude Code je maže po
  `cleanupPeriodDays`, výchozí 30 dní). Neoficiální formát jako u přehledu relací. Název jako ve výběru `/resume`
  (zjištěno z `claude.exe` 2.1.296): `custom-title` (`/rename`) > `ai-title` > `summary` > první zadání. Vynechá se
  to, co vynechává i Claude Code: `entrypoint` `sdk-…` (agent Orbitu, učení slovníku, skripty), podagenti
  (`isSidechain`), relace bez jediného zadání a relace s `continued-in` na přepis, který existuje.
- Zadání = záznam `user` od člověka (`origin.kind` human nebo chybí, ne `isMeta`, ne `isCompactSummary`, ne výsledek
  nástroje, ne text začínající `<`: oznámení úkolů, zprávy jiných relací, `<local-command…>`); příkaz jako „/loop 5m …“.
  Poslední zadání = nejnovější takový záznam. Záznam `last-prompt` jen jako záloha: Claude Code ho při odchodu
  z relace znovu zapíše na konec a bývá v něm pak první zadání (viděno v Pepově přepisu). Počet zadání =
  `turnPosition.promptIndex` z konce (sedí na ±1).
- Rychlost: čte se začátek (bloky 256 kB, nejvýš 4 MB: na začátku bývá `CLAUDE.md` jako attachment) a konec pozpátku
  (nejvýš 8 MB, dokud není název, poslední zadání a větev). `Index` drží výsledek podle velikosti a mtime; přepis,
  který jen narostl, má znovu čtený jen konec. Na Pepových datech první načtení 1,4–1,5 s (ve vlákně okna), další 4 ms.
  Okno čte znovu každých 5 s, jen když je otevřené, a seznam překreslí jen při změně.
- Okno: vlevo hledání (všechna slova, bez diakritiky, i v zadáních, cestě, větvi a id), filtr složky („m-tex (90)“),
  řádky s proužkem a složkou v barvě složky (`colors.color_for`, jako panel) a „běží“ zeleně
  (`sessions.running_ids`, seznam relací Claude Code). Vpravo název, cesta, větev, kdy začala a naposledy, počet
  zadání, první a poslední zadání (stejné = jen „Zadání“), „Pokračovat v relaci“ (i dvojklik a Enter), „Kopírovat
  příkaz“ (`claude --resume <id>`), „Otevřít složku“.
- Pokračování: `favorites.start_session(cwd, resume=id)` → `agent_tools.resume_folder` (samostatný proces jako u
  plusku, `_launch(..., resume=id)`: `--resume "!ORBIT_RESUME!"`, id jen jako proměnná a jen tvaru UUID, složka =
  `cwd` z prvního záznamu přepisu, kde relace začala). Není nástroj agenta. Běžící relace se znovu neotevře: okno do
  popředí (`sessions.focus`, když ji zná přehled relací), jinak hláška v okně. Chyba = bublina „Relace ve složce …
  se neotevřela“ (třeba smazaná složka). Ověřeno skutečným `cmd.exe` s falešným `claude.bat`: dostal přesně
  `--dangerously-skip-permissions --resume "<id>"`. Neověřeno: skutečné `claude --resume` z Orbitu.

### Model relací (od 16. 10., `app/models.py`)
- Pepa chtěl „strašně jednoduše měnit modely jednotlivých session“, třeba při otevření zvolit Sonnet, Opus nebo
  Haiku. Nabízí se Fable, Opus, Sonnet, Haiku (`models.FAMILIES`, aliasy Claude Code 2.1.301: `fable` = Fable 5.1,
  `opus` = Opus 5.5, `sonnet` = Sonnet 5.5, `haiku` = Haiku 5.5; všechny mají nativně kontext 1 mil., velikost
  kontextu přepnutí neomezuje). Výchozí model = `model` v uživatelském `settings.json` (u Pepy `opus[1m]`,
  `models.default`). Volba téže rodiny jako výchozí dá přesně výchozí řetězec (Opus = `opus[1m]`, `models.alias`).
- **Přesné názvy všude** (Pepa 16. 10.: „ať je tam přesný název, třeba Sonnet 5.5, nejenom Sonnet“): v přepínači
  plusku, nabídce relace, řádku panelu, Historii relací i bublinách „Fable 5.1 / Opus 5.5 / Sonnet 5.5 / Haiku 5.5“.
  Na co alias ukazuje, řekne Claude Code sám: `claude -p --input-format stream-json` a jen `control_request`
  `initialize` (bez zprávy modelu, `--no-session-persistence`, ~0,8 s), v odpovědi `models` je
  `{value: "sonnet", resolvedModel: "claude-sonnet-5-5", displayName: "Sonnet 5.5"}` (totéž, co SDK vrací jako
  `supportedModels`). `models.refresh_names` se ptá po každé kontrole připojení Clauda (`Dictation._claude_changed`,
  ve vlákně), ale jen jednou na verzi Claude Code; výsledek je v `<data>/cache/models.json` (čte ho i podproces, který
  spouští relace). Než odpověď přijde, ukazuje se jen rodina („Sonnet“). U běžící relace je název z přepisu
  (`claude-sonnet-5-5` → „Sonnet 5.5“, `models.label`).
- **Při otevření**: nahoře v nabídce plusku (i v menu Orbitu „Nová relace Claude Code“) přepínač „Model Fable Opus
  Sonnet Haiku“ (`ui.ModelPicker` v `QWidgetAction`: klik vybere, nabídka zůstane otevřená). Při každém otevření
  nabídky je vybraný výchozí model (volba se nepamatuje, aby další relace omylem nejela na Haiku); překreslení po
  změně barvy složky volbu nechá (`keep_model`). Výchozí = žádné `--model` (relace jako z Průzkumníka), jiný =
  `--model "!ORBIT_MODEL!"` (`agent_tools._launch`, jen alias z `models.is_alias`, jako proměnná). Platí i pro
  „Nové repo…“. V Historii relací vedle „Pokračovat v relaci“ seznam „Model jako naposledy“ (Claude Code při
  `--resume` vrátí model relace) / Fable / Opus / Sonnet / Haiku, „Kopírovat příkaz“ přidá `--model`.
- **Běžící relace**: pravý klik na relaci v panelu → „Model: Opus 5.5“ a čtyři modely, fajfka u toho, na čem běží
  (tooltip: k čemu je, a že další zpráva znovu načte celou konverzaci bez mezipaměti, s počtem tokenů). V řádku
  panelu je za názvem tlumeně model jen tehdy, když není výchozí („Haiku“, `ui.model_tag`), při přepínání v barvě
  akcentu „→ Sonnet“; tooltip vždy „Model: …“. Model relace = z konce přepisu poslední odpověď hlavní větve
  (`"message":{"model":"claude-opus-5-5"`) nebo novější `<local-command-stdout>Set model to `Sonnet 5.5``
  (`sessions._model`), před první odpovědí `model` z hooku SessionStart.
- **Jak se přepne**: Orbit zapíše `<data>/sessions/model/<relace>.<id>.json` (`{session_id, id, time, model,
  default}`, `models.ask`), mod `orbit-mozek` 0.5.0 (viz Mody) ho do 2 s převezme (`.ack.json`), spustí v relaci
  `$.command.run({command: 'model', args})` (= `/model sonnet`, u pracující relace až po tahu) a odpoví `.done.json`
  (`{ok, text, model}`, ok = relace teď běží na té rodině). Proč vlastní `/model` Claude Code, ne přepis modelu
  v každém požadavku (`turn.step` v modu by to uměl): relace pak ví, na čem běží (patička, `/model`, podagenti,
  kontextové okno).
- Co `/model` dělá navíc (zjištěno 16. 10. z kódu `claude.exe` 2.1.301 a vyzkoušeno na skutečné relaci s Haiku):
  1. V relaci, která už odpověděla, se v jejím okně zeptá „Switch model? … the full history gets re-read“ a čeká
     na Enter (snímek okna). Přeskočí to jen hook PreModelSwitch s `permissionDecision: "allow"` (`skipConfirm`).
     Proto `cc_hook.py` u PreModelSwitch (synchronní, nic nezapisuje, stavy relací se nemění) řekne allow **jen**
     když v `sessions/model/` je žádost Orbitu pro tu relaci a přesně ten `requested_model`, mladší než 10 min
     (`models.ASK_FRESH_S`); jinak mlčí a Claude Code se ptá jako vždy. Pomalý hook by přepnutí zablokoval
     (timeout = blokace), proto nic pomalého, vždy kód 0. Bez hooku (bez souhlasu `claude_hooks`) relace dialog
     ukáže a Orbit po 5 s v klidu bublinou řekne, ať to potvrdí v jejím okně; „No, go back“ (`Kept model as…`)
     je uživatelova volba, bez bubliny.
  2. **Uloží model i jako výchozí pro nové relace** (`settings.json` `model`; lokálně `/model <název>` i řádek
     Model v `/config` vždy, „jen pro tuhle relaci“ umí jen výběr přes Alt+P, Remote Control a SDK). Orbit si při
     žádosti zapíše původní hodnotu a hned po odpovědi modu ji vrátí (`models.restore_default` →
     `claude_settings.set_default_model`, jen když tam pořád je model z žádosti; žádná hodnota = klíč pryč; dvě
     přepnutí naráz: druhé vezme původní hodnotu z prvního). Naměřeno: výchozí model byl jiný ~60 ms. Běžící
     relace klíč nesledují (Pepova relace spuštěná bez `--model` jela 40 s na Opusu, i když byl výchozí Sonnet),
     týkalo by se to jen relace spuštěné právě v tu chvíli. V okně relace zůstane řádek „…and saved as your default
     for new sessions“, mod proto ukáže toast „jiný model jen pro tuhle relaci, výchozí … zůstává“.
- Bez odpovědi modu do 7 s (`models.ACK_WAIT_S`, relace spuštěná se starším modem) bublina: `/reload-plugins` nebo
  `/model …` v jejím okně. Odmítnutí od Claude Code (model účet nemá) = červená bublina s jeho textem. Žádost, na
  kterou Orbit nedočkal (restart), převezme další start (`models.leftovers`).
- **Ověřeno 16. 10.** skutečnou interaktivní relací (Haiku, nainstalovaný mod 0.5.0, skutečný `cc_hook.py` jako
  PreModelSwitch přes `--settings`): převzetí 0,86 s, přepnutí bez dialogu za 1,07 s, další odpověď od
  `claude-sonnet-5-5`, výchozí `opus[1m]` vrácený. Neověřeno: celé z běžícího Orbitu (pravý klik) a `--model`
  ze skutečného plusku (řetězec příkazu je v testech, rozbalení proměnné v cmd je stejné jako u `--resume`).
  Testy `tests/test_core_models.py`, `tests/test_ui_models.py`, `--model` v `test_claude_agent_tools.py`.

### Autopilot (od 13. 10., `app/autopilot.py`, `app/autopilotview.py`, `app/bland.py`)
- Pepa viděl reel Rileyho Browna („give Claude Code a phone number“, Bland AI) a chtěl: ikonka telefonu, v ní aktivní
  relace, jednu vybrat, „dát do řešení“ ve smyčce a po každém kole (třeba po hodině) mu zavolat, co udělala, co dál
  a jak by problém řešila. Rozhodnutí (13. 10.): název **Autopilot**; odpověď z hovoru **hned spustí další kolo**,
  volá se nejvýš jednou za interval (relace mezitím stojí); nezvednutý hovor = **relace počká** a za interval se volá
  znovu; telefonie **Bland AI**. Rozebrané a zamítnuté: WhatsApp (Calling API chce firemní číslo na Cloud API
  s limitem aspoň 2 000 příjemců denně, webhook nebo SIP s vlastním WebRTC, a 4 nezvednuté hovory po sobě odeberou
  povolení volat), ElevenLabs + Twilio (nejlepší čeština, ale dva účty a číslo), Twilio jen s nahrávkou (bez rozhovoru),
  Telegram (bot volat neumí, jen hlasovky).
- Panel: kruh s telefonem (E717) vlevo od plusu (jen s Claudem), číslo = kolik relací je na autopilotu
  (`FloatingButton._phone_center`, `autopilot_clicked`); v menu Orbitu „Autopilot…“. U relace na autopilotu je za
  názvem telefon a „kolo 2“ / čas dalšího hovoru / „volá“ / „stojí“ v barvě akcentu (`Session.autopilot`, tooltip
  `autopilot_note`, nastavuje `Dictation._drive_autopilot` před `set_sessions`).
- Okno (`AutopilotWindow`, QDialog `#autopilot`): nahoře číslo (`bland.normalize_phone`: 9 číslic = +420, jinak E.164),
  klíč Bland AI (pole je po uložení prázdné, v configu `autopilot_key` jako `dpapi:<base64>` šifrovaný pro účet
  Windows, `bland.protect`; po uložení `GET /v1/me` ukáže kredit), hlas (nepovinné), „V noci (22–7 h) nevolat“,
  „Kde vzít klíč“ (`v2.app.bland.ai/settings`), „Zkusit hovor“. Vlevo běžící relace (proužek v barvě složky), vpravo
  cíl (prázdný = pokračovat v tom, na čem pracuje), „Volat nejvýš jednou za“ 30 min / 1 h / 2 h / 3 h, „Pustit na
  autopilota“; u relace na autopilotu stav, cíl, poslední hlášení, poslední hovor (výsledek, minuty, cena, shrnutí,
  přepis), „Zavolat teď“ (hned, i v noci) nebo „Pokračovat“, když stojí, a „Vypnout autopilota“.
- **Jak relace dostane zadání**: mod `orbit-mozek` 0.4.0 (viz Mody) každé 2 s projde `<data>/sessions/prompt/`
  a `<relace>.<id>.json` (`{session_id, id, time, text}`, mladší než minuta) pošle `$.prompt.submit({text, asUser:
  true})` jako slova uživatele (vlastní tah, až relace nic nedělá), vedle zapíše `….done.json` `{ok, text: started /
  queued / důvod}`; „queued“ po 1,5 s, když relace zrovna pracuje (submit se vyřeší až se začátkem tahu). Bez odpovědi
  do 7 s (`ACK_WAIT_S`) autopilot stojí: relace nemá mod 0.4 (běží ze starší verze) → `/reload-plugins` nebo restart
  a „Pokračovat“ pošle stejné zadání znovu. Nepoužívá `/loop` ani CronCreate: kola řídí Orbit.
- **Kolo**: zadání (`first_prompt`, `next_prompt`) říká cíl, ať pracuje sám a o drobnostech rozhoduje sám, uživatel je
  mimo počítač, a ať tah ukončí blokem „## Hlášení pro telefon“ (Co jsem udělal / Stav / Návrhy, jak dál 1) 2) 3) /
  Otázka; bez kódu, cest a odkazů). Kolo skončí, když přehled relací (hooky) hlásí hotovo/chybu se Stopem po zadání
  (`s.since >= sent_at`); „čeká na tebe“ (oprávnění) se jen ukáže, nevolá se. Hlášení = poslední odpověď od nadpisu
  dál (`report_text` maže Markdown, kód, cesty, odkazy; max 3500 znaků), bez nadpisu celá.
- **Hovor** (`bland.start_call`): `language: "cs"`, `wait_for_greeting` (nejdřív „Haló?“), `record: false`,
  `voicemail: hangup`, `max_duration` 10 min, `first_sentence` „Ahoj, tady Orbit. Volám kvůli relaci …“, `task` =
  instrukce pro hlasového agenta Blandu (tykat, bez rodových tvarů, shrnout, návrhy, otázka, doptat se, odpovídat jen
  z hlášení, na konci zopakovat, co předá; nic neslibovat, žádná hesla) + hlášení, `summary_prompt` = co chce
  uživatel dál. Na telefonu mluví model Blandu, ne Claude. Orbit se ptá `GET /v1/calls/<id>` každých 8 s
  (`POLL_CALL_S`, nic z internetu nemusí do PC), `bland.outcome`: odpověděl (aspoň jedna jeho neprázdná věta),
  nezvedl (no-answer, busy, hlasová schránka, ticho), chyba. Přepis „Pepa: … / Orbit: …“ + shrnutí jde jako další
  kolo; „AUTOPILOT: KONEC“ na začátku odpovědi relace (když v hovoru zaznělo ukončení) autopilota vypne.
- Kdy volat: první kolo hned po jeho konci, další nejdřív interval po posledním hovoru (`next_call`), noc 22–7 h
  posune na 7:00 (`_when`, `autopilot_quiet`). Bubliny (`_notify`, klik = okno na té relaci): „Kolo je hotové,
  zavolám v …“ (jen když se čeká přes minutu), „Hovor skončil, relace pokračuje kolem N“, „Hovor nikdo nezvedl…
  zkusím to znovu v …“, chyby (klíč, kredit 402, relace bez modu) = autopilot stojí. Skončená relace autopilota vypne.
- Stav v `<data>/autopilot.json` (atomicky, jen při změně): po restartu Orbitu hovor, na který se čeká, pokračuje
  (`calling` s id), hovor bez id se zavolá znovu, nepřevzaté zadání se pošle znovu. Požadavky na Bland běží ve
  vlastních 2 vláknech, výsledky si `tick()` bere každou sekundu (`_poll_sessions` → `_drive_autopilot`); bez přehledu
  relací (hooky + `show_sessions`) autopilot stojí a okno řekne proč.
- Log: číslo jen jako „…456“, klíč nikdy, hlášení a přepisy jen délky. Bland: kredit nejméně 5 $ pro hovory mimo
  USA/Kanadu, cena podle srovnání ~0,12–0,14 $/min + telefonie; čeština podle dokumentace podporovaná.
- Ověřeno 13. 10.: mod 0.4.0 ve skutečné relaci Claude Code (`claude -p --input-format stream-json`, haiku,
  dočasná datová složka) soubor se zadáním převzal za 1,5 s, relace odpověděla novým tahem, `.done.json` =
  `{"ok":true,"text":"started"}`. **Ověřeno i v Pepově interaktivní relaci** (13. 10. v 17:41, m-tex, bezpečnostní
  hlídka): zadání převzal mod za 2 s, hook UserPromptSubmit pro něj běží, relace po 8 min napsala hlášení přesně
  v požadovaném tvaru (1269 znaků).
- **Stop přijde až po „idle“**: seznam relací Claude Code přepnul na `idle` dřív, než async Stop hook zapsal odpověď
  (13. 10. o 1 ms), přehled relací to bral jako přerušený tah bez odpovědi a autopilot vzal prázdné hlášení. Teď
  kolo bez odpovědi čeká na Stop až 15 s (`STOP_WAIT_S`, `Autopilot._quiet`); přerušený tah (Esc, Stop nepřijde)
  pak pokračuje bez hlášení.
- **Kredit zdarma do Česka nevolá**: Bland vrátí 400 „International calling requires a completed purchase. Adding
  a card by itself does not enable it – buy credits or turn on auto-recharge“; úvodní kredit (Pepa měl 2 $) ani
  samotná karta nestačí, `bland._request` to říká česky. **Ani po nákupu do Česka nevolá** (Pepa 13. 10. koupil
  10 $, kredit 12 $): pak 400 „Call not permitted to this destination, or call was formatted incorrectly.“ (zkoušeno
  ještě 15. 10.). Podpora Blandu 16. 10. (e-mail na obchod@m-tex.cz): +420 je přes výchozí telefonii Blandu zakázané,
  kredit ani čekání to nezmění; jediná cesta je vlastní Twilio (BYOT: Česko ve Voice Geo Permissions v Twiliu, Twilio
  připojit v Bland › Add-ons › BYOT, číslo importovat, volat s hlavičkou `encrypted_key` a `from` = to číslo). Bland
  pak strhává z kreditu jen svou sazbu (0,14 $/min na plánu Start), volání platí Twilio. Orbit BYOT zatím neumí.
  **Neověřeno**: skutečný hovor, kvalita češtiny Blandu.
  Testy `tests/test_core_autopilot.py` (falešný Bland a mod) a `tests/test_ui_autopilot.py`.

### Mody pro Claude Code (od 8. 10., `mods/`)
- Pepa slyšel o modech Claude Code (doplňky v TypeScriptu, které běží uvnitř Claude Code: panely, řádek nad promptem,
  příkazy, nástroje, přístup k proudu odpovědi; od 2.1.287, API je v ranném přístupu) a vybral dva nápady:
  „mozek relace“ a úkoly z Poznámek přímo v relaci. Návod a typy: skill `plugin-authoring` (typy jsou ve složce
  skillu, po načtení modu i v `mods/<mod>/.claude-plugin/types/`, ty nejsou v gitu).
- **`orbit-mozek`**: `/mozek` otevře panel (u Pepy v režimu `"tui": "fullscreen"` vedle konverzace): fáze tahu
  (přemýšlí/píše/nástroje), konec myšlení a psaného textu z proudu `turn.step`, nástroje tahu s časy (`tool.call`),
  podagenti, „aktivita“ (výstupní tokeny po krocích) a kontext jako `/context` z `$.session.usage({ breakdown:
  'summary' })` (odhad bez požadavků na API, nejvýš jednou za 2,5 s) s limity 5 h a týden. Proud se do vykreslení
  propisuje nejvýš po 120 ms (`flush`), běžící čas tiká jen během tahu. Nic neposílá ven.
- **Limity pro panel Orbitu** (od 10. 10., `orbit-mozek` 0.2.0): hook `session.measure` (engine ho volá po každém tahu
  a při posunu limitu o celý bod, s tím, co hlásily odpovědi: `rateLimits` `{kind, percentUsed, resetsAt}` ISO, bez
  požadavku) zapíše `<data>/sessions/status/<id relace>.mod.json` (`session_id`, `time` v s, `source`,
  `rate_limits.five_hour/seven_day` `{used_percentage, resets_at}`) do každé datové složky Orbitu, kterou najde (má
  `config.json`): `ORBIT_DATA_DIR`, `ORBIT_TASK_DATA`, `%LOCALAPPDATA%\Orbit`, `~\orbit`; bez nalezené zkusí znovu
  po 10 min. Funguje i bez panelu `/mozek` (hook běží v každé relaci s modem). Fable v `rateLimits` není.
- **Zastavení příkazu na pozadí** (od 11. 10., `orbit-mozek` 0.3.0): každé 2 s projde `<data>/sessions/stop/`
  (`$.fs.list`), žádost své relace mladší než minuta (`STOP_FRESH_MS`) vyřídí jednou (`stopsSeen`: jméno + čas
  souboru) přes `TaskStop` a vedle zapíše odpověď `{ok, text}` (viz Příkazy na pozadí). Mazat soubory mod neumí
  (`$.fs` nemá remove), maže Orbit.
- **Zadání z Autopilota** (od 13. 10., `orbit-mozek` 0.4.0, `promptRequested`): ve stejné smyčce po 2 s projde
  `<data>/sessions/prompt/`, zadání své relace (mladší než minuta, nejvýš 60 tis. znaků, jednou) pošle
  `$.prompt.submit({text, asUser: true})` a odpoví `{ok, text}` (started, po 1,5 s queued, nebo proč ne). Viz Autopilot.
- **Přepnutí modelu** (od 16. 10., `orbit-mozek` 0.5.0, `modelRequested`): ve stejné smyčce `<data>/sessions/model/`,
  žádost své relace (mladší než minuta, model jen `fable|opus|sonnet|haiku` s nepovinným `[1m]`, jednou) potvrdí
  `.ack.json`, spustí `$.command.run({command: 'model', args})` a odpoví `.done.json` `{ok, text, model}`
  (`$.session.model()` po přepnutí). Viz Model relací. 16. 10. nainstalovaný u Pepy (0.4.0 → 0.5.0).
- **`orbit-ukoly`**: v relaci s `ORBIT_TASK_ID` řádek nad promptem (úkol, složka, počet poznámek, tlačítka Poznámka,
  Hotovo, Skrýt), sekce systémového promptu „pracuješ na úkolu…“ (`prompt.compose`, ne když je úkol hotový) a nástroje
  `mcp__orbit-ukoly__task_note` a `task_done` (`isDeferred: false`). Úkol čte z `tasks.json` (znovu po 15 s), píše jen
  do schránky (viz Poznámky a úkoly). `/ukol` vypíše aktivní úkoly, `/ukol 2` relaci připojí (pamatuje si to v
  `$.store` podle id relace, takže to platí i po obnovení), `/ukol odpojit`. Datovou složku bez proměnné hledá:
  poslední známá, `ORBIT_DATA_DIR`, `%LOCALAPPDATA%\Orbit`, `~\orbit`. Na mobilu není `Input`, tlačítko Poznámka tam
  chybí.
- Instalace u Pepy (8. 10.): `claude plugin marketplace add C:\Users\josef\orbit` (marketplace `orbit` typu
  directory) a `claude plugin install orbit-mozek@orbit` + `orbit-ukoly@orbit` pro uživatele; v `settings.json` jsou
  `enabledPlugins` a `extraKnownMarketplaces`. **Nainstalovaný mod je kopie** v `~/.claude/plugins/cache/orbit/<mod>/
  <verze>` (`installed_plugins.json`), ne složka repa: po úpravě zvednout `version` v `plugin.json`, pak
  `claude plugin marketplace update orbit` a `claude plugin update <mod>@orbit` (10. 10. tak 0.1.0 → 0.2.0, 11. 10.
  `orbit-mozek` 0.3.0); běžící
  relace ho načtou po restartu (nebo `/reload-plugins`). Ostatní:
  `/plugin install orbit-mozek --marketplace josefkotran/orbit` (až bude `mods/` na GitHubu).
- Kontrola: `claude plugin validate mods/<mod>` a `claude plugin test mods/<mod>` (testy v `tests/*.test.ts` běží
  proti enginu: vše, co engine dělá sám, odpovídá test; volání na `$` vrací `{ value }`, cesty přicházejí se
  zpětnými lomítky). Typy: po načtení modu `video\node_modules\.bin\tsc -p mods/<mod>` (engine k modu zapíše
  `tsconfig.json` a `.claude-plugin/types/`, obojí mimo git). Nástroje, které mod registruje až za běhu, typy enginu
  neznají, proto matcher `tool.call` jako regulární výraz (`/^mcp__orbit-ukoly__task_note$/`), ne jméno.
- Agent Orbitu (`--setting-sources ""`) a učení slovníku (`--safe-mode`) mody nenačítají.

### Hlasové povely pro terminál
- „Nový řádek“ = zalomení, „nový odstavec“ = prázdný řádek. Od 8. 10. i samotné „odstavec“, ale jen jako samostatný
  kus mezi interpunkcí („Ahoj Andrej, odstavec, přeposílám“; Pepa to tak řekl do Outlooku a čekal odstavec),
  „přepiš ten odstavec“ zůstane textem (`whisper_server._COMMAND_RE`).
- Věta „Odešli.“ (nebo „Odeslat.“) na konci diktátu = Enter; diktát jen „Stop.“ / „Zastav.“ = Esc (přeruší Clauda).
  Jen jako samostatná věta, „…tak mu to odešli.“ zůstane textem. Patří pod přepínač „Hlasové povely“.
- Enter jde po textu se zpožděním 300 ms + 1 ms na znak (max 1,5 s): terminál vkládá asynchronně a Claude Code bere
  klávesu ve stejné dávce jako psaný text za součást vložení.
- Enter i Esc jdou jen do okna, které bylo v popředí při vložení (od 7. 10., `Inserter.press(…, on_skipped)`): když
  se během zpoždění přepne jinam, klávesa se nepošle a přijde bublina „Okno se mezitím změnilo, povel „Odešli“ jsem
  neprovedl.“ (nebo „Stop“).

### Vrátit, opravit a upravit diktát (od 8. 10. večer, `editing.py`, `history.py`, `rewrite.py`)
- Pepa nechal udělat rešerši podobných nástrojů (Wispr Flow, Aqua Voice, Talon, Dragon, Win+H…, report
  `reports/Diktovací nástroje a podněty pro Orbit.md`, není v gitu) a vybral z ní čtyři věci: diktát vrátit nebo
  opravit hlasem, historii diktátů, úpravy textu hlasem a učení slovníku ze skutečných oprav.
- **„Smaž to“, „Vyber to“, „Vlož to znovu“** jsou povely, jen když jsou celým diktátem (jako „Stop.“, i „Vymaž to“,
  „Odstranit to“, „Vyškrtni to“ jako ve Win+H; `editing.command`), pod přepínačem Hlasové povely. Krátký povel Whisper
  píše pokaždé jinak (Pepovo „Smaž to“ 8. 10.: „Smáš to!“, „Smažu to.“, „Smažuto.“, „S máštou!“, „Smaš to.“; první
  verze s přesným zněním je vkládala jako text), proto se porovnává bez diakritiky a mezer s pevným slovesem a volným
  tvarem (`_DELETE_RE` na `_said`). Čistá podobnost nešla: „Vrať to.“ vycházelo jako „Vyber to“ a „Smaž to. Odešli.“
  (prompt pro Clauda) jako mazání. Daň: samotné „Smažu to.“ je povel, ne text. „Smaž to“ = Backspace
  přes poslední napsaný diktát, další „Smaž to“ ten před ním (až 10 za sebou), „Vyber to“ = Shift+← přes něj (pak
  „Smaž to“ = jeden Backspace, nový diktát ho přepíše), „Vlož to znovu“ = poslední diktát z historie do okna vpředu.
- **Kdy je to bezpečné** (`editing.Trail`, pravidlo Talonu pro „scratch that“): jen ve stejném okně a jen když od
  vložení nepřišla žádná uživatelova klávesa ani klik, jinak by Backspace mazal jeho text. Hlásí to hook diktovací
  klávesy (`PushToTalk(on_input=…)`): každá klávesa kromě samotných Ctrl/Shift/Alt/Win a vlastní vazby, každé tlačítko
  myši kromě kliku na Orbitova okna (`inserter.own_point`) a tlačítka agenta (`PushToTalk.ignore`). Orbitovy klávesy
  jsou injected a nepočítají se. Myší hook u vazby na klávesu běží jen od vložení do prvního kliku
  (`watch_clicks`), protože vidí každý pohyb myši. „Odešli“/„Stop“ trail smaže (text odešel). Klávesy se posílají až
  po puštění Ctrl/Shift (`Inserter.when_keys_up`, max 3 s): s drženým Ctrl by Backspace mazal celá slova.
- **Terminál**: Claude Code sbalí vložení nad 800 znaků nebo nad 3 řádky do jednoho bloku `[Pasted text #1]`
  (code.claude.com/docs/en/terminal-config) a Backspace by pak smazal blok najednou a zbytek by snědl text před ním.
  V terminálu (`inserter.is_terminal`: WT, konzole, mintty…) proto Orbit maže a přepisuje jen kratší diktáty
  (`editing.terminal_safe`), „Vyber to“ tam neumí. Ověřeno na falešném poli, ne v živém Claude Code.
- **Historie diktátů** (`keep_history`, výchozí zapnutá, jen v počítači): `<data>/history.json`, posledních 1000
  (Pepa: „ať vidím všechnu historii“; ~300 kB): text, Whisperův surový text, program (`inserter.app_name`),
  vloženo/ve schránce, délka, nahrávka (`recordings/<stem>`, když se ukládají), pokyn a původní text u úprav,
  uživatelova oprava. Vypnutí soubor smaže, v paměti zůstane poslední (kvůli „Vlož to znovu“). Okno
  (`historyview.HistoryWindow`) otevře ikona bubliny s řádky (E8BD, `ui.DICTATIONS_GLYPH`) hned vpravo od sešitu
  Poznámek (`FloatingButton.dictation_history_clicked`, i bez Clauda) a menu „Historie diktátů…“. Do 10. 10. ji
  otevírala ikona hodin vedle agenta, tu má teď Historie relací (Pepa: „nechci tam Historii diktátů, chci tam
  Historii sessions“), a Pepa pak chtěl „novou ikonku vedle poznámek Historie diktátů“. Kopírování je
  hlavní: ikona na konci každého řádku (po kliku na chvíli zelená fajfka, `_RowDelegate`), dvojklik nebo Ctrl+C;
  nahoře hledání bez diakritiky. Vpravo Vložit (okno se schová, Windows vrátí předchozí okno a text jde tam),
  Kopírovat, Přehrát nahrávku, Přepsat znovu (s dnešním slovníkem), Uložit opravu, Smazat; dole Vymazat historii.
  V menu i „Vložit / Kopírovat poslední diktát“. Text, který skončil ve schránce (okno se změnilo), má bublinu „Nebo
  klikni sem a vložím ho, kam teď píšeš“.
- **I věty pro agenta Orbit** (od 10. 10., Pepa: „přidej do historie diktátů i diktování botovi… ať je to tam
  oddělené, vzhledově že to bylo pro AI agenta Orbit“): každá nahrávka pro agenta s textem je záznam `kind: "agent"`
  (`history.AGENT`, `Dictation._remember_agent` z `_agent_heard`, jen s `take`: druhé volání z otázky úkolu nic
  nepřidá). Kromě holé odpovědi na otázku „Mám to poslat?“ (`agent.confirmation` je ano nebo ne: „jo“, „ano, pošli to“,
  „ne“; Pepa: „ať se jo neukládá v historii diktátů“): ta se neukládá a stav odeslání dostane záznam věty, která
  otázku vyvolala. „Ano, ale do jiné relace“ se ukládá (říká něco nového). Odpověď agenta (`reply`) a řádek odeslání (`action`, „→ téma, složka · odesláno ✓“ + zpráva) se
  doplňují z panelu (`_feed_update` → `_feed_to_history`), dokud tah agenta trvá; událost `done` (bez čekající otázky),
  `exit` a `reset` ho ukončí, tah, který začala zpráva od relace, tak k větě nic nepřipíše. S vypnutým
  `keep_history` se nezapisují (jediný záznam v paměti má zůstat poslední diktát). `History.last()` (Vlož to znovu,
  menu) je přeskakuje. Okno: řádky kreslí `_RowDelegate` celé (čas a cíl tlumeně, text), u agenta proužek v barvě
  akcentu a „Agent Orbit“ v ní; nahoře výběr Všechno / Diktáty / Agent Orbit; vpravo „pro agenta Orbit“ a pole
  „Odpověď agenta Orbit“; hledá se i v odpovědi. Obnovení okna během odpovědi agenta nechá rozepsanou opravu
  i přehrávání (`_shown`).
- **Úpravy textu hlasem** (`voice_edit`, noví uživatelé vypnuté, posílá text Claudovi): **Ctrl nebo Shift držený se
  začátkem diktátu** (`inserter.edit_held`, kontrola při stisku a znovu s prvním zvukem; diktovací klávesa sama se
  nepočítá) = to, co se řekne, je pokyn. Tlačítko má místo mikrofonu tužku (E70F), pořád červenou při poslechu.
  Gesto Ctrl + klávesa navrhl Pepa sám v nápadech. Během přepisu pokynu Orbit (po puštění Ctrl/Shift) zkusí přečíst
  výběr přes **Ctrl+Insert** (`Inserter.copy_selection`: kopíruje všude, na rozdíl od Ctrl+C nikdy nepřeruší program,
  schránka se hned vrátí a značky „ne do historie“ zůstanou; v terminálech a JetBrains IDE se nezkouší, VS Code
  „řádek bez výběru“ pozná podle `vscode-editor-data`). Pak: pokyn „Smaž to/Vyber to“ jako bez Ctrl; **„Nahraď X za
  Y“** (i „oprav/přepiš/změň X na Y“, „místo X napiš Y“) udělá Orbit sám, když X najde (`editing.find`: celá slova,
  bez diakritiky, podobnost ≥ 0,75, všechny stejné výskyty, velké písmeno na začátku věty); jinak **Claude**
  (`rewrite.Rewriter`: `claude -p --safe-mode --model sonnet --effort low`, JSON `{text, problem}`), spuštěný už při
  stisku (`claude_cli.Prepared`), takže po puštění trvá 3–6 s (měřeno 8. 10.). **Od 24. 10. jde zadání jako
  stream-json** (`--input-format stream-json`, výsledek z události `result`): Claude Code 2.1.310 s obyčejným stdin
  skončí, když do 3 s nic nepřijde („no stdin data received in 3s“), a pokyn se řekne a přepíše za déle, takže každá
  úprava přes Clauda by selhala (ověřeno: čekání 6 s = chyba, 2 s v pořádku; se stream-json 6 s v pořádku).
  Claude dostane označený text, jinak
  poslední diktát (když je ještě bezpečně před kurzorem), jinak nic a podle pokynu píše nový text („napiš krátkou
  odpověď…“), nebo vrátí `problem` („Přelož to.“ bez textu). Text je pro něj data (ověřeno: pokyn uvnitř textu
  neposlechl), tvary bez rodu („nestihnu přijít“).
- Výsledek: přes výběr vždy **vložením** (Ctrl+V nahradí výběr, a když výběr není v poli, nic se nestane, kdežto
  psaná písmena by mohla být zkratky stránky), přes poslední diktát Backspace od prvního rozdílu a dopsání zbytku, bez
  textu na kurzor. Když se mezitím změnilo okno nebo přišla klávesa či klik, jde výsledek do schránky. Bublina „Klikni
  sem a vrátím původní text“ (`_revert_edit`, jen dokud je text bezpečně před kurzorem, jinak původní do schránky).
- **Opravy pro učení slovníku** (`learning.add_correction`, `<data>/corrections.json`, posledních 200): z „Nahraď X
  za Y“ (i když ho udělal Claude: `editing.word_changes` malých změn), z opravy v historii (jen u diktátů, ne u
  výsledků úprav) a slabší z diktátu řečeného do 60 s po „Smaž to“ do stejného okna, když se podobá smazanému
  (`REDICTATE_SIMILAR` 0,5; jen pro učení, bez bubliny). Bublina „Opraveno: X → Y. Klikni sem a budu to tak opravovat
  vždycky“ přidá opravu do `replacements` (jen změnu velikosti písmen do slovníku). Učení slovníku se spustí i po 3
  nových opravách (`CORRECTIONS_EVERY`) a Claude je dostane jako nejspolehlivější důkaz („said again“ slaběji).
- **Hudba při diktování** (`duck_audio`, Nastavení › Chování: Hraje dál / Ztiší se / Úplně se ztlumí; od 8. 10.,
  Pepa: „ať se ztlumí muzika, když diktuju“): `ducking.Ducker` při startu nahrávání (diktát i agent) ztlumí, nebo
  ztiší na pětinu vlastní hlasitosti, zvukové relace všech ostatních programů na všech aktivních výstupech (to, co
  ukazuje Směšovač hlasitosti: `IAudioSessionManager2` → `ISimpleAudioVolume`, ctypes bez dalšího balíčku). Orbit
  (`os.getpid()`, jeho pípnutí) a systémové zvuky Windows zůstanou, relace už ztlumené nebo na nule taky. Po zastavení
  mikrofonu (`_finish_recording`, `_drop_recording`, Ukončit) se vrátí jen to, co je pořád na Orbitově hodnotě (když
  to uživatel mezitím ve směšovači změnil, nechá se). Co se mění, se nejdřív zapíše do `<data>/ducked.json`: když Orbit
  spadne uprostřed diktátu, další start to vrátí (podle instance relace, jinak podle programu). Běží ve vlastním vlákně
  (pomalý ovladač nezdrží mikrofon).
- **Relace, která během diktátu skončí** (od 11. 10., Pepa: „nefunguje mi zvuk na Chromu, na Spotify jo“): Windows si
  ztlumení a hlasitost pamatují pro každý program a výstup (`HKCU\Software\Microsoft\Internet Explorer\LowRegistry\
  Audio\PolicyConfig\PropertyStore`, hodnota `5` = ztlumení) a dají je jeho další relaci. Chrome si zvukový proces
  (`--utility-sub-type=audio.mojom.AudioService`) vypíná, když nic nehraje: 10. 10. ve 12:31 ho Orbit ztlumil při
  33s nahrávce pro agenta, proces mezitím skončil, Orbit hlásil „vrácen: 0 z 1“ a Chrome byl od té doby ztlumený na
  reproduktorech (Realtek line-out) a Orbit ho bral jako ztlumený uživatelem. Teď: změna, jejíž relace zmizela, zůstane
  jako dluh (`Ducker._owed`, v `ducked.json` i přes restart, s `seen` = relace z doby ztlumení) a každé 2 s
  (`RETRY_S`, průchod relacemi ~1,5 ms CPU) se hledá nová relace téhož programu na tom výstupu, která tam při ztlumení
  nebyla; ta dostane hodnotu zpět (jen když je pořád Orbitova), nejdéle týden (`GIVE_UP_S`). Stejně se při vracení
  vezme i relace téhož programu, která vznikla během diktátu. Ověřeno na skutečném Core Audio: ztlumený přehrávač
  ukončený, nový Windows spustily ztlumený, Orbit ho za 1,9 s vrátil. Log jmenuje program („Teď nehraje, zvuk mu
  vrátím, až zase začne: chrome.exe“). Ověřeno na skutečné relaci testovacího procesu (ztlumit, ztišit, vrátit, návrat
  po „pádu“). Orbit z venvu má relaci pod PID skutečného `pythonw.exe` (ne spouštěče z venvu), a to je
  `os.getpid()`. Piper hraje ve vlastním procesu, ale při nahrávání stejně mlčí.
- Ověřeno 8. 10.: v testovacím okně jiného procesu psaní, Backspace přesně o diktát, Shift+← výběr, Ctrl+Insert
  přečte výběr a vrátí schránku, bez výběru `None`; skutečný `claude -p` u pěti pokynů. 38 nových testů
  (`test_core_editing`, `test_ui_editing` na falešném poli). Neověřeno: skutečný hook s fyzickou klávesou a klikem
  (hooky injected vstup nevidí) a chování v živém Claude Code.

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
- **Od 10. 10. jen nad čísly z relací** (`claude_usage.combined`, Pepa: „pořád se to opakuje, nejsou vidět limity“).
  V logu od 9. 10. 22:32 ani jedna úspěšná odpověď: endpoint vracel 429 s `Retry-After` přes hodinu, po každém restartu
  znovu, a s ním i 401 při startu (token zrovna vypršel, Claude Code ho obnoví až další relací). Na endpoint se ptají
  i samy relace Claude Code (`fetchUtilization` v `claude.exe`: `/api/oauth/usage?at_wall=1`, `cedar_ember`…) a limit
  je na účet, takže při hodně relacích na Orbit nezbývá. Teď 5 h a týden berou z `<data>/sessions/status/*.json`
  (stavový řádek Orbitu `<id>.json`, mod `orbit-mozek` `<id>.mod.json`, viz Mody) každých 5 s, novější hlášení
  vyhrává (`Limit.at`, i proti odpovědi endpointu); endpoint se ptá nejvýš jednou za 30 min (`OAUTH_EVERY_S`) a jen
  když od posledního pokusu nějaká relace něco nahlásila (Claude Code se nepoužívá = limity se nehýbou, přes noc ani
  jeden dotaz; čas pokusu `asked_at` v cache platí i přes restart; menu „Obnovit využití Clauda“ = hned), kvůli řádku
  Fable (jen on ho má, ukáže se z odpovědi až 12 h staré, `OAUTH_EXTRA_S`) a práci mimo Claude Code. Dřív každé
  2 min (30 dotazů za hodinu). Jeho chyba se jen zaloguje, panel nezešedne. Bez čísel z relací je to endpoint sám
  (každých 5 min, `OAUTH_ALONE_S`, chyby do panelu). Orbitovy běhy `claude -p` (agent, úpravy, učení, souhrny) se
  na endpoint neptají (ověřeno `--debug-file` 10. 10.); zbytek dotazů posílají interaktivní relace Claude Code.
  Tooltip: „údaj z 10:30“ u řádku staršího o 10 min než nejnovější. Ověřeno 10. 10.: relace v m-tex s novým modem
  zapsaly limity, panel 5 h 7 % a týden 2 % během 429.
- Zdroj `statusline` bez souhlasu se stavovým řádkem ukáže limity ze souborů modu, když nějaké jsou (jinak „Zapnout →“).
- **Token se jen čte, nikdy neobnovuje** (refresh by rotoval refresh token a mohl rozbít přihlášení Claude Code).
- Bubliny potřebují `Qt.WA_AlwaysShowToolTips`, jinak se u neaktivního okna nezobrazí.
- Předpověď: z odběrů 5h okna za posledních 30 min (aspoň 10 min a +1 bod) se spočítá, kdy dojde. Když dřív než
  se okno obnoví, jednou za okno přijde bublina, pokud zbývá < 60 min. **Hlavička panelu** (`FloatingButton._header_note`,
  od 10. 10.; Pepa: „nevím, co znamená ‚dojde v 15:51‘, když vedle není, kdy se 5hodinový limit obnoví“, předpověď
  dřív odpočet obnovení nahradila): oranžově „Při tomhle tempu vyčerpáš limit 5 h v 15:51“ a tlumeně „· obnoví se až
  v 17:20“, vždy obojí; když se nevejde, kratší „Limit 5 h vyčerpáš asi v 15:51 · obnoví se v 17:20“ a „5 h dojde
  v 15:51 · obnova 17:20“. Bez předpovědi ↻ „limit 5 h se obnoví v 17:20 (za 2 h 14 min)“ (dřív jen „2 h 14 min“).
  Tooltip panelu i bublina mají větu `claude_usage.forecast_text`: „Při tempu posledních 30 minut vyčerpáš limit
  5 h v 15:51, ale obnoví se až v 17:20: pak by se čekalo 1 h 29 min.“
- Endpoint vrací 429, když se ptá moc často (např. několik restartů Orbitu za sebou; v Pepově logu ~20×). Po 429 se
  Orbit neptá aspoň 5 min (nebo podle `Retry-After`, max 1 h).
- **Přes restart** (od 9. 10., Pepa: „nefungujou Claude limity“ po třech restartech za 20 min): poslední odpověď
  a pauza po 429 jsou v `<data>/cache/usage-oauth.json` (`at`, `answer`, `retry_at`; token ne). Odpověď mladší než
  110 s (`OAUTH_FRESH_S`) nový Orbit ukáže bez ptaní, pauza po 429 platí i pro nový Orbit (`claude_usage.Limited`)
  a panel mezitím ukáže poslední odpověď do hodiny staré jako „neaktuální“ místo prázdna (`Dictation._usage_failed`).
  Před restartem Orbitu při ladění tak stačí, aby běžel aspoň 2 min (nebo cache čerstvě naplnit `fetch_oauth()`).

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
  `statusline-previous.json` (původní stavový řádek uživatele, když je Orbitův zapnutý), `tasks.json` (+ `tasks\`
  s dlouhými zadáními; úkoly z Poznámek, nikdy do gitu), `autopilot.json` (relace na Autopilotu, hlášení a přepisy
  hovorů; `sessions\prompt\` zadání pro mod). Ve složce aplikace zůstává
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
  Proč: dřív výchozí hodnoty při prvním uložení přepsaly slovník (ověřeno zámkem bez sdílení). Když `config.json`
  nejde přečíst, výchozí „ne“ neodebere hooky ani stavový řádek, dokud uživatel sám neuloží nastavení nebo průvodce
  (`Dictation._cfg_doubtful`, od 7. 10.). Proč: jinak by hooky zmizely jen kvůli zamčenému souboru.
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

### Verze Claude Code a aktualizace (od 13. 10.)
- Pepa chtěl vidět aktuální verzi Claude Code, jestli není potřeba aktualizace, a tlačítko na aktualizaci. Kde:
  nastavení › Claude pod účtem („Claude Code 2.1.296 · nejnovější verze ✓“ zeleně, „… · je nová verze 2.1.297“
  oranžově + „Aktualizovat Claude Code“) a menu Orbitu pod „Obnovit využití Clauda“ („Claude Code 2.1.296: nejnovější
  verze“ šedě, nebo „Aktualizovat Claude Code na 2.1.297 (teď 2.1.296)“).
- **V panelu pořád** (Pepa hned potom: „ať je pořád napsána verze, nějak čitelně, a možnost aktualizace“): pilulka
  ve stylu panelu mezi panelem a kruhy reproduktoru a mikrofonu (`FloatingButton.set_claude_version`,
  `_version_layout`, `_paint_version`; data z `Dictation._claude_version_line`). Vlastní pruh `VER_PILL_H` +
  `VER_GAP` (27 px): panel se o něj posune, kruhy zůstanou na místě. Zarovnaná s okrajem panelu nad kruhy (vpravo,
  vlevo, uprostřed jako panel), s panelem pod tlačítkem je pod kruhy. Stavy: „Claude Code 2.1.296 ✓ nejnovější“
  (zeleně), „Claude Code 2.1.290 → 2.1.296“ (oranžově) + tlačítko v akcentu **Aktualizovat**, „Aktualizuju Claude
  Code na 2.1.296…“, „… aktualizace se nepovedla“ + **Zkusit znovu**, bez známé nejnovější jen verze. Tooltip:
  podrobnosti, důvod chyby, relace na staré verzi. Klik na tlačítko = `ClaudeConnection.update_claude` (bez bubliny na
  začátku, panel to ukazuje; na konci bublina jako z menu). Bez panelu (vypnuté limity i relace) se neukazuje.
  Protože je vidět pořád, ptá se Orbit na nejnovější verzi i každých 30 min (`RELEASE_CHECK_MS`). „Nová verze“ tak
  občas chvíli svítí, než ji Claude Code (`autoUpdates`) nainstaluje sám.
- **Nejnovější verze přesně jako ji zjišťuje Claude Code** (jeho vlastní návod v `claude.exe` 2.1.296,
  `claude_setup.release`): kanál = `autoUpdatesChannel` v `settings.json` (jen `latest`/`stable`, nic jiného do
  adresy nejde; bez něj `latest`), npm instalace (cesta přes `node_modules`, Pepa) → `registry.npmjs.org/
  @anthropic-ai/claude-code/<kanál>` (to instaluje `claude update`), ostatní → `downloads.claude.ai/
  claude-code-releases/<kanál>` (verze jako text). Odpověď musí vypadat jako verze, porovnává se jako semver bez
  `+sha`. S `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` (prostředí nebo `env` v `settings.json`) se neptá. Spolu
  s tím znovu `claude --version` (Claude Code se mezitím mohl aktualizovat sám), dohromady ~0,4 s. Ptá se po
  připojení Clauda, každých 30 min, při otevření menu nejvýš jednou za hodinu (`RELEASE_STALE_S`), při otevření
  nastavení po 10 min, „Zkontrolovat znovu“ hned. 13. 10.: latest 2.1.296 (Pepa ji má), stable 2.1.287.
- **Aktualizace = `claude update` na pozadí** (`claude_setup.update`, `ClaudeConnection.update_claude`), bez okna:
  na nic se neptá a trvá obvykle do minuty (limit 10 min). U winget instalace to, co spouští Claude Code sám
  (`winget upgrade --id Anthropic.ClaudeCode --exact --silent --disable-interactivity`). Povedlo se = `claude
  --version` je po ní vyšší (ne kód ukončení: s kódem 0 končí i „Another Claude process … try again“); jinak česká
  věta podle výstupu (exe drží jiný program, aktualizuje se jinde, práva, síť, winget nic nemá), jinak poslední
  řádek výstupu. Výstup jde do logu (posledních pár řádků). Z menu bublina na začátku a na konci (klik = nastavení),
  s otevřeným nastavením jen v jeho boxu.
- **Běžící relace zůstávají na staré verzi**: verze relace je v seznamu Claude Code (`~/.claude/sessions/<pid>.json`,
  `version`, `sessions.running_versions`). Po aktualizaci box i bublina řeknou, kolik relací jede na starší, a že se
  nová projeví po novém spuštění (Historie relací › Pokračovat v relaci). `/restart` (alias `/update`) Claude Code
  na Windows nenabízí (jen macOS a Linux, ověřeno v `claude.exe`), proto se nezmiňuje.
- Když jsou automatické aktualizace vypnuté (`autoUpdates: false` v `.claude.json`, u nativní instalace jen bez
  `autoUpdatesProtectedForNative`, nebo `DISABLE_AUTOUPDATER`/`DISABLE_UPDATES`), box to u nové verze řekne.
- Neověřeno: skutečná aktualizace z Orbitu (Pepa měl 13. 10. nejnovější verzi, `claude update` se v testech nespouští).

### Zbalení do ikonky (od 13. 10.)
- Pepa: „celé to okno … se bude dát minimalizovat a bude to jenom jako ikonka Orbitu … podle toho, kde to mám
  umístěné, když na tu ikonku kliknu, tak se to celý zase rozbalí, ale někde bude ikonka zbalit“.
- Zbalit: samostatná kulatá bublinka s tučnou bílou čárkou v pruhu nad panelem, úplně vpravo (pravým okrajem na
  okraji panelu), hned vedle barev (`_fold_center`, `_on_fold`, `_paint_fold_chip`, pod myší světlejší), nebo menu
  Orbitu „Zbalit do ikonky“ (zaškrtávací). Pilulka barev je proto o bublinku a mezeru 8 px vlevo (`_dots`) a s ní
  agent, hodiny a plusko (počítají se od teček). Ve verzi 1.2.0 to byla tenká šedá čárka (znak E921) v hlavičce
  panelu a Pepa ji nenašel (vedle odpočtu limitu vypadala jako pomlčka za větou), pak chtěl „vedle barev, ale
  samostatná bublinka, barvy posuň doleva“. Test `test_its_own_chip_right_of_the_colours`. Rozbalit: klik na ikonku, nebo totéž
  v menu. `config.json` `collapsed` (výchozí false), vydrží restart (`Dictation._set_collapsed`).
- Zbalený `FloatingButton` (`set_collapsed`, `_collapsed`): okno jen čtverec mikrofonu (`_side`, `_btn_off` 0,0),
  takže `button_pos` a uložené místo se nemění a ikonka sedí přesně na středu mikrofonu; `_has_panel` je False
  (pruh, tečky, čipy, pilulka verze, řádky relací nic nekreslí ani nechytají). Ikonka `ICON_D` 44 px = favicon webu
  (planeta s nakloněnou dráhou, měsíc v barvě akcentu, `_paint_icon`). Červená s prstencem hlasitosti při diktování
  i poslechu agenta (soukromí: je vidět, že mikrofon je otevřený), oblouk při přepisu/načítání, oranžová tečka, když
  relace čeká na uživatele, pod myší světlejší. Stisk ikonky **není** push-to-talk (`_press_on_button` False),
  tažení ji přesune (uloží se jako dřív), pravý klik = menu Orbitu. Bubliny míří na ikonku (`bubble_anchor`).
- Pozor na zkratky v `paintEvent`: čtverec reproduktoru (`_speaker_area`) zasahuje 4 px do čtverce mikrofonu, zbalený
  ho proto vrací prázdný a `paintEvent` zbaleného kreslí jen ikonku hned na začátku (jinak by vlny čtení kreslily kus
  reproduktoru do ikonky). Testy `tests/test_ui_fold.py`.
- **Animace zbalení a rozbalení** (od 16. 10., `app/foldfx.py`; Pepa: „ať to udělá nějakou mega cool animaci … a když
  to odminimalizovávám, ať to udělá hezkou animaci a načte se okno“). Zbalení (800 ms): panel se nadechne (+4 %),
  pak se stáčí a zrychleně padá do středu mikrofonu jako do černé díry (stopa rozmazání, 80° po směru hodin), hvězdy
  z jeho ploch (56, na neprůhledných místech obrázku) za ním padají po spirálách, ve středu záblesk, ikonka vyskočí
  s přestřelem 20 %, natočí se na místo, měsíc kolem planety oběhne dvakrát (i za ní) a rozběhnou se dvě rázové vlny.
  Rozbalení (740 ms): ikonka nabobtná, měsíc zrychluje, záblesk a ikonka praskne, rázové vlny, hvězdy vyletí na svá
  místa v panelu a panel se ze středu rozvine (malý přestřel, otočení −40° → 0); přes panel pak přeběhne světelná
  vlna od mikrofonu ven (načítá se).
  - **Tlačítko se změní hned** (`set_collapsed(on, animate=True)`): velikost, místo, kliky, `button_pos` jsou rovnou
    ty nové (testy zbalení platí beze změny), jen kreslí nic (`_fx_hidden`), dokud animace neskončí. Animace je vlastní
    okno (`FoldFx`: průhledné, `WindowTransparentForInput`, bez aktivace, kolem obrázku `PAD` 64 px na rázové vlny,
    které by okno tlačítka u svého okraje usekly). Obrázek je okno tlačítka nakreslené celé (`_snapshot` →
    `_paint_whole`, to, co kreslí `paintEvent`): u zbalení to, co je teď na obrazovce, u rozbalení panel, jak bude
    vypadat (`_layout` spočítá rozvržení bez změny okna, `_wanted_align` zarovnání jako `_auto_align`). První snímek
    animace = to, co bylo vidět, poslední = to, co pak ukáže tlačítko (testy porovnávají pixely). Pořadí: okno animace
    se ukáže a vykreslí, pak se tlačítko schová; na konci se tlačítko vykreslí, pak okno animace zmizí: chvíli jsou
    vidět obě stejná, nikdy žádné.
  - Animuje se jen klik (čip se čárkou, ikonka) a menu „Zbalit do ikonky“, ne start Orbitu, ne skryté tlačítko a ne
    s vypnutými animacemi Windows (Nastavení › Přístupnost › Vizuální efekty › Efekty animace,
    `SPI_GETCLIENTAREAANIMATION`, `foldfx.animations_on`). Začátek nahrávání (diktát i agent), skrytí tlačítka a nový
    klik animaci hned ukončí: mikrofon musí být vidět červeně hned (soukromí). Okno animace začíná na průhlednosti
    tlačítka (zprůhledněné po 3 s) a za 150 ms je plné, jako `_wake`.
  - `_paint_icon(p, c, scale, spin, moon)`: ikonku animace kreslí stejná funkce jako tlačítko, s velikostí, natočením
    a polohou měsíce na dráze (`moon` v radiánech po směru hodin, `None` = přesně jeho místo; za planetou se kreslí
    před ní a je o kousek menší).
  - Změřeno 16. 10.: snímek 0,2–4,2 ms (okno 578×414), na skutečných Windows ~65 snímků/s, nejdelší mezera 15,6 ms.
    Testy `tests/test_ui_foldfx.py`; náhled po snímcích jde vyrobit přes `FoldFx.frame(u)`. Neověřeno: jak to vypadá
    v pohybu na Pepově obrazovce (jen snímky a běh mimo obrazovku).

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
  .venv\Scripts\python.exe build\build_whisper.py        # jen při nové verzi whisper.cpp: whisper-next\ → whisper\
  .venv\Scripts\python.exe build\build_installer.py [--without-piper] [--no-installer]   # whisper z whisper\
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
- **whisper-server pro cizí PC** (od 3. 10. ve `whisper/`, dřív `whisper-next/`): starý `whisper\` byl přeložený pro Pepův procesor (`GGML_NATIVE`)
  a s Vulkanem jako povinnou DLL, jinde by nenaběhl. Nový: whisper.cpp 1.9.4, `GGML_BACKEND_DL` +
  `GGML_CPU_ALL_VARIANTS` (14 `ggml-cpu-*.dll`, vybere se podle procesoru), `ggml-vulkan.dll` se bez Vulkanu přeskočí
  (pak procesor). Na Pepových nahrávkách stejný text i rychlost jako starý (6/6, large-v3 i turbo). Od commitu
  0f7a5c2 (3. 10.) je tenhle build v repu jako `whisper\` a build instalátoru ho bere sám (`whisper-next\` 13. 10. už
  nebyla a `--whisper-dir whisper-next` skončil chybou).
- **Co instalátor dělá** (`installer/orbit.iss`): instalace jen pro uživatele do `%LOCALAPPDATA%\Programs\Orbit`
  (pevné `AppId`, česky, na anglických Windows anglicky): `runtime\` (Python 3.13.7 embeddable + balíčky, PySide6
  zmenšený z 640 MB na 46 MB jen na moduly, které `app\` importuje), `app\`, `Orbit.pyw`, `assets\`, `whisper\`,
  `licenses\`, `THIRD_PARTY_NOTICES.md`; celkem ~294 MB (bez Piperu ~198 MB). Modely v něm
  nejsou, stahuje je průvodce do datové složky `%LOCALAPPDATA%\Orbit` (`paths.py`). Zástupce v nabídce Start,
  na ploše jen na přání, po instalaci „Spustit Orbit“ (ne při tiché instalaci). Aktualizace nejdřív smaže
  `runtime\Lib`, `app\`, `assets\`, `whisper\`, ať nezůstanou soubory, které nová verze nemá. Data zůstávají.
- **Aktualizace nemaže celý `runtime\`** (od 7. 10.): každá relace Claude Code spouští `runtime\python.exe` pro hooky
  a stavový řádek (stačí jim stdlib vedle něj), dřív během aktualizace selhávaly. Soubor, který běžící hook zrovna
  drží, instalátor přejmenuje na `*.orbit-old` a vedle zapíše nový (`MoveAsideIfInUse`; běžící exe a DLL smazat
  nejde, přejmenovat ano, ověřeno), jinak by tichá instalace z `install.ps1` (`/SUPPRESSMSGBOXES`) skončila na Abort.
  `restartreplace` bez práv správce nic nedělá. Zbytky smaže další aktualizace nebo odinstalace; nová menší verze
  Pythonu by tam nechala staré soubory (nepoužité). **Ověřeno 8. 10. na 1.1.0** testovací variantou `.iss` (jiné
  `AppId`, mutex, zástupce; data a Claude Code v tempu): `/VERYSILENT` aktualizace, během které se `runtime\python.exe`
  spouštěl každých 100 ms (120 spuštění, všechna prošla), skončila kódem 0, `python.exe`, `python313.dll`
  a `vcruntime140.dll` šly stranou jako `*.orbit-old`, nový `python.exe` běží, další aktualizace zbytky smazala,
  `tasks.json` zůstal beze změny, odinstalace smazala složku i `*.orbit-old` a data nechala. **Pozor:** při spouštění
  python.exe každých 100 ms už od startu Setupu visel Setup ~10 min na kontrole Restart Manageru (`RmGetList`, PID
  se recyklují) a pokračoval až po zastavení smyčky; po 1 s trvala kontrola 2–3 s. Skutečné hooky tak husté nejsou.
  Kdyby se to stalo, `CloseApplications=no` v `orbit.iss` kontrolu vypne (běžící Orbit hlídá mutex, držené soubory
  `MoveAsideIfInUse`). Neověřeno: `/SILENT` (jak instaluje `install.ps1`) a hodně dlouhá cesta instalace.
- **Spouští se `runtime\pythonw.exe -s Orbit.pyw`.** `runtime\python313._pth` nastaví `sys.path` jen na balíček
  a schválně **nemá `import site`**: s ním by Python přidal uživatelovo `%APPDATA%\Python\Python313\site-packages`
  (u Pepy jiný numpy a PySide6) i u spuštění, která Orbit dělá sám bez `-s` (klíč Run, hooky, stavový řádek,
  MCP server agenta). Balíček žádné `.pth` nemá, `verify_bundle.py` to hlídá a běží bez `-s`.
- **Běžící Orbit**: instalátor i odinstalátor ho poznají podle mutexu `Local\Orbit-single-instance` (stejný má
  každá kopie, takže Pepův vývojový Orbit a nainstalovaný nepoběží naráz – schválně, bojovaly by o klávesu
  a mikrofon) a řeknou, ať ho uživatel zavře.
- **Odinstalace**: nejdřív `runtime\python.exe -s Orbit.pyw --cleanup` (hooky a stavový řádek *této* instalace pryč,
  původní stavový řádek zpět, jen její hodnota v Run; jiná kopie Orbitu zůstane, viz Spuštění), pak otázka, jestli
  smazat i `%LOCALAPPDATA%\Orbit` (nastavení, slovník, poznámky, nahrávky, modely); výchozí Ne, tichá odinstalace
  data vždy nechá.
- **Vydané verze**: 1.0.0 (7. 10. 2026), **1.1.0 (8. 10. 2026)**: Poznámky a úkoly, barvy relací, zprůhlednění
  tlačítka v nastavení, nové relace agenta ve Windows Terminalu a opravy ze 7. 10. po vydání 1.0.0 (Piper ve vlastním
  procesu, potvrzování agenta, překreslování…); `Orbit-Setup-1.1.0.exe`,
  81 942 251 B, SHA-256 `b9b24530…6714771`; **1.2.0 (13. 10. 2026)**: verze Claude Code v panelu s aktualizací
  jedním klikem, zbalení do ikonky, příkazy na pozadí (a jejich zastavení přes mod `orbit-mozek` 0.3.0), Historie
  relací, oblíbené složky a nové repo pod pluskem, úpravy textu hlasem, „Smaž to / Vyber to / Vlož to znovu“,
  historie diktátů, ztlumení hudby při diktování, limity z relací, nový reproduktor; `Orbit-Setup-1.2.0.exe`,
  82 004 811 B, SHA-256 `09b18ed1…636922d5` (celý v `web/release.json`). Ověřeno: build s kontrolou balíčku
  (`verify_bundle.py`), stažený soubor z webu má stejný SHA-256, rozsahy bajtů (206). Tichou instalací se 1.2.0
  nezkoušela (`orbit.iss` se od 1.1.0 nezměnil). **1.3.0 (24. 10. 2026)**: kontrola přepisu Claudem s druhým
  rozpoznávačem Canary (onnx-asr v balíčku) a vložení až opraveného textu, pilulka „Přepisuji… / Claude kontroluje
  přepis…“ u tlačítka, ořez ticha za posledním slovem, 1000 nahrávek, model relací (Fable / Opus / Sonnet / Haiku
  při otevření i za běhu, mod `orbit-mozek` 0.5.0), animace zbalení a rozbalení, diktát tlačítkem myši do okna pod
  myší, tlačítko vrácené nad okna jiných programů, hluchý mikrofon, Autopilot (hovory přes Bland AI; do Česka zatím
  nevolá); `Orbit-Setup-1.3.0.exe`, 82 754 842 B, SHA-256 `69ab5122…25bbbfe4`. Ověřeno: build s kontrolou balíčku
  (`verify_bundle.py` i import onnx_asr a příprava zvuku pro Canary), 407 testů. Tichou instalací se nezkoušela
  (`orbit.iss` se nezměnil).
- Tichá instalace: `Orbit-Setup-1.3.0.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER` (Orbit se po ní nespustí),
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
- **Testy** (od 7. 10., stdlib `unittest`, 406 testů, ~110 s): `.venv\Scripts\python.exe -m unittest discover -s tests`
  (jen část: `-p "test_core*.py"`, `test_claude*`, `test_dist*`, `test_ui*`; `test_ui_*` zkouší metody `Dictation`
  na stubu a `VoiceAgent` s falešným procesem, bez Clauda). Samy si nastaví `ORBIT_DATA_DIR`/`ORBIT_CLAUDE_DIR`
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
  spouštění, `claude_setup.update` se zkouší s nahrazeným `_run` (`tests/test_ui_claude_version.py`).
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
  proto stránka nesmí spouštět žádný kód kromě tří souborů statistik (`.htaccess` jiné PHP zakazuje, viz Návštěvy webu).
- **První verzi (Bodoni Moda + Barlow, zlatá na tmavě modré) Pepa odmítl jako „AI slob“**: chtěl designérskou práci,
  jiné písmo, hodně pohybu, hover efektů a JavaScriptu. Teď: nadpisy **Anybody** (variabilní šířka 50–150, tloušťka
  100–900, jen od 48 px), text **Mona Sans**; barvy aplikace (akcent `#5B9DFF`, přepínatelný na fialovou/tyrkysovou
  tečkami v menu jako v Orbitu) na `#04060C`, žádná zlatá. Efekty: hvězdné pole na canvasu (letí podle rychlosti
  scrollu, nad hlavním tlačítkem hyperprostor), písmena nadpisu reagují na kurzor, vlastní kurzor se štítky,
  magnetická tlačítka, pás povelů tlačený scrollem, diktát odvíjený scrollem (připnutý, obří obrysové hodiny), věta
  o soukromí rozsvěcovaná po slovech, tok paketů ve schématu, panel Clauda hrající scénu ke každé funkci, pravítko
  instalace. Vše respektuje `prefers-reduced-motion`.
- **Žádné „poslouchání“ v úvodu** (8. 10., Pepa: „proč bych mluvil, když ta stránka mě neposlouchá a nemá přístup
  k mikrofonu, to je zavádějící“): podržení nadpisu (myš, prst, mezerník) dřív přepnulo kurzor na „Mluv“, hvězdy
  seřadilo do hlasové vlny a písmena nadpisu se chvěla, pod nadpisem byla nápověda „Podrž nadpis nebo mezerník…“.
  Celé je to pryč, i s kódem. Ukázka diktování v sekci Diktování zůstala, ta je výslovně „jen ukázka“. Nic, co
  vypadá, že stránka poslouchá, nevracet.
- Posudek nezávislého agenta „art director“ pomohl: odhalení písmen přes vlasový řez vypadalo rozbitě (teď jen
  průhlednost + rozmazání), všechny sekce měly stejnou šablonu a tři mřížky stejných karet (teď každá jinak), Anybody
  v malých velikostech působilo jako e-sportovní písmo. Kontrola: Playwright v `scratchpad`, snímky desktop + 390 px.
- Písma jsou přímo na webu (žádné Google Fonts), žádné cookies ani cizí skripty. CSP + `Permissions-Policy: microphone=()`.
  Do 24. 10. stránka nic neměřila a slibovala „nemá analytiku“; od té doby si návštěvy počítá sama (další bod) a text
  v Soukromí i otázka „Co o mně ví tahle stránka?“ to říkají. Když se měření změní, opravit oba texty.
- **Návštěvy webu** (od 24. 10., Pepa: „jak fungují konverze na M-texu … admin stránku, kde bych viděl konverze, kdo na
  webu byl, na co koukal“, pak „ve vzhledu Orbitu, ten na M-texu se mi tak moc nelíbí … ať vím, kdo tam přišel a ať
  jsou to relevantní návštěvy, ne boti“). Vzor je karta „Co se právě dělo“ v Konverzích M-texu, vzhled je Orbitu.
  - **https://orbit.easya.cz/admin/** (`admin/index.php`, `admin.css`, `admin.js`): shrnutí větou, dlaždice (lidé na webu,
    stažení instalátoru, instalace příkazem, zkopírované zadání, teď na webu; srovnání se stejným úsekem předtím), graf
    den po dni (dnes po hodinách; návštěvy se stažením nebo instalací v akcentu, ostatní šedomodře: dvojice prošla
    validátorem dataviz proti `#0E1424`, skrytá tabulka pro čtečky), **Kdo přišel** (návštěva = řádek jako relace v panelu
    Orbitu: proužek podle výsledku, čas, doba na stránce, země, zařízení a prohlížeč, odkud, části stránky s časem
    a kroky: stažení s tlačítkem, zkopírování, funkce v panelu, otázky, video se zvukem, ukázka diktování, instalace
    v PowerShellu; krátké návštěvy jen s úvodem sbalené po dnech; „To jsem byl já“ ji smaže, dvě kliknutí), vpravo cesta
    po stránce s největším únikem, odkud, země, na čem (kolik z Windows), co si prohlédli, odkud stahují. Období Dnes /
    7 / 30 / 90 dní. Bez rodových tvarů u návštěvníků.
  - **Měření** (`assets/visit.js`): žádná cookie, nic v prohlížeči, jedno náhodné id na načtení stránky v paměti.
    Začne, až je stránka opravdu vidět (ne karta na pozadí, ne prerender), DNT / Global Privacy Control = nic. Posílá
    přes `sendBeacon` na `api/hit.php`: `start` (odkud bez dotazu, utm, kotva, `navigator.webdriver`), `ev` (download
    s místem tlačítka, copy, github, script_view, video_sound, demo, feature po kliku nebo 1,2 s najetí, faq, theme, link)
    a každých 30 s, při skrytí a odchodu `end` (sekce `{id: [kdy poprvé, ms na obrazovce]}` přes IntersectionObserver na
    čáru uprostřed obrazovky, viditelný čas, video, interakce `i`, `x` = odchod, pak už „teď na webu“ nesvítí). Sekce =
    `id` v `index.html` (`top` … `konec`, závěr má `id="konec"` kvůli tomu), seznam je v `visit.js` i `Stats::SECTIONS`.
  - **Server** (`lib/stats.php`, PHP 7.4+, ověřeno 8.0 a 8.3): `data/hits-RRRR-MM-DD.php` po řádcích JSON za strážním
    řádkem `<?php exit; ?>` (servírované omylem nic neukáže), flock, strop 20 MB na den, 400 dní. IP se neukládá: `vh`
    (prohlížeč + síť) a `ih` (síť) jsou HMAC s klíčem serveru (`data/secret.php`, vznikne sám) a datem, IPv6 po /64.
    IP návštěvníka je `CF-Connecting-IP`, jen když požadavek přišel z rozsahů Cloudflaru, země `CF-IPCountry` (ověřeno
    24. 10.: chodí), město jen se zapnutým „Add visitor location headers“ v Cloudflaru. Limit 240 požadavků na síť za
    10 min. Neměří se síť majitele (jako na M-texu) ani prohlížeč přihlášený do administrace (cookie
    `orbit_no_stats` na rok). IP majitele **není v kódu** (repozitář je veřejný): je v
    `~\m-tex\private\orbit-owner-ips.txt` (IP na řádek, `#` komentář), `publish.py` z něj udělá `data/owner.php` a nahraje ho se
    stránkou, `Stats::ownerIps()` ho čte (od 24. 10., předtím konstanta `OWNER_IPS`; bez souboru se měří všichni).
  - **Jen lidé, ne roboti**: robot podle user-agenta (boti, náhledy odkazů, headless, Lighthouse, curl, Python…, i
    Chrome nebo Firefox pod 90 jako scraperové pooly na M-texu) nebo `navigator.webdriver`; návštěva bez scrollu, pohybu
    myši, dotyku nebo kliku pod 8 s na obrazovce = „otevření bez prohlížení“. Obojí jen počet v poznámce seznamu.
    Načtení stránky téhož prohlížeče ze stejné sítě do 30 min = jedna návštěva (přes den, mezi dny se spojit nedají).
  - **Instalace příkazem**: `install.ps1` a `download/latest.json` jdou přes `api/serve.php` (přepis v `.htaccess`, cíl
    **musí být absolutní** `/api/serve.php`: s relativním vrátil hosting 404 a instalace příkazem byla 24. 10. asi 3 min
    rozbitá). Soubor jde ven celý a beze změny, počítá se až po něm. PowerShell na `install.ps1` = spuštěná instalace,
    na `latest.json` = stahuje instalátor; Claude, prohlížeč, curl se ukážou jako čtení skriptu. Připojí se k návštěvě ze
    stejné sítě do hodiny po ní, jinak „jen příkaz“.
  - **Heslo**: `python web\publish.py --admin-password` vygeneruje nové, na server nahraje jen otisk PBKDF2 (400 000 ×,
    `data/admin.php`) a heslo zapíše do `~\m-tex\private\orbit-admin.txt` (mimo veřejné repo, vedle přihlášení FTP).
    Změnit jde i v administraci (odhlásí ostatní prohlížeče). Cookie `__Host-orbit-admin` podepsaná klíčem serveru,
    30 dní, SameSite=Strict, POST jen z vlastního webu a s CSRF tokenem, 5 špatných hesel za 15 min ze sítě nebo 20 za
    hodinu odkudkoli = čekání. Administrace má vlastní CSP bez inline skriptů (`admin/.htaccess`).
  - Ochrana: `.htaccess` povolí jen `hit.php`, `serve.php`, `index.php`; jiné PHP, `lib/` a `data/` nejdou otevřít
    (403, k tomu přepis na 404 a vlastní `Require all denied` v obou složkách). `publish.py` z `site/data/` nahraje jen `.htaccess` (a `.gitignore` ho drží mimo git),
    nahrává jedním spojením a `.htaccess` s přepisem až po `api/serve.php`.
  - Testy `tests/test_dist_web_stats.py` (skutečné PHP přes `php -S`, bez něj se přeskočí: `ORBIT_PHP`, PATH,
    `~\tools\php83`). Celé kolo s prohlížečem (člověk z GitHubu, dva roboti, neviděná karta, instalace v PowerShellu,
    přihlášení, snímky 1440 a 390 px) jde Playwrightem z `meteoradar\node_modules`, `navigator.webdriver` vypne
    `--disable-blink-features=AutomationControlled`.
  - Na živém webu nejde z Pepovy sítě vyzkoušet, že se návštěva zapíše (síť se neměří): z mobilu na datech, pak
    „To jsem byl já“. Ověřeno 24. 10. živě: instalační skript a `latest.json` přes PHP stejné bajty, `lib/` a `data/`
    403, přihlášení, Cloudflare a země, poznaná síť majitele. Zápis návštěv jen lokálně.
- **Preloader** (od 20. 10., Pepa: „hezký preloader … mega luxusní, ať to matchuje celou stránku“): uprostřed logo
  Orbitu (stínovaná koule, při letu zploští na logo z menu), měsíc během načítání obkreslí svou dráhu (tečkovaná jako
  halo videa → plná, kometa v barvě akcentu), kolem prach v rovině dráhy, slovo „Orbit“ pod ním tloustne písmeno po
  písmenu (Anybody wdth 50 → 125, wght 100 → 700 = přesně logo v menu), dole linka s počítadlem. Odchod (1,7 s):
  nadechnutí, záblesk a dvě rázové vlny po rovině dráhy (jako rozbalení v aplikaci), závoj se otevře měkkým kruhem od
  planety, prach odletí v čarách, hvězdy webu vyletí hyperprostorem a logo i slovo **odletí na logo v menu** (ověřeno
  na pixel i s polohou měsíce, Chromium, Firefox, WebKit, i na 390 px); když menu není vidět (načtení níž), rozplynou
  se. Kód: markup a skript hned pod `<body>` v `index.html` (musí běžet od prvního vykreslení, `site.js` je až na konci),
  styly `.preloader`/`.pl-*` v `site.css`. `window.OrbitPreloader` (`onReveal`, `onDone`, `ready`, `covered`): `site.js`
  pod závojem nekreslí hvězdy ani nadpis, úvod stránky (hyperprostor, skládání nadpisu, video od začátku, položky menu)
  spustí až `onReveal`, Lenis pustí až `onDone` (do přistání se nescrolluje). Odchází, když jsou písma, `site.js`
  (`ready()`) a `load` (na ten po `ready` čeká nejvýš 1,2 s, `load` čeká i na metadata videa), nejdřív po 1,5 s
  viditelného času, později v relaci prohlížeče po 0,7 s (`sessionStorage` `orbit-pl`), nejpozději po 6 s. Bez JS,
  s omezením pohybu a při tisku není; bez GSAP odejde sám (`load` + 1,5 s); bez skriptu ho CSS za 1 s schová.
- **Plynulost preloaderu** (měřeno Playwrightem: headless Chromium s `--use-angle=d3d11` na RX 9070 XT, mezery mezi
  snímky a čas JS v rAF, pak trace Chromu):
  JS je 1–5 ms na snímek, zdržovalo GPU. Celoobrazovkové přechody a cesta se stovkami oblouků na plátně stály 13–28 ms
  GPU na snímek → záře jsou dvě CSS vrstvy (jen opacity/transform), závoj je pozadí a jediný přechod až při otevření,
  prach jsou sprity. Rozmazané znaky nadpisu, kterým se každý snímek mění osy písma, se překreslovaly → osy stojí, dokud
  se znak neskládá (platí pro všechny kinetické nadpisy). Text a tlačítko pod nadpisem (`.hero .rv`, široký stín tlačítka)
  mají během prolnutí `will-change`, pod závojem opacity 0,001 (úplně průhledné Chrome nekreslí a první vykreslení pak
  stojí snímek). Výsledek: odchod 100–101 snímků ze 101 včas (dřív p90 33 ms, nejhorší 117 ms). `will-change` na
  znacích nadpisu ani na položkách menu nepomohl (spíš uškodil). Neověřeno: skutečný Chrome s oknem na Pepově monitoru.
- **Úvodní video** (Remotion, viz níže) je ve `web/site/assets/video/` (`orbit.mp4`, `orbit.webm`, `poster.jpg`),
  hraje ztlumeně ve smyčce, tlačítko pustí od začátku se zvukem. Bez `orbit.mp4` (nebo s `--no-video`) je místo něj
  animovaný orrery. Hudba „Mountains“ (Andrew Ev, Mixkit) je uvedená v patičce.
- Tlačítko „Stáhnout pro Windows“ na konci videa nejde kliknout (Pepa: „je na hovno“), proto na něj v čase
  103,18–113,86 s přiletí shora skutečné tlačítko a levituje přesně nad ním (`#stageCta`; ve videu je 490×76 px se
  středem na 818, 855 v 1920×1080, velikost přes `cqw`, o kousek větší, aby to nakreslené při levitaci nevykouklo).
  Časy jsou z `video/src/scenes/Outro.tsx` (takt po konci bicích, 53; nakreslené tlačítko vyskočí v 104,2 s): když
  se konec videa přestříhá, musí se změnit `CTA_IN`/`CTA_OUT`/`END_FRAME`/`POP` v `site.js` (do 20. 10. 64,15–74,8 s,
  video 76 s; do 24. 10. 87,58–98,23 s, video 99,4 s). Se zvukem video nehraje ve smyčce: po konci skočí na záběr
  v 109,0 s, tlačítko zůstane a objeví se „Přehrát znovu“. Dokud není instalátor, tlačítko říká „Instalátor už brzy“ a vede na instalaci.
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
- **Poznámky na webu** (od 8. 10.): replika panelu má vlevo nad ním sešit s číslem aktivních (`#wNotes`, jako
  `_notes_center` v aplikaci), karta „Poznámky a úkoly“ je **třetí** (za Relace) a hraje scénu `poznamky` v `site.js`
  (otázka v panelu a bublina jako `Dictation._check_tasks`, klik na bublinu, „otevírám…“ → „otevřeno ✓“ a nová relace
  `#s4`). Jako poslední karta nešla: sekce už končí, lepivý panel odjel nahoru a na 1280×720 byl sešit mimo obraz.
  Zmínky jsou i v úvodu, sekci Claude, soukromí (úkol dostane relace až po potvrzení, jinak zůstává v počítači),
  požadavcích, otázkách (bez Claude Code, hlas na internet, aktualizace, odinstalace) a v orrery bez videa.
- **Verze Claude Code a zbalení na webu** (od 13. 10., verze 1.2.0): replika má pod panelem pilulku `#wVer` (jako
  aplikace: „Claude Code 2.1.296 ✓ nejnovější“), v pruhu za barvami bublinku s čárkou `#wFold` (jako aplikace) a u mikrofonu skrytou ikonku
  `#wIcon` (symbol `#i-orbit` = favicon). Dvě poslední karty: „Verze Claude Code“ (scéna `verze`: nová verze →
  Aktualizovat → „Aktualizuju…“ → ✓ a bublina) a „Zbalit do ikonky“ (scéna `zbalit`: `.widget.folded` celou
  repliku jen zprůhlední, ne vyjme z layoutu, aby stránka neposkočila, a ukáže ikonku na místě mikrofonu). Ověřeno
  Playwrightem: 1440×900, 1280×720 (obě karty se při scrollu kolečkem rozsvítí a replika je celá vidět) i 390 px.
- **Zbalení na webu přesně jako v aplikaci** (od 20. 10., Pepa: „dej tam tu přesnou animaci, která je v aplikaci“):
  scéna `zbalit` volá `fold(on, true)` a ta pustí přepis `app/foldfx.py` v `site.js` (`startFx`, `fxFrame`, `fxGlow`,
  `fxRing`, `fxStars`, `fxShimmer`, `fxIcon`; stejné křivky, časy 800/740 ms, 56 hvězd, pořadí kreslení). Skutečné
  části repliky se přepnou hned a čekají skryté (`.fx-quiet`), jejich kopie (bez id, `aria-hidden`) se točí jako
  skupiny kolem středu mikrofonu (čtyři: tři slabší na rozmazání), plátno nad nimi kreslí hvězdy, záři, rázové vlny
  a ikonku (`_paint_icon` v jednotkách favicony). Délky z aplikace se násobí velikostí mikrofonu / 52 px, layout se
  čte jen na začátku (i s `zoom` úzkého layoutu). Animaci hned ukončí `baseline()`, jiná scéna, `.off` (mimo
  obrazovku), skrytá karta a změna šířky okna; s omezením pohybu jen přepne. Kopie se neskrývají, jen jsou skoro
  průhledné (0,001): skryté by Chrome při zvětšení kreslil znovu (špičky 33–50 ms). Ikonka `.w-icon` má 0,846
  velikosti mikrofonu a sedí na jeho středu (dřív 52 px na pevném místě, na úzkém layoutu vedle). Ověřeno
  Playwrightem proti snímkům z aplikace (`video/out/fold-ref`) v 1440×900 a 390×844, Firefox i WebKit, snímky nejvýš
  16,8 ms (Chromium s `--use-angle=d3d11`). Neověřeno: skutečný Chrome s oknem.
  Ostatní novinky 1.2.0 (úpravy hlasem, „Smaž to“, historie diktátů a relací, plusko, příkazy na pozadí) na webu
  zatím nejsou.
- **Kontrola přepisu na webu** (od 24. 10., verze 1.3.0): poslední karta v sekci Claude „Kontrola přepisu“ (scéna
  `kontrola` v `site.js`: mikrofon repliky červený, oranžový, vedle něj pilulka `#wChip` „Přepisuji…“ a „Claude
  kontroluje přepis…“ jako `ui.StatusChip`, pak bublina „Opraveno…“; `dictation()` nastavuje `data-state` mikrofonu
  a pilulku), `Stats::FEATURES` ji zná. „Jak přesně píše“ ukazuje měření z 24. 10. (181 vět FLEURS: large-v3 9,3 %,
  turbo 10,4 %, s kontrolou přepisu 4,7 %; VoxPopuli 12,7 → 9,4 % v poznámce), otázka o slabší grafice taky; „Kolik
  Orbit stojí?“ říká, kolik tokenů bere kontrola (~2 500 Haiku na diktát, ~0,0003 $ podle ceníku API). Popis videu
  pro čtečky obrazovky zmiňuje novou scénu.
- Stránka odkazuje na GitHub (menu, instalace, otázka „Kolik Orbit stojí?“, patička).
  Bez `--installer` se nahrají jen změněné soubory stránky. Podrobnosti a FTP (FTPS přes `ftp.m-tex.cz`, heslo
  v `~/m-tex/private/ftp.netrc`, Windows curl useknul soubory) v `web/README.md`.
- **Kolo oprav 7. 10. večer** (Pepa: „neplynulé scrollování a náhodné létající hvězdy“; 12 auditorů, 9 balíčků oprav
  s nezávislou kontrolou, commit 24f6b87). Příčiny, ať se nevrátí:
  - *Scroll*: Lenis během dojezdu kolečka přepisoval nativní scroll (klávesy, posuvník, prostřední tlačítko) a táhl
    stránku zpět; teď mu tyhle vstupy dají přednost. Kotvy jedou plynule (ne expo-out se skokem 500 px). Smyčka
    `frame()` nesmí číst layout (`getBoundingClientRect`) ani kreslit sekce mimo obrazovku; nekonečné CSS animace
    se pod obrazovkou zastaví, eq pruhy jdou přes `transform`.
  - *Hvězdy*: rychlost se násobila časem snímku dvakrát (Lenis `velocity` už je za snímek), jeden práh přepínal
    všechny hvězdy naráz na čáry, hyperprostor se spouštěl i bez pohybu myši (tlačítko přijelo pod kurzor), na mobilu
    každá změna výšky (adresní řádek) hvězdy vygenerovala znovu. Teď rychlost podle času, stopa po hvězdách zvlášť,
    warp jen po skutečném pohybu myši nad tlačítkem, při změně jen výšky se pole nepřegeneruje.
  - Video má `preload="none"` a hraje, až je vidět (bez JS jen plakát), má tlačítko pauzy. CSS/JS mají v `.htaccess`
    cache na rok (mají `?v=`). `install.ps1` odmítne běžet, když Orbit běží (mutex), a kontroluje `latest.json`
    (jméno, formát SHA-256, velikost). Přibyl `robots.txt`.
  - Měřeno v headless Chromu (1440×900, 9000 px kolečkem): snímky nad 25 ms 23 → 6–9, p95 33 → 17 ms.
  - **Nehotové, příště**: animované nadpisy pořád zapisují `font-variation-settings` každému písmenu v každém snímku
    (největší zbývající cena, 3–20 ms na snímek); první pokus (zaokrouhlit osy, psát jen při změně) rozkmital vlnu
    nadpisu v úvodu, proto nevyšel. Na rozhodnutí Pepy: nový nadpis sekce Claude Code, tlačítko „Zastavit pohyb“,
    přestavba sekce instalace, menší verze videa pro mobil (nový export ve `video/`), přesměrování HTTP→HTTPS
    v Cloudflare. Dál CSP s hashem místo `'unsafe-inline'`, podmnožina písem, 404/sitemap/JSON-LD.
  - Testy webu: Playwright jen headless (Orbit píše diktát do okna v popředí). WebKit v Playwrightu na Windows nepřehraje
    ani MP4, ani WebM a `load` pak může viset: čekat na `domcontentloaded`, video v testu vypnout.

## Úvodní video (od 3. 10. 2026)

- Pepa chtěl „nejkrásnější Remotion video“ o Orbitu úplně nahoru na web: screeny, benefity, hudba, výzva ke stažení.
  Projekt `video/` (podrobnosti v `video/README.md`), 1920×1080, 115,1 s (do 20. 10. 76 s, do 24. 10. 99,4 s),
  stříhané na takty hudby.
- **Kontrola přepisu ve videu (24. 10.**, Pepa: „dej to jako další feature a do Remotion videa, takže to přegeneruj“):
  nová fráze (8 taktů, 44–52) po zbalení, před závěrem: do relace z plusku se nadiktuje „Dej to na git, pushni to na
  git.“, vlevo „Whisper slyšel „Daytona Git, Pushnitona Git.““, vedle kruhů pilulka „Přepisuji…“ a „Claude kontroluje
  přepis…“ (replika `ui.StatusChip`: `StatusChip` v `OrbitWidget.tsx`), do terminálu jde opravená věta, tichá bublina
  „Opraveno: Daytona → Dej to na, Pushnitona → pushni to na…“ (zalomená jako v Qt), pak „Až o polovinu méně chyb.“
  s grafem (FLEURS 9,3 → 4,7 %, VoxPopuli 12,7 → 9,4 %) a v závěru na drahách „Kontrola přepisu“. Proč celá fráze
  a až po dropu: před dropem by se musela posunout hudba proti scénám (fráze jsou svázané s úvodem skladby), po dropu
  stačí skok na konec skladby o frázi později (`build_music.py`: `CUT_FROM` 193 → 225; basa a kopák taktů 225–257
  jdou jako fráze před nimi, obálka basy taktu 225 sedí s 193 na r = 0,83, žádný break). `time.ts`: `CUT_BAR` 52,
  závěr počítá takty od něj. MP4 a WebM jsou úměrně delší (stejný datový tok).
- **Nová verze 20. 10.** (Pepa: „předělej úvodní video, máme spoustu nových vylepšení … ať je tam i ta animace
  zbalení“): hudba začíná o 4 takty dřív (tichý úvod skladby) a groove po dropu je o frázi delší (`build_music.py`),
  přibyla scéna „Opravíš hlasem.“ (`scenes/Edit.tsx`: „Smaž to.“ smaže poslední diktát, s Ctrl „Napiš to
  formálněji.“ a text přepíše Claude, tužka místo mikrofonu), panel se na dropu rozbalí z ikonky Orbitu a v poslední
  frázi plusko otevře novou relaci (nabídka s modelem Sonnet 5.5, složka web, okno Windows Terminalu v modré barvě
  složky), aktualizace Claude Code z pilulky s verzí a zbalení do ikonky a zpět. Replika panelu je přepsaná podle
  aplikace ze 16. 10. (čipy telefonu, plusku, historie relací a historie diktátů, zbalení, barvy složek, šroubovák
  a fajfka, pilulka s verzí, nová hlavička „limit 5 h se obnoví v …“), animace zbalení je přepis `app/foldfx.py`
  (`video/src/components/FoldFx.tsx`, snímky ověřené proti `FoldFx.frame(u)` z aplikace, `grab.py` je ukládá do
  `video/out/fold-ref/`). Autopilot ve videu není (do Česka Bland nevolá). Tlačítko na konci je na stejném místě,
  jen o 23,43 s později (časy na webu viz Web).
  Na webu od 20. 10. večer (`publish.py`, s ním šel ven i preloader ze stejného dne; Pepa to odsouhlasil). Ověřeno na
  živém webu: video a WebM vrací 206, délka 99,44 s, skutečné tlačítko v 90,5 s na nakresleném, scéna `zbalit` hraje
  animaci, bez chyb v konzoli (Playwright, headless). Neověřeno: přehrání se zvukem v Pepově Chromu a iPhone.
  Zbalení a model relací ve videu jsou z aplikace po vydání 1.2.0 (16. 10.): instalátor na webu je zatím 1.2.0.
- Vzhled sleduje web (barvy, písma Anybody + Mona Sans, „dýchající“ nadpisy z `site.js`). Když se změní web, změnit
  `video/src/lib/theme.ts`, písma v `video/public/fonts` a vyrenderovat znovu. Aplikace ve videu je replika
  `app/ui.py` v Reactu (`video/src/components/OrbitWidget.tsx`, `Bubble.tsx`); po změně vzhledu aplikace ji upravit.
  Ověřené proti skutečnému renderu z Qt (`video/capture/grab.py`, ukázková data, 3× rozlišení).
- Od 8. 10. ukazuje i Poznámky bez přestřihu: replika panelu má sešit s „2“ (`NotesChip`, ověřeno proti Qt
  `FloatingButton.set_notes_count(2)`) a v závěru krouží „Poznámky a úkoly“ (vnější dráha, fáze 3,9, nikde se
  nepřekrývá s jiným popiskem). Tlačítko na konci je na stejném místě. „Kontrola přepisu“ (24. 10.) krouží na
  prostřední dráze (fáze 4,15), ověřeno snímky po celý závěr.
- Hudba: „Mountains“ (Andrew Ev, Mixkit, licence bez uvádění autora, nesmí se šířit samostatně, proto není v gitu).
- Video má být srozumitelné i ztlumené (na webu hraje bez zvuku), proto je všechno řečené i v obraze.
- Render: `npx remotion render Orbit out/orbit-master.mp4 --crf 14` (~2 min), pak `node scripts/export-web.mjs`
  (2 průchody, 1,95 a 1,65 Mbit/s: u 99,4 s MP4 25,1 MB a WebM 21,3 MB, u 115,1 s od 24. 10. 29,0 a 24,7 MB;
  datový tok se kvůli délce nesnižoval, video má `preload="none"`). Na nahrání webu je `web/publish.py`.
- Chrome kreslí text na neprůhledném pozadí subpixelově (ClearType) a ve videu pak má tenké písmo modré a oranžové
  okraje: text na čipech, kruzích, oknech a v nabídce je proto ve skupině s `opacity: 0.999` (šedé vyhlazení).
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
se kvůli tomu 7. 10. přepsala (záloha lokálně ve větvi `backup/before-author-rewrite`). Postranní seznam
Contributors na úvodní stránce repozitáře pak ještě 8. 10. ukazoval i `claude` a `joseKot` (vlastní mezipaměť, API
`/contributors` i `/stats/contributors` už měly jen josefkotran). Pomohlo přepnout přes API výchozí větev na dočasnou
kopii `main` a zpět a kopii smazat; seznam se do 2 minut přepočítal. Kontrola: stránku vykreslit (Playwright), seznam
se načítá dodatečně, v HTML není.
`whisper-server.exe` má 59 MB, GitHub jen varuje (limit 100 MB);
ve `whisper/` je největší `ggml-vulkan.dll` (56 MB). Výstupy buildu (`build/cache`, `tools`, `dist`, `output`)
v gitu nejsou.

## Nápady na další práci (Pepa zatím nevybral)

Historie diktátů, úpravy textu s Ctrl a „Smaž to“ jsou od 8. 10. hotové (viz Vrátit, opravit a upravit diktát).
Další náměty jsou v reportu `reports/Diktovací nástroje a podněty pro Orbit.md` (seřazené podle přínosu).

1. Doladění na jeho hlas z `recordings/` (LoRA i na enkodér, podle studie stačí málo minut opravených nahrávek).
   Od 24. 10. se drží 1000 nahrávek a `build/eval_dictation.py` měří na diktátech opravených v historii; PyTorch pro
   RX 9070 XT na Windows existuje (ROCm 7.2). Nejdřív pár desítek opravených diktátů jako měřítko.
2. Vlastní ikona pro Orbit (teď je to pořád ikona mikrofonu).
3. Z reportu: Esc během držení klávesy zahodí nahrávku, klávesa pro „Odešli“ podle
   aplikace, whisper.cpp 1.9.5 (opravy Flash Attention ve Vulkanu) změřit na nahrávkách, agent čte odpověď od
   první hotové věty. (Ticho za posledním slovem od 24. 10. řeší `trim_tail`, Silero VAD už není potřeba.)
4. Canary rychleji: na grafice s fp16 enkodérem a dekodérem s cache (Masterx export má `decoder-kv`/`cross-kv`),
   nebo až ho umí whisper.cpp (od 1.9.0 umí Parakeet); oprava by přišla o ~1 s dřív.
