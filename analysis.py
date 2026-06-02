"""
analysis.py — Inti logika game latihan tinju Study Guardian (Punch Trainer).

Modul ini MURNI Python (tanpa OpenCV / MediaPipe) supaya bisa diuji tanpa
kamera (lihat blok __main__ di bawah). Seluruh keputusan game — apakah sebuah
gerakan dianggap pukulan sah, apakah mengenai target, skor & kombo — terjadi di
sini, BUKAN di browser.

Mode: "Target Reaksi" — sebuah target menyala di salah satu zona; pemain harus
"meninju" ke zona itu. Pukulan hanya dihitung bila: (1) cukup CEPAT,
(2) lengan TER-EKSTENSI cukup (relatif jangkauan), dan (3) mendarat di zona
target yang aktif.

Tanpa kalibrasi manual: tekan Play → langsung main. Jangkauan memakai nilai
default universal, lalu MENYESUAIKAN diri (reach adaptif) dengan postur & jarak
kamera tiap pemain selama bermain.

Peningkatan akurasi (vs versi awal):
  1. One-Euro filter pada pergelangan → meredam jitter landmark tanpa menunda
     pukulan cepat (halus saat diam, responsif saat gerak cepat).
  2. Gating arah kecepatan → hanya gerakan yang menjulur KELUAR (menjauh dari
     bahu) yang dihitung pukulan; menarik tangan / jitter lateral diabaikan.
  3. Apex hit-test → posisi pukulan diuji pada PUNCAK ekstensi (titik terjauh),
     bukan saat ambang baru terlewati, sehingga hit/miss lebih akurat.
  4. Reach adaptif → ambang ekstensi belajar dari jangkauan nyata pemain tiap
     siklus julur-tarik (tetap tanpa langkah kalibrasi manual).
"""

import math
import random
import time
from collections import deque, namedtuple
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Ambang & konstanta game (boleh diubah lewat /api/settings)
# --------------------------------------------------------------------------
PUNCH_SPEED_MIN = 1.5      # kecepatan KELUAR pergelangan minimal (unit-layar/detik)
PUNCH_EXTEND_FRAC = 0.70   # pukulan sah bila ekstensi >= 70% jangkauan (adaptif)
REARM_FRAC = 0.55          # harus menarik tangan < 55% jangkauan untuk "isi ulang"
SPEED_SMOOTH = 2           # smoothing vektor kecepatan — 2 frame sudah cukup halus
DEFAULT_REACH = 1.5        # jangkauan awal (extension penuh ≈ 1,5× lebar bahu)
TARGET_RADIUS = 0.18       # radius zona target (koordinat ternormalisasi)
SCORE_BASE = 100           # poin dasar per hit (dikali kombo)
ASSUMED_SHOULDER_M = 0.40  # asumsi lebar bahu (m) untuk estimasi kecepatan m/s

# Reach adaptif — ambang ekstensi menyesuaikan jangkauan nyata pemain.
REACH_ADAPT = 0.25         # laju belajar reach tiap siklus julur-tarik (0..1)
MIN_REACH = 0.6            # batas bawah reach (cegah ambang runtuh)
MAX_REACH = 3.0            # batas atas reach
MIN_PEAK_FOR_ADAPT = 0.5   # puncak ekstensi minimal agar dipakai mengubah reach

# Apex hit-test — uji posisi pukulan pada PUNCAK ekstensi.
# Disetel agresif agar respons terasa instan: pukulan cepat berlangsung <100ms
# sehingga window & stagnant threshold harus sangat kecil.
APEX_WINDOW = 0.09         # detik; batas keras menunggu apex (~1-2 frame @25Hz)
APEX_DROP = 0.08           # ekstensi turun sebanyak ini dari puncak → tangan menarik
APEX_EPS = 0.04            # kenaikan < ini dianggap sudah melandai
APEX_STAGNANT = 1          # 1 frame tanpa puncak baru → sudah di apex
# Pukulan dengan kecepatan sangat tinggi langsung diselesaikan di frame berikutnya.
FAST_PUNCH_MULTIPLIER = 2.5  # outward_speed >= speed_min * ini → fast-path (stagnant=1)

# One-Euro filter (Casiez et al., 2012) — parameter untuk koordinat ternormalisasi.
# Disetel SANGAT RESPONSIF: filter harus transparan untuk gerakan cepat (jab <100ms).
ONE_EURO_MIN_CUTOFF = 2.5  # makin kecil = makin halus saat diam (tapi makin lag)
ONE_EURO_BETA = 2.0        # makin besar = makin responsif saat gerak cepat
ONE_EURO_DCUTOFF = 10.0    # cutoff turunan tinggi = deteksi arah sangat cepat

