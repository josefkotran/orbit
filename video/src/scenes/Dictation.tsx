import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { OrbitWidget } from "../components/OrbitWidget";
import { KIN, Kinetic } from "../components/Kinetic";
import { sub } from "../components/Text";
import { Caret, Cursor, Window } from "../components/Window";
import { EASE_IN_OUT, lerp, prog, rise, rnd } from "../lib/anim";
import { C, UI_VAR } from "../lib/theme";
import { bar } from "../lib/time";
import { DICT_MIC, INTRO_END } from "./Intro";

// "Drž, mluv, pusť." – the three verbs land on bars 4, 5 and 7 while the demo does exactly that.
export const DRZ = bar(4);
export const MLUV = bar(5);
export const PUST = bar(7);
export const REC_ON = DRZ + 6; // red once sound really flows
export const BUSY_ON = PUST + 2;
export const INSERT = PUST + 18;
export const DICT_END = bar(8) + 14;

export const SPOKEN = "Ahoj Petře, posílám ti nabídku na zítřek. Ozvi se mi prosím do pátku.";
const WORDS = SPOKEN.split(" ");
const WORD_GAP = 8;
const SPEAK_FROM = MLUV + 4;
export const wordAt = (i: number) => SPEAK_FROM + i * WORD_GAP;

/** Mic level from the spoken words: a bump per syllable-ish, a little jitter. */
export const speechLevel = (f: number, starts: number[], gap = WORD_GAP) => {
  let v = 0;
  starts.forEach((s, i) => {
    const t = (f - s) / (gap * 1.1);
    if (t > -0.1 && t < 1) v = Math.max(v, Math.sin(Math.max(0, t) * Math.PI) * (0.6 + 0.35 * rnd(i, 9)));
  });
  return Math.min(1, v * (0.85 + 0.15 * Math.sin(f * 1.7)));
};

export const WIN = { x: 100, y: 110, w: 980, h: 600 };
const WIDGET_SCALE = 2;
// buttons-only widget is 126 x 72 logical; its mic centre is at (90, 36)
const WIDGET_POS = { x: DICT_MIC.x - 90 * WIDGET_SCALE, y: DICT_MIC.y - 36 * WIDGET_SCALE };

const Verb: React.FC<{ f: number; at: number; word: string; note: string; active: boolean; level?: number }> = ({
  f,
  at,
  word,
  note,
  active,
  level = 0,
}) => {
  const dimmed = !active && f >= at;
  return (
    <div style={{ position: "relative", height: 228, opacity: dimmed ? 0.3 : 1 }}>
      <Kinetic lines={[word]} at={at} stagger={2} cfg={KIN.hero} size={146} lineHeight={1} level={level} />
      <div style={{ ...sub(30), marginTop: 12, ...rise(f, at + 8, 20, 16) }}>{note}</div>
    </div>
  );
};

// the dictated sentence as it is said, in two fixed lines
const SAID_LINES = ["„Ahoj Petře, posílám ti", "nabídku na zítřek. Ozvi se mi", "prosím do pátku.“"];

