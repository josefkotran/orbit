# Orbit – kontext projektu

Orbit je malý pomocník pro Windows, který běží v oznamovací oblasti a jako plovoucí tlačítko nad všemi okny:

1. **Diktování česky push-to-talk** do libovolného okna. Rozpoznávání běží lokálně na grafice (whisper.cpp s Vulkanem
   a model Whisper large-v3), zvuk nikam neodchází.
2. **Přehled limitů Clauda** v panelu nad mikrofonem: 5hodinové okno, týdenní limit a týdenní limit Fable.

Projekt vznikl 24. 9. 2026 v jedné relaci Claude Code (spuštěné ve složce `C:\Users\josef\pepa`, což je nesouvisející
projekt s TWLanem). Původní název byl „Diktování“ a složka `C:\Users\josef\diktovani`, pak se přejmenoval na Orbit.

## Uživatel a prostředí

- Josef (Pepa) Kotran. Komunikuje **česky**, celé UI aplikace je česky. Často diktuje přímo přes Orbit, takže
  zprávy můžou obsahovat chyby z přepisu.
- Windows 11 Pro, Ryzen 7 5800X, 32 GB RAM, **AMD Radeon RX 9070 XT (16 GB, bez CUDA)**, Python 3.13 (`C:\Python313`).
- Mikrofon: USB headset **HyperX 7.1** (v MME se jmenuje `Headset Microphone (HyperX 7.1 `, zkrácené na 31 znaků).
- Předplatné Claude Max 20x. Claude Code je nainstalovaný přes npm (`%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe`).
- V uživatelských proměnných Windows je `ANTHROPIC_API_KEY` **bez kreditu** („Credit balance is too low“). `claude -p`
  ho upřednostní před předplatným, proto ho Orbit při spouštění Clauda z prostředí odebírá.
- GitHub účet `josefkotran`. `gh` CLI **není** nainstalované, git má přihlášení v Git Credential Manageru.
- Pracuje ve firmách HHW Hommel Hercules (nářadí) a M-tex (bytový textil), proto se ve slovníku hodí jejich názvy.

## Jeho aktuální nastavení (`config.json`, není v gitu)

Push-to-talk je **boční tlačítko myši vpřed** (`{"kind": "mouse", "code": 6}`), model `ggml-large-v3.bin`, mikrofon HyperX,
vkládání **psaním znaků** (`insert_mode: "type"`), bez mezery za textem, povely zapnuté, pípání zapnuté, panel Clauda
zapnutý, **ukládání nahrávek zapnuté** (`recordings/`), spouštění s Windows zapnuté. Průběžný přepis a učení
slovníku jsou zapnuté (výchozí). Slovník a opravy (`vocabulary`, `replacements`) doplňuje Claude, `learned_until`
je čas posledního přepisu z logu, který už Claude viděl.

## Struktura

