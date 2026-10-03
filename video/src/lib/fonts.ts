import { loadFont } from "@remotion/fonts";
import { staticFile } from "remotion";

// The website's own font files (web/site/assets/fonts): Anybody (variable width 50–150 %, weight 100–900) for
// headlines and things said aloud, Mona Sans for text. Split into latin and latin-ext like Google serves them.
const LATIN =
  "U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC," +
  "U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD";
const LATIN_EXT =
  "U+0100-02BA,U+02BD-02C5,U+02C7-02CC,U+02CE-02D7,U+02DD-02FF,U+0304,U+0308,U+0329,U+1D00-1DBF,U+1E00-1E9F," +
  "U+1EF2-1EFF,U+2020,U+20A0-20AB,U+20AD-20C0,U+2113,U+2C60-2C7F,U+A720-A7FF";

const faces = [
  { family: "Anybody", file: "anybody-normal", weight: "100 900", stretch: "50% 150%", style: "normal" },
  { family: "Anybody", file: "anybody-italic", weight: "100 900", stretch: "50% 150%", style: "italic" },
  { family: "Mona Sans", file: "mona-sans-normal", weight: "200 900", stretch: "75% 125%", style: "normal" },
];

export const fontsLoaded = Promise.all(
  faces.flatMap((f) =>
    [
      [`${f.file}-latin.woff2`, LATIN],
      [`${f.file}-latin-ext.woff2`, LATIN_EXT],
    ].map(([file, range]) =>
      loadFont({
        family: f.family,
        url: staticFile(`fonts/${file}`),
        weight: f.weight,
        stretch: f.stretch,
        style: f.style,
        unicodeRange: range,
      }),
    ),
  ),
);
