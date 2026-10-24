# Úvodní video Orbitu (Remotion)

Video nahoře na webu https://orbit.easya.cz. 1920×1080, 30 fps, 115,1 s, s hudbou. Vzhled je ze stránky
(`web/site/assets/site.css`): vesmír `#04060C`, akcent `#5B9DFF`, nadpisy **Anybody** a text **Mona Sans** (soubory
písem jsou kopie z `web/site/assets/fonts`). Nadpisy „dýchají“ stejně jako na webu (`src/components/Kinetic.tsx`
podle `site.js`): každé písmeno má vlastní šířku a tloušťku, běží jimi vlna, při objevení se skládají z tenkých
a úzkých a věty, které někdo říká (kurzíva Anybody), se chvějí podle hlasitosti. Začíná příletem z hyperprostoru
jako web. Aplikace ve videu je **věrná replika** kreslicího kódu `app/ui.py` (stejné rozměry, barvy, písma Segoe UI
a ikony Segoe Fluent Icons): panel s čipy nad ním (sešit Poznámek, historie diktátů, telefon, plusko, historie relací,
agent, barvy, zbalení), relacemi v barvách složek (šroubovák u „pracuje“, fajfka u „hotovo“), pilulkou s verzí Claude
Code pod panelem, nabídkou plusku s výběrem modelu (`src/components/Menu.tsx`) a ikonkou Orbitu. Animace zbalení
a rozbalení je přepsaná z `app/foldfx.py` se stejnými křivkami a konstantami (`src/components/FoldFx.tsx`). Okno
nastavení je skutečný render z Qt.

## Příběh a střih na hudbu

Celé video je stříhané na takty (`src/lib/time.ts`, 122,92 BPM, takt = 1,952 s, fráze 8 taktů začínají v taktech 4,
12, 20, 28, 36, 44 a 52):

| Čas | Takty | Scéna |
|---|---|---|
| 0–7 s | 0–3 | Přílet z hyperprostoru, dráhy, mikrofon, „Orbit – Diktování česky pro Windows“ |
| 6–16 s | 3–8 | Diktování do e-mailu: „Drž,“ (takt 4) „mluv,“ (5) „pusť.“ (7) |
| 16–20 s | 8–10 | „Píše tam, kde máš kurzor.“ – čtyři okna |
| 20–28 s | 10–14 | „Opravíš hlasem.“: „Smaž to.“ smaže poslední diktát, s Ctrl „Napiš to formálněji.“ a text přepíše Claude |
| 27–35 s | 14–18 | Soukromí: skutečné nastavení, „Běží na tvé grafice. Zvuk nikam neodchází.“ |
| 35–39 s | 18–20 | „A když pracuješ s Claude Code…“, hvězdy se rozjedou, vpravo dole ikonka Orbitu |
| 38,7 s | drop | nastoupí basa, ikonka praskne a rozbalí se z ní panel (animace z aplikace) |
| 39–55 s | 20–28 | Limity, relace v barvách složek, bublina „hotovo“ a „čeká na tebe“ (se zvuky z aplikace) |
| 55–64 s | 28–33 | Hlasový agent: otázka, odpověď, zpráva do relace, „Jo.“, odesláno |
| 64–70 s | 33–36 | Předčítání odpovědí a artefaktů |
| 70–76 s | 36–39 | „Nová relace jedním klikem.“: plusko, model Sonnet 5.5, složka web, okno Windows Terminalu v barvě složky |
| 76–80 s | 39–41 | „Claude Code vždy aktuální.“: Aktualizovat v pilulce s verzí, bublina |
| 80–86 s | 41–44 | „Zbalíš ho do ikonky.“: zbalení a rozbalení přesně jako v aplikaci |
| 86–94 s | 44–48 | „Přepis ti ohlídá Claude.“: „Dej to na git, pushni to na git.“, Whisper slyší „Daytona Git, Pushnitona Git.“, vedle kruhů „Přepisuji…“ a „Claude kontroluje přepis…“, do terminálu jde opravená věta, bublina „Opraveno…“ |
| 94–102 s | 48–52 | „Až o polovinu méně chyb.“: graf FLEURS a VoxPopuli, Whisper a s kontrolou |
| 102–115 s | 52– | Bicí skončí, mikrofon doletí doprostřed, funkce na drahách, „Stáhni si Orbit.“ |

## Hudba

„Mountains“ od Andrew Ev z Mixkitu (Mixkit Stock Music Free License: volně i komerčně ve videích na webu, bez
uvádění autora; skladbu nelze šířit samostatně, proto originál v `music-src/` ani hotová stopa nejsou v gitu).
Originál: https://assets.mixkit.co/music/187/187.mp3. `capture/build_music.py` z něj udělá
`public/audio/music.wav` (Python s `numpy` a `scipy`, mp3 dekóduje ffmpeg z Remotionu): začne v druhé půlce tichého
úvodu skladby (doba 17, 8,49 s) a na začátku fráze v 110,02 s (doba 225, video 101,53 s) skočí přesně do místa, kde
ve skladbě končí bicí (251,88 s, změřené křížovou korelací rytmu a basy pro dobu 161; basová linka se opakuje po
frázích, takže o dvě fráze později sedí stejně), takže video končí skutečným závěrem skladby. Do 20. 10. 2026 video
začínalo dobou 33 a skákalo z doby 161 (76 s), do 24. 10. skákalo z doby 193 (99,4 s).
Zvuky (pípnutí, zvonky bublin) jsou přímo z Orbitu (`assets/*.wav`), hudba pod zvonky na chvíli ztiší.
Výsledná hlasitost je −14 LUFS, špička −1,1 dBTP.

## Práce s projektem

```
npm i
npx remotion studio                 # náhled
node scripts/stills.mjs 150 330 990 # kontrolní snímky do out/stills (poloviční velikost)
npx remotion render Orbit out/orbit-master.mp4 --codec h264 --crf 14 --audio-bitrate 320k
node scripts/export-web.mjs         # orbit.mp4, orbit.webm, poster.jpg do web/site/assets/video
python ..\web\publish.py            # nahraje změněné soubory na web pod novým ?v= (Cloudflare drží staré kopie rok)
```

Screeny aplikace: `..\.venv\Scripts\python.exe capture\grab.py` (z kořene repozitáře `video\capture\grab.py`)
vyrenderuje widgety Orbitu s ukázkovými daty do `public/screens` ve 3× rozlišení, nic neukazuje na obrazovce (datová
složka i složka Claude Code jsou dočasné). Vypíše i souřadnice prvků nastavení, které video zvýrazňuje (`Privacy.tsx`),
a do `out/fold-ref/` uloží snímky animace zbalení z aplikace (u = 0, 0,1 … 1). Repliku s nimi porovnají kompozice
`WidgetTest` (panel a nabídka plusku), `PartsTest` (ikonka, bublina), `FoldTest` a `UnfoldTest` (snímek k = u 0,1·k):
`npx remotion still WidgetTest out/widgettest.png`.

Text na neprůhledném pozadí (čipy, kruhy, okna, nabídka) je ve skupině s `opacity: 0.999`: Chrome by ho jinak
vyhladil subpixelově (ClearType) a ve videu by měl modré a oranžové okraje.
Renderuje se na Windows, protože aplikace používá písma Windows (Segoe UI, Segoe Fluent Icons).

Remotion je zdarma pro jednotlivce a firmy do 3 lidí (https://www.remotion.dev/license).
