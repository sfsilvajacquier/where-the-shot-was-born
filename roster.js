// The roster page. Both teams of one match; the focused player's profile from SkillCorner's data alone: this game (positions and
// labels), his defence (matchups, close-outs, the ledger) and the season counts SkillCorner publishes. Enter opens his featured play,
// E opens it through his eyes; Esc goes back to the match.
//   ?game=<id>   ?team=home|away   ?player=<id>

import * as THREE from 'three';
import { onFloor } from './court.js';
import { makeScene } from './scene.js';
import { infoMark, wireInfo } from './info.js';
import { FocusList, Tabs, keys, short, dip, place, fail } from './ui.js';
import { kitOf, badge } from './kits.js';
import { css } from './palette.js';

const W = 1920, H = 1080;
const REFS = '<a class="reflink" href="reference.html">References \u2192</a>';  // what every name on the page means, and whose figure it is
const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const HERO = 'chance-191313-1-7';
const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const pctOf = (a, b) => (b ? `${Math.round((100 * a) / b)} %` : '–');
const frac = (a, b) => `${a}/${b} <em>${pctOf(a, b)}</em>`;
const signed = (v, nd) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(nd);
const orbit = (target, azDeg, elDeg, dist) => {
  const az = THREE.MathUtils.degToRad(azDeg), el = THREE.MathUtils.degToRad(elDeg);
  return new THREE.Vector3(target.x + dist * Math.cos(el) * Math.sin(az), dist * Math.sin(el), target.z + dist * Math.cos(el) * Math.cos(az));
};
const date = (iso) => new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
const row = (k, v) => ({ k, v });  // a cell's data; positioned into the shared grid at render time, so its row lines up across the three columns

async function load() {
  const games = await (await fetch('games/index.json')).json();
  const game = params.get('game') ? Number(params.get('game')) : (games.find((g) => g.roster) || {}).game;
  const rowG = games.find((g) => g.game === game);
  if (games.length && games[0].roster === undefined) throw new Error('stale');  // an index without the roster flag: the server predates this page
  if (!rowG) throw new Error('game');
  if (!rowG.roster) throw new Error('roster');
  const [ros, court] = await Promise.all([fetch(`rosters/${game}.json`).then((r) => r.json()), fetch('court.json').then((r) => r.json())]);
  return { ros, court, game };
}

/** The profile's three columns, from the roster file's fields. */
function columns(p) {
  const g = p.game, d = p.defence, s = p.season, sh = g.shots;
  const game = [
    row('On the tracked play', `${mmss(g.seconds)}`),
    row('Distance covered', `${Math.round(g.distance_ft).toLocaleString('en-GB')} ft`),
    row('Top speed', g.top_speed == null ? '–' : `${g.top_speed.toFixed(1)} ft/s`),
    row('Shots', sh.n ? `${frac(sh.made, sh.n)}${sh.three ? ` · ${sh.three_made}/${sh.three} threes` : ''}` : '–'),
    row('Quality of his looks', sh.quality == null ? '–' : `${Math.round(sh.quality)} % <em>SkillCorner</em>`),
    row('Points from the field', String(sh.points)),
    row('Assists / turnovers', `${g.assists} / ${g.turnovers}`),
    row('Completed passes', String(g.passes)),
    row('Drives', g.drives ? `${g.drives}${g.blowby ? ` · ${g.blowby} blow-by${g.blowby === 1 ? '' : 's'}` : ''}` : '–'),
    row('Ball screens', `${g.picks_handler} as handler · ${g.screens} set`),
    row('Rebounds', `${g.rebounds[0]} off · ${g.rebounds[1]} def`),
    row('Fouls', String(g.fouls)),
  ];
  const def = [
    // single-line stats first, so most of the table stays compact; the two lists (which can run to three lines) go last
    row('Beyond his normal spot', d.extra ? `${signed(d.extra.mean, 1)} ft <em>mean</em>` : '–'),
    row('Within 3 ft of it', d.extra ? `${pctOf(d.extra.within_3 * 1000, 1000)} <em>of the time</em>` : '–'),
    row('Close-outs', d.closeouts ? `${d.closeouts.n} · ${d.closeouts.start == null ? '–' : d.closeouts.start.toFixed(0)} → ${d.closeouts.end == null ? '–' : d.closeouts.end.toFixed(1)} ft` : '–'),
    row('After his close-outs', d.closeouts && d.closeouts.pts != null ? `${d.closeouts.pts.toFixed(2)} pts/poss` : '–'),
    row('The attacker shot / drove / passed', d.closeouts ? `${d.closeouts.actions.shot || 0} / ${d.closeouts.actions.drive || 0} / ${d.closeouts.actions.pass || 0}` : '–'),
    row('Shots conceded, nearest defender', d.conceded ? `${frac(d.conceded.made, d.conceded.n)}` : '–'),
    row('His distance at those releases', d.conceded && d.conceded.distance != null ? `${d.conceded.distance.toFixed(1)} ft <em>median</em>` : '–'),
    row('Rotations he paid for', d.price ? `<b style="color:${css(Math.min(15, Math.max(0, d.price.value * 30)))}">${signed(d.price.value, 2)} pts</b> <em>${d.price.n} shot${d.price.n === 1 ? '' : 's'}</em>` : '–'),
    row('Guarded most', d.guarded.length ? d.guarded.map((x) => `${x.who} <em>${mmss(x.seconds)}</em>`).join('<br>') : '–'),
    row('Of which', d.price ? Object.entries(d.price.kinds).map(([k, n]) => `${n} ${k}`).join('<br>') : '–'),
  ];
  const season = !s ? [row('Season aggregates', 'not published for him')] : [
    row('Games', String(s.games)),
    row('Field goals', frac(s.fg[0], s.fg[1])),
    row('Threes', frac(s.three[0], s.three[1])),
    row('Catch-and-shoot threes', frac(s.cns_three[0], s.cns_three[1])),
    row('Contested shots', frac(s.contested[0], s.contested[1])),
    row('Points', String(s.points)),
    row('Ball screens as handler', s.picks ? `${s.picks.n} · ${s.picks.points} pts · ${s.picks.turnovers} TO` : '–'),
    row('Drives', s.drives ? `${s.drives.n} · ${s.drives.blowby} blow-bys · ${s.drives.points} pts` : '–'),
  ];
  return { game, def, season };
}

