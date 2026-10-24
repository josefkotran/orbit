"""orbit.easya.cz's own visit statistics (web/site/api, lib, admin): what the beacons write, that robots and pages
nobody looked at stay out of the list, that install.ps1 still goes out byte for byte through api/serve.php, and the
admin login, CSRF and "that was me". Runs the real PHP (php -S over a temp copy of the site, ORBIT_STATS_DEV=1);
without PHP it is skipped (ORBIT_PHP, php on PATH, or ~/tools/php83/php.exe).

    .venv\\Scripts\\python.exe -m unittest discover -s tests -p "test_dist_web*.py"
"""
import http.cookiejar
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "web" / "site"
CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
POWERSHELL = "Mozilla/5.0 (Windows NT; Windows NT 10.0; cs-CZ) WindowsPowerShell/5.1.26100.6584"
PASSWORD = "dlouhe-zkusebni-heslo"


def find_php():
    for cand in (os.environ.get("ORBIT_PHP"), shutil.which("php"), str(Path.home() / "tools" / "php83" / "php.exe")):
        if cand and Path(cand).is_file():
            return cand
    return None


PHP = find_php()


def load_publish():
    spec = importlib.util.spec_from_file_location("orbit_publish", ROOT / "web" / "publish.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@unittest.skipUnless(PHP, "PHP není k dispozici")
class WebStats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="orbit-web-"))
        cls.root = cls.tmp / "site"
        shutil.copytree(SITE, cls.root, ignore=shutil.ignore_patterns("video"))
        (cls.root / "download").mkdir()
        (cls.root / "download" / "latest.json").write_text('{"version": "9.9.9"}\n', encoding="utf-8")
        cls.data = cls.tmp / "data"
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            cls.port = s.getsockname()[1]
        env = dict(os.environ, ORBIT_STATS_DEV="1", ORBIT_STATS_DATA=str(cls.data))
        cls.log = open(cls.tmp / "php-server.log", "wb")  # php -S logs every request: a pipe nobody reads would fill up
        cls.server = subprocess.Popen([PHP, "-S", f"127.0.0.1:{cls.port}", "-t", str(cls.root)], env=env,
                                      stdout=subprocess.DEVNULL, stderr=cls.log)
        cls.base = f"http://127.0.0.1:{cls.port}"
        for _ in range(50):
            try:
                urllib.request.urlopen(cls.base + "/robots.txt", timeout=1).read()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait(5)
        cls.log.close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        shutil.rmtree(self.data, ignore_errors=True)
        self.n = 0

    # ------------------------------------------------------------ helpers

    def request(self, path, data=None, ua=CHROME, cookie="", opener=None, method=None):
        headers = {"User-Agent": ua}
        if cookie:
            headers["Cookie"] = cookie
        if isinstance(data, dict):
            data = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            with (opener or urllib.request.build_opener(NoRedirect)).open(req, timeout=20) as r:
                return r.status, r.read().decode("utf-8"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8"), e.headers

    def beacon(self, payload, ua=CHROME, cookie=""):
        status, _, _ = self.request("/api/hit.php", json.dumps(payload).encode(), ua=ua, cookie=cookie)
        self.assertEqual(status, 204)

    def visit(self, ua=CHROME, referrer="https://github.com/josefkotran/orbit", acted=True, seen=20000, events=(), cookie=""):
        self.n += 1
        vid = f"{self.n:020x}"
        self.beacon({"id": vid, "k": "start", "r": referrer, "u": "", "h": "", "wd": 0}, ua, cookie)
        for at, (e, m) in enumerate(events):
            self.beacon({"id": vid, "k": "ev", "e": e, "m": m, "at": 1000 * (at + 1)}, ua, cookie)
        self.beacon({"id": vid, "k": "end", "s": {"top": [0, 5000], "claude": [6000, 9000], "instalace": [16000, 4000]},
                     "vt": seen, "vs": 5, "va": 0, "vm": 0, "i": 1 if acted else 0, "dm": 0, "x": 1}, ua, cookie)
        return vid

    def lines(self):
        # php -S serves one request at a time: when this one is answered, the script before it has finished writing
        # (serve.php keeps counting after the client already has the whole file)
        self.request("/robots.txt")
        out = []
        for f in sorted(self.data.glob("hits-*.php")):
            raw = f.read_text(encoding="utf-8")
            self.assertTrue(raw.startswith("<?php exit; ?>\n"), f)  # served by mistake, it prints nothing
            out += [json.loads(line) for line in raw.splitlines()[1:] if line]
        return out

    def log_in(self):
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / "admin.php").write_text(load_publish().admin_file(PASSWORD), encoding="utf-8", newline="\n")
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        status, html, _ = self.request("/admin/", {"action": "login", "password": PASSWORD}, opener=opener)
        self.assertEqual(status, 200, html[:300])
        self.assertIn("Kdo byl na webu", html)
        return opener, jar

    def dashboard(self, opener, query="?d=1"):
        status, html, _ = self.request("/admin/" + query, opener=opener)
        self.assertEqual(status, 200)
        return html

    # ------------------------------------------------------------ collecting

    def test_beacons_are_written_without_ip(self):
        self.visit(events=[("download", "instalace"), ("copy", "zadani")])
        recs = self.lines()
        self.assertEqual([r["k"] for r in recs], ["start", "ev", "ev", "end"])
        start = recs[0]
        self.assertEqual((start["r"], start["o"], start["b"], start["d"]), ("github.com/josefkotran/orbit", "Windows", "Chrome", "desktop"))
        self.assertRegex(start["vh"], r"^[0-9a-f]{16}$")
        self.assertNotIn("127.0.0.1", json.dumps(recs))

    def test_odd_beacons_are_dropped(self):
        for payload in ({"id": "xyz", "k": "start"}, {"id": "0" * 20, "k": "nope"},
                        {"id": "0" * 20, "k": "ev", "e": "hack", "m": ""}, "not json"):
            self.request("/api/hit.php", (payload if isinstance(payload, str) else json.dumps(payload)).encode())
        self.request("/api/hit.php", b"{" + b" " * 9000 + b"}")
        self.assertEqual(self.lines(), [])
        self.assertEqual(self.request("/api/hit.php")[0], 405)

    def test_owner_browser_is_not_measured(self):
        self.visit(cookie="orbit_no_stats=1")
        self.assertEqual(self.lines(), [])

    def test_owner_network_comes_from_the_server_not_the_code(self):
        self.assertNotIn("OWNER_IPS", (SITE / "lib" / "stats.php").read_text(encoding="utf-8"))  # the repo is public
        text = load_publish().owner_file("# Pepa\n127.0.0.1\n\n198.51.100.7  # kancelář\n")
        self.assertEqual(text, '<?php exit; ?>\n{"ips": ["127.0.0.1", "198.51.100.7"]}')
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / "owner.php").write_text(text, encoding="utf-8")
        self.visit()  # php -S: the visitor is 127.0.0.1
        self.assertEqual(self.lines(), [])
        (self.data / "owner.php").unlink()
        self.visit()
        self.assertEqual(len(self.lines()), 2)

    def test_referrer_keeps_no_query(self):
        self.visit(referrer="https://www.google.com/search?q=tajne+heslo")
        self.assertEqual(self.lines()[0]["r"], "google.com/search")

    # ------------------------------------------------------------ install.ps1 through PHP

    def test_install_script_goes_out_unchanged_and_counts(self):
        status, body, headers = self.request("/api/serve.php?f=script", ua=POWERSHELL)
        self.assertEqual(status, 200)
        self.assertEqual(body, (SITE / "install.ps1").read_text(encoding="utf-8"))
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        status, body, headers = self.request("/api/serve.php?f=release", ua=POWERSHELL)
        self.assertEqual((status, json.loads(body)["version"]), (200, "9.9.9"))
        self.assertEqual([(r["k"], r["e"], r["m"]) for r in self.lines()], [("srv", "script", "powershell"), ("srv", "release", "powershell")])
        self.assertEqual(self.request("/api/serve.php?f=../config")[0], 404)

    # ------------------------------------------------------------ the admin

    def test_admin_shows_people_and_leaves_robots_out(self):
        self.visit(events=[("feature", "agent"), ("faq", "Kolik Orbit stojí?"), ("download", "uvod")])
        self.request("/api/serve.php?f=script", ua=POWERSHELL)
        self.request("/api/serve.php?f=release", ua=POWERSHELL)
        self.visit(ua="Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)")
        self.visit(ua="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/141.0.0.0 Safari/537.36")
        self.visit(ua=CHROME.replace("141.0", "48.0"))                    # scraper pools use ancient browsers
        self.visit(ua=CHROME.replace("Win64", "WOW64"), acted=False, seen=2000)  # a tab nobody looked at
        opener, jar = self.log_in()
        html = self.dashboard(opener)
        self.assertEqual(html.count('<article class="visit'), 1)
        for text in ("GitHub", "Stažení instalátoru", "Hlasový agent", "Kolik Orbit stojí?",
                     "Instalace spuštěná v PowerShellu", "stahuje instalátor", "Vynecháno: 3 roboti a 1 otevření bez prohlížení"):
            self.assertIn(text, html)
        self.assertIn("orbit_no_stats", {c.name for c in jar})  # the admin's browser isn't counted from now on

    def test_admin_says_where_the_install_was_copied(self):
        self.visit(events=[("copy", "prikaz:uvod")])
        self.visit(events=[("copy", "zadani")])  # written before 24 Oct: no place
        opener, _ = self.log_in()
        html = self.dashboard(opener)
        self.assertIn("Zkopírovaný příkaz pro PowerShell <em>v úvodu</em>", html)
        self.assertIn("Zkopírované zadání pro Claude Code</li>", html)

    def test_visitor_text_is_escaped(self):
        self.visit(referrer='https://evil.example/"><script>alert(1)</script>', events=[("faq", "<img src=x onerror=alert(1)>")])
        opener, _ = self.log_in()
        html = self.dashboard(opener)
        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img src=x", html)

    def test_login_wrong_password_and_lock(self):
        self.data.mkdir(parents=True, exist_ok=True)
        (self.data / "admin.php").write_text(load_publish().admin_file(PASSWORD), encoding="utf-8", newline="\r\n")  # edited over FTP
        for _ in range(5):
            status, html, _ = self.request("/admin/", {"action": "login", "password": "spatne"})
            self.assertIn("Heslo nesouhlasí", html)
        status, html, _ = self.request("/admin/", {"action": "login", "password": PASSWORD})
        self.assertIn("Moc špatných hesel", html)
        self.assertNotIn("Kdo byl na webu", html)

    def test_dashboard_needs_login(self):
        status, html, _ = self.request("/admin/")
        self.assertIn("Heslo ještě není nastavené", html)
        self.assertNotIn("Kdo byl na webu", html)
        status, html, _ = self.request("/admin/?d=7", cookie="orbit_admin=9999999999.abc.def")
        self.assertNotIn("Kdo byl na webu", html)

    def test_forget_needs_the_token_and_removes_the_visit(self):
        vid = self.visit(events=[("download", "menu")])
        opener, _ = self.log_in()
        html = self.dashboard(opener)
        t0 = html.split('name="t0" value="')[1].split('"')[0]
        status, _, _ = self.request("/admin/?d=1", {"action": "forget", "ids": vid, "t0": t0, "t1": t0, "csrf": "x" * 32}, opener=opener)
        self.assertEqual(status, 403)
        self.assertTrue(self.lines())
        csrf = html.split('name="csrf" value="')[1].split('"')[0]
        status, html, _ = self.request("/admin/?d=1", {"action": "forget", "ids": vid, "t0": t0, "t1": t0, "csrf": csrf}, opener=opener)
        self.assertEqual(status, 200)
        self.assertEqual(self.lines(), [])
        self.assertIn("Návštěva je pryč", self.dashboard(opener, "?d=1&msg=forgot"))


