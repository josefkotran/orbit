import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { KIN, Kinetic } from "../components/Kinetic";
import { OrbitWidget } from "../components/OrbitWidget";
import { sub } from "../components/Text";
import { Caret, Cursor, Window } from "../components/Window";
import { EASE_IN_OUT, lerp, prog, rise } from "../lib/anim";
import { C, TEXT, UI_VAR } from "../lib/theme";
import { bar } from "../lib/time";
import { DICT_MIC } from "./Intro";
import { SPOKEN, WIN, speechLevel } from "./Dictation";

// Correcting by voice (app/editing.py, rewrite.py): "Smaž to." takes back the last dictation, and with Ctrl held what
// you say is an instruction for Claude, who rewrites the text. Back in the mail window of the dictation scene.
export const EDIT_START = bar(10);
export const EDIT_END = bar(14) + 18;

const EXTRA = " Mimochodem, tvůj návrh loga je hrozný.";
const FORMAL = "Dobrý den, pane Nováku, zasílám Vám nabídku na zítřek. Prosím o odpověď do pátku.";

const S1 = EDIT_START + 34; // press: „Smaž to.“
const S1_WORDS = [S1 + 8, S1 + 16];
const S1_UP = S1 + 30;
const ERASE = S1_UP + 8; // the last dictation goes, from its end
const CTRL = bar(12) - 13;
const S2 = bar(12); // press with Ctrl held: „Napiš to formálněji.“
const S2_WORDS = [S2 + 9, S2 + 16, S2 + 22];
const S2_UP = S2 + 45;
const REWRITE = S2_UP + 24; // Claude's text replaces it
export const EDIT_EVENTS = { listen: [S1 + 6, S2 + 6], stop: [S1_UP, S2_UP] };

const WIDGET_SCALE = 2;
const WIDGET_POS = { x: DICT_MIC.x - 90 * WIDGET_SCALE, y: DICT_MIC.y - 36 * WIDGET_SCALE };

const Keycap: React.FC<{ down: number }> = ({ down }) => (
  <div
    style={{
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      height: 54,
      padding: "0 22px",
      borderRadius: 12,
      background: "#1A2233",
      boxShadow: `inset 0 0 0 1.5px ${down > 0 ? C.accent : "rgba(255,255,255,.18)"}, 0 ${6 - 4 * down}px 0 #0B1020`,
      transform: `translateY(${4 * down}px)`,
      fontFamily: TEXT,
      fontWeight: 600,
      fontSize: 28,
      color: C.text,
    }}
  >
    <span style={{ opacity: 0.999 }}>Ctrl</span>
  </div>
);

