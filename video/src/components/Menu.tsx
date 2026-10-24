import React from "react";
import { C, ICONS, UI_VAR } from "../lib/theme";
import { GLYPHS } from "./OrbitWidget";

// Replica of the + menu above the panel (app/main.py _fill_favorites: ui.FolderMenu with ui.ModelPicker at the top),
// in the app's QMenu style (theme.py), checked against capture/grab.py's menu-new.png. 406 x 234 logical px.

export const MENU = { w: 406, h: 234 };
export const MODELS = ["Fable 5.1", "Opus 5.5", "Sonnet 5.5", "Haiku 5.5"];
export const FOLDERS: [string, string][] = [
  ["eshop", "#F28C38"],
  ["faktury", "#3DD68C"],
  ["web", "#5B9DFF"],
];
const LINE = "#2A3550";
const TEXT = "#E7ECF5";
const DIM = "#8B96AD";
const ITEM_H = 29;
const TOP = 7; // the menu's padding and border

/** Where things are, from the menu's top left: a model's segment centre, a folder item's centre. */
export const menuSpot = {
  model: (i: number) => ({ x: 63 + i * 82 + 39, y: 53 }),
  folder: (i: number) => ({ x: 120, y: TOP + ITEM_H + 34 + ITEM_H * i + ITEM_H / 2 }),
};

export const NewSessionMenu: React.FC<{
  /** The model picked (index into MODELS); hover: the segment under the mouse. */
  model: number;
  modelHover?: number;
  /** The folder item under the mouse (-1: none) and how lit (0..1). */
  hover?: number;
  hoverLight?: number;
  accent?: string;
}> = ({ model, modelHover = -1, hover = -1, hoverLight = 1, accent = C.accent }) => {
  let y = TOP;
  const item = (key: string, content: React.ReactNode, lit = 0) => {
    const top = y;
    y += ITEM_H;
    return (
      <div key={key} style={{ position: "absolute", left: 7, right: 7, top, height: ITEM_H }}>
        {lit > 0 ? <div style={{ position: "absolute", inset: 0, borderRadius: 5, background: "#24365A", opacity: lit }} /> : null}
        {content}
      </div>
    );
  };
  const text = (t: string, color = TEXT) => (
    <span style={{ position: "absolute", left: 32, top: 0, lineHeight: `${ITEM_H}px`, color, opacity: 0.999 }}>{t}</span>
  );
  const rows: React.ReactNode[] = [];
  rows.push(item("head", text("Nová relace Claude Code ve složce", DIM)));
  const pickerTop = y;
  y += 34;
  FOLDERS.forEach(([name, color], i) =>
    rows.push(
      item(
        name,
        <>
          <div style={{ position: "absolute", left: 2, top: ITEM_H / 2 - 6, width: 12, height: 12, borderRadius: "50%", background: color }} />
          {text(name)}
        </>,
        i === hover ? hoverLight : 0,
      ),
    ),
  );
  const sepTop = y;
  y += 11;
  rows.push(
    item(
      "repo",
      <>
        <span style={{ position: "absolute", left: 0, width: 16, top: 0, lineHeight: `${ITEM_H}px`, textAlign: "center", fontFamily: ICONS, fontSize: 13, color: DIM, opacity: 0.999 }}>
          {GLYPHS.add}
        </span>
        {text("Nové repo…")}
      </>,
    ),
  );
  rows.push(
    item(
      "choose",
      <>
        <span style={{ position: "absolute", left: 0, width: 16, top: 0, lineHeight: `${ITEM_H}px`, textAlign: "center", fontFamily: ICONS, fontSize: 13, color: DIM, opacity: 0.999 }}>
          {String.fromCharCode(0xe762)}
        </span>
        {text("Vybrat složky a barvy…")}
      </>,
    ),
  );
  return (
    <div
      style={{
        position: "relative",
        width: MENU.w,
        height: MENU.h,
        borderRadius: 8,
        background: "#161D2C",
        boxShadow: `inset 0 0 0 1px ${LINE}, 0 10px 30px rgba(0,0,0,.45)`,
        fontFamily: UI_VAR,
        fontSize: 13,
        color: TEXT,
      }}
    >
      {rows}
      <div style={{ position: "absolute", left: 7, top: pickerTop, width: MENU.w - 14, height: 34 }}>
        <span style={{ position: "absolute", left: 12, top: 0, lineHeight: "34px", fontSize: 12, color: DIM, opacity: 0.999 }}>Model</span>
        {MODELS.map((m, i) => {
          const picked = i === model;
          const hov = i === modelHover;
          return (
            <div
              key={m}
              style={{
                position: "absolute",
                left: 56 + i * 82,
                top: 6,
                width: 78,
                height: 22,
                borderRadius: 6,
                boxSizing: "border-box",
                border: `1px solid ${picked ? accent : LINE}`,
                background: picked ? `${accent}46` : hov ? `${accent}1c` : "transparent",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 12,
                fontWeight: picked ? 700 : 400,
                color: picked || hov ? TEXT : DIM,
              }}
            >
              <span style={{ opacity: 0.999 }}>{m}</span>
            </div>
          );
        })}
      </div>
      <div style={{ position: "absolute", left: 13, right: 13, top: sepTop + 5, height: 1, background: LINE }} />
    </div>
  );
};
