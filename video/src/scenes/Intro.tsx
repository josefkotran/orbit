import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { LogoMark } from "../components/Logo";
import { Orbits } from "../components/Orbits";
import { KIN, Kinetic } from "../components/Kinetic";
import { Words, sub } from "../components/Text";
import { EASE_IN_OUT, EXPO_OUT, lerp, pop, prog } from "../lib/anim";
import { C, GLYPH, ICONS } from "../lib/theme";
import { bar } from "../lib/time";

export const INTRO_END = 206;
const CX = 960;
const CY = 430;
// where the mic lands in the dictation scene (its centre) and its size there
export const DICT_MIC = { x: 1150, y: 790, d: 104 };

/** Big Orbit mic, as in the app (idle: dark circle, white Fluent mic glyph). */
export const MicBadge: React.FC<{ d: number; glow?: number }> = ({ d, glow = 0 }) => (
  <div style={{ position: "relative", width: d, height: d }}>
    {glow > 0 ? (
      <div
        style={{
          position: "absolute",
          left: -d * 1.1,
          top: -d * 1.1,
          width: d * 3.2,
          height: d * 3.2,
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(91,157,255,.34) 0%, rgba(91,157,255,.09) 35%, rgba(91,157,255,0) 65%)",
          opacity: glow,
        }}
      />
    ) : null}
    <div
      style={{
        position: "absolute",
        inset: 0,
        borderRadius: "50%",
        background: "#2F3542",
        boxShadow: `inset 0 0 0 ${d / 40}px rgba(0,0,0,.235), 0 0 0 1px rgba(255,255,255,.06)`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: ICONS,
        fontSize: Math.floor(d * 0.46),
        color: "#fff",
      }}
    >
      {GLYPH.mic}
    </div>
  </div>
);

export const Intro: React.FC = () => {
  const f = useCurrentFrame();
  if (f > INTRO_END) return null;
  const exit = prog(f, 166, INTRO_END, EASE_IN_OUT);
  const rings = [860, 600, 360].map((rx, i) => ({
    rx,
    ry: rx * 0.3,
    draw: prog(f, 2 + i * 10, 70 + i * 10, EASE_IN_OUT),
    ticks: i === 0,
  }));
  const satIn = prog(f, 30, 70);
  const t = f / 30;
  const satellites = [
    { ring: 1, angle: 2.35 + t * 0.16, r: 7, color: C.accent, glow: true },
    { ring: 2, angle: 5.6 + t * 0.24, r: 5, color: C.text },
    { ring: 0, angle: 3.9 + t * 0.09, r: 5, color: C.text },
  ];

  // the mic: pops in at the centre, then flies to its place in the dictation scene
  const micIn = pop(f, 12, 14);
  const fly = prog(f, 170, INTRO_END, EASE_IN_OUT);
  const d = lerp(fly, [0, 1], [140, DICT_MIC.d]);
  const mx = lerp(fly, [0, 1], [CX, DICT_MIC.x]);
  const my = lerp(fly, [0, 1], [CY, DICT_MIC.y]);
  const breathe = 0.75 + 0.25 * Math.sin(f * 0.07);

  return (
    <AbsoluteFill>
      <div
        style={{
          position: "absolute",
          inset: 0,
          opacity: 1 - exit,
          transform: `scale(${1 + exit * 0.35 + f * 0.0004})`,
          transformOrigin: `${CX}px ${CY}px`,
        }}
      >
        <Orbits
          cx={CX}
          cy={CY}
          tilt={-14}
          width={1920}
          height={1080}
          rings={rings}
          satellites={satellites.map((s) => ({ ...s, r: s.r * satIn }))}
        />
      </div>

      <div
        style={{
          position: "absolute",
          left: mx - d / 2,
          top: my - d / 2,
          transform: `scale(${Math.max(0.001, micIn)})`,
          opacity: f < INTRO_END ? Math.min(1, micIn * 1.4) : 0,
        }}
      >
        <MicBadge d={d} glow={(1 - fly) * breathe} />
      </div>

      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 600,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          opacity: 1 - prog(f, 156, 178, EASE_IN_OUT),
          transform: `translateY(${-prog(f, 156, 186, EXPO_OUT) * 20}px)`,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 30 }}>
          <div style={{ opacity: prog(f, bar(1) - 6, bar(1) + 20), transform: `rotate(${(1 - prog(f, bar(1) - 6, bar(1) + 40)) * -40}deg)` }}>
            <LogoMark size={112} moonAngle={0.55 + (1 - prog(f, bar(1) - 6, bar(1) + 50)) * 2.4} />
          </div>
          <Kinetic lines={["Orbit"]} at={bar(1)} stagger={3} dur={36} cfg={KIN.mark} size={150} />
        </div>
        <Words text="Diktování česky pro Windows" at={bar(1) + 26} stagger={4} style={{ ...sub(40), marginTop: 22 }} />
      </div>
    </AbsoluteFill>
  );
};
