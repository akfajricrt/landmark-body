// app.js — Komponen Alpine.js untuk UI Punch Trainer (game latihan tinju).
//
// Tampilan saja — deteksi pukulan terjadi di Python (camera.py + analysis.py).
//   • WebSocket native (/ws) untuk status game real-time (flask-sock = WS biasa).
//   • Tombol Play (mulai) & Stop (berhenti).
//   • Toast (Toastify) saat HIT/MISS, dipicu lewat perubahan last_event.seq.
//   • Alert bar untuk pesan backend (tubuh tidak terdeteksi, dll.).
//   • Metrics bar: kecepatan kiri/kanan + akurasi saat playing.

function boxing() {
  return {
    // ---------------- state ----------------
    conn: "off",
    status: "idle",            // "idle" | "playing"
    metrics: { left: { ext: null, speed: null }, right: { ext: null, speed: null } },
    alerts: [],
    target: null,
    stats: {
      score: 0, combo: 0, best_combo: 0, punches: 0, hits: 0, accuracy: 0,
      avg_speed: 0, best_speed: 0, last_reaction_ms: 0, avg_reaction_ms: 0,
      elapsed_sec: 0,
    },
    busy: false,
    videoError: false,

    // ---------------- level kesulitan ----------------
    difficulty: "menengah",
    levels: ["mudah", "menengah", "sulit"],
    levelLabel: { mudah: "Mudah", menengah: "Menengah", sulit: "Sulit" },

    // ---------------- suara ----------------
    soundOn: true,

    _ws: null,
    _lastSeq: 0,
    _audioCtx: null,

    // ---------------- lifecycle ----------------
    init() {
      this.loadSettings();
      this.connectWS();
    },

    async loadSettings() {
      try {
        const res = await fetch("/api/settings");
        const s = await res.json();
        if (s.difficulty) this.difficulty = s.difficulty;
        if (Array.isArray(s.levels) && s.levels.length) this.levels = s.levels;
      } catch (_) { /* pakai default */ }
    },

    async setDifficulty(level) {
      if (level === this.difficulty) return;
      const prev = this.difficulty;
      this.difficulty = level;   // optimistik
      try {
        await fetch("/api/settings", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ difficulty: level }),
        });
        this._toast(`Level: ${this.levelLabel[level] || level}`, "hit");
      } catch (_) {
        this.difficulty = prev;   // gagal → kembalikan
        this._toast("Gagal mengubah level.", "miss");
      }
    },

    // ---------------- computed ----------------
    get statusText() {
      return this.status === "playing" ? "Tinju!" : "Tekan Play";
    },
    get statusClass() {
      return this.status === "playing" ? "is-good" : "is-calib";
    },
    get elapsedText() {
      const s = this.stats.elapsed_sec || 0;
      const m = Math.floor(s / 60);
      return `${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
    },
    get targetStyle() {
      if (!this.target) return "display:none";
      const w = this.target.r * 200; // diameter = 2r sebagai % lebar stage
      return `left:${this.target.x * 100}%; top:${this.target.y * 100}%; width:${w}%;`;
    },

    // ---------------- WebSocket ----------------
    connectWS() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      this._ws = ws;
      ws.onopen  = () => { this.conn = "on"; };
      ws.onmessage = (e) => {
        try { this.onFeedback(JSON.parse(e.data)); } catch (_) { /* abaikan */ }
      };
      ws.onclose = () => {
        this.conn = "off";
        setTimeout(() => this.connectWS(), 1500);
      };
      ws.onerror = () => ws.close();
    },

    onFeedback(fb) {
      this.status  = fb.status;
      this.metrics = fb.metrics || this.metrics;
      this.target  = fb.target  || null;
      this.alerts  = fb.alerts  || [];
      this.stats   = fb.stats   || this.stats;

      // Toast hanya saat ada event baru (HIT/MISS) — pakai seq agar tak terlewat.
      const ev = fb.last_event;
      if (ev && ev.seq && ev.seq !== this._lastSeq) {
        this._lastSeq = ev.seq;
        if (ev.type === "hit") {
          this._sfxHit(ev.combo);
          this._toast(`🥊 HIT! x${ev.combo} · ⚡${ev.speed} m/s · ${ev.reaction_ms}ms`, "hit");
        } else if (ev.type === "miss") {
          this._sfxMiss();
          this._toast("✋ Meleset — kombo putus!", "miss");
        }
      }
    },

    _toast(text, kind) {
      const bg = kind === "hit"
        ? "linear-gradient(135deg, #e23b4e, #c8743a)"
        : "linear-gradient(135deg, #6b7280, #4b5563)";
      Toastify({
        text, duration: 2000, gravity: "top", position: "right",
        close: false, stopOnFocus: true,
        style: {
          background: bg, borderRadius: "14px",
          boxShadow: "0 10px 30px rgba(120, 40, 40, .3)",
          fontWeight: "700", padding: "13px 18px",
        },
      }).showToast();
    },

    // ---------------- suara (Web Audio API, disintesis — tanpa file) ----------
    // AudioContext baru boleh berbunyi setelah gestur user (kebijakan autoplay
    // browser), jadi diinisialisasi saat tombol Play ditekan.
    _initAudio() {
      if (!this._audioCtx) {
        try {
          const AC = window.AudioContext || window.webkitAudioContext;
          this._audioCtx = AC ? new AC() : null;
        } catch (_) { this._audioCtx = null; }
      }
      if (this._audioCtx && this._audioCtx.state === "suspended") {
        this._audioCtx.resume();
      }
    },

    toggleSound() {
      this.soundOn = !this.soundOn;
      if (this.soundOn) { this._initAudio(); this._blip(880, 1100, 0.1, 0.35, "square"); }
    },

    // Nada melengsing (oscillator) — frekuensi awal→akhir dengan envelope cepat.
    _blip(fStart, fEnd, dur, gain, type = "sine") {
      const ctx = this._audioCtx;
      if (!ctx || !this.soundOn) return;
      const t = ctx.currentTime;
      const o = ctx.createOscillator(), g = ctx.createGain();
      o.type = type;
      o.frequency.setValueAtTime(fStart, t);
      o.frequency.exponentialRampToValueAtTime(Math.max(1, fEnd), t + dur);
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(gain, t + 0.005);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(ctx.destination);
      o.start(t); o.stop(t + dur + 0.02);
    },

    // Letupan derau ter-filter → kesan "impact" kepalan.
    _noise(dur, gain, freq) {
      const ctx = this._audioCtx;
      if (!ctx || !this.soundOn) return;
      const t = ctx.currentTime;
      const len = Math.floor(ctx.sampleRate * dur);
      const buf = ctx.createBuffer(1, len, ctx.sampleRate);
      const data = buf.getChannelData(0);
      for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
      const src = ctx.createBufferSource(); src.buffer = buf;
      const bp = ctx.createBiquadFilter(); bp.type = "bandpass";
      bp.frequency.value = freq; bp.Q.value = 0.8;
      const g = ctx.createGain();
      g.gain.setValueAtTime(gain, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      src.connect(bp).connect(g).connect(ctx.destination);
      src.start(t); src.stop(t + dur);
    },

    // HIT: letupan impact + dentum rendah; nada naik seiring kombo.
    _sfxHit(combo) {
      this._noise(0.07, 0.45, 1300);
      const base = 200 + Math.min(combo || 1, 10) * 22;
      this._blip(base, base * 0.5, 0.18, 0.5, "sine");
    },
    // MISS: dentum tumpul menurun.
    _sfxMiss() { this._blip(150, 70, 0.22, 0.3, "sawtooth"); },
    // Mulai: dentang naik dua nada.
    _sfxStart() { this._blip(620, 880, 0.16, 0.4, "square"); },

    // ---------------- aksi REST ----------------
    async play() {
      this.busy = true;
      this._lastSeq = 0;
      this._initAudio();   // gestur user → boleh memutar suara
      try {
        await fetch("/api/play", { method: "POST" });
        this._sfxStart();
        this._toast("🔔 Mulai — tinju targetnya!", "hit");
      } catch (_) {
        this._toast("Tidak bisa menghubungi server.", "miss");
      } finally {
        this.busy = false;
      }
    },

    async stop() {
      this.busy = true;
      try {
        const res  = await fetch("/api/stop", { method: "POST" });
        const data = await res.json();
        const s    = data.summary || {};
        this._toast(`⏹ Berhenti · Skor ${s.score ?? 0} · ${s.hits ?? 0} kena`, "miss");
      } catch (_) {
        this._toast("Tidak bisa menghubungi server.", "miss");
      } finally {
        this.busy = false;
      }
    },
  };
}
