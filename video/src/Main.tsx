import { Audio } from "@remotion/media";
import React from "react";
import { AbsoluteFill, Sequence, staticFile, useCurrentFrame } from "remotion";
import { Space } from "./components/Space";
import { prog } from "./lib/anim";
import { CUT, DROP, DURATION, beat } from "./lib/time";
import { AnyWindow } from "./scenes/AnyWindow";
import { AGENT_EVENTS, Claude, T } from "./scenes/Claude";
import { BUSY_ON, Dictation, REC_ON } from "./scenes/Dictation";
import { Intro } from "./scenes/Intro";
import { Outro } from "./scenes/Outro";
import { Privacy } from "./scenes/Privacy";
import { Tease, warpAt } from "./scenes/Tease";

// the bubble chimes of the app; the music dips a little under them
const CHIMES: [number, string][] = [
  [T.done, "done"],
  [T.waiting, "waiting"],
  [T.read + 4, "info"],
];
const duck = (fr: number) =>
  CHIMES.reduce((v, [at]) => v * (1 - 0.28 * prog(fr, at - 3, at + 2) * (1 - prog(fr, at + 22, at + 34))), 1);

const Sfx: React.FC<{ at: number; file: string; volume?: number }> = ({ at, file, volume = 0.5 }) => (
  <Sequence from={at} durationInFrames={45} layout="none">
    <Audio src={staticFile(`sfx/${file}.wav`)} volume={volume} />
  </Sequence>
);

export const Main: React.FC = () => {
  const f = useCurrentFrame();
  const { warp, travel } = warpAt(f);
  // after the drop the stars breathe with the kick, until the drums stop
  const sinceBeat = f >= DROP && f < CUT ? (f - DROP) % beat(1) : 99;
  const pulse = Math.exp(-sinceBeat / 5) * 0.5;
  const flash = f >= DROP ? Math.exp(-(f - DROP) / 7) * (1 - prog(f, DROP + 30, DROP + 40)) : 0;

  return (
    <AbsoluteFill style={{ background: "#060912" }}>
      <Space warp={warp} travel={travel} pulse={pulse} drift={f / DURATION} />
      <Intro />
      <Dictation />
      <AnyWindow />
      <Privacy />
      <Tease />
      <Claude />
      <Outro />
      {flash > 0.01 ? (
        <AbsoluteFill
          style={{
            background: "radial-gradient(circle at 1400px 700px, rgba(210,226,255,.6), rgba(91,157,255,.28) 30%, rgba(6,9,18,0) 62%)",
            opacity: flash,
          }}
        />
      ) : null}

      <Audio
        src={staticFile("audio/music.wav")}
        volume={(fr) => duck(fr) * (1 - prog(fr, DURATION - 80, DURATION - 2))}
      />
      <Sfx at={REC_ON} file="start" volume={0.45} />
      <Sfx at={BUSY_ON} file="stop" volume={0.45} />
      {CHIMES.map(([at, file]) => (
        <Sfx key={at} at={at} file={file} volume={1} />
      ))}
      {AGENT_EVENTS.listen.map((at) => (
        <Sfx key={`l${at}`} at={at} file="start" volume={0.66} />
      ))}
      {AGENT_EVENTS.stop.map((at) => (
        <Sfx key={`s${at}`} at={at} file="stop" volume={0.66} />
      ))}
    </AbsoluteFill>
  );
};
