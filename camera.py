"""
camera.py — Akuisisi kamera + MediaPipe Pose untuk Study Guardian.

Kelas Camera menjalankan loop di thread latar: baca frame (OpenCV) → deteksi
pose (MediaPipe, CPU) → gambar skeleton → simpan JPEG terbaru + landmark
terbaru. app.py mengambil keduanya lewat get_jpeg() dan get_landmarks().

Catatan desain (CLAUDE.md §2): modul ini HANYA mengurus visi (frame +
landmark + skeleton). Seluruh keputusan postur ada di analysis.py.

Privasi (CLAUDE.md §10): frame TIDAK pernah ditulis ke disk atau dikirim ke
luar; hanya disediakan sebagai MJPEG ke jaringan lokal oleh Flask.
"""

import threading
import time

import cv2
import mediapipe as mp

mp_pose = mp.solutions.pose
mp_draw = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles


class Camera:
    def __init__(self, index=0, width=640, height=480):
        self.index = index
        self.width = width
        self.height = height

        self.cap = None
        # model_complexity=0 -> model "lite", paling ringan untuk Jetson CPU.
        self.pose = mp_pose.Pose(
            model_complexity=0,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

        self._lock = threading.Lock()
        self._jpeg = None        # bytes JPEG frame terbaru (sudah ber-skeleton)
        self._landmarks = None   # list landmark terbaru, atau None
        self._running = False
        self._thread = None

    # ------------------------------------------------------------------
    def start(self):
        if self._running:
            return
        self.cap = cv2.VideoCapture(self.index)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Kamera index {self.index} tidak bisa dibuka. "
                "Periksa koneksi webcam (v4l2-ctl --list-devices di Jetson)."
            )
        self._running = True
        self._thread = threading.Thread(target=self._update, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        if self.cap is not None:
            self.cap.release()
        self.pose.close()

    # ------------------------------------------------------------------
    def _update(self):
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                continue

            # Cermin (mirror) agar gerakan terasa natural seperti melihat cermin.
            # Fitur analisis simetris, jadi pencerminan tidak mengubah hasil.
            frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            rgb.flags.writeable = False
            results = self.pose.process(rgb)

            landmarks = None
            if results.pose_landmarks:
                landmarks = results.pose_landmarks.landmark
                mp_draw.draw_landmarks(
                    frame,
                    results.pose_landmarks,
                    mp_pose.POSE_CONNECTIONS,
                    landmark_drawing_spec=mp_styles.get_default_pose_landmarks_style(),
                )

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                continue

            with self._lock:
                self._jpeg = buf.tobytes()
                self._landmarks = landmarks

    # ------------------------------------------------------------------
    def get_jpeg(self):
        with self._lock:
            return self._jpeg

    def get_landmarks(self):
        with self._lock:
            return self._landmarks

    def mjpeg_frames(self):
        """Generator untuk endpoint /video_feed (multipart MJPEG)."""
        boundary = b"--frame"
        while True:
            jpeg = self.get_jpeg()
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield (boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            time.sleep(1 / 30)  # batasi ~30 fps streaming, hemat CPU
