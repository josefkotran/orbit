"""Claude Code on this PC: where it is, which version, whether it's logged in, and Anthropic's own ways to install it
and to log in.

Orbit never sees a password, an e-mail it asked for or a token (Anthropic's terms forbid apps to collect or pass on
Claude.ai credentials): the official installer and `claude auth login` run in a visible window the user watches, the
login itself happens on Anthropic's page in the browser, and Orbit only polls `claude auth status --json`.

Standard library only: agent_tools.py imports this (through claude_cli) in its own process.
"""
import base64
import http.client
import json
import logging
import os
import re
import shutil
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .version import VERSION as ORBIT_VERSION

log = logging.getLogger(__name__)

# The official Windows install command (code.claude.com/docs/en/setup): the native build into ~/.local/bin, no admin
# rights, updates itself. Git for Windows is optional (without it Claude Code uses PowerShell for its shell tool).
INSTALL_COMMAND = "irm https://claude.ai/install.ps1 | iex"
SETUP_DOCS = "https://code.claude.com/docs/en/setup"
PLANS = {"pro": "Pro", "max": "Max", "team": "Team", "enterprise": "Enterprise", "free": "Free"}

# What a Claude Code session sets for its own child processes. If Orbit was started from a session (a restart from a
# terminal), a CLI it starts with these would think it runs nested inside that session.
_SESSION_VARS = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_CODE_ENTRYPOINT", "CLAUDE_CODE_EXECPATH",
                 "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_CHILD_SESSION"}
_SESSION_PREFIXES = ("CLAUDE_CODE_SESSION", "CLAUDE_CODE_MESSAGING")
_NPM_EXE = Path("node_modules/@anthropic-ai/claude-code/bin/claude.exe")


def _candidates() -> list[Path]:
    appdata, local = os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")
    found = [
        Path(appdata) / "npm" / _NPM_EXE if appdata else None,  # npm install -g
        Path.home() / ".local" / "bin" / "claude.exe",  # the native installer
        Path(local) / "Microsoft" / "WinGet" / "Links" / "claude.exe" if local else None,  # winget
    ]
    if exe := shutil.which("claude.exe"):
        found.append(Path(exe))
    if shim := shutil.which("claude"):  # npm's claude.cmd with another prefix (nvm, fnm, a custom one)
        found.append(Path(shim).parent / _NPM_EXE)
    # which() looks in the current folder first (unless NoDefaultCurrentDirectoryInExePath is set) and gives that
    # as a relative path: never a claude.exe that only some folder Orbit was started in has
    return [p for p in found if p and p.is_absolute()]


def find_exe() -> str | None:
    """The real claude.exe, never a .cmd/.bat wrapper: cmd.exe would cut the multi-line system prompts at the first
    line break and expand % and quotes in them. Looked up on every call, Claude Code may get installed while Orbit
    runs (and Orbit's PATH stays the one it started with)."""
    for exe in _candidates():
        if exe.suffix.lower() == ".exe" and exe.is_file():
            return str(exe)
    return None


def environment() -> dict:
    """For every Claude Code CLI Orbit starts. Without ANTHROPIC_API_KEY it uses the Claude subscription login (a key
    without credit would win over it), and without the variables of the session Orbit may have been started from
    it doesn't think it runs inside that session. The user's own settings (CLAUDE_CONFIG_DIR,
    CLAUDE_CODE_GIT_BASH_PATH, …) stay."""
    env = {k: v for k, v in os.environ.items() if k.upper() != "ANTHROPIC_API_KEY"
           and k.upper() not in _SESSION_VARS and not k.upper().startswith(_SESSION_PREFIXES)}
    if os.environ.get("ORBIT_CLAUDE_DIR"):  # tests: the CLI uses the same fake Claude Code folder as Orbit
        env["CLAUDE_CONFIG_DIR"] = os.environ["ORBIT_CLAUDE_DIR"]
    return env


