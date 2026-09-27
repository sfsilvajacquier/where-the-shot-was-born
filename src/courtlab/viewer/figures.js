// The players as figures: one modelled body for everybody, dressed in the club's kit and moved by posture.js. READ posture.js FIRST:
// the data has no body pose, so every pose here is generated from the tracking and the events. The body is Quaternius' "Animated
// Base Character" (assets/models/mannequin.glb, CC0; see assets/models/models.LICENSE): its animation clips are NOT used, only its
// skin and skeleton, which our own posture drives bone by bone. The garments are the body's own triangles pushed outwards (a tank
// top and loose shorts), cut by a distance to the neckline, the armholes and the hems, and printed with the flat drawings of kits.js.
// The body and the garments are built once and shared: a player owns a skeleton, three skinned meshes on the shared geometries, and
// his prints. The figures load in the background as soon as the play does, so the switch to them costs nothing.

import * as THREE from 'three';
import { GLTFLoader } from './vendor/GLTFLoader.js';
import { clone as cloneSkinned } from './vendor/SkeletonUtils.js';
import { Posture } from './posture.js';
import { kitOf, jerseyCanvas, shortsCanvas, clothBump, crestImage } from './kits.js';

const HEIGHT = 6.3;  // ft, one height for everybody: heights are not in the data
const SKIN = new THREE.Color(0xd9d3c7), SOCK = new THREE.Color(0xf1f1ee), SHOE = new THREE.Color(0xe9e9e6), SOLE = new THREE.Color(0x1d2230);
const JOINT_TINT = 0.855;  // the joint rings of the model, a shade darker than the skin around them
const X = new THREE.Vector3(1, 0, 0), Y = new THREE.Vector3(0, 1, 0), Z = new THREE.Vector3(0, 0, 1), DOWN = new THREE.Vector3(0, -1, 0);
const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smooth = (v, a, b) => { const t = clamp((v - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const lerp = (a, b, f) => a + (b - a) * f;
const Q = () => new THREE.Quaternion(), V = () => new THREE.Vector3();
const TQ = new THREE.Quaternion(), TV = new THREE.Vector3(), TV2 = new THREE.Vector3(), TM = new THREE.Matrix4();  // scratch for the per-frame work, never kept

// Where things are on the body at rest, in feet, measured from the model's bones: the cut of the garments is written against them.
const AT = { waist: 3.05, belt: 3.42, hem: 1.93, chest: 4.52, neck: 5.11, shoulder: 4.95, armX: 0.72, spineZ: -0.21, crotch: 2.95, ankle: 0.36 };

/** Signed angles that take a reference direction (down for limbs, up for the spine) to a bone's direction: about +x (flex) and about +z (abduction, towards +x). */
function angles(ref, dir) {
  const c = V().crossVectors(ref, dir), d = ref.dot(dir);
  return { flex: Math.atan2(c.x, d), abd: Math.atan2(c.z, d) };
}

const wrap01 = (u) => u - Math.floor(u);
const around = (x, z) => wrap01((Math.atan2(x, z) - Math.PI / 2) / TAU);  // u around a vertical axis: his left 0, back 0.25, right 0.5, front 0.75

// The two garments: which bones' skin they cover, how far they stand off it, how the print wraps, where the cloth ends (a signed distance in feet, cloth where positive), how much a vertex hangs (0 held, 1 free).
const JERSEY = {
  bones: new Set(['DEF-hips', 'DEF-spine.001', 'DEF-spine.002', 'DEF-spine.003', 'DEF-shoulder.L', 'DEF-shoulder.R']),
  hang: (x, y) => smooth(y, AT.shoulder, AT.waist),
  offset: (h) => 0.02 + 0.015 * h,
  radial: (x, y, z) => [x, 0, z - AT.spineZ],
  hangs: [3.0, 5.4],  // between these heights the cloth hangs from whatever sticks out above it, spanning the hollows
  uv: (x, y, z) => [around(x, z - AT.spineZ), (y - 3.0) / 2.35],
  cut: (x, y, z) => {
    const zz = z - AT.spineZ, ax = Math.abs(x);
    const depth = 0.14 + 0.2 * smooth(Math.cos(Math.atan2(x, zz)), -0.2, 0.8);  // the neckline: shallow at the back, a scoop at the front
    const s = Math.min(1, ax / 0.27), neck = AT.neck + 0.15 - depth * Math.sqrt(1 - s * s) - y;
    const arm = (((ax - AT.armX) / 0.2) ** 2 + ((y - 4.68) / 0.5) ** 2 + (zz / 0.4) ** 2 - 1) * 0.2;  // the armhole: a window on each side, up over the shoulder
    return Math.min(y - AT.waist, neck, arm);
  },
  drag: 0.35,
};
const SHORTS = {
  bones: new Set(['DEF-hips', 'DEF-thigh.L', 'DEF-thigh.R']),
  skinOnly: true,  // from the main skin, not the joint rings: cut into cloth, the hip rings opened at the crease when a thigh lifted
  hang: (x, y) => smooth(y, AT.belt, AT.hem),
  offset: (h) => 0.05 + 0.07 * h,
  radial: (x, y, z) => { const f = clamp((3.17 - y) / 1.3, 0, 1), leg = smooth(y, AT.crotch + 0.1, AT.crotch - 0.1); return [x - Math.sign(x) * lerp(0.28, 0.48, f) * leg, 0, z - lerp(-0.25, lerp(-0.06, 0.45, f), leg)]; },
  uv: (x, y, z) => {  // around the hips, then around each thigh; mirrored on the right leg so the outer side of both legs is u = 0
    const t = smooth(y, AT.crotch + 0.1, AT.crotch - 0.1), ax = Math.abs(x), f = clamp((3.17 - y) / 1.3, 0, 1);
    const hip = Math.atan2(ax, z + 0.25), leg = Math.atan2(ax - lerp(0.28, 0.48, f), z - lerp(-0.06, 0.45, f));
    const th = hip + Math.atan2(Math.sin(leg - hip), Math.cos(leg - hip)) * t;
    return [wrap01((th - Math.PI / 2) / TAU), (y - 1.9) / 1.6];
  },
  cut: (x, y) => Math.min(AT.belt - y, y - AT.hem),
  drag: 0.5,  // the hem swings with speed and stride (Figures.update); the cloth itself follows the leg exactly, or the thigh shows through when it lifts
};

/** Cloth: the print, the weave, a sheen, and the cut with its piping done per pixel from the distance each vertex carries. */
function clothMaterial(canvas, bump, trim, uniforms, base) {
  const map = new THREE.CanvasTexture(canvas);
  map.colorSpace = THREE.SRGBColorSpace; map.wrapS = THREE.RepeatWrapping; map.anisotropy = 8;
  // a little light of its own, in the kit's colour, so a leg swung back (its cloth facing down, away from the key light) keeps its colour instead of going black; a softer sheen, or the forward leg burnt white at a grazing angle
  const m = new THREE.MeshPhysicalMaterial({ map, bumpMap: bump, bumpScale: 0.006, roughness: 0.88, metalness: 0, sheen: 0.22, sheenRoughness: 0.85, sheenColor: new THREE.Color(0xffffff), emissive: new THREE.Color(base), emissiveIntensity: 0.22 });
  m.onBeforeCompile = (sh) => {
    Object.assign(sh.uniforms, uniforms);
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute float sdf; attribute float hang; varying float vSdf; uniform vec3 uDrag;')
      .replace('#include <skinning_vertex>', '#include <skinning_vertex>\ntransformed += uDrag * hang * hang;\nvSdf = sdf;');
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying float vSdf; uniform vec3 uTrim;')
      .replace('#include <map_fragment>', '#include <map_fragment>\nif (vSdf < 0.0) discard;\ndiffuseColor.rgb = mix(uTrim, diffuseColor.rgb, smoothstep(0.04, 0.055, vSdf));');
  };
  m.customProgramCacheKey = () => 'cloth';
  m.userData.uDrag = uniforms.uDrag;  // set per frame by Figures.update
  return { material: m, map };
}

// Skin under cloth is never drawn. The garments are a shell offset from the skin measured in the REST pose, but a lifted thigh folds
// the hip crease and linear-blend skinning collapses the fold, so that shell can end up BEHIND the very skin it covers and the body
// draws over it: that is the long-standing "bare thigh" — the cloth was never missing, only buried. Drawing the covered skin at all
// is what makes the burial visible, so it is cut, the way a game character is not modelled underneath its kit. Each vertex carries
// how deep inside a garment it sits (`under`, built in prepare() from the same `cut` the garments already use); past UNDER_INSET it
// is dropped. The inset is wider than the hem's own swing, so the edge of the cloth always keeps skin behind it.
const UNDER_INSET = 0.18;  // ft inside a garment's edge; SHORTS.drag moves the hem by at most 0.15 ft (capped in update)
const BODY = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.58, metalness: 0 });  // one for everybody: the colours are in the vertices
BODY.onBeforeCompile = (sh) => {
  sh.uniforms.uInset = { value: UNDER_INSET };
  sh.vertexShader = sh.vertexShader
    .replace('#include <common>', '#include <common>\nattribute float under; varying float vUnder;')
    .replace('#include <begin_vertex>', '#include <begin_vertex>\nvUnder = under;');
  sh.fragmentShader = sh.fragmentShader
    .replace('#include <common>', '#include <common>\nvarying float vUnder; uniform float uInset;')
    .replace('#include <clipping_planes_fragment>', '#include <clipping_planes_fragment>\nif (vUnder > uInset) discard;');
};
BODY.customProgramCacheKey = () => 'bodyUnder';
const GHOST = new THREE.MeshStandardMaterial({ color: 0x8e99ad, transparent: true, opacity: 0.35, depthWrite: false, roughness: 0.9 });  // a player nobody saw wears no kit, so his skin is never cut

export class Figures {
  /** `onReady(figures)` fires once the bodies are built (the file loads in the background). */
  constructor(scene, data, onReady = null) {
    this.d = data;
    this.posture = new Posture(data);
    this.group = new THREE.Group();
    this.group.visible = false;
    scene.add(this.group);
    this.bodies = new Map(); this.ready = false;
    this.bump = new THREE.CanvasTexture(clothBump());
    this.bump.wrapS = this.bump.wrapT = THREE.RepeatWrapping; this.bump.repeat.set(24, 18);
    new GLTFLoader().load('assets/models/mannequin.glb', (gltf) => { this.build(gltf.scene, data); if (onReady) onReady(this); });
  }

  build(src, data) {
    const box = new THREE.Box3().setFromObject(src), k = HEIGHT / (box.max.y - box.min.y);
    src.scale.setScalar(k); src.position.y = -box.min.y * k; src.rotation.y = Math.PI;  // the file faces −z; our figures face +z, their left is +x
    src.updateMatrixWorld(true);
    const shared = this.prepare(src), unit = shared.unit;
    for (const p of data.players) {
      const kit = kitOf(p.side === 'attack' ? data.game.attack : data.game.defence);
      const body = cloneSkinned(src);  // his own skeleton; the file's two pieces come along and are swapped for the shared body
      body.updateMatrixWorld(true);
      const pieces = [];
      body.traverse((o) => { if (o.isSkinnedMesh) pieces.push(o); });
      const skeleton = pieces[0].skeleton, slot = pieces[0].parent;
      for (const o of pieces) slot.remove(o);
      const bones = {};
      body.traverse((o) => { if (o.isBone) bones[o.userData.name || o.name] = o; });  // the loader strips the dots from names; userData keeps the file's

      // his prints; the body's material is shared
      const uniforms = { uDrag: { value: V() }, uTrim: { value: new THREE.Color(kit.secondary) } };
      const jersey = clothMaterial(jerseyCanvas(kit, String(p.jersey), null), this.bump, kit.secondary, uniforms, kit.primary);
      crestImage(kit, (img) => { jersey.map.image = jerseyCanvas(kit, String(p.jersey), img); jersey.map.needsUpdate = true; });
      const shorts = clothMaterial(shortsCanvas(kit), this.bump, kit.secondary, { uDrag: { value: V() }, uTrim: uniforms.uTrim }, kit.shorts || kit.primary);
      const mesh = this.skinned(shared.body, BODY, shared, skeleton);
      mesh.castShadow = true;
      const wear = [this.skinned(shared.jersey, jersey.material, shared, skeleton), this.skinned(shared.shorts, shorts.material, shared, skeleton)];
      slot.add(mesh, ...wear);

      // the joints the posture drives: the bone, its rest rotation, the body's axes written in its parent's frame, and how far from straight it rests
      const joint = (name, ref, parent) => {
        const bone = bones[name], inv = bone.parent.getWorldQuaternion(Q()).invert();
        const dir = Y.clone().applyQuaternion(bone.getWorldQuaternion(Q()));
        const a = angles(ref, dir), pa = parent ? angles(ref, Y.clone().applyQuaternion(parent.bone.getWorldQuaternion(Q()))) : { flex: 0, abd: 0 };
        return { bone, rest: bone.quaternion.clone(), lat: X.clone().applyQuaternion(inv), fwd: Z.clone().applyQuaternion(inv), up: Y.clone().applyQuaternion(inv), restFlex: a.flex - pa.flex, restAbd: a.abd - pa.abd };
      };
      const j = { hips: joint('DEF-hips', Y), spine1: joint('DEF-spine.001', Y), spine2: joint('DEF-spine.002', Y), head: joint('DEF-head', Y) };
      j.spine2.restFlex = 0; j.head.restFlex = 0;  // the spine rests as modelled; only the limbs are straightened
      const arms = [[1, 'L'], [-1, 'R']].map(([side, s]) => {
        const upper = joint(`DEF-upper_arm.${s}`, DOWN), fore = joint(`DEF-forearm.${s}`, DOWN, upper);
        return { side, upper, fore, l1: bones[`DEF-forearm.${s}`].position.length() * unit, l2: bones[`DEF-hand.${s}`].position.length() * unit + 0.25 };
      });
      const legs = [[1, 'L'], [-1, 'R']].map(([side, s]) => {
        const thigh = joint(`DEF-thigh.${s}`, DOWN), shin = joint(`DEF-shin.${s}`, DOWN, thigh), foot = joint(`DEF-foot.${s}`, DOWN, shin);
        // the foot bone's rest pose is not a mirrored pair in the source rig: measured restAbd was -0.303 on the left foot and -0.878 on
        // the right (nearly 3x, on a materially different axis) — the model itself isn't symmetric here, not a sign error in this
        // code. Since posture.js never drives foot abduction (always 0), leaving restAbd unzeroed forced a ~50° corrective twist on
        // the right foot alone to cancel out its own bind pose, every frame — that twist is what read as "the right ankle is twisted."
        // restFlex gets the same treatment, but not here: the two feet do not rest at the same slope either (measured -59.3 deg on the
        // left, -69.0 deg on the right), and posture.js drives both from one formula, so zeroing each separately left that 9.7 deg gap
        // riding on every frame -- the right ankle permanently higher than the left, the walk landing on the edge of one foot.
        foot.restAbd = 0;
        return { side, thigh, shin, foot };
      });
      // Bring the right foot onto the left one's rest slope instead of zeroing each: the left keeps exactly the pose it has today and
      // the right answers the same command. Read off the rig, so a new model needs no new constant here.
      const footRest = legs[0].foot.restFlex;
      for (const leg of legs) leg.foot.restFlex -= footRest;
      const legLen = (bones['DEF-shin.L'].position.length() + bones['DEF-foot.L'].position.length()) * unit;
      const holder = new THREE.Group();
      holder.add(body);
      this.group.add(holder);
      this.bodies.set(p.id, { holder, mesh, wear, cloth: [[jersey.material, JERSEY.drag], [shorts.material, SHORTS.drag]], j, arms, legs, unit, legLen, hipRest: bones['DEF-hips'].position.clone() });
    }
    this.ready = true;
  }

  /** A skinned mesh on a shared geometry, placed where the file's pieces were and bound to this body's skeleton. */
  skinned(geometry, material, shared, skeleton) {
    const m = new THREE.SkinnedMesh(geometry, material);
    m.position.copy(shared.position); m.quaternion.copy(shared.quaternion); m.scale.copy(shared.scale);
    m.bind(skeleton, shared.bindMatrix);
    m.receiveShadow = false;  // the body's own shadow map is too coarse for it: it printed the chest's ledge as a dark band
    return m;  // culled by the frustum as any mesh: the shared geometries carry a sphere wide enough for any pose
  }

  /** Once, from the file: its two pieces as one body geometry with skin, socks and shoes painted per vertex, and the garments cut from it. */
  prepare(src) {
    const pieces = [];
    src.traverse((o) => { if (o.isSkinnedMesh) pieces.push(o); });
    const first = pieces[0], names = first.skeleton.bones.map((b) => b.userData.name || b.name);
    const hips = first.skeleton.bones.find((b) => (b.userData.name || b.name) === 'DEF-hips');
    const unit = hips.parent.getWorldScale(V()).y;  // scene feet per bone unit
    const toFirst = first.matrixWorld.clone().invert();  // every piece written in the first piece's frame, where the merged mesh lives
    const P = [], N = [], UV = [], SI = [], SW = [], C = [], I = [], REST = [], DOM = [], JOINT = [];
    const lo = V().setScalar(Infinity), hi = V().setScalar(-Infinity);
    let base = 0;
    for (const mesh of pieces) {
      const geo = mesh.geometry, n = geo.attributes.position.count, joint = mesh.material.name === 'M_Joints';
      const rel = toFirst.clone().multiply(mesh.matrixWorld), relN = new THREE.Matrix3().getNormalMatrix(rel);
      const pos = geo.attributes.position, nor = geo.attributes.normal, uv = geo.attributes.uv, si = geo.attributes.skinIndex, sw = geo.attributes.skinWeight;
      const v = V(), w = V();
      for (let i = 0; i < n; i += 1) {
        v.fromBufferAttribute(pos, i).applyMatrix4(rel); P.push(v.x, v.y, v.z);
        w.fromBufferAttribute(nor, i).applyMatrix3(relN).normalize(); N.push(w.x, w.y, w.z);
        UV.push(uv ? uv.getX(i) : 0, uv ? uv.getY(i) : 0);
        let best = 0, bw = -1;
        for (let s = 0; s < 4; s += 1) { const ws = sw.getComponent(i, s); SI.push(si.getComponent(i, s)); SW.push(ws); if (ws > bw) { bw = ws; best = si.getComponent(i, s); } }
        const owner = names[best];
        DOM.push(owner); JOINT.push(joint);
        mesh.getVertexPosition(i, v).applyMatrix4(rel);  // where the skin renders at rest, in the first piece's frame…
        lo.min(v); hi.max(v);
        v.applyMatrix4(first.matrixWorld); REST.push(v.x, v.y, v.z);  // …and in the body's frame (feet, his left +x, up +y, front +z)
        let c = SKIN;
        if (owner === 'DEF-foot.L' || owner === 'DEF-foot.R' || owner === 'DEF-toe.L' || owner === 'DEF-toe.R' || v.y < AT.ankle + 0.05) c = v.y < 0.12 ? SOLE : SHOE;
        else if ((owner === 'DEF-shin.L' || owner === 'DEF-shin.R') && v.y < AT.ankle + 0.6) c = SOCK;
        const tint = joint ? JOINT_TINT : 1;
        C.push(c.r * tint, c.g * tint, c.b * tint);
      }
      const idx = geo.index.array;
      for (let t = 0; t < idx.length; t += 1) I.push(idx[t] + base);
      base += n;
    }
    const body = new THREE.BufferGeometry();
    body.setAttribute('position', new THREE.Float32BufferAttribute(P, 3)); body.setAttribute('normal', new THREE.Float32BufferAttribute(N, 3));
    body.setAttribute('uv', new THREE.Float32BufferAttribute(UV, 2)); body.setAttribute('color', new THREE.Float32BufferAttribute(C, 3));
    body.setAttribute('skinIndex', new THREE.Float32BufferAttribute(SI, 4)); body.setAttribute('skinWeight', new THREE.Float32BufferAttribute(SW, 4));
    body.setIndex(I);
    const rest = Float32Array.from(REST);
    // how deep inside a garment each skin vertex sits, from that garment's own `cut`: the BODY material drops anything past
    // UNDER_INSET (see above). A vertex only counts as covered when its dominant bone is one the garment is cut from, or an arm
    // hanging at hip height would read as "inside the shorts" purely from its y.
    const UNDER = new Float32Array(DOM.length);
    for (let i = 0; i < DOM.length; i += 1) {
      const x = rest[i * 3], y = rest[i * 3 + 1], z = rest[i * 3 + 2];
      let deepest = -1;
      for (const spec of [JERSEY, SHORTS]) if (spec.bones.has(DOM[i])) deepest = Math.max(deepest, spec.cut(x, y, z));
      UNDER[i] = deepest;
    }
    body.setAttribute('under', new THREE.BufferAttribute(UNDER, 1));
    const nrm = new THREE.Matrix3().getNormalMatrix(first.matrixWorld), back = nrm.clone().invert();  // the first piece's frame to the body's and back
    const jersey = this.garment(body, rest, DOM, JOINT, JERSEY, unit, nrm, back), shorts = this.garment(body, rest, DOM, JOINT, SHORTS, unit, nrm, back);
    const sphere = new THREE.Sphere(lo.clone().add(hi).multiplyScalar(0.5), hi.distanceTo(lo) * 0.5 * 1.7);  // the rest body, with room for arms up and a stride
    for (const g of [body, jersey, shorts]) g.boundingSphere = sphere.clone();
    return { body, jersey, shorts, unit, bindMatrix: first.bindMatrix.clone(), position: first.position.clone(), quaternion: first.quaternion.clone(), scale: first.scale.clone() };
  }

  /** One garment: the body's triangles owned by `spec.bones`, pushed out along their normals, printed, cut and hung. */
  garment(body, rest, dom, joint, spec, unit, nrm, back) {
    const idx = body.index.array, pos = body.attributes.position, nor = body.attributes.normal, si = body.attributes.skinIndex, sw = body.attributes.skinWeight;
    const tris = [];
    for (let t = 0; t < idx.length; t += 3) if (spec.bones.has(dom[idx[t]]) && spec.bones.has(dom[idx[t + 1]]) && spec.bones.has(dom[idx[t + 2]]) && !(spec.skinOnly && joint[idx[t]])) tris.push(idx[t], idx[t + 1], idx[t + 2]);
    // cloth under tension spans the hollows of the body: a vertex is pushed out to the widest radius found at its height or a little above
    let span = () => 0;
    if (spec.hangs) {
      const NA = 72, NY = 60, [y0, y1] = spec.hangs, grid = new Float32Array(NA * NY);
      const cell = (i) => { const r = spec.radial(rest[i * 3], rest[i * 3 + 1], rest[i * 3 + 2]); return [((Math.floor(((Math.atan2(r[0], r[2]) + Math.PI) / TAU) * NA) % NA) + NA) % NA, clamp(Math.floor(((rest[i * 3 + 1] - y0) / (y1 - y0)) * NY), 0, NY - 1), Math.hypot(r[0], r[2])]; };
      for (const i of tris) { const [a, b, r] = cell(i); grid[b * NA + a] = Math.max(grid[b * NA + a], r); }
      span = (i) => {
        const [a, b, r] = cell(i);
        let m = 0;
        for (let db = 0; db <= 2; db += 1) for (let da = -1; da <= 1; da += 1) m = Math.max(m, grid[clamp(b + db, 0, NY - 1) * NA + (a + da + NA) % NA]);
        return Math.max(0, m - 0.012 - r);
      };
    }
    const n = tris.length, P = new Float32Array(n * 3), N = new Float32Array(n * 3), UV = new Float32Array(n * 2), SI = new Float32Array(n * 4), SW = new Float32Array(n * 4), SDF = new Float32Array(n), HANG = new Float32Array(n);
    for (let k = 0; k < n; k += 1) {
      const i = tris[k], x = rest[i * 3], y = rest[i * 3 + 1], z = rest[i * 3 + 2], h = spec.hang(x, y);
      const recess = joint[i] ? -0.012 : 0;  // the joint rings' cloth sits just under the body's, filling the gaps between the pieces without standing out
      const d = (spec.offset(h) + recess + span(i)) / unit;
      // the cloth's normal: the skin's, pulled towards the radial direction of the garment, so ledges and grooves of the body do not print through
      const r = spec.radial(x, y, z), rl = Math.hypot(r[0], r[1], r[2]) || 1;
      const skin = V().set(nor.getX(i), nor.getY(i), nor.getZ(i)).applyMatrix3(nrm).normalize(), wr = rl < 0.12 ? 0 : skin.y < 0 ? 0.92 : 0.6;  // under a ledge the skin faces down; cloth spans it; on the axis itself only the skin's normal means anything
      const nw = skin.multiplyScalar(1 - wr).add(V().set(r[0] / rl, r[1] / rl, r[2] / rl).multiplyScalar(wr)); nw.y += 0.28; nw.normalize();  // tilted upwards: cloth catches the light from above whichever way the limb swings
      const nb = nw.clone().applyMatrix3(back).normalize();  // back in the mesh's frame
      P[3 * k] = pos.getX(i) + nb.x * d; P[3 * k + 1] = pos.getY(i) + nb.y * d; P[3 * k + 2] = pos.getZ(i) + nb.z * d;
      N[3 * k] = nb.x; N[3 * k + 1] = nb.y; N[3 * k + 2] = nb.z;
      const [u, vv] = spec.uv(x, y, z); UV[2 * k] = u; UV[2 * k + 1] = vv;
      SDF[k] = spec.cut(x, y, z); HANG[k] = h;
      for (let s = 0; s < 4; s += 1) { SI[4 * k + s] = si.getComponent(i, s); SW[4 * k + s] = sw.getComponent(i, s); }
    }
    for (let k = 0; k < n; k += 3) {  // a triangle across the seam of the print: carry the low side over, the texture repeats
      const us = [UV[2 * k], UV[2 * k + 2], UV[2 * k + 4]];
      if (Math.max(...us) - Math.min(...us) > 0.5) for (let s = 0; s < 3; s += 1) if (us[s] < 0.5) UV[2 * (k + s)] += 1;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(P, 3)); g.setAttribute('normal', new THREE.BufferAttribute(N, 3)); g.setAttribute('uv', new THREE.BufferAttribute(UV, 2));
    g.setAttribute('skinIndex', new THREE.BufferAttribute(SI, 4)); g.setAttribute('skinWeight', new THREE.BufferAttribute(SW, 4));
    g.setAttribute('sdf', new THREE.BufferAttribute(SDF, 1)); g.setAttribute('hang', new THREE.BufferAttribute(HANG, 1));
    return g;
  }

  setVisible(on) { this.group.visible = on; }
  hide(id) { this.hiddenId = id; }

  /** Turn a joint from its straightened rest: flex about the body's lateral axis, abduction about its forward axis, yaw about its up axis. */
  pose(j, flex, abd = 0, yaw = 0) {
    j.bone.quaternion.setFromAxisAngle(j.lat, flex - j.restFlex);
    if (abd - j.restAbd) j.bone.quaternion.multiply(TQ.setFromAxisAngle(j.fwd, abd - j.restAbd));
    if (yaw) j.bone.quaternion.multiply(TQ.setFromAxisAngle(j.up, yaw));
    j.bone.quaternion.multiply(j.rest);
  }

  /** Point a bone (its +y runs along it) at a world direction, keeping the rest twist. */
  aim(j, dirWorld) {
    const local = TV.copy(dirWorld).applyQuaternion(j.bone.parent.getWorldQuaternion(TQ).invert());
    j.bone.quaternion.setFromUnitVectors(TV2.copy(Y).applyQuaternion(j.rest), local).multiply(j.rest);
  }

  /** Two-bone reach: the hand of `arm` on a world point, clamped to what the arm can reach. */
  reach(b, arm, world) {
    const S = arm.upper.bone.getWorldPosition(V()), t = world.clone().sub(S), max = arm.l1 + arm.l2;
    let d = t.length();
    if (d > max) { t.multiplyScalar(max / d); d = max; }
    d = Math.max(d, 0.4);
    const dir = t.clone().normalize();
    const pole = new THREE.Vector3(arm.side * 0.7, -0.45, -0.55).applyQuaternion(b.holder.quaternion);  // the elbow goes out, down and back
    const axis = V().crossVectors(dir, pole);
    if (axis.lengthSq() < 1e-6) axis.set(arm.side, 0, 0); else axis.normalize();
    const a = Math.acos(clamp((arm.l1 ** 2 + d * d - arm.l2 ** 2) / (2 * arm.l1 * d), -1, 1));
    this.aim(arm.upper, dir.clone().applyAxisAngle(axis, a));
    this.aim(arm.fore, S.clone().add(t).sub(arm.fore.bone.getWorldPosition(V())).normalize());
  }

  update(t, ball, holder) {
    if (!this.ready) return;
    for (const p of this.d.players) {
      const b = this.bodies.get(p.id), pose = p.id === this.hiddenId ? null : this.posture.posture(p, t, ball, holder, b.holder, b.legLen);
      b.holder.visible = !!pose;
      if (!pose) continue;
      // a player the cameras did not see is a ghost: the body alone, grey and translucent
      b.mesh.material = pose.seen ? BODY : GHOST;
      for (const g of b.wear) g.visible = pose.seen;
      b.j.hips.bone.position.copy(b.hipRest).addScaledVector(b.j.hips.up, (pose.hop + pose.bob - pose.drop) / b.unit).addScaledVector(b.j.hips.lat, pose.sway / b.unit);
      this.pose(b.j.hips, 0, 0, pose.twist);
      this.pose(b.j.spine1, pose.lean * 0.5, 0, -0.8 * pose.twist); this.pose(b.j.spine2, pose.lean * 0.5, 0, -0.8 * pose.twist);
      this.pose(b.j.head, -pose.lean * 0.7, 0, pose.headYaw);
      for (let i = 0; i < 2; i += 1) {
        const leg = b.legs[i], l = pose.legs[i];
        this.pose(leg.thigh, l.thigh, l.side * l.apart); this.pose(leg.shin, l.knee); this.pose(leg.foot, l.foot);
        const arm = b.arms[i], a = pose.arms[i];
        this.pose(arm.upper, a.flex, a.abd * 0.7); this.pose(arm.fore, a.elbow);  // a little less out than the angles say: this body reads them literally
      }
      b.holder.updateMatrixWorld(true);
      for (const r of pose.reach) this.reach(b, b.arms.find((arm) => arm.side === r.side), r.at);
      if (pose.tuck) for (const arm of b.arms) { this.pose(arm.upper, -0.5, arm.side * 0.15); this.pose(arm.fore, -2.0); }
      // cloth: the hems trail his speed and his changes of speed, bounce with the stride and lag the jump; written in the mesh's own frame
      const drag = TV.set(-(pose.v[0] * 0.012 + pose.acc[0] * 0.004), 0.025 * Math.sin(2 * pose.phase) * pose.go - 0.12 * pose.hop, -(pose.v[1] * 0.012 + pose.acc[1] * 0.004));
      if (drag.length() > 0.15) drag.setLength(0.15);  // never more than the hem stands off the skin: a hem blown back into the forward thigh would show the thigh through the cloth
      TM.copy(b.mesh.matrixWorld).invert();
      drag.applyMatrix4(TM).sub(TV2.set(0, 0, 0).applyMatrix4(TM));
      for (const [material, k] of b.cloth) material.userData.uDrag.value.copy(drag).multiplyScalar(k);
    }
  }
}
