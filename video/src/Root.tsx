import React from "react";
import { Composition } from "remotion";
import { fontsLoaded } from "./lib/fonts";
import { DURATION, FPS } from "./lib/time";
import { Main } from "./Main";
import { FoldTest, PartsTest, WidgetTest } from "./WidgetTest";

void fontsLoaded;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition id="Orbit" component={Main} durationInFrames={DURATION} fps={FPS} width={1920} height={1080} />
      <Composition id="WidgetTest" component={WidgetTest} durationInFrames={1} fps={FPS} width={1920} height={1080} />
      <Composition id="PartsTest" component={PartsTest} durationInFrames={1} fps={FPS} width={1920} height={1080} />
      <Composition id="FoldTest" component={FoldTest} durationInFrames={11} fps={FPS} width={1156} height={828} defaultProps={{ folding: true }} />
      <Composition id="UnfoldTest" component={FoldTest} durationInFrames={11} fps={FPS} width={1156} height={828} defaultProps={{ folding: false }} />
    </>
  );
};
