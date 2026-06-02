// app.js — Komponen Alpine.js untuk UI Study Guardian.
//
// Tanggung jawab (sisi tampilan saja — deteksi pose ada di Python/Jetson):
//   • WebSocket native (/ws) untuk status real-time  -> flask-sock = WS biasa,
//     JANGAN pakai socket.io.
//   • Tombol Kalibrasi & Akhiri Sesi (REST).
//   • Toast (Toastify) hanya saat transisi baik -> buruk, supaya tidak spam.
//   • Grafik tren skor (Chart.js) + format waktu (Day.js).
//
// Dipakai lewat  x-data="guardian()"  pada <body>. Fungsi ini global dan
// dimuat sebelum Alpine, jadi tersedia saat Alpine init.

function guardian() {
  return {
    // ---------------- state ----------------
    conn: "off",
    status: "need_calibration",
    metrics: { head_ratio: null, eye_width: null, tilt_deg: null },
    flags: { slouching: false, too_close: false, tilted: false, break_due: false },
    stats: {
      posture_score: 100, elapsed_sec: 0,
      slouch_events: 0, close_events: 0, tilt_events: 0,
    },
    calibrating: false,
    videoError: false,
    history: [],

    _ws: null,
    _prevFlags: { slouching: false, too_close: false, tilted: false },
    _chart: null,

    // ---------------- lifecycle ----------------
    init() {
      this.connectWS();
      this.loadHistory();
    },

    // ---------------- computed ----------------
    get statusText() {
      return this.status === "good" ? "Postur Baik"
        : this.status === "warn" ? "Perlu Diperbaiki"
        : "Perlu Kalibrasi";
    },
    get statusClass() {
      return this.status === "good" ? "is-good"
        : this.status === "warn" ? "is-warn"
        : "is-calib";
    },
    get elapsedText() {
      const s = this.stats.elapsed_sec || 0;
      const h = Math.floor(s / 3600);
      const m = Math.floor((s % 3600) / 60);
      const sec = s % 60;
      const mm = String(m).padStart(2, "0");
      const ss = String(sec).padStart(2, "0");
      return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
    },
    get totalEvents() {
      return (this.stats.slouch_events || 0) +
             (this.stats.close_events || 0) +
             (this.stats.tilt_events || 0);
    },
    get scoreRingStyle() {
      // Cincin progres skor: warna mengikuti kualitas skor.
      const v = Math.max(0, Math.min(100, this.stats.posture_score || 0));
      const col = v >= 80 ? "#5fa17a" : v >= 60 ? "#d98a3d" : "#cf6b5a";
      return `background: conic-gradient(${col} ${v * 3.6}deg, var(--ring-track) 0deg);`;
    },

    // ---------------- helpers ----------------
    fmt(v, d = 2) {
      return (v === null || v === undefined) ? "–" : Number(v).toFixed(d);
    },
    scoreBadgeClass(score) {
      if (score === null || score === undefined) return "h-score--calib";
      return score >= 80 ? "h-score--good" : score >= 60 ? "h-score--warn" : "h-score--bad";
    },
    histLabel(iso) {
      return iso ? dayjs(iso).format("DD MMM · HH:mm") : "–";
    },
    histDur(sec) {
      const s = sec || 0;
      const m = Math.floor(s / 60);
      return `${m}m ${String(s % 60).padStart(2, "0")}s`;
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
        setTimeout(() => this.connectWS(), 1500); // sambung ulang otomatis
      };
      ws.onerror = () => ws.close();
    },

    onFeedback(fb) {
      this.status = fb.status;
      this.metrics = fb.metrics || { head_ratio: null, eye_width: null, tilt_deg: null };
      this.flags = fb.flags || this.flags;
      this.stats = fb.stats || this.stats;
      this._notifyEdges();
    },

    // Toast hanya pada transisi false -> true agar tidak spam tiap frame.
    _notifyEdges() {
      const f = this.flags;
      const p = this._prevFlags;
      if (f.slouching && !p.slouching) this._toast("🪑 Punggung membungkuk — tegakkan badan.", "warn");
      if (f.too_close && !p.too_close) this._toast("🔍 Wajah terlalu dekat — mundur sedikit.", "warn");
      if (f.tilted && !p.tilted) this._toast("↔️ Badan miring — luruskan bahu.", "warn");
      if (f.break_due) this._toast("☕ Istirahat 20-20-20 — lihat objek jauh selama 20 detik.", "info");
      this._prevFlags = { slouching: f.slouching, too_close: f.too_close, tilted: f.tilted };
    },

    _toast(text, kind = "info") {
      const bg = kind === "warn"
        ? "linear-gradient(135deg, #e0913f, #c8743a)"
        : "linear-gradient(135deg, #5fa17a, #4f8a86)";
      Toastify({
        text,
        duration: 4000,
        gravity: "top",
        position: "right",
        close: true,
        stopOnFocus: true,
        style: {
          background: bg,
          borderRadius: "14px",
          boxShadow: "0 10px 30px rgba(120, 90, 60, .28)",
          fontWeight: "600",
          padding: "14px 18px",
        },
      }).showToast();
    },

    // ---------------- aksi REST ----------------
    async calibrate() {
      this.calibrating = true;
      try {
        const res = await fetch("/api/calibrate", { method: "POST" });
        const data = await res.json();
        if (!res.ok) this._toast(data.error || "Kalibrasi gagal.", "warn");
        else this._toast("✅ Kalibrasi berhasil — baseline tersimpan.", "info");
      } catch (_) {
        this._toast("Tidak bisa menghubungi server.", "warn");
      } finally {
        this.calibrating = false;
      }
    },

    async endSession() {
      if (!confirm("Akhiri sesi dan simpan ke riwayat?")) return;
      try {
        const res = await fetch("/api/session/end", { method: "POST" });
        const data = await res.json();
        const s = data.summary || {};
        this._toast(
          `Sesi ${data.saved ? "tersimpan" : "selesai (DB tak aktif)"} · Skor ${s.posture_score}`,
          "info"
        );
        this.loadHistory();
      } catch (_) {
        this._toast("Tidak bisa menghubungi server.", "warn");
      }
    },

    async loadHistory() {
      try {
        const res = await fetch("/api/history");
        this.history = await res.json();
        // Tunggu DOM render (x-show) sebelum gambar chart.
        this.$nextTick(() => this.renderChart());
      } catch (_) {
        this.history = [];
      }
    },

    // ---------------- grafik tren (Chart.js) ----------------
    renderChart() {
      const el = document.getElementById("trendChart");
      if (!el || !this.history.length) return;

      const rows = [...this.history].reverse(); // lama -> baru
      const labels = rows.map((r) => dayjs(r.started_at).format("DD/MM HH:mm"));
      const data = rows.map((r) => r.posture_score ?? 0);

      if (this._chart) this._chart.destroy();
      const ctx = el.getContext("2d");
      const grad = ctx.createLinearGradient(0, 0, 0, 180);
      grad.addColorStop(0, "rgba(200, 127, 74, .35)");
      grad.addColorStop(1, "rgba(200, 127, 74, 0)");

      this._chart = new Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [{
            data,
            fill: true,
            backgroundColor: grad,
            borderColor: "#c87f4a",
            borderWidth: 2.5,
            tension: 0.35,
            pointRadius: 3,
            pointHoverRadius: 5,
            pointBackgroundColor: "#c87f4a",
          }],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false }, tooltip: { displayColors: false } },
          scales: {
            y: { min: 0, max: 100, ticks: { stepSize: 25, color: "#9a8f86" },
                 grid: { color: "#ece3d8" } },
            x: { ticks: { color: "#9a8f86", maxRotation: 0, autoSkip: true, maxTicksLimit: 6 },
                 grid: { display: false } },
          },
        },
      });
    },
  };
}
