# Orbit

Malý pomocník, který obíhá nad všemi okny ve Windows:

- **Diktování česky push-to-talk** do libovolného okna. Běží lokálně na grafice (Whisper large-v3 přes whisper.cpp + Vulkan),
  zvuk nikam neodchází.
- **Přehled limitů Clauda** nad mikrofonem: 5hodinové okno, týdenní limit a Fable.

## Použití

- Spusť zástupce **Orbit** (plocha / nabídka Start).
- **Drž zvolenou klávesu**, po pípnutí mluv, pusť – text se vloží tam, kde máš kurzor.
- Totéž jde myší: drž levé tlačítko na plovoucím mikrofonu. Tažením ho přesuneš, pravým tlačítkem otevřeš menu.
- Nastavení: klik na ikonu v oznamovací oblasti vedle hodin.

Barvy mikrofonu: tmavá = připraveno, červená = nahrávám (kruh ukazuje hlasitost), oranžová = přepisuji, šedá = načítám model.

- **Slovník** (v nastavení): jména, značky a výrazy, které má psát přesně takhle – Whisper je dostane jako nápovědu.
- **Hlasové povely**: „nový řádek“ a „nový odstavec“ (v režimu psaní se posílá Shift+Enter, aby chat zprávu neodeslal).
- **Mikrofon je zapnutý jen při držení klávesy** (a v okně nastavení kvůli ukazateli hlasitosti). Headset po zapnutí
  chvíli posílá ticho, proto pípnutí a červené tlačítko přijdou až ve chvíli, kdy zvuk opravdu teče.
- **Využití Clauda**: stejná čísla jako `/usage` v Claude Code, obnovuje se každé 2 minuty, po najetí myší ukáže časy
  obnovení. Čte přihlášení Claude Code z `~/.claude/.credentials.json` (jen čte, token neobnovuje – to dělá Claude Code
  sám). Endpoint `/api/oauth/usage` je interní, může se časem změnit.

## Instalace na jiném počítači

Potřeba: Windows 10/11, Python 3.13, grafika s Vulkanem (bez ní poběží whisper pomalu na procesoru).

```powershell
git clone https://github.com/josefkotran/orbit.git
cd orbit
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
mkdir models
curl.exe -L -o models\ggml-large-v3.bin https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3.bin
.venv\Scripts\pythonw.exe Orbit.pyw
```

Volitelně i rychlejší `ggml-large-v3-turbo.bin` (stejná adresa). Model se vybírá v nastavení.

## Soubory

| Cesta | Co to je |
|---|---|
| `Orbit.pyw` | spouštěcí skript (pythonw = bez konzole) |
| `app/` | aplikace (PySide6, sounddevice, pynput) |
| `whisper/` | `whisper-server.exe` zkompilovaný s Vulkanem (+ licence whisper.cpp) |
| `models/` | modely Whisper – nejsou v gitu, stáhnou se zvlášť |
| `config.json` | nastavení (vytvoří se při prvním spuštění, není v gitu) |
| `orbit.log` | log aplikace – sem koukni, když něco nefunguje |
| `recordings/` | posledních 30 nahrávek, když je zapnuté ukládání (není v gitu) |

## Přesnost modelů

Měřeno na 150 nahrávkách z české části datasetu FLEURS (RX 9070 XT):

| Model | chybná slova | chybné znaky | přepis |
|---|---|---|---|
| large-v3 | 8,9 % | 2,5 % | 1,9 s |
| large-v3-turbo | 10,2 % | 2,9 % | 0,9 s |
| mikr/whisper-large-v3-czech-cv13 (q5_0) | 11,3 % | 4,8 % | 1,9 s |

## Poznámky

- Do oken spuštěných **jako správce** Windows vkládat nedovolí (ochrana UIPI).
- whisper.cpp v1.9.4 nemá pro Windows oficiální build s Vulkanem, `whisper/` je zkompilovaný přes MSYS2 (UCRT64):
  ```
  pacman -S mingw-w64-ucrt-x86_64-{gcc,cmake,ninja,vulkan-devel,shaderc}
  cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_VULKAN=ON -DBUILD_SHARED_LIBS=OFF \
        -DCMAKE_EXE_LINKER_FLAGS='-static-libgcc -static-libstdc++'
  cmake --build build --target whisper-server
  ```
  a vedle exe je potřeba `libwinpthread-1.dll` z `ucrt64/bin`.