# --------------------------------------------------------------------------
# Indeks landmark MediaPipe Pose yang dipakai (tubuh bagian atas)
# Koordinat ternormalisasi 0..1, sumbu Y ke bawah.
# --------------------------------------------------------------------------
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16

HANDS = {
    "left": (LEFT_SHOULDER, LEFT_WRIST),
    "right": (RIGHT_SHOULDER, RIGHT_WRIST),
}
VISIBILITY_THRESHOLD = 0.5

# Zona target (pusat ternormalisasi, dalam ruang gambar yang ditampilkan/mirror)
ZONES = [
    {"id": "TL", "x": 0.30, "y": 0.35},
    {"id": "TR", "x": 0.70, "y": 0.35},
    {"id": "ML", "x": 0.25, "y": 0.55},
    {"id": "MR", "x": 0.75, "y": 0.55},
    {"id": "C",  "x": 0.50, "y": 0.45},
]

# Teks yang terlihat user (Bahasa Indonesia)
ALERT_PRESS_PLAY = "Tekan ▶ Play untuk mulai bertanding."
ALERT_NO_POSE = "Tubuh tidak terdeteksi — mundur agar bahu & tangan terlihat kamera."

# Titik ternormalisasi sederhana (hasil filter pergelangan).
_Pt = namedtuple("_Pt", ["x", "y"])


def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


# --------------------------------------------------------------------------
# One-Euro filter — peredam jitter adaptif (halus saat diam, lincah saat cepat)
# --------------------------------------------------------------------------
def _alpha(cutoff, dt):
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class _OneEuro:
    """Filter One-Euro untuk satu nilai skalar."""

    def __init__(self, min_cutoff, beta, d_cutoff):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x = None
        self._dx = 0.0

    def reset(self):
        self._x = None
        self._dx = 0.0

    def __call__(self, x, dt):
        if self._x is None:
            self._x = x
            return x
        dx = (x - self._x) / dt
        a_d = _alpha(self.d_cutoff, dt)
        self._dx = a_d * dx + (1.0 - a_d) * self._dx
        cutoff = self.min_cutoff + self.beta * abs(self._dx)
        a = _alpha(cutoff, dt)
        self._x = a * x + (1.0 - a) * self._x
        return self._x


class _WristFilter:
    """One-Euro untuk titik 2D pergelangan (x & y terpisah)."""

    def __init__(self):
        self.fx = _OneEuro(ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DCUTOFF)
        self.fy = _OneEuro(ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_DCUTOFF)

    def reset(self):
        self.fx.reset()
        self.fy.reset()

    def __call__(self, wrist, dt):
        return _Pt(self.fx(wrist.x, dt), self.fy(wrist.y, dt))


