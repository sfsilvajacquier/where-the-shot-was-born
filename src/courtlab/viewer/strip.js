// The tension strip: one row per attacker, one column per frame, coloured by how far his defender is beyond
// his normal spot. Above it, what SkillCorner labels in the possession. It is also the scrubber.

import { css } from './palette.js';

const LABELS = 212;     // px kept for the names on the left
const LANE = 25;        // one lane of action chips
const PASSES = 23;      // the lane of numbered passes
const ROW = 19, ROW_GAP = 5;
const AXIS = 27;
const INK = '#f4f7fb', INK_2 = '#a3aec0', INK_3 = '#6b7890';

const surname = (name) => {
  const parts = name.split(' ');
  return parts.length > 2 && parts[parts.length - 1].length < 4 ? parts.slice(-2).join(' ') : parts[parts.length - 1];
};

export class Strip {
  constructor(canvas, data, { onSeek, onHover }) {
    this.cv = canvas; this.d = data; this.onSeek = onSeek; this.onHover = onHover;
    this.n = data.frames.idx.length;
    this.attack = data.players.filter((p) => p.side === 'attack');
    this.names = new Map(data.players.map((p) => [p.id, surname(p.name)]));
    this.shot = data.actions.find((a) => a.type === 'shot') || null;
    this.zero = this.shot ? this.shot.i : this.n - 1;
    this.chips = this.markers();
    this.base = null;
    const seek = (e) => { const t = this.frameAt(e); if (t != null) this.onSeek(t); };
    canvas.addEventListener('pointerdown', (e) => { canvas.setPointerCapture(e.pointerId); this.dragging = true; seek(e); });
    canvas.addEventListener('pointermove', (e) => { if (this.dragging) seek(e); this.hover(e); });
    canvas.addEventListener('pointerup', () => { this.dragging = false; });
    canvas.addEventListener('pointerleave', () => this.onHover(null));
  }

  /** The labelled actions, packed into as few lanes as they need. Passes after the ball screen are numbered. */
  markers() {
    const d = this.d, out = [];
    const pick = d.actions.find((a) => a.type === 'pick');
    let pass = 0;
    for (const a of d.actions) {
      if (a.i == null) continue;
      if (a.type === 'screen') out.push({ i: a.i, text: 'Off-ball screen' });
      else if (a.type === 'handoff') out.push({ i: a.i, text: 'Hand-off' });
      else if (a.type === 'pick') out.push({ i: a.i, text: `Ball screen · defended ${a.coverage}`, strong: true });
      else if (a.type === 'drive') out.push({ i: a.i, text: a.beat ? 'Drive · beats his man' : 'Drive' });
      else if (a.type === 'isolation') out.push({ i: a.i, text: 'Isolation' });
      else if (a.type === 'post') out.push({ i: a.i, text: 'Post-up' });
      else if (a.type === 'shot') out.push({ i: a.i, text: `${a.three ? 'Three' : 'Shot'} · ${a.made ? 'made' : 'missed'}`, strong: true });
      else if (a.type === 'pass' && a.complete && pick && a.i > pick.i) { pass += 1; out.push({ i: a.i, pass }); }
    }
    out.sort((p, q) => p.i - q.i);
    return out;
  }

  resize(ratio) {
    const w = this.cv.clientWidth;
    if (!w) return;  // folded away: keep the last layout, draw nothing
    this.ratio = ratio; this.w = w;
    this.x0 = LABELS; this.x1 = w - 4;
    // pack the chips into as few lanes as they need, left to right
    const c = document.createElement('canvas').getContext('2d'), placed = [];
    for (const chip of this.chips.filter((k) => !k.pass)) {
      c.font = `${chip.strong ? 600 : 500} 15px Inter`;
      chip.w = c.measureText(chip.text).width + 20;
      chip.x = Math.min(this.X(chip.i), this.x1 - chip.w);
      chip.lane = 0;
      while (placed.some((p) => p.lane === chip.lane && chip.x < p.x + p.w + 8 && p.x < chip.x + chip.w + 8)) chip.lane += 1;
      placed.push(chip);
    }
    this.lanes = Math.max(1, ...placed.map((p) => p.lane + 1));
    this.passY = 8 + this.lanes * LANE + PASSES / 2;
    this.rowsTop = 8 + this.lanes * LANE + PASSES + 6;
    this.height = this.rowsTop + this.attack.length * (ROW + ROW_GAP) + AXIS;
    this.cv.style.height = `${this.height}px`;
    this.cv.width = Math.round(w * ratio); this.cv.height = Math.round(this.height * ratio);
    this.base = null;
  }

