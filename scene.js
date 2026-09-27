// The world every screen shares: the renderer, the hall the floor reflects, the lights and the court. A play adds its actors on top;
// the report shows the court empty. One setup, so the three screens are the same place.

import * as THREE from 'three';
import { buildCourt, onFloor } from './court.js';

const W = 1920, H = 1080;

function studio(renderer) {
  // what the glossy floor reflects: a dark hall with a few soft panels of light overhead
  const env = new THREE.Scene();
  env.add(new THREE.Mesh(new THREE.SphereGeometry(200, 32, 16), new THREE.MeshBasicMaterial({ color: 0x04060b, side: THREE.BackSide })));
  const panel = (x, y, z, w, d, k, tint = 0xffffff) => {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshBasicMaterial({ color: new THREE.Color(tint).multiplyScalar(k), side: THREE.DoubleSide }));
    m.position.set(x, y, z); m.lookAt(0, 0, 0); env.add(m);
  };
  panel(-30, 90, -10, 70, 40, 9, 0xfff1dc); panel(40, 80, 30, 50, 30, 4, 0xdfe9ff); panel(-10, 60, -120, 120, 30, 2.5, 0xbfd2ff); panel(0, 40, 140, 160, 20, 1.2, 0xffe2c0);
  const pmrem = new THREE.PMREMGenerator(renderer);
  const tex = pmrem.fromScene(env, 0.035).texture;
  pmrem.dispose();
  return tex;
}

/** Renderer, scene, lights and the court on `canvas`; `court` is the geometry block of a possession file (or court.json); `kit` the home club's, for the floor. */
export function makeScene(canvas, court, kit = null) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance', preserveDrawingBuffer: true });
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.0;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x05080e);
  scene.fog = new THREE.Fog(0x05080e, 150, 300);
  scene.environment = studio(renderer);
  scene.environmentIntensity = 0.55;

  // a long lens from the sideline: deep enough to feel like a hall, flat enough to read distances
  const camera = new THREE.PerspectiveCamera(24, W / H, 1, 600);

  scene.add(new THREE.HemisphereLight(0x9fb6ff, 0x1a120a, 0.42));
  const key = new THREE.SpotLight(0xfff0dc, 5.8, 0, 0.37, 1, 0);
  key.position.set(-24, 95, 16); key.target.position.copy(onFloor(-28, 0, 0));
  scene.add(key, key.target);
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  key.shadow.mapSize.set(2048, 2048); key.shadow.bias = -0.0004; key.shadow.normalBias = 0.04; key.shadow.radius = 5;
  key.shadow.camera.near = 40; key.shadow.camera.far = 160;
  const rim = new THREE.DirectionalLight(0x9cc0ff, 0.9);
  rim.position.set(-60, 40, -80);
  scene.add(rim);
  const fill = new THREE.DirectionalLight(0xe4ebff, 0.32);  // from the broadcast side, low: what the stands bounce back onto the players' fronts
  fill.position.set(20, 30, 120);
  scene.add(fill);

  const floor = buildCourt(court, renderer.capabilities.getMaxAnisotropy(), kit);
  scene.add(floor);
  return { renderer, scene, camera, key, court: floor };
}
