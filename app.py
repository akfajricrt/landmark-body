"""
app.py — Entrypoint Flask Study Guardian (arsitektur monolitik, CLAUDE.md §2).

Satu proses menangani semuanya:
  GET  /              -> index.html (UI HTML/JS)
  GET  /video_feed    -> MJPEG (frame + skeleton)
  WS   /ws            -> dorong feedback tiap analisis (kontrak §5)
  POST /api/calibrate -> set baseline dari frame saat ini
  POST /api/session/end -> tutup sesi & simpan ke PostgreSQL
  GET  /api/history   -> daftar sesi terakhir
  GET/PUT /api/settings -> baca/ubah ambang (F11, opsional)

Loop analisis berjalan di thread sendiri (~10 Hz): mengambil landmark dari
camera.py, memanggil PostureAnalyzer.analyze(), menyimpan feedback terbaru
yang lalu didorong ke semua klien WebSocket.
"""

import json
import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, render_template, request
from flask_sock import Sock

import db
from analysis import PostureAnalyzer

app = Flask(__name__)
sock = Sock(app)

# ----------------------------------------------------------------------
# State global (satu pengguna lokal — lihat PRD §3 "Bukan Tujuan").
# ----------------------------------------------------------------------
analyzer = PostureAnalyzer()
camera = None  # diinisialisasi di main (impor kamera ditunda agar app bisa diuji)
ANALYZE_HZ = 10

_feedback_lock = threading.Lock()
_latest_feedback = {
    "type": "feedback",
    "status": "need_calibration",
    "metrics": None,
    "flags": {"slouching": False, "too_close": False, "tilted": False,
              "break_due": False},
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
    """Thread: analisis landmark terbaru pada laju tetap."""
    period = 1.0 / ANALYZE_HZ
    while True:
        landmarks = camera.get_landmarks() if camera else None
        fb = analyzer.analyze(landmarks)
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
    except Exception:  # noqa: BLE001 — klien putus koneksi; akhiri loop dengan tenang
        return


# ----------------------------------------------------------------------
# REST API (kontrak §5)
# ----------------------------------------------------------------------
@app.route("/api/calibrate", methods=["POST"])
def api_calibrate():
    landmarks = camera.get_landmarks() if camera else None
    baseline = analyzer.calibrate(landmarks)
    if baseline is None:
        return jsonify({
            "error": "Pose tidak terdeteksi. Pastikan wajah & bahu terlihat, "
                     "lalu coba lagi."
        }), 400
    return jsonify({"baseline": baseline})


@app.route("/api/session/end", methods=["POST"])
def api_session_end():
    stats = analyzer.stats.to_dict()
    started_at = analyzer.started_at
    ended_at = datetime.now(timezone.utc)
    session_id = db.save_session(started_at, ended_at, stats)
    # Mulai sesi baru (baseline kalibrasi dipertahankan).
    analyzer.reset()
    return jsonify({
        "saved": session_id is not None,
        "session_id": session_id,
        "summary": stats,
    })


@app.route("/api/history")
def api_history():
    return jsonify(db.get_history(limit=20))


def _settings_dict():
    """Pengaturan saat ini dalam bentuk dict berkunci-DB (close_ratio, bukan
    too_close_ratio) — dipakai untuk respons API & penyimpanan ke PostgreSQL."""
    return {
        "slouch_ratio": analyzer.slouch_ratio,
        "close_ratio": analyzer.too_close_ratio,   # pemetaan nama §7
        "tilt_degrees": analyzer.tilt_degrees,
        "break_interval": analyzer.break_interval,
    }


def _apply_settings(d):
    """Terapkan dict berkunci-DB ke analyzer (abaikan kunci yang None/absen)."""
    if not d:
        return
    if d.get("slouch_ratio") is not None:
        analyzer.slouch_ratio = float(d["slouch_ratio"])
    if d.get("close_ratio") is not None:
        analyzer.too_close_ratio = float(d["close_ratio"])
    if d.get("tilt_degrees") is not None:
        analyzer.tilt_degrees = float(d["tilt_degrees"])
    if d.get("break_interval") is not None:
        analyzer.break_interval = int(d["break_interval"])


@app.route("/api/settings", methods=["GET", "PUT"])
def api_settings():
    if request.method == "GET":
        return jsonify(_settings_dict())
    # PUT — terapkan ambang yang dikirim, lalu simpan ke PostgreSQL.
    _apply_settings(request.get_json(silent=True) or {})
    saved = db.save_settings(_settings_dict())
    return jsonify({**_settings_dict(), "saved": saved})


# ----------------------------------------------------------------------
def main():
    global camera
    from camera import Camera  # impor ditunda: butuh OpenCV/MediaPipe

    cam_index = int(os.environ.get("CAMERA_INDEX", "0"))
    camera = Camera(index=cam_index)
    camera.start()

    threading.Thread(target=_analysis_loop, daemon=True).start()

    if db.is_available():
        print("[app] PostgreSQL terhubung — riwayat sesi akan disimpan.")
        # Muat ambang tersimpan (F11) bila ada, agar persisten antar-restart.
        saved = db.get_settings()
        if saved:
            _apply_settings(saved)
            print(f"[app] Pengaturan ambang dimuat dari DB: {saved}")
    else:
        print("[app] PostgreSQL TIDAK tersedia — aplikasi tetap jalan, "
              "riwayat & pengaturan tidak tersimpan.")

    # threaded=True agar /video_feed, /ws, dan /api/* bisa dilayani bersamaan.
    app.run(host="0.0.0.0", port=5000, threaded=True)


if __name__ == "__main__":
    main()
