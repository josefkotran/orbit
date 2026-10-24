import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Bubble, bubbleHeight } from "../components/Bubble";
import { FOLD_S, FoldFx, UNFOLD_S } from "../components/FoldFx";
import { KIN, Kinetic } from "../components/Kinetic";
import { MENU, menuSpot, NewSessionMenu } from "../components/Menu";
import { Feed, FeedRow, OrbitWidget, STATUS_H, Sess, StatusChip, Version, chips, panelHeight, statusWidth, widgetBox, widgetShapes } from "../components/OrbitWidget";
import { Words, sub } from "../components/Text";
import { Cursor, Window } from "../components/Window";
import { EASE_IN_OUT, EXPO_OUT, lerp, prog, rise, sink } from "../lib/anim";
import { C, DISPLAY, TEXT } from "../lib/theme";
import { FPS, bar, CUT, DROP } from "../lib/time";
import { speechLevel } from "./Dictation";
import { OUTRO_MIC } from "./Outro";

// After the drop: Orbit's panel in the bottom right corner of the "screen", captions on the left. It bursts out of
// Orbit's icon on the drop (the app's own unfold animation); in the phrase from bar 36 it opens a new session from the +,
// updates Claude Code and folds into its icon and back; in the last one (bar 44) a dictation into that session is
// misheard by Whisper and goes in fixed after Claude's check, then what the check does in numbers.
export const T = {
  icon: DROP - 46,
  unfold: DROP - 7, // its burst (u ≈ 0.3) on the drop
  limits: DROP,
  sessions: bar(22),
  done: bar(24),
  waiting: bar(26),
  agent: bar(28),
  reply1: bar(29),
  ask2: bar(30),
  confirm: bar(31),
  yes: bar(32),
  read: bar(33),
  plus: bar(36),
  version: bar(39),
  fold: bar(41),
  check: bar(44),
  numbers: bar(48),
  end: CUT,
};
const LISTEN_LEN = 46;
export const AGENT_EVENTS = {
  listen: [T.agent, T.ask2, T.yes],
  stop: [T.agent + LISTEN_LEN, T.ask2 + LISTEN_LEN, T.yes + 16],
  sent: T.yes + 24,
};
// the + menu: a click on the +, Sonnet picked, the folder "web", the new session
const P = { hover: T.plus + 26, click: T.plus + 36, sonnet: T.plus + 62, web: T.plus + 90 };
const NEW_SESSION = P.web + 12;
// Claude Code's update from the version pill
const V = { hover: T.version + 18, click: T.version + 26, done: T.version + 66 };
// fold into the icon and back
const F = { hover: T.fold + 14, fold: T.fold + 20, iconHover: T.fold + 66, unfold: bar(42.6) };
const UNFOLD_LEN = Math.round(UNFOLD_S * FPS);
const FOLD_LEN = Math.round(FOLD_S * FPS);
export const CLAUDE_CHIMES = { versionDone: V.done };
// the transcript check: said, the key let go, Whisper and Canary done and they differ (Claude asked), the fixed text in
const K = { rec: bar(44.5), up: bar(44.5) + 54, check: bar(44.5) + 84, fix: bar(44.5) + 146 };
const SAID = "Dej to na git, pushni to na git.";
const SAID_WORDS = SAID.split(" ").map((_, i) => K.rec + 4 + i * 6);
export const CHECK_EVENTS = { listen: [K.rec + 6], stop: [K.up] };
const TRANSCRIBING = "Přepisuji…";
const CHECKING = "Claude kontroluje přepis…";
// main._tell_fixed's quiet bubble, wrapped as Qt wraps it (ui.Bubble._lines)
const CHECK_BUBBLE = ["Opraveno: Daytona → Dej to na, Pushnitona →", "pushni to na. Klikni sem a vrátím, co napsal", "Whisper."];

const RIGHT = 1830;
// the version pill's button ("Aktualizovat"), its centre from the widget's left
const D_VER_BTN = { x: 440 - 3 - 38 };

/** The camera: the panel at 2.25x in the bottom right, a bit smaller and lower in the last phrase (room for the + menu
 * above it). */
const cam = (f: number) => {
  const t = prog(f, T.plus, T.plus + 26, EASE_IN_OUT);
  return { s: lerp(t, [0, 1], [2.25, 2.0]), bottom: lerp(t, [0, 1], [960, 1040]) };
};

const Q1 = "Co dělá relace s katalogem?";
const Q1_LINES = ["„Co dělá relace", "s katalogem?“"];
const A1 = "Překládá katalog z němčiny, má hotovou zhruba polovinu.";
const Q2 = "Napiš jí, ať ceny převede na koruny.";
const Q2_LINES = ["„Napiš jí, ať ceny", "převede na koruny.“"];
const A2 = "Pošlu to do relace s katalogem. Mám?";
const MSG = "Ceny v katalogu rovnou převeď na koruny.";

