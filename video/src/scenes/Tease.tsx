import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { KIN, Kinetic } from "../components/Kinetic";
import { EASE_IN, EXPO_OUT, prog } from "../lib/anim";
import { bar, DROP } from "../lib/time";

export const TEASE_START = bar(14);

/** "A když pracuješ s Claude Code…" while the stars start to streak; it rushes past the camera on the drop. */
export const Tease: React.FC = () => {
  const f = useCurrentFrame();
  if (f < TEASE_START - 2 || f > DROP + 2) return null;
  const rush = prog(f, DROP - 22, DROP, EASE_IN);
  return (
    <AbsoluteFill
      style={{
        alignItems: "center",
        justifyContent: "center",
        opacity: 1 - rush,
        transform: `scale(${1 + rush * 0.5})`,
        filter: rush > 0 ? `blur(${rush * 10}px)` : undefined,
      }}
    >
      <div style={{ textAlign: "center", marginTop: -40 }}>
        <Kinetic lines={["A když pracuješ"]} at={TEASE_START} stagger={2} cfg={KIN.hero} size={118} align="center" />
        <Kinetic lines={["s Claude Code…"]} at={bar(15)} stagger={2} cfg={KIN.hero} size={118} align="center" style={{ marginTop: 6 }} />
      </div>
    </AbsoluteFill>
  );
};

/** Warp amount (0..1) and accumulated travel for the starfield: the video arrives out of hyperspace (like the
 * website on load) and jumps into it again right before the drop. */
export const warpAt = (f: number) => {
  if (f < 70) {
    const t = prog(f, 0, 64, EXPO_OUT);
    return { warp: 1 - t, travel: -0.32 * (1 - t) };
  }
  const w = (k: number) => prog(k, TEASE_START + 20, DROP, EASE_IN);
  if (f >= DROP) return { warp: 0, travel: 0 };
  let travel = 0;
  for (let k = TEASE_START + 20; k <= f; k++) travel += 0.05 * w(k) ** 2;
  return { warp: w(f), travel };
};