def _run(args: list[str], timeout: float) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
                          env=environment(), stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)


def version(exe: str, timeout: float = 30) -> str:
    """"2.1.288" ("" when it doesn't answer)."""
    try:
        out = _run([exe, "--version"], timeout).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    m = re.search(r"\d+\.\d+\.\d+", out)
    return m.group(0) if m else ""


@dataclass
class Status:
    installed: bool = False
    exe: str = ""
    version: str = ""
    logged_in: bool = False
    method: str = ""  # authMethod: "claude.ai" (a subscription), "console", "api_key", "none", …
    plan: str = ""  # subscriptionType: "pro", "max", "team", …
    email: str = ""  # shown in Orbit's window only, never logged
    error: str = ""  # it couldn't be checked (then the rest isn't known)

    @property
    def connected(self) -> bool:
        return self.installed and self.logged_in

    @property
    def subscription(self) -> bool:
        return self.method == "claude.ai"

    @property
    def plan_label(self) -> str:
        return PLANS.get(self.plan.lower(), self.plan.capitalize()) if self.plan else ""

    def describe(self) -> str:
        """One line for the user."""
        if self.error:
            return f"Stav Claude Code nejde zjistit: {self.error}"
        if not self.installed:
            return "Claude Code není nainstalovaný."
        if not self.logged_in:
            return "Claude Code je nainstalovaný, ale není přihlášený."
        if not self.subscription:
            return (f"Účet {self.email} je" if self.email else "Účet je") + \
                " z Anthropic Console: platí se z API kreditu, ne z předplatného."
        plan = f"předplatné {self.plan_label}" if self.plan else "přihlášeno"
        return f"Účet {self.email}, {plan}." if self.email else f"{plan[0].upper()}{plan[1:]}."


def parse_status(text: str) -> dict:
    """`claude auth status --json`, any extra or missing fields tolerated. {} when it isn't that JSON."""
    try:
        data = json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def status(timeout: float = 30) -> Status:
    """Blocking (under a second): is Claude Code here and logged in? Without ANTHROPIC_API_KEY (environment()), so it
    says whether the subscription login works, which is what Orbit uses."""
    exe = find_exe()
    if not exe:
        return Status()
    with ThreadPoolExecutor(1) as pool:  # --version (about 0.2 s) runs alongside auth status (0.6 s), not before it
        found = pool.submit(version, exe, timeout)
        try:
            proc, error = _run([exe, "auth", "status", "--json"], timeout), ""
        except (OSError, subprocess.SubprocessError) as e:
            proc, error = None, "Claude Code neodpovídá." if isinstance(e, subprocess.TimeoutExpired) else str(e)
    s = Status(installed=True, exe=exe, version=found.result())
    if proc is None:
        s.error = error
        return s
    data = parse_status(proc.stdout)
    if not data:  # an old version without "auth status", or something broke
        s.error = (proc.stderr or proc.stdout).strip()[:200] or f"neznámá odpověď (kód {proc.returncode})"
        return s
    s.logged_in = data.get("loggedIn") is True
    s.method = str(data.get("authMethod") or "")
    s.plan = str(data.get("subscriptionType") or "")
    s.email = str(data.get("email") or "")
    return s


# --- Anthropic's own install and login, in a window the user watches -------------------------------

def _powershell() -> str:
    """Windows' own PowerShell 5.1, not whatever is called powershell.exe on the PATH."""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe")


def _start(script: str, visible: bool) -> subprocess.Popen:
    """Runs a PowerShell script in a new console window (visible=False: hidden, for tests). -EncodedCommand: no
    quoting rules to get wrong, and Czech text arrives intact."""
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    flags = subprocess.CREATE_NEW_CONSOLE if visible else subprocess.CREATE_NO_WINDOW
    return subprocess.Popen([_powershell(), "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-EncodedCommand", encoded], env=environment(), creationflags=flags,
                            stdin=None if visible else subprocess.DEVNULL)


