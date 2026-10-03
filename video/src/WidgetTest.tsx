import React from "react";
import { AbsoluteFill, Img, staticFile } from "remotion";
import { Bubble } from "./components/Bubble";
import { OrbitWidget } from "./components/OrbitWidget";

// Dev check: the replica (left) next to the real app rendered by video/capture/grab.py (right), both at 2x.
export const WidgetTest: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: "#0B0F1A" }}>
      <div style={{ position: "absolute", left: 20, top: 20, transform: "scale(2)", transformOrigin: "0 0" }}>
        <OrbitWidget
          limits={[
            { label: "5 h", percent: 42 },
            { label: "Týden", percent: 63 },
            { label: "Fable", percent: 28 },
          ]}
          sessions={[
            { name: "Překlad katalogu z němčiny", folder: "eshop", state: "working", context: 0.34 },
            { name: "Oprava exportu faktur", folder: "faktury", state: "waiting", context: 0.12 },
            { name: "Nová úvodní stránka", folder: "web", state: "done", context: 0.57 },
          ]}
          feed={{
            status: "",
            rows: [
              { kind: "you", text: "Co dělá relace s katalogem?" },
              { kind: "reply", text: "Překládá katalog z němčiny, má hotovou zhruba polovinu stránek." },
              { kind: "target", name: "Překlad katalogu z němčiny", folder: "eshop", label: "odesláno ✓", color: "#3DD68C" },
              { kind: "message", text: "Ceny v katalogu rovnou převeď na koruny." },
            ],
          }}
        />
      </div>
      <Img src={staticFile("screens/panel-agent.png")} style={{ position: "absolute", left: 960, top: 20, width: 900 }} />
      <div style={{ position: "absolute", left: 20, top: 760, transform: "scale(2)", transformOrigin: "0 0" }}>
        <Bubble kind="done" title="Nová úvodní stránka" note="hotovo" lines={["Stránka je hotová a nasazená. Přidal jsem i video", "do horní části."]} tailY={30} />
      </div>
      <Img src={staticFile("screens/bubble-done.png")} style={{ position: "absolute", left: 960, top: 740, width: 708 }} />
    </AbsoluteFill>
  );
};
