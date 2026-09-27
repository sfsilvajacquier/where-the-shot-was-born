// courtlab viewer. One possession file in, one scene out. No build step: open it with `courtlab serve`.
//   ?chance=<id>   which possession (default: the featured one); without it, the start screen
//   ?i=<frame>     start paused on that frame (stills and deterministic capture use this)
//   ?play=1        start playing

import * as THREE from 'three';
import { onFloor } from './court.js';
import { makeScene } from './scene.js';
import { Actors } from './actors.js';
import { Strip } from './strip.js';
import { Cameras, PRESETS } from './cameras.js';
import { Broadcast } from './broadcast.js';
import { css, LEGEND } from './palette.js';
import { Start } from './start.js';
import { Tabs, dip, short, place, fail } from './ui.js';
import { Story } from './story.js';
import { Hud } from './hud.js';
import { kitOf, badge, SKILLCORNER } from './kits.js';

const W = 1920, H = 1080;
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

const surname = (name) => {
  const parts = name.split(' ');
  return parts.length > 2 && parts[parts.length - 1].length < 4 ? parts.slice(-2).join(' ') : parts[parts.length - 1];
};

async function load() {
  const games = await (await fetch('games/index.json')).json();  // every game with something exported on this machine, for the start screen
  const list = games.flatMap((g) => g.plays);
  if (!list.length) throw new Error('empty');
  let chance = params.get('chance');
  if (!chance || !list.some((r) => r.chance === chance)) chance = (list.find((r) => r.chance === 'chance-191313-1-7') || list[0]).chance;
  const res = await fetch(`possessions/${chance}.json`);
  if (!res.ok) throw new Error(chance);
  const data = await res.json();
  data.__games = games;
  data.__clock = (list.find((r) => r.chance === chance) || {}).clock || '';
  return data;
}

function build(data) {
  // Home and a play are two loads of this same page, told apart by the URL alone, so the floor is simply picked here rather than
  // swapped later: Home is the project's own screen and wears SkillCorner's green and mark; a play is a real match, and keeps the
  // home club's colours the way an arena does.
  const atHome = params.get('start') === '1' || !params.has('chance');
  const { renderer, scene, camera, key, court } = makeScene($('gl'), data.court, atHome ? SKILLCORNER : kitOf(data.game.home));
  const cameras = new Cameras(camera, data, params);
  const azimuth = THREE.MathUtils.degToRad(cameras.num('az', 12));  // the jersey numbers on the pucks face the broadcast seat
  const actors = new Actors(scene, data, azimuth);
  return { renderer, scene, camera, cameras, actors, key, court };
}