def _quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def install_script(command: str = INSTALL_COMMAND) -> str:
    return f"""$Host.UI.RawUI.WindowTitle = 'Orbit – instalace Claude Code'
Write-Host 'Instaluji Claude Code oficiálním instalátorem od Anthropicu:' -ForegroundColor Cyan
Write-Host '  {command.replace("'", "''")}'
Write-Host ''
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
try {{ {command} }} catch {{ Write-Host $_ -ForegroundColor Red }}
Write-Host ''
Write-Host 'Hotovo. Vrať se do Orbitu, tohle okno můžeš zavřít.' -ForegroundColor Cyan
Read-Host 'Enter zavře okno'
"""


def install(command: str = INSTALL_COMMAND, visible: bool = True) -> subprocess.Popen:
    """Starts the official installer in a PowerShell window. Callers poll find_exe() / status() until it's there or
    the window closes."""
    log.info("Claude Code: spouštím instalátor (%s)", command)
    return _start(install_script(command), visible)


def login_script(exe: str) -> str:
    return f"""$Host.UI.RawUI.WindowTitle = 'Orbit – přihlášení do Clauda'
Write-Host 'Přihlášení do Clauda: v prohlížeči se otevře stránka Anthropicu, přihlas se tam svým účtem.' -ForegroundColor Cyan
Write-Host 'Orbit tvoje heslo ani přihlašovací údaje nevidí. Až bude hotovo, okno se samo zavře.'
Write-Host ''
& {_quote(exe)} auth login --claudeai
if ($LASTEXITCODE -ne 0) {{
    Write-Host ''
    Write-Host 'Přihlášení se nedokončilo. Zkus to v Orbitu znovu.' -ForegroundColor Red
    Read-Host 'Enter zavře okno'
}}
"""


def login(exe: str | None = None, visible: bool = True) -> subprocess.Popen:
    """`claude auth login --claudeai` (the Claude subscription, not the API Console) in a console window. Claude Code
    opens Anthropic's login page in the browser; callers poll status() until logged in or the window closes."""
    exe = exe or find_exe()
    if not exe:
        raise FileNotFoundError("Claude Code (claude.exe) nebyl nalezen.")
    log.info("Claude Code: spouštím přihlášení")
    return _start(login_script(exe), visible)


# --- the version: the newest one on its release channel, and Anthropic's own update ---------------
# The way Claude Code checks itself (its own instructions in claude.exe 2.1.296): the channel is autoUpdatesChannel
# in settings.json (unset = latest, stable = a slower one); an npm install asks npm's dist-tag of that name (that's
# what `claude update` installs there), anything else Anthropic's release file, which is the version as plain text.

CHANNELS = ("latest", "stable")
_RELEASES = "https://downloads.claude.ai/claude-code-releases/{}"
_NPM_TAG = "https://registry.npmjs.org/@anthropic-ai/claude-code/{}"  # npm's public registry, never a project .npmrc
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
UPDATE_TIMEOUT_S = 600
_BUSY = "Claude Code se zrovna aktualizuje jinde (třeba sám v některé relaci). Zkus to za chvíli."
_UPDATE_PROBLEMS = (  # `claude update` (and winget) in English → what the user reads
    ("is in use", "Soubor claude.exe drží jiný program. Zavři relace Claude Code (i ve VS Code) a zkus to znovu."),
    ("another instance is currently performing an update", _BUSY),
    ("another claude process", _BUSY),
    ("insufficient permissions", "Na aktualizaci chybí práva. Zkus v terminálu příkaz claude update."),
    ("failed to check for updates", "Novou verzi nejde zjistit. Je počítač připojený k internetu?"),
    ("managed by a package manager", "Claude Code tu nainstaloval správce balíčků, aktualizuj ho v něm."),
    ("no available upgrade", "Winget zatím novější verzi nenabízí. Zkus to později."),
    ("no newer package", "Winget zatím novější verzi nenabízí. Zkus to později."),
)