export const Edit: React.FC = () => {
  const f = useCurrentFrame();
  if (f < EDIT_START + 8 || f > EDIT_END) return null;
  const winIn = prog(f, EDIT_START + 10, EDIT_START + 32); // after the four windows are gone
  const exitT = prog(f, EDIT_END - 18, EDIT_END, EASE_IN_OUT);

  const rec1 = f >= S1 + 6 && f < S1_UP;
  const rec2 = f >= S2 + 6 && f < S2_UP;
  const busy1 = f >= S1_UP && f < ERASE;
  const busy2 = f >= S2_UP && f < REWRITE;
  const level = rec1 ? speechLevel(f, S1_WORDS, 8) : rec2 ? speechLevel(f, S2_WORDS, 7) : 0;
  const editing = f >= S2 && f < REWRITE + 4;

  // the text in the window: the last dictation (marked) erased from its end, then the rest rewritten by Claude
  const kept = Math.round(EXTRA.length * (1 - prog(f, ERASE, ERASE + 14, EASE_IN_OUT)));
  const extra = EXTRA.slice(0, kept);
  const lastMark = prog(f, EDIT_START + 20, EDIT_START + 34) * (1 - prog(f, S1_UP, ERASE));
  const rewriting = prog(f, S2_UP, S2_UP + 10) * (1 - prog(f, REWRITE, REWRITE + 8));
  const swap = prog(f, REWRITE, REWRITE + 14);

  // the cursor holds the mic for both, with Ctrl down for the second
  const curIn = prog(f, EDIT_START + 8, S1 - 2, EASE_IN_OUT);
  const curOut = prog(f, S2_UP + 14, S2_UP + 44, EASE_IN_OUT);
  const tip = { x: DICT_MIC.x - 2, y: DICT_MIC.y - 4 };
  const hop = lerp(f, [S1_UP, S1_UP + 10, S2 - 10, S2], [0, 1, 1, 0], EASE_IN_OUT);
  const cx = lerp(curIn, [0, 1], [1600, tip.x]) + curOut * 230 + hop * 40;
  const cy = lerp(curIn, [0, 1], [1080, tip.y]) + curOut * 150 + hop * 46;
  const press = (f >= S1 && f < S1_UP ? prog(f, S1, S1 + 4) : 0) + (f >= S2 && f < S2_UP ? prog(f, S2, S2 + 4) : 0);
  const ctrlDown = f >= CTRL && f < S2_UP + 4 ? prog(f, CTRL, CTRL + 4) : 0;

  const active = f < S2 - 8 ? 0 : 1;
  const barY = lerp(f, [S2 - 10, S2 + 4], [119, 333], EASE_IN_OUT);

  return (
    <AbsoluteFill style={{ opacity: 1 - exitT }}>
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
          <div style={{ position: "relative", marginTop: 30, fontFamily: UI_VAR, fontSize: 34, lineHeight: 1.5, color: "#E6E8EC" }}>
            {swap < 1 ? (
              <div style={{ opacity: 1 - swap, filter: swap > 0 ? `blur(${swap * 6}px)` : undefined }}>
                <span
                  style={{
                    background: `rgba(91,157,255,${(0.16 * rewriting).toFixed(3)})`,
                    boxShadow: rewriting > 0 ? `0 0 0 3px rgba(91,157,255,${(0.16 * rewriting).toFixed(3)})` : undefined,
                    borderRadius: 4,
                  }}
                >
                  {SPOKEN}
                </span>
                <span
                  style={{
                    background: `rgba(91,157,255,${(0.2 * lastMark).toFixed(3)})`,
                    borderRadius: 4,
                    boxShadow: lastMark > 0 ? `0 0 0 3px rgba(91,157,255,${(0.2 * lastMark).toFixed(3)})` : undefined,
                  }}
                >
                  {extra}
                </span>
                {swap === 0 ? <Caret frame={f} h={40} /> : null}
              </div>
            ) : null}
            {swap > 0 ? (
              <div style={{ position: "absolute", left: 0, top: 0, opacity: swap, filter: swap < 1 ? `blur(${(1 - swap) * 6}px)` : undefined }}>
                {FORMAL}
                <Caret frame={f} h={40} />
              </div>
            ) : null}
          </div>
        </div>
      </Window>

      {/* Orbit's floating button: a pencil instead of the mic while the dictation is an instruction */}
      <div style={{ position: "absolute", left: WIDGET_POS.x, top: WIDGET_POS.y, transform: `scale(${WIDGET_SCALE})`, transformOrigin: "0 0", opacity: winIn }}>
        <OrbitWidget
          panel={false}
          mic={rec1 || rec2 ? "recording" : busy1 || busy2 ? "busy" : "idle"}
          editing={editing}
          level={level}
          phase={f * 0.36}
          pressed={Math.min(1, press)}
        />
      </div>
      {busy2 ? (
        <div style={{ position: "absolute", left: DICT_MIC.x - 380, top: DICT_MIC.y + 62, width: 380, textAlign: "right", ...sub(24), ...rise(f, S2_UP + 2, 12, 8) }}>
          Claude přepisuje…
        </div>
      ) : null}
      {f >= EDIT_START + 8 && f < S2_UP + 46 ? <Cursor x={cx} y={cy} press={Math.min(1, press)} /> : null}

      {/* what to say, and what it does */}
      <div style={{ position: "absolute", left: 1262, top: 150, width: 620 }}>
        <Kinetic lines={["Opravíš hlasem."]} at={EDIT_START + 12} cfg={KIN.h2} size={76} />
        <div style={{ position: "relative", marginTop: 46, height: 200, opacity: active === 0 ? 1 : 0.32 }}>
          <Kinetic lines={["„Smaž to.“"]} at={S1} wordAt={(w) => S1_WORDS[w] - 2} dur={16} cfg={KIN.said} italic size={64} lineHeight={1.1} level={rec1 ? level : 0} />
          <div style={{ ...sub(28), marginTop: 12, ...rise(f, S1_UP, 20, 14) }}>a poslední diktát zmizí. Umí i Vyber to, Vlož to znovu a Nahraď.</div>
        </div>
        <div style={{ position: "relative", marginTop: 14, opacity: f >= CTRL - 6 ? 1 : 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, ...rise(f, CTRL - 6, 16, 12) }}>
            <Keycap down={ctrlDown} />
            <span style={{ fontFamily: TEXT, fontSize: 30, color: C.soft }}>a řekni, co s textem:</span>
          </div>
          <Kinetic
            lines={["„Napiš to formálněji.“"]}
            at={S2}
            wordAt={(w) => S2_WORDS[w] - 2}
            dur={16}
            cfg={KIN.said}
            italic
            size={54}
            lineHeight={1.1}
            level={rec2 ? level : 0}
            style={{ marginTop: 18 }}
          />
          <div style={{ ...sub(28), marginTop: 12, ...rise(f, REWRITE - 4, 20, 14) }}>Text ti přepíše Claude.</div>
        </div>
        <div
          style={{
            position: "absolute",
            left: -34,
            top: barY,
            width: 2,
            height: lerp(f, [S2 - 10, S2 + 4], [160, 190], EASE_IN_OUT),
            background: C.accent,
            boxShadow: "0 0 18px rgba(91,157,255,.6)",
            opacity: prog(f, S1, S1 + 16),
          }}
        />
      </div>
    </AbsoluteFill>
  );
};
