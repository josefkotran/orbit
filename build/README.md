# Sestavení instalátoru Orbitu

Z repozitáře vznikne jeden soubor **`build\output\Orbit-Setup-<verze>.exe`**, který jde poslat komukoli.
Instalátor funguje na čistých Windows 10 (1809+) a 11 x64. Nepotřebuje práva správce, Python ani nic dalšího.

## Jak sestavit

```powershell
# 1) whisper-server pro jakékoli PC (stačí jednou a pak při změně verze whisper.cpp)
.venv\Scripts\python.exe build\build_whisper.py          # -> whisper-next\

# 2) instalátor
.venv\Scripts\python.exe build\build_installer.py --whisper-dir whisper-next
```

Volby `build_installer.py`:

| Volba | Co dělá |
|---|---|
| `--whisper-dir <složka>` | odkud vzít whisper-server (výchozí `whisper\`, pro distribuci `whisper-next\`) |
| `--without-piper` | vynechá Piper (GPL-3.0) a onnxruntime, předčítat pak umí jen hlas Windows (viz Licence) |
| `--no-installer` | jen sestaví a zkontroluje `build\dist\Orbit`, Inno Setup nespouští |

Napoprvé je potřeba internet. Vše stažené se ukládá do `build\cache` (MSYS2, zdrojáky whisper.cpp, Python,
instalátor Inno Setupu) a `build\tools` (Inno Setup). Obojí je v `.gitignore`. Do systému se nic neinstaluje.
MSYS2 je jen rozbalený archiv a Inno Setup se nainstaluje tiše v režimu „portable“ do `build\tools`, bez
odinstalátoru a bez zápisu do registru. Každé stažení má ve skriptu pevný SHA256 a skript ho ověřuje. Wheely
z PyPI hlídá přesná verze v `requirements.txt`.

Sestavení instalátoru trvá asi 2 minuty, když má pip balíčky v cache (poprvé se stahuje asi 300 MB wheelů).
`build_whisper.py` poprvé stahuje MSYS2 s GCC (asi 1 GB rozbalené) a kompiluje asi 15 minut, pak už jen pár sekund.

**Výsledek (verze 1.0.0, s `whisper-next`):** instalátor **82 MB**, po instalaci 294 MB. Z toho runtime je 210 MB
(PySide6 46 MB, numpy 39 MB, onnxruntime 46 MB, Piper 45 MB) a whisper 76 MB. Bez Piperu má instalace 198 MB.
Modely (1,6–3,1 GB) si Orbit stáhne sám.

## Co sestavení udělá

`build_installer.py`:

1. Přečte `VERSION` z `app\version.py`.
2. Stáhne Python 3.13.7 embeddable (amd64) z python.org, ověří SHA256 a rozbalí ho do `build\dist\Orbit\runtime`.
   `python313._pth` nastaví `sys.path` jen na stdlib, `runtime\Lib\site-packages` a kořen aplikace (`..`), kde je
   `Orbit.pyw` a `app\`. Proměnné `PYTHONPATH` atd. se neberou.

   **Bez řádku `import site`:** s ním by Python přidal i uživatelovo `%APPDATA%\Python\Python313\site-packages`
   (u Pepy je tam spousta balíčků, jiný numpy i PySide6), a to i u spuštění, která si dělá Orbit sám bez `-s`
   (klíč Run, hooky, status line, MCP server agenta). Balíček žádné soubory `.pth` nemá, takže `site` nepotřebuje;
   `verify_bundle.py` to hlídá a spouští se schválně bez `-s`. Zástupci, `[Run]` a `--cleanup` mají `-s` i tak.
3. Nainstaluje `requirements.txt` do `runtime\Lib\site-packages` přes pip z `.venv`, jen hotové wheely pro
   win_amd64 a cp313.
4. Ořeže PySide6 (asi 640 MB → 46 MB). Nechá jen Qt moduly, které `app\` opravdu importuje (hledá
   `PySide6.QtXxx` ve zdrojácích, takže nový modul se přidá sám), pluginy `qwindows`, `qoffscreen`, styl Windows,
   ikony a obrázky (ico, svg, jpeg, gif) a hlasy `winrt`/`sapi`. Qt knihovny dopočítá podle importů v DLL.
   Smaže i testy numpy a verze PortAudio pro ASIO, 32 bitů a ARM.
5. Vedle `python.exe` dá jednotnou sadu Visual C++ runtime (z PySide6). Čisté Windows ji nemají a potřebuje ji
   onnxruntime.
6. Zkopíruje `app\` (bez `__pycache__`), `Orbit.pyw`, statické soubory z `assets\` (ne vygenerované `*.wav` a
   `chevron.png`), složku whisperu (bez logů), `THIRD_PARTY_NOTICES.md` a `installer\licenses\`. Do
   `licenses\python-packages.txt` vypíše všechny balíčky s verzí a licencí.
7. **Kontrola balíčku:**
   - Projde všechny DLL/PYD/EXE a ověří, že každou importovanou knihovnu má balíček nebo čisté Windows.
   - Pak spustí `build\verify_bundle.py` přímo pythonem z balíčku. Ten běží s minimálním `PATH`,
     `QT_QPA_PLATFORM=offscreen` a `ORBIT_DATA_DIR`/`ORBIT_CLAUDE_DIR` v `%TEMP%`.
   - `verify_bundle.py` naimportuje všechny moduly `app\` a balíčky a vytvoří okno nastavení mimo obrazovku
     (screenshot uloží do `%TEMP%\orbit-verify-*`). Zkontroluje hlas `winrt` a pošle ukázkovou událost hooku
     `cc_hook.py`.
   - Co kontrola v balíčku vytvoří, se zase smaže.
8. Volitelně podepíše whisper-server a jeho DLL (viz níže) a zavolá Inno Setup s `installer\orbit.iss`.

## whisper-server pro jakékoli PC (`build_whisper.py`)

Původní `whisper\whisper-server.exe` byl přeložený s `GGML_NATIVE=ON`, tedy pro Pepův Ryzen. Na procesoru bez
stejných instrukcí by spadl. Navíc importoval `vulkan-1.dll`, takže bez ovladače s Vulkanem vůbec nenaběhl.
Nový build (whisper.cpp **1.9.4**, stejná verze, GCC 16.2 z MSYS2 UCRT64):

```
-DGGML_NATIVE=OFF -DGGML_BACKEND_DL=ON -DGGML_CPU_ALL_VARIANTS=ON -DGGML_VULKAN=ON -DGGML_OPENMP=OFF
-DBUILD_SHARED_LIBS=ON -DCMAKE_SHARED_MODULE_PREFIX= -DCMAKE_SHARED_LIBRARY_PREFIX=
linker: -static-libgcc -static-libstdc++ (u DLL navíc -Wl,--exclude-libs,ALL)
```

- Backendy jsou DLL, které ggml načte za běhu. `ggml-vulkan.dll` jen když jde (bez Vulkanu ho přeskočí), z 14
  variant `ggml-cpu-*.dll` (x64, sse42 … zen4, sapphirerapids) vybere nejlepší pro daný procesor.
- `CMAKE_SHARED_MODULE_PREFIX=`: MinGW by DLL pojmenoval `libggml-cpu-*.dll`, ale ggml na Windows hledá
  `ggml-cpu-*.dll`.
- `--exclude-libs,ALL`: bez něj `ggml-base.dll` exportuje `_Unwind_Resume` ze statického libgcc a backendy nejdou
  slinkovat.
- OpenMP vypnuté jako dřív (ggml má vlastní vlákna, odpadá `libgomp-1.dll`).
- Výstup ve `whisper-next\`: `whisper-server.exe`, `libwhisper.dll`, `ggml.dll`, `ggml-base.dll`,
  `ggml-vulkan.dll`, 14× `ggml-cpu-*.dll`, `libwinpthread-1.dll`, `LICENSE`, `LICENSE-winpthreads` (76 MB).
  Kromě systémových DLL importuje `vulkan-1.dll` jen `ggml-vulkan.dll`.

Ověřeno na Pepových nahrávkách (2–35 s), stejné parametry jako `app\whisper_server.py`:

| | starý `whisper\` | nový `whisper-next\` |
|---|---|---|
| large-v3, 6 nahrávek: text | – | 6/6 shodných |
| large-v3, součet časů | 18,99 s | 19,07 s |
| large-v3-turbo, 6 nahrávek: text | – | 6/6 shodných |
| large-v3-turbo, součet časů | 10,05 s | 9,62 s |
| CPU varianta na Ryzenu 5800X | (nativní build) | `ggml-cpu-haswell.dll` |

Záloha na CPU funguje třemi způsoby: bez `ggml-vulkan.dll`, s Vulkanem bez ovladače (`VK_DRIVER_FILES` na
neexistující soubor) a s neplatným `GGML_VK_VISIBLE_DEVICES`. Text je pokaždé stejný jako na grafice, ale pomalý.
whisper-server bere výchozí 4 vlákna, s nimi turbo potřebuje asi 13 s na 2s nahrávku. S `-t 8` je to 7,6–8,2 s
(turbo, 2–7 s řeči) nebo asi 10 s (large-v3, 2 s řeči). Na CPU proto Orbit má volit turbo a předat `-t` podle
počtu jader.

## Podepisování

Bez podpisu Windows SmartScreen u staženého instalátoru varuje („Neznámý vydavatel“). Podpis se zapne
proměnnými prostředí. Když nejsou nastavené, sestavení podpis přeskočí.

| Proměnná | Význam |
|---|---|
| `ORBIT_SIGN_PFX` | cesta k certifikátu `.pfx` |
| `ORBIT_SIGN_PASSWORD` | heslo k `.pfx` (nepovinné) |
| `ORBIT_SIGN_THUMBPRINT` | místo PFX otisk (SHA1) certifikátu v úložišti Windows, např. na tokenu |
| `ORBIT_SIGN_TIMESTAMP` | časové razítko RFC 3161, výchozí `http://timestamp.digicert.com` |
| `ORBIT_SIGNTOOL` | cesta k `signtool.exe`, výchozí nejnovější z Windows SDK (`Windows Kits\10\bin\*\x64`) |
| `ORBIT_SIGN_COMMAND` | celý vlastní příkaz místo výše uvedených (např. Azure Trusted Signing). Ve stylu Inno Setup: `$f` = soubor v uvozovkách, `$q` = uvozovka. |

Podepíše se `whisper-server.exe` a jeho DLL, instalátor i odinstalátor (Inno `SignTool` + `SignedUninstaller`).
Python a Qt podepsané už jsou (PSF, The Qt Company).

## Jak se instalátor chová

- **Bez práv správce**, jen pro aktuálního uživatele, do `%LOCALAPPDATA%\Programs\Orbit` (výběr složky se
  neukazuje, jde změnit parametrem `/DIR=`).
- Česky. Na anglických Windows anglicky, na jiných nabídne výběr (čeština je první).
- Když Orbit běží, instalátor i odinstalátor řekne, ať ho zavřeš (`AppMutex=Local\Orbit-single-instance`, stejný
  mutex jako `app\winutil.py`). Inno jméno předá `OpenMutex` beze změny, předpona `Local\` proto funguje: instalátor
  běží ve stejné relaci Windows. Navíc `CloseApplications` přes Restart Manager.
- Zástupce v nabídce Start, na ploše jen na přání (úloha). Oba spouští
  `runtime\pythonw.exe -s "{app}\Orbit.pyw"` s ikonou `assets\orbit.ico` a AppUserModelID `Orbit`.
- Na konci nabídne spuštění Orbitu (ne při tiché instalaci).
- Aktualizace přes starou verzi nejdřív smaže `runtime\`, `app\`, `assets\` a `whisper\`, ať po staré verzi nezůstanou
  soubory.
- **Odinstalace:**
  - Nejdřív spustí `runtime\python.exe -s Orbit.pyw --cleanup`. To odebere hooky, status line a klíč Run *této*
    instalace, jiná kopie Orbitu je zachovaná.
  - Pak smaže soubory programu.
  - Nakonec se zeptá, jestli smazat i data v `%LOCALAPPDATA%\Orbit`. Výchozí je **Ne**, tichá odinstalace data
    vždy nechá.
- Tichá instalace: `Orbit-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES` (Orbit se po ní nespustí).

## Kde jsou data uživatele

O složce rozhoduje `app\paths.py`:

1. proměnná `ORBIT_DATA_DIR`, když je nastavená,
2. jinak složka aplikace, když v ní je `config.json` nebo soubor `portable` (Pepova vývojová kopie),
3. jinak `%LOCALAPPDATA%\Orbit`, což je normální případ instalace.

Uvnitř je `config.json`, `orbit.log`, `recordings\`, `models\` (modely Whisperu a hlasy Piperu, stahují se při
prvním spuštění), `sessions\` a `cache\`. Složka programu (`%LOCALAPPDATA%\Programs\Orbit`) se za běhu nemění,
kromě bajtkódu Pythonu, který odinstalace smaže.

## Licence

Podrobně v `THIRD_PARTY_NOTICES.md` v kořeni repozitáře, který jde i do instalace. Co je potřeba vyřešit před
hromadnou distribucí:

- **Piper a espeak-ng jsou GPL-3.0.** Orbit Piper načítá do svého procesu, takže distribuce s Piperem znamená
  distribuovat Orbit pod licencí slučitelnou s GPL-3.0 a se zdrojáky. Jinak sestavit s `--without-piper`.
- **Hlas Jirka** je doladěný z anglického hlasu lessac. Ten je natrénovaný na datech Blizzard 2013, která povolují
  jen výzkum, žádné komerční použití.
- **Hlas Kasandra** je pod CC BY 4.0 (uvést autora Ondřeje Šimka), ale autor na své stránce prodává balíček „včetně
  licenčních podmínek“. Než ho Orbit nabídne všem, je dobré se ho zeptat.
- **Orbit sám zatím nemá licenci** (v repozitáři chybí LICENSE).
- **Qt/PySide6 (LGPL-3.0):**
  - DLL jsou nezměněné a vyměnitelné.
  - Texty LGPL a GPL jsou v `licenses\`.
  - Je potřeba zajistit zdrojáky. `THIRD_PARTY_NOTICES.md` slibuje zdroje na požádání 3 roky, jinak je vystavit
    vedle instalátoru.
- **Inno Setup** dovoluje i komerční použití, ale autoři žádají komerční uživatele o zakoupení licence.