def install_kind(exe: str) -> str:
    """How this claude.exe got here: "npm" (npm install -g), "winget", or "native" (the official installer, and
    whatever else: `claude update` sorts that out itself)."""
    parts = [part.lower() for part in Path(exe).parts]
    return "npm" if "node_modules" in parts else "winget" if "winget" in parts else "native"


def _json_file(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _flag(name: str, settings: dict) -> bool:
    """A Claude Code switch, set in the environment or in the env block of settings.json."""
    env = settings.get("env") if isinstance(settings.get("env"), dict) else {}
    value = os.environ.get(name) or str(env.get(name) or "")
    return value.strip().lower() not in ("", "0", "false", "no", "off")


def channel(settings: dict | None = None) -> str:
    settings = _json_file(paths.claude_dir() / "settings.json") if settings is None else settings
    value = settings.get("autoUpdatesChannel")
    return value if value in CHANNELS else "latest"  # only a known name goes into a URL


def auto_updates(kind: str, settings: dict | None = None) -> bool:
    """Does Claude Code update itself in the background? Not with DISABLE_AUTOUPDATER / DISABLE_UPDATES, or with
    autoUpdates false in .claude.json (which a native install ignores when autoUpdatesProtectedForNative is set)."""
    settings = _json_file(paths.claude_dir() / "settings.json") if settings is None else settings
    if _flag("DISABLE_AUTOUPDATER", settings) or _flag("DISABLE_UPDATES", settings):
        return False
    state = _json_file(paths.claude_json())
    return state.get("autoUpdates") is not False or (kind == "native" and
                                                     state.get("autoUpdatesProtectedForNative") is True)


def version_key(text: str) -> tuple:
    core, _, pre = text.split("+")[0].partition("-")
    return tuple(int(part) for part in core.split(".")), (1,) if not pre else (0, pre)  # 2.1.3-beta before 2.1.3


def older(a: str, b: str) -> bool:
    """Is version a before version b? A "+sha" build suffix doesn't count; "" or junk is never older."""
    if not (_VERSION_RE.match(a or "") and _VERSION_RE.match(b or "")):
        return False
    return version_key(a) < version_key(b)


def latest_version(kind: str, chan: str = "latest", timeout: float = 10) -> str:
    """The newest Claude Code on the channel. Raises OSError, ValueError or http.client.HTTPException."""
    url = (_NPM_TAG if kind == "npm" else _RELEASES).format(chan if chan in CHANNELS else "latest")
    request = urllib.request.Request(url, headers={"User-Agent": f"Orbit/{ORBIT_VERSION}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(1 << 20).decode("utf-8", "replace")
    if kind == "npm":
        data = json.loads(body)
        body = data.get("version") if isinstance(data, dict) else ""
    text = str(body or "").strip()
    if not _VERSION_RE.match(text):  # it only ever goes on screen; still, nothing but a version
        raise ValueError(f"nečekaná odpověď z {url.split('/')[2]}")
    return text


@dataclass
class Release:
    """Claude Code's version against the newest one on its release channel (release())."""
    installed: str = ""  # `claude --version` now ("" = it didn't answer)
    latest: str = ""  # "" = not known, error says why
    channel: str = "latest"
    kind: str = ""  # install_kind()
    auto_updates: bool = True  # Claude Code updates itself in the background
    error: str = ""

    @property
    def behind(self) -> bool:
        return older(self.installed, self.latest)


def release(exe: str | None = None, timeout: float = 10) -> Release:
    """Blocking (under a second): the installed version and the newest one on its channel, side by side."""
    exe = exe or find_exe()
    if not exe:
        return Release(error="Claude Code tu není.")
    settings = _json_file(paths.claude_dir() / "settings.json")
    kind = install_kind(exe)
    r = Release(channel=channel(settings), kind=kind, auto_updates=auto_updates(kind, settings))
    with ThreadPoolExecutor(1) as pool:
        found = pool.submit(version, exe)
        if _flag("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", settings):  # Claude Code itself doesn't ask then
            r.error = "Claude Code má vypnuté nepotřebné dotazy na internet, novou verzi proto nezjišťuju."
        else:
            try:
                r.latest = latest_version(kind, r.channel, timeout)
            except (OSError, ValueError, http.client.HTTPException) as e:
                log.info("Claude Code: nejnovější verzi nejde zjistit (%s)", e)
                r.error = "Novou verzi teď nejde zjistit."
        r.installed = found.result()
    return r


def stale_sessions_text(versions: list[str]) -> str:
    """"2 běžící relace jedou ještě na 2.1.290. …": sessions started before an update ("" = none). On Windows they
    can't switch themselves (Claude Code's /restart is macOS and Linux only), they need to be started again."""
    n = len(versions)
    if not n:
        return ""
    distinct = sorted(set(versions), key=version_key)
    on = distinct[0] if len(distinct) == 1 else f"{distinct[0]} až {distinct[-1]}"
    who = "Jedna běžící relace jede" if n == 1 else f"{n} běžící relace jedou" if n < 5 else \
        f"{n} běžících relací jede"
    it = ("ní", "ji") if n == 1 else ("nich", "je")
    return (f"{who} ještě na {on}. Nová verze se v {it[0]} projeví, až {it[1]} zavřeš a otevřeš znovu "
            "(Historie relací › Pokračovat v relaci).")


def update_command(exe: str, kind: str) -> list[str]:
    """`claude update`; for a winget install the command Claude Code's own background update runs."""
    if kind != "winget":
        return [exe, "update"]
    local = os.environ.get("LOCALAPPDATA")
    winget = str(Path(local) / "Microsoft" / "WindowsApps" / "winget.exe") if local else "winget"
    return [winget, "upgrade", "--id", "Anthropic.ClaudeCode", "--exact", "--silent", "--disable-interactivity"]


@dataclass
class Updated:
    """How update() ended."""
    ok: bool
    before: str
    after: str
    text: str  # for the user


def update(exe: str | None = None, timeout: float = UPDATE_TIMEOUT_S) -> Updated:
    """Anthropic's own update in the background (no window, nothing to answer). Blocking, usually a minute or so.
    Whether it worked says `claude --version` before and after; the output only explains why not."""
    exe = exe or find_exe()
    if not exe:
        return Updated(False, "", "", "Claude Code tu není.")
    kind, before = install_kind(exe), version(exe)
    log.info("Claude Code: aktualizuji %s (%s)", before or "?", kind)
    try:
        proc = _run(update_command(exe, kind), timeout)
        out, code = _ANSI_RE.sub("", f"{proc.stdout}\n{proc.stderr}"), proc.returncode
    except subprocess.TimeoutExpired:
        out, code = "", None
    except OSError as e:
        log.warning("Claude Code: aktualizace nejde spustit: %s", e)
        return Updated(False, before, before, f"Aktualizace nejde spustit: {e}")
    after = version(exe) or before
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    log.info("Claude Code: aktualizace skončila (kód %s), %s → %s: %s", code, before or "?", after or "?",
             " | ".join(lines[-4:])[:400])
    if older(before, after):
        return Updated(True, before, after, f"Claude Code je aktualizovaný: {before} → {after}.")
    low = out.lower()
    if code == 0 and "up to date" in low:
        return Updated(True, before, after, f"Claude Code {after} je nejnovější, nebylo co aktualizovat.")
    for needle, text in _UPDATE_PROBLEMS:
        if needle in low:
            return Updated(False, before, after, text)
    if code is None:
        return Updated(False, before, after, f"Aktualizace neskončila ani za {timeout / 60:.0f} minut.")
    return Updated(False, before, after, "Aktualizace se nepovedla: " + (lines[-1][:200] if lines else f"kód {code}"))
