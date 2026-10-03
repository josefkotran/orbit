import React from "react";
import { useCurrentFrame } from "remotion";
import { EASE_IN, EXPO_OUT, prog, rnd } from "../lib/anim";
import { C, DISPLAY } from "../lib/theme";

// The website's kinetic type (site.js): every letter of Anybody has its own width and weight. A wave runs through
// the line, letters assemble from thin and narrow when they appear, and while someone speaks they shiver with the
// voice level. Times here are in frames at 30 fps (the site's sin(t * 0.0016 - i * 0.55) with t in ms).

export type KinCfg = { base: [number, number]; wave: [number, number]; listen: [number, number]; spacing: string };
export const KIN = {
  hero: { base: [108, 640], wave: [9, 55], listen: [30, 240], spacing: "-0.02em" },
  h2: { base: [100, 600], wave: [5, 34], listen: [24, 200], spacing: "-0.01em" },
  mark: { base: [132, 800], wave: [6, 50], listen: [0, 0], spacing: "-0.01em" },
  said: { base: [108, 560], wave: [4, 30], listen: [34, 260], spacing: "0em" },
} satisfies Record<string, KinCfg>;

type Props = {
  /** One string per line (lines never re-wrap while the letters breathe). */
  lines: string[];
  /** Frame the first letter starts to assemble. */
  at: number;
  /** Frames between letters. */
  stagger?: number;
  /** Instead of `stagger`: when each word (counted over all lines) starts. */
  wordAt?: (word: number) => number;
  dur?: number;
  /** Frame the letters start to dissolve (thin out and rise). */
  out?: number;
  cfg?: KinCfg;
  size: number;
  italic?: boolean;
  /** Voice level 0..1: the letters shiver with it. */
  level?: number;
  color?: string;
  lineHeight?: number;
  align?: "left" | "center";
  style?: React.CSSProperties;
};

export const Kinetic: React.FC<Props> = ({
  lines,
  at,
  stagger = 1.4,
  wordAt,
  dur = 30,
  out,
  cfg = KIN.hero,
  size,
  italic = false,
  level = 0,
  color = C.text,
  lineHeight = 0.96,
  align = "left",
  style,
}) => {
  const f = useCurrentFrame();
  let i = 0;
  let w = 0;
  return (
    <div
      style={{
        fontFamily: DISPLAY,
        fontStyle: italic ? "italic" : "normal",
        fontSize: size,
        lineHeight,
        letterSpacing: cfg.spacing,
        color,
        textAlign: align,
        whiteSpace: "nowrap",
        ...style,
      }}
    >
      {lines.map((line, li) => (
        <div key={li}>
          {line.split(" ").map((word, wi, all) => {
            const wordStart = wordAt ? wordAt(w) : undefined;
            w++;
            const chars = Array.from(word).map((ch, ci) => {
              const n = i++;
              const start = wordStart !== undefined ? wordStart + ci * 1.2 : at + n * stagger;
              let a = prog(f, start, start + dur, EXPO_OUT);
              let lift = (1 - a) * 0.35;
              if (out !== undefined) {
                const b = prog(f, out + n * 0.6, out + n * 0.6 + 16, EASE_IN);
                a *= 1 - b;
                lift = b > 0 ? -b * 0.2 : lift;
              }
              const wave = Math.sin(f * 0.0533 - n * 0.55);
              let tw = cfg.base[0] + cfg.wave[0] * wave;
              let tg = cfg.base[1] + cfg.wave[1] * wave;
              if (level > 0.001) {
                const seed = rnd(n, 4) * 100;
                const jig = Math.sin(f * 0.7 + seed) * 0.5 + Math.sin(f * 0.457 + seed * 2.3) * 0.5;
                tw += level * cfg.listen[0] * jig;
                tg += level * cfg.listen[1] * (0.4 + 0.6 * Math.abs(jig));
              }
              const wd = Math.min(150, Math.max(50, 50 + (tw - 50) * a));
              const wg = Math.min(900, Math.max(100, 100 + (tg - 100) * a));
              return (
                <span
                  key={ci}
                  style={{
                    display: "inline-block",
                    fontVariationSettings: `"wdth" ${wd.toFixed(1)}, "wght" ${wg.toFixed(0)}`,
                    opacity: a,
                    transform: a < 1 ? `translateY(${lift.toFixed(3)}em)` : undefined,
                  }}
                >
                  {ch}
                </span>
              );
            });
            return (
              <React.Fragment key={wi}>
                <span style={{ display: "inline-block" }}>{chars}</span>
                {wi < all.length - 1 ? " " : null}
              </React.Fragment>
            );
          })}
        </div>
      ))}
    </div>
  );
};
