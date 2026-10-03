import React, { useMemo } from "react";
import { AbsoluteFill, useCurrentFrame, useVideoConfig } from "remotion";
import { rnd } from "../lib/anim";
import { C } from "../lib/theme";

type Props = {
  /** 0 = still stars, 1 = full warp (stars streak out of the centre). */
  warp?: number;
  /** How far the warp has travelled (accumulated, so stars keep moving). */
  travel?: number;
  /** Brightness pulse 0..1 (on the beat after the drop). */
  pulse?: number;
  /** Shift of the nebula glow, for a slow camera feel. */
  drift?: number;
};

const COUNT = 520;

/** Deep space like the website: tiny stars (some in the accent), streaks in hyperspace, a nebula in the theme
 * colour top right with faint violet and teal ones (site.css body::before). */
export const Space: React.FC<Props> = ({ warp = 0, travel = 0, pulse = 0, drift = 0 }) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const cx = width / 2;
  const cy = height / 2;
  const stars = useMemo(
    () =>
      Array.from({ length: COUNT }, (_, i) => {
        const big = rnd(i, 3) > 0.94;
        return {
          x: rnd(i, 1) * width,
          y: rnd(i, 2) * height,
          r: big ? 1.1 + rnd(i, 4) * 0.9 : 0.45 + rnd(i, 4) * 0.7,
          warm: rnd(i, 5) > 0.8,
          blue: rnd(i, 9) > 0.86,
          base: 0.25 + rnd(i, 6) * 0.6,
          tw: rnd(i, 7) * Math.PI * 2,
          depth: 0.3 + rnd(i, 8) * 1.4,
        };
      }),
    [width, height],
  );

  return (
    <AbsoluteFill style={{ background: C.space }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(40% 35% at ${78 - drift * 4}% ${8 + drift * 3}%, rgba(91,157,255,.20), rgba(4,6,12,0) 70%),
            radial-gradient(35% 40% at ${6 + drift * 3}% 42%, rgba(167,139,250,.09), rgba(4,6,12,0) 70%),
            radial-gradient(40% 30% at 64% ${96 - drift * 3}%, rgba(45,212,191,.07), rgba(4,6,12,0) 70%)`,
        }}
      />
      <svg width={width} height={height} style={{ position: "absolute", inset: 0 }}>
        {stars.map((s, i) => {
          const twinkle = 0.82 + 0.18 * Math.sin(frame * 0.05 + s.tw);
          const o = Math.min(1, s.base * twinkle * (1 + pulse * 0.6));
          const color = s.blue ? "#5B9DFF" : s.warm ? "#FFF1DE" : "#E4ECFF";
          if (warp <= 0.001 && Math.abs(travel) <= 0.001) {
            return <circle key={i} cx={s.x} cy={s.y} r={s.r} fill={color} opacity={o} />;
          }
          // fly through: push each star out from the centre, nearer ones faster; streak length grows with warp
          const dx = s.x - cx;
          const dy = s.y - cy;
          const k = 1 + travel * s.depth;
          const len = warp * 0.22 * s.depth;
          const hx = cx + dx * k;
          const hy = cy + dy * k;
          const tx = cx + dx * k * (1 - len);
          const ty = cy + dy * k * (1 - len);
          return (
            <line
              key={i}
              x1={tx}
              y1={ty}
              x2={hx}
              y2={hy}
              stroke={color}
              strokeWidth={s.r * 1.6}
              strokeLinecap="round"
              opacity={Math.min(1, o * (1 + warp))}
            />
          );
        })}
      </svg>
      <AbsoluteFill
        style={{
          background: "radial-gradient(ellipse at center, rgba(4,6,12,0) 55%, rgba(2,3,7,.75) 100%)",
        }}
      />
    </AbsoluteFill>
  );
};
