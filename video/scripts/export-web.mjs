// Encodes the rendered master (out/orbit-master.mp4) for the website: web/site/assets/video/
//   orbit.mp4  – H.264 High, 2-pass ~2.3 Mbit/s, AAC 160k, faststart (plays everywhere)
//   orbit.webm – VP9 2-pass ~1.9 Mbit/s, Opus 128k (smaller, for browsers that take it)
//   poster.jpg – the title frame (dark), shown before the video loads
// Run: node scripts/export-web.mjs   (uses the ffmpeg that comes with Remotion; `npx remotion ffmpeg` would go
// through cmd.exe on Windows, which mangles some arguments, so the binary is called directly)
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const master = path.resolve("out/orbit-master.mp4");
const outDir = path.resolve("../web/site/assets/video");
const POSTER_S = 5.27; // "Orbit" with its orbits, frame 158
fs.mkdirSync(outDir, { recursive: true });
const passlog = path.join(os.tmpdir(), "orbit-video-pass");

const bin = path.resolve(
  "node_modules/@remotion",
  `compositor-${process.platform === "win32" ? "win32-x64-msvc" : `${process.platform}-${process.arch}`}`,
  process.platform === "win32" ? "ffmpeg.exe" : "ffmpeg",
);
const ffmpeg = (args) => {
  console.log("ffmpeg", args.join(" "));
  execFileSync(bin, ["-hide_banner", "-loglevel", "error", "-y", ...args], { stdio: "inherit" });
};
const nul = process.platform === "win32" ? "NUL" : "/dev/null";

// Remotion's master is full-range BT.601 (JPEG frames). Chrome's hardware VP9 decoder (seen on a Radeon RX 9070 XT)
// fails on full-range VP9 with PIPELINE_ERROR_DECODE, and then it does not fall back to the MP4 source, so the video
// just stands still. Both web files are therefore converted to limited-range BT.709 and tagged so, like any normal video.
const colour = [
  "-vf", "scale=in_range=pc:out_range=tv:in_color_matrix=bt601:out_color_matrix=bt709,format=yuv420p",
  "-color_range", "tv", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
];
const x264 = [...colour, "-c:v", "libx264", "-preset", "slower", "-profile:v", "high", "-pix_fmt", "yuv420p", "-b:v", "2300k", "-maxrate", "4000k", "-bufsize", "6000k", "-g", "60"];
ffmpeg(["-i", master, ...x264, "-pass", "1", "-passlogfile", passlog, "-an", "-f", "mp4", nul]);
ffmpeg(["-i", master, ...x264, "-pass", "2", "-passlogfile", passlog, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", path.join(outDir, "orbit.mp4")]);

const vp9 = [...colour, "-c:v", "libvpx-vp9", "-b:v", "1900k", "-maxrate", "3500k", "-bufsize", "5000k", "-row-mt", "1", "-tile-columns", "2", "-g", "120", "-pix_fmt", "yuv420p"];
ffmpeg(["-i", master, ...vp9, "-pass", "1", "-passlogfile", passlog, "-deadline", "good", "-cpu-used", "4", "-an", "-f", "webm", nul]);
ffmpeg(["-i", master, ...vp9, "-pass", "2", "-passlogfile", passlog, "-deadline", "good", "-cpu-used", "1", "-c:a", "libopus", "-b:a", "128k", path.join(outDir, "orbit.webm")]);

ffmpeg(["-ss", String(POSTER_S), "-i", master, "-frames:v", "1", "-q:v", "3", path.join(outDir, "poster.jpg")]);

for (const f of ["orbit.mp4", "orbit.webm", "poster.jpg"]) {
  const size = fs.statSync(path.join(outDir, f)).size;
  console.log(`${f}: ${(size / 1024 / 1024).toFixed(2)} MB`);
}
