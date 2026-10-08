# Úvodní video Orbitu (Remotion)

Video nahoře na webu https://orbit.easya.cz. 1920×1080, 30 fps, 76 s, s hudbou. Vzhled je ze stránky
(`web/site/assets/site.css`): vesmír `#04060C`, akcent `#5B9DFF`, nadpisy **Anybody** a text **Mona Sans** (soubory
písem jsou kopie z `web/site/assets/fonts`). Nadpisy „dýchají“ stejně jako na webu (`src/components/Kinetic.tsx`
podle `site.js`): každé písmeno má vlastní šířku a tloušťku, běží jimi vlna, při objevení se skládají z tenkých
a úzkých a věty, které někdo říká (kurzíva Anybody), se chvějí podle hlasitosti. Začíná příletem z hyperprostoru
jako web. Aplikace ve videu je **věrná replika** kreslicího kódu `app/ui.py` (stejné rozměry, barvy, písma Segoe UI
a ikony Segoe Fluent Icons), i se sešitem Poznámek vlevo nad panelem (s počtem aktivních úkolů, jako
`_paint_notes_chip`), okno nastavení je skutečný render z Qt.

## Příběh a střih na hudbu

Celé video je stříhané na takty (`src/lib/time.ts`, 122,92 BPM, takt = 1,952 s):

| Čas | Takty | Scéna |
|---|---|---|
| 0–7 s | 0–3 | Přílet z hyperprostoru, dráhy, mikrofon, „Orbit – Diktování česky pro Windows“ |
| 6–16 s | 3–8 | Diktování do e-mailu: „Drž,“ (takt 4) „mluv,“ (5) „pusť.“ (7) |
| 16–20 s | 8–10 | „Píše tam, kde máš kurzor.“ – čtyři okna |
| 20–28 s | 10–14 | Soukromí: skutečné nastavení, „Běží na tvé grafice. Zvuk nikam neodchází.“ |
| 27–31 s | 14–16 | „A když pracuješ s Claude Code…“, hvězdy se rozjedou |
| 31 s | drop | nastoupí basa, záblesk, panel Orbitu |
| 31–47 s | 16–24 | Limity, relace, bublina „hotovo“ a „čeká na tebe“ (se zvuky z aplikace) |
| 47–57 s | 24–29 | Hlasový agent: otázka, odpověď, zpráva do relace, „Jo.“, odesláno |
| 57–62 s | 29–32 | Předčítání odpovědí a artefaktů |
| 62–76 s | 32– | Bicí skončí, mikrofon doletí doprostřed, funkce na drahách (i „Poznámky a úkoly“), „Stáhni si Orbit.“ |

## Hudba

„Mountains“ od Andrew Ev z Mixkitu (Mixkit Stock Music Free License: volně i komerčně ve videích na webu, bez
uvádění autora; skladbu nelze šířit samostatně, proto originál v `music-src/` ani hotová stopa nejsou v gitu).
Originál: https://assets.mixkit.co/music/187/187.mp3. `capture/build_music.py` z něj udělá
`public/audio/music.wav` (potřebuje Python s `librosa` a `soundfile`): začne na taktu v 16,30 s a v 78,78 s skočí přesně do místa, kde ve skladbě
končí bicí (251,88 s, změřené křížovou korelací rytmu a basy), takže video končí skutečným závěrem skladby.
Zvuky (pípnutí, zvonky bublin) jsou přímo z Orbitu (`assets/*.wav`), hudba pod zvonky na chvíli ztiší.
Výsledná hlasitost je −14 LUFS, špička −1,1 dBTP.

## Práce s projektem

```
npm i
npx remotion studio                 # náhled
node scripts/stills.mjs 150 330 990 # kontrolní snímky do out/stills (poloviční velikost)
npx remotion render Orbit out/orbit-master.mp4 --codec h264 --crf 14 --audio-bitrate 320k
node scripts/export-web.mjs         # orbit.mp4 (~22 MB), orbit.webm (~19 MB), poster.jpg do web/site/assets/video
python ..\web\publish.py            # nahraje změněné soubory na web pod novým ?v= (Cloudflare drží staré kopie rok)
```

Screeny aplikace: `..\.venv\Scripts\python.exe capture\grab.py` (z kořene repozitáře `video\capture\grab.py`)
vyrenderuje widgety Orbitu s ukázkovými daty do `public/screens` ve 3× rozlišení, nic neukazuje na obrazovce.
Renderuje se na Windows, protože aplikace používá písma Windows (Segoe UI, Segoe Fluent Icons).

Remotion je zdarma pro jednotlivce a firmy do 3 lidí (https://www.remotion.dev/license).
