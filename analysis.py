"""
analysis.py — Inti logika game latihan tinju Study Guardian (Punch Trainer).

Modul ini MURNI Python (tanpa OpenCV / MediaPipe) supaya bisa diuji tanpa
kamera (lihat blok __main__ di bawah). Seluruh keputusan game — apakah sebuah
gerakan dianggap pukulan sah, apakah mengenai target, skor & kombo — terjadi di
sini, BUKAN di browser.

Mode: "Target Reaksi" — sebuah target menyala di salah satu zona; pemain harus
"meninju" ke zona itu. Pukulan hanya dihitung bila: (1) cukup CEPAT,
(2) lengan TER-EKSTENSI cukup (relatif jangkauan default), dan (3) mendarat di
zona target yang aktif.

Tanpa kalibrasi manual: tekan Play → langsung main. Jangkauan memakai nilai
default universal (dinormalisasi lebar bahu, jadi adil untuk semua ukuran badan).
"""

import math
import random
import time
from collections import deque
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Ambang & konstanta game (boleh diubah lewat /api/settings)
# --------------------------------------------------------------------------
PUNCH_SPEED_MIN = 1.5      # kecepatan pergelangan minimal (unit-layar/detik)
PUNCH_EXTEND_FRAC = 0.70   # pukulan sah bila ekstensi >= 70% jangkauan default
REARM_FRAC = 0.55          # harus menarik tangan < 55% jangkauan untuk "isi ulang"
SPEED_SMOOTH = 3           # smoothing ringan untuk kecepatan (jangan terlalu besar)
DEFAULT_REACH = 1.5        # jangkauan default (extension penuh ≈ 1,5× lebar bahu)
TARGET_RADIUS = 0.18       # radius zona target (koordinat ternormalisasi)
SCORE_BASE = 100           # poin dasar per hit (dikali kombo)
ASSUMED_SHOULDER_M = 0.40  # asumsi lebar bahu (m) untuk estimasi kecepatan m/s

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