const words = (text: string, from: number, gap = 7) => text.split(" ").map((_, i) => from + 4 + i * gap);

const heightAt = (f: number) =>
  lerp(
    f,
    [T.sessions, T.sessions + 14, T.agent, T.agent + 10, T.reply1, T.reply1 + 10, T.confirm, T.confirm + 12, T.plus, T.plus + 18, NEW_SESSION, NEW_SESSION + 12],
    [
      panelHeight(3, 0, null),
      panelHeight(3, 3, null),
      panelHeight(3, 3, null),
      panelHeight(3, 3, 1),
      panelHeight(3, 3, 1),
      panelHeight(3, 3, 2),
      panelHeight(3, 3, 2),
      panelHeight(3, 3, 4),
      panelHeight(3, 3, 4),
      panelHeight(3, 3, null),
      panelHeight(3, 3, null),
      panelHeight(3, 4, null),
    ],
    EASE_IN_OUT,
  );

type Agent = "idle" | "listening" | "thinking" | "speaking" | "confirm";

const agentState = (f: number): Agent => {
  const { listen, stop } = AGENT_EVENTS;
  for (let i = 0; i < 3; i++) if (f >= listen[i] && f < stop[i]) return "listening";
  if (f >= stop[0] && f < T.reply1) return "thinking";
  if (f >= T.reply1 && f < T.reply1 + 40) return "speaking";
  if (f >= stop[1] && f < T.confirm) return "thinking";
  if (f >= T.confirm && f < T.yes) return f < T.confirm + 34 ? "speaking" : "confirm";
  return "idle";
};

const feedAt = (f: number): Feed | null => {
  if (f < T.agent || f >= T.plus + 18) return null;
  const st = agentState(f);
  const status =
    st === "listening" ? "Poslouchám…" : st === "thinking" ? "Přemýšlím…" : st === "speaking" ? "Mluví" : st === "confirm" ? "Mám? Řekni „jo“" : "";
  const statusColor = st === "listening" ? C.appListen : st === "confirm" ? C.busy : undefined;
  const rows: FeedRow[] = [];
  const asked2 = f >= AGENT_EVENTS.stop[1];
  const leaving = 1 - prog(f, T.plus, T.plus + 10);
  if (f >= AGENT_EVENTS.stop[0] - 6) rows.push({ kind: "you", text: asked2 ? Q2 : Q1, opacity: prog(f, AGENT_EVENTS.stop[0] - 6, AGENT_EVENTS.stop[0] + 2) * leaving });
  if (f >= T.reply1) rows.push({ kind: "reply", text: f >= T.confirm ? A2 : A1, opacity: prog(f, T.reply1, T.reply1 + 8) * leaving });
  if (f >= T.confirm) {
    const sent = f >= AGENT_EVENTS.sent;
    rows.push({
      kind: "target",
      name: "Překlad katalogu z němčiny",
      folder: "eshop",
      label: sent ? "odesláno ✓" : f >= AGENT_EVENTS.stop[2] ? "posílám…" : "čeká na tvoje „jo“",
      color: sent ? C.done : f >= AGENT_EVENTS.stop[2] ? undefined : C.busy,
      opacity: prog(f, T.confirm + 4, T.confirm + 12) * leaving,
    });
    rows.push({ kind: "message", text: MSG, opacity: prog(f, T.confirm + 8, T.confirm + 16) * leaving });
  }
  return { status, statusColor, rows };
};

/** Left column: headline + note that swap per section (top: placed there instead of centred). */
const Caption: React.FC<{ f: number; at: number; until: number; lines: string[]; note: string; top?: number }> = ({ f, at, until, lines, note, top }) => {
  if (f < at - 1 || f > until + 8) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: 110,
        top: top ?? 0,
        bottom: top === undefined ? 0 : undefined,
        width: 700,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
      }}
    >
      <Kinetic lines={lines} at={at + 3} out={until - 14} cfg={KIN.h2} size={74} lineHeight={1.02} />
      <Words text={note} at={at + 14} out={until - 12} style={{ ...sub(34), marginTop: 30 }} />
    </div>
  );
};

/** What Pepa says to the agent: Anybody italic, each word when it is spoken, shivering with his voice. */
const SaidLine: React.FC<{ f: number; lines: string[]; at: number; out: number; size?: number }> = ({ f, lines, at, out, size = 50 }) => {
  const idx = AGENT_EVENTS.listen.indexOf(at);
  const level = idx >= 0 && f >= at && f < AGENT_EVENTS.stop[idx] ? speechLevel(f, words(lines.join(" "), at)) : 0;
  return <Kinetic lines={lines} at={at} wordAt={(w) => at + 4 + w * 7} dur={16} out={out} cfg={KIN.said} italic size={size} lineHeight={1.12} level={level} />;
};

