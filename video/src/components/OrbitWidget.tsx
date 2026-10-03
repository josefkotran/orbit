import React from "react";
import { C, GLYPH, ICONS, UI } from "../lib/theme";

// A faithful replica of app/ui.py FloatingButton (same geometry, colours and fonts), drawn in logical pixels
// and scaled as a whole. The panel sits above the button, lined up with its right edge ("right" alignment).

export const D = {
  DIAMETER: 52,
  MARGIN: 10,
  GAP: 8,
  PANEL_W: 440,
  PAD: 8,
  HEADER_H: 16,
  ROW_H: 18,
  SEP_H: 9,
  DOT: 10,
  DOT_STEP: 20,
  PILL_H: 22,
  AGENT_D: 30,
  STRIP_H: 40,
  FEED_LINE: 15,
};
const SIDE = D.DIAMETER + 2 * D.MARGIN; // 72
export const WIDGET_W = D.PANEL_W + D.MARGIN; // 450
export const BUTTONS_W = Math.floor((D.DIAMETER * 3) / 2) + D.GAP - SIDE / 2 + 4 + SIDE; // 126 without a panel

const TEXT = "#E6E8EC";
const DIM = "#9AA1AD";
const PANEL_BG = "rgba(24,27,34,.92)";
const PANEL_LINE = "rgba(255,255,255,.11)";
const SEP = "rgba(255,255,255,.086)";

export type MicState = "idle" | "recording" | "busy" | "loading";
export type AgentState = "idle" | "listening" | "transcribing" | "thinking" | "speaking" | "confirm";
export type SessionState = "working" | "waiting" | "done" | "idle" | "error";

export type Limit = { label: string; percent: number };
export type Sess = { name: string; folder: string; state: SessionState; context: number; opacity?: number; x?: number };
export type FeedRow =
  | { kind: "you"; text: string; opacity?: number }
  | { kind: "reply"; text: string; opacity?: number }
  | { kind: "target"; name: string; folder: string; label: string; color?: string; opacity?: number }
  | { kind: "message"; text: string; opacity?: number };
export type Feed = { status: string; statusColor?: string; rows: FeedRow[] };

const SESSION_COLORS: Record<SessionState, string> = {
  working: "#5B9DFF",
  waiting: "#F5A524",
  done: "#3DD68C",
  idle: "#5B6272",
  error: "#E5484D",
};
const STATE_LABELS: Record<SessionState, string> = {
  working: "pracuje",
  waiting: "čeká na tebe",
  done: "hotovo",
  idle: "v klidu",
  error: "chyba",
};

const barColor = (p: number, accent: string) => (p >= 90 ? "#E5484D" : p >= 70 ? "#F5A524" : accent);

export const panelHeight = (limits: number, sessions: number, feedRows: number | null) => {
  let h = D.PAD + D.HEADER_H + D.PAD - 2;
  h += limits * D.ROW_H;
  if (sessions) h += (limits ? D.SEP_H : 0) + sessions * D.ROW_H;
  if (feedRows !== null) h += D.SEP_H + D.ROW_H + feedRows * D.FEED_LINE;
  return h;
};

type Props = {
  mic?: MicState;
  level?: number;
  phase?: number;
  accent?: string;
  /** Panel (and colour dots + agent chip) shown at all, and how visible. */
  panel?: boolean;
  panelOpacity?: number;
  /** Override for the panel height while it grows (logical px). */
  height?: number;
  note?: string;
  limits?: Limit[];
  limitsOpacity?: number;
  sessions?: Sess[];
  feed?: Feed | null;
  agent?: AgentState;
  agentLevel?: number;
  reading?: boolean;
  muted?: boolean;
  theme?: "blue" | "violet" | "teal";
  /** 0..1 press feedback on the mic (a slightly darker circle). */
  pressed?: number;
  speakerOpacity?: number;
  micOpacity?: number;
};

const glyph = (size: number, color: string, ch: string, extra?: React.CSSProperties) => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      fontFamily: ICONS,
      fontSize: size,
      color,
      lineHeight: 1,
      ...extra,
    }}
  >
    {ch}
  </div>
);