class PunchStats:
    """Statistik sesi latihan berjalan."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._start = time.monotonic()
        self.score = 0
        self.combo = 0
        self.best_combo = 0
        self.punches = 0          # total pukulan sah dilempar
        self.hits = 0             # pukulan yang kena target
        self._speeds = []         # m/s (estimasi) tiap pukulan
        self._reactions = []      # ms, hanya untuk hit

    @property
    def elapsed_sec(self):
        return int(time.monotonic() - self._start)

    @property
    def accuracy(self):
        return round(100 * self.hits / self.punches) if self.punches else 0

    @property
    def avg_speed(self):
        return round(sum(self._speeds) / len(self._speeds), 1) if self._speeds else 0.0

    @property
    def best_speed(self):
        return round(max(self._speeds), 1) if self._speeds else 0.0

    @property
    def last_reaction_ms(self):
        return self._reactions[-1] if self._reactions else 0

    @property
    def avg_reaction_ms(self):
        return round(sum(self._reactions) / len(self._reactions)) if self._reactions else 0

    def to_dict(self):
        return {
            "elapsed_sec": self.elapsed_sec,
            "score": self.score,
            "combo": self.combo,
            "best_combo": self.best_combo,
            "punches": self.punches,
            "hits": self.hits,
            "accuracy": self.accuracy,
            "avg_speed": self.avg_speed,
            "best_speed": self.best_speed,
            "last_reaction_ms": self.last_reaction_ms,
            "avg_reaction_ms": self.avg_reaction_ms,
        }


class PunchAnalyzer:
    """Menerima landmark pose tiap frame; mendeteksi pukulan sah, mengelola
    target & skor, lalu menghasilkan objek feedback untuk WebSocket.

    Tidak butuh kalibrasi manual: panggil start() (tombol Play) untuk mulai;
    jangkauan memakai DEFAULT_REACH lalu menyesuaikan diri (reach adaptif)."""

    def __init__(self):
        # Ambang per-instance (bisa diubah lewat /api/settings)
        self.speed_min = PUNCH_SPEED_MIN
        self.extend_frac = PUNCH_EXTEND_FRAC
        self.target_radius = TARGET_RADIUS

        self.stats = PunchStats()
        self.started_at = datetime.now(timezone.utc)
        self.playing = False

        self.active_target = None
        self._target_spawn = 0.0
        self._event_seq = 0
        self._last_event = self._no_event()
        self._last_time = time.monotonic()

        self._init_hand_state()

    # ------------------------------------------------------------------
    def _init_hand_state(self):
        """(Re)inisialisasi seluruh state per-tangan."""
        self._armed = {"left": True, "right": True}
        self._reach_est = {"left": DEFAULT_REACH, "right": DEFAULT_REACH}
        self._cycle_peak = {"left": 0.0, "right": 0.0}
        self._filt = {"left": _WristFilter(), "right": _WristFilter()}
        self._prev_wrist = {"left": None, "right": None}   # pergelangan ter-filter
        self._vel_buf = {"left": deque(maxlen=SPEED_SMOOTH),
                         "right": deque(maxlen=SPEED_SMOOTH)}
        self._pending = {"left": None, "right": None}      # pukulan menunggu apex

    @staticmethod
    def _no_event():
        return {"seq": 0, "type": "none", "hand": None,
                "combo": 0, "speed": 0.0, "reaction_ms": 0}

    def _reset_runtime(self):
        self.stats.reset()
        self.started_at = datetime.now(timezone.utc)
        self._last_time = time.monotonic()
        self.active_target = None
        self._event_seq = 0
        self._last_event = self._no_event()
        self._init_hand_state()

    def start(self):
        """Mulai bermain (tombol Play). Reset statistik & langsung munculkan
        target — tanpa kalibrasi. Selalu berhasil."""
        self._reset_runtime()
        self.playing = True
        self._spawn_target()
        return True

    def stop(self):
        """Hentikan permainan (tombol Stop). Tidak menyimpan apa pun."""
        self.playing = False
        self.active_target = None

    # ------------------------------------------------------------------
    def _visible(self, landmarks, idx_iterable):
        if landmarks is None:
            return False
        try:
            for i in idx_iterable:
                vis = getattr(landmarks[i], "visibility", 1.0)
                if vis is not None and vis < VISIBILITY_THRESHOLD:
                    return False
        except (IndexError, AttributeError, TypeError):
            return False
        return True

    def _spawn_target(self):
        choices = [z for z in ZONES if not self.active_target
                   or z["id"] != self.active_target["id"]]
        z = random.choice(choices)
        self.active_target = {"id": z["id"], "x": z["x"], "y": z["y"],
                              "r": self.target_radius}
        self._target_spawn = time.monotonic()

    def _register_event(self, etype, hand, speed_ms, reaction_ms):
        self._event_seq += 1
        self._last_event = {
            "seq": self._event_seq, "type": etype, "hand": hand,
            "combo": self.stats.combo, "speed": round(speed_ms, 1),
            "reaction_ms": reaction_ms,
        }

    # ------------------------------------------------------------------
    def analyze(self, landmarks, frame_time=None):
        """Analisis satu frame → objek feedback.

        frame_time: time.monotonic() saat frame di-capture kamera (dari camera.py).
        Jika diberikan, dt dihitung dari waktu frame asli → kecepatan lebih akurat.
        Jika None (self-test / kamera belum siap), pakai jam loop seperti sebelumnya.
        """
        now = frame_time if frame_time is not None else time.monotonic()
        dt = min(max(now - self._last_time, 0.01), 0.2)  # clamp; 0.01 min untuk 30fps+
        self._last_time = now

        empty_metrics = {"left": {"ext": None, "speed": None},
                         "right": {"ext": None, "speed": None}}

        # Belum/berhenti bermain → tampilkan ajakan tekan Play.
        if not self.playing:
            return self._feedback("idle", empty_metrics, [ALERT_PRESS_PLAY])

        # Bermain tapi tubuh tak terlihat.
        if not self._visible(landmarks, (LEFT_SHOULDER, RIGHT_SHOULDER)):
            self._drop_all_hands()
            return self._feedback("playing", empty_metrics, [ALERT_NO_POSE])

        shoulder_width = _dist(landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER])
        if shoulder_width < 1e-6:
            self._drop_all_hands()
            return self._feedback("playing", empty_metrics, [ALERT_NO_POSE])

        m_per_norm = ASSUMED_SHOULDER_M / shoulder_width
        metrics = {}
        resolved = []  # pukulan yang mencapai apex pada frame ini

        for hand in HANDS:
            sh_idx, wr_idx = HANDS[hand]
            if not self._visible(landmarks, (sh_idx, wr_idx)):
                metrics[hand] = {"ext": None, "speed": None}
                self._drop_hand(hand)
                continue

            shoulder = landmarks[sh_idx]
            wrist = self._filt[hand](landmarks[wr_idx], dt)   # ter-filter (One-Euro)
            ext_dist = _dist(wrist, shoulder)
            ext = ext_dist / shoulder_width

            # Kecepatan vektor pergelangan (dihaluskan ringan), dari titik ter-filter.
            prev = self._prev_wrist[hand]
            if prev is not None:
                self._vel_buf[hand].append(((wrist.x - prev.x) / dt,
                                            (wrist.y - prev.y) / dt))
            self._prev_wrist[hand] = wrist

            if self._vel_buf[hand]:
                vx = sum(v[0] for v in self._vel_buf[hand]) / len(self._vel_buf[hand])
                vy = sum(v[1] for v in self._vel_buf[hand]) / len(self._vel_buf[hand])
            else:
                vx = vy = 0.0
            speed_mag = math.hypot(vx, vy)

            # Komponen kecepatan KELUAR (menjauh dari bahu) → gating arah.
            if ext_dist > 1e-6:
                ox, oy = (wrist.x - shoulder.x) / ext_dist, (wrist.y - shoulder.y) / ext_dist
                outward_speed = vx * ox + vy * oy
            else:
                outward_speed = 0.0

            speed_ms = speed_mag * m_per_norm
            metrics[hand] = {"ext": round(ext, 2), "speed": round(speed_ms, 1)}

            self._cycle_peak[hand] = max(self._cycle_peak[hand], ext)
            reach = self._reach_est[hand]

            # 1) Pukulan menunggu apex → lacak puncak, lalu selesaikan.
            pend = self._pending[hand]
            if pend is not None:
                new_peak = ext > pend["best_ext"] + APEX_EPS
                if ext > pend["best_ext"]:
                    pend["best_ext"] = ext
                # Selama masih di sekitar puncak, segarkan posisi landing ke
                # titik ter-filter terbaru (terus menyusul ke fist yang menjulur).
                if ext >= pend["best_ext"] - APEX_DROP:
                    pend["best_wrist"] = wrist
                    pend["speed_ms"] = max(pend["speed_ms"], speed_ms)
                pend["stagnant"] = 0 if new_peak else pend["stagnant"] + 1
                at_apex = (pend["stagnant"] >= APEX_STAGNANT
                           or ext < pend["best_ext"] - APEX_DROP
                           or (now - pend["start_t"]) >= APEX_WINDOW)
                if at_apex:
                    resolved.append((hand, pend["best_wrist"], pend["speed_ms"]))
                    self._pending[hand] = None

            # 2) Isi ulang saat tangan ditarik + reach belajar dari siklus ini.
            if ext < REARM_FRAC * reach:
                if self._cycle_peak[hand] >= MIN_PEAK_FOR_ADAPT:
                    reach += REACH_ADAPT * (self._cycle_peak[hand] - reach)
                    self._reach_est[hand] = min(max(reach, MIN_REACH), MAX_REACH)
                self._cycle_peak[hand] = ext
                self._armed[hand] = True

            # 3) Picu pukulan: ter-armed, terjulur cukup, dan bergerak KELUAR cepat.
            if (self._armed[hand] and self._pending[hand] is None
                    and ext >= self.extend_frac * self._reach_est[hand]
                    and outward_speed >= self.speed_min):
                self._armed[hand] = False
                # Fast-path: pukulan sangat cepat → anggap sudah di apex (stagnant=1)
                # sehingga diselesaikan pada frame berikutnya tanpa menunggu APEX_WINDOW.
                init_stagnant = (1 if outward_speed >= self.speed_min * FAST_PUNCH_MULTIPLIER
                                 else 0)
                self._pending[hand] = {"start_t": now, "best_ext": ext,
                                       "best_wrist": wrist, "speed_ms": speed_ms,
                                       "stagnant": init_stagnant}

        if self.active_target is None:
            self._spawn_target()

        # Satu pukulan per frame: ambil yang tercepat bila dua tangan bersamaan.
        if resolved:
            resolved.sort(key=lambda r: r[2], reverse=True)
            self._resolve_punch(*resolved[0], now=now)

        return self._feedback("playing", metrics, [])

    # ------------------------------------------------------------------
    def _drop_hand(self, hand):
        """Tangan keluar frame: reset filter & kecepatan; selesaikan pending
        memakai puncak terakhir agar pukulan tak hilang."""
        self._filt[hand].reset()
        self._prev_wrist[hand] = None
        self._vel_buf[hand].clear()
        pend = self._pending[hand]
        if pend is not None:
            now = time.monotonic()
            self._pending[hand] = None
            self._resolve_punch(hand, pend["best_wrist"], pend["speed_ms"], now=now)

    def _drop_all_hands(self):
        for hand in HANDS:
            self._drop_hand(hand)

    def _resolve_punch(self, hand, wrist, speed_ms, now):
        """Hitung satu pukulan sah yang sudah mencapai apex: hit/miss, skor, kombo."""
        self.stats.punches += 1
        self.stats._speeds.append(speed_ms)
        tgt = self.active_target
        hit = tgt is not None and math.hypot(wrist.x - tgt["x"], wrist.y - tgt["y"]) <= tgt["r"]
        if hit:
            reaction_ms = int((now - self._target_spawn) * 1000)
            self.stats.combo += 1
            self.stats.best_combo = max(self.stats.best_combo, self.stats.combo)
            self.stats.score += SCORE_BASE * self.stats.combo
            self.stats.hits += 1
            self.stats._reactions.append(reaction_ms)
            self._register_event("hit", hand, speed_ms, reaction_ms)
            self._spawn_target()
        else:
            self.stats.combo = 0
            self._register_event("miss", hand, speed_ms, 0)

    # ------------------------------------------------------------------
    def _feedback(self, status, metrics, alerts):
        return {
            "type": "feedback",
            "status": status,
            "metrics": metrics,
            "target": self.active_target,
            "last_event": self._last_event,
            "alerts": alerts,
            "stats": self.stats.to_dict(),
        }


# ==========================================================================
# Self-test (`python analysis.py`) — tanpa kamera/MediaPipe.
# ==========================================================================
if __name__ == "__main__":
    Landmark = namedtuple("Landmark", ["x", "y", "visibility"])

    def make_pose(lw=(0.40, 0.45), rw=(0.60, 0.45),
                  ls=(0.40, 0.40), rs=(0.60, 0.40), vis=1.0):
        """Bangun 33 landmark; default tangan 'guard' (dekat bahu).
        shoulder_width = 0.20."""
        lm = [Landmark(0.5, 0.5, vis) for _ in range(33)]
        lm[LEFT_SHOULDER] = Landmark(ls[0], ls[1], vis)
        lm[RIGHT_SHOULDER] = Landmark(rs[0], rs[1], vis)
        lm[LEFT_WRIST] = Landmark(lw[0], lw[1], vis)
        lm[RIGHT_WRIST] = Landmark(rw[0], rw[1], vis)
        return lm

    def feed(an, poses):
        fb = None
        for p in poses:
            fb = an.analyze(p)
        return fb

    def jab_left(to_y, settle=4):
        """Rangkaian pose: guard → julur cepat tangan kiri ke (0.40, to_y) →
        tahan beberapa frame agar filter mencapai puncak (apex)."""
        poses = [make_pose(), make_pose()]                 # guard (baseline)
        y = 0.45
        while y < to_y - 1e-9:                              # julur cepat (~0.18/frame)
            y = min(to_y, y + 0.18)
            poses.append(make_pose(lw=(0.40, y)))
        poses += [make_pose(lw=(0.40, to_y)) for _ in range(settle)]  # tahan di apex
        return poses

    passed = failed = 0

    def check(name, cond):
        global passed, failed
        if cond:
            passed += 1; print(f"  [OK]   {name}")
        else:
            failed += 1; print(f"  [GAGAL] {name}")

    print("== Self-test PunchAnalyzer ==")

    guard = make_pose()  # ext = 0.05/0.2 = 0.25

    # 1. Sebelum Play → idle, tanpa target
    an = PunchAnalyzer()
    fb = an.analyze(guard)
    check("Sebelum Play -> status idle", fb["status"] == "idle")
    check("Sebelum Play -> tidak ada target", fb["target"] is None)

    # 2. Play langsung mulai (tanpa kalibrasi) + target muncul
    check("start() berhasil", an.start() is True)
    fb = an.analyze(guard)
    check("Sesudah Play -> status playing", fb["status"] == "playing")
    check("Sesudah Play -> target muncul", fb["target"] is not None)

    # 3. Pukulan sah + kena target -> HIT (diuji pada apex ekstensi)
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.40, "y": 0.90, "r": 0.20}
    fb = feed(an, jab_left(0.90))
    check("Pukulan sah ke target -> hit", fb["last_event"]["type"] == "hit")
    check("Hit -> skor bertambah", fb["stats"]["score"] >= SCORE_BASE)
    check("Hit -> hits == 1", fb["stats"]["hits"] == 1)
    check("Hit -> kombo == 1", fb["stats"]["combo"] == 1)
    check("Hit -> punches == 1", fb["stats"]["punches"] == 1)

    # 4. Tetap terjulur (tanpa menarik tangan) tidak menghitung pukulan kedua
    fb = feed(an, [make_pose(lw=(0.40, 0.90)) for _ in range(6)])
    check("Tetap terjulur -> tidak double-count", fb["stats"]["punches"] == 1)

    # 5. Pukulan pelan tidak dihitung (kecepatan keluar < ambang)
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.40, "y": 0.90, "r": 0.20}
    poses = [make_pose()]
    y = 0.45
    for _ in range(25):
        y += 0.02
        poses.append(make_pose(lw=(0.40, y)))
    fb = feed(an, poses)
    check("Pukulan pelan -> tidak terhitung", fb["stats"]["punches"] == 0)

    # 6. Pukulan cepat TAPI meleset target -> miss, kombo putus
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.05, "y": 0.05, "r": 0.10}
    fb = feed(an, jab_left(0.90))
    check("Pukulan meleset -> miss", fb["last_event"]["type"] == "miss")
    check("Miss -> hits tetap 0", fb["stats"]["hits"] == 0)
    check("Miss -> kombo 0", fb["stats"]["combo"] == 0)
    check("Miss -> tetap dihitung pukulan", fb["stats"]["punches"] == 1)

    # 7. Gating arah: menarik tangan cepat (ke dalam) tidak terhitung pukulan
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.40, "y": 0.90, "r": 0.20}
    feed(an, [make_pose(lw=(0.40, 0.90)) for _ in range(4)])  # mulai terjulur (diam)
    base = an.stats.punches
    pull = []
    y = 0.90
    while y > 0.46:
        y -= 0.18
        pull.append(make_pose(lw=(0.40, max(0.45, y))))
    fb = feed(an, pull)
    check("Tarik tangan cepat -> bukan pukulan", fb["stats"]["punches"] == base)

    # 8. Stop -> berhenti, tanpa target, kembali idle
    an = PunchAnalyzer(); an.start(); an.stop()
    fb = an.analyze(guard)
    check("Sesudah Stop -> status idle", fb["status"] == "idle")
    check("Sesudah Stop -> tidak ada target", fb["target"] is None)

    # 9. Kasus tepi: tubuh tak terdeteksi saat playing -> tanpa crash
    an = PunchAnalyzer(); an.start()
    fb = an.analyze(None)
    check("Pose None saat playing -> tanpa crash", fb["status"] == "playing")

    # 10. Reach adaptif: pemain berjangkauan pendek tetap bisa memicu pukulan
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.40, "y": 0.62, "r": 0.20}
    # ekstensi puncak hanya ~1.1 (di bawah ambang awal 0.7*1.5=1.05 nyaris) — ulang
    # beberapa siklus agar reach menyesuaikan, lalu pukulan pendek terhitung.
    short = []
    for _ in range(4):
        short += jab_left(0.62, settle=4)
        short += [make_pose() for _ in range(4)]   # tarik → reach belajar
    fb = feed(an, short)
    check("Reach adaptif -> pukulan pendek akhirnya terhitung", fb["stats"]["punches"] >= 1)

    # 11. Bentuk stats dict
    keys = {"elapsed_sec", "score", "combo", "best_combo", "punches", "hits",
            "accuracy", "avg_speed", "best_speed", "last_reaction_ms",
            "avg_reaction_ms"}
    check("stats.to_dict() berkunci sesuai kontrak", set(an.stats.to_dict()) == keys)

    print(f"\nHasil: {passed} lulus, {failed} gagal")
    raise SystemExit(1 if failed else 0)
