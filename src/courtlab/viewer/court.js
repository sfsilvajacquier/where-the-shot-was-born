// The floor, the painted lines and the two baskets, from the FIBA measures that come inside every possession file.
// Feet everywhere. Data (x, y) sits on the floor as three.js (x, 0, +y); height is three.js y.
// Why +y and not -y: SkillCorner's frame is a MIRROR of the real court (its y grows towards the broadcast camera, although the
// documentation says the opposite; checked against a broadcast frame of the Zaragoza three). Mapping y to +z turns the mirror
// back into a rotation, so left and right on screen are the real left and right, seen from the far sideline.
// Wood and paint are a texture; the lines are geometry, so they stay sharp at any zoom. The paint takes the home club's colour and
// its crest sits at centre court, as arenas do (a template in the club's colour, not the real floor of any arena); the hall around the
// court (boards, benches, stands) is dark decoration, so the eye stays on the floor.

import * as THREE from 'three';
import { crestImage, floorColour } from './kits.js';

export const RUNOFF_X = 10;
export const RUNOFF_Y = 8;
const LINE = 0.2; // FIBA paints 5 cm (0.16 ft); a touch wider so it survives a phone screen
const LIFT = 0.012;

export const onFloor = (x, y, h = 0) => new THREE.Vector3(x, h, y);

