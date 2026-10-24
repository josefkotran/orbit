import React from "react";
import { C, GLYPH, ICONS, UI, UI_VAR } from "../lib/theme";

// A faithful replica of app/ui.py FloatingButton (same geometry, colours and fonts), drawn in logical pixels
// and scaled as a whole. The panel sits above the button, lined up with its right edge ("right" alignment), with
// Claude Code's version in a pill between the panel and the circles; folded, it is just Orbit's icon where the mic is.
// Checked against the real widget rendered by capture/grab.py (the WidgetTest composition).

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
  VER_PILL_H: 22,
  VER_GAP: 5,
  ICON_D: 44,
};
export const SIDE = D.DIAMETER + 2 * D.MARGIN; // 72
export const WIDGET_W = D.PANEL_W + D.MARGIN; // 450
const SLOT = Math.floor((D.DIAMETER * 3) / 2) + D.GAP - SIDE / 2 + 4; // 54: room left of the mic for the speaker
export const BUTTONS_W = SLOT + SIDE; // 126 without a panel
const VER_H = D.VER_PILL_H + D.VER_GAP;

const TEXT = "#E6E8EC";
const DIM = "#9AA1AD";
const PANEL_BG = "rgba(24,27,34,.92)"; // tint("#181B22") at alpha 235
const CHIP_BG = "#181B22";
const PANEL_LINE = "rgba(255,255,255,.11)";
const SEP = "rgba(255,255,255,.086)";
const INK = "#C9D1DC";

export const GLYPHS = {
  history: String.fromCharCode(0xe81c),
  dictations: String.fromCharCode(0xe8bd),
  add: String.fromCharCode(0xe710),
  phone: String.fromCharCode(0xe717),
  edit: String.fromCharCode(0xe70f),
  waves: [0xe993, 0xe994, 0xe995].map((c) => String.fromCharCode(c)),
};

export type MicState = "idle" | "recording" | "busy" | "loading";
export type AgentState = "idle" | "listening" | "transcribing" | "thinking" | "speaking" | "confirm";
export type SessionState = "working" | "waiting" | "done" | "idle" | "error";

export type Limit = { label: string; percent: number };
export type Sess = {
  /** Its topic; "" = Claude Code hasn't named it yet ("Nová relace", dim). */
  name: string;
  folder: string;
  /** Its folder's colour (colors.py): the stripe and the folder's name. */
  color: string;
  state: SessionState;
  /** How full its context is (0..1); negative: not known yet (no number). */
  context: number;
  /** Another model than the default: its exact name after the topic ("Sonnet 5.5"). */
  model?: string;
  /** Orbit switches it to this one right now: "→ Sonnet 5.5" in the accent colour. */
  switching?: string;
  opacity?: number;
  x?: number;
};
export type FeedRow =
  | { kind: "you"; text: string; opacity?: number }
  | { kind: "reply"; text: string; opacity?: number }
  | { kind: "target"; name: string; folder: string; label: string; color?: string; opacity?: number }
  | { kind: "message"; text: string; opacity?: number };
export type Feed = { status: string; statusColor?: string; rows: FeedRow[] };
/** Right side of the header: an orange warning, the dim rest, the refresh icon before it. */
export type HeaderNote = { warn?: string; rest: string; refresh?: boolean };
export type Version = {
  state: "current" | "new" | "updating" | "failed";
  installed: string;
  latest?: string;
  /** 0..1: the mouse over its button, and pressed. */
  hover?: number;
  press?: number;
};
/** The shimmer of the unfold animation (foldfx _shimmer): a ring of light from the mic outwards, on the picture. */
export type Shimmer = { cx: number; cy: number; rho: number; band: number; alpha: number; color: string };

const SESSION_COLORS: Record<SessionState, string> = {
  working: "#5B9DFF",
  waiting: "#F5A524",
  done: "#3DD68C",
  idle: "#3DD68C",
  error: "#E5484D",
};
const STATE_LABELS: Record<SessionState, string> = {
  working: "pracuje",
  waiting: "čeká na tebe",
  done: "hotovo",
  idle: "hotovo",
  error: "chyba",
};

