// The match page. One game: seven tiles per defending side, and its plays, the featured one first and then the shots conceded off a
// broken rotation, most expensive first. Enter opens a play at its pass; Esc goes home.
//   ?game=<id>                 which game (default: the latest with a report)
//   ?team=home|away            which defence (default: home)
//   ?focus=play:<chance> | moment:<k> | tile:<id>   what the focus starts on (stills, and the way back from a play)

import * as THREE from 'three';
import { onFloor } from './court.js';
import { makeScene } from './scene.js';
import { infoMark, wireInfo } from './info.js';
import { FocusList, Detail, Tabs, keys, miniStrip, short, dip, place, fail } from './ui.js';
import { kitOf, badge } from './kits.js';
import { css } from './palette.js';

const W = 1920, H = 1080;
const REFS = '<a class="reflink" href="reference.html">References \u2192</a>';  // what every name on the page means, and whose figure it is
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const HERO = 'chance-191313-1-7';
const NOUN = { transition: 'transition possessions', shot_selection: 'shots conceded', ball_screens: 'set possessions with a ball screen', closeouts: 'close-outs',
               rim: 'rim attempts conceded', glass: 'misses rebounded', rotations: 'shots with a counterfactual', look: 'catches that fed a shot' };
// One second-order fact per tile, lifted out of the detail the card already opens into, so the height a tile takes is height it earns.
// By index, not by label: the rows a tile carries are data (a coverage combo, an opponent's name), and their wording changes by game,
// but their order does not. The index skips any row that only restates the tile's own `n` (rim and glass both open with that).
const UNDER_HEAD = { transition: 0, ball_screens: 0, closeouts: 0, rim: 1, glass: 1, look: 0 };
const signed = (v, nd) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(nd);
const BIG = { transition: (v) => v.toFixed(2), shot_selection: (v) => signed(v, 1), ball_screens: (v) => v.toFixed(2), closeouts: (v) => v.toFixed(2),
              rim: (v) => String(Math.round(v)), glass: (v) => String(Math.round(v)), rotations: (v) => signed(v, 1), look: (v) => String(Math.round(v)) };
