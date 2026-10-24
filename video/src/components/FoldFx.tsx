import React, { useMemo } from "react";
import { C } from "../lib/theme";
import { MOON_REST, OrbitIcon, Shimmer, mixHex } from "./OrbitWidget";

// The app's fold and unfold animation (app/foldfx.py), frame by frame with the same curves and constants.
// Folding (800 ms), the panel breathes in and swirls into the planet like into a black hole, its stars spiral in
// after it, and the icon pops out with its moon whipping round and a shock wave. Unfolding (740 ms), the icon charges
// up with the moon speeding round, bursts, and the panel unwinds out of it while its stars fly to their places and a
// wave of light runs across it. Everything is in the widget's logical pixels, scaled with it.

export const FOLD_S = 0.8;
export const UNFOLD_S = 0.74;
const PAD = 64;
const STARS = 56;
const PANEL_END = 0.68;

const clamp = (t: number) => (t < 0 ? 0 : t > 1 ? 1 : t);
const smooth = (a: number, b: number, t: number) => {
  const x = clamp((t - a) / (b - a));
  return x * x * (3 - 2 * x);
};
const outCubic = (t: number) => 1 - (1 - t) ** 3;
const inBack = (t: number, k: number) => (k + 1) * t ** 3 - k * t * t;
const outBack = (t: number, k: number) => {
  const x = t - 1;
  return 1 + (k + 1) * x ** 3 + k * x * x;
};
/** Folding: the panel's size and turn (degrees, clockwise) at a, its part of the animation. */
const foldPose = (a: number): [number, number] => {
  const x = clamp(a);
  return [Math.max(0.015, 1 - 0.985 * inBack(x, 1.0)), 80 * x ** 3];
};
/** Unfolding: out of the planet, a little past its size and back, unwinding. */
const unfoldPose = (g: number): [number, number] => {
  const x = clamp(g);
  return [0.03 + 0.97 * outBack(x, 1.25), -40 * (1 - outCubic(x))];
};

export type Shape = { kind: "rect"; x: number; y: number; w: number; h: number } | { kind: "circle"; x: number; y: number; r: number };

type Star = { r: number; th: number; start: number; length: number; spin: number; size: number; color: string };

const mulberry = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let t = seed;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

const inside = (s: Shape, x: number, y: number) =>
  s.kind === "rect" ? x >= s.x && x <= s.x + s.w && y >= s.y && y <= s.y + s.h : Math.hypot(x - s.x, y - s.y) <= s.r;

/** Stars on the picture's opaque parts (the panel, its chips, the circles), not on the mic itself. */
const placeStars = (w: number, h: number, c: { x: number; y: number }, iconR: number, shapes: Shape[], folding: boolean, seed: number, accent: string) => {
  const rnd = mulberry(seed);
  const uni = (a: number, b: number) => a + (b - a) * rnd();
  const stars: Star[] = [];
  for (let i = 0; i < STARS * 25 && stars.length < STARS; i++) {
    const x = uni(0, w);
    const y = uni(0, h);
    if (!shapes.some((s) => inside(s, x, y))) continue;
    const dx = x - c.x;
    const dy = y - c.y;
    if (Math.hypot(dx, dy) < iconR + 8) continue;
    const [start, length] = folding ? [uni(0.04, 0.46), uni(0.28, 0.42)] : [uni(0.28, 0.42), uni(0.34, 0.5)];
    const pick = rnd();
    const color = pick < 0.18 ? "#ffffff" : pick < 0.45 ? mixHex(accent, "#ffffff", 0.5) : accent;
    stars.push({ r: Math.hypot(dx, dy), th: Math.atan2(dy, dx), start, length, spin: uni(0.45, 0.95), size: uni(1.6, 3.0), color });
  }
  return stars;
};

type Props = {
  /** 0..1 of the animation. */
  u: number;
  folding: boolean;
  /** The picture's size (the unfolded widget) and the icon's centre in it (the mic's). */
  w: number;
  h: number;
  c: { x: number; y: number };
  iconR?: number;
  /** The unfolded widget, with the unfold's wave of light on it (null: none). */
  picture: (shimmer: Shimmer | null) => React.ReactNode;
  shapes: Shape[];
  accent?: string;
  seed?: number;
};