def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


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
    jangkauan memakai DEFAULT_REACH yang dinormalisasi lebar bahu."""

    def __init__(self):
        # Ambang per-instance (bisa diubah lewat /api/settings)
        self.speed_min = PUNCH_SPEED_MIN
        self.extend_frac = PUNCH_EXTEND_FRAC
        self.target_radius = TARGET_RADIUS

        self.full_reach = {"left": DEFAULT_REACH, "right": DEFAULT_REACH}
        self.stats = PunchStats()
        self.started_at = datetime.now(timezone.utc)
        self.playing = False

        self._armed = {"left": True, "right": True}
        self._prev_wrist = {"left": None, "right": None}
        self._speed_buf = {"left": deque(maxlen=SPEED_SMOOTH),
                           "right": deque(maxlen=SPEED_SMOOTH)}
        self._last_time = time.monotonic()

        self.active_target = None
        self._target_spawn = 0.0
        self._event_seq = 0
        self._last_event = self._no_event()

    # ------------------------------------------------------------------
    @staticmethod
    def _no_event():
        return {"seq": 0, "type": "none", "hand": None,
                "combo": 0, "speed": 0.0, "reaction_ms": 0}

    def _reset_runtime(self):
        self.stats.reset()
        self.started_at = datetime.now(timezone.utc)
        self._armed = {"left": True, "right": True}
        self._prev_wrist = {"left": None, "right": None}
        self._speed_buf = {"left": deque(maxlen=SPEED_SMOOTH),
                           "right": deque(maxlen=SPEED_SMOOTH)}
        self._last_time = time.monotonic()
        self.active_target = None
        self._event_seq = 0
        self._last_event = self._no_event()

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

    def _extension(self, landmarks, hand, shoulder_width):
        sh_idx, wr_idx = HANDS[hand]
        if not self._visible(landmarks, (sh_idx, wr_idx)):
            return None
        return _dist(landmarks[wr_idx], landmarks[sh_idx]) / shoulder_width, landmarks[wr_idx]

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
    def analyze(self, landmarks):
        """Analisis satu frame → objek feedback."""
        now = time.monotonic()
        dt = min(max(now - self._last_time, 0.02), 0.2)  # clamp agar speed stabil
        self._last_time = now

        empty_metrics = {"left": {"ext": None, "speed": None},
                         "right": {"ext": None, "speed": None}}

        # Belum/berhenti bermain → tampilkan ajakan tekan Play.
        if not self.playing:
            return self._feedback("idle", empty_metrics, [ALERT_PRESS_PLAY])

        # Bermain tapi tubuh tak terlihat.
        if not self._visible(landmarks, (LEFT_SHOULDER, RIGHT_SHOULDER)):
            return self._feedback("playing", empty_metrics, [ALERT_NO_POSE])

        shoulder_width = _dist(landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER])
        if shoulder_width < 1e-6:
            return self._feedback("playing", empty_metrics, [ALERT_NO_POSE])

        m_per_norm = ASSUMED_SHOULDER_M / shoulder_width
        metrics = {}
        punch = None  # (hand, wrist, speed_ms) pukulan sah pada frame ini

        for hand in HANDS:
            res = self._extension(landmarks, hand, shoulder_width)
            if res is None:
                metrics[hand] = {"ext": None, "speed": None}
                self._prev_wrist[hand] = None
                continue
            ext, wrist = res

            prev = self._prev_wrist[hand]
            raw_speed = (_dist(wrist, prev) / dt) if prev is not None else 0.0
            self._prev_wrist[hand] = wrist
            self._speed_buf[hand].append(raw_speed)
            speed = sum(self._speed_buf[hand]) / len(self._speed_buf[hand])
            speed_ms = speed * m_per_norm

            metrics[hand] = {"ext": round(ext, 2), "speed": round(speed_ms, 1)}

            reach = self.full_reach[hand]
            if ext < REARM_FRAC * reach:          # isi ulang saat tangan ditarik
                self._armed[hand] = True

            if (self._armed[hand] and ext >= self.extend_frac * reach
                    and speed >= self.speed_min):
                self._armed[hand] = False
                if punch is None or speed_ms > punch[2]:
                    punch = (hand, wrist, speed_ms)

        if self.active_target is None:
            self._spawn_target()

        if punch is not None:
            hand, wrist, speed_ms = punch
            self.stats.punches += 1
            self.stats._speeds.append(speed_ms)
            tx, ty = self.active_target["x"], self.active_target["y"]
            hit = math.hypot(wrist.x - tx, wrist.y - ty) <= self.active_target["r"]
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

        return self._feedback("playing", metrics, [])

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
    from collections import namedtuple

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

    passed = failed = 0

    def check(name, cond):
        global passed, failed
        if cond:
            passed += 1; print(f"  [OK]   {name}")
        else:
            failed += 1; print(f"  [GAGAL] {name}")

    print("== Self-test PunchAnalyzer ==")

    extended = make_pose(lw=(0.40, 0.90), rw=(0.60, 0.90))  # ext = 0.5/0.2 = 2.5
    guard = make_pose()                                     # ext = 0.05/0.2 = 0.25

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

    # 3. Pukulan sah + kena target -> HIT
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.40, "y": 0.90, "r": 0.20}
    for _ in range(3):
        an.analyze(guard)
    fb = an.analyze(extended)
    check("Pukulan sah ke target -> hit", fb["last_event"]["type"] == "hit")
    check("Hit -> skor bertambah", fb["stats"]["score"] >= SCORE_BASE)
    check("Hit -> hits == 1", fb["stats"]["hits"] == 1)
    check("Hit -> kombo == 1", fb["stats"]["combo"] == 1)

    # 4. Rearm: tetap terjulur tidak menghitung pukulan kedua
    fb = an.analyze(extended)
    check("Tetap terjulur -> tidak double-count", fb["stats"]["punches"] == 1)

    # 5. Pukulan pelan tidak dihitung
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.40, "y": 0.90, "r": 0.20}
    an.analyze(guard)
    y = 0.45
    for _ in range(25):
        y += 0.02
        fb = an.analyze(make_pose(lw=(0.40, y), rw=(0.60, y)))
    check("Pukulan pelan -> tidak terhitung", fb["stats"]["punches"] == 0)

    # 6. Ekstensi kurang (setengah) walau cepat tidak dihitung
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.40, "y": 0.60, "r": 0.30}
    for _ in range(3):
        an.analyze(guard)
    half = make_pose(lw=(0.40, 0.60), rw=(0.60, 0.60))  # ext = 1.0 < 0.7*1.5 = 1.05
    fb = an.analyze(half)
    check("Ekstensi setengah -> tidak terhitung", fb["stats"]["punches"] == 0)

    # 7. Pukulan sah TAPI meleset target -> miss, kombo putus
    an = PunchAnalyzer(); an.start()
    an.active_target = {"id": "X", "x": 0.05, "y": 0.05, "r": 0.10}
    for _ in range(3):
        an.analyze(guard)
    fb = an.analyze(extended)
    check("Pukulan meleset -> miss", fb["last_event"]["type"] == "miss")
    check("Miss -> hits tetap 0", fb["stats"]["hits"] == 0)
    check("Miss -> kombo 0", fb["stats"]["combo"] == 0)

    # 8. Stop -> berhenti, tanpa target, kembali idle
    an = PunchAnalyzer(); an.start(); an.stop()
    fb = an.analyze(extended)
    check("Sesudah Stop -> status idle", fb["status"] == "idle")
    check("Sesudah Stop -> tidak ada target", fb["target"] is None)

    # 9. Kasus tepi: tubuh tak terdeteksi saat playing -> tanpa crash
    an = PunchAnalyzer(); an.start()
    fb = an.analyze(None)
    check("Pose None saat playing -> tanpa crash", fb["status"] == "playing")

    # 10. Bentuk stats dict
    keys = {"elapsed_sec", "score", "combo", "best_combo", "punches", "hits",
            "accuracy", "avg_speed", "best_speed", "last_reaction_ms",
            "avg_reaction_ms"}
    check("stats.to_dict() berkunci sesuai kontrak", set(an.stats.to_dict()) == keys)

    print(f"\nHasil: {passed} lulus, {failed} gagal")
    raise SystemExit(1 if failed else 0)
