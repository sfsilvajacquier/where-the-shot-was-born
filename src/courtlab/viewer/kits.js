// The clubs' classic home kits, written by hand from public knowledge (SkillCorner's data carries team names only), and their crests
// (assets/crests/, the clubs' own trademarks, shown to identify them; not covered by this repository's licence). The kit dresses the
// figures (figures.js draws the cloth from the flat prints below) and tints the pucks' rings; the crest sits in the headers, on Home
// rows and on the chest. A club that is not listed gets the neutral kit. The cut of every garment is the same; only the print changes,
// and the print is a template in the club's colours (stripes for the clubs that wear them), not the real design of any season.

const KITS = [
  { key: 'breogan', name: 'Breogán', initials: 'BRE', primary: '#6fb7e9', secondary: '#ffffff' },
  { key: 'zaragoza', name: 'Zaragoza', initials: 'ZAR', primary: '#d9262c', secondary: '#ffffff' },
  { key: 'barcelona', name: 'Barcelona', initials: 'BAR', primary: '#a50044', secondary: '#004d98', stripes: true, shorts: '#004d98' },
  { key: 'gran canaria', name: 'Gran Canaria', initials: 'GCA', primary: '#f5c400', secondary: '#10305e' },
  { key: 'real madrid', name: 'Real Madrid', initials: 'RMB', primary: '#f4f4f4', secondary: '#c9a227', style: 'plain' },
  { key: 'tenerife', name: 'Tenerife', initials: 'TEN', primary: '#151515', secondary: '#f2c200' },
  { key: 'malaga', name: 'Unicaja', initials: 'UNI', primary: '#1c9e4b', secondary: '#ffffff' },
  { key: 'valencia', name: 'Valencia', initials: 'VAL', primary: '#f26a1b', secondary: '#151515' },
  { key: 'andorra', name: 'Andorra', initials: 'AND', primary: '#4fa3e0', secondary: '#f5c400' },
  { key: 'bilbao', name: 'Bilbao', initials: 'BIL', primary: '#151515', secondary: '#d8202a' },
  { key: 'baskonia', name: 'Baskonia', initials: 'BKN', primary: '#003a8c', secondary: '#c8102e', stripes: true },
  { key: 'girona', name: 'Girona', initials: 'GIR', primary: '#d71920', secondary: '#ffffff' },
  { key: 'burgos', name: 'Burgos', initials: 'BUR', primary: '#1f4fa3', secondary: '#ffffff' },
  { key: 'murcia', name: 'Murcia', initials: 'MUR', primary: '#a6192e', secondary: '#1f4fa3' },
  { key: 'joventut', name: 'Joventut', initials: 'JOV', primary: '#00843d', secondary: '#151515', stripes: true },
  { key: 'manresa', name: 'Manresa', initials: 'MAN', primary: '#d71f26', secondary: '#ffffff' },
  { key: 'granada', name: 'Granada', initials: 'GRA', primary: '#d71920', secondary: '#151515' },
];
const NEUTRAL = { key: '', name: '', initials: '', primary: '#8b98ae', secondary: '#f4f7fb' };
// Not a club: the floor Home stands on. The landing screen belongs to the project and the data behind it, so it wears SkillCorner's
// green and their mark at centre, rather than borrowing whichever club happens to host the featured play. Every other screen is a
// real match and keeps the home club's floor. The green is sampled from their own mark (assets/skillcorner.png), not guessed; its
// luminance lands at 0.788, just under the 0.8 at which floorColour() falls back to `secondary`, so both are the same green and the
// floor stays green whichever branch it takes. SkillCorner's mark is their trademark, shown to credit the data (see LICENSE.md).
export const SKILLCORNER = { key: 'skillcorner', name: 'SkillCorner', initials: 'SC', primary: '#33ff6b', secondary: '#33ff6b', floorBase: '#05110a', lineColour: 0x0a1410 };

/** The kit of a team, from any of the names SkillCorner uses for it. */
export function kitOf(teamName) {
  const n = (teamName || '').toLowerCase();
  return KITS.find((k) => n.includes(k.key)) || NEUTRAL;
}

export const lum = (hex) => { const v = parseInt(hex.slice(1), 16); return (0.2126 * (v >> 16) + 0.7152 * ((v >> 8) & 255) + 0.0722 * (v & 255)) / 255; };

