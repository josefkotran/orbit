import { Easing, interpolate, spring } from "remotion";
import { FPS } from "./time";

export const EXPO_OUT = Easing.bezier(0.16, 1, 0.3, 1);
export const EASE_IN_OUT = Easing.bezier(0.65, 0, 0.35, 1);
export const EASE_IN = Easing.bezier(0.5, 0, 0.75, 0);

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;

/** 0 → 1 between frames a and b (clamped), eased. */
export const prog = (f: number, a: number, b: number, easing = EXPO_OUT) =>
  interpolate(f, [a, b], [0, 1], { ...clamp, easing });

/** Linear map with clamping. */
export const lerp = (f: number, input: number[], output: number[], easing?: (t: number) => number) =>
  interpolate(f, input, output, { ...clamp, easing });

/** Opacity that fades in at [in, in+d] and out at [out-d, out]. */
export const window_ = (f: number, inAt: number, outAt: number, d = 12) =>
  Math.min(prog(f, inAt, inAt + d, EASE_IN_OUT), 1 - prog(f, outAt - d, outAt, EASE_IN_OUT));

/** Gentle spring starting at frame `at`. */
export const pop = (f: number, at: number, damping = 16, mass = 0.9) =>
  spring({ frame: f - at, fps: FPS, config: { damping, mass, stiffness: 140 } });

/** Text entrance: rise, unblur, fade. Returns CSS for a word that starts at frame `at`. */
export const rise = (f: number, at: number, dur = 20, dist = 26): React.CSSProperties => {
  const t = prog(f, at, at + dur);
  return {
    opacity: t,
    transform: `translateY(${(1 - t) * dist}px)`,
    filter: t < 1 ? `blur(${(1 - t) * 10}px)` : undefined,
  };
};

/** Text exit: drift up, blur, fade. */
export const sink = (f: number, at: number, dur = 14, dist = 18): React.CSSProperties => {
  const t = prog(f, at, at + dur, EASE_IN);
  if (t <= 0) return {};
  return {
    opacity: 1 - t,
    transform: `translateY(${-t * dist}px)`,
    filter: `blur(${t * 8}px)`,
  };
};

/** Deterministic pseudo random in [0, 1) for index i and a salt. */
export const rnd = (i: number, salt = 0) => {
  const x = Math.sin(i * 127.1 + salt * 311.7) * 43758.5453;
  return x - Math.floor(x);
};