@unittest.skipUnless(PHP, "PHP není k dispozici")
class Helpers(unittest.TestCase):
    """The small pure functions of lib/stats.php, called through the PHP command line."""

    def php(self, code, server=None):
        script = "require " + json.dumps(str(SITE / "lib" / "stats.php")) + ";"
        if server:
            script += "$_SERVER = array_merge($_SERVER, json_decode(" + json.dumps(json.dumps(server)) + ", true));"
        out = subprocess.run([PHP, "-r", script + "echo json_encode(" + code + ");"], capture_output=True, text=True,
                             env=dict(os.environ, ORBIT_STATS_DATA=tempfile.gettempdir()), timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout)

    def test_cloudflare_ip_only_from_cloudflare(self):
        cf = {"REMOTE_ADDR": "172.68.10.5", "HTTP_CF_CONNECTING_IP": "193.165.1.2"}
        self.assertEqual(self.php("Stats::clientIp()", cf), "193.165.1.2")
        forged = {"REMOTE_ADDR": "203.0.113.9", "HTTP_CF_CONNECTING_IP": "198.51.100.7"}
        self.assertEqual(self.php("Stats::clientIp()", forged), "203.0.113.9")  # can't pretend to be the owner
        self.assertTrue(self.php("Stats::viaCloudflare()", {"REMOTE_ADDR": "2606:4700:10::ac43:1"}))

    def test_bots(self):
        reasons = self.php("array_map([Stats::class, 'botReason'], ['', 'curl/8.4', 'Mozilla/5.0 (compatible; bingbot/2.0)', "
                           "'Mozilla/5.0 Chrome/48.0 Safari/537.36', 'WhatsApp/2.23', " + json.dumps(CHROME) + "])")
        self.assertEqual(reasons, ["ua", "ua", "ua", "old", "ua", None])

    def test_sources(self):
        got = self.php("[Stats::source('google.cz', null), Stats::source('mail.google.com/mail', null), "
                       "Stats::source('github.com/josefkotran/orbit', null), Stats::source(null, null), "
                       "Stats::source('l.facebook.com', null), Stats::source('notgithub.com', null)]")
        self.assertEqual(got, ["Google", "E-mail", "GitHub", "Přímo", "Facebook", "notgithub.com"])


if __name__ == "__main__":
    unittest.main()
