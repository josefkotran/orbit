"""Build and publish the Orbit web page at https://orbit.easya.cz.

    python web/publish.py --dry-run              # only render into web/dist, upload nothing
    python web/publish.py                        # render and upload the page (changed files only)
    python web/publish.py --installer PATH.exe   # upload a new installer first, then the page that offers it
    python web/publish.py --admin-password       # new password for orbit.easya.cz/admin/ (only its hash goes up)

The page lives in the folder easya_cz/orbit on the Blueboard FTP account that m-tex.cz uses (the hosting turns a
folder in easya_cz/ into a subdomain). Uploads go only over FTPS with a verified certificate, through ftplib (Windows
curl cut files short with "426"). The password is not in this repo: it is read from the m-tex project's netrc file
(or ORBIT_FTP_NETRC).

Besides the static page there are three small PHP files for the page's own visit statistics (api/hit.php,
api/serve.php, admin/index.php; their code in lib/). What they write lives in data/ on the server and is never
uploaded from here, except the admin password's hash (--admin-password).
"""
import argparse
import datetime
import secrets
import tempfile
import ftplib
import hashlib
import json
import netrc
import os
import re
import shutil
import ssl
import sys
import urllib.request
from pathlib import Path

WEB = Path(__file__).resolve().parent
SITE, DIST = WEB / "site", WEB / "dist"
RELEASE = WEB / "release.json"  # the installer the page offers, written by --installer
PUBLISHED = WEB / ".published.json"  # hashes of what is already on the server
URL = "https://orbit.easya.cz/"

FTP_HOST = "ftp.blueboard.cz"  # the certificate is *.blueboard.cz
# ftp.blueboard.cz itself didn't answer on 3 Oct 2026; ftp.m-tex.cz is the same server. Empty = connect directly.
FTP_CONNECT = os.environ.get("ORBIT_FTP_CONNECT", "ftp.m-tex.cz")
FTP_DIR = "/easya_cz/orbit/"
NETRC = Path(os.environ.get("ORBIT_FTP_NETRC", Path.home() / "m-tex" / "private" / "ftp.netrc"))
# --admin-password keeps the new password here (outside this public repo, beside the FTP login), never in the output
ADMIN_SECRET = Path(os.environ.get("ORBIT_ADMIN_PASSWORD_FILE", Path.home() / "m-tex" / "private" / "orbit-admin.txt"))
ADMIN_ITERATIONS = 400000  # PBKDF2-SHA256, as Admin::ITERATIONS in site/lib/admin.php
# the owner's networks, one IP a line: their visits aren't measured (Stats::ownerIps). Outside the repository, which is
# public; it goes to the server as data/owner.php
OWNER_IPS = Path(os.environ.get("ORBIT_OWNER_IPS_FILE", Path.home() / "m-tex" / "private" / "orbit-owner-ips.txt"))
# Mixed into the ?v= of every asset. Bump it when Cloudflare holds a bad copy (3 Oct 2026: videos cached gzipped).
ASSET_SALT = "2"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def czech_size(size: int) -> str:
    return f"{size / 1048576:.0f} MB"


def czech_date(iso: str) -> str:
    d = datetime.date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}"


def app_version() -> str:
    text = (WEB.parent / "app" / "version.py").read_text(encoding="utf-8")
    return re.search(r'VERSION\s*=\s*"([^"]+)"', text).group(1)


def keep_block(html: str, name: str, keep: bool) -> str:
    """<!--name-->…<!--/name-->: drop the markers, and the content too unless it is kept."""
    pattern = re.compile(rf"[ \t]*<!--{name}-->\n?(.*?)[ \t]*<!--/{name}-->\n?", re.S)
    return pattern.sub(lambda m: m.group(1) if keep else "", html)


def czech_typography(html: str) -> str:
    """Non-breaking spaces where Czech typesetting wants them, in text only (not in tags, scripts or styles):
    after one-letter words (v, k, s, z, o, u, a, i) and between a number and its unit."""
    parts = re.split(r"(<script\b.*?</script>|<style\b.*?</style>|<[^>]+>)", html, flags=re.S)
    for i in range(0, len(parts), 2):
        text = parts[i]
        text = re.sub(r"(?<![\w&;])([vkszouaiVKSZOUAI]) +(?=\S)", "\\1&nbsp;", text)
        text = re.sub(r"(\d) +(%|s|ms|h|min|d|GB|MB)(?![\w])", "\\1&nbsp;\\2", text)
        parts[i] = text
    return "".join(parts)


def version_assets(html: str) -> str:
    """assets/x → assets/x?v=<hash>, so the CDN and browsers never serve an old copy after a change."""
    def repl(m):
        rel = m.group(2).removeprefix(URL)
        path = DIST / rel
        if not path.is_file() or rel.startswith("assets/fonts/"):  # fonts never change; the CSS asks for them bare
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}?v={hashlib.sha256((sha256(path) + ASSET_SALT).encode()).hexdigest()[:10]}"
    return re.sub(r"""(["'(])((?:https://orbit\.easya\.cz/)?assets/[^"'()?#\s]+)""", repl, html)


