# Web orbit.easya.cz

Statická stránka Orbitu s instalátorem ke stažení. Běží na hostingu Blueboard ve složce `easya_cz/orbit` (FTP účet
m-tex.cz, hosting dělá ze složky v `easya_cz/` subdoménu), před ním je Cloudflare.

| Soubor | Co to je |
|---|---|
| `site/index.html` | obsah stránky se značkami `__VERSION__` apod., které doplní `publish.py` |
| `site/assets/site.css`, `site.js` | vzhled a všechny efekty (jedna smyčka přes `gsap.ticker`); knihovny GSAP, ScrollTrigger a Lenis jsou v `assets/vendor/` |
| `site/.htaccess` | hlavičky (CSP, mikrofon zakázaný, cache), zákaz spouštění skriptů, bez gzipu pro video a stahování |
| `site/assets/` | písma Anybody a Mona Sans (vlastní kopie, žádné Google Fonts), ikona, `og.png` pro sdílení |
| `site/assets/video/` | úvodní video z Remotionu (zdroj ve složce `video/`): `orbit.mp4` (H.264), `orbit.webm` (VP9), `poster.jpg`. Bez `orbit.mp4` je v hlavním okně animovaný orrery |
| `release.json` | instalátor, který stránka nabízí (vznikne při `--installer`). Bez něj tlačítko ukazuje „Instalátor dokončujeme“ |
| `og.html`, `icon.html` | zdroje `og.png` (1200×630) a `apple-touch-icon.png` (180×180) |
| `publish.py` | sestaví stránku do `dist/` a nahraje změněné soubory |

## Nahrání

```powershell
python web\publish.py --dry-run                               # jen sestavit do web\dist a prohlédnout
python web\publish.py                                         # nahrát změněné soubory
python web\publish.py --installer build\...\Orbit-Setup.exe   # nahrát nový instalátor a pak stránku
python web\publish.py --no-video                              # stránka s orrery místo videa
```

- Instalátor se nahraje jako `download/Orbit-Setup-<verze>.exe` (verze z `app/version.py`, jde přepsat `--version`),
  nejdřív pod dočasným jménem, po kontrole velikosti se přejmenuje. Na stránce pak je verze, velikost, datum a SHA-256.
- FTP jen přes FTPS s ověřeným certifikátem `*.blueboard.cz`. `ftp.blueboard.cz` 3. 10. 2026 neodpovídal, proto se
  připojuje na `ftp.m-tex.cz` (stejný server, `ORBIT_FTP_CONNECT`). Heslo není v repu: čte se z
  `~/m-tex/private/ftp.netrc` (`ORBIT_FTP_NETRC`). Windows `curl` nahrával useknuté soubory (chyba 426), proto `ftplib`.
- Odkazy na soubory v `assets/` (kromě písem) dostanou `?v=<hash>`, takže Cloudflare ani prohlížeč nepodrží starou
  verzi. Cloudflare drží soubory rok; když si uloží špatnou kopii (3. 10. 2026 gzipované video bez rozsahů bajtů),
  zvyš `ASSET_SALT` v `publish.py` a nahraj znovu.
- Test: `curl -r 0-99 -D - <adresa videa>` musí vrátit `206 Partial Content`, jinak iPhone video nepřehraje.
- `--all` nahraje všechno znovu (`.published.json` si pamatuje, co už na serveru je).

## Obrázky pro sdílení

```bash
chrome --headless=new --hide-scrollbars --window-size=1200,630 --virtual-time-budget=2000 --screenshot=web/site/assets/og.png file:///C:/Users/josef/orbit/web/og.html
chrome --headless=new --hide-scrollbars --window-size=180,180 --screenshot=web/site/assets/apple-touch-icon.png file:///C:/Users/josef/orbit/web/icon.html
```