  X(i) { return this.x0 + (i / (this.n - 1)) * (this.x1 - this.x0); }

  frameAt(e) {
    const r = this.cv.getBoundingClientRect(), x = ((e.clientX - r.left) / r.width) * this.w;
    if (x < this.x0 - 8) return null;
    return Math.min(this.n - 1, Math.max(0, ((x - this.x0) / (this.x1 - this.x0)) * (this.n - 1)));
  }

  hover(e) {
    const r = this.cv.getBoundingClientRect(), y = ((e.clientY - r.top) / r.height) * this.height, t = this.frameAt(e);
    const row = Math.floor((y - this.rowsTop) / (ROW + ROW_GAP));
    if (t == null || row < 0 || row >= this.attack.length) { this.onHover(null); return; }
    const p = this.attack[row], i = Math.round(t), guard = this.d.guard[p.id][i];
    this.onHover({ x: e.clientX, y: e.clientY, name: this.names.get(p.id), guard: guard ? this.names.get(guard) : null,
      extra: this.d.extra[p.id][i], gap: this.d.gap[p.id][i], seconds: (i - this.zero) / this.d.fps });
  }

  /** Everything that does not depend on the playhead, drawn once. */
  paint() {
    const off = document.createElement('canvas');
    off.width = this.cv.width; off.height = this.cv.height;
    const c = off.getContext('2d');
    c.scale(this.ratio, this.ratio);
    const d = this.d;

    // what SkillCorner labels, and the passes that follow the ball screen, numbered
    const rowsBottom = this.rowsTop + this.attack.length * (ROW + ROW_GAP) - ROW_GAP;
    c.textBaseline = 'middle';
    for (const chip of this.chips) {
      const x = this.X(chip.i);
      if (chip.pass) {
        c.fillStyle = 'rgba(255,255,255,0.14)'; c.beginPath(); c.arc(x, this.passY, 9.5, 0, Math.PI * 2); c.fill();
        c.fillStyle = INK; c.font = '600 12px Inter'; c.textAlign = 'center'; c.fillText(String(chip.pass), x, this.passY + 0.5);
        c.fillStyle = 'rgba(255,255,255,0.16)'; c.fillRect(x - 0.5, this.passY + 10, 1, rowsBottom - this.passY - 10);
        continue;
      }
      const y = 8 + chip.lane * LANE;
      c.fillStyle = 'rgba(255,255,255,0.3)'; c.fillRect(x - 0.5, y, 1, rowsBottom - y);
      c.font = `${chip.strong ? 600 : 500} 15px Inter`;
      c.fillStyle = chip.strong ? 'rgba(42,52,74,0.98)' : 'rgba(28,36,54,0.98)';
      c.beginPath(); c.roundRect(chip.x, y, chip.w, LANE - 5, 6); c.fill();
      c.fillStyle = chip.strong ? INK : INK_2; c.textAlign = 'left'; c.fillText(chip.text, chip.x + 10, y + (LANE - 5) / 2 + 0.5);
    }

    // rows
    const inPlay = (i) => this.attack.some((p) => d.guard[p.id][i]);
    this.attack.forEach((p, r) => {
      const y = this.rowsTop + r * (ROW + ROW_GAP);
      c.textAlign = 'left'; c.textBaseline = 'middle';
      c.fillStyle = INK_3; c.font = '600 14px Inter'; c.fillText(String(p.jersey).padStart(2, ' '), 0, y + ROW / 2 + 0.5);
      c.fillStyle = INK; c.font = '500 16px Inter'; c.fillText(this.names.get(p.id), 30, y + ROW / 2 + 0.5);
      c.save();
      c.beginPath(); c.roundRect(this.x0, y, this.x1 - this.x0, ROW, 5); c.clip();
      c.fillStyle = 'rgba(255,255,255,0.04)'; c.fillRect(this.x0, y, this.x1 - this.x0, ROW);
      const step = (this.x1 - this.x0) / (this.n - 1);
      const edge = (i) => Math.round((this.X(i) - step / 2) * this.ratio) / this.ratio;  // cells meet on device pixels: no seams
      let open = null;
      for (let i = 0; i < this.n; i += 1) {
        const e = d.extra[p.id][i];
        if (e != null) { c.fillStyle = css(e, e < 0 ? 0.6 : 1); c.fillRect(edge(i), y, edge(i + 1) - edge(i), ROW); }
        const nobody = e == null && inPlay(i);
        if (nobody && open == null) open = i;
        if ((!nobody || i === this.n - 1) && open != null) {
          if (i - open >= d.fps) this.hatch(c, edge(open), y, edge(i) - edge(open), (i - open) / d.fps);  // under a second it is a hand-over between two defenders, not a man left alone
          open = null;
        }
      }
      c.restore();
    });

    // seconds to the release
    const yAxis = this.rowsTop + this.attack.length * (ROW + ROW_GAP) + 2;
    c.textBaseline = 'top'; c.textAlign = 'center'; c.font = '500 13px Inter';
    const first = Math.ceil(-this.zero / d.fps), last = Math.floor((this.n - 1 - this.zero) / d.fps);
    for (let s = first; s <= last; s += 1) {
      const x = this.X(this.zero + s * d.fps), major = s % 2 === 0;
      c.fillStyle = major ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.18)'; c.fillRect(x - 0.5, yAxis, 1, major ? 7 : 4);
      if (major) { c.fillStyle = s === 0 ? INK : INK_3; c.fillText(s === 0 ? 'release' : `${s > 0 ? '+' : '−'}${Math.abs(s)} s`, x, yAxis + 10); }
    }
    this.base = off;
  }

  hatch(c, x, y, w, seconds) {
    c.save();
    c.beginPath(); c.rect(x, y, w, ROW); c.clip();
    c.fillStyle = 'rgba(5,8,14,0.55)'; c.fillRect(x, y, w, ROW);
    c.strokeStyle = 'rgba(163,174,192,0.5)'; c.lineWidth = 1.2;
    for (let k = x - ROW; k < x + w + ROW; k += 7) { c.beginPath(); c.moveTo(k, y + ROW); c.lineTo(k + ROW, y); c.stroke(); }
    c.restore();
    if (w > 150) {
      const text = `nobody on him · ${seconds.toFixed(1)} s`;
      c.font = '600 13px Inter'; c.textAlign = 'center'; c.textBaseline = 'middle';
      const tw = c.measureText(text).width + 16;
      c.fillStyle = 'rgba(8,12,22,0.86)'; c.beginPath(); c.roundRect(x + w / 2 - tw / 2, y + 2, tw, ROW - 4, 4); c.fill();
      c.fillStyle = INK; c.fillText(text, x + w / 2, y + ROW / 2 + 0.5);
    }
  }

  draw(t) {
    if (!this.cv.clientWidth || !this.w) return;
    if (!this.base) this.paint();
    const c = this.cv.getContext('2d');
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, this.cv.width, this.cv.height);
    c.drawImage(this.base, 0, 0);
    c.scale(this.ratio, this.ratio);
    const x = this.X(t), top = this.rowsTop, bottom = top + this.attack.length * (ROW + ROW_GAP) - ROW_GAP;
    if (this.chapter) {  // the chapter the play is in: a faint band under the rows
      const a = this.X(this.chapter.i0), b = this.X(this.chapter.i1 + 1);
      c.fillStyle = 'rgba(255,255,255,0.07)'; c.fillRect(a, top - 4, b - a, bottom - top + 8);
      c.fillStyle = 'rgba(255,255,255,0.35)'; c.fillRect(a, top - 4, b - a, 1);
    }
    c.fillStyle = 'rgba(8,12,22,0.6)';  // what has not happened yet is dimmed
    c.fillRect(x, top - 2, this.x1 - x + 2, bottom - top + 4);
    c.fillStyle = INK; c.fillRect(x - 1, this.passY - PASSES / 2, 2, bottom - this.passY + PASSES / 2 + 3);
    c.beginPath(); c.arc(x, bottom + 3, 5, 0, Math.PI * 2); c.fill();
  }
}