async function main() {
  $('stage').classList.add('booting');
  place($('stage'));
  const still = params.get('motion') === '0' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (still) $('stage').classList.add('nomotion');
  await Promise.all([document.fonts.load('700 48px Inter'), document.fonts.load('500 16px Inter'), document.fonts.load('600 16px Inter')]);
  let ros, court, game;
  try { ({ ros, court, game } = await load()); } catch (e) {
    const why = { stale: 'The server running is older than this page. Stop it and start it again: <code>uv run courtlab serve</code>, then reload.',
                  game: `No game ${params.get('game') || ''} on this machine. <small>Home lists the games that are.</small>`,
                  roster: 'No roster for this game yet. Write it on this machine: <code>uv run courtlab report --all</code> and reload.' }[e.message]
      || 'The viewer could not reach its server. Start it: <code>uv run courtlab serve</code>, then reload.';
    fail($('stage'), why);
    return;
  }

  const { renderer, scene, camera } = makeScene($('gl'), court, kitOf(ros.game.home));
  camera.fov = 26; camera.updateProjectionMatrix();
  const target = onFloor(-22, 0, 2);
  const fit = () => {
    const scale = Math.min(innerWidth / W, innerHeight / H);
    $('stage').style.transform = `scale(${scale}) translate(-50%, -50%)`;
    renderer.setPixelRatio(Math.min(2, Math.max(1, devicePixelRatio * scale)));
    renderer.setSize(W, H, false);
  };
  addEventListener('resize', fit); fit();
  wireInfo($('stage'));  // delegated: the columns are rebuilt on every player change and keep their `i`

  const g = ros.game;
  $('match').textContent = `${short(g.home)} ${g.score[0]}–${g.score[1]} ${short(g.away)}`;
  $('match').title = `${g.home} (home) – ${g.away}`;
  badge($('badge-home'), kitOf(g.home)); badge($('badge-away'), kitOf(g.away));
  $('context').innerHTML = `${g.competition} · ${date(g.date)} · the roster · SkillCorner open data · ${REFS}`;
  const sideOf = { home: ros.teams.find((t) => t.side === 'home'), away: ros.teams.find((t) => t.side === 'away') };
  for (const b of $('teams').querySelectorAll('button')) b.textContent = short(sideOf[b.dataset.tab].team);

  let list = null, team = null, focused = null, chipFocus = -1;
  const show = (p) => {
    focused = p; chipFocus = -1;
    $('p-num').textContent = `#${p.jersey}`; $('p-name').textContent = p.name;
    $('p-sub').textContent = `${team.team} · ${mmss(p.game.seconds)} on the tracked play${p.season ? ` · ${p.season.games} games in SkillCorner's season aggregates` : ''}`;
    badge($('p-badge'), kitOf(team.team));
    const c = columns(p);
    // one shared grid: each row is placed at the same grid-row across the three columns, so a taller cell (a two- or three-name list)
    // only stretches its own row, never breaks alignment with the rows after it — the three lists can differ in length or line count
    // and their dividers still line up, the way a real table's do.
    // the three columns answer three different questions about where a figure came from, so each carries its own `i`
    const titled = [['This game', c.game, ['tracking']], ['Defence', c.def, ['beyond', 'price', 'look']], ['Season · SkillCorner aggregates', c.season, ['season']]];
    let html = titled.map(([title, , ids], ci) => `<p class="section" style="grid-column:${ci + 1};grid-row:1">${title}${infoMark(...ids)}</p>`).join('');
    titled.forEach(([, rows], ci) => {
      rows.forEach((r, ri) => { html += `<div class="row${ri === 0 ? ' first' : ''}" style="grid-column:${ci + 1};grid-row:${ri + 2}"><span class="k">${r.k}</span><span class="v">${r.v}</span></div>`; });
    });
    $('cols').innerHTML = html;
    $('plays-head').textContent = p.plays.length ? `Plays on this machine he appears in · ↵ opens one, E through his eyes` : 'No exported play on this machine has him in it';
    $('p-plays').innerHTML = p.plays.map((q, k) => `<button class="chip" data-k="${k}" title="${q.story || ''}">Q${q.period} ${q.clock || ''} <em>${q.side === 'attack' ? 'attacking' : 'defending'}${q.chance === HERO ? ' · featured' : ''}</em></button>`).join('');
    [...$('p-plays').children].forEach((b, k) => { b.onclick = () => openPlay(p.plays[k], false); b.onmouseenter = () => { chipFocus = k; markChip(); }; });
  };
  const markChip = () => { [...$('p-plays').children].forEach((b, k) => b.setAttribute('aria-selected', String(k === chipFocus))); };
  const openPlay = (q, eyes) => {
    const u = new URLSearchParams({ chance: q.chance, play: '1' });
    if (eyes) { u.set('cam', 'eyes'); u.set('eyes', String(focused.id)); u.set('view', 'figures'); }
    dip(() => { location.href = `./?${u}`; });
  };
  const render = (side, playerId) => {
    team = sideOf[side];
    $('players').innerHTML = '';
    $('players-section').textContent = `${team.team} · by minutes on the tracked play`;
    list = new FocusList($('players'), team.players, {
      className: 'item player', visible: 12,
      render: (b, p) => {
        const sh = p.game.shots, bits = [sh.n ? `${sh.made}/${sh.n} FG` : 'no shot', p.defence.closeouts ? `${p.defence.closeouts.n} close-out${p.defence.closeouts.n === 1 ? '' : 's'}` : '', p.defence.guarded[0] ? `guarded ${p.defence.guarded[0].who}` : ''].filter(Boolean);
        b.innerHTML = `<span class="jersey">${p.jersey}</span><span class="meta"><span class="teams">${p.name}</span><span class="sub">${bits.join(' · ')}</span></span><span class="mins">${mmss(p.game.seconds)}</span>`;
      },
      onFocus: (p) => show(p),
      onOpen: (p) => { if (p.plays.length) openPlay(p.plays.find((q) => q.chance === HERO) || p.plays[0], false); },
    });
    const k = playerId ? team.players.findIndex((p) => p.id === playerId) : 0;
    list.setFocus(Math.max(0, k), true);
    tabs.set(side);
  };
  const tabs = new Tabs($('teams'), { onChange: (side) => { const q = new URLSearchParams(location.search); q.set('team', side); q.delete('player'); history.replaceState({}, '', `?${q}`); render(side, null); } });
  keys(document.querySelector('.keys'), [[['↑', '↓'], 'Choose'], [['↵'], 'Open his play'], [['E'], 'Through his eyes'], [['⇥'], 'Other team'], [['Esc'], 'Back to the match']]);
  const side = ['home', 'away'].includes(params.get('team')) ? params.get('team') : 'home';
  render(side, params.has('player') ? Number(params.get('player')) : null);

  $('back').onclick = () => dip(() => { location.href = `report.html?game=${game}&team=${tabs.value}`; });
  addEventListener('pageshow', (e) => { if (e.persisted) $('dip').classList.remove('on'); });
  addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { $('back').click(); return; }
    if (e.key === 'Tab') { e.preventDefault(); const other = tabs.value === 'home' ? 'away' : 'home'; tabs.set(other); tabs.buttons.find((b) => b.dataset.tab === other).click(); return; }
    if ((e.key === 'e' || e.key === 'E') && focused && focused.plays.length) { openPlay(focused.plays[Math.max(0, chipFocus)], true); return; }
    if (e.key === 'ArrowRight' && focused && focused.plays.length) { e.preventDefault(); chipFocus = (chipFocus + 1) % focused.plays.length; markChip(); return; }
    if (e.key === 'ArrowLeft' && focused && focused.plays.length) { e.preventDefault(); chipFocus = (chipFocus - 1 + focused.plays.length) % focused.plays.length; markChip(); return; }
    if (e.key === 'Enter' && chipFocus >= 0) { e.preventDefault(); openPlay(focused.plays[chipFocus], false); return; }
    list.key(e);
  });

  [...document.querySelectorAll('#stage.roster .title, #stage.roster .topright, .players-col > *')].forEach((el, i) => el.style.setProperty('--i', i));
  $('profile').style.setProperty('--i', 4); document.querySelector('.keys').style.setProperty('--i', 6);
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
