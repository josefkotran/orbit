import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Bubble } from "../components/Bubble";
import { Feed, FeedRow, OrbitWidget, Sess, panelHeight } from "../components/OrbitWidget";
import { KIN, Kinetic } from "../components/Kinetic";
import { Words, sub } from "../components/Text";
import { EASE_IN_OUT, EXPO_OUT, lerp, pop, prog, rise, sink } from "../lib/anim";
import { C, TEXT } from "../lib/theme";
import { bar, CUT, DROP } from "../lib/time";
import { speechLevel } from "./Dictation";
import { OUTRO_MIC } from "./Outro";

// After the drop: Orbit's panel in the bottom right corner of the "screen", captions on the left.
export const T = {
  limits: DROP,
  sessions: bar(18),
  done: bar(20),
  waiting: bar(22),
  agent: bar(24),
  reply1: bar(25),
  ask2: bar(26),
  confirm: bar(27),
  yes: bar(28),
  read: bar(29),
  end: CUT,
};
const LISTEN_LEN = 46;
export const AGENT_EVENTS = {
  listen: [T.agent, T.ask2, T.yes],
  stop: [T.agent + LISTEN_LEN, T.ask2 + LISTEN_LEN, T.yes + 16],
  sent: T.yes + 24,
};

const S = 2.25;
const RIGHT = 1830;
const BOTTOM = 960;
const MIC = { x: RIGHT - 36 * S, y: BOTTOM - 36 * S };
const SPEAKER = { x: MIC.x - 60 * S, y: MIC.y };

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
    [T.sessions, T.sessions + 14, T.agent, T.agent + 10, T.reply1, T.reply1 + 10, T.confirm, T.confirm + 12],
    [
      panelHeight(3, 0, null),
      panelHeight(3, 3, null),
      panelHeight(3, 3, null),
      panelHeight(3, 3, 1),
      panelHeight(3, 3, 1),
      panelHeight(3, 3, 2),
      panelHeight(3, 3, 2),
      panelHeight(3, 3, 4),
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
  if (f < T.agent) return null;
  const st = agentState(f);
  const status =
    st === "listening" ? "Poslouchám…" : st === "thinking" ? "Přemýšlím…" : st === "speaking" ? "Mluví" : st === "confirm" ? "Mám? Řekni „jo“" : "";
  const statusColor = st === "listening" ? C.appListen : st === "confirm" ? C.busy : undefined;
  const rows: FeedRow[] = [];
  const asked2 = f >= AGENT_EVENTS.stop[1];
  if (f >= AGENT_EVENTS.stop[0] - 6) rows.push({ kind: "you", text: asked2 ? Q2 : Q1, opacity: prog(f, AGENT_EVENTS.stop[0] - 6, AGENT_EVENTS.stop[0] + 2) });
  if (f >= T.reply1) rows.push({ kind: "reply", text: f >= T.confirm ? A2 : A1, opacity: prog(f, T.reply1, T.reply1 + 8) });
  if (f >= T.confirm) {
    const sent = f >= AGENT_EVENTS.sent;
    rows.push({
      kind: "target",
      name: "Překlad katalogu z němčiny",
      folder: "eshop",
      label: sent ? "odesláno ✓" : f >= AGENT_EVENTS.stop[2] ? "posílám…" : "čeká na tvoje „jo“",
      color: sent ? C.done : f >= AGENT_EVENTS.stop[2] ? undefined : C.busy,
      opacity: prog(f, T.confirm + 4, T.confirm + 12),
    });
    rows.push({ kind: "message", text: MSG, opacity: prog(f, T.confirm + 8, T.confirm + 16) });
  }
  return { status, statusColor, rows };
};

