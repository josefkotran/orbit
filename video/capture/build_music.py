"""Cuts the soundtrack from "Mountains" (Andrew Ev, Mixkit Stock Music Free License).

Video second 0 = the track's beat #33 (a phrase start, 16.30 s). At beat #161 (a phrase start, 62.48 s into the
video) it jumps to the moment the track's drums stop (251.88 s): the bass note is the same on both sides, so the
groove simply ends there and the closing pad rings out – the ending of the video.

Grid (measured): beat k at 0.1928 + k * 0.48812 s (122.92 BPM), downbeats at k = 1 (mod 4), phrases every 32 beats.
The ending is not on that grid: cross-correlating kicks and bass notes puts body time t at t + 173.100 s there.

Run: <python with librosa + soundfile> video/capture/build_music.py <mountains.mp3> video/public/audio/music.wav
"""
import sys

import librosa
import numpy as np
import soundfile as sf

P, B0 = 0.48812, 0.1928
START, CUT_FROM = 33, 161
ENDING_OFFSET = 173.100  # body time + this = the same spot of the groove in the ending
SR = 48000

src, out = sys.argv[1], sys.argv[2]
y, _ = librosa.load(src, sr=SR, mono=False)  # (2, n)


t_start = B0 + START * P
t_from = B0 + CUT_FROM * P
t_to = t_from + ENDING_OFFSET
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
joined *= min(1.0, 0.94 / peak)
sf.write(out, joined.T, SR, subtype="PCM_16")
cut_video = (i_from - int(t_start * SR)) / SR + lead
print(f"cut (drums stop) at video {cut_video:.4f}s; total {joined.shape[1] / SR:.2f}s; "
      f"peak was {peak:.3f}")