const barColor = (p: number, accent: string) => (p >= 90 ? "#E5484D" : p >= 70 ? "#F5A524" : accent);

// text widths, as Qt measures them (the same Windows fonts in the same Chrome that renders the video)
let ctx: CanvasRenderingContext2D | null = null;
export const measure = (text: string, size = 11, weight = 400, family = UI) => {
  if (!ctx) ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) return text.length * size * 0.5;
  ctx.font = `${weight} ${size}px ${family}`;
  return ctx.measureText(text).width;
};

export const panelHeight = (limits: number, sessions: number, feedRows: number | null) => {
  let h = D.PAD + D.HEADER_H + D.PAD - 2;
  h += limits * D.ROW_H;
  if (sessions) h += (limits ? D.SEP_H : 0) + sessions * D.ROW_H;
  if (feedRows !== null) h += D.SEP_H + D.ROW_H + feedRows * D.FEED_LINE;
  return h;
};

/** The widget's size and the mic's centre (from its top left) for a panel of height ph (null: no panel). */
export const widgetBox = (ph: number | null, version = true) => {
  if (ph === null) return { w: BUTTONS_W, h: SIDE, mic: { x: BUTTONS_W - SIDE / 2, y: SIDE / 2 } };
  const vh = version ? VER_H : 0;
  const h = D.STRIP_H + ph + vh + SIDE;
  return { w: WIDGET_W, h, mic: { x: WIDGET_W - SIDE / 2, y: h - SIDE / 2 } };
};

/** Centres of the chips in the strip above the panel (ui.py _dots, _fold_center, _agent_center, …). */
export const chips = (() => {
  const y = D.STRIP_H - (4 + D.AGENT_D / 2);
  const fold = D.PANEL_W - 2 - D.AGENT_D / 2;
  const right = D.PANEL_W - 2 - D.AGENT_D - 8;
  const first = right - D.PILL_H / 2 - D.DOT_STEP * 2;
  const agent = first - D.PILL_H / 2 - 8 - D.AGENT_D / 2;
  const history = agent - D.AGENT_D - 6;
  const plus = history - D.AGENT_D - 6;
  const phone = plus - D.AGENT_D - 6;
  const notes = 2 + D.AGENT_D / 2;
  return { y, fold, dots: [first, first + D.DOT_STEP, first + 2 * D.DOT_STEP], agent, history, plus, phone, notes, dictations: notes + D.AGENT_D + 6 };
})();

/** The widget's opaque parts with a panel of height ph (for the fold animation's stars): the panel, the strip's chips
 * and pills, the version pill (about versionW wide), the two circles. */
export const widgetShapes = (ph: number, versionW = 190) => {
  const { h, mic } = widgetBox(ph);
  const r = D.AGENT_D / 2;
  const verTop = D.STRIP_H + ph + D.VER_GAP;
  return [
    { kind: "rect" as const, x: 0, y: D.STRIP_H, w: D.PANEL_W, h: ph },
    ...[chips.notes, chips.dictations, chips.phone, chips.plus, chips.history, chips.agent, chips.fold].map((x) => ({ kind: "circle" as const, x, y: chips.y, r })),
    { kind: "rect" as const, x: chips.dots[0] - D.PILL_H / 2, y: chips.y - D.PILL_H / 2, w: D.DOT_STEP * 2 + D.PILL_H, h: D.PILL_H },
    { kind: "rect" as const, x: D.PANEL_W - versionW, y: verTop, w: versionW, h: D.VER_PILL_H },
    { kind: "circle" as const, x: mic.x - D.DIAMETER - D.GAP, y: mic.y, r: D.DIAMETER / 2 },
    { kind: "circle" as const, x: mic.x, y: mic.y, r: D.DIAMETER / 2 },
  ].filter(() => h > 0);
};