/** Ellipse arc as a polyline path, in Qt's convention: degrees counter-clockwise from 3 o'clock. */
const arc = (a: number, b: number, fromDeg: number, spanDeg: number) => {
  const pts: string[] = [];
  const n = 48;
  for (let i = 0; i <= n; i++) {
    const t = ((fromDeg + (spanDeg * i) / n) * Math.PI) / 180;
    pts.push(`${(a * Math.cos(t)).toFixed(3)},${(-b * Math.sin(t)).toFixed(3)}`);
  }
  return `M${pts.join("L")}`;
};

const Circle: React.FC<{ cx: number; cy: number; bg: string; children?: React.ReactNode }> = ({ cx, cy, bg, children }) => {
  const r = D.DIAMETER / 2;
  return (
    <div
      style={{
        position: "absolute",
        left: cx - r,
        top: cy - r,
        width: 2 * r,
        height: 2 * r,
        borderRadius: "50%",
        background: bg,
        boxShadow: "inset 0 0 0 1.3px rgba(0,0,0,.235)",
      }}
    >
      {children}
    </div>
  );
};

export const AgentChip: React.FC<{ state: AgentState; level: number; phase: number; accent: string; size?: number }> = ({
  state,
  level,
  phase,
  accent,
  size = D.AGENT_D,
}) => {
  const r = size / 2;
  const color = state === "listening" ? C.appListen : state === "confirm" ? C.busy : accent;
  const bg = state === "listening" ? C.appListen : "#181B22";
  const ink = state === "listening" ? "#FFFFFF" : color;
  const a = r * 0.8;
  const b = r * 0.27;
  const planet = r * 0.38;
  const moon = r * 0.15;
  const t = state === "transcribing" || state === "thinking" ? phase * 1.6 : (40 * Math.PI) / 180;
  const mx = a * Math.cos(t);
  const my = b * Math.sin(t);
  const front = Math.sin(t) >= 0;
  const pulse = state === "listening" ? level : 0.5 + 0.5 * Math.sin(phase * 2);
  const halo = state === "listening" || state === "speaking" || state === "confirm";
  const pad = 8;
  const moonEl = <circle cx={mx} cy={my} r={moon} fill={ink} stroke={bg} strokeWidth={1.6} />;
  const id = `pl${state}`;
  return (
    <svg
      width={size + 2 * pad}
      height={size + 2 * pad}
      viewBox={`${-r - pad} ${-r - pad} ${size + 2 * pad} ${size + 2 * pad}`}
      style={{ overflow: "visible" }}
    >
      <defs>
        <radialGradient id={id} cx={-planet * 0.45} cy={-planet * 0.5} r={planet * 1.6} gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor={shade(ink, 1.35)} />
          <stop offset="1" stopColor={shade(ink, 1 / 1.5)} />
        </radialGradient>
      </defs>
      {halo ? (
        <circle r={r + 1.5 + 3.5 * pulse} fill={color} opacity={(45 + 60 * pulse) / 255} />
      ) : null}
      <circle r={r - 0.5} fill={bg} stroke="rgba(255,255,255,.11)" strokeWidth={1} />
      <g transform="rotate(-24)">
        <path d={arc(a, b, 0, 180)} fill="none" stroke={ink} strokeOpacity={0.7} strokeWidth={1.6} />
        {front ? null : moonEl}
        <circle r={planet} fill={`url(#${id})`} />
        <path d={arc(a, b, 200, 140)} fill="none" stroke={bg} strokeWidth={4} />
        <path d={arc(a, b, 180, 180)} fill="none" stroke={ink} strokeWidth={1.6} strokeLinecap="round" />
        {front ? moonEl : null}
      </g>
    </svg>
  );
};

/** Qt's lighter()/darker() approximated in HSV value. */
function shade(hex: string, factor: number) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const f = (v: number) => Math.max(0, Math.min(255, Math.round(v * factor)));
  return `rgb(${f(r)},${f(g)},${f(b)})`;
}

