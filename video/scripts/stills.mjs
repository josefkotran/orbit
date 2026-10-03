// Renders check frames of the Orbit composition: node scripts/stills.mjs 60 150 260 ...  (scale 0.5, out/stills)
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import path from "node:path";
import fs from "node:fs";

const frames = process.argv.slice(2).map(Number);
const scale = Number(process.env.SCALE ?? 0.5);
const outDir = path.resolve("out/stills");
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const composition = await selectComposition({ serveUrl, id: "Orbit" });
for (const frame of frames) {
  const output = path.join(outDir, `f${String(frame).padStart(4, "0")}.png`);
  await renderStill({ composition, serveUrl, output, frame, scale });
  console.log(output);
}
