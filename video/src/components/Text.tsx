import React from "react";
import { useCurrentFrame } from "remotion";
import { rise, sink } from "../lib/anim";
import { C, TEXT } from "../lib/theme";

type WordsProps = {
  text: string;
  at: number;
  /** Frames between words. */
  stagger?: number;
  out?: number;
  style?: React.CSSProperties;
  dur?: number;
  dist?: number;
};

/** Body text (Mona Sans) that comes in word by word (rise + unblur) and leaves together. */
export const Words: React.FC<WordsProps> = ({ text, at, stagger = 2, out, style, dur = 20, dist = 18 }) => {
  const f = useCurrentFrame();
  const words = text.split(" ");
  const exit = out !== undefined ? sink(f, out) : {};
  return (
    <div style={{ ...style, ...exit }}>
      {words.map((w, i) => (
        <React.Fragment key={i}>
          <span style={{ display: "inline-block", ...rise(f, at + i * stagger, dur, dist) }}>{w}</span>
          {i < words.length - 1 ? " " : null}
        </React.Fragment>
      ))}
    </div>
  );
};

export const sub = (size = 34): React.CSSProperties => ({
  fontFamily: TEXT,
  fontWeight: 400,
  fontSize: size,
  lineHeight: 1.45,
  color: C.soft,
});