export const FoldFx: React.FC<Props> = ({ u, folding, w, h, c, iconR = 22, picture, shapes, accent = C.accent, seed = 7 }) => {
  const { x: cx, y: cy } = c;
  const stars = useMemo(() => placeStars(w, h, { x: cx, y: cy }, iconR, shapes, folding, seed, accent), [w, h, cx, cy, iconR, shapes, folding, seed, accent]);
  const far = Math.max(...[0, w].flatMap((x) => [0, h].map((y) => Math.hypot(x - c.x, y - c.y))));
  const ring = mixHex(accent, "#ffffff", 0.35);

  const layers: React.ReactNode[] = [];
  const layer = (key: string, [scale, turn]: [number, number], opacity: number, shimmer: Shimmer | null = null) => {
    if (opacity <= 0.004 || scale <= 0.01) return;
    layers.push(
      <div
        key={key}
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          width: w,
          height: h,
          transformOrigin: `${c.x}px ${c.y}px`,
          transform: scale !== 1 || turn ? `rotate(${turn.toFixed(3)}deg) scale(${scale.toFixed(4)})` : undefined,
          opacity,
        }}
      >
        {picture(shimmer)}
      </div>,
    );
  };

  let glow = { strength: 0, radius: 0 };
  let icon: { opacity: number; scale: number; spin: number; moon: number | null } | null = null;
  const rings: { r: number; width: number; alpha: number }[] = [];

  if (folding) {
    const a = u / PANEL_END;
    if (a < 1) {
      const fade = 1 - smooth(0.62, 1.0, a);
      if (a > 0.4)
        ([
          [0.045, 0.12],
          [0.03, 0.2],
          [0.015, 0.32],
        ] as const).forEach(([lag, share], i) => layer(`g${i}`, foldPose(a - lag), fade * share));
      layer("main", foldPose(a), fade);
    }
    glow = { strength: smooth(0.3, 0.62, u) * (1 - smooth(0.64, 0.96, u)), radius: iconR * (0.8 + 1.2 * smooth(0.3, 0.7, u)) };
    const b = u < 1 ? clamp((u - 0.55) / 0.45) : 1;
    if (b >= 1) icon = { opacity: 1, scale: 1, spin: 0, moon: null };
    else if (b > 0) {
      const turn = outCubic(b);
      icon = { opacity: Math.min(1, b * 5), scale: outBack(b, 2.6), spin: -150 * (1 - turn), moon: MOON_REST - 4 * Math.PI * (1 - turn) };
    }
    ([
      [0.62, 34, 3.2],
      [0.72, 20, 1.6],
    ] as const).forEach(([start, grow, width]) => {
      const t = clamp((u - start) / (1 - start));
      if (t > 0 && t < 1) rings.push({ r: iconR + grow * outCubic(t), width: width * (1 - t) + 0.6, alpha: 0.9 * (1 - t) ** 1.6 });
    });
  } else {
    const grow = u < 1 ? clamp((u - 0.3) / 0.66) : 1;
    const s = clamp((u - 0.5) / 0.5);
    let shimmer: Shimmer | null = null;
    if (s > 0 && s < 1) {
      const band = 54;
      const rho = band * 0.5 + (far + band) * outCubic(s);
      shimmer = { cx: c.x, cy: c.y, rho, band, alpha: 0.3 * Math.sin(Math.PI * s) ** 0.6, color: mixHex(accent, "#ffffff", 0.6) };
    }
    if (grow >= 1) layer("main", [1, 0], 1, shimmer);
    else if (grow > 0) {
      const alpha = smooth(0, 0.28, grow);
      if (grow < 0.5)
        ([
          [0.06, 0.1],
          [0.04, 0.18],
          [0.02, 0.3],
        ] as const).forEach(([lag, share], i) => {
          if (grow > lag) layer(`g${i}`, unfoldPose(grow - lag), alpha * share);
        });
      const pose = unfoldPose(grow);
      // the wave is drawn over the window, not the scaled picture: its radius in the picture's own pixels
      layer("main", pose, alpha, shimmer ? { ...shimmer, rho: shimmer.rho / pose[0], band: shimmer.band / pose[0] } : null);
    }
    glow = { strength: smooth(0.04, 0.3, u) * (1 - smooth(0.32, 0.62, u)), radius: iconR * (1.0 + 1.6 * smooth(0.1, 0.4, u)) };
    const hh = clamp(u / 0.34);
    if (hh < 1) {
      const scale = hh < 0.62 ? 1 + 0.16 * outCubic(hh / 0.62) : 1.16 * (1 - inBack((hh - 0.62) / 0.38, 1.2));
      icon = { opacity: 1, scale, spin: 110 * hh ** 3, moon: hh === 0 ? null : MOON_REST + 3 * Math.PI * hh * hh };
    }
    ([
      [0.3, 70, 3.4],
      [0.37, 46, 1.8],
    ] as const).forEach(([start, grow2, width]) => {
      const t = clamp((u - start) / 0.5);
      if (t > 0 && t < 1) rings.push({ r: iconR * 0.8 + grow2 * outCubic(t), width: width * (1 - t) + 0.5, alpha: 0.9 * (1 - t) ** 1.5 });
    });
  }

  const box = { left: -PAD, top: -PAD, width: w + 2 * PAD, height: h + 2 * PAD };
  const svg = (key: string, children: React.ReactNode) => (
    <svg key={key} width={box.width} height={box.height} viewBox={`${-PAD} ${-PAD} ${box.width} ${box.height}`} style={{ position: "absolute", ...box, overflow: "visible" }}>
      {children}
    </svg>
  );

  const glowEl =
    glow.strength > 0.01
      ? svg(
          "glow",
          <>
            <defs>
              <radialGradient id="fxglow" cx={c.x} cy={c.y} r={glow.radius} gradientUnits="userSpaceOnUse">
                <stop offset="0" stopColor="#ffffff" stopOpacity={Math.min(1, 0.95 * glow.strength)} />
                <stop offset="0.22" stopColor={accent} stopOpacity={0.55 * glow.strength} />
                <stop offset="1" stopColor={accent} stopOpacity={0} />
              </radialGradient>
            </defs>
            <circle cx={c.x} cy={c.y} r={glow.radius} fill="url(#fxglow)" />
          </>,
        )
      : null;

  const starEls: React.ReactNode[] = [];
  const defs: React.ReactNode[] = [];
  stars.forEach((s, i) => {
    const q = (u - s.start) / s.length;
    if (!(q > 0 && q < 1)) return;
    let alpha: number;
    let size = s.size;
    let at: (q: number) => { x: number; y: number };
    if (folding) {
      alpha = Math.min(1, q / 0.12) * (1 - smooth(0.82, 1.0, q));
      size = s.size * (1 - 0.45 * q);
      const [scale, turn] = foldPose(s.start / PANEL_END);
      at = (k) => {
        const e = k ** 2.2;
        const r = s.r * scale * (1 - e);
        const th = s.th + (turn * Math.PI) / 180 + (s.spin * e) / (1 - 0.7 * e);
        return { x: c.x + r * Math.cos(th), y: c.y + r * Math.sin(th) };
      };
    } else {
      alpha = Math.min(1, q / 0.08) * (1 - smooth(0.65, 1.0, q));
      at = (k) => {
        const e = 1 - (1 - k) ** 2.6;
        const th = s.th - (s.spin * (1 - e)) / (1 - 0.7 * (1 - e));
        return { x: c.x + s.r * e * Math.cos(th), y: c.y + s.r * e * Math.sin(th) };
      };
    }
    if (alpha <= 0.01) return;
    const head = at(q);
    const tail = at(Math.max(0, q - 0.08));
    const id = `fxs${i}`;
    defs.push(
      <linearGradient key={id} id={id} gradientUnits="userSpaceOnUse" x1={tail.x} y1={tail.y} x2={head.x} y2={head.y}>
        <stop offset="0" stopColor={s.color} stopOpacity={0} />
        <stop offset="1" stopColor={s.color} stopOpacity={alpha * 0.7} />
      </linearGradient>,
    );
    starEls.push(
      <g key={i}>
        <line x1={tail.x} y1={tail.y} x2={head.x} y2={head.y} stroke={`url(#${id})`} strokeWidth={size} strokeLinecap="round" />
        <circle cx={head.x} cy={head.y} r={size * 0.8} fill={s.color} opacity={alpha} />
      </g>,
    );
  });
  const starsEl = starEls.length
    ? svg(
        "stars",
        <>
          <defs>{defs}</defs>
          {starEls}
        </>,
      )
    : null;

  const iconEl =
    icon && icon.opacity > 0.01 && icon.scale > 0.02 ? (
      <div key="icon" style={{ position: "absolute", left: c.x, top: c.y }}>
        <OrbitIcon r={iconR} scale={icon.scale} spin={icon.spin} moon={icon.moon} accent={accent} opacity={icon.opacity} />
      </div>
    ) : null;

  const ringsEl = rings.length
    ? svg(
        "rings",
        rings.map((r, i) => <circle key={i} cx={c.x} cy={c.y} r={r.r} fill="none" stroke={ring} strokeOpacity={r.alpha} strokeWidth={r.width} />),
      )
    : null;

  return (
    <div style={{ position: "relative", width: w, height: h }}>
      {layers}
      {folding ? [glowEl, starsEl, iconEl, ringsEl] : [glowEl, iconEl, ringsEl, starsEl]}
    </div>
  );
};
