// The cameras. The scene is real (positions from tracking, the ball's reconstructed height), so a camera can stand anywhere.
// Every camera is a pure function of the frame, so scrubbing and capture are deterministic; switching between two of them
// eases over half a second. Eye-level cameras use one declared rule for where a man looks: the man on the ball looks at the
// hoop, everybody else looks at the ball. There is no pose in the data, so that rule is a convention, not a measurement.

import * as THREE from 'three';
import { onFloor } from './court.js';

const W = 1920, H = 1080;
const EYE = 5.8;               // feet; every figure is one height
const EASE_S = 0.55;
const rad = THREE.MathUtils.degToRad;

const orbit = (target, azDeg, elDeg, dist) => {
  const az = rad(azDeg), el = rad(elDeg);
  return new THREE.Vector3(target.x + dist * Math.cos(el) * Math.sin(az), dist * Math.sin(el), target.z + dist * Math.cos(el) * Math.cos(az));
};
const smooth = (t) => t * t * (3 - 2 * t);

/** Presets, in the order the menu shows them. `fov` in degrees; `offset` keeps the court left of the cards and above the strip. */
export const PRESETS = [
  { id: 'auto', label: 'Director (cuts with the play)', fov: 24, offset: [232, 132] },
  { id: 'drift', label: 'Drift (start screen)', fov: 26, offset: [-360, 40], hidden: true },
  { id: 'broadcast', label: 'Broadcast', fov: 24, offset: [232, 132], figuresOffset: [236, 96] },
  { id: 'baseline', label: 'Behind the basket', fov: 40, offset: [232, 120] },
  { id: 'top', label: 'Top down', fov: 22, offset: [210, 50] },
  { id: 'rail', label: 'Follow the ball', fov: 34, offset: [232, 110] },
  { id: 'behind', label: 'Behind the ball', fov: 44, offset: [232, 100] },
  { id: 'eyes', label: 'Eyes of a player', fov: 62, offset: [0, 0] },
  { id: 'free', label: 'Free', fov: 30, offset: [232, 132] },
];

export class Cameras {
  constructor(camera, data, params) {
    this.camera = camera; this.d = data; this.hoop = data.court.hoop;
    this.n = data.frames.idx.length;
    this.num = (k, v) => (params.has(k) ? Number(params.get(k)) : v);  // ?az=&el=&dist=&tx=&ty=&ox=&oy= tune the broadcast seat without touching the code
    this.preset = 'broadcast'; this.mode = 'pucks'; this.eyesOf = null;
    this.tv = false;  // sit on the sideline the real broadcast camera sat on (the attack may then run to the right, as it did on TV)
    this.heldBy = data.holder.map((h, i, arr) => { for (let k = i; k >= 0; k -= 1) if (arr[k]) return arr[k]; return null; });  // who had the ball last by each frame (0 = nobody)
    this.gaze = null; this.gazeId = null; this.dt = 0;  // the eye-level camera: where he looks and how fast the head turns
    this.shiftY = 0;  // px the court moves down when the strip is folded away
    this.panel = true;  // false when the side panel is hidden: the court takes the whole width
    this.tvSide = data.tv_sideline_y || -1;
    this.free = { az: 12, el: 43, dist: 186, target: onFloor(-23, 0, 0) };
    this.from = null; this.blend = 1; this.lastPose = null;
    this.shot = data.actions.find((a) => a.type === 'shot') || null;
    this.anchor = null;  // 'behind' follows whoever has the ball; this remembers him through a pass and through the shot
    this.cuts = this.direct();
    this.live = null;  // the preset the director has on right now
    this.tmp = { pos: new THREE.Vector3(), look: new THREE.Vector3() };
  }

  /** True when the camera should sit on the −y sideline: the TV's when asked for it, the other one when not. */
  get flipped() { return (this.tv ? this.tvSide : -this.tvSide) < 0; }

  set(preset, { mode = this.mode, eyesOf = this.eyesOf } = {}) {
    if (this.lastPose) { this.from = { ...this.lastPose, fov: this.camera.fov }; this.blend = 0; }
    this.preset = preset; this.mode = mode; this.eyesOf = eyesOf;
    if (preset === 'free' && this.lastPose) {  // the free camera starts where the last one was
      const p = this.lastPose.pos, t = this.lastPose.look;
      const dx = p.x - t.x, dy = p.y - t.y, dz = p.z - t.z, dist = Math.hypot(dx, dy, dz);
      this.free = { az: THREE.MathUtils.radToDeg(Math.atan2(dx, dz)), el: THREE.MathUtils.radToDeg(Math.asin(dy / dist)), dist, target: t.clone() };
    }
  }

