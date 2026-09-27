// The players page. Every player of the games on this machine, one point per player and game. The chart asks one of five questions a
// coach would ask (or plots any pair of metrics); the profile of the focused point is a scouting card, every row with a strip of all
// the players shown and his mark on it; a second player can be pinned to compare. Numbers come from the rosters (courtlab roster)
// and nothing else. Colour follows the project's one rule: only "feet beyond his normal spot" is coloured, with the tension palette.
//   ?view=making|discipline|closeouts|workload|creation|custom   ?x=<metric>&y=<metric> (custom)   ?team=<name>   ?min=10|20
//   ?focus=<player id>:<game id>   ?pin=<player id>:<game id>

import * as THREE from 'three';
import { onFloor } from './court.js';
import { makeScene } from './scene.js';
import { Tabs, keys, short, dip, place, fail } from './ui.js';
import { kitOf, badge } from './kits.js';
import { css } from './palette.js';

const W = 1920, H = 1080, PW = 1180, PH = 560, PAD = { l: 76, r: 32, t: 24, b: 52 };
const REFS = '<a class="reflink" href="reference.html">References \u2192</a>';  // what every name on the page means, and whose figure it is
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const signed = (v, nd) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(nd);
const pct = (a, b) => (b ? `${Math.round((100 * a) / b)} %` : '–');
const mmss = (m) => `${Math.floor(m)}:${String(Math.round((m % 1) * 60)).padStart(2, '0')}`;
const date = (iso) => new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const orbit = (target, azDeg, elDeg, dist) => {
  const az = THREE.MathUtils.degToRad(azDeg), el = THREE.MathUtils.degToRad(elDeg);
  return new THREE.Vector3(target.x + dist * Math.cos(el) * Math.sin(az), dist * Math.sin(el), target.z + dist * Math.cos(el) * Math.cos(az));
};

// the metrics: a value per row (null when the sample is too small to mean anything), its unit, how it is written, which way is good
const M = {
  minutes: { label: 'Minutes on the tracked play', unit: 'min', of: (r) => r.minutes, fmt: (v) => mmss(v), good: 'high' },
  ft_per_min: { label: 'Feet per minute', unit: 'ft/min', of: (r) => r.ft_per_min, fmt: (v) => String(Math.round(v)), good: 'high' },
  distance_ft: { label: 'Distance covered', unit: 'ft', of: (r) => r.distance_ft, fmt: (v) => Math.round(v).toLocaleString('en-GB'), good: 'high' },
  top_speed: { label: 'Top speed', unit: 'ft/s', of: (r) => r.top_speed, fmt: (v) => v.toFixed(1), good: 'high' },
  extra: { label: 'Beyond his normal spot, mean', unit: 'ft', of: (r) => r.extra, fmt: (v) => signed(v, 1), colour: true, good: 'low', lowerIsTighter: true },
  within_3: { label: 'Within 3 ft of his normal spot', unit: '% of the time', of: (r) => (r.within_3 == null ? null : 100 * r.within_3), fmt: (v) => `${Math.round(v)}`, good: 'high' },
  closeouts: { label: 'Close-outs', unit: 'count', of: (r) => r.closeouts, fmt: (v) => String(v), good: 'high' },
  co_end: { label: 'Where his close-outs arrived', unit: 'ft  (3 or more)', of: (r) => r.co_end, fmt: (v) => v.toFixed(1), good: 'low' },
  co_pts: { label: 'Points after his close-outs', unit: 'pts/poss  (3 or more)', of: (r) => r.co_pts, fmt: (v) => v.toFixed(2), good: 'low' },
  conceded: { label: 'Shots conceded as nearest defender', unit: 'count', of: (r) => r.conceded, fmt: (v) => String(v), good: 'low' },
  conceded_made: { label: 'Conceded shots made', unit: '%  (5 or more)', of: (r) => (r.conceded >= 5 ? (100 * r.conceded_made) / r.conceded : null), fmt: (v) => `${Math.round(v)}`, good: 'low' },
  conc_dist: { label: 'His distance at those releases', unit: 'ft  (3 or more)', of: (r) => r.conc_dist, fmt: (v) => v.toFixed(1), good: 'low' },
  price: { label: 'What his rotations cost', unit: 'pts', of: (r) => r.price, fmt: (v) => signed(v, 2), good: 'low' },
  price_per_conceded: { label: 'Cost per shot conceded', unit: 'pts  (3 or more)', of: (r) => r.price_per_conceded, fmt: (v) => signed(v, 2), good: 'low' },
  shots: { label: 'Shots', unit: 'count', of: (r) => r.shots, fmt: (v) => String(v), good: 'high' },
  fg: { label: 'Field goals made', unit: '%  (5 or more shots)', of: (r) => (r.shots >= 5 ? (100 * r.made) / r.shots : null), fmt: (v) => `${Math.round(v)}`, good: 'high' },
  quality: { label: 'Quality of his looks', unit: '%  (5 or more shots)', of: (r) => (r.shots >= 5 && r.quality != null ? r.quality : null), fmt: (v) => `${Math.round(v)}`, good: 'high' },
  points: { label: 'Points from the field', unit: 'pts', of: (r) => r.points, fmt: (v) => String(v), good: 'high' },
  assists: { label: 'Assists', unit: 'count', of: (r) => r.assists, fmt: (v) => String(v), good: 'high' },
  turnovers: { label: 'Turnovers', unit: 'count', of: (r) => r.turnovers, fmt: (v) => String(v), good: 'low' },
  season_three: { label: 'Season threes', unit: '%  (40 or more, SkillCorner)', of: (r) => (r.season_three && r.season_three[1] >= 40 ? (100 * r.season_three[0]) / r.season_three[1] : null), fmt: (v) => `${Math.round(v)}`, good: 'high' },
  season_cns: { label: 'Season catch-and-shoot threes', unit: '%  (40 or more, SkillCorner)', of: (r) => (r.season_cns_three && r.season_cns_three[1] >= 40 ? (100 * r.season_cns_three[0]) / r.season_cns_three[1] : null), fmt: (v) => `${Math.round(v)}`, good: 'high' },
};

