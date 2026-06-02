# CLAUDE.md — Study Guardian

Panduan konteks untuk asisten coding (Claude Code) saat mengembangkan proyek ini.
Dokumen perencanaan lengkap ada di **`PRD_Study_Guardian.md`** — jika ada
keraguan soal *kenapa* sebuah keputusan diambil, rujuk PRD. File ini berisi
*bagaimana* mengerjakannya secara konkret. Jaga keduanya tetap konsisten.

---

## 1. Apa ini

Study Guardian = perangkat edge AI pemantau postur belajar. Berjalan di **NVIDIA
Jetson Orin Nano** dengan kamera menghadap meja. MediaPipe + seluruh logika
analisis berjalan **di perangkat (Python)**; video tidak pernah keluar ke cloud.
User memantau lewat halaman web sederhana yang **disajikan oleh Flask itu sendiri**.

Tiga deteksi inti: **membungkuk**, **wajah terlalu dekat ke layar**, **badan miring**.
Plus pengingat istirahat **20-20-20** dan **skor postur** per sesi.

---

## 2. Arsitektur (monolitik — JANGAN dipisah)

Satu proses Flask menangani semuanya. Tidak ada server frontend terpisah, tidak
ada Node/npm, tidak ada langkah build.

```
Kamera ──► OpenCV ──► MediaPipe Pose (Python) ──► PostureAnalyzer ──► Flask
                                                                       ├─ menyajikan index.html (HTML/JS)
                                                                       ├─ /video_feed  (MJPEG, frame + skeleton)
                                                                       ├─ /ws          (WebSocket: feedback + statistik)
                                                                       ├─ /api/...     (REST: kalibrasi, riwayat, settings)
                                                                       └─ PostgreSQL   (riwayat sesi)
```

Aturan penting:
- Deteksi pose terjadi **di Python di Jetson**, BUKAN di browser.
- Browser hanya menampilkan: `<img src="/video_feed">` + update via WebSocket.
- Logika keputusan (apakah membungkuk, kapan ingatkan, skor) **hanya di Python**.

---

## 3. Tech stack

| Lapisan | Pilihan | Catatan |
|---------|---------|---------|
| Perangkat | Jetson Orin Nano (JetPack/L4T) | MediaPipe jalan di **CPU** untuk MVP (lihat §9) |
| Kamera + frame | OpenCV (`opencv-python`) | webcam USB diutamakan |
| Deteksi | `mediapipe` (Pose Landmarker, model **lite**) | indeks landmark di §6 |
| Server + UI | **Flask** + `flask-sock` | satu server menyajikan UI & API |
| Database | **PostgreSQL** (`psycopg2-binary`, atau SQLAlchemy) | skema di §7 |
| Frontend | **HTML + JavaScript polos** | folder `templates/` & `static/`, tanpa build |

Jangan menambah framework frontend (React/Vue/Nuxt), bundler, atau ORM berat
kecuali diminta eksplisit. Tujuan utama: simpel & cepat.

---

## 4. Struktur folder (target)

```
study-guardian/
├── CLAUDE.md
├── PRD_Study_Guardian.md
├── requirements.txt
├── README.md
├── app.py                # entrypoint Flask: route, /video_feed, /ws, /api/*
├── camera.py             # loop kamera + MediaPipe Pose; hasilkan frame + landmarks
├── analysis.py           # PostureAnalyzer (SUDAH ADA — jangan tulis ulang dari nol)
├── db.py                 # koneksi PostgreSQL + query sesi
├── schema.sql            # DDL tabel (lihat §7)
├── templates/
│   └── index.html        # halaman utama (live view + status + riwayat)
└── static/
    ├── app.js            # logika UI: WebSocket, kalibrasi, render statistik
    └── style.css         # tema terang lembut/hangat (lihat PRD §13)
```

---

## 5. Kontrak API (frontend & backend WAJIB ikut ini)

Sumber kebenaran. Kalau mengubah salah satu sisi, ubah dua-duanya + perbarui file ini.

- `GET /` → render `index.html`.
- `GET /video_feed` → MJPEG `multipart/x-mixed-replace`, frame sudah digambari skeleton.
- `WS /ws` → server mendorong objek feedback tiap analisis:
  ```json
  {
    "type": "feedback",
    "status": "good | warn | need_calibration",
    "metrics": { "head_ratio": 0.95, "eye_width": 0.10, "tilt_deg": 3.2 },
    "flags": { "slouching": false, "too_close": true, "tilted": false, "break_due": false },
    "alerts": ["Wajah terlalu dekat ke layar — mundur sedikit."],
    "stats": { "elapsed_sec": 540, "posture_score": 82,
               "slouch_events": 3, "close_events": 1, "tilt_events": 0 }
  }
  ```
- `POST /api/calibrate` → set baseline dari frame saat ini → `{ "baseline": { "head_ratio": 1.2, "eye_width": 0.08 } }`.
- `POST /api/session/end` → tutup sesi & simpan ke PostgreSQL.
- `GET /api/history` → daftar JSON sesi terakhir (lihat §7 untuk field).
- `GET /api/settings` / `PUT /api/settings` → baca/ubah ambang (opsional, F11).

---

## 6. Indeks landmark MediaPipe Pose yang dipakai