const AgentLine: React.FC<{ f: number; text: string; at: number; out: number; color?: string }> = ({ f, text, at, out, color = C.soft }) => (
  <div style={{ display: "flex", gap: 18, alignItems: "baseline", marginTop: 28, ...rise(f, at, 18, 14), ...sink(f, out) }}>
    <span style={{ fontFamily: TEXT, fontWeight: 650, fontSize: 25, color: C.accent, letterSpacing: ".02em", flexShrink: 0 }}>Orbit</span>
    <span style={{ fontFamily: TEXT, fontSize: 34, lineHeight: 1.38, color }}>{text}</span>
  </div>
);

const AgentColumn: React.FC<{ f: number }> = ({ f }) => {
  if (f < T.agent - 1 || f > T.read + 4) return null;
  return (
    <div style={{ position: "absolute", left: 110, top: 190, width: 680 }}>
      <Kinetic lines={["Hlasový agent."]} at={T.agent + 3} out={T.read - 14} cfg={KIN.h2} size={74} />
      <div style={{ position: "relative", height: 390, marginTop: 46 }}>
        {f < T.ask2 + 4 ? (
          <div style={{ position: "absolute", inset: 0 }}>
            <SaidLine f={f} lines={Q1_LINES} at={T.agent} out={T.ask2 - 12} />
            {f >= T.reply1 ? <AgentLine f={f} text={A1} at={T.reply1 + 2} out={T.ask2 - 12} /> : null}
          </div>
        ) : null}
        {f >= T.ask2 && f < T.yes + 4 ? (
          <div style={{ position: "absolute", inset: 0 }}>
            <SaidLine f={f} lines={Q2_LINES} at={T.ask2} out={T.yes - 12} />
            {f >= T.confirm ? <AgentLine f={f} text={A2} at={T.confirm + 2} out={T.yes - 12} /> : null}
          </div>
        ) : null}
        {f >= T.yes ? (
          <div style={{ position: "absolute", inset: 0, ...sink(f, T.read - 12) }}>
            <SaidLine f={f} lines={["„Jo.“"]} at={T.yes} out={T.read + 40} size={66} />
            {f >= AGENT_EVENTS.sent ? (
              <div style={{ fontFamily: TEXT, fontWeight: 600, fontSize: 38, color: C.done, marginTop: 24, ...rise(f, AGENT_EVENTS.sent, 16, 12) }}>
                Odesláno do relace ✓
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
      <Words text="Než něco pošle, počká na tvoje „jo“." at={T.confirm + 20} stagger={2} out={T.read - 12} style={{ ...sub(34), marginTop: 26 }} />
    </div>
  );
};

/** Sound rings from the speaker while Orbit reads aloud. */
const SoundRings: React.FC<{ f: number; from: number; to: number; at: { x: number; y: number } }> = ({ f, from, to, at }) => {
  if (f < from || f > to + 30) return null;
  const fade = 1 - prog(f, to - 10, to + 20);
  return (
    <>
      {[0, 1, 2].map((k) => {
        const t = ((((f - from + k * 12) % 36) + 36) % 36) / 36;
        const r = 30 + t * 90;
        return (
          <div
            key={k}
            style={{
              position: "absolute",
              left: at.x - r,
              top: at.y - r,
              width: 2 * r,
              height: 2 * r,
              borderRadius: "50%",
              border: `2px solid ${C.accent}`,
              opacity: (1 - t) * 0.5 * fade * prog(f, from, from + 10),
            }}
          />
        );
      })}
    </>
  );
};

// Claude Code's welcome mascot, its block characters drawn as quadrants (a font's block glyphs leave seams)
const QUADS: Record<string, number[]> = { "▐": [1, 3], "▛": [0, 1, 2], "█": [0, 1, 2, 3], "▜": [0, 1, 3], "▌": [0, 2], "▝": [1], "▘": [0], " ": [] };
const MASCOT = [" ▐▛███▜▌", "▝▜█████▛▘", "  ▘▘ ▝▝"];
const Mascot: React.FC<{ color: string; cell?: number }> = ({ color, cell = 11 }) => (
  <svg width={9 * cell} height={3 * cell * 2} style={{ flex: "none" }}>
    {MASCOT.flatMap((line, row) =>
      Array.from(line).flatMap((ch, col) =>
        (QUADS[ch] ?? []).map((q) => (
          <rect key={`${row}-${col}-${q}`} x={col * cell + (q % 2) * (cell / 2)} y={row * cell * 2 + Math.floor(q / 2) * cell} width={cell / 2 + 0.4} height={cell + 0.4} fill={color} />
        )),
      ),
    )}
  </svg>
);

/** The new session's Windows Terminal, its background in its folder's colour (colors.py shade of blue); prompt: text
 * typed into it, `typed` of it so far. */
const Terminal: React.FC<{ f: number; at: number; out: number; top?: number; h?: number; prompt?: string; typed?: number }> = ({
  f,
  at,
  out,
  top = 590,
  h = 380,
  prompt = "",
  typed = 0,
}) => {
  if (f < at || f > out + 20) return null;
  const t = prog(f, at, at + 20);
  const o = Math.min(t, 1 - prog(f, out, out + 18, EASE_IN_OUT));
  const mono = '"Cascadia Mono", Consolas, monospace';
  const orange = "#D97757";
  const shown = prompt.slice(0, Math.round(prompt.length * typed));
  return (
    <Window
      w={760}
      h={h}
      title="✳ Claude Code"
      titleSize={18}
      bar={46}
      bg="#182230"
      style={{
        left: 110,
        top,
        opacity: o,
        transform: `translateY(${(1 - t) * 40}px) scale(${0.95 + t * 0.05})`,
        filter: t < 1 ? `blur(${(1 - t) * 8}px)` : undefined,
      }}
    >
      <div style={{ padding: "22px 26px", fontFamily: mono, fontSize: 21, lineHeight: 1.45, color: "#C9D1DC", whiteSpace: "pre" }}>
        <div style={{ display: "flex", gap: 22, alignItems: "center" }}>
          <Mascot color={orange} />
          <div>
            <div>
              <b style={{ color: "#E7ECF5" }}>Claude Code</b> <span style={{ color: "#8B96AD" }}>v2.1.304</span>
            </div>
            <div style={{ color: "#8B96AD" }}>Sonnet 5.5 · Claude Max</div>
            <div style={{ color: "#8B96AD" }}>C:\Users\pepa\web</div>
          </div>
        </div>
        <div style={{ marginTop: 26, borderTop: "1px solid rgba(255,255,255,.22)", borderBottom: "1px solid rgba(255,255,255,.22)", padding: "8px 0" }}>
          <span style={{ color: "#E7ECF5" }}>{"> "}</span>
          <span style={{ color: "#E7ECF5" }}>{shown}</span>
          <span style={{ display: "inline-block", width: 11, height: 24, background: "#E7ECF5", verticalAlign: "middle", opacity: Math.floor(f / 16) % 2 ? 0 : 1 }} />
        </div>
        <div style={{ color: "#6B7690", fontSize: 18, marginTop: 6 }}>? for shortcuts</div>
      </div>
    </Window>
  );
};

/** The check's left column: the headline, what was said (shivering with the voice), what Whisper heard instead
 * (crossed out once Claude's fix is in) and that the fixed text is what goes into the window. */
const CheckColumn: React.FC<{ f: number }> = ({ f }) => {
  if (f < T.check - 1 || f > T.numbers + 8) return null;
  const out = T.numbers - 12;
  const level = f >= K.rec + 6 && f < K.up ? speechLevel(f, SAID_WORDS, 6) : 0;
  const crossed = prog(f, K.fix, K.fix + 12, EASE_IN_OUT);
  return (
    <div style={{ position: "absolute", left: 110, top: 150, width: 760 }}>
      <Kinetic lines={["Přepis ti", "ohlídá Claude."]} at={T.check + 3} out={out} cfg={KIN.h2} size={74} lineHeight={1.02} />
      <div style={{ marginTop: 34 }}>
        <Kinetic lines={[`„${SAID}“`]} at={K.rec} wordAt={(w) => SAID_WORDS[w] - 2} dur={16} out={out} cfg={KIN.said} italic size={44} lineHeight={1.1} level={level} />
      </div>
      <div style={{ display: "flex", gap: 14, alignItems: "baseline", marginTop: 16, ...rise(f, K.up + 22, 18, 12), ...sink(f, out) }}>
        <span style={{ fontFamily: TEXT, fontSize: 28, color: C.dim, flexShrink: 0 }}>Whisper slyšel</span>
        <span style={{ position: "relative", fontFamily: TEXT, fontSize: 30, color: C.busy }}>
          „Daytona Git, Pushnitona Git.“
          <span
            style={{
              position: "absolute",
              left: 0,
              top: "54%",
              height: 3,
              width: `${crossed * 100}%`,
              background: C.busy,
              borderRadius: 2,
            }}
          />
        </span>
      </div>
      <div style={{ fontFamily: TEXT, fontWeight: 600, fontSize: 30, color: C.done, marginTop: 14, ...rise(f, K.fix + 8, 18, 12), ...sink(f, out) }}>
        Do okna jde rovnou opravené ✓
      </div>
    </div>
  );
};

// FLEURS cs (181 read sentences) and VoxPopuli cs (161 pieces of parliament speech, 44 speakers): words wrong, Orbit's
// whisper-server with its settings, measured 24 Oct 2026 (CLAUDE.md, Kontrola přepisu)
const ERRORS = [
  { label: "Předčítaná řeč", note: "FLEURS", whisper: 9.3, checked: 4.7 },
  { label: "Volná řeč", note: "VoxPopuli, 44 řečníků", whisper: 12.7, checked: 9.4 },
];

/** The check in numbers: words wrong in Czech, Whisper alone and Whisper with Canary and Claude's check. */
const ErrorChart: React.FC<{ f: number; at: number; out: number }> = ({ f, at, out }) => {
  if (f < at || f > out + 20) return null;
  const t = prog(f, at, at + 20);
  const o = Math.min(t, 1 - prog(f, out, out + 18, EASE_IN_OUT));
  const full = 470; // px for 14 %
  const pct = (v: number) => v.toFixed(1).replace(".", ",") + " %";
  return (
    <div
      style={{
        position: "absolute",
        left: 110,
        top: 640,
        width: 760,
        padding: "26px 34px 28px",
        borderRadius: 18,
        background: "rgba(11,16,32,.86)",
        boxShadow: "inset 0 0 0 1px rgba(255,255,255,.1), 0 24px 60px rgba(0,0,0,.45)",
        opacity: o,
        transform: `translateY(${(1 - t) * 40}px)`,
        fontFamily: TEXT,
      }}
    >
      <div style={{ fontSize: 22, color: C.dim, letterSpacing: ".02em", opacity: 0.999 }}>Slova přepsaná špatně, čeština</div>
      {ERRORS.map((e, i) => {
        const grow = (k: number) => prog(f, at + 14 + i * 22 + k * 10, at + 44 + i * 22 + k * 10, EASE_IN_OUT);
        return (
          <div key={e.label} style={{ marginTop: 22 }}>
            <div style={{ fontSize: 24, color: C.text, opacity: 0.999 }}>
              {e.label} <span style={{ color: C.dim, fontSize: 20 }}>· {e.note}</span>
            </div>
            {[
              { name: "Whisper", v: e.whisper, color: "#59637A", k: 0 },
              { name: "s kontrolou", v: e.checked, color: C.accent, k: 1 },
            ].map((b) => (
              <div key={b.name} style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 10 }}>
                <span style={{ width: 132, fontSize: 21, color: b.k ? C.text : C.soft, opacity: 0.999 }}>{b.name}</span>
                <div style={{ width: (full * b.v * grow(b.k)) / 14, height: 18, borderRadius: 9, background: b.color, boxShadow: b.k ? "0 0 18px rgba(91,157,255,.45)" : undefined }} />
                <span style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 24, color: b.k ? C.accent : C.soft, opacity: grow(b.k) }}>{pct(b.v)}</span>
              </div>
            ))}
          </div>
        );
      })}
    </div>
  );
};

