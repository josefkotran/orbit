"""Artifacts read aloud: when a Claude Code session publishes a page with the Artifact tool, Orbit lets Claude sum
it up in 7 sentences and reads them to Pepa.

Orbit's PostToolUse hook (app/cc_hook.py) leaves a file per publish in sessions/artifacts/. The page's text comes
from the local file the session published (the claude.ai copy would need a login), only that text goes to Claude.
"""
import difflib
import json
import logging
import re
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from . import claude_cli
from .config import ROOT

log = logging.getLogger(__name__)

ARTIFACTS_DIR = ROOT / "sessions" / "artifacts"
MAX_AGE_S = 300  # publishes older than this (Orbit wasn't running) are not read anymore
MAX_FILE_BYTES = 5_000_000
MAX_CHARS = 60_000  # of page text sent to Claude
SAME_RATIO = 0.8  # a republish at least this similar to what was already read isn't read again
SENTENCES = 7

_URL_RE = re.compile(r"https://claude\.ai/(?:code/)?artifact/[\w-]+")

SYSTEM_PROMPT = """\
Claude Code just published a page (an "artifact") for Josef. He works on something else and will hear your \
summary read aloud by a Czech text-to-speech voice instead of reading the page.

Write in Czech. Return:
- title: what the page is, in 2 to 6 Czech words.
- sentences: exactly 7 sentences with the most important content. First what the page is about, then the key \
findings, numbers, decisions and recommendations, last what Josef should do or check (if the page says). Concrete \
facts beat describing the layout ("the page has a table and a chart" is useless). Speak to Josef directly and \
informally (tykání), without his name.

It will be heard, not seen: plain spoken sentences, each under about 25 words. No Markdown, lists, emoji, URLs, file \
paths, code or symbols like arrows and slashes. Round long numbers unless the exact value matters.

After the visible text come the page's scripts: take facts and numbers from the data in them, never talk about the \
code. The text may be cut short."""

SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "sentences": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "sentences"],
}


@dataclass
class Published:
    session_id: str
    cwd: str
    transcript: str
    path: str  # the local file the session published
    url: str
    title: str
    time: float
    record: Path | None = None  # the hook's file, removed once the summary is done

    @property
    def name(self) -> str:
        """The session's folder."""
        return Path(self.cwd).name or self.cwd or "?"


@dataclass
class Summary:
    title: str
    sentences: list[str]
    updated: bool  # the artifact was already read before and changed a lot since


_taken: set[Path] = set()


def take_new() -> list[Published]:
    """Publishes the hook recorded since the last call, oldest first. Their files stay until done() – if Orbit
    quits (or restarts) in the middle of a summary, the next start picks them up again."""
    try:
        files = sorted(ARTIFACTS_DIR.glob("*.json"), key=lambda f: f.stat().st_mtime)
    except OSError:
        return []
    found = []
    for f in files:
        if f in _taken:
            continue
        try:
            record = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        pub = _parse(record)
        if pub and time.time() - pub.time < MAX_AGE_S:
            pub.record = f
            _taken.add(f)
            found.append(pub)
        else:
            f.unlink(missing_ok=True)
    return found


def done(pub: Published) -> None:
    if pub.record:
        pub.record.unlink(missing_ok=True)
        _taken.discard(pub.record)


def _parse(record: dict) -> Published | None:
    args = record.get("tool_input") or {}  # the hook keeps only publishes of a page
    if not args.get("file_path"):
        return None
    response = record.get("tool_response")
    info = response if isinstance(response, dict) else {}
    url = args.get("url") or info.get("url") or ""
    if not url and (m := _URL_RE.search(json.dumps(response, ensure_ascii=False))):
        url = m.group(0)
    return Published(session_id=record.get("session_id", ""), cwd=record.get("cwd", ""),
                     transcript=record.get("transcript_path") or "", path=args["file_path"],
                     url=url, title=str(info.get("title") or args.get("title") or ""), time=record.get("time", 0))


class _TextParser(HTMLParser):
    SKIP = {"head", "script", "style", "noscript", "template", "svg"}
    BLOCKS = {"p", "div", "li", "tr", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "header",
              "footer", "main", "aside", "table", "ul", "ol", "dl", "dt", "dd", "blockquote", "pre", "figcaption",
              "details", "summary", "label", "button"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []  # visible text
        self.scripts: list[str] = []  # inline scripts (often the data the page renders)
        self._skip: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip.append(tag)
        elif tag in self.BLOCKS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" · ")

    def handle_endtag(self, tag):
        if tag in self._skip:
            while self._skip.pop() != tag:
                pass
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)
        elif self._skip[-1] == "script" and data.strip():
            self.scripts.append(data.strip())


def page_text(path: str) -> str:
    """What the page says: an HTML page's visible text and then its inline scripts, which often hold the data behind
    its tables and charts. Any other file as it is."""
    p = Path(path)
    if p.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"soubor {p.name} je moc velký")
    source = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() not in (".html", ".htm"):
        return source.strip()[:MAX_CHARS]
    parser = _TextParser()
    parser.feed(source)
    parser.close()
    lines = (" ".join(line.split()) for line in "".join(parser.parts).splitlines())
    text = "\n".join(line for line in lines if line.strip(" ·"))
    if parser.scripts:
        scripts = re.sub(r"data:[^\"'`)\s]{200,}", "data:…", "\n".join(parser.scripts))  # embedded images
        text += "\n\n--- The page's scripts (data behind its tables and charts) ---\n" + scripts
    return text[:MAX_CHARS]


class Summarizer:
    """Turns published artifacts into spoken summaries; remembers what it has read, so fixing a typo and
    republishing doesn't read the whole thing again."""

    def __init__(self):
        self._read: dict[str, str] = {}  # artifact (URL or file) -> the text that was summarized

    def summarize(self, pub: Published) -> Summary | None:
        """Blocking (tens of seconds). None when a republished artifact hardly changed."""
        text = page_text(pub.path)
        if not text:
            return None
        key = pub.url or pub.path
        before = self._read.get(key)
        if before is not None and _similar(before, text):
            log.info("Artefakt %s se změnil jen málo, znovu ho nečtu", key)
            return None
        cut = " (cut short)" if len(text) >= MAX_CHARS else ""
        prompt = f"Page title: {pub.title or Path(pub.path).stem}\n\nPage text{cut}:\n{text}"
        result = claude_cli.ask(prompt, SYSTEM_PROMPT, SCHEMA)
        sentences = [" ".join(str(s).split()) for s in result.get("sentences", []) if str(s).strip()][:SENTENCES]
        if not sentences:
            raise claude_cli.ClaudeError("Claude vrátil prázdný souhrn.")
        self._read[key] = text
        return Summary(" ".join(str(result.get("title", "")).split()) or pub.title, sentences, before is not None)


def _similar(a: str, b: str) -> bool:
    return difflib.SequenceMatcher(None, a.split()[:20000], b.split()[:20000]).ratio() >= SAME_RATIO
