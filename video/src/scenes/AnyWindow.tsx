import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { KIN, Kinetic } from "../components/Kinetic";
import { Words, sub } from "../components/Text";
import { Caret, Window } from "../components/Window";
import { EASE_IN_OUT, prog } from "../lib/anim";
import { C, ICONS, GLYPH, UI_VAR } from "../lib/theme";
import { bar, beat } from "../lib/time";
import { SPOKEN } from "./Dictation";

export const ANY_START = bar(8);
export const ANY_END = bar(10) + 16;

const W = 420;
const H = 360;
const Y = 380;
const xs = [66, 522, 978, 1434];

/** A dictated line landing in a window: a red mic blip, then the text fades in sharp. */
const Dictated: React.FC<{ f: number; at: number; text: string; size?: number; color?: string; mono?: boolean }> = ({
  f,
  at,
  text,
  size = 23,
  color = "#E6E8EC",
  mono,
}) => {
  const t = prog(f, at, at + 10);
  return (
    <span style={{ fontFamily: mono ? '"Cascadia Mono", Consolas, monospace' : UI_VAR, fontSize: size, color, lineHeight: 1.45 }}>
      <span style={{ opacity: t, filter: t < 1 ? `blur(${(1 - t) * 5}px)` : undefined }}>{text}</span>
      {f < at ? <Caret frame={f} h={size * 1.15} /> : null}
    </span>
  );
};

const RecBlip: React.FC<{ f: number; at: number }> = ({ f, at }) => {
  const on = prog(f, at - 16, at - 12) * (1 - prog(f, at - 2, at + 4));
  return (
    <div
      style={{
        position: "absolute",
        right: 18,
        bottom: 18,
        width: 46,
        height: 46,
        borderRadius: "50%",
        background: C.appListen,
        boxShadow: `0 0 0 ${6 + 4 * Math.sin(f * 0.6)}px rgba(229,72,77,.3)`,
        color: "#fff",
        fontFamily: ICONS,
        fontSize: 21,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        opacity: on,
        transform: `scale(${0.7 + on * 0.3})`,
      }}
    >
      {GLYPH.mic}
    </div>
  );
};

export const AnyWindow: React.FC = () => {
  const f = useCurrentFrame();
  if (f < ANY_START - 2 || f > ANY_END) return null;
  const out = prog(f, ANY_END - 18, ANY_END, EASE_IN_OUT);
  const lines = [ANY_START + beat(2), ANY_START + beat(4), ANY_START + beat(6)];

  const win = (i: number) => {
    const t = prog(f, ANY_START + i * 4, ANY_START + 22 + i * 4);
    const fan = (i - 1.5) * 7;
    return {
      left: xs[i],
      top: Y,
      opacity: t * (1 - out),
      transform: `perspective(1600px) rotateY(${-fan * (1 - t * 0.5)}deg) translateY(${(1 - t) * 50 - out * 20}px) scale(${0.92 + t * 0.08})`,
      filter: t < 1 ? `blur(${(1 - t) * 6}px)` : undefined,
    } as React.CSSProperties;
  };

  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", top: 118, left: 0, right: 0, textAlign: "center", opacity: 1 - out }}>
        <Kinetic lines={["Píše tam, kde máš kurzor."]} at={ANY_START + 6} cfg={KIN.h2} size={92} align="center" />
        <Words text="E-mail, dokument, chat i terminál." at={ANY_START + 18} stagger={2} style={{ ...sub(36), marginTop: 26 }} />
      </div>

      <Window w={W} h={H} title="Nová zpráva" titleSize={17} bar={44} style={win(0)}>
        <div style={{ padding: "14px 22px", fontSize: 17, color: "#9AA1AD", borderBottom: "1px solid rgba(255,255,255,.07)" }}>
          Komu: <span style={{ color: "#E6E8EC" }}>Petr Novák</span>
        </div>
        <div style={{ padding: "16px 22px", fontFamily: UI_VAR, fontSize: 21, lineHeight: 1.45, color: "#E6E8EC" }}>{SPOKEN}</div>
      </Window>

      <Window w={W} h={H} title="Zápis z porady" titleSize={17} bar={44} bg="#1D2029" style={win(1)}>
        <div style={{ padding: "20px 26px" }}>
          <div style={{ fontFamily: UI_VAR, fontSize: 27, fontWeight: 600, color: "#E6E8EC", marginBottom: 12 }}>Porada 3. 10.</div>
          <div style={{ height: 2, width: 60, background: "rgba(255,255,255,.12)", marginBottom: 16 }} />
          <Dictated f={f} at={lines[0]} text="Schválili jsme nový ceník, platí od listopadu." />
        </div>
        <RecBlip f={f} at={lines[0]} />
      </Window>

      <Window w={W} h={H} title="Tým" titleSize={17} bar={44} style={win(2)}>
        <div style={{ padding: "18px 20px", display: "flex", flexDirection: "column", gap: 12, fontFamily: UI_VAR, fontSize: 20 }}>
          <div style={{ alignSelf: "flex-start", background: "#2A2F3B", color: "#E6E8EC", padding: "10px 16px", borderRadius: 16 }}>
            Stihneš to dnes?
          </div>
          {f >= lines[1] ? (
            <div
              style={{
                alignSelf: "flex-end",
                background: "#2B4A80",
                color: "#fff",
                padding: "10px 16px",
                borderRadius: 16,
                maxWidth: 300,
                opacity: prog(f, lines[1], lines[1] + 8),
                transform: `translateY(${(1 - prog(f, lines[1], lines[1] + 10)) * 14}px)`,
              }}
            >
              Jasně, pošlu to hned po obědě.
            </div>
          ) : null}
        </div>
        <div
          style={{
            position: "absolute",
            left: 16,
            right: 16,
            bottom: 16,
            height: 46,
            borderRadius: 23,
            background: "#232834",
            padding: "0 18px",
            display: "flex",
            alignItems: "center",
          }}
        >
          {f < lines[1] ? <Caret frame={f} h={22} /> : null}
        </div>
        <RecBlip f={f} at={lines[1]} />
      </Window>

      <Window w={W} h={H} title="✳ Export faktur" titleSize={17} bar={44} bg="#0E1117" style={win(3)}>
        <div style={{ padding: "18px 22px", fontFamily: '"Cascadia Mono", Consolas, monospace', fontSize: 18, color: "#8B96AD", lineHeight: 1.6 }}>
          <div>~/faktury</div>
          <div
            style={{
              marginTop: 14,
              border: "1px solid rgba(255,255,255,.18)",
              borderRadius: 8,
              padding: "10px 14px",
              color: "#E6E8EC",
              minHeight: 80,
            }}
          >
            <span style={{ color: C.dim }}>&gt; </span>
            <Dictated f={f} at={lines[2]} text="Oprav export faktur a spusť testy." size={18} mono />
          </div>
        </div>
        <RecBlip f={f} at={lines[2]} />
      </Window>
    </AbsoluteFill>
  );
};