Hanya bagian atas tubuh. Koordinat ter-normalisasi 0..1, sumbu **Y ke bawah**.

```
0 nose · 2 left_eye · 5 right_eye · 7 left_ear · 8 right_ear
11 left_shoulder · 12 right_shoulder
```

Tiga fitur turunan (sumber kebenaran ada di `analysis.py` — JANGAN ubah rumus
tanpa alasan, dan kalau diubah, samakan dengan PRD §12):

- `head_ratio = (Y_bahu_tengah − Y_mata_tengah) / lebar_bahu`  → kecil = membungkuk
- `eye_width  = jarak(mata_kiri, mata_kanan)` (TIDAK dinormalisasi) → besar = terlalu dekat
- `tilt_deg   = |sudut garis bahu thd horizontal|` → besar = miring

Ambang (relatif terhadap baseline hasil kalibrasi), harus sama dengan `analysis.py`:

```
SLOUCH_RATIO    = 0.82     # membungkuk bila head_ratio < 82% baseline
TOO_CLOSE_RATIO = 1.22     # terlalu dekat bila eye_width > 122% baseline
TILT_DEGREES    = 9.0      # miring bila tilt_deg > 9°
SMOOTH_WINDOW   = 8        # moving average antar-frame
BREAK_INTERVAL_SEC = 1200  # 20 menit (kecilkan saat demo)
```

`PostureAnalyzer` sudah punya: `calibrate(landmarks)`, `analyze(landmarks)`, dan
`stats.to_dict()`. Panggil dari `camera.py`/`app.py`, jangan duplikasi logikanya.

---

## 7. Skema database (PostgreSQL)

```sql
CREATE TABLE sessions (
    id             SERIAL PRIMARY KEY,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    duration_sec   INTEGER,
    posture_score  INTEGER,
    slouch_events  INTEGER DEFAULT 0,
    close_events   INTEGER DEFAULT 0,
    tilt_events    INTEGER DEFAULT 0
);
```

Catatan pemetaan nama: `analysis.py` memakai `too_close_events`; di DB & `/api/history`
kolomnya `close_events`. Lakukan pemetaan saat menyimpan, jangan ubah salah satunya
diam-diam.

---

## 8. Perintah

```bash
# instalasi (di Jetson; OpenCV mungkin sudah dari JetPack — jangan timpa)
pip install -r requirements.txt          # flask, flask-sock, psycopg2-binary, opencv-python, mediapipe

# database
sudo apt install postgresql
psql -U postgres -f schema.sql

# jalankan (dev)
python app.py                            # buka http://<IP_JETSON>:5000

# mode daya maksimal Jetson
sudo nvpmodel -m 0 && sudo jetson_clocks

# uji logika analisis tanpa kamera
python analysis.py                       # ada self-test di blok __main__
```

---

## 9. Catatan Jetson (PENTING)

- **Jalankan MediaPipe di CPU.** GPU di Jetson Orin Nano rumit (tak ada wheel GPU
  resmi, sering jatuh ke CPU). GPU/TensorRT hanya target "jika sempat", BUKAN MVP.
- Kalau `pip install mediapipe` gagal untuk kombinasi JetPack/Python di perangkat,
  pakai wheel aarch64 komunitas atau build dari source — jangan habiskan waktu
  mengejar GPU.
- Jaga fps tetap usable: resolusi ~640×480, proses tiap frame untuk satu orang;
  kalau berat, proses tiap-N frame.
- Catat versi yang berhasil (JetPack ↔ Python ↔ mediapipe) di README — ini bagian
  "environment" yang diminta tugas.

---

## 10. Konvensi kode

- Komentar & string yang terlihat user: **Bahasa Indonesia** (konsisten dgn `analysis.py`).
- Nama variabel/fungsi: bahasa Inggris, `snake_case` (Python), `camelCase` (JS).
- Python: jaga gaya & kebersihan seperti `analysis.py`; fungsi kecil & jelas.
- Jangan menambah dependensi baru tanpa alasan kuat; tujuan proyek = simpel & cepat.
- Tangani kasus tepi: tidak ada pose terdeteksi, sebagian tubuh keluar frame,
  belum kalibrasi → balas `status: "need_calibration"`, jangan crash.
- Privasi: JANGAN pernah menulis/mengirim frame video ke disk atau jaringan luar.

---

## 11. Urutan pengerjaan (status saat ini)

Lihat PRD §15 untuk jadwal 4 minggu. Ringkas:

1. **[x]** `camera.py`: kamera → MediaPipe → gambar skeleton (Jetson, CPU).  ← belum diuji di Jetson nyata
2. **[x]** `analysis.py`: `PostureAnalyzer` — lulus self-test (17/17).
3. **[x]** `app.py`: Flask + `/video_feed` (MJPEG) + `/ws` (feedback) + `/api/*`.
4. **[x]** `db.py` + `schema.sql`: simpan & ambil riwayat (PostgreSQL, tahan-gagal).
5. **[x]** `templates/index.html` + `static/app.js` + `static/style.css`: live view, kalibrasi, statistik, riwayat.
6. **[~]** Pengingat 20-20-20 (selesai di `analysis.py`), pengujian (self-test unit OK; uji di Jetson belum), (opsional) autostart systemd belum.

Tandai item saat selesai. Jaga kontrak §5 dan ambang §6 tetap sinkron di semua file.