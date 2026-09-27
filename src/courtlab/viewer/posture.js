// The posture of every player, frame by frame. READ THIS FIRST: the basketball data has no body pose, only where each player stands.
// Everything a body does is GENERATED from what the data does give: position, speed and direction of travel (tracking), who holds
// the ball, every bounce, pass, shot and close-out (SkillCorner's events), and the ball's reconstructed path. It is an illustration
// of the tracking, never a measurement of a body. All figures share one height: heights are not in the data. Every pose is a pure
// function of the frame, so scrubbing and frame-by-frame capture give the same picture. figures.js puts a body on it.

import * as THREE from 'three';
import { onFloor } from './court.js';

const LEG = 3.15;            // ft, hip to floor with the leg straight; the stride is sized to it
const HANDS_UP = 7.5;        // ft, where the hands go on a follow-through
const HAND_UP = 7.3;         // ft, the close-out hand
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = (v, a, b) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const lerp = (a, b, f) => a + (b - a) * f;
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

/** One leg over its stride, by phase: planted, it travels back under the body at the body's own speed (linear, so the foot does not slide); in the air it swings forward with a lift. `a` runs +1 (back) to −1 (front). */
function gait(phi) {
  const u = (((phi + Math.PI / 2) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI)) / Math.PI;  // 0..1 in the air, 1..2 planted
  if (u < 1) { const e = u * u * (3 - 2 * u); return { a: 1 - 2 * e, lift: Math.sin(Math.PI * u), planted: false }; }
  return { a: -1 + 2 * (u - 1), lift: 0, planted: true };
}

export class Posture {
  constructor(data) {
    this.d = data;
    this.n = data.frames.idx.length;
    this.shot = data.actions.find((a) => a.type === 'shot') || null;
    this.closeouts = data.actions.filter((a) => a.type === 'closeout');
    this.picks = data.actions.filter((a) => a.type === 'pick' || a.type === 'screen');
    this.passes = data.actions.filter((a) => a.type === 'pass' && a.i_end != null && a.complete);
    this.kin = new Map(data.players.map((p) => [p.id, this.kinematics(p)]));
  }