/** The colour a club paints its floor with: its first colour, or its second when the first is near white. */
export function floorColour(kit) { return kit.key ? (lum(kit.primary) > 0.8 ? kit.secondary : kit.primary) : null; }

/** The ink that reads on a colour: dark on a light kit, light on a dark one. */
export function inkOn(hex) { return lum(hex) > 0.55 ? '#0b1220' : '#f4f7fb'; }

const crests = new Map();  // one image per club, loaded once and shared

/** The club's crest as an image, or null for a club without one; `onLoad` fires once it can be drawn (at once if it already can). */
export function crestImage(kit, onLoad) {
  if (!kit.key) return null;
  let img = crests.get(kit.key);
  if (!img) { img = new Image(); img.src = `assets/crests/${kit.key.replace(' ', '-')}.png`; crests.set(kit.key, img); }
  if (img.complete && img.naturalWidth) onLoad(img); else img.addEventListener('load', () => onLoad(img), { once: true });
  return img;
}

/** The badge: the club's crest, drawn on `cv` at its own size; the monogram in the kit's colours stands in until it loads. */
export function badge(cv, kit) {
  const c = cv.getContext('2d'), s = cv.width, r = s / 2;
  c.clearRect(0, 0, s, s);
  c.beginPath(); c.arc(r, r, r - 1, 0, Math.PI * 2); c.fillStyle = kit.primary; c.fill();
  c.lineWidth = Math.max(2, s * 0.06); c.strokeStyle = kit.secondary; c.stroke();
  c.fillStyle = inkOn(kit.primary); c.font = `800 ${Math.round(s * 0.34)}px Inter`; c.textAlign = 'center'; c.textBaseline = 'middle';
  c.fillText(kit.initials, r, r + s * 0.02);
  crestImage(kit, (img) => {
    c.clearRect(0, 0, s, s);
    const k = Math.min(s / img.width, s / img.height);
    c.drawImage(img, r - (img.width * k) / 2, r - (img.height * k) / 2, img.width * k, img.height * k);
  });
}

// The prints. Both are flat drawings wrapped around the body by figures.js: u runs around the player from his left side (0) over his
// back (0.25), his right side (0.5) and his chest (0.75); v runs up the garment, 0 at its hem and 1 at its top. The cut of the cloth
// (neckline, armholes, hems) and the piping along it are not drawn here: they are geometry, so they stay sharp.

const W = 1024;

function shade(c, X, Y, W, H) {  // soft shadow where cloth folds or meets the body: multiplied over the print
  c.globalCompositeOperation = 'multiply';
  return { spot: (u, v, ru, rv, a) => { c.save(); c.translate(X(u), Y(v)); c.scale(1, rv / ru); const g = c.createRadialGradient(0, 0, 0, 0, 0, X(ru)); g.addColorStop(0, `rgba(0,0,0,${a})`); g.addColorStop(1, 'rgba(0,0,0,0)'); c.fillStyle = g; c.fillRect(-X(ru), -X(ru), 2 * X(ru), 2 * X(ru)); c.restore(); },
    band: (v0, v1, a0, a1) => { const g = c.createLinearGradient(0, Y(v0), 0, Y(v1)); g.addColorStop(0, `rgba(0,0,0,${a0})`); g.addColorStop(1, `rgba(0,0,0,${a1})`); c.fillStyle = g; c.fillRect(0, Math.min(Y(v0), Y(v1)), W, Math.abs(Y(v1) - Y(v0))); },
    done: () => { c.globalCompositeOperation = 'source-over'; } };
}

function creases(c, X, Y, v0, v1, n, seed) {  // a few soft folds, lit on one side and shaded on the other
  let a = seed;
  const rnd = () => { a = (a * 16807) % 2147483647; return a / 2147483647; };
  for (let k = 0; k < n; k += 1) {
    const u = rnd(), v = v0 + rnd() * (v1 - v0), len = 0.05 + rnd() * 0.08, tilt = (rnd() - 0.5) * 0.6;
    for (const [dx, col] of [[-2, 'rgba(255,255,255,0.05)'], [2, 'rgba(0,0,0,0.09)']]) {
      c.strokeStyle = col; c.lineWidth = 6; c.lineCap = 'round';
      c.beginPath(); c.moveTo(X(u) + dx, Y(v)); c.lineTo(X(u + tilt * len) + dx, Y(v + len)); c.stroke();
    }
  }
}

