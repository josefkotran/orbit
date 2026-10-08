import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Orbits } from "../components/Orbits";
import { KIN, Kinetic } from "../components/Kinetic";
import { EASE_IN_OUT, pop, prog, rise } from "../lib/anim";
import { C, GLYPH, ICONS, TEXT } from "../lib/theme";
import { bar, CUT, DURATION } from "../lib/time";
import { MicBadge } from "./Intro";

const CX = 960;
const CY = 405;
const TILT = -14;
/** The mic in the middle of the orrery; Claude's widget hands its mic over here at frame `at`. */
export const OUTRO_MIC = { x: CX, y: CY, d: 130, at: CUT + 30 };

const FEATURES = [
  { ring: 0, phase: 0.2, label: "Diktování česky", color: C.text },
  { ring: 0, phase: Math.PI + 0.2, label: "Limity Clauda", color: C.accent },
  { ring: 1, phase: 1.9, label: "Na tvé grafice", color: C.text },
  { ring: 1, phase: 1.9 + Math.PI, label: "Relace Claude Code", color: C.accent },
  { ring: 2, phase: 3.6, label: "Hlasový agent", color: C.accent },
  { ring: 2, phase: 3.6 + Math.PI, label: "Předčítání", color: C.text },
  // upper left at first, then over the top: clear of the other labels, the mic and the headline the whole outro
  { ring: 0, phase: 3.9, label: "Poznámky a úkoly", color: C.accent },
];

/** Drums stop, the pad rings out: the orrery again, every feature on its orbit, and the download. */
export const Outro: React.FC = () => {
  const f = useCurrentFrame();
  if (f < CUT - 2) return null;
  const rings = [820, 590, 350].map((rx, i) => ({
    rx,
    ry: rx * 0.3,
    draw: prog(f, CUT + 16 + i * 8, CUT + 84 + i * 8, EASE_IN_OUT),
    ticks: i === 0,
  }));
  const t = (f - CUT) / 30;
  const speeds = [0.07, 0.11, 0.16];
  const rad = (TILT * Math.PI) / 180;
  const sats = FEATURES.map((s, i) => {
    const ring = rings[s.ring];
    const angle = s.phase + t * speeds[s.ring];
    const x = ring.rx * Math.cos(angle);
    const y = ring.ry * Math.sin(angle);
    const sx = CX + x * Math.cos(rad) - y * Math.sin(rad);
    const sy = CY + x * Math.sin(rad) + y * Math.cos(rad);
    const front = Math.min(1, Math.max(0, (CY + 70 - sy) / 90)); // labels only on the upper arc, clear of the text
    const dist = Math.hypot(sx - CX, sy - CY);
    const clear = Math.min(1, Math.max(0, (dist - 150) / 90)); // and not across the mic
    const appear = prog(f, CUT + 40 + i * 6, CUT + 70 + i * 6);
    return {
      ring: s.ring,
      angle,
      r: 6 * appear * Math.min(1, Math.max(0, (dist - 70) / 20)),
      color: s.color,
      glow: s.color === C.accent,
      label: s.label,
      labelOpacity: appear * front * clear,
    };
  });

  const glowIn = prog(f, OUTRO_MIC.at, OUTRO_MIC.at + 30);
  const fadeAll = prog(f, DURATION - 34, DURATION - 2, EASE_IN_OUT);
  const btn = pop(f, bar(33) + 22, 13);
  const breathe = 0.75 + 0.25 * Math.sin(f * 0.07);

  return (
    <AbsoluteFill style={{ opacity: 1 - fadeAll }}>
      <Orbits cx={CX} cy={CY} tilt={TILT} width={1920} height={1080} rings={rings} satellites={sats} />
      {f >= OUTRO_MIC.at ? (
        <div style={{ position: "absolute", left: CX - OUTRO_MIC.d / 2, top: CY - OUTRO_MIC.d / 2 }}>
          <MicBadge d={OUTRO_MIC.d} glow={breathe * glowIn} />
        </div>
      ) : null}
      <div
        style={{
          position: "absolute",
          left: 960 - 900,
          top: 600,
          width: 1800,
          height: 420,
          background: "radial-gradient(closest-side, rgba(4,6,12,.85), rgba(4,6,12,0))",
          opacity: prog(f, bar(33) - 10, bar(33) + 20),
        }}
      />

      <div style={{ position: "absolute", left: 0, right: 0, top: 650, display: "flex", flexDirection: "column", alignItems: "center" }}>
        <Kinetic lines={["Stáhni si Orbit."]} at={bar(33)} stagger={2} cfg={KIN.hero} size={132} align="center" />
        <div style={{ display: "flex", alignItems: "center", gap: 40, marginTop: 40 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 16,
              height: 78,
              padding: "0 44px",
              borderRadius: 39,
              background: C.accent,
              color: C.onAccent,
              fontFamily: TEXT,
              fontWeight: 650,
              fontSize: 32,
              letterSpacing: ".01em",
              boxShadow: "0 0 0 1px rgba(255,255,255,.12), 0 16px 50px rgba(91,157,255,.35)",
              transform: `scale(${btn})`,
              opacity: Math.min(1, btn * 1.4),
            }}
          >
            <span style={{ fontFamily: ICONS, fontSize: 26 }}>{GLYPH.download}</span>
            Stáhnout pro Windows
          </div>
          <div style={{ fontFamily: TEXT, fontWeight: 500, fontSize: 36, color: C.soft, letterSpacing: ".02em", ...rise(f, bar(34), 22, 14) }}>
            orbit.easya.cz
          </div>
        </div>
      </div>
    </AbsoluteFill>
  );
};
