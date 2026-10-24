import React from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { KIN, Kinetic } from "../components/Kinetic";
import { sub } from "../components/Text";
import { EASE_IN_OUT, prog, rise } from "../lib/anim";
import { C, GLYPH, ICONS, UI_VAR } from "../lib/theme";
import { bar } from "../lib/time";

export const PRIV_START = bar(14);
export const PRIV_END = bar(18) + 10;

// the real settings window (video/capture/grab.py, 820 x 1384 logical px rendered at 3x), its upper part
const SHOT_W = 640;
const K = SHOT_W / 820;
const TITLE = 40;
const SHOWN_H = 1050; // logical px of it in the window, the rest fades out at the bottom

// where grab.py says these are (logical px in the dialog)
const marks = [
  { at: bar(14), x: 20, y: 246, w: 372, h: 69 }, // Model: large-v3
  { at: bar(16), x: 20, y: 613, w: 372, h: 77 }, // Učit se z diktátů: "pošle jejich text (ne zvuk)"
  { at: bar(17), x: 385, y: 144, w: 415, h: 48 }, // "Mikrofon je zapnutý jen při držení klávesy…"
];

const statements = [
  { at: bar(14), lines: ["Běží na tvé grafice."], size: 70, note: "Whisper large-v3, přímo v tvém počítači." },
  { at: bar(16), lines: ["Zvuk nikam neodchází."], size: 70, note: "Přepis vzniká u tebe, ne na serveru." },
  { at: bar(17), lines: ["Mikrofon poslouchá,", "jen když držíš klávesu."], size: 58, note: "" },
];

export const Privacy: React.FC = () => {
  const f = useCurrentFrame();
  if (f < PRIV_START - 4 || f > PRIV_END) return null;
  const inT = prog(f, PRIV_START - 4, PRIV_START + 30);
  const out = prog(f, PRIV_END - 22, PRIV_END, EASE_IN_OUT);
  const current = marks.filter((m) => f >= m.at).length - 1;
  const drift = (f - PRIV_START) * 0.08;

  return (
    <AbsoluteFill style={{ opacity: 1 - out }}>
      <div
        style={{
          position: "absolute",
          left: 150,
          top: 118,
          width: SHOT_W,
          height: TITLE + SHOWN_H * K,
          WebkitMaskImage: "linear-gradient(#000 calc(100% - 170px), transparent)",
          borderRadius: 12,
          overflow: "hidden",
          background: C.ink,
          boxShadow: "0 0 0 1px rgba(255,255,255,.08), 0 50px 110px rgba(0,0,0,.6)",
          opacity: inT,
          transform: `perspective(1800px) rotateY(${14 - inT * 4}deg) translateX(${(1 - inT) * -60}px) translateY(${-drift}px)`,
          transformOrigin: "100% 50%",
          filter: inT < 1 ? `blur(${(1 - inT) * 8}px)` : undefined,
        }}
      >
        <div
          style={{
            height: TITLE,
            display: "flex",
            alignItems: "center",
            padding: "0 0 0 16px",
            fontFamily: UI_VAR,
            fontSize: 15,
            color: "#C9CED8",
            background: C.ink,
          }}
        >
          <span style={{ flex: 1, opacity: 0.999 }}>Orbit – nastavení</span>
          {[GLYPH.min, GLYPH.max, GLYPH.close].map((g) => (
            <span key={g} style={{ fontFamily: ICONS, fontSize: 10, width: 46, textAlign: "center", color: "#9AA1AD", opacity: 0.999 }}>
              {g}
            </span>
          ))}
        </div>
        <Img
          src={staticFile("screens/settings.png")}
          style={{ width: SHOT_W, display: "block" }}
        />
        {marks.map((m, i) => {
          const on = i === current ? prog(f, m.at, m.at + 14) : i < current ? 1 - prog(f, marks[i + 1].at, marks[i + 1].at + 10) : 0;
          if (on <= 0) return null;
          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: m.x * K - 6,
                top: TITLE + m.y * K - 6,
                width: m.w * K + 12,
                height: m.h * K + 12,
                borderRadius: 10,
                border: `2px solid ${C.accent}`,
                boxShadow: `0 0 26px rgba(91,157,255,.35), inset 0 0 18px rgba(91,157,255,.15)`,
                opacity: on,
                transform: `scale(${1.04 - on * 0.04})`,
              }}
            />
          );
        })}
      </div>

      <div style={{ position: "absolute", left: 930, top: 210, width: 900, display: "flex", flexDirection: "column", gap: 54 }}>
        {statements.map((s, i) => {
          const active = i === current;
          return (
            <div key={i} style={{ position: "relative", paddingLeft: 46, opacity: f >= s.at ? (active ? 1 : 0.42) : 0 }}>
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: 30,
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: C.accent,
                  boxShadow: "0 0 14px rgba(91,157,255,.7)",
                  ...rise(f, s.at, 16, 10),
                }}
              />
              <Kinetic lines={s.lines} at={s.at} cfg={KIN.h2} size={s.size} lineHeight={1.02} />
              {s.note ? <div style={{ ...sub(32), marginTop: 14, ...rise(f, s.at + 8, 20, 14) }}>{s.note}</div> : null}
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};
