# Study Guardian

Perangkat **edge AI pemantau postur belajar**. Berjalan di NVIDIA Jetson Orin
Nano dengan kamera menghadap meja. MediaPipe + seluruh logika analisis berjalan
**di perangkat (Python)** — video tidak pernah keluar ke cloud. User memantau
lewat halaman web sederhana yang disajikan langsung oleh Flask.

Tiga deteksi inti: **membungkuk**, **wajah terlalu dekat ke layar**, **badan
miring**. Plus pengingat istirahat **20-20-20** dan **skor postur** per sesi.

Dokumen perencanaan lengkap: [`PRD_Study_Guardian.md`](PRD_Study_Guardian.md).
Panduan konteks coding: [`CLAUDE.md`](CLAUDE.md).

---

## Arsitektur (monolitik)

Satu proses Flask menangani semuanya — tidak ada server frontend terpisah,
tidak ada Node/npm, tidak ada langkah build.

```
Kamera ─► OpenCV ─► MediaPipe Pose (Python) ─► PostureAnalyzer ─► Flask
                                                                  ├─ index.html (HTML/JS)
                                                                  ├─ /video_feed (MJPEG + skeleton)
                                                                  ├─ /ws (WebSocket: feedback)
                                                                  ├─ /api/... (REST)
                                                                  └─ PostgreSQL (riwayat sesi)
```

Deteksi pose & seluruh keputusan terjadi **di Python**, bukan di browser.
Browser hanya menampilkan `<img src="/video_feed">` + update via WebSocket.

## Struktur berkas

| Berkas | Peran |
|--------|-------|
| `analysis.py` | `PostureAnalyzer` — kalibrasi, deteksi, smoothing, skor, timer 20-20-20. Punya self-test. |
| `camera.py` | Akuisisi kamera + MediaPipe **Pose Landmarker (Tasks API)**, gambar skeleton, sediakan frame & landmark. |
| `app.py` | Entrypoint Flask: `/`, `/video_feed`, `/ws`, `/api/*`, loop analisis. |
| `db.py` | Koneksi PostgreSQL: riwayat sesi + pengaturan ambang (tahan-gagal). |
| `schema.sql` | DDL tabel `sessions` & `settings`. |
| `models/pose_landmarker_lite.task` | Model MediaPipe Pose (lite, ~5,5 MB). Disertakan agar jalan offline. |
| `templates/index.html`, `static/app.js`, `static/style.css` | UI (live view, status, statistik, riwayat). |

---

## Instalasi

```bash
# 1. Dependensi Python (di Jetson; OpenCV mungkin sudah dari JetPack — jangan timpa)
pip install -r requirements.txt

# 2. Database
sudo apt install postgresql
sudo -u postgres createdb study_guardian
psql -U postgres -d study_guardian -f schema.sql
```

Konfigurasi koneksi DB lewat environment variable (punya default lokal):
`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`. Kamera lewat
`CAMERA_INDEX` (default `0`).

## Menjalankan

```bash
# Mode daya maksimal Jetson
sudo nvpmodel -m 0 && sudo jetson_clocks

# Jalankan server
python app.py
# Buka http://<IP_JETSON>:5000 dari browser (Jetson atau perangkat se-jaringan)
```

Aplikasi tetap berjalan walau PostgreSQL belum tersedia (riwayat tidak
tersimpan) sehingga mudah didemokan.

## Uji logika analisis tanpa kamera

```bash
python analysis.py     # menjalankan 17 self-test PostureAnalyzer
```

---

## Cara pakai

1. Buka halaman, tunggu live view + status muncul.
2. **Duduk tegak** senyaman mungkin, tekan **Kalibrasi** (menetapkan baseline).
3. Pantau status: hijau "Postur Baik" / kuning "Perlu Diperbaiki" + peringatan.
4. Tekan **Akhiri Sesi** untuk menyimpan skor & statistik ke riwayat.

Ambang (relatif terhadap baseline kalibrasi), lihat `analysis.py` / CLAUDE.md §6:

| Parameter | Nilai | Arti |
|-----------|-------|------|
| `SLOUCH_RATIO` | 0.82 | membungkuk bila `head_ratio` < 82% baseline |
| `TOO_CLOSE_RATIO` | 1.22 | terlalu dekat bila `eye_width` > 122% baseline |
| `TILT_DEGREES` | 9.0 | miring bila `tilt_deg` > 9° |
| `SMOOTH_WINDOW` | 8 | moving average antar-frame |
| `BREAK_INTERVAL_SEC` | 1200 | pengingat istirahat tiap 20 menit (kecilkan saat demo) |

---

## Catatan environment (Jetson)

MediaPipe dijalankan di **CPU** untuk MVP — akselerasi GPU di Orin Nano rumit
dan bukan target (CLAUDE.md §9 / PRD §18). Resolusi ~640×480, model Pose *lite*
(`model_complexity=0`).

Kombinasi versi sangat menentukan keberhasilan instalasi MediaPipe.
Catat versi yang berhasil di sini:

**Dev (macOS Intel, x86_64) — TERVERIFIKASI:**

| Komponen | Versi yang berhasil |
|----------|---------------------|
| Python | 3.10.20 |
| mediapipe | 0.10.14 |
| opencv-contrib-python | 4.9.0.80 |
| numpy | 1.26.4 (`<2`) |
| flask | 3.1.3 |

> Catatan pin (lihat komentar di `requirements.txt`): `mediapipe` di-pin agar pip
> tidak *backtracking*; `opencv-contrib-python` di-pin ke 4.9.0.80 karena versi
> terbaru memaksa `numpy>=2` yang bentrok dengan mediapipe 0.10.14 (butuh numpy 1).

**Jetson (aarch64) — isi setelah teruji di perangkat:**

| Komponen | Versi yang berhasil |
|----------|---------------------|
| JetPack / L4T | _isi setelah teruji_ |
| Python | _isi setelah teruji_ |
| mediapipe | _isi setelah teruji_ |
| opencv (JetPack) | _isi setelah teruji_ |

Jika `pip install mediapipe` gagal untuk kombinasi JetPack/Python kalian, pakai
wheel aarch64 komunitas atau build dari source (lihat PRD §19).

---

## Privasi

Frame video **tidak pernah** ditulis ke disk atau dikirim ke jaringan luar.
MJPEG hanya disajikan ke jaringan lokal untuk ditampilkan di UI.
