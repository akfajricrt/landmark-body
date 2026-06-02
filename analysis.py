"""
analysis.py — Inti logika analisis postur Study Guardian.

Modul ini MURNI Python (tanpa OpenCV / MediaPipe) supaya bisa diuji tanpa
kamera (lihat blok __main__ di bawah). Seluruh keputusan postur — apakah
membungkuk, terlalu dekat, miring, kapan istirahat, dan skor — terjadi di
sini, BUKAN di browser (lihat CLAUDE.md §2).

Sumber kebenaran rumus & ambang: CLAUDE.md §6 dan PRD §12.
Jangan mengubah rumus tanpa menyamakan kedua dokumen tersebut.
"""

import math
import time
from collections import deque
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Ambang & konstanta (HARUS sama dengan CLAUDE.md §6 / PRD §12)
# --------------------------------------------------------------------------
SLOUCH_RATIO = 0.82        # membungkuk bila head_ratio < 82% baseline
TOO_CLOSE_RATIO = 1.22     # terlalu dekat bila eye_width > 122% baseline
TILT_DEGREES = 9.0         # miring bila tilt_deg > 9°
SMOOTH_WINDOW = 8          # moving average antar-frame
BREAK_INTERVAL_SEC = 1200  # 20 menit (kecilkan saat demo)

VISIBILITY_THRESHOLD = 0.5  # landmark dianggap valid bila visibility >= ini

# --------------------------------------------------------------------------
# Indeks landmark MediaPipe Pose yang dipakai (CLAUDE.md §6)
# Koordinat ternormalisasi 0..1, sumbu Y ke bawah.
# --------------------------------------------------------------------------
NOSE = 0
LEFT_EYE = 2
RIGHT_EYE = 5
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12

# Landmark yang wajib terlihat agar analisis valid
REQUIRED_LANDMARKS = (LEFT_EYE, RIGHT_EYE, LEFT_SHOULDER, RIGHT_SHOULDER)

# Teks peringatan yang terlihat user (Bahasa Indonesia, lihat CLAUDE.md §10)
ALERT_SLOUCH = "Punggung membungkuk — tegakkan badan."
ALERT_TOO_CLOSE = "Wajah terlalu dekat ke layar — mundur sedikit."
ALERT_TILTED = "Badan miring — luruskan bahu."
ALERT_BREAK = "Saatnya istirahat 20-20-20 — lihat objek jauh selama 20 detik."
ALERT_NO_POSE = "Pose tidak terdeteksi — pastikan tubuh bagian atas terlihat kamera."
ALERT_NEED_CALIB = "Silakan kalibrasi: duduk tegak lalu tekan Kalibrasi."


def _extract_features(landmarks):
    """Hitung tiga fitur turunan dari landmark. Mengembalikan
    (head_ratio, eye_width, tilt_deg) atau None bila tak bisa dihitung."""
    le, re = landmarks[LEFT_EYE], landmarks[RIGHT_EYE]
    ls, rs = landmarks[LEFT_SHOULDER], landmarks[RIGHT_SHOULDER]

    shoulder_width = math.hypot(ls.x - rs.x, ls.y - rs.y)
    if shoulder_width < 1e-6:
        return None

    eye_mid_y = (le.y + re.y) / 2.0
    shoulder_mid_y = (ls.y + rs.y) / 2.0

    # a. Rasio tinggi kepala — dinormalisasi terhadap lebar bahu agar tidak
    #    terpengaruh jarak user ke kamera. Kecil = membungkuk.
    head_ratio = (shoulder_mid_y - eye_mid_y) / shoulder_width

    # b. Lebar antar-mata — SENGAJA tidak dinormalisasi. Besar = terlalu dekat.
    eye_width = math.hypot(le.x - re.x, le.y - re.y)

    # c. Kemiringan garis bahu terhadap horizontal via atan2. Besar = miring.
    tilt_deg = abs(math.degrees(math.atan2(rs.y - ls.y, rs.x - ls.x)))
    if tilt_deg > 90.0:
        tilt_deg = 180.0 - tilt_deg  # lipat ke rentang 0..90

    return head_ratio, eye_width, tilt_deg