// the questions: axes, a reference and one line that says how to read it. Pairs with no signal in these games are not offered.
const VIEWS = {
  discipline: { title: 'Discipline and its price', x: 'extra', y: 'price', ref: 'means', question: '<b>Feet beyond his normal spot, and what his rotations cost.</b> The further he roams, the more he tends to pay; the dashed lines are the means of the players shown.' },
  making: { title: 'Shot making vs shot selection', x: 'quality', y: 'fg', ref: 'diagonal', question: '<b>What his looks were worth, and what he made of them.</b> Above the line he converted more than the quality of his shots said; below it, less. Five shots or more.' },
  closeouts: { title: 'Who closes out, who pays', x: 'closeouts', y: 'price_per_conceded', ref: 'means', question: '<b>How often he ran to close out, and what each shot he conceded cost.</b> The bill for a rotation goes to the man who runs; the cost per shot separates the runner from the late one.' },
  workload: { title: 'Workload', x: 'minutes', y: 'ft_per_min', ref: 'means', question: '<b>Minutes on the tracked play, and how hard they were run.</b> Feet per minute is the intensity; the range in these games is narrow, so a few feet mean a lot.' },
  creation: { title: 'Creation', x: 'turnovers', y: 'assists', ref: 'diagonal', question: '<b>Assists against turnovers.</b> Above the line he created more than he gave away.' },
  custom: { title: 'Custom', x: null, y: null, ref: 'means', question: 'Any two metrics. Pairs that showed no relation in these games (top speed against anything, the season against one game) are here for looking, not for concluding.' },
};

async function load() {
  const d = await (await fetch('players/index.json')).json();
  if (!d.rows || !d.rows.length) throw new Error('empty');
  if (d.schema !== 'courtlab.players/2') throw new Error('stale');  // an index without the derived metrics: the server running is older than this page
  const court = await (await fetch('court.json')).json();
  return { d, court };
}