  /** Per frame and per player: speed, velocity, where he faces, what he looks at and how far along his stride he is. Computed once. */
  kinematics(p) {
    const d = this.d, n = this.n, xy = p.xy, hoop = d.court.hoop;
    const v = [], speed = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      const a = xy[Math.max(0, i - 2)], b = xy[Math.min(n - 1, i + 2)], dt = (Math.min(n - 1, i + 2) - Math.max(0, i - 2)) / d.fps;
      const vx = a && b && a[0] != null && b[0] != null ? (b[0] - a[0]) / dt : 0, vy = a && b && a[1] != null && b[1] != null ? (b[1] - a[1]) / dt : 0;
      v.push([vx, vy]); speed[i] = Math.hypot(vx, vy);
    }
    const man = new Int32Array(n);  // for a defender: the attacker he is assigned to
    if (p.side === 'defence') for (const [att, g] of Object.entries(d.guard)) for (let i = 0; i < n; i += 1) if (g[i] === p.id) man[i] = Number(att);
    const others = new Map(d.players.map((q) => [q.id, q.xy]));
    const face = [], look = [];
    for (let i = 0; i < n; i += 1) {
      const me = xy[i] && xy[i][0] != null ? xy[i] : [0, 0], ball = d.ball.xyz[i] || [hoop[0], 0, 0];
      let at = d.holder[i] === p.id ? hoop : ball;  // the man on the ball squares up to the basket; everybody else watches the ball…
      if (man[i] && others.get(man[i])[i]) { const m = others.get(man[i])[i]; at = [(m[0] * 2 + ball[0]) / 3, (m[1] * 2 + ball[1]) / 3]; }  // …a defender, mostly his man
      look.push(at);
      let fx = at[0] - me[0], fy = at[1] - me[1];
      const fl = Math.hypot(fx, fy) || 1; fx /= fl; fy /= fl;
      const w = smooth(speed[i], 4, 9), s = speed[i] || 1;  // at a run he faces where he is going
      face.push([lerp(fx, v[i][0] / s, w), lerp(fy, v[i][1] / s, w)]);
    }
    const heading = new Float32Array(n), phase = new Float32Array(n);
    for (let i = 0; i < n; i += 1) {
      let sx = 0, sy = 0;
      for (let k = -7; k <= 7; k += 1) { const j = clamp(i + k, 0, n - 1), g = Math.exp(-0.5 * (k / 3.5) ** 2); sx += face[j][0] * g; sy += face[j][1] * g; }
      heading[i] = Math.atan2(sy, sx);
      if (i) phase[i] = phase[i - 1] + (speed[i] / d.fps / (3.4 + 0.42 * speed[i])) * Math.PI * 2;  // one stride cycle per 3.4 ft + 0.42 ft per ft/s
    }
    return { v, speed, heading, phase, look };
  }

  /**
   * The posture of one player at time t, the same for every body: where he stands and faces (written into `root`), how low he sits,
   * the angle of every limb and where his hands go. Angles follow the primitives' frame: x is his left, z his front; a positive turn
   * about x swings a hanging limb back and tilts the trunk forward. Returns null when he is off the data.
   */
  posture(p, t, ball, holder, root, legLen = LEG) {
    const d = this.d, k = this.kin.get(p.id), i0 = clamp(Math.floor(t), 0, this.n - 1), i1 = Math.min(this.n - 1, i0 + 1), f = t - i0;
    const a = p.xy[i0], b = p.xy[i1];
    if (!(a && a[0] != null)) return null;
    const x = lerp(a[0], b && b[0] != null ? b[0] : a[0], f), y = lerp(a[1], b && b[1] != null ? b[1] : a[1], f);
    const psi = k.heading[i0] + wrap(k.heading[i1] - k.heading[i0]) * f, speed = lerp(k.speed[i0], k.speed[i1], f), phase = lerp(k.phase[i0], k.phase[i1], f);
    const vx = lerp(k.v[i0][0], k.v[i1][0], f), vy = lerp(k.v[i0][1], k.v[i1][1], f);
    const ia = Math.max(0, i0 - 2), ib = Math.min(this.n - 1, i0 + 2), dt = Math.max(1, ib - ia) / d.fps;  // acceleration, for what cloth does
    const ax = (k.v[ib][0] - k.v[ia][0]) / dt, ay = (k.v[ib][1] - k.v[ia][1]) / dt;
    const fwd = (vx * Math.cos(psi) + vy * Math.sin(psi)) / (speed || 1), left = (-vx * Math.sin(psi) + vy * Math.cos(psi)) / (speed || 1);
    const defender = p.side === 'defence', onBall = holder === p.id;
    const onBallD = defender && holder != null && !!d.guard[holder] && d.guard[holder][i0] === p.id;  // guarding the man with the ball: the lowest, widest stance
    root.position.copy(onFloor(x, y, 0));
    root.rotation.y = Math.PI / 2 - psi;

    // stance: defenders and the man on the ball sit lower; everybody sinks a little more as they speed up
    const shooting = this.shot && this.shot.player === p.id && t >= this.shot.i - 14 && t <= this.shot.i + 12;
    const hop = shooting && ball ? clamp(ball[2] - 7.3, 0, 1.3) * smooth(t, this.shot.i - 8, this.shot.i) * (1 - smooth(t, this.shot.i + 4, this.shot.i + 12)) : 0;
    // knee bend (kneeBase, below) is 2*acos((legLen-drop)/legLen): acos is steep near 1, so the old 0.04-0.5 ft range of drop gave a defender
    // a squatting ~65 deg bend, held statically while he shuffled — the duck-walk. These depths keep the deepest stance (closing on the
    // ball) at a defensible ~50 deg and a relaxed attacker at ~20 deg.
    const crouch = (onBallD ? 0.24 : defender ? 0.16 : onBall ? 0.12 : 0.05) + 0.006 * Math.min(speed, 14) - (shooting ? 0.05 : 0);
    const drop = clamp(crouch, 0.03, 0.3), kneeBase = 2 * Math.acos(clamp((legLen - drop) / legLen, 0, 1));
    const lean = clamp(0.05 + 0.022 * speed * Math.max(0, fwd) + (onBallD ? 0.24 : defender ? 0.18 : 0) - (shooting ? 0.1 : 0), -0.1, 0.5);

    // the stride: its length is the one the phase integrates, so the planted foot travels exactly what the body does
    const go = smooth(speed, 0.6, 5.5), cycle = 3.4 + 0.42 * speed;  // full stride only past a jog: a walk into position does not march
    const amp = Math.asin(clamp(cycle / (4 * legLen), 0, 0.85)) * go;
    const bob = 0.05 * Math.abs(Math.sin(phase)) * smooth(speed, 3, 12);
    const steps = { 1: gait(phase), [-1]: gait(phase + Math.PI) };
    const legs = [1, -1].map((side) => {
      const g = steps[side];
      const swing = amp * g.a * fwd, lift = g.lift * (0.35 + 0.07 * Math.min(speed, 16)) * go;
      const apart = (onBallD ? 0.3 : defender ? 0.2 : 0.09) + Math.abs(left) * amp * 0.55 * Math.max(0, -g.a * Math.sign(left || 1) * side);  // sideways it shuffles
      const thigh = swing - kneeBase / 2 - lift * 0.45, knee = kneeBase + lift;
      // -(thigh + knee) cancels the leg chain, so whatever is added here IS the foot's angle to the floor: planted it is flat, in the
      // air it droops by that much and no more. `lift` reaches about 1.47 rad at a sprint, so the old 0.9 of it was pointing the toes
      // some 76° down — the ballet point, on every stride. A small fraction, capped, is a foot that hangs; the cap is what keeps the
      // fastest strides from being the ugliest ones.
      return { side, thigh, knee, apart, foot: -(thigh + knee) + Math.min(lift * 0.18, 0.22) };
    });
    const twist = 0.1 * steps[1].a * go * Math.abs(fwd);  // the pelvis turns with the stride, the shoulders against it
    const sway = 0.05 * -Math.cos(phase) * go;  // the weight over the planted foot
    const arms = [1, -1].map((side) => ({  // swing against the legs; defenders carry them out and up
      side,
      flex: -0.7 * amp * steps[side].a * fwd - (onBallD ? 0.45 : defender ? 0.35 : 0.08),
      abd: side * (onBallD ? 0.9 : defender ? 0.75 : 0.16),
      elbow: -(onBallD ? 1.0 : defender ? 0.9 : 0.35 + 0.05 * Math.min(speed, 14)),
    }));
    const at = k.look[i0], headYaw = clamp(wrap(Math.atan2(at[1] - y, at[0] - x) - psi), -1.1, 1.1);  // the head turns to what he watches, the body keeps its heading

    // hands go where the data says the ball is: dribbling, holding, shooting, catching
    root.updateMatrixWorld(true);
    const reach = [];
    if (ball) {
      const ballW = onFloor(ball[0], ball[1], Math.max(0.45, ball[2]));
      const catching = this.passes.find((q) => t >= q.i_end - 5 && t <= q.i_end + 1);
      const mine = onBall || (catching && catching.to === p.id);
      if (mine && Math.hypot(ball[0] - x, ball[1] - y) < 4.2) {
        const local = root.worldToLocal(ballW.clone());
        const low = ball[2] < 3.0 && onBall && !shooting;  // a bounce: one hand, the one on the ball's side
        for (const side of [1, -1]) if (!low || Math.sign(local.x || 1) === side) reach.push({ side, at: ballW.clone().add(new THREE.Vector3(0, low ? 0.35 : 0, 0)) });
      } else if (this.shot && this.shot.player === p.id && t > this.shot.i && t < this.shot.i + 16) {
        const up = root.localToWorld(new THREE.Vector3(0, HANDS_UP, 1.0));  // the follow-through, held for half a second
        for (const side of [1, -1]) reach.push({ side, at: up });
      }
    }
    const co = this.closeouts.find((c) => c.defender === p.id && t >= c.i + (c.i_end - c.i) * 0.55 && t <= c.i_end + 10);
    if (co) {  // the last steps of a close-out: the hand nearest the shooter goes up
      const sh = d.players.find((q) => q.id === co.player).xy[i0];
      if (sh && sh[0] != null) {
        const side = Math.sign(root.worldToLocal(onFloor(sh[0], sh[1], 5)).x || 1);
        reach.push({ side, at: root.localToWorld(new THREE.Vector3(side * 0.5, HAND_UP, 1.1)) });
      }
    }
    const tuck = !!this.picks.find((q) => q.screener === p.id && Math.abs(t - q.i) <= 12);  // a screen: arms tucked in
    return { seen: !!p.seen[i0], drop, hop, bob, lean, twist, sway, legs, arms, headYaw, reach, tuck, v: [vx, vy], acc: [ax, ay], speed, go, phase };
  }
}