const UNIT = { transition: 'pts per possession', shot_selection: 'pts per 100 shots conceded', ball_screens: 'pts per possession after the last screen', closeouts: 'pts per possession after one', rim: '% made, a defender within 4 ft', glass: '% of their misses they got back', rotations: 'pts the rotations cost', look: '% of catches, ball or man out of view' };  // the tiles' units, short enough for two lines
const BLUE = css(-4), AMBER = css(8), SAME = 'var(--ink-3)';  // the tension palette: blue = tighter than the league, amber = more conceded
// the shot card is the one card in this band that's deliberately bigger than its neighbours (a hero tile, not a mis-sized one) — a
// small mark in its own eyebrow says so on both the card and the popup it opens into, instead of leaving size as the only signal.
const TARGET_ICON = '<svg class="hero-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg>';
// the zone breakdown rows: shared by the small card's table and the large popup's, so the two never drift into two slightly different
// formats of the same numbers.
const zoneRows = (zones) => zones.map((z) => `<span class="z">${z.title}</span><span class="v">${z.made}/${z.n}</span><span class="v">${z.expected_per_shot == null ? '–' : z.expected_per_shot.toFixed(2)}</span>`).join('');
const vsLeague = (t) => {
  if (t.big.value == null || t.league == null) return '';
  const rel = t.league === 0 ? t.big.value : (t.big.value - t.league) / Math.abs(t.league);
  const tone = Math.abs(rel) < 0.05 ? SAME : rel > 0 ? AMBER : BLUE;
  return `<span class="vs"><i style="background:${tone}"></i>league ${BIG[t.id](t.league)}</span>`;
};
const priceTone = (v) => (v == null ? 'var(--ink)' : css(Math.min(15, Math.max(0, v * 30))));  // a rotation's cost, on the amber end of the scale
const tone = (t) => {  // the dot beside the league figure: amber conceded more than the league, blue less, grey within 5 %
  if (t.big.value == null || t.league == null) return SAME;
  const rel = t.league === 0 ? t.big.value : (t.big.value - t.league) / Math.abs(t.league);
  return Math.abs(rel) < 0.05 ? SAME : rel > 0 ? AMBER : BLUE;
};
/** The comparison bar: one track for this game and the league, the league as a tick, this game as the fill, from zero (or the lower of the two when negative). */
const cmpBar = (t) => {
  if (t.big.value == null || t.league == null) return `<span class="cmp"><span class="track"></span>${vsLeague(t)}</span>`;
  const lo = Math.min(0, t.big.value, t.league), hi = Math.max(t.big.value, t.league, 1e-9) * 1.15, span = hi - lo || 1;
  const x = (v) => (100 * (v - lo)) / span, a = x(Math.min(0, t.big.value) > lo ? 0 : lo), b = x(t.big.value);
  return `<span class="cmp"><span class="track"><i style="left:${Math.min(a, b).toFixed(1)}%; width:${Math.abs(b - a).toFixed(1)}%; background:${tone(t)}"></i><b style="left:calc(${x(t.league).toFixed(1)}% - 1px)"></b></span>${vsLeague(t)}</span>`;
};
/** The game by quarter: what the looks were worth (grey) and what was scored (ink), the rotations' price beneath. */
const quarterChart = (q) => {
  const W = 520, H = 104, PADL = 8, top = 14, base = 70, max = Math.max(1, ...q.map((r) => Math.max(r.expected, r.scored)));
  const gw = (W - 2 * PADL) / Math.max(q.length, 1), bw = 22, y = (v) => base - ((base - top) * v) / max;
  let svg = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Points conceded by quarter, expected and scored">`;
  q.forEach((r, k) => {
    const cx = PADL + gw * k + gw / 2;
    svg += `<rect class="q-exp" x="${cx - bw - 3}" y="${y(r.expected)}" width="${bw}" height="${base - y(r.expected)}" rx="2"/>`;
    svg += `<rect class="q-got" x="${cx + 3}" y="${y(r.scored)}" width="${bw}" height="${base - y(r.scored)}" rx="2"/>`;
    svg += `<text class="q-val" x="${cx + 3 + bw / 2}" y="${y(r.scored) - 4}" text-anchor="middle">${r.scored}</text>`;
    svg += `<text class="q-axis" x="${cx}" y="${base + 13}" text-anchor="middle">Q${r.period}</text>`;
    svg += `<text class="q-price" x="${cx}" y="${base + 28}" text-anchor="middle" style="fill:${priceTone(r.price)}">${signed(r.price, 2)}</text>`;
  });
  return svg + '</svg>';
};
/** The half court, attacked hoop at the top, in feet from court.json; every conceded shot as a mark, a green disc made, a cross missed. */
const halfCourt = (court, shots, big = false) => {
  const L = court.length / 2, Wd = court.width / 2, [hx] = court.hoop, R = court.three_radius, cy = court.three_corner_y, [pl, pw] = court.paint;
  const X = (x, y) => y + Wd, Y = (x, y) => x + L;  // rotate: baseline at the top, the sideline width across
  const t0 = Math.asin(cy / R), xa = hx + R * Math.cos(t0);
  let d = `M${X(0, -cy)} ${Y(-L, -cy)} L${X(0, -cy)} ${Y(xa, -cy)}`;
  for (let k = 0; k <= 40; k += 1) { const th = -t0 + (2 * t0 * k) / 40, x = hx + R * Math.cos(th), y = R * Math.sin(th); d += ` L${X(x, y).toFixed(2)} ${Y(x, y).toFixed(2)}`; }
  d += ` L${X(0, cy)} ${Y(-L, cy)}`;
  const depth = 33;  // ft from the baseline: past the top of the arc and no further, so the shots fill the picture (a heave from beyond falls off it)
  // the aspect ratio written on the svg itself, not assumed by whatever CSS box happens to hold it: object-fit: contain already keeps
  // the artwork at its own proportions inside that box, but if the box's own shape is far off (a tall box for a wide, short court)
  // most of the box still goes unused above and below it — this is what actually pins the box's shape to the content's own, so a
  // parent container sized to fill its share of a card no longer fights the drawing for space.
  let svg = `<svg viewBox="0 0 ${2 * Wd} ${depth}" preserveAspectRatio="xMidYMin meet" style="aspect-ratio:${(2 * Wd).toFixed(2)}/${depth}" role="img" aria-label="Where the shots conceded came from">`;
  svg += `<rect class="court-fill" x="0" y="0" width="${2 * Wd}" height="${depth}"/><path class="court-line" d="M0 ${depth} L0 0 L${2 * Wd} 0 L${2 * Wd} ${depth}"/>`;
  svg += `<rect class="court-paint" x="${X(0, -pw / 2)}" y="0" width="${pw}" height="${pl}"/>`;  // the key filled, not just outlined: a dot's zone should read from the picture, not only from the table beside it
  svg += `<rect class="court-line" x="${X(0, -pw / 2)}" y="0" width="${pw}" height="${pl}"/><circle class="court-line" cx="${X(0, 0)}" cy="${pl}" r="${court.free_throw_radius}"/>`;
  svg += `<path class="court-line" d="${d}"/><circle class="court-line" cx="${X(0, 0)}" cy="${Y(hx, 0)}" r="0.75"/>`;
  // Made and missed used to differ only by filled versus hollow, in the same near-white, which stops telling them apart exactly where
  // it matters: the pile at the rim. Now they differ in shape as well as in value — a made shot is a filled disc in SkillCorner's
  // green with a dark rim, a miss is a cross, dark, carried on a pale one a shade wider so a dozen crossing each other still read as
  // a dozen. Shape survives overlap in a way that fill-versus-outline does not.
  shots.forEach((s, k) => {
    const x = X(s.x, s.y), y = Y(s.x, s.y), r = big ? 1.15 : 0.95, cls = `shot ${s.made ? 'made' : 'miss'}${s.dim ? ' dim' : ''}`;
    const title = `<title>${s.shooter} · Q${s.period} · ${s.three ? 'three' : 'two'} ${s.made ? 'made' : 'missed'} · quality ${s.quality} %</title>`;
    if (s.made) { svg += `<circle class="${cls}" data-k="${k}" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${r}">${title}</circle>`; return; }
    const a = r * 0.8, d = `M${(x - a).toFixed(2)} ${(y - a).toFixed(2)}L${(x + a).toFixed(2)} ${(y + a).toFixed(2)}M${(x - a).toFixed(2)} ${(y + a).toFixed(2)}L${(x + a).toFixed(2)} ${(y - a).toFixed(2)}`;
    svg += `<g class="${cls}" data-k="${k}"><path class="x-halo" d="${d}"/><path class="x-mark" d="${d}"/>${title}</g>`;
  });
  return svg + '</svg>';
};
const chip = (c) => (c.value == null ? '–' : c.unit === 'ft' ? signed(c.value, 1) + ' ft' : c.unit === '%' ? `${Math.round(c.value)} %` : `${c.value} ${c.unit}`);
const result = (o) => ({ FGM3: 'three made', FGX3: 'three missed', FGM: 'two made', FGX: 'two missed' }[o] || o);
const orbit = (target, azDeg, elDeg, dist) => {
  const az = THREE.MathUtils.degToRad(azDeg), el = THREE.MathUtils.degToRad(elDeg);
  return new THREE.Vector3(target.x + dist * Math.cos(el) * Math.sin(az), dist * Math.sin(el), target.z + dist * Math.cos(el) * Math.cos(az));
};
const date = (iso) => new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });

async function load() {
  const games = await (await fetch('games/index.json')).json();
  const withReport = games.filter((g) => g.score);
  const game = params.get('game') ? Number(params.get('game')) : (withReport[0] || {}).game;
  const row = games.find((g) => g.game === game);
  if (!row) throw new Error('game');
  if (!row.score) throw new Error('report');
  const [rep, court] = await Promise.all([fetch(`reports/${game}.json`).then((r) => r.json()), fetch('court.json').then((r) => r.json())]);
  return { rep, row, court };
}

/** The plays of one defending side: the game's own plays it defended (the featured first), then the report's moments, without repeats. */
function playsOf(row, team) {
  const own = row.plays.filter((p) => !p.moment && p.defence === team.team).sort((a, b) => (a.chance === HERO ? -1 : b.chance === HERO ? 1 : 0));
  const items = own.map((p) => ({ kind: 'play', ...p }));
  for (const m of team.moments) {
    const twin = items.find((p) => p.chance === m.chance);
    if (twin) Object.assign(twin, { price: m.price, i: m.i }); else items.push({ kind: 'moment', ...m, clip: (row.plays.find((p) => p.chance === m.chance) || {}).clip });
  }
  return items;
}

async function main() {
  $('stage').classList.add('booting');
  place($('stage'));
  const still = params.get('motion') === '0' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) $('stage').classList.add('nomotion');
  await Promise.all([document.fonts.load('700 48px Inter'), document.fonts.load('500 16px Inter'), document.fonts.load('600 16px Inter')]);
  let rep, row, court, game;
  try { ({ rep, row, court } = await load()); game = row.game; } catch (e) {
    const why = { game: `No game ${params.get('game') || ''} on this machine. <small>Home lists the games that are.</small>`,
                  report: 'No report for this game yet. Write it on this machine: <code>uv run courtlab report --all</code> and reload.' }[e.message]
      || 'The viewer could not reach its server. Start it: <code>uv run courtlab serve</code>, then reload.';
    fail($('stage'), why);
    return;
  }

  // the empty court, from the start screen's seat, drifting a little
  const { renderer, scene, camera } = makeScene($('gl'), court, kitOf(rep.game.home));
  camera.fov = 26; camera.updateProjectionMatrix();
  const target = onFloor(-22, 0, 2);
  let scale = 1;
  const fit = () => {
    scale = Math.min(innerWidth / W, innerHeight / H);
    $('stage').style.transform = `scale(${scale}) translate(-50%, -50%)`;
    renderer.setPixelRatio(Math.min(2, Math.max(1, devicePixelRatio * scale)));
    renderer.setSize(W, H, false);
  };
  addEventListener('resize', fit); fit();
  wireInfo($('stage'));  // delegated, so the cards may be re-rendered on a tab change and keep their `i`

  const g = rep.game;
  $('match').textContent = `${short(g.home)} ${g.score[0]}–${g.score[1]} ${short(g.away)}`;
  $('match').title = `${g.home} (home) – ${g.away}`;
  badge($('badge-home'), kitOf(g.home)); badge($('badge-away'), kitOf(g.away));
  $('context').innerHTML = `${g.competition} · ${date(g.date)} · SkillCorner open data · league figures from ${rep.source.league.n_games} games · ${REFS}`;
  const sideOf = { home: rep.teams.find((t) => t.side === 'home'), away: rep.teams.find((t) => t.side === 'away') };
  for (const b of $('teams').querySelectorAll('button')) b.textContent = `${short(sideOf[b.dataset.tab].team)} defending`;

  const detail = new Detail($('detail'));
  // the plays list used to stop at a flat 540px regardless of what the detail card below/over it actually needed — a short detail (a
  // tile with one line of context) left a dead gap of bare 3D court above it, a tall one (a play's four chapters, or a stat with a long
  // paragraph and seven rows, like "The Look") could run its top edge INTO the list's last rows instead. The list's own bottom now
  // tracks whichever sits highest, the detail card's top (when one is showing) or the footer key legend, with the same breathing room
  // either way — the way `fit()` on the play page already re-measures the broadcast panel against the story card's real height instead
  // of assuming one.
  const keysEl = document.querySelector('#stage.report .keys');
  const fitList = () => {
    const list = $('plays'), top = list.getBoundingClientRect().top;
    const limits = [keysEl.getBoundingClientRect().top];
    if (!detail.el.hidden) limits.push(detail.el.getBoundingClientRect().top);
    list.style.maxHeight = `${Math.max(160, Math.min(...limits) - 24 - top)}px`;
  };
  new MutationObserver(fitList).observe(detail.el, { childList: true, attributes: true, attributeFilter: ['hidden', 'class'] });
  addEventListener('resize', fitList);
  let pane = 'plays', cards = null, plays = null, team = null;
  const showCard = (c, silent) => detail.show((el) => {
    el.classList.remove('large');
    $('stage').classList.remove('zones-open');  // belt and suspenders alongside closeLarge: showCard is the one function every path away from the large popup runs through
    if (c.kind === 'tile') {
      const t = c.tile;
      el.innerHTML = `<p class="section">${t.title}</p><p class="lead">${t.line}</p><div class="rows">${t.detail.map((r) => `<div class="row"><span class="k">${r.label}</span><span class="v">${r.value}</span></div>`).join('')}</div>`
        + `<p class="foot">n = ${t.n} ${NOUN[t.id] || ''} · per-game numbers are counts; only the league figures carry intervals</p>`;
    } else if (c.kind === 'bill') {
      el.innerHTML = `<p class="section">The game by quarter</p><p class="lead">${c.tiles[0].line}</p><div class="rows">${c.quarters.map((q) => `<div class="row"><span class="k">Q${q.period} · ${q.shots} shots</span><span class="v">worth ${q.expected.toFixed(1)} · scored ${q.scored} · rotations <b style="color:${priceTone(q.price)}">${signed(q.price, 2)}</b> · broken ${q.broken} of ${q.catches}</span></div>`).join('')}</div>`
        + '<p class="foot">worth = what SkillCorner\'s quality of the looks expected, from the field · rotations = the ledger\'s sum for the quarter · broken = set catches off a broken rotation</p>';
    } else if (c.kind === 'who') {
      el.innerHTML = `<p class="section">Who paid</p><p class="lead">The ledger names the defender whose distance at the release the counterfactual moves: the man who closed out late, or the one who let go.</p><div class="rows">${c.rows.map((r) => `<div class="row"><span class="k">${r.name}</span><span class="v"><b style="color:${priceTone(r.price)}">${signed(r.price, 2)} pts</b> on ${r.shots} shot${r.shots === 1 ? '' : 's'} · ${r.closeouts} close-outs · nearest on ${r.conceded} conceded</span></div>`).join('')}</div>`
        + `<p class="foot">${c.nobody ? `${c.nobody} shots priced with nobody assigned to the shooter and no free man found · ` : ''}an upper bound: the defender arrives and nothing else changes</p>`;
    } else if (c.kind === 'zones') {
      el.innerHTML = `<p class="section">Where they shot from</p><p class="lead">Every field-goal attempt conceded, where it was taken. Worth is what SkillCorner's quality expected per shot; made is what happened.</p><div class="rows">${c.zones.map((z) => `<div class="row"><span class="k">${z.title}</span><span class="v">${z.n ? `${z.made} of ${z.n} made (${Math.round((100 * z.made) / z.n)} %) · worth ${z.expected_per_shot.toFixed(2)} per shot` : '–'}</span></div>`).join('')}</div>`
        + '<p class="foot">fouled shots excluded · one game: a picture, not a tendency · <kbd>↵</kbd> opens the court large, shot by shot</p>';
    }
    return true;
  }, silent);
  // the zones card, opened: the half court large, every shot with its shooter, the shooters as a filter (click one, or all)
  let zonesShooter = null;
  const showZonesLarge = (c) => detail.show((el) => {
    const shooters = [...new Set(c.shots.map((s) => s.shooter))].sort();
    const shots = c.shots.map((s) => ({ ...s, dim: zonesShooter && s.shooter !== zonesShooter }));
    const shown = zonesShooter ? shots.filter((s) => !s.dim) : shots, made = shown.filter((s) => s.made).length;
    const worth = shown.length ? shown.reduce((a, s) => a + (s.three ? 3 : 2) * s.quality / 100, 0) / shown.length : 0;
    el.classList.add('large');
    $('stage').classList.add('zones-open');  // the rest of the grid dims further while this is up: it's the one place on this page that behaves like a modal, so it should look like one
    // the eyebrow stays the fixed title (as every other card's does, now with the same mark the small card carries); the team name
    // and stats — which vary in length with the opponent's name and the shooter filter — go in a `.lead` line below, the same row
    // style the small card already uses, instead of being crammed onto one nowrap line where a longer team name pushed the
    // worth-per-shot figure off into an ellipsis
    const zrows = zoneRows(c.zones);
    el.innerHTML = `<p class="section">${TARGET_ICON}Where they shot from</p><p class="lead">${zonesShooter || short(team.opponent)} · ${made} of ${shown.length} made · worth ${worth.toFixed(2)} per shot</p>`
      + `<div class="shotrow"><div class="court-large">${halfCourt(court, shots, true)}</div>`
      + `<div class="zbreak"><span class="h">zone</span><span class="h v">made</span><span class="h v">worth</span>${zrows}<span class="zbreak-note">the whole game, not just the shooters kept above</span></div></div>`
      + `<div class="shooters">${['', ...shooters].map((n) => `<button class="chip${(n || null) === zonesShooter ? ' on' : ''}" data-n="${n}">${n || 'Everyone'}</button>`).join('')}</div>`
      + '<p class="open">A green disc went in, a cross did not · hover one for its quarter and quality · click a name to keep his shots · <kbd>Esc</kbd> closes</p>';
    for (const b of el.querySelectorAll('.shooters .chip')) b.onclick = (e) => { e.stopPropagation(); zonesShooter = b.dataset.n || null; showZonesLarge(c); };
    return true;
  }, true);
  const closeLarge = () => { const el = $('detail'); if (!el.classList.contains('large')) return false; el.classList.remove('large'); $('stage').classList.remove('zones-open'); zonesShooter = null; showCard(focusable[cards.focus], true); return true; };
  const showPlay = (m, silent) => detail.show((el) => {
    el.classList.remove('large'); $('stage').classList.remove('zones-open');  // hovering a play while the zones popup is open is a real path (mouseenter on .item), not just Esc/click
    if (m.kind === 'play') {
      el.innerHTML = `<p class="section">${m.chance === HERO ? 'Featured play' : 'Play'} · Q${m.period} ${m.clock || ''} · ${short(m.attack)} attacking</p><p class="lead">${m.story || ''}</p>`
        + `<div class="chips">${(m.chapters || []).map((c) => `<span class="chip"><b>${chip(c)}</b><span>${c.title}</span></span>`).join('')}</div>`
        + (m.price && m.price.value != null ? `<p class="line price"><b style="color:${priceTone(m.price.value)}">Price ${signed(m.price.value, 2)} pts</b> · ${m.price.kind}${m.price.note ? ` · ${m.price.note}` : ''}</p>` : '')
        + '<p class="open">Press <kbd>↵</kbd> to open the play</p>';
      return true;
    }
    const shot = `${m.shot.three ? 'three' : 'two'}, ${m.shot.made ? 'made' : 'missed'}${m.shot.quality != null ? ` · quality ${Math.round(m.shot.quality)} %` : ''}`;
    el.innerHTML = `<p class="section">${m.clock} · ${m.shooter} · ${shot}</p><p class="lead">${m.origin}</p><p class="line">${m.rotation}</p>`
      + (m.closeout ? `<p class="line">${m.closeout}</p>` : '')
      + (m.price.value != null ? `<p class="line price"><b style="color:${priceTone(m.price.value)}">Price ${signed(m.price.value, 2)} pts</b> · ${m.price.kind}${m.price.note ? ` · ${m.price.note}` : ''}</p>` : '')
      + '<p class="open">Most expensive first · press <kbd>↵</kbd> to open the play at the pass</p>';
    return true;
  }, silent);
  const openPlay = (m) => {
    const q = new URLSearchParams({ chance: m.chance, play: '1' });
    if (m.kind === 'moment') q.set('i', String(m.i));
    dip(() => { location.href = `./?${q}`; });
  };
  const render = (side, focus, silent = true) => {
    team = sideOf[side];
    $('cards').innerHTML = ''; $('plays').innerHTML = '';
    $('cards-section').textContent = `When ${short(team.team)} defended · ${short(team.opponent)} attacking`;
    const T = Object.fromEntries(team.tiles.map((t) => [t.id, t])), st = team.story || { quarters: [], zones: [], shots: [], who: [] };
    // the second band used to be two rows (four tiles, then two more beside the shot card) — the shot card's own height drove a row it
    // only half shared, leaving the two tiles beside it either too short (a bare gap under them) or artificially stretched (dead air
    // inside them). Three columns of two tiles, stacked, next to the shot card as its own full-height fourth column: the shot card's
    // height is however tall two stacked tiles plus the gap between them come out to, never a guess in either direction.
    // The first band carries no label on purpose: the plays column beside it opens on ONE line, and a second heading here pushed this
    // whole column a line lower than that one, which is the misalignment along the top. "The bill" and "Who paid" name themselves,
    // so the line they lose costs no meaning; the band that introduces the breakdown below them keeps its own.
    // what each card's `i` explains: the terms a reader of THAT card would stop on, in the order they meet them
    const INFO = { transition: ['transition', 'league'], ball_screens: ['labels', 'league'], closeouts: ['labels', 'league'],
      rim: ['zones', 'league'], glass: ['glass', 'league'], look: ['look', 'league'] };
    const cardsList = [  // the order a coach reads it in: what it cost, when; how the set broke, and where they shot from
      { kind: 'bill', title: 'The bill', tiles: [T.shot_selection, T.rotations], quarters: st.quarters },
      { kind: 'who', title: 'Who paid', rows: st.who, nobody: st.unpriced_to_nobody },
      { kind: 'band', title: 'How the set broke, and where they shot from' },
      { kind: 'tile', tile: T.transition }, { kind: 'tile', tile: T.ball_screens }, { kind: 'tile', tile: T.closeouts },
      // the small card is one column wide and its heading has to clear the `i` in the corner, so it carries the short name; the band
      // above it and the popup below both say "where they shot from" in full
      { kind: 'zones', title: 'Shots conceded', zones: st.zones, shots: st.shots },  // placed here so it auto-flows into the one column still free in this row, then spans down into the next
      { kind: 'tile', tile: T.rim }, { kind: 'tile', tile: T.glass }, { kind: 'tile', tile: T.look },
    ];
    const focusable = cardsList.filter((c) => c.kind !== 'band');
    cards = new FocusList($('cards'), focusable, {
      className: 'card',
      render: (b, c) => {
        if (c.kind === 'tile') {
          const t = c.tile, v = t.big.value;
          b.classList.add('tile');
          const under = (t.detail || [])[UNDER_HEAD[t.id]];
          b.innerHTML = `<span class="k">${t.title}${infoMark(...(INFO[t.id] || []))}</span><span class="pair"><span class="big">${v == null ? '–' : BIG[t.id](v)}</span><span class="unit">${UNIT[t.id] || t.big.unit}</span></span>`
            + (under ? `<span class="more"><span class="ml">${under.label}</span><span class="mv">${under.value}</span></span>` : '')
            + `${cmpBar(t)}<span class="n">n = ${t.n} ${NOUN[t.id] || ''}</span>`;
        } else if (c.kind === 'bill') {
          b.classList.add('bill');
          b.innerHTML = `<span class="k">${c.title}${infoMark('bill', 'selection', 'price')}</span><span class="two">${c.tiles.map((t) => `<span class="pair"><span class="big">${t.big.value == null ? '–' : BIG[t.id](t.big.value)}</span><span class="unit">${UNIT[t.id] || t.big.unit}</span><span class="vs"><i style="background:${tone(t)}"></i>league ${t.league == null ? '–' : BIG[t.id](t.league)}</span></span>`).join('')}</span>`
            + quarterChart(c.quarters) + '<span class="legend"><span><i style="background:rgba(255,255,255,0.22)"></i>what the looks were worth</span><span><i style="background:var(--ink)"></i>scored from the field</span><span>· below: what the rotations cost</span></span>';
        } else if (c.kind === 'who') {
          b.classList.add('who');
          b.innerHTML = `<span class="k">${c.title}${infoMark('who_paid', 'price')}</span><span class="list-in">${c.rows.slice(0, 6).map((r) => `<span class="row-in"><span>${r.name}</span><span class="v" style="color:${priceTone(r.price)}">${signed(r.price, 2)}</span><span class="s">on ${r.shots} shot${r.shots === 1 ? '' : 's'}</span><span class="s">${r.closeouts} close-out${r.closeouts === 1 ? '' : 's'}</span></span>`).join('') || '<span class="row-in"><span>Nothing priced to a defender</span></span>'}</span>`
            + `<span class="n">the ledger by the defender it names${c.nobody ? ` · ${c.nobody} priced to nobody` : ''}</span>`;
        } else if (c.kind === 'zones') {
          b.classList.add('zones');
          const rows = zoneRows(c.zones);
          b.innerHTML = `<span class="k">${TARGET_ICON}${c.title}${infoMark('shot_marks', 'worth', 'zones')}</span><span class="half">${halfCourt(court, c.shots)}<span class="ztable"><span class="h">zone</span><span class="h v">made</span><span class="h v">worth</span>${rows}</span></span><span class="n">${c.shots.length} shots conceded · a green disc went in, a cross did not · worth = expected points per shot, SkillCorner</span>`;
        }
      },
      onFocus: (c, k, s) => { if (pane === 'cards') showCard(c, s); },
      onOpen: (c) => { if (c.kind === 'zones') showZonesLarge(c); },
    });
    // the band eyebrows sit between the cards, in the grid
    let k = 0;
    for (const c of cardsList) {
      if (c.kind === 'band') { const e = document.createElement('p'); e.className = 'band'; e.textContent = c.title; $('cards').insertBefore(e, cards.rows[k] || null); } else k += 1;
    }
    const items = playsOf(row, team);
    plays = new FocusList($('plays'), items, {
      className: 'item', visible: 6,
      render: (b, m) => {
        if (m.kind === 'play') {
          const origin = (m.story || '').split(' → ').slice(0, -1).join(' → ');
          const tags = [m.chance === HERO ? 'Featured' : '', m.clip ? 'TV clip' : ''].filter(Boolean);
          b.innerHTML = `<span class="meta"><span class="teams">Q${m.period} ${m.clock || ''} · ${short(m.shooter)}, ${result(m.outcome)}</span><span class="sub">${origin || 'No labelled action'}${tags.length ? ' · ' : ''}${tags.map((t) => `<em>${t}</em>`).join(' ')}</span></span><canvas width="320" height="48"></canvas><span class="price" style="color:${priceTone(m.price && m.price.value)}">${m.price && m.price.value != null ? signed(m.price.value, 2) : ''}</span>`;
          miniStrip(b.querySelector('canvas'), m.thumb, m.release);
          return;
        }
        b.innerHTML = `<span class="meta"><span class="teams">${m.clock} · ${m.shooter}, ${m.shot.three ? 'three' : 'two'} ${m.shot.made ? 'made' : 'missed'}</span><span class="sub">${m.price.kind || ''}${m.shot.quality != null ? ` · quality ${Math.round(m.shot.quality)} %` : ''}${m.clip ? ' · <em>TV clip</em>' : ''}</span></span><canvas width="320" height="48"></canvas><span class="price" style="color:${priceTone(m.price.value)}">${m.price.value == null ? '–' : signed(m.price.value, 2)}</span>`;
        miniStrip(b.querySelector('canvas'), m.thumb, null);
      },
      onFocus: (m, k, s) => { if (pane === 'plays') showPlay(m, s); },
      onOpen: openPlay,
    });
    for (const b of cards.rows) b.addEventListener('mouseenter', () => { pane = 'cards'; showCard(focusable[cards.focus]); });
    for (const b of plays.rows) b.addEventListener('mouseenter', () => { pane = 'plays'; showPlay(items[plays.focus]); });
    const [kind, which] = (focus || 'play:0').split(':');
    if (kind === 'tile') { pane = 'cards'; cards.focusWhere((c) => (c.kind === 'tile' ? c.tile.id === which : c.kind === which), silent); showCard(focusable[cards.focus], silent); }
    else if (kind === 'court') { pane = 'cards'; cards.focusWhere((c) => c.kind === 'zones', silent); showZonesLarge(focusable[cards.focus]); }  // the half court open large (stills)
    else {
      pane = 'plays';
      const k = kind === 'moment' ? items.findIndex((m) => m.chance === (team.moments[Number(which) || 0] || {}).chance) : kind === 'play' && which && Number.isNaN(Number(which)) ? items.findIndex((m) => m.chance === which) : Number(which) || 0;
      plays.setFocus(Math.max(0, k), silent);
      if (items.length) showPlay(items[plays.focus], silent); else detail.show(() => false, true);
    }
    tabs.set(side);
  };
  const tabs = new Tabs($('teams'), { onChange: (side) => { const q = new URLSearchParams(location.search); q.set('team', side); q.delete('focus'); history.replaceState({}, '', `?${q}`); render(side, null); } });
  keys(document.querySelector('.keys'), [[['↵'], 'Open the play'], [['↑', '↓', '←', '→'], 'Choose'], [['⇥'], 'Other defence'], [['R'], 'Roster'], [['Esc'], 'Home']]);
  const openRoster = () => dip(() => { location.href = `roster.html?game=${game}&team=${tabs.value}`; });
  $('roster').onclick = openRoster; $('roster').hidden = !row.roster;
  const focus = params.get('focus');
  const wanted = focus && focus.startsWith('play:') ? row.plays.find((p) => p.chance === focus.slice(5)) : null;
  const side = ['home', 'away'].includes(params.get('team')) ? params.get('team') : wanted ? (wanted.defence === g.home ? 'home' : 'away') : 'home';
  render(side, focus);
  fitList();  // the observer only fires on the next change; this covers the very first paint

  $('back').onclick = () => dip(() => { location.href = './?start=1'; });
  addEventListener('pageshow', (e) => { if (e.persisted) $('dip').classList.remove('on'); });
  addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (!closeLarge()) $('back').click(); return; }
    if (e.key === 'r' || e.key === 'R') { if (row.roster) openRoster(); return; }
    if (e.key === 'Tab') { e.preventDefault(); const other = tabs.value === 'home' ? 'away' : 'home'; tabs.set(other); tabs.buttons.find((b) => b.dataset.tab === other).click(); return; }
    if (pane === 'cards') {
      const dir = { ArrowDown: [0, 1], ArrowUp: [0, -1], ArrowRight: [1, 0], ArrowLeft: [-1, 0] }[e.key];
      if (!dir) return;
      e.preventDefault();
      const me = cards.rows[cards.focus].getBoundingClientRect(), cx = (me.left + me.right) / 2, cy = (me.top + me.bottom) / 2;
      let best = -1, bestD = Infinity;  // the nearest card in that direction, by the centres
      cards.rows.forEach((b, k) => {
        if (k === cards.focus) return;
        const r = b.getBoundingClientRect(), dx = (r.left + r.right) / 2 - cx, dy = (r.top + r.bottom) / 2 - cy;
        const along = dx * dir[0] + dy * dir[1], across = Math.abs(dx * dir[1]) + Math.abs(dy * dir[0]);
        if (along <= 4) return;
        const d = along + across * 2;
        if (d < bestD) { bestD = d; best = k; }
      });
      if (best >= 0) cards.setFocus(best); else if (e.key === 'ArrowRight') { pane = 'plays'; plays.setFocus(plays.focus); }
    } else if (e.key === 'ArrowLeft') { e.preventDefault(); pane = 'cards'; cards.setFocus(cards.focus); }
    else plays.key(e);
  });

  // ordered entrance, then the loop: a slow drift of the seat, none when motion is off
  [...document.querySelectorAll('#stage.report .title, #stage.report .topright, .cards-col > *, .plays-col > *')].forEach((el, i) => el.style.setProperty('--i', i));
  $('detail').style.setProperty('--i', 8); document.querySelector('.keys').style.setProperty('--i', 9);
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