function scale(values, lo, hi, includeZero = false) {  // a nice linear scale with round ticks
  let min = Math.min(...values), max = Math.max(...values);
  if (includeZero) { min = Math.min(min, 0); max = Math.max(max, 0); }
  const span = max - min || 1;
  const step = [1, 2, 2.5, 5, 10].map((k) => k * 10 ** Math.floor(Math.log10(span / 4))).find((s) => span / s <= 6) || span / 4;
  const a = Math.floor(min / step) * step, b = Math.ceil(max / step) * step;
  const ticks = []; for (let v = a; v <= b + 1e-9; v += step) ticks.push(+v.toFixed(6));
  return { a, b, to: (v) => lo + ((v - a) / (b - a || 1)) * (hi - lo), ticks };
}

async function main() {
  $('stage').classList.add('booting');
  place($('stage'));
  const still = params.get('motion') === '0' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) $('stage').classList.add('nomotion');
  await Promise.all([document.fonts.load('700 48px Inter'), document.fonts.load('500 16px Inter'), document.fonts.load('600 16px Inter')]);
  let d, court;
  try { ({ d, court } = await load()); } catch (e) {
    fail($('stage'), e.message === 'stale' ? 'The server running is older than this page. Stop it and start it again: <code>uv run courtlab serve</code>, then reload.'
      : 'No players to show yet. Write the rosters on this machine: <code>uv run courtlab report --all</code> and reload.<small>If they are there and this page still shows, the server running is older than the page: stop it and start it again with <code>uv run courtlab serve</code>.</small>');
    return;
  }

  const { renderer, scene, camera } = makeScene($('gl'), court);
  camera.fov = 26; camera.updateProjectionMatrix();
  const target = onFloor(-22, 0, 2);
  const fit = () => {
    const scale_ = Math.min(innerWidth / W, innerHeight / H);
    $('stage').style.transform = `scale(${scale_}) translate(-50%, -50%)`;
    renderer.setPixelRatio(Math.min(2, Math.max(1, devicePixelRatio * scale_)));
    renderer.setSize(W, H, false);
  };
  addEventListener('resize', fit); fit();

  const rows = d.rows, teams = [...new Set(rows.map((r) => r.team))].sort();
  $('context').innerHTML = `${new Set(rows.map((r) => r.id)).size} players in ${d.games} games · one point per player and game · SkillCorner open data · ${REFS}`;
  for (const [id, v] of Object.entries(VIEWS)) $('view').append(new Option(v.title, id));
  for (const sel of [$('x'), $('y')]) for (const k of Object.keys(M)) sel.append(new Option(M[k].label, k));
  $('team').append(new Option('Every team', ''));
  for (const t of teams) $('team').append(new Option(short(t), t));
  const state = { view: VIEWS[params.get('view')] ? params.get('view') : 'discipline', x: M[params.get('x')] ? params.get('x') : 'quality', y: M[params.get('y')] ? params.get('y') : 'fg',
                  team: teams.includes(params.get('team')) ? params.get('team') : '', min: params.get('min') === '20' ? 20 : 10, focus: params.get('focus'), pin: params.get('pin') };
  const axes = () => (state.view === 'custom' ? { x: state.x, y: state.y } : { x: VIEWS[state.view].x, y: VIEWS[state.view].y });
  const syncControls = () => { const a = axes(); $('view').value = state.view; $('x').value = a.x; $('y').value = a.y; $('team').value = state.team; for (const c of document.querySelectorAll('.ctl.custom')) c.hidden = state.view !== 'custom'; };
  const mins = new Tabs($('mins'), { attr: 'aria-checked', onChange: (v) => { state.min = Number(v); sync(); render(); } });
  mins.set(String(state.min));
  const svg = $('svg'), NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs, text) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };
  const key = (r) => `${r.id}:${r.game}`;
  const byKey = (k) => rows.find((r) => key(r) === k) || null;
  let pool = [], shown = [], order = [];

  // the scouting card: every metric as a row with a strip of the players shown and his mark, and the share of them he beats
  const CARD = ['minutes', 'ft_per_min', 'top_speed', 'fg', 'quality', 'points', 'extra', 'within_3', 'closeouts', 'co_end', 'price', 'price_per_conceded', 'season_three'];  // plus the chart's own two axes when they are not here
  const strip = (m, mine, pinned) => {
    const vals = pool.map(m.of).filter((v) => v != null);
    if (mine == null || vals.length < 2) return { html: '<span class="strip"></span>', beat: null };
    const lo = Math.min(...vals), hi = Math.max(...vals), x = (v) => 4 + ((v - lo) / (hi - lo || 1)) * 142;
    const beat = vals.filter((v) => (m.good === 'high' ? v < mine : v > mine)).length / vals.length;
    const ticks = vals.map((v) => `<line class="others" x1="${x(v).toFixed(1)}" x2="${x(v).toFixed(1)}" y1="3" y2="11"/>`).join('');
    const pin = pinned == null ? '' : `<line class="pinned" x1="${x(pinned).toFixed(1)}" x2="${x(pinned).toFixed(1)}" y1="0" y2="14"/>`;
    return { html: `<span class="strip" title="the players shown, low to high; his mark in white${pinned == null ? '' : ', the pinned player dashed'}"><svg viewBox="0 0 150 14">${ticks}${pin}<line class="mine" x1="${x(mine).toFixed(1)}" x2="${x(mine).toFixed(1)}" y1="0" y2="14"${m.colour ? ` style="stroke:${css(mine)}"` : ''}/></svg></span>`, beat };
  };
  const profile = (r) => {
    const p = state.pin ? byKey(state.pin) : null;
    $('p-num').textContent = `#${r.jersey}`; $('p-name').textContent = r.name;
    $('p-sub').textContent = `${short(r.team)} ${r.side === 'home' ? 'v' : 'at'} ${short(r.opponent)} · ${date(r.date)}`;
    badge($('p-badge'), kitOf(r.team));
    $('pinline').hidden = !p; if (p) $('pinline').innerHTML = `Compared with <b>${p.name}</b> · ${short(p.team)} ${p.side === 'home' ? 'v' : 'at'} ${short(p.opponent)} · the dashed mark on every strip`;
    $('caption').textContent = `Each strip: the ${pool.length} players shown, low to high, his mark in white; the grey figure is the share of them he beats.`;
    const a = axes(), cardRows = [...CARD, ...[a.x, a.y].filter((k) => !CARD.includes(k))];
    $('p-rows').innerHTML = cardRows.map((k) => {
      const m = M[k], v = m.of(r), s = strip(m, v, p && p !== r ? m.of(p) : null);
      const val = v == null ? '–' : `${m.colour ? `<b style="color:${css(v)}">${m.fmt(v)}</b>` : m.fmt(v)}${s.beat == null ? '' : `<em>${Math.round(100 * s.beat)} %</em>`}`;
      return `<div class="row metric"><span class="k">${m.label}</span>${s.html}<span class="v" title="${s.beat == null ? '' : `${m.good === 'high' ? 'higher' : 'better'} than ${Math.round(100 * s.beat)} % of the players shown`}">${val}</span></div>`;
    }).join('');
  };
  const tip = $('tip');
  const showTip = (r, x, y) => {
    const a = axes(), mx = M[a.x], my = M[a.y], vx = mx.of(r), vy = my.of(r);
    tip.innerHTML = `<b>${r.name}</b> · ${short(r.team)} ${r.side === 'home' ? 'v' : 'at'} ${short(r.opponent)}<br>${mx.label}: <b>${vx == null ? '–' : mx.fmt(vx)}</b> ${mx.unit.split('  ')[0]} · ${my.label}: <b>${vy == null ? '–' : my.fmt(vy)}</b> ${my.unit.split('  ')[0]}`;
    tip.hidden = false;
    const s = Math.min(innerWidth / W, innerHeight / H), left = innerWidth / 2 + (x - W / 2) * s, top = innerHeight / 2 + (y - H / 2) * s;
    tip.style.left = `${Math.min(innerWidth - 380, left + 14)}px`; tip.style.top = `${top - 56}px`;
  };
  const mark = (cls, k) => {  // the ring and name of the focused (or pinned) point
    const ring = svg.querySelector(`.${cls}`), lab = svg.querySelector(`.name.${cls}-name`), c = k && svg.querySelector(`.dot[data-key="${k}"]`);
    if (!ring) return;
    if (!c) { ring.setAttribute('r', 0); lab.textContent = ''; return; }
    const cx = +c.getAttribute('cx'), cy = +c.getAttribute('cy'), right = cx > PW - 160;
    ring.setAttribute('cx', cx); ring.setAttribute('cy', cy); ring.setAttribute('r', cls === 'focus' ? 9 : 12);
    lab.setAttribute('x', right ? cx - 14 : cx + 14); lab.setAttribute('text-anchor', right ? 'end' : 'start'); lab.setAttribute('y', cy < PAD.t + 24 ? cy + 24 : cy - 12); lab.textContent = byKey(k).surname;
  };
  const setFocus = (r, silent = false) => {
    state.focus = r ? key(r) : null;
    mark('focus', state.focus); mark('pin', state.pin);
    for (const t of svg.querySelectorAll('.name.edge')) t.style.display = t.dataset.key === state.focus || t.dataset.key === state.pin ? 'none' : '';  // the ring's own name replaces the edge label
    for (const b of document.querySelectorAll('.ranks .rank')) b.setAttribute('aria-selected', String(b.dataset.key === state.focus));
    if (r) profile(r);
    if (silent) tip.hidden = true;
  };

  const render = () => {
    const a = axes(), mx = M[a.x], my = M[a.y], view = VIEWS[state.view];
    pool = rows.filter((r) => r.minutes >= state.min && (!state.team || r.team === state.team));
    shown = pool.filter((r) => mx.of(r) != null && my.of(r) != null);
    order = [...shown].sort((b, c) => my.of(c) - my.of(b));
    $('question').innerHTML = view.question;
    svg.innerHTML = '';
    if (!shown.length) { $('plot-note').textContent = 'Nothing to plot with these filters.'; return; }
    const diag = view.ref === 'diagonal';
    const xs = shown.map(mx.of), ys = shown.map(my.of), both = diag ? [...xs, ...ys] : null;
    const sx = scale(diag ? both : xs, PAD.l, PW - PAD.r, mx.unit === 'count' || mx.unit.startsWith('pts')), sy = scale(diag ? both : ys, PH - PAD.b, PAD.t, my.unit === 'count' || my.unit.startsWith('pts'));
    for (const t of sx.ticks) { svg.append(el('line', { class: 'grid', x1: sx.to(t), x2: sx.to(t), y1: PAD.t, y2: PH - PAD.b })); svg.append(el('text', { class: 'tick', x: sx.to(t), y: PH - PAD.b + 18, 'text-anchor': 'middle' }, mx.fmt(t))); }
    for (const t of sy.ticks) { svg.append(el('line', { class: 'grid', x1: PAD.l, x2: PW - PAD.r, y1: sy.to(t), y2: sy.to(t) })); svg.append(el('text', { class: 'tick', x: PAD.l - 10, y: sy.to(t) + 4, 'text-anchor': 'end' }, my.fmt(t))); }
    svg.append(el('line', { class: 'axis', x1: PAD.l, x2: PW - PAD.r, y1: PH - PAD.b, y2: PH - PAD.b })); svg.append(el('line', { class: 'axis', x1: PAD.l, x2: PAD.l, y1: PAD.t, y2: PH - PAD.b }));
    svg.append(el('text', { class: 'axis-title', x: PW - PAD.r, y: PH - PAD.b + 38, 'text-anchor': 'end' }, `${mx.label} · ${mx.unit}`));
    svg.append(el('text', { class: 'axis-title', x: PAD.l, y: 12 }, `${my.label} · ${my.unit}${my.lowerIsTighter ? ' · lower is tighter' : ''}`));
    // the reference: the diagonal (same units on both axes) or the means of the players shown
    if (diag) {
      const lo = Math.max(sx.a, sy.a), hi = Math.min(sx.b, sy.b);
      svg.append(el('line', { class: 'ref', x1: sx.to(lo), y1: sy.to(lo), x2: sx.to(hi), y2: sy.to(hi) }));
      svg.append(el('text', { class: 'ref-label', x: sx.to(hi) - 6, y: sy.to(hi) + 14, 'text-anchor': 'end' }, a.x === 'quality' ? 'made what the looks were worth' : 'one for one'));
    } else {
      const mxv = xs.reduce((s, v) => s + v, 0) / xs.length, myv = ys.reduce((s, v) => s + v, 0) / ys.length;
      svg.append(el('line', { class: 'ref', x1: sx.to(mxv), x2: sx.to(mxv), y1: PAD.t, y2: PH - PAD.b })); svg.append(el('line', { class: 'ref', x1: PAD.l, x2: PW - PAD.r, y1: sy.to(myv), y2: sy.to(myv) }));
      const fm = (m, v) => (m.unit === 'count' ? v.toFixed(1) : m.fmt(v));
      svg.append(el('text', { class: 'ref-label', x: sx.to(mxv) + 6, y: PH - PAD.b - 6 }, `mean ${fm(mx, mxv)}`)); svg.append(el('text', { class: 'ref-label', x: PW - PAD.r - 4, y: sy.to(myv) - 5, 'text-anchor': 'end' }, `mean ${fm(my, myv)}`));
    }
    const coloured = mx.colour || my.colour;
    for (const r of shown) {
      const c = el('circle', { class: 'dot' + (state.team ? ' team' : ''), cx: sx.to(mx.of(r)).toFixed(1), cy: sy.to(my.of(r)).toFixed(1), r: 5, 'data-key': key(r) });
      if (coloured && r.extra != null) c.style.fill = css(r.extra, 0.85);
      c.addEventListener('mouseenter', () => { setFocus(r); showTip(r, +c.getAttribute('cx') + 40, +c.getAttribute('cy') + 168); });
      c.addEventListener('mouseleave', () => { tip.hidden = true; });
      c.addEventListener('click', () => open(r));
      svg.append(c);
    }
    // the extremes get a name, so the chart reads without the mouse
    const edges = [...new Set([order[0], order[1], order[order.length - 1], order[order.length - 2], ...[...shown].sort((b, c) => mx.of(c) - mx.of(b)).slice(0, 1)])].filter(Boolean);
    for (const r of edges) {
      const cx = sx.to(mx.of(r)), cy = sy.to(my.of(r)), right = cx > PW - 160;
      svg.append(el('text', { class: 'name edge', x: right ? cx - 9 : cx + 9, y: cy + 4, 'text-anchor': right ? 'end' : 'start', 'data-key': key(r) }, r.surname));
    }
    svg.append(el('circle', { class: 'pin', cx: -20, cy: -20, r: 0 })); svg.append(el('text', { class: 'name pin-name', x: -20, y: -20 }, ''));
    svg.append(el('circle', { class: 'focus', cx: -20, cy: -20, r: 0 })); svg.append(el('text', { class: 'name focus-name', x: -20, y: -20 }, ''));
    $('plot-note').textContent = `${shown.length} player-games · ${pool.length - shown.length} left out for want of a value${coloured ? ' · colour: feet beyond his normal spot' : ''} · one game per point: a question, not a verdict`;
    ranks();
    const wanted = state.focus && shown.find((r) => key(r) === state.focus);
    setFocus(wanted || order[0], true);
  };
  const ranks = () => {
    const lists = [['Fastest', 'top_speed'], ['Tightest to his normal spot', 'extra'], ['Costliest rotations', 'price']];
    $('ranks').innerHTML = '';
    for (const [title, m] of lists) {
      const mm = M[m], asc = mm.good === 'low', rs = pool.filter((r) => mm.of(r) != null).sort((b, c) => (asc ? mm.of(b) - mm.of(c) : mm.of(c) - mm.of(b))).slice(0, 6);
      const max = Math.max(...rs.map((r) => Math.abs(mm.of(r))), 1e-9);
      const col = document.createElement('div');
      col.innerHTML = `<p class="section">${title} · ${mm.unit.split('  ')[0]}</p>`;
      rs.forEach((r, k) => {
        const b = document.createElement('button'); b.className = 'rank'; b.dataset.key = key(r);
        const v = mm.of(r), colour = mm.colour ? css(v) : 'var(--ink-2)';
        b.innerHTML = `<span class="k">${k + 1}</span><span class="who">${r.surname} <em>${short(r.team)}</em></span><span class="v">${mm.fmt(v)}</span><span class="bar"><i style="width:${(100 * Math.abs(v)) / max}%; background:${colour}"></i></span>`;
        b.onmouseenter = () => setFocus(r); b.onclick = () => open(r);
        col.append(b);
      });
      $('ranks').append(col);
    }
  };
  const open = (r) => dip(() => { location.href = `roster.html?game=${r.game}&team=${r.side}&player=${r.id}`; });
  const sync = () => {
    const q = new URLSearchParams(); q.set('view', state.view);
    if (state.view === 'custom') { q.set('x', state.x); q.set('y', state.y); }
    if (state.team) q.set('team', state.team); if (state.min !== 10) q.set('min', String(state.min)); if (state.pin) q.set('pin', state.pin); if (still) q.set('motion', '0');
    history.replaceState({}, '', `?${q}`);
  };
  $('view').onchange = () => { state.view = $('view').value; syncControls(); sync(); render(); };
  $('x').onchange = () => { state.x = $('x').value; sync(); render(); };
  $('y').onchange = () => { state.y = $('y').value; sync(); render(); };
  $('team').onchange = () => { state.team = $('team').value; sync(); render(); };
  syncControls();
  render();

  keys(document.querySelector('.keys'), [[['↑', '↓'], 'Choose'], [['↵'], 'Open his profile'], [['Space'], 'Pin to compare'], [['V'], 'Next view'], [['T'], 'Next team'], [['M'], 'Minutes'], [['Esc'], 'Home']]);
  $('back').onclick = () => dip(() => { location.href = './?start=1'; });
  addEventListener('pageshow', (e) => { if (e.persisted) $('dip').classList.remove('on'); });
  addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { $('back').click(); return; }
    if (e.target && e.target.tagName === 'SELECT') return;
    const i = order.findIndex((r) => key(r) === state.focus);
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); if (order.length) setFocus(order[(i + 1) % order.length], true); }
    else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); if (order.length) setFocus(order[(i - 1 + order.length) % order.length], true); }
    else if (e.key === 'Enter' && i >= 0) { open(order[i]); }
    else if (e.code === 'Space') { e.preventDefault(); state.pin = state.pin === state.focus ? null : state.focus; sync(); setFocus(byKey(state.focus), true); }
    else if (e.key === 'v' || e.key === 'V') { const ids = Object.keys(VIEWS); state.view = ids[(ids.indexOf(state.view) + 1) % ids.length]; syncControls(); sync(); render(); }
    else if (e.key === 't' || e.key === 'T') { const all = ['', ...teams], k = all.indexOf(state.team); state.team = all[(k + 1) % all.length]; $('team').value = state.team; sync(); render(); }
    else if (e.key === 'm' || e.key === 'M') { state.min = state.min === 10 ? 20 : 10; mins.set(String(state.min)); sync(); render(); }
  });

  [$('plot'), $('profile'), ...$('ranks').children].forEach((e, i) => e.style.setProperty('--i', i));
  const frame = (now) => {
    const az = 14 + (still ? 0 : 3 * Math.sin(now / 24000));
    camera.position.copy(orbit(target, az, 30, 150)); camera.lookAt(target);
    camera.setViewOffset(W, H, 0, 60, W, H);
    renderer.render(scene, camera);
    if (!window.__ready) { window.__ready = true; requestAnimationFrame(() => { $('stage').classList.add('up'); $('stage').classList.remove('booting'); }); }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

main();