function chrome(data) {
  const g = data.game, names = new Map(data.players.map((p) => [p.id, surname(p.name)]));
  $('match').textContent = `${short(g.attack)} ${g.attack === g.away ? 'at' : 'v'} ${short(g.defence)}`;
  $('match').title = `${g.attack} attacking ${g.defence}`;
  badge($('badge-attack'), kitOf(g.attack)); badge($('badge-defence'), kitOf(g.defence));
  $('context').textContent = `${g.competition} · Q${g.period} ${data.__clock} · SkillCorner open data`;
  $('start-eyebrow').textContent = `SkillCorner open data · ${g.competition}`;
  $('score').textContent = `${g.score_before[0]}–${g.score_before[1]}`;
  $('score').parentElement.title = `${g.home} (home) – ${g.away}`;
  $('period').textContent = `Q${g.period}`;
  const w = data.model.normal_spot;
  $('model').textContent = `Normal spot = ${w.man} × his man + ${w.ball} × the ball + ${w.hoop} × the hoop (Franks et al., 2015; refitted here).`;

  const lo = LEGEND[0], hi = LEGEND[LEGEND.length - 1], stops = [];
  for (let k = 0; k <= 42; k += 1) { const f = lo + ((hi - lo) * k) / 42; stops.push(`${css(f)} ${((k / 42) * 100).toFixed(1)}%`); }
  $('ramp').style.background = `linear-gradient(90deg, ${stops.join(',')})`;
  $('ticks').innerHTML = LEGEND.map((f) => `<span style="left:${((f - lo) / (hi - lo)) * 100}%">${f > 0 ? '+' : f < 0 ? '−' : ''}${Math.abs(f)}${f === hi ? ' ft' : ''}</span>`).join('');

  const rows = new Map();
  for (const p of data.players.filter((q) => q.side === 'attack')) {
    const el = document.createElement('div');
    el.className = 'row';
    el.innerHTML = `<span class="num">${p.jersey}</span><span class="who"><span class="name">${names.get(p.id)}</span><span class="by"></span></span><span class="bar"><i></i></span><span class="val"></span>`;
    $('rows').append(el);
    rows.set(p.id, { el, by: el.querySelector('.by'), bar: el.querySelector('i'), val: el.querySelector('.val'), last: '' });
  }

  const labels = new Map();
  for (const p of data.players) {
    const el = document.createElement('div');
    el.className = p.side === 'attack' ? 'label' : 'label def';
    el.innerHTML = `<span class="n" hidden>${p.jersey}</span>${names.get(p.id)}`;
    $('labels').append(el);
    labels.set(p.id, el);
  }

  const shot = data.actions.find((a) => a.type === 'shot');
  let tabChoice = null;  // what the user picked; null = follow the play
  const story = new Story($('tab-story'), data);
  const showTab = (name) => {
    $('tab-marks').hidden = name !== 'marks'; $('tab-story').hidden = name !== 'story';
    $('panel-title').textContent = name === 'story' ? (story.current ? story.current.title : 'Story') : 'Beyond his normal spot';
    document.querySelector('.info').style.visibility = name === 'marks' ? '' : 'hidden';
  };
  const tabs = new Tabs($('tabs'), { onChange: (name) => { tabChoice = name; showTab(name); } });
  let shown = 'marks';
  const setTab = (name) => { shown = name; tabs.set(name); showTab(name); };
  // the card follows the play unless the user chose a tab: Story while a chapter is on; scrubbing back before any chapter forgets the choice
  const follow = (t) => {
    const chapter = story.at(t);
    if (story.render(chapter) && shown === 'story') showTab('story');
    tabs.enable('story', !!chapter);
    if (!chapter) tabChoice = null;
    const want = tabChoice && (tabChoice !== 'story' || chapter) ? tabChoice : chapter ? 'story' : 'marks';
    if (want !== shown) setTab(want);
    return chapter;
  };
  return { names, rows, labels, shot, follow, story };
}

function describe(data, ui, state, t) {
  const pass = data.actions.find((a) => a.type === 'pass' && a.i_end != null && t >= a.i && t <= a.i_end);
  const shot = ui.shot;
  if (shot && t >= shot.i && t <= shot.i_end) return `${ui.names.get(shot.player)} shoots`;
  if (shot && t > shot.i_end) return shot.made ? 'It goes in' : 'It misses';
  if (pass) return `${ui.names.get(pass.from)} passes to ${ui.names.get(pass.to)}`;
  if (state.holder) return `${ui.names.get(state.holder)} on the ball`;
  return 'Ball in the air';
}

