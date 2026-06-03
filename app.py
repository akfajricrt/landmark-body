"""
app.py — Entrypoint Flask Study Guardian (Punch Trainer — game latihan tinju).

Arsitektur monolitik: satu proses menangani semuanya.
  GET  /              -> index.html (UI HTML/JS)
  GET  /video_feed    -> MJPEG (frame + skeleton)
  WS   /ws            -> dorong feedback game tiap analisis
  POST /api/play      -> mulai bermain
  POST /api/stop      -> berhenti bermain
  GET/PUT /api/settings -> baca/ubah ambang game (in-memory, tidak persisten)

Loop analisis berjalan di thread sendiri (~25 Hz): mengambil landmark dari
camera.py, memanggil PunchAnalyzer.analyze(), menyimpan feedback terbaru yang
lalu didorong ke semua klien WebSocket.
"""

import json
import os
import threading
import time

from flask import Flask, Response, jsonify, render_template, request
from flask_sock import Sock

from analysis import DIFFICULTY, PunchAnalyzer

app = Flask(__name__)
sock = Sock(app)

# ----------------------------------------------------------------------
# State global (satu pemain lokal).
# ----------------------------------------------------------------------
analyzer = PunchAnalyzer()
camera = None  # diinisialisasi di main (impor kamera ditunda)
ANALYZE_HZ = 25  # 25Hz: ~40ms/frame — pukulan cepat (<100ms) tertangkap 2-3× per gerakan

_feedback_lock = threading.Lock()
_latest_feedback = {
    "type": "feedback",
    "status": "idle",
    "metrics": {"left": {"ext": None, "speed": None},
                "right": {"ext": None, "speed": None}},
    "target": None,
    "last_event": {"seq": 0, "type": "none", "hand": None,
                   "combo": 0, "speed": 0.0, "reaction_ms": 0},
    "alerts": ["Menunggu kamera…"],
    "stats": analyzer.stats.to_dict(),
}


def _set_feedback(fb):
    global _latest_feedback
    with _feedback_lock:
        _latest_feedback = fb


def _get_feedback():
    with _feedback_lock:
        return _latest_feedback


def _analysis_loop():
    """Thread: analisis landmark terbaru pada laju tetap.

    Hanya analisis frame BARU (frame_time berubah). Frame duplikat dilewati
    agar kecepatan pergelangan tidak dihitung ulang dengan displacement = 0.
    """
    period = 1.0 / ANALYZE_HZ
    last_frame_time = None
    while True:
        if camera:
            landmarks, frame_time = camera.get_landmarks()
        else:
            landmarks, frame_time = None, None

        if frame_time is not None and frame_time == last_frame_time:
            # Frame sama seperti iterasi sebelumnya — skip, jangan analisis ulang.
            time.sleep(period)
            continue

        last_frame_time = frame_time
        fb = analyzer.analyze(landmarks, frame_time=frame_time)
        _set_feedback(fb)
        time.sleep(period)


# ----------------------------------------------------------------------
# Routes — UI & video
# ----------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    if camera is None:
        return "Kamera belum siap", 503
    return Response(
        camera.mjpeg_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ----------------------------------------------------------------------
# WebSocket — dorong feedback berkala
# ----------------------------------------------------------------------
@sock.route("/ws")
def ws(ws):
    try:
        while True:
            ws.send(json.dumps(_get_feedback()))
            time.sleep(1.0 / ANALYZE_HZ)
    except Exception:  # noqa: BLE001 — klien putus koneksi; akhiri dengan tenang
        return


# ----------------------------------------------------------------------
# REST API
# ----------------------------------------------------------------------
@app.route("/api/play", methods=["POST"])
def api_play():
    # Tombol Play: langsung mulai bermain (tanpa kalibrasi).
    analyzer.start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    # Tombol Stop: hentikan permainan.
    summary = analyzer.stats.to_dict()
    analyzer.stop()
    return jsonify({"ok": True, "summary": summary})


def _settings_dict():
    return {
        "speed_min": analyzer.speed_min,
        "extend_frac": analyzer.extend_frac,
        "target_radius": analyzer.target_radius,
        "difficulty": analyzer.difficulty,
        "levels": list(DIFFICULTY.keys()),   # untuk pilihan di UI
    }


def _apply_settings(d):
    """Terapkan dict pengaturan ke analyzer (abaikan kunci None/absen)."""
    if not d:
        return
    # Level diterapkan dulu: ia menyetel speed_min & ukuran target sesuai preset.
    if d.get("difficulty") is not None:
        analyzer.set_difficulty(d["difficulty"])
    if d.get("speed_min") is not None:
        analyzer.speed_min = float(d["speed_min"])
    if d.get("extend_frac") is not None:
        analyzer.extend_frac = float(d["extend_frac"])
    if d.get("target_radius") is not None:
        analyzer.target_radius = float(d["target_radius"])


@app.route("/api/settings", methods=["GET", "PUT"])
def api_settings():
    if request.method == "GET":
        return jsonify(_settings_dict())
    _apply_settings(request.get_json(silent=True) or {})
    return jsonify({**_settings_dict(), "saved": True})


# ----------------------------------------------------------------------
def main():
    global camera
    from camera import Camera  # impor ditunda: butuh OpenCV/MediaPipe

    cam_index = int(os.environ.get("CAMERA_INDEX", "0"))
    camera = Camera(index=cam_index)
    camera.start()

    threading.Thread(target=_analysis_loop, daemon=True).start()

    # threaded=True agar /video_feed, /ws, dan /api/* dilayani bersamaan.
    app.run(host="0.0.0.0", port=5000, threaded=True)


if __name__ == "__main__":
    main()