export const Claude: React.FC = () => {
  const f = useCurrentFrame();
  const shapes3 = useMemo(() => widgetShapes(panelHeight(3, 0, null), 196), []);
  const shapes4 = useMemo(() => widgetShapes(panelHeight(3, 4, null), 196), []);
  if (f < T.icon || f >= OUTRO_MIC.at) return null;
  const { s: S0, bottom: BOTTOM } = cam(f);
  const ph = heightAt(f);
  const box = widgetBox(ph);
  const st = agentState(f);
  const ask = [Q1, Q2, "Jo."];
  const listenIdx = AGENT_EVENTS.listen.findIndex((s, i) => f >= s && f < AGENT_EVENTS.stop[i]);
  const agentLevel = listenIdx >= 0 ? speechLevel(f, words(ask[listenIdx], AGENT_EVENTS.listen[listenIdx])) : 0;

  const sessions: Sess[] = [
    { name: "Překlad katalogu z němčiny", folder: "eshop", color: "#F28C38", state: "working", context: 0.34 },
    { name: "Oprava exportu faktur", folder: "faktury", color: "#3DD68C", state: f >= T.waiting ? "waiting" : "working", context: 0.12 },
    { name: "Nová úvodní stránka", folder: "web", color: "#5B9DFF", state: f >= T.done ? "done" : "working", context: 0.57 },
  ].map((s, i) => {
    const t = prog(f, T.sessions + 4 + i * 7, T.sessions + 20 + i * 7);
    return { ...(s as Sess), opacity: t, x: (1 - t) * 16 };
  });
  if (f >= NEW_SESSION) {
    const t = prog(f, NEW_SESSION + 4, NEW_SESSION + 20);
    sessions.push({ name: "", folder: "web", color: "#5B9DFF", state: "idle", context: -1, model: "Sonnet 5.5", opacity: t, x: (1 - t) * 16 });
  }
  const showSessions = f >= T.sessions;

  const limits = [
    { label: "5 h", percent: 42 },
    { label: "Týden", percent: 63 },
    { label: "Fable", percent: 28 },
  ].map((l, i) => ({ ...l, percent: l.percent * prog(f, DROP + 12 + i * 7, DROP + 52 + i * 7, EXPO_OUT) }));

  const version: Version =
    f < T.version
      ? { state: "current", installed: "2.1.303" }
      : f < V.click + 2
        ? { state: "new", installed: "2.1.303", latest: "2.1.304", hover: prog(f, V.hover, V.hover + 5), press: f >= V.click ? 1 - prog(f, V.click + 2, V.click + 4) : 0 }
        : f < V.done
          ? { state: "updating", installed: "2.1.303", latest: "2.1.304" }
          : { state: "current", installed: "2.1.304" };

  // when the drums stop the mic flies to the centre and becomes the outro's mic (OUTRO_MIC)
  const exit = prog(f, CUT, CUT + 30, EASE_IN_OUT);
  const fade = 1 - prog(f, CUT, CUT + 12);
  const scaleEnd = OUTRO_MIC.d / 52;
  const S = S0 + (scaleEnd - S0) * exit;
  const tx = (OUTRO_MIC.x - RIGHT + 36 * scaleEnd) * exit;
  const ty = (OUTRO_MIC.y - BOTTOM + 36 * scaleEnd) * exit;
  // screen position of a point of the (unfolded) widget, with no exit
  const at = (x: number, y: number) => ({ x: RIGHT - (box.w - x) * S0, y: BOTTOM - (box.h - y) * S0 });
  const MIC = at(box.mic.x, box.mic.y);
  const SPEAKER = { x: MIC.x - 60 * S0, y: MIC.y };

  // what the widget shows: the icon before the drop and while folded, the animations, else the panel
  const folded = (f >= T.icon && f < T.unfold) || (f >= F.fold + FOLD_LEN && f < F.unfold);
  const fx =
    f >= T.unfold && f < T.unfold + UNFOLD_LEN
      ? { u: (f - T.unfold) / (UNFOLD_S * FPS), folding: false, shapes: shapes3 }
      : f >= F.fold && f < F.fold + FOLD_LEN
        ? { u: (f - F.fold) / (FOLD_S * FPS), folding: true, shapes: shapes4 }
        : f >= F.unfold && f < F.unfold + UNFOLD_LEN
          ? { u: (f - F.unfold) / (UNFOLD_S * FPS), folding: false, shapes: shapes4 }
          : null;
  const reading = f >= T.read + 4 && f < T.plus;
  // the dictation of the transcript check: red while said, orange until the fixed text is in
  const checkRec = f >= K.rec + 6 && f < K.up;
  const props = {
    height: ph,
    panelOpacity: fade,
    speakerOpacity: fade,
    limits,
    sessions: showSessions ? sessions : [],
    feed: feedAt(f),
    agent: st === "idle" ? ("idle" as const) : st,
    agentLevel,
    notes: 2,
    phase: f * 0.12,
    workPhase: f * 0.229,
    reading,
    wave: Math.floor(f / 10) % 3,
    version,
    mic: checkRec ? ("recording" as const) : f >= K.up && f < K.fix ? ("busy" as const) : ("idle" as const),
    level: checkRec ? speechLevel(f, SAID_WORDS, 6) : 0,
    plusHover: f >= P.hover && f < P.click + 4 ? prog(f, P.hover, P.hover + 5) : 0,
    foldHover: f >= F.hover && f < F.fold ? prog(f, F.hover, F.hover + 5) : 0,
  };
  const iconIn = f < T.unfold ? prog(f, T.icon, T.icon + 20) : 1;
  const widget = fx ? (
    <FoldFx u={fx.u} folding={fx.folding} w={box.w} h={box.h} c={box.mic} shapes={fx.shapes} picture={(shimmer) => <OrbitWidget {...props} shimmer={shimmer} />} />
  ) : folded ? (
    <div style={{ opacity: iconIn, transform: `scale(${0.6 + 0.4 * iconIn})`, transformOrigin: "36px 36px" }}>
      <OrbitWidget collapsed iconHover={f >= F.iconHover && f < F.unfold ? prog(f, F.iconHover, F.iconHover + 5) : 0} />
    </div>
  ) : (
    <OrbitWidget {...props} />
  );

  const bubbleX = SPEAKER.x - 26 * S0 - 6 * S0 - 338 * S0;
  const bubbleY = MIC.y - 26 * S0;
  // a taller bubble stays on the screen, as Qt keeps it there (ui.Bubble.show_near), its tail still at the mic
  const checkH = bubbleHeight(CHECK_BUBBLE.length);
  const checkTop = Math.min(bubbleY, 1080 - 14 - checkH * S0);
  const checkTail = Math.min(Math.max((MIC.y - checkTop) / S0, 16), checkH - 16);
  const bubble = (from: number, to: number) => {
    const t = prog(f, from, from + 9);
    const o = Math.min(prog(f, from, from + 6), 1 - prog(f, to - 8, to));
    return {
      position: "absolute" as const,
      left: bubbleX,
      top: bubbleY,
      transform: `translateX(${(1 - t) * 20}px) scale(${S0})`,
      transformOrigin: "0 0",
      opacity: o,
    };
  };

  // the + menu, popped up above the + and kept on the screen like Qt does
  const plusAt = at(chips.plus - 15, chips.y - 19);
  const menuX = Math.min(1920 - 12 - MENU.w * S0, plusAt.x);
  const menuY = Math.max(10, plusAt.y - MENU.h * S0);
  const menuOn = f >= P.click + 2 && f < P.web + 2;
  const spot = (p: { x: number; y: number }) => ({ x: menuX + p.x * S0, y: menuY + p.y * S0 });

  // the cursor in the last phrase: the +, Sonnet, web; the version's button; the fold chip; the icon
  const plus = at(chips.plus + 2, chips.y + 3);
  const sonnet = spot(menuSpot.model(2));
  const web = spot(menuSpot.folder(2));
  const verBtn = at(D_VER_BTN.x, box.h - 72 - 27 + 5 + 11);
  const foldChip = at(chips.fold + 1, chips.y + 2);
  const icon = { x: MIC.x + 2, y: MIC.y + 4 };
  const path: [number, { x: number; y: number }][] = [
    [T.plus + 4, { x: 1180, y: 1100 }],
    [P.hover, plus],
    [P.click + 8, plus],
    [P.sonnet - 4, sonnet],
    [P.sonnet + 8, sonnet],
    [P.web - 4, web],
    [P.web + 10, web],
    [V.hover - 8, { x: web.x + 40, y: web.y + 300 }],
    [V.hover, verBtn],
    [V.click + 14, verBtn],
    [F.hover - 4, foldChip],
    [F.fold + 6, foldChip],
    [F.iconHover, icon],
    [F.unfold + 6, icon],
    [F.unfold + 40, { x: icon.x + 260, y: icon.y + 160 }],
  ];
  const cursorOn = f >= T.plus + 4 && f < F.unfold + 40;
  let cur = path[0][1];
  for (let i = 1; i < path.length; i++) {
    if (f < path[i][0]) {
      const k = prog(f, path[i - 1][0], path[i][0], EASE_IN_OUT);
      cur = { x: path[i - 1][1].x + (path[i][1].x - path[i - 1][1].x) * k, y: path[i - 1][1].y + (path[i][1].y - path[i - 1][1].y) * k };
      break;
    }
    cur = path[i][1];
  }
  const clickAt = [P.click, P.sonnet, P.web, V.click, F.fold, F.unfold];
  const press = Math.max(0, ...clickAt.map((c) => (f >= c - 2 && f < c + 3 ? 1 : 0)));

  return (
    <AbsoluteFill>
      {/* soft accent glow behind the widget */}
      <div
        style={{
          position: "absolute",
          left: RIGHT - 1100,
          top: MIC.y - 300 - box.h * S0 * 0.6,
          width: 1300,
          height: 1100,
          background: "radial-gradient(closest-side, rgba(91,157,255,.13), rgba(91,157,255,0))",
          opacity: prog(f, T.unfold, T.unfold + 20) * fade,
        }}
      />

      <Terminal f={f} at={NEW_SESSION} out={T.version - 4} />
      <Terminal f={f} at={T.check + 6} out={T.numbers - 8} top={640} h={330} prompt={SAID} typed={Math.min(1, Math.max(0, (f - K.fix) / 14))} />
      <ErrorChart f={f} at={T.numbers + 2} out={CUT - 12} />

      <div
        style={{
          position: "absolute",
          right: 1920 - RIGHT,
          bottom: 1080 - BOTTOM,
          transform: `translate(${tx}px, ${ty}px) scale(${S})`,
          transformOrigin: "100% 100%",
        }}
      >
        {widget}
      </div>

      <SoundRings f={f} from={T.read + 4} to={T.plus} at={SPEAKER} />

      {/* what it's busy with, in words beside the circles (ui.StatusChip): shown 300 ms after the key is let go */}
      {f >= K.up + 9 && f < K.fix + 6 ? (
        <div
          style={{
            position: "absolute",
            left: SPEAKER.x - 26 * S0 - 14 * S0 - statusWidth(f >= K.check ? CHECKING : TRANSCRIBING) * S0,
            top: MIC.y - (STATUS_H / 2) * S0,
            transform: `scale(${S0})`,
            transformOrigin: "0 0",
            opacity: Math.min(prog(f, K.up + 9, K.up + 14), 1 - prog(f, K.fix, K.fix + 6)),
          }}
        >
          <StatusChip text={f >= K.check ? CHECKING : TRANSCRIBING} moon={f * 0.16} />
        </div>
      ) : null}

      {f >= T.done && f < T.waiting ? (
        <div style={bubble(T.done, T.waiting - 2)}>
          <Bubble kind="done" title="Nová úvodní stránka" note="hotovo" lines={["Stránka je hotová a nasazená. Přidal jsem", "i video do horní části."]} tailY={26} />
        </div>
      ) : null}
      {f >= T.waiting && f < T.agent ? (
        <div style={bubble(T.waiting, T.agent - 2)}>
          <Bubble kind="waiting" title="Oprava exportu faktur" note="čeká na tebe" lines={["Můžu přepsat starý export? Potřebuju", "tvoje svolení."]} tailY={26} />
        </div>
      ) : null}
      {f >= T.read + 4 && f < T.plus + 4 ? (
        <div style={bubble(T.read + 4, T.plus + 4)}>
          <Bubble kind="info" title="Artefakt z relace eshop" note="čtu nahlas" lines={["Katalog má 48 stran a ceny jsou nově", "v korunách. Překlad je hotový."]} tailY={26} />
        </div>
      ) : null}
      {f >= K.fix + 8 && f < T.numbers + 18 ? (
        <div style={{ ...bubble(K.fix + 8, T.numbers + 18), top: checkTop }}>
          <Bubble kind="done" title="Kontrola přepisu" note="" lines={CHECK_BUBBLE} tailY={checkTail} />
        </div>
      ) : null}
      {f >= V.done && f < T.fold - 2 ? (
        <div style={bubble(V.done, T.fold - 2)}>
          <Bubble kind="done" title="Claude Code je aktualizovaný" note="" lines={["Hotovo: 2.1.303 → 2.1.304. Relace, které", "běží, ji dostanou, až je otevřeš znovu."]} tailY={26} />
        </div>
      ) : null}

      {menuOn ? (
        <div
          style={{
            position: "absolute",
            left: menuX,
            top: menuY,
            transform: `scale(${S0})`,
            transformOrigin: "0 0",
            opacity: prog(f, P.click + 2, P.click + 6),
          }}
        >
          <NewSessionMenu
            model={f >= P.sonnet ? 2 : 1}
            modelHover={f >= P.sonnet - 6 && f < P.sonnet ? 2 : -1}
            hover={f >= P.web - 8 ? 2 : -1}
            hoverLight={prog(f, P.web - 8, P.web - 4)}
          />
        </div>
      ) : null}

      {cursorOn ? <Cursor x={cur.x} y={cur.y} press={press} /> : null}

      <Caption f={f} at={T.limits} until={T.sessions} lines={["Limity Clauda", "máš pořád", "na očích."]} note="5hodinové okno, týden i Fable. Obnovuje se samo." />
      <Caption f={f} at={T.sessions} until={T.done} lines={["Vidíš, co dělá", "každá relace."]} note="Pracuje, čeká na tebe, hotovo. Každá složka ve své barvě." />
      <Caption f={f} at={T.done} until={T.waiting} lines={["Ozve se, když", "Claude dodělá."]} note="Klikneš na bublinu a jsi zpátky v relaci." />
      <Caption f={f} at={T.waiting} until={T.agent} lines={["A zaklepe,", "když čeká", "na tebe."]} note="Žádné hlídání terminálů." />
      <AgentColumn f={f} />
      <Caption f={f} at={T.read} until={T.plus} lines={["Odpovědi ti", "přečte nahlas."]} note="I shrnutí artefaktu, který relace zveřejní." />
      <Caption f={f} at={T.plus} until={T.version} top={150} lines={["Nová relace", "jedním klikem."]} note="V oblíbené složce, s modelem, jaký chceš." />
      <Caption f={f} at={T.version} until={T.fold} lines={["Claude Code", "vždy aktuální."]} note="Verzi vidíš pod panelem. Novou nainstaluješ jedním klikem." />
      <Caption f={f} at={T.fold} until={T.check} lines={["Zbalíš ho", "do ikonky."]} note="Diktuje dál. Klikneš a panel je celý zpátky." />
      <CheckColumn f={f} />
      <Caption
        f={f}
        at={T.numbers}
        until={CUT}
        top={150}
        lines={["Až o polovinu", "méně chyb."]}
        note="Druhý rozpoznávač běží u tebe na procesoru. Claude dostane jen text, zvuk nikdy."
      />
    </AbsoluteFill>
  );
};