| Soubor | Co dělá |
|---|---|
| `Orbit.pyw` | vstupní bod (spouští se přes `.venv\Scripts\pythonw.exe`, bez konzole) |
| `app/main.py` | třída `Dictation`: řídí stavy, Qt signály (`Bridge`) mezi vlákny, tray, menu, nastavení, polling limitů |
| `app/whisper_server.py` | spouští `whisper-server.exe` jako podproces, přepis přes HTTP, filtry halucinací, slovník, povely |
| `app/recorder.py` | nahrávání přes sounddevice (MME, 16 kHz mono int16), detekce „zvuk opravdu teče“, režim měřáku |
| `app/hotkey.py` | globální push-to-talk přes pynput low-level hooky, zachytávání nové klávesy, české názvy kláves |
| `app/inserter.py` | vložení textu: schránka + Ctrl+V (se zálohou schránky), nebo psaní přes `SendInput` Unicode |
| `app/ui.py` | `FloatingButton` (mikrofon + panel limitů), `SettingsDialog` (nastavení), kreslení ikony |
| `app/theme.py` | vzhled „noční signál“: barvy, QSS, `Toggle` přepínač, `LevelWave` živá vlna, tmavý titulek přes DWM |
| `app/claude_usage.py` | načtení limitů Clauda, parsování, české texty pro odpočty |
| `app/learning.py` | učení slovníku: přepisy z logu → `claude -p` → nová slova a opravy |
| `app/sessions.py` | přehled relací Claude Code: stav z hook souborů, kontext z přepisu, přepnutí okna, instalace hooků |
| `app/cc_hook.py` | hook, který Claude Code spouští (jen stdlib, rychlý): zapíše `sessions/<id>.<událost>.json` |
| `sessions/` | stavové soubory relací od hooku – nejsou v gitu |
| `app/config.py` | výchozí nastavení, cesty, popisky modelů |
| `app/winutil.py` | jedna instance (mutex), AppUserModelID, spouštění s Windows (registry), pípání |
| `whisper/` | `whisper-server.exe` (Vulkan build, 59 MB), `libwinpthread-1.dll`, licence whisper.cpp |
| `models/` | `ggml-large-v3.bin` (3,1 GB) a `ggml-large-v3-turbo.bin` (1,6 GB) – nejsou v gitu |
| `recordings/` | posledních 30 nahrávek (`.wav` + `.txt` s přepisem), když je zapnuté ukládání – nejsou v gitu |
| `orbit.log` | log aplikace včetně všech přepisů a časů – první místo, kam se dívat |