export function mulberry32(seed) {
  let a = seed;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** The outline of the area inside the three-point line at the -x end, as data points. */
function insideTheArc(court) {
  const [hx] = court.hoop;
  const R = court.three_radius, cy = court.three_corner_y, base = -court.length / 2;
  const t0 = Math.asin(cy / R);
  const pts = [[base, -cy]];
  for (let k = 0; k <= 96; k += 1) {
    const t = -t0 + (2 * t0 * k) / 96;
    pts.push([hx + R * Math.cos(t), R * Math.sin(t)]);
  }
  pts.push([base, cy]);
  return pts;
}

/** Two colours mixed, as a CSS rgba string. */
function blend(a, b, f, alpha = 1) {
  const A = parseInt(a.slice(1), 16), B = parseInt(b.slice(1), 16), ch = (s) => Math.round(((A >> s) & 255) + (((B >> s) & 255) - ((A >> s) & 255)) * f);
  return `rgba(${ch(16)},${ch(8)},${ch(0)},${alpha})`;
}

function woodTexture(court, anisotropy, kit) {
  const totalL = court.length + 2 * RUNOFF_X, totalW = court.width + 2 * RUNOFF_Y;
  const Wpx = 4096, px = Wpx / totalL, Hpx = Math.round(totalW * px);
  const cv = document.createElement('canvas');
  cv.width = Wpx; cv.height = Hpx;
  const c = cv.getContext('2d');
  const X = (x) => (x + totalL / 2) * px, Y = (y) => (totalW / 2 - y) * px;
  const rnd = mulberry32(7);

  // boards: 3 in wide, 4 to 8 ft long, each with its own tone
  c.fillStyle = '#7a6046';
  c.fillRect(0, 0, Wpx, Hpx);
  const board = 0.26 * px;
  for (let y = 0; y < Hpx; y += board) {
    let x = -rnd() * 8 * px;
    while (x < Wpx) {
      const len = (4 + rnd() * 4) * px;
      const l = 38 + (rnd() - 0.5) * 8, s = 27 + (rnd() - 0.5) * 9, h = 30 + (rnd() - 0.5) * 6;
      c.fillStyle = `hsl(${h} ${s}% ${l}%)`;
      c.fillRect(x, y, len, board);
      c.fillStyle = 'rgba(40,20,6,0.22)';
      c.fillRect(x + len - 1, y, 1, board);
      x += len;
    }
    c.fillStyle = 'rgba(40,20,6,0.13)';
    c.fillRect(0, y, Wpx, 1);
  }
  // grain: long faint streaks along the boards
  for (let k = 0; k < 52000; k += 1) {
    const dark = rnd() < 0.62;
    c.fillStyle = dark ? `rgba(70,36,10,${0.03 + rnd() * 0.06})` : `rgba(255,232,190,${0.02 + rnd() * 0.04})`;
    c.fillRect(rnd() * Wpx, rnd() * Hpx, 30 + rnd() * 170, 1);
  }

  const path = (pts, s) => {
    c.beginPath();
    pts.forEach(([x, y], k) => (k ? c.lineTo(X(s * x), Y(y)) : c.moveTo(X(s * x), Y(y))));
    c.closePath();
  };
  const base = -court.length / 2, [paintL, paintW] = court.paint;
  // a club paints over the arena's dark navy; a kit may name its own base instead (SKILLCORNER in kits.js paints over near-black, so
  // its green reads as green on black rather than green on navy)
  const club = kit ? floorColour(kit) : null, dark = (kit && kit.floorBase) || '#101e3a';
  const paint = club ? blend(dark, club, 0.4, 0.93) : 'rgba(16,30,58,0.93)';
  for (const s of [1, -1]) {
    // a darker stain inside the three-point line, as many courts have: the arc reads at a glance
    c.globalCompositeOperation = 'multiply';
    c.fillStyle = '#c4ad93';
    path(insideTheArc(court), s); c.fill();
    c.globalCompositeOperation = 'source-over';
    // the paint, in the home club's colour
    c.fillStyle = paint;
    path([[base, -paintW / 2], [base + paintL, -paintW / 2], [base + paintL, paintW / 2], [base, paintW / 2]], s); c.fill();
  }
  c.fillStyle = paint;
  c.beginPath(); c.arc(X(0), Y(0), court.free_throw_radius * px, 0, Math.PI * 2); c.fill();
  // the run-off around the court, a shade of the same
  c.fillStyle = club ? blend((kit && kit.floorBase) || '#0b111f', club, 0.18, 0.95) : 'rgba(11,17,31,0.95)';
  c.beginPath();
  c.rect(0, 0, Wpx, Hpx);
  c.rect(X(-court.length / 2), Y(court.width / 2), court.length * px, court.width * px);
  c.fill('evenodd');

  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = anisotropy;
  // The home crest at centre court, upright from whichever sideline the camera sits on. The canvas is NOT mirrored on its way to the
  // floor -- an earlier `c.scale(1, -1)` here, added on that belief, flipped every crest top to bottom, which on a near-symmetric
  // mark (SkillCorner's S, Real Madrid's roundel) reads as a mirror image. Measured by painting a letter R at centre court and
  // matching the render against the asset rotated, mirrored and flipped: it matched the flip. So the crest is drawn as it is, and a
  // seat on the far sideline gets a true half-turn. A floor crest reads from one side only, as it does in an arena.
  const crest = (flipped) => {
    if (!kit) return;
    crestImage(kit, (img) => {
      c.fillStyle = paint;
      c.beginPath(); c.arc(X(0), Y(0), court.free_throw_radius * px, 0, Math.PI * 2); c.fill();
      const r = court.free_throw_radius * px * 0.62, k = (2 * r) / Math.max(img.width, img.height);
      c.save(); c.translate(X(0), Y(0)); if (flipped) c.scale(-1, -1); c.globalAlpha = 0.55;
      c.drawImage(img, -(img.width * k) / 2, -(img.height * k) / 2, img.width * k, img.height * k);
      c.restore(); tex.needsUpdate = true;
    });
  };
  crest(false);
  return { tex, totalL, totalW, crest };
}

// A club paints its lines the usual near-white; a kit may ask for its own (SKILLCORNER paints them near-black, so Home reads as
// SkillCorner's green and black rather than a green court with an ordinary white markup over it).
function lines(court, colour = 0xf3f1ea) {
  const g = new THREE.Group();
  const mat = new THREE.MeshStandardMaterial({ color: colour, roughness: 0.55, metalness: 0, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
  const bar = (x0, y0, x1, y1) => {  // a straight line between two data points
    const len = Math.hypot(x1 - x0, y1 - y0) + LINE;
    const m = new THREE.Mesh(new THREE.PlaneGeometry(len, LINE), mat);
    m.rotation.set(-Math.PI / 2, 0, -Math.atan2(y1 - y0, x1 - x0));
    m.position.copy(onFloor((x0 + x1) / 2, (y0 + y1) / 2, LIFT));
    g.add(m);
  };
  const arc = (cx, cy, r, a0, a1) => {  // angles in data space, counter-clockwise from +x
    const m = new THREE.Mesh(new THREE.RingGeometry(r - LINE / 2, r + LINE / 2, 128, 1, a0, a1 - a0), mat);
    m.rotation.x = -Math.PI / 2;
    m.position.copy(onFloor(cx, cy, LIFT));
    g.add(m);
  };
  const Lh = court.length / 2, Wh = court.width / 2, [hx] = court.hoop;
  const R = court.three_radius, cy = court.three_corner_y, [paintL, paintW] = court.paint;
  bar(-Lh, -Wh, Lh, -Wh); bar(-Lh, Wh, Lh, Wh); bar(-Lh, -Wh, -Lh, Wh); bar(Lh, -Wh, Lh, Wh);
  bar(0, -Wh, 0, Wh);
  arc(0, 0, court.free_throw_radius, 0, Math.PI * 2);
  const t0 = Math.asin(cy / R), xa = hx + R * Math.cos(t0);
  for (const s of [1, -1]) {
    const fx = (x) => s * x;
    bar(fx(-Lh), -cy, fx(xa), -cy); bar(fx(-Lh), cy, fx(xa), cy);
    if (s === 1) arc(hx, 0, R, -t0, t0); else arc(-hx, 0, R, Math.PI - t0, Math.PI + t0);
    const ft = -Lh + paintL;
    bar(fx(-Lh), -paintW / 2, fx(ft), -paintW / 2); bar(fx(-Lh), paintW / 2, fx(ft), paintW / 2); bar(fx(ft), -paintW / 2, fx(ft), paintW / 2);
    if (s === 1) arc(ft, 0, court.free_throw_radius, -Math.PI / 2, Math.PI / 2); else arc(-ft, 0, court.free_throw_radius, Math.PI / 2, 1.5 * Math.PI);
    // no-charge semicircle, with its two short legs back to the line of the backboard
    const nc = court.no_charge_radius;
    if (s === 1) arc(hx, 0, nc, -Math.PI / 2, Math.PI / 2); else arc(-hx, 0, nc, Math.PI / 2, 1.5 * Math.PI);
    bar(fx(court.backboard_x), -nc, fx(hx), -nc); bar(fx(court.backboard_x), nc, fx(hx), nc);
  }
  return g;
}

function netTexture() {
  const cv = document.createElement('canvas');
  cv.width = 512; cv.height = 256;
  const c = cv.getContext('2d');
  c.strokeStyle = 'rgba(255,255,255,0.92)';
  c.lineWidth = 5;
  const n = 12, w = cv.width / n;
  for (let k = -n; k < 2 * n; k += 1) {
    c.beginPath(); c.moveTo(k * w, 0); c.lineTo(k * w + cv.height * 0.55, cv.height); c.stroke();
    c.beginPath(); c.moveTo(k * w, 0); c.lineTo(k * w - cv.height * 0.55, cv.height); c.stroke();
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function beam(a, b, thick, mat) {
  const len = a.distanceTo(b);
  const m = new THREE.Mesh(new THREE.BoxGeometry(len, thick, thick), mat);
  m.position.copy(a).add(b).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(new THREE.Vector3(1, 0, 0), b.clone().sub(a).normalize());
  return m;
}

/** The basket at the -x end (the one every possession attacks). Rotate by pi for the other. */
function basket(court) {
  const g = new THREE.Group();
  const [hx] = court.hoop, rimH = court.rim_height, bx = court.backboard_x;
  const boardW = 5.91, boardH = 3.44, boardLow = 9.51;
  const glass = new THREE.MeshPhysicalMaterial({ color: 0xdfeaff, roughness: 0.08, metalness: 0, transparent: true, opacity: 0.2, side: THREE.DoubleSide, depthWrite: false });
  const white = new THREE.MeshStandardMaterial({ color: 0xf3f1ea, roughness: 0.5 });
  const pad = new THREE.MeshStandardMaterial({ color: 0x141d31, roughness: 0.75 });
  const orange = new THREE.MeshStandardMaterial({ color: 0xe8622c, roughness: 0.4, metalness: 0.3 });

  const board = new THREE.Mesh(new THREE.BoxGeometry(0.12, boardH, boardW), glass);
  board.position.set(bx - 0.06, boardLow + boardH / 2, 0);
  board.renderOrder = 3;
  g.add(board);
  const edge = (w, h, y, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(0.14, h, w), white); m.position.set(bx - 0.06, y, z); g.add(m); };
  edge(boardW, 0.16, boardLow + 0.08, 0); edge(boardW, 0.16, boardLow + boardH - 0.08, 0);
  edge(0.16, boardH, boardLow + boardH / 2, -boardW / 2 + 0.08); edge(0.16, boardH, boardLow + boardH / 2, boardW / 2 - 0.08);
  const innerW = 1.94, innerH = 1.48, innerLow = rimH - 0.08;  // the small rectangle behind the rim: 59 x 45 cm
  edge(innerW, 0.12, innerLow, 0); edge(innerW, 0.12, innerLow + innerH, 0);
  edge(0.12, innerH, innerLow + innerH / 2, -innerW / 2); edge(0.12, innerH, innerLow + innerH / 2, innerW / 2);

  const rim = new THREE.Mesh(new THREE.TorusGeometry(0.738, 0.05, 12, 64), orange);
  rim.rotation.x = Math.PI / 2;
  rim.position.set(hx, rimH, 0);
  g.add(rim);
  const plate = new THREE.Mesh(new THREE.BoxGeometry(hx - 0.738 - bx, 0.08, 0.5), orange);
  plate.position.set((bx + hx - 0.738) / 2, rimH - 0.02, 0);
  g.add(plate);
  const net = new THREE.Mesh(new THREE.CylinderGeometry(0.72, 0.42, 1.35, 32, 1, true),
    new THREE.MeshBasicMaterial({ map: netTexture(), transparent: true, opacity: 0.8, side: THREE.DoubleSide, depthWrite: false }));
  net.position.set(hx, rimH - 0.7, 0);
  net.renderOrder = 4;
  g.add(net);

  const cushion = new THREE.Mesh(new THREE.BoxGeometry(0.34, 0.22, boardW - 0.2), pad);  // the padding along the bottom of the board
  cushion.position.set(bx + 0.05, boardLow - 0.11, 0);
  g.add(cushion);
  const baseX = -court.length / 2 - 5.4;
  const block = new THREE.Mesh(new THREE.BoxGeometry(4.2, 3.4, 3.4), pad);
  block.position.set(baseX, 1.7, 0);
  g.add(block);
  const arm = [new THREE.Vector3(baseX + 0.6, 3.2, 0), new THREE.Vector3(baseX + 1.1, 7.2, 0), new THREE.Vector3(baseX + 2.2, 10.2, 0), new THREE.Vector3(bx - 0.1, 11.2, 0)];
  for (let k = 0; k + 1 < arm.length; k += 1) g.add(beam(arm[k], arm[k + 1], 0.9 - 0.1 * k, pad));
  // the shot clock over the board, fed the data's value by the play
  const cv = document.createElement('canvas');
  cv.width = 160; cv.height = 96;
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  const panel = new THREE.Mesh(new THREE.BoxGeometry(0.3, 1.5, 2.6), pad);
  panel.position.set(bx - 0.15, boardLow + boardH + 1.15, 0);
  const face = new THREE.Mesh(new THREE.PlaneGeometry(2.4, 1.3), new THREE.MeshBasicMaterial({ map: tex }));
  face.position.set(bx + 0.01, boardLow + boardH + 1.15, 0); face.rotation.y = Math.PI / 2;
  g.add(panel, face);
  g.userData.clock = { cv, tex, last: null };
  return g;
}

/** Write a value on a basket's shot clock (only when it changes). */
function showClock(g, text) {
  const k = g.userData.clock;
  if (k.last === text) return;
  k.last = text;
  const c = k.cv.getContext('2d');
  c.fillStyle = '#05070c'; c.fillRect(0, 0, 160, 96);
  c.fillStyle = '#ff5a3c'; c.font = '700 74px Inter'; c.textAlign = 'center'; c.textBaseline = 'middle';
  c.fillText(text, 80, 52);
  k.tex.needsUpdate = true;
}

/** The hall around the court: boards, the table and the benches on the broadcast side, dark stands beyond. Decoration, nothing from the data. */
function surroundings(court) {
  const g = new THREE.Group();
  const L = court.length / 2 + RUNOFF_X, W = court.width / 2 + RUNOFF_Y;
  const dark = new THREE.MeshStandardMaterial({ color: 0x0c1220, roughness: 0.95 });
  const led = new THREE.MeshStandardMaterial({ color: 0x0a1020, emissive: 0x1b2d52, emissiveIntensity: 0.8, roughness: 0.6 });
  const box = (w, h, d, x, y, z, mat) => { const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat); m.position.set(x, y, z); g.add(m); return m; };
  // advertising boards, unlettered, along the sidelines and behind the baskets
  for (const s of [1, -1]) box(2 * L, 0.95, 0.35, 0, 0.48, s * (W - 0.6), led);
  for (const s of [1, -1]) box(0.35, 0.95, 2 * W - 3, s * (L - 0.5), 0.48, 0, led);
  // the scorer's table and the two benches on the broadcast side
  box(24, 2.4, 2.4, 0, 1.2, W + 2.6, dark);
  for (const s of [1, -1]) box(22, 1.5, 1.6, s * 27, 0.75, W + 2.4, dark);
  // stands: dark tiers rising away, on the far side and behind both baskets
  // stands: one dark slope on the far side and behind each basket, with faint rows of seats drawn on it
  const rows = 22, rise = 1.6, run = 2.6, slope = Math.hypot(rows * rise, rows * run);
  const tex = new THREE.CanvasTexture((() => {
    const cv = document.createElement('canvas'); cv.width = 1024; cv.height = 512;
    const c = cv.getContext('2d'); c.fillStyle = '#0a0e18'; c.fillRect(0, 0, 1024, 512);
    for (let r = 0; r < rows; r += 1) { const y = (r / rows) * 512; c.fillStyle = 'rgba(255,255,255,0.05)'; c.fillRect(0, y, 1024, 2); c.fillStyle = 'rgba(20,30,52,0.6)'; c.fillRect(0, y + 8, 1024, 512 / rows - 12); }
    return cv;
  })());
  tex.colorSpace = THREE.SRGBColorSpace; tex.wrapS = THREE.RepeatWrapping; tex.repeat.set(6, 1);
  const seats = new THREE.MeshStandardMaterial({ map: tex, roughness: 1 });
  const tilt = Math.atan2(rows * rise, rows * run);
  const tier = (len, x, z, ry) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(len, slope), seats);
    m.position.set(x, (rows * rise) / 2, z); m.rotation.set(-Math.PI / 2 + tilt, 0, 0);
    const g2 = new THREE.Group(); g2.add(m); g2.position.set(0, 0, 0); g2.rotation.y = ry; g.add(g2);
  };
  const far = W + 12 + (rows * run) / 2;
  tier(2 * L + 60, 0, -far, 0);
  tier(2 * W + 40, 0, -(L + 12 + (rows * run) / 2), Math.PI / 2);
  tier(2 * W + 40, 0, -(L + 12 + (rows * run) / 2), -Math.PI / 2);
  return g;
}

/** The court in the home club's colours (`kit`, or null for the plain floor); `group.setShotClock(text)` writes the shot clocks. */
export function buildCourt(court, anisotropy, kit = null) {
  const group = new THREE.Group();
  const { tex, totalL, totalW, crest } = woodTexture(court, anisotropy, kit);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(totalL, totalW),  // waxed maple: a clear coat over the wood, so the lights and the figures reflect in it
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.34, metalness: 0, envMapIntensity: 0.8 }));
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;  // only the mannequins cast any
  group.add(floor);
  // beyond the run-off the hall is dark: a large matte apron so the horizon never shows
  const apron = new THREE.Mesh(new THREE.PlaneGeometry(900, 900), new THREE.MeshStandardMaterial({ color: 0x05080f, roughness: 1 }));
  apron.rotation.x = -Math.PI / 2;
  apron.position.y = -0.03;
  group.add(apron);
  group.add(lines(court, kit && kit.lineColour ? kit.lineColour : 0xf3f1ea));
  const near = basket(court);
  const far = basket(court);
  far.rotation.y = Math.PI;
  group.add(near, far, surroundings(court));
  group.setShotClock = (text) => { showClock(near, text); showClock(far, text); };
  group.setShotClock('');
  group.faceCrest = crest;  // the seat may cross to the other sideline while the viewer runs; the crest turns with it
  return group;
}