type Props = {
  mic?: MicState;
  /** The dictation is an instruction for editing text (Ctrl held): a pencil instead of the mic. */
  editing?: boolean;
  level?: number;
  phase?: number;
  /** The working sessions' screwdrivers (ui.py _work_phase). */
  workPhase?: number;
  accent?: string;
  /** Panel (and colour dots, agent and notebook chips) shown at all, and how visible. */
  panel?: boolean;
  panelOpacity?: number;
  /** Override for the panel height while it grows (logical px). */
  height?: number;
  header?: HeaderNote;
  limits?: Limit[];
  limitsOpacity?: number;
  sessions?: Sess[];
  feed?: Feed | null;
  agent?: AgentState;
  agentLevel?: number;
  /** Tasks in Aktivní: the number on the notebook chip at the panel's left end (0 = none). */
  notes?: number;
  /** Claude Code's version under the panel (null: none). */
  version?: Version | null;
  reading?: boolean;
  /** Which of the speaker's growing waves while reading (0–2). */
  wave?: number;
  muted?: boolean;
  theme?: "blue" | "violet" | "teal";
  /** 0..1 press feedback on the mic (a slightly darker circle). */
  pressed?: number;
  /** 0..1 the mouse over the fold chip, the +. */
  foldHover?: number;
  plusHover?: number;
  speakerOpacity?: number;
  micOpacity?: number;
  /** Folded into Orbit's icon (just the mic's square). */
  collapsed?: boolean;
  /** 0..1 the mouse over the icon (lighter). */
  iconHover?: number;
  shimmer?: Shimmer | null;
};

/** Text drawn on an opaque circle gets Chrome's LCD (subpixel) antialiasing, whose blue and orange fringes show in
 * the video; in a group of its own that isn't quite opaque it gets grey antialiasing like the rest. */
export const GREY_AA = 0.999;

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
      opacity: GREY_AA,
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

const Circle: React.FC<{ cx: number; cy: number; bg: string; outline?: string; children?: React.ReactNode }> = ({ cx, cy, bg, outline, children }) => {
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
        boxShadow: `inset 0 0 0 1.3px ${outline ?? "rgba(0,0,0,.235)"}`,
      }}
    >
      {children}
    </div>
  );
};

/** A chip of the strip: a dark circle with a hairline, its content in the middle. */
const Chip: React.FC<{ cx: number; cy: number; bg?: string; line?: string; children?: React.ReactNode }> = ({ cx, cy, bg = CHIP_BG, line = PANEL_LINE, children }) => {
  const r = D.AGENT_D / 2;
  return (
    <div style={{ position: "absolute", left: cx - r, top: cy - r, width: 2 * r, height: 2 * r }}>
      <div style={{ position: "absolute", inset: 0.5, borderRadius: "50%", background: bg, boxShadow: `inset 0 0 0 1px ${line}` }} />
      {children}
    </div>
  );
};

