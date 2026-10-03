// The whole video is cut to the music: "Mountains" at 122.92 BPM, video second 0 = a downbeat.
// One bar = 4 beats = 1.95248 s. Phrases are 8 bars; the bass drops in at bar 16 (a beat early, at 30.85 s)
// and the drums stop at bar 32, where the soundtrack jumps to the track's closing pad.

export const FPS = 30;
export const BEAT_S = 0.48812;
export const BAR_S = 4 * BEAT_S;

/** Frame of bar n (fractions allowed: bar(4.5) = two beats into bar 4). */
export const bar = (n: number) => Math.round(n * BAR_S * FPS);
/** Frame of beat n. */
export const beat = (n: number) => Math.round(n * BEAT_S * FPS);
/** Frames for a number of seconds. */
export const sec = (s: number) => Math.round(s * FPS);

export const DROP = Math.round(30.85 * FPS); // the bass enters
export const CUT = bar(32); // drums stop, the closing pad starts
export const DURATION = sec(76);