/** Left column: headline + note that swap per section. */
const Caption: React.FC<{ f: number; at: number; until: number; lines: string[]; note: string }> = ({ f, at, until, lines, note }) => {
  if (f < at - 1 || f > until + 8) return null;
  return (
    <div style={{ position: "absolute", left: 110, top: 0, bottom: 0, width: 680, display: "flex", flexDirection: "column", justifyContent: "center" }}>
      <Kinetic lines={lines} at={at + 3} out={until - 14} cfg={KIN.h2} size={74} lineHeight={1.02} />
      <Words text={note} at={at + 14} out={until - 12} style={{ ...sub(34), marginTop: 30 }} />
    </div>
  );
};

/** What Pepa says to the agent: Anybody italic, each word when it is spoken, shivering with his voice. */
const SaidLine: React.FC<{ f: number; lines: string[]; at: number; out: number; size?: number }> = ({ f, lines, at, out, size = 50 }) => {
  const idx = AGENT_EVENTS.listen.indexOf(at);
  const level = idx >= 0 && f >= at && f < AGENT_EVENTS.stop[idx] ? speechLevel(f, words(lines.join(" "), at)) : 0;
  return (
    <Kinetic
      lines={lines}
      at={at}
      wordAt={(w) => at + 4 + w * 7}
      dur={16}
      out={out}
      cfg={KIN.said}
      italic
      size={size}
      lineHeight={1.12}
      level={level}
    />
  );
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
const SoundRings: React.FC<{ f: number; from: number; to: number }> = ({ f, from, to }) => {
  if (f < from || f > to + 30) return null;
  const fade = 1 - prog(f, to - 10, to + 20);
  return (
    <>
      {[0, 1, 2].map((k) => {
        const t = (((f - from + k * 12) % 36) + 36) % 36 / 36;
        const r = 30 + t * 90;
        return (
          <div
            key={k}
            style={{
              position: "absolute",
              left: SPEAKER.x - r,
              top: SPEAKER.y - r,
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

export const Claude: React.FC = () => {
  const f = useCurrentFrame();
  if (f < DROP - 1 || f >= OUTRO_MIC.at) return null;
  const ph = heightAt(f);
  const st = agentState(f);
  const ask = [Q1, Q2, "Jo."];
  const listenIdx = AGENT_EVENTS.listen.findIndex((s, i) => f >= s && f < AGENT_EVENTS.stop[i]);
  const agentLevel =
    listenIdx >= 0 ? speechLevel(f, words(ask[listenIdx], AGENT_EVENTS.listen[listenIdx])) : 0;

  const sessions: Sess[] = [
    { name: "Překlad katalogu z němčiny", folder: "eshop", state: "working", context: 0.34 },
    { name: "Oprava exportu faktur", folder: "faktury", state: f >= T.waiting ? "waiting" : "working", context: 0.12 },
    { name: "Nová úvodní stránka", folder: "web", state: f >= T.done ? "done" : "working", context: 0.57 },
  ].map((s, i) => {
    const t = prog(f, T.sessions + 4 + i * 7, T.sessions + 20 + i * 7);
    return { ...s, state: s.state as Sess["state"], opacity: t, x: (1 - t) * 16 };
  });
  const showSessions = f >= T.sessions;

  const limits = [
    { label: "5 h", percent: 42 },
    { label: "Týden", percent: 63 },
    { label: "Fable", percent: 28 },
  ].map((l, i) => ({ ...l, percent: l.percent * prog(f, DROP + 10 + i * 7, DROP + 50 + i * 7, EXPO_OUT) }));

  const enter = pop(f, DROP, 15, 0.8);
  // when the drums stop the mic flies to the centre and becomes the outro's mic (OUTRO_MIC)
  const exit = prog(f, CUT, CUT + 30, EASE_IN_OUT);
  const fade = 1 - prog(f, CUT, CUT + 12);
  const scaleEnd = OUTRO_MIC.d / 52;
  const widgetScale = S * (0.86 + 0.14 * enter) + (scaleEnd - S) * exit;
  const tx = (OUTRO_MIC.x - RIGHT + 36 * scaleEnd) * exit;
  const ty = (OUTRO_MIC.y - BOTTOM + 36 * scaleEnd) * exit;
  const H = 40 + ph + 72;

  // light sweep across the panel right after the drop
  const sweep = prog(f, DROP + 4, DROP + 34, EASE_IN_OUT);
  const panelTop = BOTTOM - (H - 40) * S;

  const bubbleX = SPEAKER.x - 26 * S - 6 * S - 338 * S;
  const bubbleY = MIC.y - 26 * S;
  const bubble = (from: number, to: number) => {
    const t = prog(f, from, from + 9);
    const o = Math.min(prog(f, from, from + 6), 1 - prog(f, to - 8, to));
    return {
      position: "absolute" as const,
      left: bubbleX,
      top: bubbleY,
      transform: `translateX(${(1 - t) * 20}px) scale(${S})`,
      transformOrigin: "0 0",
      opacity: o,
    };
  };

  return (
    <AbsoluteFill>
      {/* soft accent glow behind the widget */}
      <div
        style={{
          position: "absolute",
          left: RIGHT - 1100,
          top: panelTop - 300,
          width: 1300,
          height: 1100,
          background: "radial-gradient(closest-side, rgba(91,157,255,.13), rgba(91,157,255,0))",
          opacity: enter * fade,
        }}
      />

      <div
        style={{
          position: "absolute",
          right: 1920 - RIGHT,
          bottom: 1080 - BOTTOM,
          transform: `translate(${tx}px, ${ty}px) scale(${widgetScale})`,
          transformOrigin: "100% 100%",
          opacity: prog(f, DROP, DROP + 8),
        }}
      >
        <OrbitWidget
          height={ph}
          panelOpacity={fade}
          speakerOpacity={fade}
          limits={limits}
          sessions={showSessions ? sessions : []}
          feed={feedAt(f)}
          agent={st === "idle" ? "idle" : st}
          agentLevel={agentLevel}
          notes={2}
          phase={f * 0.12}
          reading={f >= T.read + 4 && f < T.end}
        />
        {sweep > 0 && sweep < 1 ? (
          <div
            style={{
              position: "absolute",
              left: 0,
              top: 40,
              width: 440,
              height: ph,
              borderRadius: 10,
              overflow: "hidden",
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: -60,
                bottom: -60,
                width: 120,
                left: -160 + sweep * 760,
                transform: "rotate(18deg)",
                background: "linear-gradient(90deg, rgba(255,255,255,0), rgba(255,255,255,.10), rgba(255,255,255,0))",
              }}
            />
          </div>
        ) : null}
      </div>

      <SoundRings f={f} from={T.read + 4} to={T.end} />

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
      {f >= T.read + 4 ? (
        <div style={bubble(T.read + 4, T.end + 20)}>
          <Bubble kind="info" title="Artefakt z relace eshop" note="čtu nahlas" lines={["Katalog má 48 stran a ceny jsou nově", "v korunách. Překlad je hotový."]} tailY={26} />
        </div>
      ) : null}

      <Caption f={f} at={T.limits} until={T.sessions} lines={["Limity Clauda", "máš pořád", "na očích."]} note="5hodinové okno, týden i Fable. Obnovuje se samo." />
      <Caption f={f} at={T.sessions} until={T.done} lines={["Vidíš, co dělá", "každá relace."]} note="Pracuje, čeká na tebe, hotovo. I kolik má kontextu." />
      <Caption f={f} at={T.done} until={T.waiting} lines={["Ozve se, když", "Claude dodělá."]} note="Klikneš na bublinu a jsi zpátky v relaci." />
      <Caption f={f} at={T.waiting} until={T.agent} lines={["A zaklepe,", "když čeká", "na tebe."]} note="Žádné hlídání terminálů." />
      <AgentColumn f={f} />
      <Caption f={f} at={T.read} until={T.end} lines={["Odpovědi ti", "přečte nahlas."]} note="I shrnutí artefaktu, který relace zveřejní." />
    </AbsoluteFill>
  );
};