export const Dictation: React.FC = () => {
  const f = useCurrentFrame();
  if (f < 160 || f > DICT_END + 4) return null;

  const winIn = prog(f, 168, 212);
  const exitT = prog(f, bar(8) - 6, bar(8) + 12, EASE_IN_OUT);
  const recording = f >= REC_ON && f < BUSY_ON;
  const busy = f >= BUSY_ON && f < INSERT + 2;
  const level = recording ? speechLevel(f, WORDS.map((_, i) => wordAt(i))) : 0;

  // cursor: glides onto the mic, presses, holds, lets go, drifts away
  const curIn = prog(f, 196, DRZ - 2, EASE_IN_OUT);
  const curOut = prog(f, PUST + 24, PUST + 54, EASE_IN_OUT);
  const tip = { x: DICT_MIC.x - 2, y: DICT_MIC.y - 4 };
  const cx = lerp(curIn, [0, 1], [1560, tip.x]) + curOut * 230;
  const cy = lerp(curIn, [0, 1], [1080, tip.y]) + curOut * 150;
  const press = f >= DRZ && f < PUST ? prog(f, DRZ, DRZ + 4) : 0;

  const inserted = prog(f, INSERT, INSERT + 10);
  const flyUp = prog(f, INSERT - 4, INSERT + 10, EASE_IN_OUT);
  const active = f < MLUV ? 0 : f < PUST ? 1 : 2;

  return (
    <AbsoluteFill style={{ opacity: 1 - exitT }}>
      {/* the mail window */}
      <Window
        w={WIN.w}
        h={WIN.h}
        title="Nová zpráva"
        style={{
          left: WIN.x,
          top: WIN.y,
          opacity: winIn,
          transform: `translateY(${(1 - winIn) * 40}px) scale(${0.96 + winIn * 0.04 - exitT * 0.06})`,
          filter: winIn < 1 ? `blur(${(1 - winIn) * 8}px)` : undefined,
        }}
      >
        <div style={{ padding: "8px 40px 0", fontSize: 26, color: "#9AA1AD" }}>
          {[
            ["Komu", "Petr Novák"],
            ["Předmět", "Nabídka na zítřek"],
          ].map(([k, v]) => (
            <div key={k} style={{ display: "flex", gap: 22, padding: "18px 0", borderBottom: "1px solid rgba(255,255,255,.07)" }}>
              <span style={{ width: 120 }}>{k}</span>
              <span style={{ color: "#E6E8EC" }}>{v}</span>
            </div>
          ))}
          <div style={{ marginTop: 30, fontFamily: UI_VAR, fontSize: 34, lineHeight: 1.5, color: "#E6E8EC" }}>
            {inserted > 0 ? (
              <span style={{ opacity: inserted, filter: inserted < 1 ? `blur(${(1 - inserted) * 6}px)` : undefined }}>{SPOKEN}</span>
            ) : null}
            <Caret frame={f} h={40} />
          </div>
        </div>
      </Window>

      {/* what you say, in Anybody italic, word by word as it is spoken; on release it flies into the window */}
      <div
        style={{
          position: "absolute",
          left: WIN.x + 4,
          top: 748,
          opacity: 1 - flyUp,
          transform: `translateY(${-flyUp * 300}px) scale(${1 - flyUp * 0.15})`,
          transformOrigin: "0 0",
          filter: flyUp > 0 ? `blur(${flyUp * 6}px)` : undefined,
        }}
      >
        <Kinetic lines={SAID_LINES} at={0} wordAt={wordAt} dur={16} cfg={KIN.said} italic size={40} lineHeight={1.2} level={level} />
      </div>

      {/* Orbit's floating button: speaker + mic */}
      <div
        style={{
          position: "absolute",
          left: WIDGET_POS.x,
          top: WIDGET_POS.y,
          transform: `scale(${WIDGET_SCALE})`,
          transformOrigin: "0 0",
        }}
      >
        <OrbitWidget
          speakerOpacity={prog(f, 186, INTRO_END)}
          micOpacity={f >= INTRO_END ? 1 : 0}
          panel={false} mic={recording ? "recording" : busy ? "busy" : "idle"} level={level} phase={f * 0.36} pressed={press} />
      </div>

      {f >= 196 && f < PUST + 56 ? <Cursor x={cx} y={cy} press={press} /> : null}

      {/* the three verbs */}
      <div style={{ position: "absolute", left: 1300, top: 150, width: 560 }}>
        <Verb f={f} at={DRZ} word="Drž," note="klávesu nebo tlačítko myši" active={active === 0} />
        <Verb f={f} at={MLUV} word="mluv," note="česky, normálně jako vždycky" active={active === 1} level={level} />
        <Verb f={f} at={PUST} word="pusť." note="a text je v okně" active={active === 2} />
        <div
          style={{
            position: "absolute",
            left: -34,
            top: lerp(f, [MLUV - 2, MLUV + 12, PUST - 2, PUST + 12], [20, 248, 248, 476], EASE_IN_OUT),
            width: 2,
            height: 116,
            background: C.accent,
            boxShadow: "0 0 18px rgba(91,157,255,.6)",
            opacity: prog(f, DRZ, DRZ + 16),
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
