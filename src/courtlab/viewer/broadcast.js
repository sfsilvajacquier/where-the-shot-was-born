// The real footage beside the animation. The clip lives OUTSIDE the repository (served from ../broadcast by `courtlab serve`)
// and is only ever shown, never read: nothing in the viewer or the package takes a number from it.
// Sync rule: `release_s` in broadcast/sync.json is the second of the clip at which the ball leaves the shooter's hands;
// it is pinned to the possession's shot frame, so clip time = release_s + (t − shot.i) / fps.

export class Broadcast {
  constructor(panel, data) {
    this.panel = panel; this.video = panel.querySelector('video'); this.d = data;
    this.shot = data.actions.find((a) => a.type === 'shot') || null;
    this.ready = false; this.on = false; this.entry = null;
  }

  /** Looks for a clip of this possession; resolves true when there is one. */
  async probe(chance) {
    try {
      const sync = await (await fetch('broadcast/sync.json', { cache: 'no-store' })).json();
      const e = sync[chance];
      if (!e || !this.shot) return false;
      const head = await fetch(`broadcast/${e.file}`, { method: 'HEAD' });
      if (!head.ok) return false;
      this.entry = e;
      this.video.src = `broadcast/${e.file}`;
      this.video.muted = true;
      await new Promise((ok) => { this.video.onloadedmetadata = ok; this.video.onerror = ok; });
      this.ready = this.video.readyState >= 1;
      return this.ready;
    } catch (err) {
      return false;
    }
  }

  show(on) {
    this.on = on && this.ready;
    if (!this.on) { this.panel.hidden = true; this.video.pause(); }
  }

  clipTime(t) { return this.entry.release_s + (t - this.shot.i) / this.d.fps; }

  /** Keep the clip on the animation's clock. The window exists only while the clip has a picture for this instant:
   *  the clip is shorter than the possession, so it appears when the play reaches it and goes away when you scrub back. */
  sync(t, playing) {
    if (!this.on) return;
    const want = this.clipTime(t), v = this.video;
    const inRange = want >= 0 && want <= (v.duration || Infinity) - 0.05;
    this.panel.hidden = !inRange;
    if (!inRange) { if (!v.paused) v.pause(); return; }
    if (playing) {
      if (v.paused) { v.currentTime = want; v.play().catch(() => {}); }
      else if (Math.abs(v.currentTime - want) > 0.08) v.currentTime = want;
    } else {
      if (!v.paused) v.pause();
      if (Math.abs(v.currentTime - want) > 0.02) v.currentTime = want;
    }
  }
}