def render(with_video: bool = True) -> dict:
    """web/site → web/dist with the release and the video filled in. Returns the release (or {})."""
    release = json.loads(RELEASE.read_text(encoding="utf-8")) if RELEASE.exists() else {}
    if DIST.exists():
        shutil.rmtree(DIST)
    def skip(folder, names):
        here = Path(folder)
        if here == SITE / "data":  # what the server writes (visits, password hash, key) is never uploaded from here
            return [n for n in names if n != ".htaccess"]
        return names if not with_video and here.name == "video" else []
    shutil.copytree(SITE, DIST, ignore=skip)
    video = (DIST / "assets" / "video" / "orbit.mp4").is_file()
    html = (DIST / "index.html").read_text(encoding="utf-8")
    html = keep_block(html, "video", video)
    html = keep_block(html, "novideo", not video)
    if video and not (DIST / "assets" / "video" / "orbit.webm").is_file():
        html = re.sub(r'\s*<source src="assets/video/orbit\.webm"[^>]*>', "", html)
    if video and not (DIST / "assets" / "video" / "poster.jpg").is_file():
        html = html.replace(' poster="assets/video/poster.jpg"', "")
    values = {
        "__STATE__": "ready" if release else "pending",
        "__HREF__": f"download/{release['file']}" if release else "#instalace",
        "__VERSION__": release.get("version", ""),
        "__SIZE__": czech_size(release["size"]) if release else "",
        "__DATE__": czech_date(release["date"]) if release else "",
        "__SHA256__": release.get("sha256", ""),
    }
    for key, value in values.items():
        html = html.replace(key, value)
    leftover = re.findall(r"__[A-Z0-9]+__", html)
    if leftover:
        sys.exit(f"Nevyplněné značky v index.html: {sorted(set(leftover))}")
    html = version_assets(czech_typography(html))
    (DIST / "index.html").write_text(html, encoding="utf-8", newline="\n")
    if release:  # what install.ps1 reads: which file to download and the SHA-256 it must have
        (DIST / "download").mkdir(exist_ok=True)
        (DIST / "download" / "latest.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    if OWNER_IPS.is_file():
        (DIST / "data" / "owner.php").write_text(owner_file(OWNER_IPS.read_text(encoding="utf-8")), encoding="utf-8",
                                                 newline="\n")
    return release


def owner_file(text: str) -> str:
    """data/owner.php for the owner's networks (one IP a line, # starts a comment), as Stats::ownerIps reads it."""
    ips = [line.split("#")[0].strip() for line in text.splitlines()]
    return "<?php exit; ?>\n" + json.dumps({"ips": [ip for ip in ips if ip]})


class FTPS(ftplib.FTP_TLS):
    """FTPS whose data connections reuse the control connection's TLS session (ProFTPD wants that)."""
    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


def connect() -> FTPS:
    if not NETRC.is_file():
        sys.exit(f"Chybí přihlašovací soubor FTP: {NETRC} (nebo nastav ORBIT_FTP_NETRC).")
    auth = netrc.netrc(NETRC).authenticators(FTP_HOST)
    if not auth:
        sys.exit(f"V {NETRC} chybí záznam pro {FTP_HOST}.")
    ftp = FTPS(context=ssl.create_default_context(), timeout=60)
    ftp.connect(FTP_CONNECT or FTP_HOST, 21)
    ftp.host = FTP_HOST  # the certificate is checked against this name, whichever address we connected to
    ftp.auth()
    ftp.login(auth[0], auth[2])
    ftp.prot_p()
    return ftp


def ensure_dir(ftp: FTPS, path: str) -> None:
    ftp.cwd("/")
    for part in path.strip("/").split("/"):
        try:
            ftp.cwd(part)
        except ftplib.error_perm:
            ftp.mkd(part)
            ftp.cwd(part)


def put(ftp: FTPS, local: Path, rel: str, progress: bool = False) -> None:
    """Upload under a temporary name, check the size, then rename, so nobody gets half a file."""
    folder, name = (FTP_DIR + rel).rsplit("/", 1)
    ensure_dir(ftp, folder)
    size, sent = local.stat().st_size, [0]

    def tick(block):
        sent[0] += len(block)
        if progress:
            print(f"\r  {sent[0] / size:6.1%}", end="", flush=True)

    with local.open("rb") as f:
        ftp.storbinary(f"STOR {name}.part", f, blocksize=1 << 16, callback=tick)
    if progress:
        print()
    got = ftp.size(f"{name}.part")
    if got != size:
        raise RuntimeError(f"{rel}: na serveru je {got} B místo {size} B")
    try:
        ftp.delete(name)
    except ftplib.error_perm:
        pass
    ftp.rename(f"{name}.part", name)


def upload(files: list[Path]) -> None:
    if not files:
        return
    ftp = connect()
    try:
        for path in files:
            put(ftp, path, path.relative_to(DIST).as_posix(), progress=path.stat().st_size > 5_000_000)
    finally:
        ftp.quit()


def upload_installer(path: Path, version: str) -> dict:
    name = f"Orbit-Setup-{version}.exe"
    print(f"Nahrávám instalátor {name} ({czech_size(path.stat().st_size)})…")
    ftp = connect()
    try:
        put(ftp, path, f"download/{name}", progress=True)
    finally:
        ftp.quit()
    release = {"version": version, "file": name, "size": path.stat().st_size, "sha256": sha256(path),
               "date": datetime.date.today().isoformat()}
    RELEASE.write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    return release


def admin_file(password: str) -> str:
    """data/admin.php for this password, as Admin::account() in site/lib/admin.php reads it."""
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ADMIN_ITERATIONS, 32)
    record = {"salt": salt.hex(), "iter": ADMIN_ITERATIONS, "hash": digest.hex(),
              "set": int(datetime.datetime.now().timestamp())}
    return "<?php exit; ?>\n" + json.dumps(record)


