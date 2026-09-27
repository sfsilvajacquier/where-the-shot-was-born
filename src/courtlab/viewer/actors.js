// Everything that moves: ten pucks, the ball at its real height, and the defence drawn as elastic bands.
//
// A band joins a defender to the man SkillCorner says he guards. Its colour is how far beyond his normal spot
// he is (palette.js). A slack band sags, a taut one runs straight, thins and glows. When he is pulled more than
// a few feet away, a dashed ring shows the spot he left and a dotted tether ties him to it.
// Nothing here is drawn without a number behind it: no bodies (there is no pose in the data), no invented paths.

import * as THREE from 'three';
import { onFloor } from './court.js';
import { kitOf } from './kits.js';
import { tension, heat } from './palette.js';
import { Figures } from './figures.js';
import { mulberry32 } from './court.js';

const PUCK_R = 1.45;
const TRAIL = 30;        // frames of wake behind a player (1.2 s)
const BALL_TRAIL = 16;   // frames behind the ball (0.64 s); a shot keeps its whole arc
const BALL_R = 0.48;     // a real ball is 0.39 ft; drawn a fifth larger so it survives a phone screen
const SEG = 28;

const VERT = /* glsl */`
  attribute float alpha;
  varying vec2 vUv; varying float vAlpha;
  void main() { vUv = uv; vAlpha = alpha; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

const BAND = /* glsl */`
  uniform vec3 uColor; uniform float uAlpha, uLen, uDash, uTime, uShine;
  varying vec2 vUv;
  void main() {
    float d = abs(vUv.y - 0.5) * 2.0;
    float aa = fwidth(d) * 1.5;
    float a = 1.0 - smoothstep(1.0 - aa, 1.0, d);
    float ends = smoothstep(0.0, 0.6, vUv.x * uLen) * smoothstep(0.0, 0.6, (1.0 - vUv.x) * uLen);
    if (uDash > 0.0) {
      float p = fract((vUv.x * uLen - uTime) / uDash);
      a *= smoothstep(0.0, 0.06, p) * (1.0 - smoothstep(0.5, 0.56, p));
    }
    vec3 col = mix(uColor, vec3(1.0), uShine * (1.0 - d * d));
    gl_FragColor = vec4(col, a * ends * uAlpha);
    #include <colorspace_fragment>
  }`;

const HALO = /* glsl */`
  uniform vec3 uColor; uniform float uAlpha, uLen;
  varying vec2 vUv;
  void main() {
    float d = abs(vUv.y - 0.5) * 2.0;
    float ends = smoothstep(0.0, 1.6, vUv.x * uLen) * smoothstep(0.0, 1.6, (1.0 - vUv.x) * uLen);
    float a = exp(-d * d * 5.5) * (1.0 - smoothstep(0.85, 1.0, d));
    gl_FragColor = vec4(uColor * a * ends * uAlpha, 1.0);
    #include <colorspace_fragment>
  }`;

const RING = /* glsl */`
  uniform vec3 uColor; uniform float uAlpha, uRadius, uWidth, uDashes, uSize, uGlow;
  varying vec2 vUv;
  void main() {
    vec2 p = (vUv - 0.5) * uSize;
    float r = length(p);
    float aa = fwidth(r) * 1.2;
    float ring = 1.0 - smoothstep(uWidth * 0.5 - aa, uWidth * 0.5 + aa, abs(r - uRadius));
    if (uDashes > 0.0) {
      float q = fract(atan(p.y, p.x) / 6.2831853 * uDashes);
      ring *= smoothstep(0.0, 0.05, q) * (1.0 - smoothstep(0.55, 0.6, q));
    }
    float glow = uGlow * exp(-pow((r - uRadius) / (uWidth * 2.2), 2.0));
    gl_FragColor = vec4(uColor, max(ring, glow) * uAlpha);
    #include <colorspace_fragment>
  }`;

const TRAIL_FRAG = /* glsl */`
  uniform vec3 uColor; uniform float uAlpha;
  varying vec2 vUv; varying float vAlpha;
  void main() {
    float d = abs(vUv.y - 0.5) * 2.0;
    gl_FragColor = vec4(uColor, (1.0 - d * d) * vAlpha * uAlpha);
    #include <colorspace_fragment>
  }`;

const srgb = (r, g, b) => new THREE.Color().setRGB(r, g, b, THREE.SRGBColorSpace);
const hex = (h) => new THREE.Color(h);

function decal(material, order) {
  material.transparent = true; material.depthWrite = false;
  const m = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), material);
  m.rotation.x = -Math.PI / 2;
  m.renderOrder = order;
  return m;
}

/** A strip of SEG quads whose vertices are rewritten every frame. */
class Ribbon {
  constructor(material, order, segments = SEG) {
    this.n = segments;
    const count = 2 * (segments + 1);
    this.pos = new Float32Array(count * 3);
    this.alpha = new Float32Array(count).fill(1);
    const uv = new Float32Array(count * 2), index = [];
    for (let k = 0; k <= segments; k += 1) {
      uv.set([k / segments, 0, k / segments, 1], 4 * k);
      if (k < segments) index.push(2 * k, 2 * k + 1, 2 * k + 2, 2 * k + 1, 2 * k + 3, 2 * k + 2);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('alpha', new THREE.BufferAttribute(this.alpha, 1).setUsage(THREE.DynamicDrawUsage));
    g.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
    g.setIndex(index);
    material.transparent = true; material.depthWrite = false; material.side = THREE.DoubleSide;
    this.mesh = new THREE.Mesh(g, material);
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = order;
  }

  /** points: THREE.Vector3[n+1]; side(k) -> Vector3 half-width offset at point k. */
  set(points, side) {
    for (let k = 0; k <= this.n; k += 1) {
      const p = points[k], s = side(k);
      this.pos.set([p.x - s.x, p.y - s.y, p.z - s.z, p.x + s.x, p.y + s.y, p.z + s.z], 6 * k);
    }
    this.mesh.geometry.attributes.position.needsUpdate = true;
  }
}

function numberTexture(text, fill, ink, ring) {
  const cv = document.createElement('canvas');
  cv.width = cv.height = 256;
  const c = cv.getContext('2d');
  c.fillStyle = fill; c.fillRect(0, 0, 256, 256);
  if (ring) { c.strokeStyle = ring; c.lineWidth = 16; c.beginPath(); c.arc(128, 128, 114, 0, Math.PI * 2); c.stroke(); }
  c.fillStyle = ink;
  c.font = `800 ${text.length > 1 ? 132 : 156}px Inter`;
  c.textAlign = 'center'; c.textBaseline = 'alphabetic';
  const m = c.measureText(text);
  c.fillText(text, 128, 128 + (m.actualBoundingBoxAscent - m.actualBoundingBoxDescent) / 2);
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function blobTexture() {
  const cv = document.createElement('canvas');
  cv.width = cv.height = 128;
  const c = cv.getContext('2d');
  const g = c.createRadialGradient(64, 64, 0, 64, 64, 64);
  g.addColorStop(0, 'rgba(0,0,0,0.78)'); g.addColorStop(0.45, 'rgba(0,0,0,0.42)'); g.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = g; c.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(cv);
}

function ballTexture() {
  const cv = document.createElement('canvas');
  cv.width = 1024; cv.height = 512;
  const c = cv.getContext('2d');
  c.fillStyle = '#d9622b'; c.fillRect(0, 0, 1024, 512);
  const rnd = mulberry32(3);  // the same pebbling every load: stills compare pixel for pixel
  for (let k = 0; k < 9000; k += 1) { c.fillStyle = `rgba(90,30,5,${rnd() * 0.12})`; c.fillRect(rnd() * 1024, rnd() * 512, 2, 2); }
  c.strokeStyle = '#1d1210'; c.lineWidth = 9;
  c.beginPath(); c.moveTo(0, 256); c.lineTo(1024, 256); c.stroke();
  for (const x of [256, 768]) { c.beginPath(); c.moveTo(x, 0); c.lineTo(x, 512); c.stroke(); }
  for (const s of [1, -1]) {
    c.beginPath();
    for (let x = 0; x <= 1024; x += 8) { const y = 256 + s * (150 + 60 * Math.cos((x / 1024) * Math.PI * 4)); if (x) c.lineTo(x, y); else c.moveTo(x, y); }
    c.stroke();
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

const mix = (a, b, f) => a + (b - a) * f;
const at2 = (arr, i0, i1, f) => {
  const a = arr[i0], b = arr[i1];
  if (!a || a[0] == null) return b && b[0] != null ? b : null;
  if (!b || b[0] == null) return a;
  return a.map((v, k) => mix(v, b[k], f));
};
const at1 = (arr, i0, i1, f) => {
  const a = arr[i0], b = arr[i1];
  if (a == null) return b ?? null;
  if (b == null) return a;
  return mix(a, b, f);
};

export class Actors {
  constructor(scene, data, azimuth) {
    this.d = data;
    this.group = new THREE.Group();
    scene.add(this.group);
    this.n = data.frames.idx.length;
    this.players = new Map(data.players.map((p) => [p.id, p]));
    this.attack = data.players.filter((p) => p.side === 'attack');
    this.defence = data.players.filter((p) => p.side === 'defence');
    this.closeouts = data.actions.filter((a) => a.type === 'closeout');
    this.shot = data.actions.find((a) => a.type === 'shot') || null;
    this.w = data.model.normal_spot;
    this.hoop = data.court.hoop;
    this.ballPath = this.bounced(this.correctedBall());
    this.ballRoll = this.rolling(this.ballPath);
    this.azimuth = azimuth;
    this.figures = new Figures(scene, data, (f) => { if (this.onFiguresReady) this.onFiguresReady(f); });  // built in the background from the start; shown in figures mode

    const blob = blobTexture();
    this.pucks = new Map();
    const body = new THREE.LatheGeometry([[0, 0], [1.4, 0], [PUCK_R, 0.06], [PUCK_R, 0.3], [1.39, 0.4], [1.3, 0.44], [0, 0.44]].map(([x, y]) => new THREE.Vector2(x, y)), 64);
    for (const p of data.players) {
      // the puck is the diagram: light for the attack, dark for the defence, so the bands' blue and amber stay the only colours that carry a
      // number; the club shows in the ring, the way a collar shows the kit (the figures wear the whole kit)
      const attack = p.side === 'attack', kit = kitOf(attack ? data.game.attack : data.game.defence);
      const g = new THREE.Group();
      const shell = new THREE.Mesh(body, new THREE.MeshStandardMaterial({ color: attack ? 0xf1ece2 : 0x222b3d, roughness: attack ? 0.35 : 0.45, metalness: attack ? 0 : 0.25, transparent: true }));
      const top = new THREE.Mesh(new THREE.CircleGeometry(1.3, 64), new THREE.MeshStandardMaterial({
        map: numberTexture(String(p.jersey), attack ? '#f4efe6' : '#1b2334', attack ? '#0b1220' : '#dfe7f5', kit.key ? kit.primary : (attack ? null : '#7d8aa3')), roughness: 0.5, transparent: true }));
      top.rotation.set(-Math.PI / 2, 0, azimuth);
      top.position.y = 0.442;
      const shadow = decal(new THREE.MeshBasicMaterial({ map: blob, opacity: 0.9 }), 1);
      shadow.scale.set(5.4, 5.4, 1);
      shadow.position.set(0.35, 0.02, 0.25);
      const base = decal(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: RING, uniforms: {  // what a mannequin stands on: the puck's outline
        uColor: { value: hex(attack ? 0xf1ece2 : 0x8b98ae) }, uAlpha: { value: 0.75 }, uRadius: { value: 1.25 }, uWidth: { value: 0.1 }, uDashes: { value: 0 }, uSize: { value: 3.2 }, uGlow: { value: 0 } } }), 2);
      base.scale.set(3.2, 3.2, 1); base.position.y = 0.03; base.visible = false;
      g.add(shell, top, shadow, base);
      g.position.y = (attack ? 0.012 : 0) + 0.002 * this.pucks.size;  // two pucks that overlap never fight for the same pixels
      this.group.add(g);
      this.pucks.set(p.id, { g, shell, top, shadow, base, lift: g.position.y });
    }

    this.holderRing = decal(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: RING, uniforms: {
      uColor: { value: hex(0xfff3d6) }, uAlpha: { value: 0.95 }, uRadius: { value: 1.95 }, uWidth: { value: 0.16 }, uDashes: { value: 0 }, uSize: { value: 6 }, uGlow: { value: 0.45 } } }), 5);
    this.holderRing.scale.set(6, 6, 1);
    this.group.add(this.holderRing);

    const bandUniforms = (dash) => ({ uColor: { value: new THREE.Color() }, uAlpha: { value: 1 }, uLen: { value: 1 }, uDash: { value: dash }, uTime: { value: 0 }, uShine: { value: 0.3 } });
    this.bands = new Map();
    for (const p of this.attack) {
      const halo = new Ribbon(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: HALO, blending: THREE.AdditiveBlending, uniforms: { uColor: { value: new THREE.Color() }, uAlpha: { value: 0 }, uLen: { value: 1 } } }), 3);
      const core = new Ribbon(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: BAND, uniforms: bandUniforms(0) }), 4);
      const shade = new Ribbon(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: TRAIL_FRAG, uniforms: { uColor: { value: hex(0x000000) }, uAlpha: { value: 0.5 } } }), 2);
      this.group.add(shade.mesh, halo.mesh, core.mesh);
      this.bands.set(p.id, { halo, core, shade });
    }
    this.ghosts = new Map();
    for (const p of this.defence) {
      const ring = decal(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: RING, uniforms: {
        uColor: { value: hex(0xe6edf9) }, uAlpha: { value: 0 }, uRadius: { value: 1.3 }, uWidth: { value: 0.13 }, uDashes: { value: 14 }, uSize: { value: 3.4 }, uGlow: { value: 0 } } }), 4);
      ring.scale.set(3.4, 3.4, 1);
      const tether = new Ribbon(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: BAND, uniforms: { ...bandUniforms(0.7), uColor: { value: hex(0xe6edf9) }, uShine: { value: 0 } } }), 4, 1);
      this.group.add(ring, tether.mesh);
      this.ghosts.set(p.id, { ring, tether });
    }

    const trailMat = (color, alpha) => new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: TRAIL_FRAG, uniforms: { uColor: { value: hex(color) }, uAlpha: { value: alpha } } });
    this.trails = new Map(data.players.map((p) => {
      const r = new Ribbon(trailMat(p.side === 'attack' ? 0xfff6e6 : 0x9fb0cc, p.side === 'attack' ? 0.3 : 0.22), 2, TRAIL);
      this.group.add(r.mesh);
      return [p.id, r];
    }));

    // the path of the ball on the floor: one dotted segment per completed pass, drawn as the play advances (a layer, off by default)
    this.passes = data.actions.filter((a) => a.type === 'pass' && a.complete && a.i_end != null && a.i_end > a.i);
    this.path = this.passes.map((a) => {
      const r = new Ribbon(new THREE.ShaderMaterial({ vertexShader: VERT, fragmentShader: BAND, uniforms: { ...bandUniforms(1.1), uColor: { value: hex(0xfff1cf) }, uShine: { value: 0 }, uAlpha: { value: 0.55 } } }), 3, 1);
      r.mesh.visible = false; this.group.add(r.mesh); return r;
    });
    this.layers = { path: false, distances: false };
    this.ball = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 40, 24), new THREE.MeshStandardMaterial({ map: ballTexture(), roughness: 0.62 }));
    this.ballShadow = decal(new THREE.MeshBasicMaterial({ map: blob }), 1);
    this.ballTrail = new Ribbon(trailMat(0xffb070, 0.75), 6, 48);
    this.stem = new THREE.Mesh(new THREE.CylinderGeometry(0.022, 0.022, 1, 6), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.22, depthWrite: false }));
    this.stem.renderOrder = 6;
    this.group.add(this.ball, this.ballShadow, this.ballTrail.mesh, this.stem);
  }

  /** SkillCorner's ball track is a smoothed reconstruction: on a made shot it reaches rim height a foot or so outside the ring.
   *  For the picture only, the last third of a second of a MADE shot's flight is bent so the ball goes through the ring, then
   *  drops inside the net. Nothing is measured from this path. Missed shots are left exactly as tracked. */
  correctedBall() {
    const src = this.d.ball.xyz, out = src.map((b) => (b ? b.slice() : b)), s = this.shot;
    if (!s || !s.made || s.i == null) return out;
    const rim = this.d.court.rim_height, [hx, hy] = this.hoop;
    let apex = -1, kStar = -1;
    for (let k = s.i; k < Math.min(out.length, s.i + 60); k += 1) {
      const b = src[k];
      if (!b || b[0] == null) continue;
      if (apex < 0 || b[2] > src[apex][2]) apex = k;
    }
    for (let k = apex + 1; k < Math.min(out.length, s.i + 60); k += 1) {
      const b = src[k];
      if (b && b[0] != null && b[2] <= rim) { kStar = k; break; }
    }
    if (kStar < 0) return out;
    // the miss is spread over the WHOLE flight as a linear shear, so the arc stays one straight line in plan: no hook at the end
    const dx = hx - src[kStar][0], dy = hy - src[kStar][1];
    for (let k = s.i; k <= kStar; k += 1) {
      const b = src[k];
      if (!b || b[0] == null) continue;
      const w = (k - s.i) / (kStar - s.i);
      out[k] = [b[0] + dx * w, b[1] + dy * w, b[2]];
    }
    for (let k = kStar + 1; k < out.length; k += 1) {  // inside the net: keep the descent, kill the sideways drift
      const b = src[k];
      if (!b || b[0] == null) continue;
      const drop = Math.min(1, (k - kStar) / 10);
      out[k] = [hx + (b[0] - src[kStar][0]) * 0.25 * (1 - drop), hy + (b[1] - src[kStar][1]) * 0.25 * (1 - drop), Math.max(BALL_R, Math.min(b[2], rim - (k - kStar) * 0.22))];
    }
    return out;
  }

  /** The reconstructed ball bottoms out a foot or two above the floor on a dribble. For the picture only, at each dribble SkillCorner labels
   *  the ball is pulled down to the floor over a fifth of a second, as the bend into the ring. Nothing is measured from this path. */
  bounced(path) {
    const z = path.map((b) => (b && b[0] != null ? b[2] : null)), done = new Set();
    for (const a of this.d.actions) {
      if (a.type !== 'dribble' || a.i == null) continue;
      let m = -1;  // the valley of the track nearest the label; a label at the edge of the window with no valley near it is left alone
      for (let k = Math.max(1, a.i - 4); k <= Math.min(z.length - 2, a.i + 4); k += 1) if (z[k] != null && z[k - 1] != null && z[k + 1] != null && z[k] <= z[k - 1] && z[k] <= z[k + 1] && (m < 0 || z[k] < z[m])) m = k;
      if (m < 0 || done.has(m)) continue;
      done.add(m);
      const depth = z[m] - BALL_R;
      if (depth <= 0) continue;
      for (let k = Math.max(0, m - 5); k <= Math.min(path.length - 1, m + 5); k += 1) {
        if (!path[k] || path[k][0] == null) continue;
        const u = (k - m) / 5, w = (1 - u * u) ** 2;
        path[k][2] = Math.max(BALL_R, path[k][2] - depth * w);
      }
    }
    return path;
  }

  /** The ball's turn by each frame and the axis it turns about: in a hand or on the bounce it rolls with its travel (capped, the track is
   *  smoothed); in the air it carries backspin, two and a half turns a second, as a pass or a shot does. */
  rolling(path) {
    const n = path.length, angle = new Float32Array(n), axis = [];
    let last = new THREE.Vector3(0, 0, -1), a = 0;
    for (let i = 0; i < n; i += 1) {
      const p = path[Math.max(0, i - 1)], b = path[i];
      if (i && p && b && p[0] != null && b[0] != null) {
        const dx = b[0] - p[0], dy = b[1] - p[1];
        if (Math.hypot(dx, dy) > 0.02) last = new THREE.Vector3(dy, 0, -dx).normalize();  // rolling forward along (dx, dy) on the floor
        a += this.d.holder[i] != null ? Math.min(Math.hypot(dx, dy, b[2] - p[2]) / BALL_R, 0.5) : -(2.5 * Math.PI * 2) / this.d.fps;
      }
      angle[i] = a; axis.push(last);
    }
    return { angle, axis };
  }

  /** Hide one player's body (the eye-level camera sits inside it); null shows everybody. */
  hideBody(id) {
    if (this.hidden === id) return;
    for (const [pid, puck] of this.pucks) puck.g.visible = pid !== id && puck.g.visible;
    if (this.hidden != null) { const p = this.pucks.get(this.hidden); if (p) p.g.visible = true; }
    this.figures.hide(id);
    this.hidden = id;
  }

  /** 'pucks' (what the data measures) or 'figures' (bodies generated from it: see posture.js and figures.js). */
  setMode(mode) {
    this.mode = mode;
    this.figures.setVisible(mode === 'figures');
    for (const puck of this.pucks.values()) { puck.shell.visible = puck.top.visible = puck.shadow.visible = mode !== 'figures'; puck.base.visible = mode === 'figures'; }
  }

  /** The defender's normal spot for a man and a ball, the same formula the Python package fits. */
  spot(man, ball) {
    const { man: a, ball: b, hoop: c } = this.w;
    return [a * man[0] + b * ball[0] + c * this.hoop[0], a * man[1] + b * ball[1] + c * this.hoop[1]];
  }

  xy(id, i0, i1, f) { return at2(this.players.get(id).xy, i0, i1, f); }

  /** Place everything at fractional frame t. Returns what the read-outs need. */
  update(t, camera, clock = 0) {
    const d = this.d;
    const i0 = Math.max(0, Math.min(this.n - 1, Math.floor(t))), i1 = Math.min(this.n - 1, i0 + 1), f = t - i0;
    const ball = at2(this.ballPath, i0, i1, f);
    const holder = d.holder[f < 0.5 ? i0 : i1];

    // the jersey numbers read upright from whichever camera is on: turn them to the camera's up, projected on the floor
    const up = new THREE.Vector3(0, 1, 0).applyQuaternion(camera.quaternion); up.y = 0;
    const turn = up.lengthSq() > 1e-6 ? Math.atan2(up.x, up.z) + Math.PI : this.azimuth;
    for (const p of d.players) {
      const puck = this.pucks.get(p.id), xy = this.xy(p.id, i0, i1, f);
      puck.g.visible = !!xy && p.id !== this.hidden;
      if (!xy) continue;
      puck.top.rotation.z = turn;
      puck.g.position.copy(onFloor(xy[0], xy[1], puck.lift));
      const seen = p.seen[i0] ? 1 : 0.42;  // off camera: SkillCorner extrapolates him, so he is drawn as a ghost of himself
      puck.shell.material.opacity = seen; puck.top.material.opacity = seen;
      this.wake(this.trails.get(p.id), p.xy, t, TRAIL, 0.95);
    }

    const rows = [];
    const used = new Set();
    for (const p of this.attack) {
      const band = this.bands.get(p.id), man = this.xy(p.id, i0, i1, f);
      let guard = d.guard[p.id][f < 0.5 ? i0 : i1], extra = at1(d.extra[p.id], i0, i1, f), gap = at1(d.gap[p.id], i0, i1, f), closing = false;
      if (!guard) {  // nobody is assigned to him; if SkillCorner labels a close-out on him, that defender is the one running
        const c = this.closeouts.find((a) => a.player === p.id && t >= a.i && t <= a.i_end);
        if (c) { guard = c.defender; closing = true; }
      }
      const def = guard ? this.xy(guard, i0, i1, f) : null;
      if (!man || !def || !ball) { band.core.mesh.visible = band.halo.mesh.visible = band.shade.mesh.visible = false; rows.push({ id: p.id, guard: 0, gap: null, extra: null, closing: false }); continue; }
      const spot = this.spot(man, ball);
      if (closing || extra == null) {
        gap = Math.hypot(man[0] - def[0], man[1] - def[1]);
        extra = gap - Math.hypot(man[0] - spot[0], man[1] - spot[1]);
      }
      this.stretch(band, def, man, extra, closing, clock);
      rows.push({ id: p.id, guard, gap, extra, closing, mid: [(def[0] + man[0]) / 2, (def[1] + man[1]) / 2] });

      const ghost = this.ghosts.get(guard);
      if (ghost && !used.has(guard)) {
        used.add(guard);
        const away = Math.hypot(def[0] - spot[0], def[1] - spot[1]);
        const a = THREE.MathUtils.smoothstep(away, 3.5, 6.5);
        ghost.ring.visible = ghost.tether.mesh.visible = a > 0.01;
        ghost.ring.position.copy(onFloor(spot[0], spot[1], 0.036));
        ghost.ring.material.uniforms.uAlpha.value = 0.8 * a;
        this.straight(ghost.tether, spot, def, 0.13, 1.3, PUCK_R);
        ghost.tether.mesh.material.uniforms.uAlpha.value = 0.55 * a;
      }
    }
    for (const [id, ghost] of this.ghosts) if (!used.has(id)) ghost.ring.visible = ghost.tether.mesh.visible = false;

    this.passes.forEach((a, k) => {  // the path so far
      const r = this.path[k], on = this.layers.path && t >= a.i_end;
      r.mesh.visible = on;
      if (!on) return;
      const from = this.xy(a.from, a.i, a.i, 0), to = this.xy(a.to, a.i_end, a.i_end, 0);
      if (from && to) this.straight(r, from, to, 0.16, PUCK_R + 0.3, PUCK_R + 0.3);
    });
    const hxy = holder ? this.xy(holder, i0, i1, f) : null;
    this.holderRing.visible = !!hxy;
    if (hxy) this.holderRing.position.copy(onFloor(hxy[0], hxy[1], 0.04));

    this.ball.visible = this.ballShadow.visible = this.ballTrail.mesh.visible = this.stem.visible = !!ball;
    if (ball) {
      const z = Math.max(BALL_R, ball[2]);
      this.ball.position.copy(onFloor(ball[0], ball[1], z));
      this.ball.quaternion.setFromAxisAngle(this.ballRoll.axis[i0], mix(this.ballRoll.angle[i0], this.ballRoll.angle[i1], f));
      const s = 1.5 + z * 0.16;
      this.ballShadow.scale.set(s, s, 1);
      this.ballShadow.position.copy(onFloor(ball[0] + z * 0.06, ball[1] - z * 0.04, 0.022));
      this.ballShadow.material.opacity = 0.85 / (1 + z * 0.12);
      this.stem.visible = z > 3.2 && !holder;
      this.stem.scale.y = z - BALL_R; this.stem.position.copy(onFloor(ball[0], ball[1], (z - BALL_R) / 2));
      const flying = this.shot && t >= this.shot.i && t <= this.shot.i_end + 12;
      const near = camera.position.distanceTo(this.ball.position);  // close cameras: a shorter, thinner wake, or the ball reads as a smear
      this.flight(t, flying ? Math.min(47, Math.ceil(t - this.shot.i)) : Math.round(BALL_TRAIL * Math.min(1, Math.max(0.35, near / 120))), camera, Math.min(1, Math.max(0.12, near / 160)));
    }
    if (this.mode === 'figures') this.figures.update(t, ball, holder);
    return { i: f < 0.5 ? i0 : i1, holder, rows };
  }

  /** The band itself: a slack one sags towards the basket, a taut one is a straight line. */
  stretch(band, def, man, extra, closing, clock) {
    const dx = man[0] - def[0], dy = man[1] - def[1], len = Math.hypot(dx, dy);
    const visible = len > 2 * PUCK_R + 0.3;
    band.core.mesh.visible = band.halo.mesh.visible = band.shade.mesh.visible = visible;
    if (!visible) return;
    const ux = dx / len, uy = dy / len, h = heat(extra);
    const a = [def[0] + ux * PUCK_R * 0.9, def[1] + uy * PUCK_R * 0.9], b = [man[0] - ux * PUCK_R * 0.9, man[1] - uy * PUCK_R * 0.9];
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    let rx = this.hoop[0] - mid[0], ry = this.hoop[1] - mid[1];
    const rl = Math.hypot(rx, ry) || 1; rx /= rl; ry /= rl;
    const along = rx * ux + ry * uy;
    const sag = closing ? 0 : Math.min(1.6, Math.max(0, -extra) * 0.22) * Math.min(1, (len - 2 * PUCK_R) / 4);
    const sx = (rx - along * ux) * sag * 2, sy = (ry - along * uy) * sag * 2;  // control point of the curve
    const pts = [], n = band.core.n;
    for (let k = 0; k <= n; k += 1) {
      const u = k / n, w = 2 * u * (1 - u);
      pts.push([mix(a[0], b[0], u) + sx * w, mix(a[1], b[1], u) + sy * w]);
    }
    const width = closing ? 0.34 : mix(0.62, 0.36, h);
    const lay = (ribbon, half, lift, dx = 0, dy = 0) => {
      const v = pts.map(([x, y]) => onFloor(x + dx, y + dy, lift));
      ribbon.set(v, (k) => {
        const p = pts[Math.max(0, k - 1)], q = pts[Math.min(n, k + 1)];
        const tx = q[0] - p[0], ty = q[1] - p[1], tl = Math.hypot(tx, ty) || 1;
        return new THREE.Vector3((-ty / tl) * half, 0, (-tx / tl) * half);
      });
    };
    lay(band.core, width / 2, 0.034);
    lay(band.halo, 1.15, 0.03);
    lay(band.shade, width / 2 + 0.22, 0.027, 0.1, -0.1);
    const [r, g, bl] = tension(extra);
    const cu = band.core.mesh.material.uniforms, hu = band.halo.mesh.material.uniforms;
    cu.uColor.value.copy(srgb(r, g, bl)); hu.uColor.value.copy(srgb(r, g, bl));
    cu.uLen.value = hu.uLen.value = len - 1.8 * PUCK_R;
    cu.uDash.value = closing ? 1.5 : 0; cu.uTime.value = clock * 5;
    cu.uShine.value = 0.18 + 0.4 * h;
    cu.uAlpha.value = extra < 0 ? 0.78 : 0.95;
    hu.uAlpha.value = 0.06 + 0.42 * h;
  }

  straight(ribbon, from, to, width, trimA, trimB) {
    const dx = to[0] - from[0], dy = to[1] - from[1], len = Math.hypot(dx, dy) || 1, ux = dx / len, uy = dy / len;
    const a = onFloor(from[0] + ux * trimA, from[1] + uy * trimA, 0.035), b = onFloor(to[0] - ux * trimB, to[1] - uy * trimB, 0.035);
    const side = new THREE.Vector3((-uy) * width / 2, 0, (-ux) * width / 2);
    ribbon.set([a, b], () => side);
    ribbon.mesh.material.uniforms.uLen.value = Math.max(0.1, len - trimA - trimB);
  }

  /** The wake of a player on the floor: where he was during the last second. */
  wake(ribbon, xy, t, frames, width) {
    const pts = [];
    for (let k = 0; k <= frames; k += 1) {
      const tt = Math.max(0, t - k), i0 = Math.floor(tt), i1 = Math.min(this.n - 1, i0 + 1);
      pts.push(at2(xy, i0, i1, tt - i0) || pts[pts.length - 1] || [0, 0]);
    }
    const v = pts.map(([x, y]) => onFloor(x, y, 0.026));
    ribbon.set(v, (k) => {
      const p = pts[Math.max(0, k - 1)], q = pts[Math.min(frames, k + 1)];
      const tx = q[0] - p[0], ty = q[1] - p[1], tl = Math.hypot(tx, ty);
      const half = (width / 2) * (1 - k / frames);
      return tl < 1e-4 ? new THREE.Vector3() : new THREE.Vector3((-ty / tl) * half, 0, (-tx / tl) * half);
    });
    for (let k = 0; k <= frames; k += 1) { const a = (1 - k / frames) ** 1.5; ribbon.alpha[2 * k] = a; ribbon.alpha[2 * k + 1] = a; }
    ribbon.mesh.geometry.attributes.alpha.needsUpdate = true;
  }

  /** The path of the ball through the air, facing the camera. */
  flight(t, frames, camera, width = 1) {
    const ribbon = this.ballTrail, n = ribbon.n, pts = [];
    for (let k = 0; k <= n; k += 1) {
      const tt = Math.max(0, t - (k / n) * frames), i0 = Math.floor(tt), i1 = Math.min(this.n - 1, i0 + 1);
      const b = at2(this.ballPath, i0, i1, tt - i0) || [0, 0, 0];
      pts.push(onFloor(b[0], b[1], Math.max(BALL_R, b[2])));
    }
    const view = new THREE.Vector3(), tan = new THREE.Vector3();
    ribbon.set(pts, (k) => {
      tan.copy(pts[Math.max(0, k - 1)]).sub(pts[Math.min(n, k + 1)]);
      view.copy(camera.position).sub(pts[k]);
      const side = new THREE.Vector3().crossVectors(tan, view);
      const l = side.length();
      return l < 1e-5 ? side.set(0, 0, 0) : side.multiplyScalar((0.3 * width * (1 - k / n)) / l);
    });
    for (let k = 0; k <= n; k += 1) { const a = (1 - k / n) ** 1.3; ribbon.alpha[2 * k] = a; ribbon.alpha[2 * k + 1] = a; }
    ribbon.mesh.geometry.attributes.alpha.needsUpdate = true;
  }
}