Závislosti: PySide6, sounddevice, numpy, pynput, requests (`requirements.txt`). Venv je `.venv` (vznikl ještě ve staré
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
  z MSYS2 shellu, jinak nenajdou DLL.
- Server běží jako podproces na volném portu, čeká se na `GET /health`. Proces je přiřazený do **Job objectu
  s KILL_ON_JOB_CLOSE**, takže zemře i při pádu aplikace a neblokuje VRAM.
- Parametry `/inference`: `language=cs`, `beam_size=5`, `temperature=0`, `no_timestamps=false`, `prompt` = česká věta
  + slovník, `response_format=json`. Flash attention je v serveru zapnutá defaultně.
- **Časová razítka musí zůstat zapnutá** (`no_timestamps=false`), i když je nepoužíváme. Bez nich Whisper
  (a) u nahrávek nad 30 s ztratil vše za prvním oknem: 35 s řeči vrátilo jen „Titulky vytvořil Jirka Kováč“,
  filtr to smazal a nevložilo se nic; (b) při pauze 2–5 s uprostřed nahrávky zahodil celou větu i pod 30 s.
  Ověřeno na Pepových nahrávkách slepených s tichem: s razítky se ve 24 testech neztratilo nic, rychlost ~ +3 %.
  `verbose_json` (segmenty) by přidal ~0,7 s na každý přepis, proto zůstává `json`.
- **`suppress_nst` je schválně vypnuté**, protože maže `: " ( ) /` (např. „10:30“ by se změnilo na „10 30“).
- Filtry: nahrávka kratší než 0,3 s nebo s max. RMS pod 200 (≈ −44 dBFS) se nepřepisuje. Maže se známá halucinace
  „Titulky vytvořil JohnyX“ a samostatné „Děkuji za pozornost / sledování“, „Titulky“, „Hudba“. Filtruje se po kusech
  (viz průběžný přepis), takže halucinace uprostřed nesmaže zbytek textu.
- Opravy (`replacements`, „comgit“ → „Comgate“) se aplikují na celý text diktátu: celá slova, bez ohledu na velikost
  písmen. Pak hlasové povely.

### Průběžný přepis (`live_transcribe`, měřeno na 30 Pepových nahrávkách)
- Během držení `Recorder._cut_at_pause` odřízne hotový kus v půlce pauzy a ten se hned přepisuje. Po puštění zbývá
  jen poslední kus, text se vkládá **najednou po puštění** (Pepa nechtěl psaní během mluvení). Kusy jedné nahrávky
  jdou za sebou v jednom vlákně (`Take`); do promptu každého jde konec předchozího textu (150 znaků).
- Parametry: pauza = bloky 30 ms s RMS < 150 (HyperX v tichu 1–11, řeč 150–800) aspoň 0,5 s, kus aspoň 6 s.
  Pepovy pauzy mezi větami mají 0,4–1,3 s, s prahem 0,6 s se 35 s diktát vůbec nerozdělil.
- Výsledek: průměrné čekání po puštění 1,99 → 1,62 s, 35 s diktát 6,0 → 1,4 s, 31 s bez pauz v druhé půlce 5,3 → 4,0 s.
  Nejhorší zpomalení +0,9 s: dělení těsně před puštěním, zbytek pak čeká na grafiku (každý požadavek má ~0,9 s
  pevné režie, whisper-server přepisuje jen jeden naráz). Proto minimum 6 s; s 3 s bylo víc chyb na hranicích.
- Cena: ~5 % slov se liší od přepisu celé nahrávky, většinou nevadí („teďka/teď“), občas horší na krátkém konci
  („obrať pořadí“ → „Obratíš po řadě“), občas lepší. Proto je to přepínač v nastavení.

### Učení slovníku (`learn_vocabulary`)
- Pepa chtěl, aby se slovník „vylepšoval sám podle logu“. Orbit sám nepozná, co je chyba (naučil by se i chyby),
  proto po každých 10 nových přepisech v logu pošle jejich **text (ne zvuk)** Claudovi, s Pepovým souhlasem.
- `claude -p --safe-mode --model sonnet --tools "" --no-session-persistence --output-format json --json-schema ...`
  bez `ANTHROPIC_API_KEY` a proměnných `CLAUDE*` (poběží na předplatném a nebude si myslet, že je vnořený
  v Claude Code). Výsledek je v `structured_output`, běh trvá ~16 s. Při chybě se to hodinu nezkouší.
- Slovník má strop 300 znaků: whisper.cpp z promptu drží ~224 tokenů a při přetečení zahazuje začátek.
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

### Push-to-talk
- pynput `Listener(win32_event_filter=...)`, zvolená klávesa/tlačítko se **potlačí** (`SystemHook.SuppressException`),
  aby ji ostatní aplikace nedostaly. Injektované události (naše vlastní Ctrl+V) se ignorují.
- AltGr na české klávesnici posílá falešný levý Ctrl se scan kódem 0x21D, ten se při zachytávání ignoruje.
- Myší hook se instaluje jen když je potřeba (vazba na myš nebo zachytávání), protože vidí každý pohyb myši.
- Hooky ignorují simulovaný vstup, proto se testuje přímo `PushToTalk._handle(...)`.

### Plovoucí tlačítko a vkládání
- Okno má `WS_EX_NOACTIVATE` (a `Qt.WindowDoesNotAcceptFocus`), takže klik nebere fokus cílovému oknu. Ověřeno testem.
- Levé tlačítko držet = push-to-talk, tažení (> 6 px) nahrávání zruší a přesune tlačítko, pravé = menu.
  Pozice se ukládá jako levý horní roh oblasti tlačítka (`button_pos`), panel limitů se zarovnává podle polohy
  na obrazovce (vlevo/střed/vpravo, nad/pod).
- Vkládání přes schránku obnoví původní obsah po 700 ms a vloží formáty, které vyřadí text z historie schránky
  (Win+V). V režimu psaní se nový řádek posílá jako **Shift+Enter** (aby chat zprávu neodeslal).
- Do oken spuštěných jako správce Windows vkládat nedovolí (UIPI).
- Po 3 s nečinnosti (stav idle, myš mimo, žádné menu) tlačítko i panel zprůhlední na 30 % (`windowOpacity`,
  animace), Pepa chtěl, aby bylo vidět „jen malinko“ (10 % i 20 % byly moc průhledné, 30 % schválil). Najetí myší, nahrávání nebo
  přepis ho hned vrátí.

### Relace Claude Code (`show_sessions`, `speak_answers`)
- Pepa pouští Claude Code přes `cmd.exe` z Průzkumníka, **každá relace má vlastní okno Windows Terminalu**
  (defterm handoff). Proces: `claude.exe ← cmd.exe ← explorer.exe`. Konzole relace je skryté `PseudoConsoleWindow`,
  jeho vlastník (`GetAncestor(..., GA_ROOTOWNER)`) je okno WT → klik na řádek přepne přesně na tu relaci.
  Titulek okna nastavuje Claude Code: téma relace se spinnerem (`◐ Katalog z Německa překlad`, `✳` = v klidu).
- Hooky v `~/.claude/settings.json` (Pepa souhlasil): SessionStart, UserPromptSubmit, Notification, Stop,
  StopFailure, SessionEnd → `"command": ".venv/Scripts/python.exe", "args": ["app/cc_hook.py"], "async": true`
  (exec forma bez shellu). Orbit je přidá/odebere podle nastavení (`sessions.set_hooks`), ostatní obsah souboru
  nechá, první změna uloží `settings.json.orbit-backup`. **Běžící relace si nové hooky načtou až po restartu.**
- Hook píše jeden soubor na relaci a událost (souběžné async hooky se tak nepřepisují), s `pid` (předek `claude.exe`)
  a `hwnd` (okno WT). Orbit je čte každou sekundu. Stav = nejnovější událost; Notification jen typů
  `permission_prompt`/`elicitation_dialog` = „čeká na tebe“ (`idle_prompt` se ignoruje). Z „čeká“ zpět na „pracuje“
  pozná podle změny souboru s přepisem. Mrtvý `claude.exe` (nebo jiný proces se stejným PID) = soubory smaže.
- `claude -p --safe-mode` (učení slovníku) hooky nespouští – ověřeno, v přehledu se neobjeví.
- Stop hook nese `last_assistant_message` → bublina a předčítání. Oznamuje se jen když okno relace není v popředí
  a tah trval ≥ 20 s (`NOTIFY_TURN_S`). Dokud nějaká relace čeká na Pepu, panel se nezprůhlední.
- Kontext = `input + cache_creation + cache_read` z posledního `usage` hlavní větve (`isSidechain` false) na konci
  přepisu (čte se jen posledních 512 KB, podle mtime). Hook nemá model, proto velikost okna: 1 mil. když má
  `~/.claude/settings.json` model s `[1m]` (Pepa má `opus[1m]`) nebo tokenů je přes 200 tis., jinak 200 tis.
  Formát přepisu není oficiálně stabilní – když se změní, procento prostě zmizí.
- Předčítání: `QTextToSpeech("winrt")`, hlas **Microsoft Jakub** (cs_CZ, jediný český ve Windows, OneCore; SAPI ho
  nevidí). Při začátku nahrávání se okamžitě zastaví. `sessions.summary` čistí Markdown na první 2 věty.

### Hlasové povely pro terminál
- Věta „Odešli.“ (nebo „Odeslat.“) na konci diktátu = Enter; diktát jen „Stop.“ / „Zastav.“ = Esc (přeruší Clauda).
  Jen jako samostatná věta, „…tak mu to odešli.“ zůstane textem. Patří pod přepínač „Hlasové povely“.
- Enter jde po textu se zpožděním 300 ms + 1 ms na znak (max 1,5 s): terminál vkládá asynchronně a Claude Code bere
  klávesu ve stejné dávce jako psaný text za součást vložení.

### Limity Clauda
- `GET https://api.anthropic.com/api/oauth/usage`, hlavičky `Authorization: Bearer <token>` a
  `anthropic-beta: oauth-2025-04-20`. Token je `claudeAiOauth.accessToken` z `~/.claude/.credentials.json`.
  Endpoint je interní (našel jsem ho v `claude.exe`), může se změnit.
- Čte se pole `limits`: `session` → „5 h“, `weekly_all` → „Týden“, `weekly_scoped` → název modelu ze
  `scope.model.display_name` („Fable“). Starší tvar (`five_hour`, `seven_day`) je jako záloha.
- Obnova každé 2 minuty (`USAGE_REFRESH_MS`) plus položka v menu. **Token se jen čte, nikdy neobnovuje** (refresh by
  rotoval refresh token a mohl rozbít přihlášení Claude Code). Když vyprší, panel zešedne a ukáže „neaktuální“.
- Bubliny potřebují `Qt.WA_AlwaysShowToolTips`, jinak se u neaktivního okna nezobrazí.
- Předpověď: z odběrů 5h okna za posledních 30 min (aspoň 10 min a +1 bod) se spočítá, kdy dojde. Když dřív než
  se okno obnoví, hlavička ukáže oranžově „dojde v 14:20“ a jednou za okno přijde bublina, pokud zbývá < 60 min.
- Endpoint vrací 429, když se ptá moc často (např. několik restartů Orbitu za sebou) – za 2 minuty se to srovná.

### Vzhled „noční signál“
- Barvy: pozadí `#121826`, pole `#1A2233`, linky `#2A3550`, text `#E7ECF5`, tlumený `#8B96AD`, akcent `#5B9DFF`
  (stejný jako pruhy limitů), červená `#E5484D` jen pro „poslouchám“ (nahrávání, zachytávání klávesy, clipping).
- Písma: Bahnschrift (nadpisy, keycap), Segoe UI Variable Text (text), Segoe Fluent Icons (ikony: mikrofon E720,
  obnovit E72C, klávesnice E765, myš E962, šipka E70D). Znak „↻“ vypadal špatně, proto glyph E72C.
- Aplikace používá styl Fusion a jeden stylesheet (`theme.apply`), který stylizuje i menu, bubliny a message boxy.
  Titulek okna se barví přes `DwmSetWindowAttribute` (atributy 20, 34, 35, 36).
- Nastavení: nahoře „Drž a mluv“ s keycapem (klik = zachytávání) a živou vlnou mikrofonu, dole sloupce „Přepis“
  a „Chování“, místo zaškrtávátek přepínače.

## Spuštění, restart, testování

- Běžící instance: procesy `pythonw.exe`, jejichž příkazová řádka obsahuje `Orbit.pyw` (přes venv launcher jsou dva).
  Restart v PowerShellu:
  ```powershell
  Get-CimInstance Win32_Process -Filter "Name='pythonw.exe'" | ? { $_.CommandLine -like '*Orbit.pyw*' } | % { Stop-Process -Id $_.ProcessId -Force }
  Start-Process C:\Users\josef\orbit\.venv\Scripts\pythonw.exe -ArgumentList '"C:\Users\josef\orbit\Orbit.pyw"' -WorkingDirectory C:\Users\josef\orbit
  ```
  Whisper server při zabití aplikace skončí sám (Job object).
- Kontrola kódu: `.venv\Scripts\python.exe -m pyflakes app Orbit.pyw`.
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

## GitHub

Soukromý repozitář **https://github.com/josefkotran/orbit**, větev `main`. Vytvořen přes GitHub API s tokenem
z Git Credential Manageru (`git credential fill`, `GCM_INTERACTIVE=never`), protože `gh` chybí. Push funguje normálně.
Autor commitů: `Josef Kotran <josef.kotran@seznam.cz>`. `whisper-server.exe` má 59 MB, GitHub jen varuje (limit 100 MB).

## Nápady na další práci (Pepa zatím nevybral)

1. Historie posledních ~10 diktátů v menu, kliknutím znovu vložit. K tomu bublina „Nic jsem nerozpoznal“, když
   z delší nahrávky nic nevyjde (aby se diktát nikdy neztratil potichu).
2. Volitelná úprava textu Claudem (podržet klávesu s Ctrl, vyčistit „ten, to“ nebo udělat e-mail). Text by odcházel
   na internet, proto jen volitelně.
3. Hlasový povel „smaž to“, který vrátí poslední diktát.
4. Doladění na jeho hlas z `recordings/`.
5. Vlastní ikona pro Orbit (teď je to pořád ikona mikrofonu).