const Badge: React.FC<{ n: number; accent: string }> = ({ n, accent }) => {
  const r = D.AGENT_D / 2;
  return (
    <svg width={D.AGENT_D} height={D.AGENT_D} viewBox={`${-r} ${-r} ${D.AGENT_D} ${D.AGENT_D}`} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
      <circle cx={r * 0.62} cy={-r * 0.62} r={6.5} fill={accent} />
      <text x={r * 0.62} y={-r * 0.62} textAnchor="middle" dominantBaseline="central" fontFamily={UI} fontSize={9} fontWeight={700} fill="#0B1424">
        {n < 10 ? String(n) : "9+"}
      </text>
    </svg>
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
      {halo ? <circle r={r + 1.5 + 3.5 * pulse} fill={color} opacity={(45 + 60 * pulse) / 255} /> : null}
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

/** The user's notebook (app/ui.py _paint_notes_chip): an empty spiral notebook. */
const Notebook: React.FC = () => {
  const r = D.AGENT_D / 2;
  const cover = { left: -5, top: -7.5, w: 12, h: 15 };
  return (
    <svg width={D.AGENT_D} height={D.AGENT_D} viewBox={`${-r} ${-r} ${D.AGENT_D} ${D.AGENT_D}`} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
      <rect x={cover.left} y={cover.top} width={cover.w} height={cover.h} rx={2} fill="#22304A" stroke={INK} strokeWidth={1.4} />
      {[0, 1, 2, 3].map((i) => {
        // Qt drawArc(QRectF(left - 2.2, y - 1.1, 3.4, 2.2), 30°, 300°): a ring round the spine, open towards the cover
        const y = cover.top + 2.5 + i * 3.3;
        return <path key={i} d={arc(1.7, 1.1, 30, 300)} transform={`translate(${cover.left - 0.5} ${y})`} fill="none" stroke={INK} strokeWidth={1.2} />;
      })}
    </svg>
  );
};

/** A small screwdriver (ui.py _screwdriver), tip up before turning by angle degrees, the handle in the working blue. */
const Screwdriver: React.FC<{ angle: number }> = ({ angle }) => (
  <svg width={16} height={16} viewBox="-8 -8 16 16" style={{ position: "absolute", inset: 0, overflow: "visible" }}>
    <g transform={`rotate(${angle})`}>
      <line x1={0} y1={-6.5} x2={0} y2={0} stroke={INK} strokeWidth={1.3} strokeLinecap="round" />
      <line x1={0} y1={-6.6} x2={0} y2={-5.6} stroke={INK} strokeWidth={2.2} />
      <rect x={-2.2} y={-0.5} width={4.4} height={7} rx={1.6} fill={SESSION_COLORS.working} />
      <rect x={-0.4} y={0.8} width={0.8} height={4.6} fill="rgba(0,0,0,.275)" />
    </g>
  </svg>
);

/** Orbit's icon (ui.py _paint_icon, the website's favicon): a planet with a tilted orbit and a moon in the accent
 * colour, centred on (0, 0). scale, spin (degrees clockwise) and moon (radians clockwise from the orbit's right end,
 * behind the planet on the far side; null = where it rests) are the fold animation's. */
export const OrbitIcon: React.FC<{
  r?: number;
  scale?: number;
  spin?: number;
  moon?: number | null;
  hover?: number;
  listening?: boolean;
  level?: number;
  accent?: string;
  opacity?: number;
}> = ({ r: r0 = D.ICON_D / 2, scale = 1, spin = 0, moon = null, hover = 0, listening = false, level = 0, accent = C.accent, opacity = 1 }) => {
  const r = r0 * scale;
  const base = listening ? C.appListen : "#0B1020";
  const bg = hover > 0 && !listening ? mixHex(base, lighter(base, 1.5), hover) : base;
  const s = (2 * r) / 32;
  let mx = 9 * s;
  let my = 2.7 * s;
  let mr = 2 * s;
  let behind = false;
  if (moon !== null) {
    mx = 11.8 * Math.cos(moon) * s;
    my = 4.2 * Math.sin(moon) * s;
    mr = 2 * s * (1 + 0.15 * (Math.sin(moon) - Math.sin(MOON_REST)));
    behind = Math.sin(moon) < 0;
  }
  const moonEl = <circle cx={mx} cy={my} r={mr} fill={accent} stroke={bg} strokeWidth={1.2 * s} />;
  const ring = r + 2 + level * (D.MARGIN - 2);
  return (
    <svg width={2} height={2} viewBox="-1 -1 2 2" style={{ position: "absolute", left: -1, top: -1, overflow: "visible", opacity }}>
      {listening ? <circle r={ring} fill="rgba(229,72,77,.353)" /> : null}
      <circle r={Math.max(0, r - 0.5)} fill={bg} stroke="rgba(255,255,255,.196)" strokeWidth={1} />
      <g transform={`rotate(${-24 + spin})`}>
        <path d={arc(11.8 * s, 4.2 * s, 0, 180)} fill="none" stroke="#EEF2FA" strokeOpacity={0.55} strokeWidth={1.6 * s} />
        {behind ? moonEl : null}
        <circle r={6 * s} fill="#EEF2FA" />
        <path d={arc(11.8 * s, 4.2 * s, 180, 180)} fill="none" stroke={bg} strokeWidth={2.8 * s} />
        <path d={arc(11.8 * s, 4.2 * s, 180, 180)} fill="none" stroke="#EEF2FA" strokeWidth={1.6 * s} strokeLinecap="round" />
        {behind ? null : moonEl}
      </g>
    </svg>
  );
};
/** Where the icon's moon rests on its orbit (foldfx MOON_REST). */
export const MOON_REST = Math.atan2(2.7 / 4.2, 9 / 11.8);

/** Qt's lighter()/darker() approximated in HSV value. */
function shade(hex: string, factor: number) {
  const n = parseInt(hex.slice(1), 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  const f = (v: number) => Math.max(0, Math.min(255, Math.round(v * factor)));
  return `rgb(${f(r)},${f(g)},${f(b)})`;
}
/** Qt's QColor.lighter(f): the value (HSV) times f, the saturation down when it would pass 255. */
function lighter(hex: string, f: number) {
  const n = parseInt(hex.slice(1), 16);
  const c = [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  const max = Math.max(...c);
  const scale = Math.min(255, max * f) / (max || 1);
  return `#${c.map((v) => Math.round(Math.min(255, v * scale)).toString(16).padStart(2, "0")).join("")}`;
}

export const OrbitWidget: React.FC<Props> = ({
  mic = "idle",
  editing = false,
  level = 0,
  phase = 0,
  workPhase = 0,
  accent = C.accent,
  panel = true,
  panelOpacity = 1,
  height,
  header = { rest: "limit 5 h se obnoví v 17:20 (za 2 h 13 min)", refresh: true },
  limits = [],
  limitsOpacity = 1,
  sessions = [],
  feed = null,
  agent = "idle",
  agentLevel = 0,
  notes = 0,
  version = null,
  reading = false,
  wave = 2,
  muted = false,
  theme = "blue",
  pressed = 0,
  foldHover = 0,
  plusHover = 0,
  speakerOpacity = 1,
  micOpacity = 1,
  collapsed = false,
  iconHover = 0,
  shimmer = null,
}) => {
  if (collapsed) {
    return (
      <div style={{ position: "relative", width: SIDE, height: SIDE }}>
        <div style={{ position: "absolute", left: SIDE / 2, top: SIDE / 2 }}>
          <OrbitIcon hover={iconHover} listening={mic === "recording"} level={level} accent={accent} />
        </div>
      </div>
    );
  }
  const natural = panelHeight(limits.length, sessions.length, feed ? feed.rows.length : null);
  const ph = height ?? natural;
  const vh = panel && version ? VER_H : 0;
  const W = panel ? WIDGET_W : SLOT + SIDE;
  const H = panel ? D.STRIP_H + ph + vh + SIDE : SIDE;
  const bx = panel ? W - SIDE : SLOT;
  const by = panel ? D.STRIP_H + ph + vh : 0;
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
  const headW = rowW - measure("Claude", 11, 600) - 16;
  rows.push(
    <div key="head" style={{ position: "absolute", left: x, top: y, width: rowW, height: D.HEADER_H, lineHeight: `${D.HEADER_H}px` }}>
      <span style={{ fontWeight: 600, color: DIM }}>Claude</span>
      {limits.length ? (
        <span style={{ position: "absolute", right: 0, top: 0, maxWidth: headW, display: "flex", alignItems: "center", whiteSpace: "pre" }}>
          {header.refresh ? (
            <span style={{ fontFamily: ICONS, fontSize: 12, color: TEXT, width: 14, textAlign: "center", marginRight: 4 }}>{GLYPH.refresh}</span>
          ) : null}
          {header.warn ? <span style={{ color: C.busy }}>{header.warn}</span> : null}
          <span style={{ color: DIM }}>{header.rest}</span>
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
    const pctW = 34;
    const stateW = 70;
    const gap = 10;
    const folderW = Math.min(110, Math.max(...sessions.map((s) => measure(s.folder))));
    const workAngle = -45 + 24 * Math.sin(workPhase);
    sessions.forEach((s, i) => {
      const color = SESSION_COLORS[s.state];
      const nameW = rowW - 13 - (folderW + gap) - stateW - pctW;
      const tag = s.switching ? `→ ${s.switching}` : s.model ?? "";
      const tagW = tag ? measure(tag) : 0;
      const label = STATE_LABELS[s.state];
      const iconX = rowW - pctW - measure(label) - 19;
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
          <div style={{ position: "absolute", left: -6, top: 6, width: 2.5, height: D.ROW_H - 12, borderRadius: 1.25, background: s.color }} />
          <div style={{ position: "absolute", left: 0.5, top: D.ROW_H / 2 - 3.5, width: 7, height: 7, borderRadius: "50%", background: color }} />
          <div style={{ position: "absolute", left: 13, width: nameW, display: "flex", whiteSpace: "nowrap" }}>
            <span
              style={{
                fontWeight: s.name ? 600 : 400,
                color: s.name ? TEXT : DIM,
                overflow: "hidden",
                textOverflow: "ellipsis",
                maxWidth: nameW - (tag ? tagW + 6 : 0),
              }}
            >
              {s.name || "Nová relace"}
            </span>
            {tag ? <span style={{ marginLeft: 6, color: s.switching ? accent : DIM, flex: "none" }}>{tag}</span> : null}
          </div>
          <span style={{ position: "absolute", left: 13 + nameW + gap, width: folderW, color: s.color, whiteSpace: "nowrap", overflow: "hidden" }}>{s.folder}</span>
          {s.state === "working" ? (
            <div style={{ position: "absolute", left: iconX, top: D.ROW_H / 2 - 8, width: 16, height: 16 }}>
              <Screwdriver angle={workAngle} />
            </div>
          ) : s.state === "done" || s.state === "idle" ? (
            <div style={{ position: "absolute", left: iconX, top: D.ROW_H / 2 - 8, width: 16, height: 16 }}>
              {glyph(11, SESSION_COLORS.done, GLYPH.check)}
            </div>
          ) : null}
          <span
            style={{
              position: "absolute",
              right: pctW,
              width: stateW,
              textAlign: "right",
              color: s.state === "waiting" || s.state === "error" ? color : s.state === "working" ? TEXT : DIM,
            }}
          >
            {label}
          </span>
          {s.context >= 0 ? (
            <span style={{ position: "absolute", right: 0, width: pctW, textAlign: "right", color: s.context >= 0.8 ? C.busy : DIM }}>
              {`${Math.round(s.context * 100)} %`}
            </span>
          ) : null}
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

  // the unfold's wave of light, at its centre given as a CSS position in each piece it lights (only the panel and the
  // version pill: the rest of the picture is small)
  const shimmerBg = (at: string) => {
    if (!shimmer || shimmer.alpha <= 0.001) return undefined;
    const outer = shimmer.rho + shimmer.band;
    const clear = `${shimmer.color}00`;
    const a = Math.round(Math.min(1, shimmer.alpha) * 255).toString(16).padStart(2, "0");
    return `radial-gradient(circle ${outer.toFixed(2)}px at ${at}, ${clear} ${Math.max(0, shimmer.rho - shimmer.band).toFixed(2)}px, ${shimmer.color}${a} ${shimmer.rho.toFixed(2)}px, ${clear} ${outer.toFixed(2)}px)`;
  };

  // the version pill: under the panel, lined up with its right edge
  const verParts: [string, string, boolean][] = [];
  let verButton = "";
  if (version) {
    const name: [string, string, boolean][] = [
      ["Claude Code ", DIM, false],
      [version.installed, TEXT, true],
    ];
    if (version.state === "updating") verParts.push(["Aktualizuju Claude Code na ", DIM, false], [version.latest ?? "", TEXT, true], ["…", DIM, false]);
    else if (version.state === "new") {
      verParts.push(...name, ["  →  ", DIM, false], [version.latest ?? "", C.busy, true]);
      verButton = "Aktualizovat";
    } else if (version.state === "failed") {
      verParts.push(...name, ["  aktualizace se nepovedla", C.busy, false]);
      verButton = "Zkusit znovu";
    } else verParts.push(...name, ["  ✓ nejnovější", "#3DD68C", false]);
  }
  const verTop = D.STRIP_H + ph + D.VER_GAP;

  const iconSize = Math.floor(D.DIAMETER * 0.46);
  const speakerGlyphW = measure(GLYPH.speaker, iconSize, 400, ICONS);

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
            {shimmer ? <div style={{ position: "absolute", inset: 0, background: shimmerBg(`${shimmer.cx - 0.5}px ${shimmer.cy - D.STRIP_H - 0.5}px`) }} /> : null}
          </div>
          {/* the colour dots in their pill */}
          <div
            style={{
              position: "absolute",
              left: chips.dots[0] - D.PILL_H / 2 + 0.5,
              top: chips.y - D.PILL_H / 2 + 0.5,
              width: D.DOT_STEP * 2 + D.PILL_H - 1,
              height: D.PILL_H - 1,
              borderRadius: D.PILL_H / 2,
              background: PANEL_BG,
              boxShadow: `inset 0 0 0 1px ${PANEL_LINE}`,
            }}
          />
          {(["blue", "violet", "teal"] as const).map((t, i) => {
            const cx = chips.dots[i];
            return (
              <React.Fragment key={t}>
                <div style={{ position: "absolute", left: cx - 5, top: chips.y - 5, width: 10, height: 10, borderRadius: "50%", background: [C.accent, C.violet, C.teal][i] }} />
                {t === theme ? (
                  <div style={{ position: "absolute", left: cx - 8.25, top: chips.y - 8.25, width: 15, height: 15, borderRadius: "50%", border: "1.5px solid #E6E8EC" }} />
                ) : null}
              </React.Fragment>
            );
          })}
          <div style={{ position: "absolute", left: chips.agent - D.AGENT_D / 2 - 8, top: chips.y - D.AGENT_D / 2 - 8 }}>
            <AgentChip state={agent} level={agentLevel} phase={phase} accent={accent} />
          </div>
          <Chip cx={chips.notes} cy={chips.y}>
            <Notebook />
            {notes ? <Badge n={notes} accent={accent} /> : null}
          </Chip>
          <Chip cx={chips.dictations} cy={chips.y}>{glyph(14, INK, GLYPHS.dictations)}</Chip>
          <Chip cx={chips.history} cy={chips.y}>{glyph(15, INK, GLYPHS.history)}</Chip>
          <Chip cx={chips.plus} cy={chips.y} bg={plusHover ? mixHex(CHIP_BG, "#2A3245", plusHover) : CHIP_BG}>
            {glyph(13, plusHover ? mixHex(INK, "#FFFFFF", plusHover) : INK, GLYPHS.add)}
          </Chip>
          <Chip cx={chips.phone} cy={chips.y}>{glyph(14, INK, GLYPHS.phone)}</Chip>
          <Chip cx={chips.fold} cy={chips.y} bg={mixHex(CHIP_BG, "#2A3245", foldHover)} line={`rgba(255,255,255,${(0.11 + 0.164 * foldHover).toFixed(3)})`}>
            <div style={{ position: "absolute", left: D.AGENT_D / 2 - 6.5, top: D.AGENT_D / 2 - 0.5, width: 13, height: 2, borderRadius: 1, background: "#E6E8EC" }} />
          </Chip>
          {version ? (
            <div
              style={{
                position: "absolute",
                right: W - D.PANEL_W + 0.5,
                top: verTop + 0.5,
                height: D.VER_PILL_H - 1,
                display: "flex",
                alignItems: "center",
                paddingLeft: 11.5,
                paddingRight: verButton ? 2.5 : 11.5,
                borderRadius: D.VER_PILL_H / 2,
                background: PANEL_BG,
                boxShadow: `inset 0 0 0 1px ${PANEL_LINE}`,
                fontSize: 12,
                whiteSpace: "pre",
                overflow: "hidden",
              }}
            >
              {verParts.map(([t, color, bold], i) => (
                <span key={i} style={{ color, fontWeight: bold ? 600 : 400 }}>
                  {t}
                </span>
              ))}
              {verButton ? (
                <span
                  style={{
                    marginLeft: 8,
                    height: D.VER_PILL_H - 6,
                    lineHeight: `${D.VER_PILL_H - 6}px`,
                    padding: "0 9px",
                    borderRadius: (D.VER_PILL_H - 6) / 2,
                    background: mixHex(accent, lighter(accent, 1.15), version.hover ?? 0),
                    color: C.onAccent,
                    fontSize: 11,
                    fontWeight: 600,
                    transform: `scale(${1 - 0.06 * (version.press ?? 0)})`,
                  }}
                >
                  {verButton}
                </span>
              ) : null}
              {shimmer ? (
                <div style={{ position: "absolute", inset: 0, background: shimmerBg(`right ${D.PANEL_W - 0.5 - shimmer.cx}px top ${shimmer.cy - verTop - 0.5}px`) }} />
              ) : null}
            </div>
          ) : null}
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
          {editing ? glyph(Math.floor(D.DIAMETER * 0.42), micFg, GLYPHS.edit) : glyph(iconSize, micFg, GLYPH.mic)}
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
          {reading
            ? glyph(iconSize, "#FFFFFF", GLYPHS.waves[wave], { justifyContent: "flex-start", paddingLeft: D.DIAMETER / 2 - speakerGlyphW / 2 })
            : glyph(iconSize, muted ? "#8B96AD" : "#FFFFFF", muted ? GLYPH.mute : GLYPH.speaker)}
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

export function mixHex(a: string, b: string, t: number) {
  const pa = parseInt(a.slice(1), 16);
  const pb = parseInt(b.slice(1), 16);
  const ch = (s: number) => Math.round(((pa >> s) & 255) * (1 - t) + ((pb >> s) & 255) * t);
  return `#${[16, 8, 0].map((s) => ch(s).toString(16).padStart(2, "0")).join("")}`;
}

/** Replica of app/ui.py StatusChip: what Orbit is busy with after the key is let go ("Přepisuji…", "Claude kontroluje
 * přepis…"), a pill in the panel's style with an orange moon going round its orbit. Its width; drawn at 1×, its
 * right edge where it is placed (it sits left of the circles). */
export const STATUS_H = 28;
export const statusWidth = (text: string) => Math.min(330, Math.round(10 + 14 + 8 + measure(text, 12, 400, UI_VAR) + 13));

export const StatusChip: React.FC<{ text: string; moon: number }> = ({ text, moon }) => {
  const w = statusWidth(text);
  const c = { x: 10 + 7, y: STATUS_H / 2 };
  return (
    <div
      style={{
        position: "relative",
        width: w,
        height: STATUS_H,
        borderRadius: STATUS_H / 2,
        background: "rgba(24,27,34,.96)",
        boxShadow: "inset 0 0 0 1px rgba(255,255,255,.11), 0 1px 3px rgba(0,0,0,.25), 0 2px 6px rgba(0,0,0,.18)",
        fontFamily: UI_VAR,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: c.x - 6.7,
          top: c.y - 6.7,
          width: 13.4,
          height: 13.4,
          borderRadius: "50%",
          boxShadow: "inset 0 0 0 1.4px rgba(255,255,255,.216)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: c.x + 6 * Math.cos(moon) - 2.6,
          top: c.y + 6 * Math.sin(moon) - 2.6,
          width: 5.2,
          height: 5.2,
          borderRadius: "50%",
          background: "#F5A524",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: c.x + 15,
          top: 0,
          height: STATUS_H,
          lineHeight: `${STATUS_H}px`,
          fontSize: 12,
          color: TEXT,
          whiteSpace: "nowrap",
          opacity: GREY_AA,
        }}
      >
        {text}
      </div>
    </div>
  );
};
