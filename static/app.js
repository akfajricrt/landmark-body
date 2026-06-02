// app.js — Komponen Alpine.js untuk UI Punch Trainer (game latihan tinju).
//
// Tampilan saja — deteksi pukulan terjadi di Python (camera.py + analysis.py).
//   • WebSocket native (/ws) untuk status game real-time (flask-sock = WS biasa).
//   • Tombol Play (mulai) & Stop (berhenti, tanpa simpan riwayat).
//   • Toast (Toastify) saat HIT/MISS, dipicu lewat perubahan last_event.seq.

function boxing() {
  return {
    // ---------------- state ----------------
    conn: "off",
    status: "idle",            // "idle" | "playing"
    metrics: { left: { ext: null, speed: null }, right: { ext: null, speed: null } },
    target: null,
    stats: {
      score: 0, combo: 0, best_combo: 0, punches: 0, hits: 0, accuracy: 0,
      avg_speed: 0, best_speed: 0, last_reaction_ms: 0, avg_reaction_ms: 0,
      elapsed_sec: 0,
    },
    busy: false,
    videoError: false,

    _ws: null,
    _lastSeq: 0,

    // ---------------- lifecycle ----------------
    init() {
      this.connectWS();
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
      const w = this.target.r * 200; // diameter = 2r, sebagai % lebar arena
      return `left:${this.target.x * 100}%; top:${this.target.y * 100}%; width:${w}%;`;
    },

    // ---------------- WebSocket ----------------
    connectWS() {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      const ws = new WebSocket(`${proto}://${location.host}/ws`);
      this._ws = ws;
      ws.onopen = () => { this.conn = "on"; };
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
      this.status = fb.status;
      this.metrics = fb.metrics || this.metrics;
      this.target = fb.target || null;
      this.stats = fb.stats || this.stats;

      // Toast hanya saat ada event baru (HIT/MISS) — pakai seq agar tak terlewat.
      const ev = fb.last_event;
      if (ev && ev.seq && ev.seq !== this._lastSeq) {
        this._lastSeq = ev.seq;
        if (ev.type === "hit") {
          this._toast(`🥊 HIT! x${ev.combo} · ⚡${ev.speed} m/s · ${ev.reaction_ms}ms`, "hit");
        } else if (ev.type === "miss") {
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

    // ---------------- aksi REST ----------------
    async play() {
      this.busy = true;
      this._lastSeq = 0;
      try {
        await fetch("/api/play", { method: "POST" });
        this._toast("🔔 Mulai — tinju targetnya!", "hit");
      } catch (_) {
        this._toast("Tidak bisa menghubungi server.", "miss");
      } finally {
        this.busy = false;
      }
    },

    async stop() {
      try {
        const res = await fetch("/api/stop", { method: "POST" });
        const data = await res.json();
        const s = data.summary || {};
        this._toast(`⏹ Berhenti · Skor ${s.score ?? 0} · ${s.hits ?? 0} kena`, "miss");
      } catch (_) {
        this._toast("Tidak bisa menghubungi server.", "miss");
      }
    },
  };
}
