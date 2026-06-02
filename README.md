# Study Guardian — Punch Trainer

Game **latihan tinju berbasis edge AI**. Berjalan di NVIDIA Jetson Orin Nano
(atau laptop untuk pengembangan) dengan kamera menghadap pemain. MediaPipe +
seluruh logika game berjalan **di perangkat (Python)** — video tidak pernah
keluar ke cloud. Pemain bermain lewat halaman web yang disajikan langsung oleh
Flask.

Mode utama: **Target Reaksi** — target (🥊) menyala di salah satu zona; pemain
harus meninju ke arahnya. Pukulan **hanya dihitung** bila **cepat**, **ter-ekstensi
penuh** (relatif jangkauan default), dan **mengenai zona target**. Sistem
menghitung **skor, kombo, akurasi, kecepatan (estimasi m/s), dan waktu reaksi**.

Dokumen perencanaan lengkap: [`PRD_Study_Guardian.md`](PRD_Study_Guardian.md).
Panduan konteks coding: [`CLAUDE.md`](CLAUDE.md). Cara pakai: [`PANDUAN.md`](PANDUAN.md).

---

## Arsitektur (monolitik)

Satu proses Flask menangani semuanya — tidak ada server frontend terpisah, tidak
ada Node/npm, tidak ada langkah build (frontend pakai pustaka vendor lokal).

```
Kamera ─► OpenCV ─► MediaPipe Pose Landmarker (Tasks) ─► PunchAnalyzer ─► Flask
                                                                          ├─ index.html (HTML/JS)
                                                                          ├─ /video_feed (MJPEG + skeleton)
                                                                          ├─ /ws (WebSocket: state game)
                                                                          ├─ /api/... (REST)
                                                                          └─ PostgreSQL (riwayat sesi)
```

Deteksi pose & seluruh keputusan game terjadi **di Python**, bukan di browser.
Browser menampilkan `<img src="/video_feed">` + overlay target + update via WebSocket.

## Struktur berkas

| Berkas | Peran |
|--------|-------|
| `analysis.py` | `PunchAnalyzer` — deteksi pukulan, target, skor/kombo, reaksi. Punya self-test. |
| `camera.py` | Akuisisi kamera + MediaPipe **Pose Landmarker (Tasks API)**, gambar skeleton, sediakan frame & landmark. |
| `app.py` | Entrypoint Flask: `/`, `/video_feed`, `/ws`, `/api/*`, loop analisis (15 Hz). |
| `db.py` | Koneksi PostgreSQL: riwayat sesi + pengaturan (tahan-gagal). |
| `schema.sql` | DDL tabel `sessions` & `settings`. |
| `templates/index.html`, `static/app.js`, `static/style.css` | UI arena (live view, overlay target, HUD, statistik, riwayat). |
| `static/vendor/` | Pustaka lokal: Alpine.js, Chart.js, Toastify, Day.js. |
| `models/pose_landmarker_lite.task` | Model MediaPipe Pose (lite, ~5,5 MB). Disertakan agar jalan offline. |

---

## Instalasi

```bash
# 1. venv Python 3.10 + dependensi (lihat PANDUAN.md untuk detail)
/usr/local/opt/python@3.10/bin/python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Database
createdb study_guardian
psql -d study_guardian -f schema.sql
```

Konfigurasi koneksi DB & kamera lewat `.env` (lihat `.env.example`):
`DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `CAMERA_INDEX`,
`POSE_MODEL_PATH` (opsional).

## Menjalankan

```bash
sudo nvpmodel -m 0 && sudo jetson_clocks   # Jetson: mode daya maksimal
python app.py                              # buka http://<IP>:5000
```

Aplikasi tetap berjalan walau PostgreSQL belum tersedia (riwayat tidak tersimpan).

## Uji logika game tanpa kamera

```bash
python analysis.py     # menjalankan self-test PunchAnalyzer (19/19)
```

---

## Cara main

1. Buka halaman (layar penuh), tunggu arena muncul.
2. Tekan **▶ Play** — **langsung mulai, tanpa kalibrasi**.
3. Target 🥊 menyala di salah satu zona → **tinju cepat ke arahnya** (gerakkan tangan
   sampai—di video—menutupi 🥊).
4. Poin hanya masuk bila pukulan **cepat + lengan cukup lurus + kena zona**.
   HIT → kombo naik (pengali skor) + catat kecepatan & reaksi; MISS → kombo putus.
5. Tekan **⏹ Stop** untuk berhenti. (Riwayat sengaja **tidak disimpan**.)

Ambang game (lihat `analysis.py` / CLAUDE.md §6), bisa diubah via `/api/settings`:

| Parameter | Nilai | Arti |
|-----------|-------|------|
| `PUNCH_SPEED_MIN` | 1.5 | kecepatan pergelangan minimal (unit-layar/detik) |
| `PUNCH_EXTEND_FRAC` | 0.70 | pukulan sah bila ekstensi ≥ 70% jangkauan default |
| `REARM_FRAC` | 0.55 | harus menarik tangan < 55% untuk "isi ulang" |
| `TARGET_RADIUS` | 0.18 | radius zona target (ternormalisasi) |
| `SCORE_BASE` | 100 | poin dasar per hit (dikali kombo) |

---

## Catatan environment

MediaPipe dijalankan di **CPU** (model *lite*, Tasks API). Pukulan cepat → jaga
fps tinggi (resolusi ~640×480, analisis ~15 Hz).

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
> terbaru memaksa `numpy>=2` yang bentrok dengan mediapipe 0.10.14.

**Jetson (aarch64) — isi setelah teruji di perangkat:**

| Komponen | Versi yang berhasil |
|----------|---------------------|
| JetPack / L4T | _isi setelah teruji_ |
| Python | _isi setelah teruji_ |
| mediapipe | _isi setelah teruji_ |
| opencv (JetPack) | _isi setelah teruji_ |

Jika `pip install mediapipe` gagal di aarch64, pakai wheel komunitas atau build
dari source (lihat PRD §19).

---

## Privasi

Frame video **tidak pernah** ditulis ke disk atau dikirim ke jaringan luar.
MJPEG hanya disajikan ke jaringan lokal untuk ditampilkan di UI.
