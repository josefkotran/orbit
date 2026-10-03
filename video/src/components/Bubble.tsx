import React from "react";
import { GLYPH, ICONS, UI_VAR } from "../lib/theme";

// Replica of app/ui.py Bubble: a card in the panel's style with a tail pointing at the mic button.

export const BUBBLE_W = 330;
const PAD = 12;
const ICON = 30;
const TAIL = 8;
const LINE = 16;

const KINDS = {
  done: { color: "#3DD68C", glyph: GLYPH.check },
  waiting: { color: "#F5A524", glyph: GLYPH.help },
  error: { color: "#E5484D", glyph: GLYPH.important },
  info: { color: "#5B9DFF", glyph: GLYPH.info },
};

export const bubbleHeight = (lines: number) => PAD * 2 + Math.max(ICON, 18 + (lines ? 3 + lines * LINE : 0));

export const Bubble: React.FC<{
  kind: keyof typeof KINDS;
  title: string;
  note: string;
  lines: string[];
  /** Tail on the right edge at this height (from the card's top), or none. */
  tailY?: number;
}> = ({ kind, title, note, lines, tailY }) => {
  const { color, glyph } = KINDS[kind];
  const h = bubbleHeight(lines.length);
  return (
    <div style={{ position: "relative", width: BUBBLE_W + TAIL, height: h, fontFamily: UI_VAR }}>
      <svg width={BUBBLE_W + TAIL} height={h} style={{ position: "absolute", inset: 0, overflow: "visible" }}>
        <defs>
          <filter id="bshadow" x="-20%" y="-30%" width="140%" height="170%">
            <feDropShadow dx="0" dy="3" stdDeviation="6" floodColor="#000" floodOpacity=".45" />
          </filter>
        </defs>
        <path
          d={card(BUBBLE_W, h, 12, tailY)}
          fill="rgba(24,27,34,.96)"
          stroke="rgba(255,255,255,.11)"
          strokeWidth={1}
          filter="url(#bshadow)"
        />
      </svg>
      <div
        style={{
          position: "absolute",
          left: PAD,
          top: PAD,
          width: ICON,
          height: ICON,
          borderRadius: "50%",
          background: hexA(color, 38 / 255),
          color,
          fontFamily: ICONS,
          fontSize: 15,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {glyph}
      </div>
      <div style={{ position: "absolute", left: PAD + ICON + 12, top: PAD - 1, right: TAIL + PAD, height: 18, lineHeight: "18px" }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: "#E6E8EC" }}>{title}</span>
        <span style={{ position: "absolute", right: 0, fontSize: 11, color }}>{note}</span>
      </div>
      {lines.map((l, i) => (
        <div
          key={i}
          style={{
            position: "absolute",
            left: PAD + ICON + 12,
            top: PAD - 1 + 18 + 3 + i * LINE,
            height: LINE,
            lineHeight: `${LINE}px`,
            fontSize: 12,
            color: "#AEB5C2",
            whiteSpace: "nowrap",
          }}
        >
          {l}
        </div>
      ))}
    </div>
  );
};

function card(w: number, h: number, r: number, tailY?: number) {
  const x0 = 0.5;
  const y0 = 0.5;
  const x1 = w - 0.5;
  const y1 = h - 0.5;
  const tail =
    tailY === undefined ? `L${x1},${y1 - r}` : `L${x1},${tailY - 7}L${x1 + TAIL},${tailY}L${x1},${tailY + 7}L${x1},${y1 - r}`;
  return (
    `M${x0 + r},${y0}L${x1 - r},${y0}Q${x1},${y0} ${x1},${y0 + r}` +
    tail +
    `Q${x1},${y1} ${x1 - r},${y1}L${x0 + r},${y1}Q${x0},${y1} ${x0},${y1 - r}L${x0},${y0 + r}Q${x0},${y0} ${x0 + r},${y0}Z`
  );
}

function hexA(hex: string, a: number) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}
