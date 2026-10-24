// The whole video is cut to the music: "Mountains" at 122.92 BPM, video second 0 = a downbeat (the track's beat 17,
// the second half of its soft intro). One bar = 4 beats = 1.95248 s. Phrases are 8 bars and start at bars 4, 12, 20,
// 28, 36, 44 and 52; the bass drops in at bar 20 (a beat early, at 38.66 s) and the drums stop at bar 52, where the
// soundtrack jumps to the track's closing pad (capture/build_music.py). Until 24 Oct 2026 they stopped at bar 44:
// the phrase 44–52 is the transcript check.

export const FPS = 30;
export const BEAT_S = 0.48812;
export const BAR_S = 4 * BEAT_S;

/** Frame of bar n (fractions allowed: bar(4.5) = two beats into bar 4). */
export const bar = (n: number) => Math.round(n * BAR_S * FPS);
/** Frame of beat n. */
export const beat = (n: number) => Math.round(n * BEAT_S * FPS);
/** Frames for a number of seconds. */
export const sec = (s: number) => Math.round(s * FPS);

export const DROP = Math.round(38.66 * FPS); // the bass enters
export const CUT_BAR = 52;
export const CUT = bar(CUT_BAR); // drums stop, the closing pad starts
export const DURATION = CUT + sec(13.53);