  /** Drag on the free camera: dx, dy in stage pixels; wheel in notches. */
  drag(dx, dy) { this.free.az -= dx * 0.25; this.free.el = THREE.MathUtils.clamp(this.free.el - dy * 0.2, 4, 88); }
  wheel(notches) { this.free.dist = THREE.MathUtils.clamp(this.free.dist * (1 + notches * 0.08), 30, 400); }

  xy(id, t) {
    const p = this.d.players.find((q) => q.id === id), i0 = Math.max(0, Math.min(this.n - 1, Math.floor(t))), i1 = Math.min(this.n - 1, i0 + 1), f = t - i0;
    const a = p.xy[i0], b = p.xy[i1];
    if (!a || a[0] == null) return b && b[0] != null ? b : null;
    if (!b || b[0] == null) return a;
    return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
  }

  /** The director's cut list, from SkillCorner's own labels: setup from the side, the action over the shoulder, the feed through
   *  the closing defender's eyes, the shot from behind the shooter, the outcome from the baseline. Hard cuts, as on TV. */
  direct() {
    const A = this.d.actions, n = this.n, cuts = [];
    const first = A.find((a) => ['pick', 'screen', 'handoff', 'drive', 'isolation', 'post'].includes(a.type) && a.i != null);
    const feed = this.shot ? [...A].reverse().find((a) => a.type === 'pass' && a.complete && a.to === this.shot.player && a.i_end != null && a.i_end <= this.shot.i) : null;
    const closeout = this.shot ? A.find((a) => a.type === 'closeout' && a.player === this.shot.player) : null;
    let t0 = 0;
    const push = (until, preset, eyesOf = null) => { if (until > t0) { cuts.push({ from: t0, to: until, preset, eyesOf }); t0 = until; } };
    if (first) push(Math.max(0, first.i - 25), 'broadcast');
    if (feed) push(feed.i, 'behind');
    if (feed && closeout) push(this.shot.i, 'eyes', closeout.defender); else if (feed) push(this.shot.i, 'rail');
    if (this.shot) push(Math.min(n, this.shot.i_end + 30), 'behind');
    push(n, 'baseline');
    return cuts;
  }