async function main() {
  $('stage').classList.add('booting');
  if (params.get('motion') === '0' || matchMedia('(prefers-reduced-motion: reduce)').matches) $('stage').classList.add('nomotion');  // stills and capture: nothing time-based
  await Promise.all([document.fonts.load('800 100px Inter'), document.fonts.load('500 16px Inter'), document.fonts.load('600 16px Inter')]);
  let data;
  try { data = await load(); } catch (e) {
    place($('stage'));
    fail($('stage'), 'Nothing to show yet. Generate the plays and reports on this machine: <code>uv run courtlab report --all</code>, <code>uv run courtlab export --per-game 1</code>, and reload.'
      + '<small>If they are there and this page still shows, the server running is older than the page: stop it and start it again with <code>uv run courtlab serve</code>.</small>');
    return;
  }
  const { renderer, scene, camera, cameras, actors, key, court } = build(data);
  const ui = chrome(data);
  const n = data.frames.idx.length, zero = ui.shot ? ui.shot.i : n - 1;

  let t = params.has('i') ? Number(params.get('i')) : 0, playing = params.get('play') === '1', speed = 1;
  const atStart = params.get('start') === '1' || !params.has('chance');
  const strip = new Strip($('strip'), data, {
    onSeek: (f) => { t = f; },
    onHover: (h) => {
      const tip = $('tip');
      tip.hidden = !h;
      if (!h) return;
      const when = `${h.seconds > 0 ? '+' : '−'}${Math.abs(h.seconds).toFixed(1)} s`;
      tip.innerHTML = h.extra == null ? `<b>${h.name}</b> · ${when}<br>${h.guard ? '' : 'nobody assigned to him'}`
        : `<b>${h.name}</b> ← ${h.guard} · ${when}<br>${h.gap.toFixed(1)} ft apart: <b>${Math.abs(h.extra).toFixed(1)} ft ${h.extra >= 0 ? 'farther' : 'tighter'}</b> than normal`;
      tip.style.left = `${h.x + 14}px`; tip.style.top = `${h.y - 64}px`;
    },
  });

  // the HUD: three levels; the camera picks the default, the user can force one. Inside a level, the card and the strip fold on their own.
  const foldCard = (on) => { $('panel').classList.toggle('folded', on); cameras.panel = !on && !$('stage').classList.contains('nopanel'); fit(); };
  const foldStrip = (on) => { $('strip').parentElement.classList.toggle('folded', on); cameras.shiftY = on ? 96 : 0; fit(); };
  const hud = new Hud($('stage'), {
    onChange: (level) => { $('panel').classList.remove('folded'); cameras.panel = level === 'full'; cameras.shiftY = level === 'full' ? 0 : 96; fit(); },
    onSeek: (f) => { setPlaying(false); t = f; },
  });
  hud.chapterSegments(data.chapters, n);
  $('fold-card').onclick = () => foldCard(!$('panel').classList.contains('folded'));
  $('fold-strip').onclick = () => foldStrip(!$('strip').parentElement.classList.contains('folded'));

  let scale = 1, quality = 1, slow = 0;  // quality: the render scale, stepped down when frames keep running slow (the frame loop); it never steps back up, so it cannot flicker
  const fit = () => {
    scale = Math.min(innerWidth / W, innerHeight / H);
    $('stage').style.transform = `scale(${scale}) translate(-50%, -50%)`;
    const ratio = Math.min(2, Math.max(1, devicePixelRatio * scale));
    renderer.setPixelRatio(Math.max(0.75, ratio * quality));
    renderer.setSize(W, H, false);
    strip.resize(ratio);
    const top = H - 40 - $('strip').parentElement.offsetHeight;
    const lift = $('stage').classList.contains('hud-minimal') ? 28 : 16;  // in Minimal the scrubber sits between the controls and the pill
    $('now').style.bottom = `${H - top + lift}px`;
    $('subtitle').style.bottom = `${H - top + lift}px`;
    $('scrub').style.bottom = `${H - top + 8}px`;
    const bc = $('broadcast'), flip = $('stage').classList.contains('flip'), large = bc.classList.contains('large');
    const readout = document.querySelector('.readout');
    bc.style.bottom = '';
    if (large) { bc.style.width = '816px'; bc.style.left = `${(flip ? 480 : 40) + (1400 - 816) / 2}px`; bc.style.top = `${Math.max(112, top - 16 - 48 - 16 - bc.offsetHeight)}px`; }  // over the court, above the time pill
    else { bc.style.width = '440px'; bc.style.left = `${flip ? 40 : W - 40 - 440}px`; bc.style.top = `${$('stage').classList.contains('nopanel') ? 40 : readout.offsetTop + readout.offsetHeight + 16}px`; }  // in the column, under the marks

  };
  addEventListener('resize', fit);
  // the level at load: ?hud=, else the old ?fold= / ?panel= (both → none, one → minimal), else the camera's default (set with the camera)
  const legacy = (params.get('fold') === '1' ? 1 : 0) + (params.get('panel') === '0' ? 1 : 0);
  const level = params.get('hud') || (legacy === 2 ? 'none' : legacy === 1 ? 'minimal' : null);

  const setPlaying = (on) => {
    playing = on;
    $('playicon').innerHTML = on ? '<path d="M7 5h4v14H7zM13 5h4v14h-4z"/>' : '<path d="M8 5.5v13l11-6.5z"/>';
  };
  setPlaying(playing);
  $('play').onclick = () => { if (!playing && t >= n - 1) t = 0; setPlaying(!playing); };
  // the real footage, only if a clip of this possession sits in ../broadcast (never in the repository, never read as data)
  const broadcast = new Broadcast($('broadcast'), data);
  const chanceId = (data.source && data.source.chance_id) || params.get('chance') || '';
  broadcast.probe(chanceId).then((ok) => {
    if (!ok) return;
    $('bclab').hidden = false;
    $('bc').checked = params.get('bc') === '1';
    const apply = () => { broadcast.show($('bc').checked); };
    $('broadcast').onclick = () => { $('broadcast').classList.toggle('large'); fit(); };
    $('bc').onchange = apply;
    apply();
  });
  let mode = 'pucks';
  const setMode = (m) => {
    mode = m;
    actors.setMode(m);
    cameras.set(cameras.preset, { mode: m });
    renderer.shadowMap.enabled = m === 'figures'; key.castShadow = m === 'figures';
    scene.traverse((o) => { if (o.material) o.material.needsUpdate = true; });
    for (const b of $('view').querySelectorAll('button')) b.setAttribute('aria-checked', String(b.dataset.mode === m));
    $('disclaimer').hidden = m !== 'figures';
    for (const el of ui.labels.values()) el.querySelector('.n').hidden = m !== 'figures';  // on a mannequin the number is hard to read: it joins the name
  };
  for (const b of $('view').querySelectorAll('button')) b.onclick = () => setMode(b.dataset.mode);
  actors.onFiguresReady = (f) => {  // compile their shaders now, in the background and with shadows on, so the switch to Figures costs nothing
    if (mode === 'figures') return;
    f.group.visible = true; renderer.shadowMap.enabled = true; key.castShadow = true;
    renderer.compileAsync(scene, camera).catch(() => {});
    f.group.visible = false; renderer.shadowMap.enabled = false; key.castShadow = false;
  };

  // cameras: a choice, never automatic. ?cam=<preset>&eyes=<playerId>
  const camSel = $('cam'), eyesSel = $('eyes');
  for (const p of PRESETS) if (!p.hidden) camSel.append(new Option(p.label, p.id));
  eyesSel.append(new Option('Whoever has the ball', ''));
  for (const p of data.players) eyesSel.append(new Option(`${p.jersey} ${ui.names.get(p.id)}`, p.id));
  const setCam = (id, eyesOf) => {
    cameras.set(id, { eyesOf: eyesOf === undefined ? cameras.eyesOf : eyesOf });
    hud.forced = false; hud.camera(id);  // a new camera brings its own HUD level, unless the user forces one afterwards
    camSel.value = id;
    eyesSel.hidden = id !== 'eyes';
    $('gl').style.cursor = id === 'free' ? 'grab' : '';
    $('camnote').hidden = id !== 'eyes' && id !== 'auto';
    if (id === 'eyes') eyesSel.value = cameras.eyesOf ? String(cameras.eyesOf) : '';
  };
  camSel.onchange = () => setCam(camSel.value);
  // TV side: the camera sits on the sideline the real broadcast camera sat on, and that is where a play now opens. Half the plays were
  // filmed from the other sideline, so for those the attack runs right instead of left -- which is how they were broadcast. The crest
  // painted at centre court turns with the seat, as an arena's does, so it is upright from wherever the camera is. Unchecking the box
  // crosses to the other sideline; ?tv=0 opens there.
  const tvBox = $('tv');
  tvBox.checked = params.has('tv') ? params.get('tv') === '1' : true;
  // Home keeps its drifting seat whatever the play's TV side was, so its crest never turns.
  const applyTv = () => { cameras.tv = tvBox.checked; $('stage').classList.toggle('flip', cameras.flipped); court.faceCrest(!atStart && cameras.flipped); cameras.set(cameras.preset); fit(); };
  tvBox.onchange = applyTv;
  $('tvlab').title = `On TV this attack ran to the ${data.tv_attack || 'left'}`;
  applyTv();
  for (const k of ['distances', 'path']) {  // layers: off by default, ?layers=distances,path turns them on
    const box = $(`lay-${k}`);
    box.checked = (params.get('layers') || '').split(',').includes(k);
    actors.layers[k] = box.checked;
    box.onchange = () => { actors.layers[k] = box.checked; };
  }
  const distEls = new Map(data.players.filter((p) => p.side === 'attack').map((p) => { const el = document.createElement('div'); el.className = 'dist'; el.hidden = true; $('labels').append(el); return [p.id, el]; }));
  eyesSel.onchange = () => setCam('eyes', eyesSel.value ? Number(eyesSel.value) : null);
  setCam(PRESETS.some((p) => p.id === params.get('cam') && !p.hidden) ? params.get('cam') : 'broadcast', params.has('eyes') ? Number(params.get('eyes')) : null);
  if (level) hud.set(level, true);
  fit();
  let drag = null;
  $('gl').addEventListener('pointerdown', (e) => { if (cameras.preset === 'free') { drag = [e.clientX, e.clientY]; $('gl').setPointerCapture(e.pointerId); } });
  $('gl').addEventListener('pointermove', (e) => { if (drag) { cameras.drag((e.clientX - drag[0]) / scale, (e.clientY - drag[1]) / scale); drag = [e.clientX, e.clientY]; } });
  $('gl').addEventListener('pointerup', () => { drag = null; });
  $('gl').addEventListener('wheel', (e) => { if (cameras.preset === 'free') { e.preventDefault(); cameras.wheel(Math.sign(e.deltaY)); } }, { passive: false });
  setMode(params.get('view') === 'figures' ? 'figures' : 'pucks');
  $('speed').onclick = () => { speed = speed === 1 ? 0.5 : speed === 0.5 ? 0.25 : 1; $('speed').textContent = `${speed}×`; };
  addEventListener('keydown', (e) => {
    if (start.on) { start.key(e); return; }
    if (e.key === 'Escape') { $('back').click(); return; }
    if (e.code === 'Space') { e.preventDefault(); $('play').click(); }
    if (e.code === 'ArrowRight') { setPlaying(false); t = Math.min(n - 1, Math.round(t) + 1); }
    if (e.code === 'ArrowLeft') { setPlaying(false); t = Math.max(0, Math.round(t) - 1); }
    if (e.key === 'h' && !e.metaKey && !e.ctrlKey) hud.cycle();
    if (e.key === 'p' && !e.metaKey && !e.ctrlKey) $('fold-card').click();
    if (e.key === 's' && !e.metaKey && !e.ctrlKey) $('fold-strip').click();
  });

  const v = new THREE.Vector3();
  const screen = (x, y, lift) => { v.copy(onFloor(x, y, lift)).project(camera); return [((v.x + 1) / 2) * W, ((1 - v.y) / 2) * H]; };

  let last = performance.now();
  const frame = (now) => {
    const dt = Math.min(0.1, (now - last) / 1000); last = now;
    if (playing) { slow = dt > 0.026 ? slow + 1 : Math.max(0, slow - 1); if (slow > 45 && quality > 0.5) { quality -= 0.25; slow = 0; fit(); } }  // three quarters of a second under 38 fps: fewer pixels
    if (playing) { t += dt * data.fps * speed; if (t >= n - 1) { t = n - 1; setPlaying(false); } }
    if (start.on) { if (start.restart) { start.restart = false; t = start.loopStart(); } t = start.loop(t, dip); }
    const i0 = Math.max(0, Math.min(n - 1, Math.floor(t))), b0 = data.ball.xyz[i0];
    actors.hideBody(cameras.update(t, b0 && b0[0] != null ? b0 : null, data.holder[i0], dt));
    const state = actors.update(t, camera, now / 1000);

    const at = new Map();
    for (const p of data.players) {
      const xy = actors.xy(p.id, Math.floor(t), Math.min(n - 1, Math.floor(t) + 1), t - Math.floor(t));
      if (xy) at.set(p.id, screen(xy[0], xy[1], 0.5).concat(mode === 'figures' ? screen(xy[0], xy[1], 7.3) : []));
    }
    // names: above the puck if that is free, else below, right or left; an attacker's name wins over a defender's
    const shown = new Set(state.rows.filter((r) => r.guard && r.extra > 5).map((r) => r.guard));
    const placed = [];
    const hit = (a, b) => a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3];
    const order = [...data.players.filter((p) => p.side === 'attack'), ...data.players.filter((p) => p.side !== 'attack')];
    for (const p of order) {
      const el = ui.labels.get(p.id), c = at.get(p.id);
      if (!c || (p.side !== 'attack' && !shown.has(p.id))) { el.style.opacity = 0; continue; }
      const w = el.offsetWidth, h = el.offsetHeight;
      const fig = mode === 'figures';
      const pucks = [...at].filter(([id]) => id !== p.id).map(([, q]) => (fig ? [q[0] - 16, q[3] + 4, q[0] + 16, q[1] + 8] : [q[0] - 24, q[1] - 15, q[0] + 24, q[1] + 15]));
      const spots = (fig ? [[c[2], c[3] - 8 - h / 2], [c[0], c[1] + 18 + h / 2], [c[0] + 30 + w / 2, (c[1] + c[3]) / 2], [c[0] - 30 - w / 2, (c[1] + c[3]) / 2]]
        : [[c[0], c[1] - 24 - h / 2], [c[0], c[1] + 24 + h / 2], [c[0] + 30 + w / 2, c[1]], [c[0] - 30 - w / 2, c[1]]])
        .map(([x, y]) => [x - w / 2 - 2, y - h / 2 - 2, x + w / 2 + 2, y + h / 2 + 2]);
      const cost = (r) => placed.filter((q) => hit(r, q)).length * 3 + pucks.filter((q) => hit(r, q)).length;
      const best = spots.reduce((a, b) => (cost(b) < cost(a) ? b : a));
      if (p.side !== 'attack' && cost(best) > 0) { el.style.opacity = 0; continue; }
      el.style.opacity = 1;
      el.style.left = `${(best[0] + best[2]) / 2}px`; el.style.top = `${(best[1] + best[3]) / 2}px`;
      placed.push(best);
    }

    for (const r of state.rows) {  // the distances layer: feet between each defender and his man, on the band
      const el = distEls.get(r.id), on = actors.layers.distances && r.guard && r.gap != null && r.gap > 5 && r.mid;
      el.hidden = !on;
      if (on) { const q = screen(r.mid[0], r.mid[1], 0.6); el.style.left = `${q[0]}px`; el.style.top = `${q[1]}px`; el.textContent = `${r.gap.toFixed(1)} ft`; }
    }
    const over = state.rows.every((r) => !r.guard);  // SkillCorner assigns nobody to anybody: the play is over, not five men left alone
    for (const r of state.rows) {
      const row = ui.rows.get(r.id);
      const key = r.guard ? `${r.guard}|${r.extra.toFixed(1)}|${r.closing}` : over ? 'over' : 'nobody';
      if (key === row.last) continue;
      row.last = key;
      row.el.classList.toggle('nobody', !r.guard);
      if (!r.guard) { row.by.textContent = over ? 'play over' : 'nobody assigned to him'; row.val.textContent = over ? '–' : 'unguarded'; row.bar.style.width = '0'; continue; }
      row.by.textContent = r.closing ? `${ui.names.get(r.guard)} closing out` : `guarded by ${ui.names.get(r.guard)}`;
      row.val.innerHTML = `${r.extra >= 0 ? '+' : '−'}${Math.abs(r.extra).toFixed(1)}<small>ft</small>`;
      const zeroAt = 6 / 21, e = Math.max(-6, Math.min(15, r.extra));
      row.bar.style.left = `${(e < 0 ? zeroAt + e / 21 : zeroAt) * 100}%`;
      row.bar.style.width = `${(Math.abs(e) / 21) * 100}%`;
      row.bar.style.background = css(r.extra);
    }

    const clock = data.frames.game_clock[state.i], sc = data.frames.shot_clock[state.i];
    $('clock').textContent = clock == null ? '–' : `${Math.floor(clock / 60)}:${String(Math.floor(clock % 60)).padStart(2, '0')}`;
    $('shotclock').textContent = sc == null ? '–' : Math.ceil(sc);
    court.setShotClock(sc == null ? '' : String(Math.ceil(sc)));
    const s = (t - zero) / data.fps;
    $('nowt').textContent = `${s > 0 ? '+' : '−'}${Math.abs(s).toFixed(1)} s`;
    $('nowtext').textContent = describe(data, ui, state, t);
    $('camlive').textContent = cameras.preset === 'auto' && cameras.live ? PRESETS.find((p) => p.id === cameras.live).label : '';
    const chapter = ui.follow(t);
    if (chapter !== strip.chapter) fit();  // the story card's height can change with the chapter (a longer price note); keep the TV clip off it
    strip.chapter = chapter;
    hud.update(t, strip.chapter);

    broadcast.sync(t, playing);
    strip.draw(t);
    renderer.render(scene, camera);
    if (!window.__ready) { window.__ready = true; requestAnimationFrame(() => { $('stage').classList.add('up'); $('stage').classList.remove('booting'); }); }  // the first frame is drawn: fade the stage up
    requestAnimationFrame(frame);
  };
  window.__seek = (f) => { t = f; };

  // three screens, one page each: Home (this page without a chance) lists the games, a game's page lists its plays, and a play comes back to its game
  const go = (url) => dip(() => { location.href = url; });
  const start = new Start($('start'), data, { open: (game) => go(`report.html?game=${game}`), players: () => go('players.html'), refs: () => go('reference.html') });
  const gamePage = `report.html?game=${data.source.game_id}&team=${data.game.defence === data.game.home ? 'home' : 'away'}&focus=play:${data.source.chance_id}`;
  $('back').onclick = () => go(gamePage);
  addEventListener('pageshow', (e) => { if (e.persisted) $('dip').classList.remove('on'); });  // back from a page left mid-dip: the browser restores the dark overlay
  if (atStart) {  // the scene keeps running behind the menu: slow, drifting, looping around the featured shot
    $('stage').classList.add('start');
    speed = 0.5; $('speed').textContent = '0.5×';
    setCam('drift');
    if (!params.has('i')) { t = start.loopStart(); playing = true; }
    start.show();
  }
  requestAnimationFrame(frame);
}

main();