def set_admin_password() -> None:
    """A new random password for orbit.easya.cz/admin/: its hash goes to data/admin.php on the server, the password
    itself only into ADMIN_SECRET. Logs every browser out of the admin."""
    password = secrets.token_urlsafe(18)
    with tempfile.TemporaryDirectory() as tmp:
        local = Path(tmp) / "admin.php"
        local.write_text(admin_file(password), encoding="utf-8", newline="\n")
        ftp = connect()
        try:
            put(ftp, local, "data/admin.php")
        finally:
            ftp.quit()
    ADMIN_SECRET.parent.mkdir(parents=True, exist_ok=True)
    ADMIN_SECRET.write_text(f"https://orbit.easya.cz/admin/\n{password}\n", encoding="utf-8")
    print(f"Nové heslo do administrace je v souboru {ADMIN_SECRET} (na server šel jen jeho otisk).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="jen vyrenderovat do web/dist")
    ap.add_argument("--installer", type=Path, help="cesta k novému instalátoru (.exe)")
    ap.add_argument("--version", help="verze instalátoru (výchozí z app/version.py)")
    ap.add_argument("--all", action="store_true", help="nahrát všechno, i nezměněné soubory")
    ap.add_argument("--no-video", action="store_true", help="bez videa (i když leží v site/assets/video), místo něj orrery")
    ap.add_argument("--admin-password", action="store_true", help="nové heslo do orbit.easya.cz/admin/ (nic dalšího nenahraje)")
    args = ap.parse_args()

    if args.admin_password:
        set_admin_password()
        return

    if args.installer and not args.dry_run:
        if not args.installer.is_file():
            sys.exit(f"Instalátor neexistuje: {args.installer}")
        upload_installer(args.installer, args.version or app_version())
    release = render(with_video=not args.no_video)
    print(f"Stránka vyrenderovaná do {DIST} ({'instalátor ' + release['file'] if release else 'bez instalátoru'}"
          f"{', s videem' if (DIST / 'assets/video/orbit.mp4').is_file() else ''}).")
    if args.dry_run:
        return

    done = {} if args.all or not PUBLISHED.exists() else json.loads(PUBLISHED.read_text(encoding="utf-8"))
    files = [p for p in sorted(DIST.rglob("*")) if p.is_file()]
    hashes = {p.relative_to(DIST).as_posix(): sha256(p) for p in files}
    changed = [p for p in files if done.get(p.relative_to(DIST).as_posix()) != hashes[p.relative_to(DIST).as_posix()]]
    page, rules = DIST / "index.html", DIST / ".htaccess"
    rest = [p for p in changed if p not in (page, rules)]
    print(f"Nahrávám {len(changed)} z {len(files)} souborů…")
    # assets and PHP first, then the rules that send install.ps1 through api/serve.php, the page that points to it all last
    upload(rest + [p for p in (rules, page) if p in changed])
    PUBLISHED.write_text(json.dumps(hashes, indent=1) + "\n", encoding="utf-8")

    with urllib.request.urlopen(urllib.request.Request(URL, headers={"Cache-Control": "no-cache", "User-Agent": "Mozilla/5.0 orbit-publish"}), timeout=30) as r:
        live = r.read().decode("utf-8")
    ok = live == page.read_text(encoding="utf-8")
    print(f"{URL} {'odpovídá nahrané verzi' if ok else 'zatím vrací jinou verzi (cache?)'}.")


if __name__ == "__main__":
    main()