  /** Where the preset wants the camera at frame t, before easing. */
  pose(t, ball, holder, presetId = this.preset) {
    if (presetId === 'auto') {
      const cut = this.cuts.find((c) => t >= c.from && t < c.to) || this.cuts[this.cuts.length - 1];
      if (this.live !== cut.preset) { this.live = cut.preset; this.from = null; this.blend = 1; }  // a cut, not a glide
      const saved = this.eyesOf; this.eyesOf = cut.eyesOf ?? this.eyesOf;
      const out = this.pose(t, ball, holder, cut.preset); this.eyesOf = saved;
      return out;
    }
    const P = PRESETS.find((p) => p.id === presetId), fig = this.mode === 'figures';
    const b = ball ? onFloor(ball[0], ball[1], Math.max(0.5, ball[2])) : onFloor(this.hoop[0], 0, 4);
    let pos, look, fov = P.fov, offset = fig && P.figuresOffset ? P.figuresOffset : P.offset, up = new THREE.Vector3(0, 1, 0);
    if (presetId === 'broadcast') {
      const flip = this.flipped;  // from the −y sideline the attack runs to the right
      const target = onFloor(this.num('tx', fig ? -24 : -23), this.num('ty', fig ? 2 : 0) * (flip ? -1 : 1), 0);
      pos = orbit(target, this.num('az', 12) + (flip ? 180 : 0), this.num('el', fig ? 31 : 43), this.num('dist', fig ? 168 : 186)); look = target;
      offset = [this.num('ox', offset[0]) * (flip ? -1 : 1), this.num('oy', offset[1])];
    } else if (presetId === 'drift') {  // the start screen: a slow orbit around the attack, a pure function of the frame
      const target = onFloor(-22, 0, 2), az = 14 + 5 * Math.sin((t / this.n) * Math.PI * 2 - Math.PI / 2);
      pos = orbit(target, az, 30, 150); look = target;
    } else if (presetId === 'baseline') {  // behind the attacked basket, a little to the side so the backboard does not hide the play
      const sd = this.flipped ? -1 : 1;
      look = onFloor(-21, 2 * sd, 3);
      pos = onFloor(this.hoop[0] - 22, 14 * sd, 27);
    } else if (presetId === 'top') {  // the coach's board: straight down over the front court, a hair of tilt so the pucks keep their volume
      look = onFloor(-23, 0, 0);
      pos = onFloor(-23, 0, 172); up = new THREE.Vector3(-1, 0, 0);  // straight down, the basket at the top of the frame, no roll
    } else if (presetId === 'rail') {  // over the shoulder of the ball, from the sideline
      look = b;
      pos = new THREE.Vector3(b.x + 24, 30, b.z + 56 * (this.flipped ? -1 : 1));
    } else if (presetId === 'behind') {  // over the shoulder of the man on the ball, looking at the basket; a pass hands the seat to the receiver
      const flying = this.shot && t >= this.shot.i && t <= this.shot.i_end + 40;
      if (flying) this.anchor = this.shot.player; else if (holder) this.anchor = holder;
      const me = (this.anchor && this.xy(this.anchor, t)) || [b.x, b.z];
      let dx = me[0] - this.hoop[0], dy = me[1] - this.hoop[1];
      const dl = Math.hypot(dx, dy) || 1; dx /= dl; dy /= dl;
      const back = flying ? 24 : Math.min(26, 15 + dl * 0.3);
      pos = onFloor(me[0] + dx * back, me[1] + dy * back, flying ? 10 : 13 + dl * 0.1);
      const rimTop = onFloor(this.hoop[0], this.hoop[1], 10);
      look = flying ? b.clone().lerp(rimTop, 0.7) : onFloor(this.hoop[0] + (me[0] - this.hoop[0]) * 0.35, this.hoop[1] + (me[1] - this.hoop[1]) * 0.35, 6);  // in flight: shooter, ball and rim in one frame
      if (flying) { offset = [232, 210]; fov = 48; }
    } else if (presetId === 'eyes') {
      const id = this.eyesOf ?? (this.heldBy[Math.max(0, Math.min(this.n - 1, Math.floor(t)))] || this.d.players[0].id);  // nobody chosen: the man on the ball; through a pass the passer keeps the seat until the catch
      const me = this.xy(id, t) || [b.x, b.z];
      pos = onFloor(me[0], me[1], EYE);
      const target = holder === id ? onFloor(this.hoop[0], 0, 10) : b;  // the rule: on the ball you look at the rim, otherwise at the ball
      let dir = target.clone().sub(pos);
      if (dir.length() < 4 && this.gaze && this.gazeId === id) dir = this.gaze.clone();  // a ball at arm's length, leaving or arriving: hold the gaze rather than stare at it
      dir.y = Math.max(dir.y, -0.25 * dir.length()); dir.normalize();  // never stare at the floor
      if (this.gaze && this.gazeId === id) this.gaze.lerp(dir, 1 - Math.exp(-this.dt / 0.18)).normalize(); else this.gaze = dir;  // the head turns in about a fifth of a second
      this.gazeId = id;
      look = pos.clone().add(this.gaze.clone().multiplyScalar(20));
      pos.add(this.gaze.clone().multiplyScalar(0.5));  // his own body is hidden by the viewer while this camera is on
    } else {  // free
      pos = orbit(this.free.target, this.free.az, this.free.el, this.free.dist); look = this.free.target;
    }
    return { pos, look, fov, offset, up };
  }

  /** Apply the eased camera for this frame; dt in seconds. */
  update(t, ball, holder, dt) {
    this.dt = dt;
    const want = this.pose(t, ball, holder);
    let pos = want.pos, look = want.look, fov = want.fov;
    if (this.from && this.blend < 1) {
      this.blend = Math.min(1, this.blend + dt / EASE_S);
      const k = smooth(this.blend);
      pos = this.from.pos.clone().lerp(want.pos, k); look = this.from.look.clone().lerp(want.look, k); fov = this.from.fov + (want.fov - this.from.fov) * k;
    }
    const liveNow = this.preset === 'auto' ? this.live : this.preset;
    if (liveNow === 'behind' && this.lastPose && this.blend >= 1) {  // a pass hands the seat over in about a third of a second
      const k = 1 - Math.exp(-dt / 0.3);
      pos = this.lastPose.pos.clone().lerp(pos, k); look = this.lastPose.look.clone().lerp(look, k);
    }
    this.camera.up.copy(want.up);
    this.camera.position.copy(pos); this.camera.lookAt(look);
    if (Math.abs(this.camera.fov - fov) > 0.01) { this.camera.fov = fov; this.camera.updateProjectionMatrix(); }
    this.camera.setViewOffset(W, H, this.panel ? want.offset[0] : 0, want.offset[1] - this.shiftY, W, H);
    this.lastPose = { pos: pos.clone(), look: look.clone() };
    const cut = this.preset === 'auto' ? this.cuts.find((c) => t >= c.from && t < c.to) : null;
    return liveNow === 'eyes' ? ((cut && cut.eyesOf) ?? this.eyesOf ?? (this.heldBy[Math.max(0, Math.min(this.n - 1, Math.floor(t)))] || this.d.players[0].id)) : null;  // whose body to hide
  }
}
