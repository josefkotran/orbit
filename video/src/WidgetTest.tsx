import React, { useMemo } from "react";
import { AbsoluteFill, Img, staticFile, useCurrentFrame } from "remotion";
import { Bubble } from "./components/Bubble";
import { FoldFx } from "./components/FoldFx";
import { MODELS, NewSessionMenu } from "./components/Menu";
import { OrbitIcon, OrbitWidget, panelHeight, widgetBox, widgetShapes } from "./components/OrbitWidget";

// Dev check: the replica (left) next to the real app rendered by video/capture/grab.py (right), both at 2x.
const SESSIONS = [
  { name: "Překlad katalogu z němčiny", folder: "eshop", color: "#F28C38", state: "working" as const, context: 0.34 },
  { name: "Oprava exportu faktur", folder: "faktury", color: "#3DD68C", state: "waiting" as const, context: 0.12 },
  { name: "Nová úvodní stránka", folder: "web", color: "#5B9DFF", state: "done" as const, context: 0.57, model: "Sonnet 5.5" },
];
const LIMITS = [
  { label: "5 h", percent: 42 },
  { label: "Týden", percent: 63 },
  { label: "Fable", percent: 28 },
];

export const WidgetTest: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#0B0F1A" }}>
      <div style={{ position: "absolute", left: 20, top: 20, transform: "scale(2)", transformOrigin: "0 0" }}>
        <OrbitWidget
          limits={LIMITS}
          sessions={SESSIONS}
          notes={2}
          header={{ rest: "limit 5 h se obnoví v 21:46 (za 2 h 13 min)", refresh: true }}
          version={{ state: "current", installed: "2.1.304" }}
        />
      </div>
      <Img src={staticFile("screens/panel.png")} style={{ position: "absolute", left: 960, top: 20, width: 900 }} />
      <div style={{ position: "absolute", left: 20, top: 640, transform: "scale(2)", transformOrigin: "0 0" }}>
        <NewSessionMenu model={1} />
      </div>
      <Img src={staticFile("screens/menu-new.png")} style={{ position: "absolute", left: 960, top: 640, width: 812 }} />
    </AbsoluteFill>
  );
};

export const PartsTest: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#0B0F1A" }}>
      <div style={{ position: "absolute", left: 20, top: 20, transform: "scale(4)", transformOrigin: "0 0" }}>
        <div style={{ position: "relative", width: 72, height: 72 }}>
          <div style={{ position: "absolute", left: 36, top: 36 }}>
            <OrbitIcon />
          </div>
        </div>
      </div>
      <Img src={staticFile("screens/icon.png")} style={{ position: "absolute", left: 340, top: 20, width: 288 }} />
      <div style={{ position: "absolute", left: 20, top: 340, transform: "scale(2)", transformOrigin: "0 0" }}>
        <Bubble kind="done" title="Nová úvodní stránka" note="hotovo" lines={["Stránka je hotová a nasazená. Přidal jsem i video", "do horní části."]} tailY={30} />
      </div>
      <Img src={staticFile("screens/bubble-done.png")} style={{ position: "absolute", left: 960, top: 320, width: 708 }} />
      <div style={{ position: "absolute", left: 20, top: 600, fontFamily: "Segoe UI", color: "#fff", fontSize: 20 }}>{MODELS.join(" · ")}</div>
    </AbsoluteFill>
  );
};

/** The fold animation of the panel above, like video/out/fold-ref/*.png from the app (frame k = u k/10). */
export const FoldTest: React.FC<{ folding: boolean }> = ({ folding }) => {
  const frame = useCurrentFrame();
  const u = Math.min(1, frame / 10);
  const ph = panelHeight(3, 3, null);
  const box = widgetBox(ph);
  const shapes = useMemo(() => widgetShapes(ph), [ph]);
  return (
    <AbsoluteFill style={{ background: "#000" }}>
      <div style={{ position: "absolute", left: 64 * 2, top: 64 * 2, transform: "scale(2)", transformOrigin: "0 0" }}>
        <FoldFx
          u={u}
          folding={folding}
          w={box.w}
          h={box.h}
          c={box.mic}
          shapes={shapes}
          picture={(shimmer) => (
            <OrbitWidget limits={LIMITS} sessions={SESSIONS} notes={2} shimmer={shimmer} header={{ rest: "limit 5 h se obnoví v 21:46 (za 2 h 13 min)", refresh: true }} version={{ state: "current", installed: "2.1.304" }} />
          )}
        />
      </div>
    </AbsoluteFill>
  );
};
