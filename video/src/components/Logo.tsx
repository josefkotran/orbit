import React from "react";
import { C } from "../lib/theme";

/** The website's mark: a planet with a ring in the text colour, its moon in the accent. */
export const LogoMark: React.FC<{ size: number; bg?: string; moonAngle?: number }> = ({ size, bg = C.space, moonAngle }) => {
  // the moon sits on the ring's front arc; moonAngle moves it along (radians, 0.55 ≈ the site's resting place)
  const t = moonAngle ?? 0.55;
  const mx = 16 + 11.8 * Math.cos(t);
  const my = 16 + 4.2 * Math.sin(t);
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" style={{ overflow: "visible" }}>
      <g transform="rotate(-24 16 16)">
        <path d="M4.2 16a11.8 4.2 0 0 1 23.6 0" fill="none" stroke={C.text} strokeWidth={1.6} opacity={0.55} />
        <circle cx={16} cy={16} r={6} fill={C.text} />
        <path d="M4.2 16a11.8 4.2 0 0 0 23.6 0" fill="none" stroke={bg} strokeWidth={2.8} />
        <path d="M4.2 16a11.8 4.2 0 0 0 23.6 0" fill="none" stroke={C.text} strokeWidth={1.6} strokeLinecap="round" />
        <circle cx={mx} cy={my} r={2} fill={C.accent} stroke={bg} strokeWidth={1.2} />
      </g>
    </svg>
  );
};