class PostureStats:
    """Statistik sesi berjalan. Catatan pemetaan nama: di sini event
    'terlalu dekat' disimpan sebagai too_close_events, tetapi to_dict()
    mengeluarkannya sebagai 'close_events' sesuai kontrak §5/§7."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._start = time.monotonic()
        self.total_frames = 0
        self.good_frames = 0
        self.slouch_events = 0
        self.too_close_events = 0
        self.tilt_events = 0

    @property
    def elapsed_sec(self):
        return int(time.monotonic() - self._start)

    @property
    def posture_score(self):
        # Skor = persentase frame ber-postur baik. Default 100 saat belum ada data.
        if self.total_frames == 0:
            return 100
        return round(100 * self.good_frames / self.total_frames)

    def to_dict(self):
        return {
            "elapsed_sec": self.elapsed_sec,
            "posture_score": self.posture_score,
            "slouch_events": self.slouch_events,
            "close_events": self.too_close_events,  # pemetaan nama → §5/§7
            "tilt_events": self.tilt_events,
        }


class PostureAnalyzer:
    """Menerima landmark pose tiap frame, menghasilkan objek feedback sesuai
    kontrak WebSocket (CLAUDE.md §5). Menyimpan baseline kalibrasi, melakukan
    smoothing, menghitung event & skor, serta menjalankan timer 20-20-20."""

    def __init__(self):
        # Ambang per-instance agar bisa diubah lewat /api/settings (F11)
        self.slouch_ratio = SLOUCH_RATIO
        self.too_close_ratio = TOO_CLOSE_RATIO
        self.tilt_degrees = TILT_DEGREES
        self.break_interval = BREAK_INTERVAL_SEC

        self._hr = deque(maxlen=SMOOTH_WINDOW)
        self._ew = deque(maxlen=SMOOTH_WINDOW)
        self._td = deque(maxlen=SMOOTH_WINDOW)

        self.baseline = None  # {"head_ratio": .., "eye_width": ..}
        self.stats = PostureStats()
        self._prev_flags = {"slouching": False, "too_close": False, "tilted": False}
        self._last_break = time.monotonic()
        self.started_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    @property
    def calibrated(self):
        return self.baseline is not None

    def reset(self):
        """Mulai sesi baru. Baseline kalibrasi dipertahankan (tidak perlu
        kalibrasi ulang antar-sesi); hanya statistik & timer di-reset."""
        self.stats.reset()
        self._hr.clear()
        self._ew.clear()
        self._td.clear()
        self._prev_flags = {"slouching": False, "too_close": False, "tilted": False}
        self._last_break = time.monotonic()
        self.started_at = datetime.now(timezone.utc)

    # ------------------------------------------------------------------
    def _is_valid(self, landmarks):
        if landmarks is None:
            return False
        try:
            for i in REQUIRED_LANDMARKS:
                vis = getattr(landmarks[i], "visibility", 1.0)
                if vis is not None and vis < VISIBILITY_THRESHOLD:
                    return False
        except (IndexError, AttributeError, TypeError):
            return False
        return True

    def _smoothed(self):
        return (
            sum(self._hr) / len(self._hr),
            sum(self._ew) / len(self._ew),
            sum(self._td) / len(self._td),
        )

    def _count_events(self, slouching, too_close, tilted):
        # Event dihitung hanya pada transisi baik -> buruk (PRD §12).
        if slouching and not self._prev_flags["slouching"]:
            self.stats.slouch_events += 1
        if too_close and not self._prev_flags["too_close"]:
            self.stats.too_close_events += 1
        if tilted and not self._prev_flags["tilted"]:
            self.stats.tilt_events += 1
        self._prev_flags = {
            "slouching": slouching,
            "too_close": too_close,
            "tilted": tilted,
        }

    def _feedback(self, status, metrics, flags, alerts):
        return {
            "type": "feedback",
            "status": status,
            "metrics": metrics,
            "flags": flags,
            "alerts": alerts,
            "stats": self.stats.to_dict(),
        }

    # ------------------------------------------------------------------
    def calibrate(self, landmarks):
        """Tetapkan baseline dari frame saat ini. Mengembalikan dict baseline
        {"head_ratio", "eye_width"} atau None bila pose tak valid."""
        if not self._is_valid(landmarks):
            return None
        feats = _extract_features(landmarks)
        if feats is None:
            return None
        hr, ew, _ = feats
        self.baseline = {"head_ratio": round(hr, 4), "eye_width": round(ew, 4)}
        # Mulai bersih setelah kalibrasi agar smoothing & event tidak tercampur.
        self._hr.clear()
        self._ew.clear()
        self._td.clear()
        self._prev_flags = {"slouching": False, "too_close": False, "tilted": False}
        return self.baseline

    def analyze(self, landmarks):
        """Analisis satu frame → objek feedback sesuai kontrak §5."""
        # Timer 20-20-20 berjalan terlepas dari ada/tidaknya pose.
        now = time.monotonic()
        break_due = False
        if now - self._last_break >= self.break_interval:
            break_due = True
            self._last_break = now

        no_flags = {"slouching": False, "too_close": False, "tilted": False,
                    "break_due": break_due}
        break_alerts = [ALERT_BREAK] if break_due else []

        # Kasus tepi: pose tidak terdeteksi / sebagian tubuh keluar frame.
        if not self._is_valid(landmarks):
            return self._feedback("need_calibration", None, no_flags,
                                  [ALERT_NO_POSE] + break_alerts)

        feats = _extract_features(landmarks)
        if feats is None:
            return self._feedback("need_calibration", None, no_flags,
                                  [ALERT_NO_POSE] + break_alerts)

        hr, ew, td = feats
        self._hr.append(hr)
        self._ew.append(ew)
        self._td.append(td)
        shr, sew, std = self._smoothed()
        metrics = {
            "head_ratio": round(shr, 3),
            "eye_width": round(sew, 3),
            "tilt_deg": round(std, 1),
        }

        # Belum kalibrasi: tampilkan metrik untuk pratinjau, tapi belum menilai.
        if not self.calibrated:
            return self._feedback("need_calibration", metrics, no_flags,
                                  [ALERT_NEED_CALIB] + break_alerts)

        slouching = shr < self.slouch_ratio * self.baseline["head_ratio"]
        too_close = sew > self.too_close_ratio * self.baseline["eye_width"]
        tilted = std > self.tilt_degrees

        self._count_events(slouching, too_close, tilted)

        bad = slouching or too_close or tilted
        self.stats.total_frames += 1
        if not bad:
            self.stats.good_frames += 1

        alerts = []
        if slouching:
            alerts.append(ALERT_SLOUCH)
        if too_close:
            alerts.append(ALERT_TOO_CLOSE)
        if tilted:
            alerts.append(ALERT_TILTED)
        alerts += break_alerts

        flags = {"slouching": slouching, "too_close": too_close,
                 "tilted": tilted, "break_due": break_due}
        status = "warn" if bad else "good"
        return self._feedback(status, metrics, flags, alerts)


# ==========================================================================
# Self-test (CLAUDE.md §8: `python analysis.py`) — tanpa kamera/MediaPipe.
# ==========================================================================
if __name__ == "__main__":
    from collections import namedtuple

    # Landmark palsu untuk uji: cukup punya x, y, visibility.
    Landmark = namedtuple("Landmark", ["x", "y", "visibility"])

    def make_pose(eye_y=0.30, eye_xl=0.45, eye_xr=0.55,
                  sh_y=0.55, sh_xl=0.35, sh_xr=0.65,
                  sh_yl=None, sh_yr=None, vis=1.0):
        """Bangun list 33 landmark; hanya indeks yang dipakai yang berarti."""
        sh_yl = sh_y if sh_yl is None else sh_yl
        sh_yr = sh_y if sh_yr is None else sh_yr
        lm = [Landmark(0.5, 0.5, vis) for _ in range(33)]
        lm[LEFT_EYE] = Landmark(eye_xl, eye_y, vis)
        lm[RIGHT_EYE] = Landmark(eye_xr, eye_y, vis)
        lm[LEFT_SHOULDER] = Landmark(sh_xl, sh_yl, vis)
        lm[RIGHT_SHOULDER] = Landmark(sh_xr, sh_yr, vis)
        return lm

    def feed(an, pose, n=SMOOTH_WINDOW):
        """Isi jendela smoothing dengan pose yang sama, balikkan feedback akhir."""
        fb = None
        for _ in range(n):
            fb = an.analyze(pose)
        return fb

    passed = 0
    failed = 0

    def check(name, cond):
        global passed, failed
        if cond:
            passed += 1
            print(f"  [OK]   {name}")
        else:
            failed += 1
            print(f"  [GAGAL] {name}")

    print("== Self-test PostureAnalyzer ==")

    upright = make_pose()  # head_ratio=(0.55-0.30)/0.30 ≈ 0.833, eye_width=0.10

    # 1. Sebelum kalibrasi → need_calibration
    an = PostureAnalyzer()
    fb = an.analyze(upright)
    check("Belum kalibrasi -> status need_calibration",
          fb["status"] == "need_calibration")

    # 2. Kalibrasi mengembalikan baseline
    base = an.calibrate(upright)
    check("Kalibrasi mengembalikan baseline", base is not None and "head_ratio" in base)
    check("Sesudah kalibrasi -> calibrated True", an.calibrated)

    # 3. Postur tegak -> good, tanpa flag
    fb = feed(an, upright)
    check("Postur tegak -> status good", fb["status"] == "good")
    check("Postur tegak -> tidak ada flag aktif",
          not any([fb["flags"]["slouching"], fb["flags"]["too_close"],
                   fb["flags"]["tilted"]]))

    # 4. Membungkuk: kepala turun mendekati bahu -> head_ratio jatuh
    an = PostureAnalyzer(); an.calibrate(upright)
    slouch = make_pose(eye_y=0.48)  # head_ratio=(0.55-0.48)/0.30 ≈ 0.233
    fb = feed(an, slouch)
    check("Membungkuk -> flag slouching", fb["flags"]["slouching"])
    check("Membungkuk -> status warn", fb["status"] == "warn")
    check("Membungkuk -> slouch_events terhitung", fb["stats"]["slouch_events"] >= 1)

    # 5. Terlalu dekat: mata melebar -> eye_width naik
    an = PostureAnalyzer(); an.calibrate(upright)
    close = make_pose(eye_xl=0.43, eye_xr=0.57)  # eye_width=0.14 > 1.22*0.10
    fb = feed(an, close)
    check("Terlalu dekat -> flag too_close", fb["flags"]["too_close"])
    check("Terlalu dekat -> close_events terhitung (pemetaan nama)",
          fb["stats"]["close_events"] >= 1)

    # 6. Miring: bahu tidak rata -> tilt_deg naik
    an = PostureAnalyzer(); an.calibrate(upright)
    tilt = make_pose(sh_yl=0.50, sh_yr=0.60)  # atan2(0.10,0.30) ≈ 18.4° > 9°
    fb = feed(an, tilt)
    check("Miring -> flag tilted", fb["flags"]["tilted"])
    check("Miring -> tilt_events terhitung", fb["stats"]["tilt_events"] >= 1)

    # 7. Kasus tepi: tidak ada pose -> need_calibration, tidak crash
    an = PostureAnalyzer(); an.calibrate(upright)
    fb = an.analyze(None)
    check("Pose None -> need_calibration tanpa crash",
          fb["status"] == "need_calibration")

    # 8. Kasus tepi: landmark visibility rendah -> dianggap tak valid
    low = make_pose(vis=0.1)
    fb = an.analyze(low)
    check("Visibility rendah -> need_calibration",
          fb["status"] == "need_calibration")

    # 9. Timer istirahat: interval sangat kecil -> break_due menyala sekali
    an = PostureAnalyzer(); an.calibrate(upright)
    an.break_interval = 0  # paksa jatuh tempo segera
    fb = an.analyze(upright)
    check("Interval 0 -> break_due True", fb["flags"]["break_due"])
    check("Break -> alert istirahat muncul", ALERT_BREAK in fb["alerts"])

    # 10. Skor postur: bentuk dict sesuai kontrak §5
    keys = {"elapsed_sec", "posture_score", "slouch_events",
            "close_events", "tilt_events"}
    check("stats.to_dict() punya kunci sesuai kontrak §5",
          set(an.stats.to_dict().keys()) == keys)

    print(f"\nHasil: {passed} lulus, {failed} gagal")
    raise SystemExit(1 if failed else 0)