export const OrbitWidget: React.FC<Props> = ({
  mic = "idle",
  level = 0,
  phase = 0,
  accent = C.accent,
  panel = true,
  panelOpacity = 1,
  height,
  note = "2 h 13 min",
  limits = [],
  limitsOpacity = 1,
  sessions = [],
  feed = null,
  agent = "idle",
  agentLevel = 0,
  reading = false,
  muted = false,
  theme = "blue",
  pressed = 0,
  speakerOpacity = 1,
  micOpacity = 1,
}) => {
  const natural = panelHeight(limits.length, sessions.length, feed ? feed.rows.length : null);
  const ph = height ?? natural;
  const slot = Math.floor((D.DIAMETER * 3) / 2) + D.GAP - SIDE / 2 + 4; // 54
  const W = panel ? WIDGET_W : slot + SIDE;
  const H = panel ? D.STRIP_H + ph + SIDE : SIDE;
  const bx = panel ? W - SIDE : slot;
  const by = panel ? D.STRIP_H + ph : 0;
  const mc = { x: bx + SIDE / 2, y: by + SIDE / 2 };
  const sc = { x: mc.x - D.DIAMETER - D.GAP, y: mc.y };
  const r = D.DIAMETER / 2;

  const micBg =
    mic === "recording" ? C.appListen : mic === "busy" ? C.busy : mic === "loading" ? "#5B6272" : pressed ? mixHex("#2F3542", "#232833", pressed) : "#2F3542";
  const micFg = mic === "busy" ? "#2A1C00" : mic === "loading" ? "#D7DBE3" : "#FFFFFF";

  // the panel, in its own coordinates
  const x = 10;
  const right = D.PANEL_W - 10;
  const rowW = right - x;
  let y = D.PAD;
  const rows: React.ReactNode[] = [];
  rows.push(
    <div key="head" style={{ position: "absolute", left: x, top: y, width: rowW, height: D.HEADER_H, lineHeight: `${D.HEADER_H}px` }}>
      <span style={{ fontWeight: 600, color: DIM }}>Claude</span>
      {limits.length ? (
        <span style={{ position: "absolute", right: 0, top: 0, color: DIM, display: "flex", alignItems: "center", gap: 0 }}>
          <span style={{ fontFamily: ICONS, fontSize: 12, color: TEXT, width: 14, textAlign: "center", marginRight: 4 }}>
            {GLYPH.refresh}
          </span>
          {note}
        </span>
      ) : null}
    </div>,
  );
  y += D.HEADER_H;
  limits.forEach((lim, i) => {
    const barW = rowW - 44 - 36 - 10;
    const filled = (barW * Math.min(100, Math.max(0, lim.percent))) / 100;
    rows.push(
      <div key={`l${i}`} style={{ position: "absolute", left: x, top: y, width: rowW, height: D.ROW_H, lineHeight: `${D.ROW_H}px`, opacity: limitsOpacity }}>
        <span style={{ position: "absolute", left: 0, fontWeight: 600, color: TEXT }}>{lim.label}</span>
        <span style={{ position: "absolute", right: 0, color: TEXT }}>{`${Math.round(lim.percent)} %`}</span>
        <div style={{ position: "absolute", left: 48, top: D.ROW_H / 2 - 3, width: barW, height: 6, borderRadius: 3, background: "rgba(255,255,255,.118)" }} />
        {filled > 0 ? (
          <div
            style={{
              position: "absolute",
              left: 48,
              top: D.ROW_H / 2 - 3,
              width: Math.max(6, filled),
              height: 6,
              borderRadius: 3,
              background: barColor(lim.percent, accent),
            }}
          />
        ) : null}
      </div>,
    );
    y += D.ROW_H;
  });
  if (sessions.length) {
    if (limits.length) {
      rows.push(<div key="sep1" style={{ position: "absolute", left: x, top: y + D.SEP_H / 2, width: rowW, height: 1, background: SEP }} />);
      y += D.SEP_H;
    }
    const folderW = 40;
    sessions.forEach((s, i) => {
      const nameW = rowW - 13 - (folderW + 10) - 70 - 34;
      const color = SESSION_COLORS[s.state];
      rows.push(
        <div
          key={`s${i}`}
          style={{
            position: "absolute",
            left: x,
            top: y,
            width: rowW,
            height: D.ROW_H,
            lineHeight: `${D.ROW_H}px`,
            opacity: s.opacity ?? 1,
            transform: s.x ? `translateX(${s.x}px)` : undefined,
          }}
        >
          <div style={{ position: "absolute", left: 0.5, top: D.ROW_H / 2 - 3.5, width: 7, height: 7, borderRadius: "50%", background: color }} />
          <span style={{ position: "absolute", left: 13, width: nameW, fontWeight: 600, color: TEXT, whiteSpace: "nowrap", overflow: "hidden" }}>
            {s.name}
          </span>
          <span style={{ position: "absolute", left: 13 + nameW + 10, color: DIM }}>{s.folder}</span>
          <span
            style={{
              position: "absolute",
              right: 34,
              width: 70,
              textAlign: "right",
              color: s.state === "waiting" || s.state === "error" ? color : DIM,
            }}
          >
            {STATE_LABELS[s.state]}
          </span>
          <span style={{ position: "absolute", right: 0, width: 34, textAlign: "right", color: s.context >= 0.8 ? C.busy : DIM }}>
            {`${Math.round(s.context * 100)} %`}
          </span>
        </div>,
      );
      y += D.ROW_H;
    });
  }
  if (feed) {
    rows.push(<div key="sep2" style={{ position: "absolute", left: x, top: y + D.SEP_H / 2, width: rowW, height: 1, background: SEP }} />);
    y += D.SEP_H;
    rows.push(
      <div key="fh" style={{ position: "absolute", left: x, top: y, width: rowW, height: D.ROW_H, lineHeight: `${D.ROW_H}px` }}>
        <span style={{ fontWeight: 600, color: accent }}>Agent Orbit</span>
        <span style={{ position: "absolute", right: 0, color: feed.statusColor ?? DIM }}>{feed.status}</span>
      </div>,
    );
    y += D.ROW_H;
    feed.rows.forEach((row, i) => {
      const base: React.CSSProperties = {
        position: "absolute",
        left: x,
        top: y,
        width: rowW,
        height: D.FEED_LINE,
        lineHeight: `${D.FEED_LINE}px`,
        whiteSpace: "nowrap",
        opacity: row.opacity ?? 1,
      };
      if (row.kind === "you") rows.push(<div key={`f${i}`} style={{ ...base, color: DIM }}>{`Ty: ${row.text}`}</div>);
      else if (row.kind === "reply") rows.push(<div key={`f${i}`} style={{ ...base, color: TEXT }}>{row.text}</div>);
      else if (row.kind === "target")
        rows.push(
          <div key={`f${i}`} style={base}>
            <span style={{ fontWeight: 600, color: TEXT }}>{`→ ${row.name}`}</span>
            <span style={{ color: DIM, marginLeft: 8 }}>{row.folder}</span>
            <span style={{ position: "absolute", right: 0, color: row.color ?? DIM }}>{row.label}</span>
          </div>,
        );
      else
        rows.push(
          <div key={`f${i}`} style={base}>
            <div style={{ position: "absolute", left: 1, top: 0, width: 2, height: D.FEED_LINE, background: accent }} />
            <span style={{ marginLeft: 10, color: TEXT }}>{row.text}</span>
          </div>,
        );
      y += D.FEED_LINE;
    });
  }

  // colour dots and the agent chip, just above the panel's right end
  const dotsY = D.STRIP_H - (4 + D.AGENT_D / 2);
  const firstDot = D.PANEL_W - D.PILL_H / 2 - D.DOT_STEP * 2;
  const themes: { name: "blue" | "violet" | "teal"; color: string }[] = [
    { name: "blue", color: C.accent },
    { name: "violet", color: C.violet },
    { name: "teal", color: C.teal },
  ];
  const agentX = firstDot - D.PILL_H / 2 - 8 - D.AGENT_D / 2;

  return (
    <div style={{ position: "relative", width: W, height: H, fontFamily: UI, fontSize: 11, color: TEXT }}>
      {panel ? (
        <div style={{ opacity: panelOpacity }}>
          <div
            style={{
              position: "absolute",
              left: 0.5,
              top: D.STRIP_H + 0.5,
              width: D.PANEL_W - 1,
              height: ph - 1,
              borderRadius: 10,
              background: PANEL_BG,
              boxShadow: `inset 0 0 0 1px ${PANEL_LINE}`,
              overflow: "hidden",
            }}
          >
            {rows}
          </div>
          <div
            style={{
              position: "absolute",
              left: firstDot - D.PILL_H / 2 + 0.5,
              top: dotsY - D.PILL_H / 2 + 0.5,
              width: D.DOT_STEP * 2 + D.PILL_H - 1,
              height: D.PILL_H - 1,
              borderRadius: D.PILL_H / 2,
              background: PANEL_BG,
              boxShadow: `inset 0 0 0 1px ${PANEL_LINE}`,
            }}
          />
          {themes.map((t, i) => {
            const cx = firstDot + i * D.DOT_STEP;
            return (
              <React.Fragment key={t.name}>
                <div style={{ position: "absolute", left: cx - 5, top: dotsY - 5, width: 10, height: 10, borderRadius: "50%", background: t.color }} />
                {t.name === theme ? (
                  <div
                    style={{
                      position: "absolute",
                      left: cx - 7.5 - 0.75,
                      top: dotsY - 7.5 - 0.75,
                      width: 15,
                      height: 15,
                      borderRadius: "50%",
                      border: "1.5px solid #E6E8EC",
                    }}
                  />
                ) : null}
              </React.Fragment>
            );
          })}
          <div style={{ position: "absolute", left: agentX - D.AGENT_D / 2 - 8, top: dotsY - D.AGENT_D / 2 - 8 }}>
            <AgentChip state={agent} level={agentLevel} phase={phase} accent={accent} />
          </div>
        </div>
      ) : null}

      {mic === "recording" ? (
        <div
          style={{
            position: "absolute",
            left: mc.x - (r + 2 + level * (D.MARGIN - 2)),
            top: mc.y - (r + 2 + level * (D.MARGIN - 2)),
            width: 2 * (r + 2 + level * (D.MARGIN - 2)),
            height: 2 * (r + 2 + level * (D.MARGIN - 2)),
            borderRadius: "50%",
            background: "rgba(229,72,77,.353)",
          }}
        />
      ) : null}
      <div style={{ opacity: micOpacity }}>
        <Circle cx={mc.x} cy={mc.y} bg={micBg}>
        {glyph(Math.floor(D.DIAMETER * 0.46), micFg, GLYPH.mic)}
        {mic === "busy" || mic === "loading" ? (
          <svg width={D.DIAMETER} height={D.DIAMETER} style={{ position: "absolute", inset: 0 }}>
            <path
              d={spinner(r, r, r - 4, -2 * ((phase * 180) / Math.PI), 90)}
              fill="none"
              stroke={micFg}
              strokeWidth={3}
              strokeLinecap="round"
            />
          </svg>
        ) : null}
        </Circle>
      </div>
      <div style={{ opacity: speakerOpacity }}>
        <Circle cx={sc.x} cy={sc.y} bg={reading ? accent : "#2F3542"}>
          {glyph(Math.floor(D.DIAMETER * 0.46), muted ? "#8B96AD" : "#FFFFFF", muted ? GLYPH.mute : GLYPH.speaker)}
        </Circle>
      </div>
    </div>
  );
};

