import React from "react";
import { C } from "../lib/theme";

export type Ring = {
  rx: number;
  ry: number;
  /** 0..1 how much of the ellipse is drawn. */
  draw: number;
  /** Tick marks along the outer side, like a dial (the website's outer orbit). */
  ticks?: boolean;
  opacity?: number;
};

export type Satellite = {
  ring: number; // index into rings
  angle: number; // radians along the ellipse
  r: number;
  color: string;
  glow?: boolean;
  label?: string;
  labelOpacity?: number;
};

type Props = {
  cx: number;
  cy: number;
  tilt?: number; // degrees
  rings: Ring[];
  satellites?: Satellite[];
  /** Satellites behind the planet are dimmed when they pass behind this radius around the centre. */
  width: number;
  height: number;
  style?: React.CSSProperties;
};

const perimeter = (a: number, b: number) => Math.PI * (3 * (a + b) - Math.sqrt((3 * a + b) * (a + 3 * b)));

// Arc length along the ellipse is not proportional to its angle (ry is 0.3 rx), so the comet at the drawing front
// and the tick marks use the real arc length, like the stroke dash does.
const N = 720;
const tables = new Map<string, Float64Array>();
const table = (r: { rx: number; ry: number }) => {
  const key = `${r.rx}:${r.ry}`;
  let t = tables.get(key);
  if (!t) {
    t = new Float64Array(N + 1);
    for (let i = 1; i <= N; i++) {
      const a0 = ((i - 1) / N) * Math.PI * 2;
      const a1 = (i / N) * Math.PI * 2;
      t[i] = t[i - 1] + Math.hypot(r.rx * (Math.cos(a1) - Math.cos(a0)), r.ry * (Math.sin(a1) - Math.sin(a0)));
    }
    tables.set(key, t);
  }
  return t;
};
const fractionAt = (r: { rx: number; ry: number }, angle: number) => {
  const t = table(r);
  const i = Math.min(N, Math.max(0, Math.round((angle / (Math.PI * 2)) * N)));
  return t[i] / t[N];
};
const angleAt = (r: { rx: number; ry: number }, fraction: number) => {
  const t = table(r);
  const target = fraction * t[N];
  let lo = 0;
  let hi = N;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (t[mid] < target) lo = mid;
    else hi = mid;
  }
  const seg = t[hi] - t[lo] || 1;
  return ((lo + (target - t[lo]) / seg) / N) * Math.PI * 2;
};

/** Thin orbits in the accent with satellites, like the website's orrery. */
export const Orbits: React.FC<Props> = ({ cx, cy, tilt = -16, rings, satellites = [], width, height, style }) => {
  const rad = (tilt * Math.PI) / 180;
  const pos = (ring: Ring, angle: number) => {
    const x = ring.rx * Math.cos(angle);
    const y = ring.ry * Math.sin(angle);
    return { x: cx + x * Math.cos(rad) - y * Math.sin(rad), y: cy + x * Math.sin(rad) + y * Math.cos(rad) };
  };
  return (
    <svg width={width} height={height} style={{ position: "absolute", inset: 0, overflow: "visible", ...style }}>
      <defs>
        <radialGradient id="satglow">
          <stop offset="0" stopColor="#fff" stopOpacity=".55" />
          <stop offset="1" stopColor="#fff" stopOpacity="0" />
        </radialGradient>
      </defs>
      {rings.map((ring, i) => {
        const p = perimeter(ring.rx, ring.ry);
        const ticks = ring.ticks ? 180 : 0;
        return (
          <g key={i} opacity={ring.opacity ?? 1}>
            <ellipse
              cx={cx}
              cy={cy}
              rx={ring.rx}
              ry={ring.ry}
              transform={`rotate(${tilt} ${cx} ${cy})`}
              fill="none"
              stroke={C.accent}
              strokeOpacity={0.36}
              strokeWidth={1.4}
              strokeDasharray={`${p * ring.draw} ${p}`}
              strokeDashoffset={0}
            />
            {ring.draw > 0.001 && ring.draw < 0.999
              ? (() => {
                  const h = pos(ring, angleAt(ring, ring.draw));
                  return (
                    <g>
                      <circle cx={h.x} cy={h.y} r={16} fill={C.accent} opacity={0.16} />
                      <circle cx={h.x} cy={h.y} r={3.4} fill="#FFFFFF" />
                    </g>
                  );
                })()
              : null}
            {Array.from({ length: ticks }, (_, k) => {
              const a = (k / ticks) * Math.PI * 2;
              if (fractionAt(ring, a) > ring.draw) return null;
              const inner = pos(ring, a);
              const outer = pos({ ...ring, rx: ring.rx + 9, ry: ring.ry + 9 * (ring.ry / ring.rx) + 3 }, a);
              const long = k % 15 === 0;
              return (
                <line
                  key={k}
                  x1={inner.x}
                  y1={inner.y}
                  x2={inner.x + (outer.x - inner.x) * (long ? 1.7 : 1)}
                  y2={inner.y + (outer.y - inner.y) * (long ? 1.7 : 1)}
                  stroke="#FFFFFF"
                  strokeOpacity={long ? 0.26 : 0.12}
                  strokeWidth={1}
                />
              );
            })}
          </g>
        );
      })}
      {satellites.map((s, i) => {
        const p = pos(rings[s.ring], s.angle);
        return (
          <g key={i}>
            {s.glow ? <circle cx={p.x} cy={p.y} r={s.r * 4} fill={s.color} opacity={0.18} /> : null}
            <circle cx={p.x} cy={p.y} r={s.r} fill={s.color} />
            {s.label ? (
              <text
                x={p.x}
                y={p.y + s.r + 30}
                textAnchor="middle"
                fill={C.soft}
                opacity={s.labelOpacity ?? 1}
                style={{ font: `500 26px "Mona Sans"`, letterSpacing: ".01em" }}
              >
                {s.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
};
