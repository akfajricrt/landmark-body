import os
import threading
import time

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_tasks
from mediapipe.tasks.python import vision
from mediapipe.framework.formats import landmark_pb2

# Hanya dipakai untuk menggambar skeleton (koneksi & gaya) — bukan deteksi.
mp_pose = mp.solutions.pose
mp_draw = mp.solutions.drawing_utils
mp_styles = mp.solutions.drawing_styles

DEFAULT_MODEL = os.path.join(os.path.dirname(__file__), "models",
                             "pose_landmarker_lite.task")


class Camera:
    def __init__(self, index=0, width=640, height=480, model_path=None):
        self.index = index
        self.width = width
        self.height = height
        self.model_path = model_path or os.environ.get("POSE_MODEL_PATH", DEFAULT_MODEL)

        if not os.path.exists(self.model_path):
            raise RuntimeError(
                f"Model tidak ditemukan: {self.model_path}\n"
                "Unduh model lite ke folder models/:\n"
                "  curl -sSL -o models/pose_landmarker_lite.task \\\n"
                "    https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
                "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task"
            )

        # PoseLandmarker (Tasks API), mode VIDEO, satu orang, model lite (CPU).
        options = vision.PoseLandmarkerOptions(
            base_options=mp_tasks.BaseOptions(model_asset_path=self.model_path),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)

        self.cap = None
        self._lock = threading.Lock()
        self._jpeg = None        # bytes JPEG frame terbaru (sudah ber-skeleton)
        self._landmarks = None   # list 33 landmark terbaru, atau None
        self._frame_time = None  # time.monotonic() saat frame di-capture kamera
        self._running = False
        self._thread = None

        # Timestamp monotonik untuk detect_for_video (wajib selalu menaik).
        self._t0 = time.monotonic()
        self._last_ts = -1

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
        self.landmarker.close()

    # ------------------------------------------------------------------
    def _next_timestamp_ms(self):
        ts = int((time.monotonic() - self._t0) * 1000)
        if ts <= self._last_ts:        # jamin selalu menaik (syarat Tasks VIDEO)
            ts = self._last_ts + 1
        self._last_ts = ts
        return ts

    def _draw_skeleton(self, frame, landmarks):
        # Tasks API tak menyediakan proto siap-gambar; bangun NormalizedLandmarkList
        # lalu pakai drawing_utils Solutions (koneksi & gaya tetap sama).
        proto = landmark_pb2.NormalizedLandmarkList()
        proto.landmark.extend([
            landmark_pb2.NormalizedLandmark(x=l.x, y=l.y, z=l.z) for l in landmarks
        ])
        mp_draw.draw_landmarks(
            frame, proto, mp_pose.POSE_CONNECTIONS,
            landmark_drawing_spec=mp_styles.get_default_pose_landmarks_style(),
        )

    def _update(self):
        while self._running:
            ok, frame = self.cap.read()
            if not ok:
                continue

            # Stempel waktu diambil tepat setelah frame berhasil dibaca dari kamera.
            # Dipakai analysis.py untuk dt yang akurat (bukan jam loop analisis).
            capture_time = time.monotonic()

            # Cermin (mirror) agar gerakan terasa natural seperti bercermin.
            # MediaPipe jalan di frame cermin ini, sehingga posisi tangan di video
            # cocok dengan posisi target yang ditampilkan.
            frame = cv2.flip(frame, 1)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            result = self.landmarker.detect_for_video(mp_image, self._next_timestamp_ms())

            landmarks = None
            if result.pose_landmarks:
                landmarks = result.pose_landmarks[0]  # satu orang
                self._draw_skeleton(frame, landmarks)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                continue

            with self._lock:
                self._jpeg = buf.tobytes()
                self._landmarks = landmarks
                self._frame_time = capture_time

    # ------------------------------------------------------------------
    def get_jpeg(self):
        with self._lock:
            return self._jpeg

    def get_landmarks(self):
        """Kembalikan (landmarks, frame_time) — frame_time adalah time.monotonic()
        saat frame di-capture. Keduanya None jika kamera belum siap."""
        with self._lock:
            return self._landmarks, self._frame_time

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
