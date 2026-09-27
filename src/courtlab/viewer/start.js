// The start screen: the games on this machine. The scene keeps running behind the scrim, looping slowly around the featured shot;
// the list, detail and keys are the shared pieces of ui.js. Opening a game goes to its page.

import { FocusList, Detail, keys, miniStrip, short } from './ui.js';
import { kitOf, badge } from './kits.js';

export { short };
const FPS = 25;
const HERO = 'chance-191313-1-7';
const signed = (v, nd) => (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(nd);
const chip = (c) => (c.value == null ? '–' : c.unit === 'ft' ? signed(c.value, 1) + ' ft' : c.unit === '%' ? `${Math.round(c.value)} %` : `${c.value} ${c.unit}`);
const when = (iso) => { const t = iso ? new Date(`${iso}T12:00:00Z`) : null; return t && !Number.isNaN(t.getTime()) ? t.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }) : ''; };

export class Start {
  constructor(root, data, hooks) {
    this.root = root; this.d = data; this.hooks = hooks;
    // the featured play's game first, then by date
    const games = [...(data.__games || [])];
    const heroGame = games.find((g) => g.plays.some((p) => p.chance === HERO));
    games.sort((a, b) => (a === heroGame ? -1 : b === heroGame ? 1 : (b.date || '').localeCompare(a.date || '')));
    const lead = (g) => g.plays.find((p) => p.chance === HERO) || g.plays.find((p) => !p.moment) || g.plays[0];
    this.shot = data.actions.find((a) => a.type === 'shot') || null;
    this.n = data.frames.idx.length;
    this.on = false; this.seam = false;
    this.detail = new Detail(root.querySelector('#detail'));
    const el = (id) => root.querySelector(id);
    this.games = new FocusList(root.querySelector('#games'), games, {
      render: (b, g) => {
        const score = g.score ? `${g.score[0]}–${g.score[1]}` : 'v';
        const bits = [when(g.date), `${g.plays.length} play${g.plays.length === 1 ? '' : 's'}`, g === heroGame ? '<em>Featured</em>' : '', g.plays.some((p) => p.clip) ? '<em>TV clip</em>' : ''].filter(Boolean);
        b.innerHTML = `<span class="meta"><span class="teams"><canvas class="badge" width="56" height="56"></canvas><span>${short(g.home)} ${score} ${short(g.away)}</span><canvas class="badge" width="56" height="56"></canvas></span><span class="sub">${bits.join(' · ')}</span></span><canvas class="mini" width="320" height="48"></canvas>`;
        const [bh, ba] = b.querySelectorAll('.badge');  // each crest beside its club, as on a scoreboard
        badge(bh, kitOf(g.home)); badge(ba, kitOf(g.away));
        const p = lead(g);
        miniStrip(b.querySelector('canvas.mini'), p && p.thumb, p && p.release);  // the featured play's tension strip, the one the tiles below explain
      },
      onFocus: (g, k, silent) => this.detail.show(() => {
        const p = lead(g);
        el('#detail-section').textContent = `${short(g.home)} ${g.score ? `${g.score[0]}–${g.score[1]}` : 'v'} ${short(g.away)}`;
        el('#detail-story').textContent = p ? `${p.chance === HERO ? 'Featured play' : 'Play'} · ${p.story || `${short(p.shooter)} shoots`}` : '';
        el('#detail-chips').innerHTML = p ? (p.chapters || []).map((c) => `<span class="chip"><b>${chip(c)}</b>${c.title}</span>`).join('') : '';
        el('#detail-line').textContent = g.rotations ? `What the rotations cost: ${short(g.home)} ${signed(g.rotations.home, 1)} pts, ${short(g.away)} ${signed(g.rotations.away, 1)} pts · ${g.moments} moments to watch again.` : 'No match report yet: run courtlab report for this game.';
        return true;
      }, silent),
      onOpen: (g) => this.hooks.open(g.game),
    });
    keys(root.querySelector('.keys'), [[['↵'], 'Open the match'], [['↑', '↓'], 'Choose'], [['P'], 'Players'], [['G'], 'References']]);
    root.querySelector('#players').onclick = () => this.hooks.players();
    root.querySelector('#refs').onclick = () => this.hooks.refs();
    this.games.focusWhere((g) => g.game === (data.source && data.source.game_id));  // focus memory: the game you came from
    [...root.querySelectorAll('.col > *')].forEach((e, i) => e.style.setProperty('--i', i));  // the entrance order: every block, then each row
    root.querySelector('.detail').style.setProperty('--i', 9); root.querySelector('.keys').style.setProperty('--i', 10);
  }

  key(e) { if (e.key === 'p' || e.key === 'P') { this.hooks.players(); return; } if (e.key === 'g' || e.key === 'G') { this.hooks.refs(); return; } this.games.key(e); }

  /** The background loop: from six seconds before the shot to two after, at the page's slow speed. The seam is a dip, not a jump. */
  loopStart() { return this.shot ? Math.max(0, this.shot.i - 6 * FPS) : 0; }
  loopEnd() { return this.shot ? Math.min(this.n - 1, this.shot.i + 2 * FPS) : this.n - 1; }
  loop(t, dip) {
    const end = this.loopEnd();
    if (t < end || this.seam) return Math.min(t, end);
    this.seam = true;
    dip(() => { this.seam = false; this.restart = true; });
    return end;
  }

  show() { this.on = true; this.root.hidden = false; }
  hide() { this.on = false; this.root.hidden = true; }
}