/** Qt drawArc on a circle: start angle and span in degrees, counter-clockwise from 3 o'clock. */
function spinner(cx: number, cy: number, r: number, startDeg: number, spanDeg: number) {
  const pts: string[] = [];
  for (let i = 0; i <= 24; i++) {
    const t = ((startDeg + (spanDeg * i) / 24) * Math.PI) / 180;
    pts.push(`${(cx + r * Math.cos(t)).toFixed(2)},${(cy - r * Math.sin(t)).toFixed(2)}`);
  }
  return `M${pts.join("L")}`;
}

function mixHex(a: string, b: string, t: number) {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const ch = (s: number) => Math.round(((pa >> s) & 255) * (1 - t) + ((pb >> s) & 255) * t);
  return `rgb(${ch(16)},${ch(8)},${ch(0)})`;
}

export const widgetSize = (panel: boolean, ph: number) => ({
  w: panel ? WIDGET_W : BUTTONS_W,
  h: panel ? D.STRIP_H + ph + SIDE : SIDE,
  /** Mic circle centre, from the widget's top-left. */
  mic: panel ? { x: WIDGET_W - SIDE / 2, y: D.STRIP_H + ph + SIDE / 2 } : { x: BUTTONS_W - SIDE / 2, y: SIDE / 2 },
});
