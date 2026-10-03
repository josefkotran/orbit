import React from "react";
import { GLYPH, ICONS, UI_VAR } from "../lib/theme";

/** A dark Windows 11 style window (no particular app), floating in space. */
export const Window: React.FC<{
  w: number;
  h: number;
  title: string;
  titleSize?: number;
  bar?: number;
  bg?: string;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}> = ({ w, h, title, titleSize = 20, bar = 52, bg = "#1A1E27", style, children }) => (
  <div
    style={{
      position: "absolute",
      width: w,
      height: h,
      borderRadius: 14,
      background: bg,
      boxShadow: "0 0 0 1px rgba(255,255,255,.08), 0 40px 90px rgba(0,0,0,.55), 0 10px 30px rgba(0,0,0,.35)",
      overflow: "hidden",
      fontFamily: UI_VAR,
      ...style,
    }}
  >
    <div
      style={{
        height: bar,
        display: "flex",
        alignItems: "center",
        padding: "0 0 0 22px",
        background: "rgba(255,255,255,.025)",
        borderBottom: "1px solid rgba(255,255,255,.05)",
        color: "#C9CED8",
        fontSize: titleSize,
      }}
    >
      <span style={{ flex: 1, whiteSpace: "nowrap", overflow: "hidden" }}>{title}</span>
      {[GLYPH.min, GLYPH.max, GLYPH.close].map((g) => (
        <span key={g} style={{ fontFamily: ICONS, fontSize: titleSize * 0.62, width: bar * 1.25, textAlign: "center", color: "#9AA1AD" }}>
          {g}
        </span>
      ))}
    </div>
    {children}
  </div>
);

/** Windows' arrow cursor. */
export const Cursor: React.FC<{ x: number; y: number; scale?: number; press?: number }> = ({ x, y, scale = 1.7, press = 0 }) => (
  <svg
    width={22 * scale}
    height={32 * scale}
    viewBox="0 0 22 32"
    style={{
      position: "absolute",
      left: x,
      top: y,
      transform: `scale(${1 - press * 0.08})`,
      transformOrigin: "0 0",
      filter: "drop-shadow(0 3px 5px rgba(0,0,0,.5))",
    }}
  >
    <path d="M1,1 L1,24 L6.6,18.6 L10.4,27.4 L14.2,25.8 L10.6,17.2 L18.2,17.2 Z" fill="#fff" stroke="#000" strokeWidth={1.3} strokeLinejoin="round" />
  </svg>
);

/** Blinking text caret. */
export const Caret: React.FC<{ frame: number; h: number; color?: string }> = ({ frame, h, color = "#E6E8EC" }) => (
  <span
    style={{
      display: "inline-block",
      width: 2.5,
      height: h,
      background: color,
      verticalAlign: "middle",
      marginLeft: 2,
      opacity: Math.floor(frame / 16) % 2 === 0 ? 1 : 0,
    }}
  />
);
