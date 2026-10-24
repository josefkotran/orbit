"""Cuts the soundtrack from "Mountains" (Andrew Ev, Mixkit Stock Music Free License).

Video second 0 = the track's beat #17 (the second half of its soft intro, 8.49 s), so the hyperspace arrival is
quiet and the build starts with the dictation (beat #33, video bar 4). The bass comes in at beat #97 (video bar 20,
the drop). At beat #225 (a phrase start, 101.53 s into the video) it jumps to the moment the track's drums stop
(251.88 s): the bass line repeats every phrase (8 bars) and its note is the same on both sides, so the groove simply
ends there and the closing pad rings out – the ending of the video. (Until 24 Oct 2026 the jump was at beat #193:
the phrase between is the transcript check. Bass and kick of beats #193–225 follow the phrase before them, the bass
envelope of #225 matches #193's at r = 0.83, and the hi-hats only grow a little: no break in between.)

Grid (measured): beat k at 0.1928 + k * 0.48812 s (122.92 BPM), downbeats at k = 1 (mod 4), phrases every 32 beats.
The ending is not on that grid: cross-correlating kicks and bass notes puts body time t at t + 173.100 s there for
t = beat #161; phrases later (#193, #225) the groove is the same, so it jumps to the same spot of the ending.

Run: python video/capture/build_music.py <mountains.mp3> video/public/audio/music.wav
(numpy and scipy; the mp3 is decoded by the ffmpeg that comes with Remotion, in video/node_modules)
"""
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

P, B0 = 0.48812, 0.1928
START, CUT_FROM = 17, 225
ENDING_AT = B0 + 161 * P + 173.100  # where the drums stop (251.88 s)
SR = 48000
FFMPEG = Path(__file__).resolve().parents[1] / "node_modules" / "@remotion" / "compositor-win32-x64-msvc" / "ffmpeg.exe"

src, out = sys.argv[1], sys.argv[2]
with tempfile.TemporaryDirectory() as tmp:
    wav = Path(tmp) / "track.wav"
    subprocess.run([str(FFMPEG), "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-ar", str(SR), "-ac", "2",
                    "-c:a", "pcm_s16le", str(wav)], check=True)
    _, y = wavfile.read(wav)
y = y.T.astype(np.float64) / 32768  # (2, n)

t_start = B0 + START * P
t_from = B0 + CUT_FROM * P
t_to = ENDING_AT
print(f"start {t_start:.4f}  cut {t_from:.4f} -> {t_to:.4f}")

lead = 0.015  # cut just before the downbeat, so its attack comes whole from the ending
xf = int(0.06 * SR)  # equal-power crossfade ending at the cut
i_from, i_to = int((t_from - lead) * SR), int((t_to - lead) * SR)
a = y[:, int(t_start * SR):i_from]
b = y[:, i_to:]
fade = np.linspace(0, np.pi / 2, xf)
mix = a[:, -xf:] * np.cos(fade) + y[:, i_to - xf:i_to] * np.sin(fade)
joined = np.concatenate([a[:, :-xf], mix, b], axis=1)

fade_in = int(0.12 * SR)
joined[:, :fade_in] *= np.linspace(0, 1, fade_in) ** 2
peak = np.abs(joined).max()
joined *= min(1.0, 0.89 / peak)  # -1 dBFS: about -1 dBTP and -14 LUFS once mixed with the chimes
wavfile.write(out, SR, (np.clip(joined.T, -1, 1) * 32767).astype(np.int16))
cut_video = (i_from - int(t_start * SR)) / SR + lead
print(f"cut (drums stop) at video {cut_video:.4f}s; total {joined.shape[1] / SR:.2f}s; peak was {peak:.3f}")