/** The jersey's print: the club's colours, side panels or stripes, the number on the back and the chest, the crest on the left chest. */
export function jerseyCanvas(kit, number, crest = null) {
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = 768;
  const c = cv.getContext('2d'), H = cv.height;
  const X = (u) => u * W, Y = (v) => (1 - v) * H;
  c.fillStyle = kit.primary; c.fillRect(0, 0, W, H);
  if (kit.stripes) {  // vertical stripes, one centred on the chest and one on the back
    const period = 0.1;
    c.fillStyle = kit.secondary;
    for (let k = -6; k <= 6; k += 2) c.fillRect(X(0.75 + k * period - period / 4), 0, X(period / 2), H);
  } else if (kit.style !== 'plain') {  // side panels below the armholes
    c.fillStyle = kit.secondary;
    for (const u of [0, 0.5, 1]) c.fillRect(X(u - 0.05), Y(0.5), X(0.1), Y(0) - Y(0.5));
  }
  const ink = inkOn(kit.primary), outline = Math.abs(lum(kit.secondary) - lum(ink)) > 0.35 ? kit.secondary : null;
  const glyph = (u, v, h) => {
    c.font = `800 ${h}px Inter`; c.textAlign = 'center'; c.textBaseline = 'middle'; c.lineJoin = 'round';
    if (outline) { c.lineWidth = h * 0.09; c.strokeStyle = outline; c.strokeText(number, X(u), Y(v)); }
    c.fillStyle = ink; c.fillText(number, X(u), Y(v));
  };
  glyph(0.25, 0.58, 260); glyph(0.75, 0.53, 100);
  if (crest) { const h = 96, k = h / Math.max(crest.width, crest.height); c.drawImage(crest, X(0.855) - (crest.width * k) / 2, Y(0.68) - (crest.height * k) / 2, crest.width * k, crest.height * k); }
  const sh = shade(c, X, Y, W, H);
  for (const u of [0, 0.5, 1]) sh.spot(u, 0.62, 0.11, 0.2, 0.42);  // the armpits
  sh.band(0.2, 0, 0, 0.32);  // towards the waist, where it tucks in
  sh.done();
  creases(c, X, Y, 0.04, 0.3, 14, 5);
  return cv;
}

/** The shorts' print: the club's colour, a waistband, a stripe down each outer side and a trim at the hem. */
export function shortsCanvas(kit) {
  const cv = document.createElement('canvas');
  cv.width = W; cv.height = 512;
  const c = cv.getContext('2d'), H = cv.height;
  const X = (u) => u * W, Y = (v) => (1 - v) * H;
  const base = kit.shorts || kit.primary;
  c.fillStyle = base; c.fillRect(0, 0, W, H);
  c.fillStyle = kit.secondary;
  for (const u of [0, 1]) c.fillRect(X(u - 0.028), 0, X(0.056), H);  // the outer side of each leg (the print is mirrored on the right leg)
  c.fillRect(0, Y(0.045), W, Y(0) - Y(0.045));  // hem trim
  c.fillStyle = 'rgba(0,0,0,0.28)'; c.fillRect(0, Y(1), W, Y(0.9) - Y(1));  // the waistband, a shade darker
  c.fillStyle = 'rgba(255,255,255,0.22)'; c.fillRect(0, Y(0.905), W, 3);
  const sh = shade(c, X, Y, W, H);
  sh.band(0.9, 0.7, 0.3, 0);  // under the waistband
  sh.spot(0.5, 0.75, 0.13, 0.28, 0.45);  // between the legs
  sh.done();
  creases(c, X, Y, 0.08, 0.5, 8, 11);
  return cv;
}

/** The cloth's weave, a fine mesh as a bump map, tiled; the same for every kit. */
export function clothBump() {
  const cv = document.createElement('canvas');
  cv.width = cv.height = 256;
  const c = cv.getContext('2d');
  c.fillStyle = '#808080'; c.fillRect(0, 0, 256, 256);
  c.fillStyle = '#5c5c5c';
  for (let y = 0; y < 256; y += 8) for (let x = 0; x < 256; x += 8) { c.beginPath(); c.arc(x + 4, y + 4, 2.2, 0, Math.PI * 2); c.fill(); }
  return cv;
}
