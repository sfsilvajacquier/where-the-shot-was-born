// One colour scale, one meaning: how far a defender is beyond his normal spot (feet).
// It reads like heated metal — steel at rest, copper, orange, amber, white-hot — so lightness rises with tension
// and the scale survives colour-blindness. Blue is the other side: tighter than normal.
// Interpolated in OKLab so equal steps in feet look like equal steps in colour.

const STOPS = [
  [-6, '#4C7BE0'],
  [0, '#93A1B5'],
  [3, '#D98A5B'],
  [6, '#FF8A3C'],
  [10, '#FFC24A'],
  [15, '#FFF1B8'],
];

const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toSrgb = (c) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function hexToOklab(hex) {
  const n = parseInt(hex.slice(1), 16);
  const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((v) => toLinear(v / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return [0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s, 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s];
}

function oklabToSrgb([L, a, b]) {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s]
    .map((v) => Math.min(1, Math.max(0, toSrgb(v))));
}

const LAB = STOPS.map(([at, hex]) => [at, hexToOklab(hex)]);

/** sRGB triplet (0–1) for a number of feet beyond the normal spot. */
export function tension(feet) {
  const x = Math.min(LAB[LAB.length - 1][0], Math.max(LAB[0][0], feet));
  let k = 1;
  while (LAB[k][0] < x) k += 1;
  const [x0, c0] = LAB[k - 1];
  const [x1, c1] = LAB[k];
  const f = (x - x0) / (x1 - x0);
  return oklabToSrgb(c0.map((v, j) => v + (c1[j] - v) * f));
}

export const css = (feet, alpha = 1) => {
  const [r, g, b] = tension(feet).map((v) => Math.round(v * 255));
  return `rgba(${r},${g},${b},${alpha})`;
};

/** 0 at rest, 1 when the band is about to snap: drives glow and thinning. */
export const heat = (feet) => Math.min(1, Math.max(0, feet / 12));

export const LEGEND = STOPS.map(([at]) => at);
