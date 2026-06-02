# CLAUDE.md — Study Guardian: Punch Trainer

Panduan konteks untuk asisten coding (Claude Code) saat mengembangkan proyek ini.
Dokumen perencanaan lengkap ada di **`PRD_Study_Guardian.md`** — jika ada
keraguan soal *kenapa* sebuah keputusan diambil, rujuk PRD. File ini berisi
*bagaimana* mengerjakannya secara konkret. Jaga keduanya tetap konsisten.

---

## 1. Apa ini

Study Guardian **Punch Trainer** = perangkat edge AI untuk **latihan tinju**.
Berjalan di **NVIDIA Jetson Orin Nano** (atau laptop untuk pengembangan) dengan
kamera menghadap pemain. MediaPipe + seluruh logika game berjalan **di perangkat
(Python)**; video tidak pernah keluar ke cloud. Pemain bermain lewat halaman web
yang **disajikan oleh Flask itu sendiri**.

Mode utama: **Target Reaksi** — sebuah target (🥊) menyala di salah satu zona;
pemain harus "meninju" ke zona itu. Pukulan **hanya dihitung** bila: **cepat**
(melewati ambang kecepatan), **ter-ekstensi cukup** (relatif jangkauan
default), dan **mendarat di zona target** yang aktif. Sistem menghitung
**skor, kombo, akurasi, kecepatan (estimasi m/s), dan waktu reaksi**.

---

## 2. Arsitektur (monolitik — JANGAN dipisah)

Satu proses Flask menangani semuanya. Tidak ada server frontend terpisah, tidak
ada Node/npm, tidak ada langkah build (frontend pakai pustaka vendor lokal).

```
Kamera ──► OpenCV ──► MediaPipe Pose Landmarker (Tasks API) ──► PunchAnalyzer ──► Flask
                                                                                  ├─ menyajikan index.html (HTML/JS)
                                                                                  ├─ /video_feed  (MJPEG, frame + skeleton)
                                                                                  ├─ /ws          (WebSocket: state game)
                                                                                  ├─ /api/...     (REST: play, stop, settings)
                                                                                  └─ PostgreSQL   (settings; riwayat opsional)
```

Aturan penting:
- Deteksi pose & **keputusan pukulan** terjadi **di Python di perangkat**, BUKAN di browser.
- Browser hanya menampilkan: `<img src="/video_feed">` + overlay target + update via WebSocket.
- Logika game (apakah pukulan sah, kena/meleset, skor, kombo) **hanya di Python**.

---

## 3. Tech stack

| Lapisan | Pilihan | Catatan |
|---------|---------|---------|
| Perangkat | Jetson Orin Nano (JetPack/L4T) / laptop dev | MediaPipe jalan di **CPU** (lihat §9) |
| Kamera + frame | OpenCV (`opencv-contrib-python`) | webcam USB diutamakan |
| Deteksi | `mediapipe` **Tasks API** (`PoseLandmarker`, model **lite**) | indeks landmark di §6 |
| Server + UI | **Flask** + `flask-sock` | satu server menyajikan UI & API |
| Database | **PostgreSQL** (`psycopg2-binary`) | skema di §7 |
| Frontend | **HTML + JS polos** + Alpine.js · Chart.js · Toastify · Day.js (vendor lokal) | folder `templates/` & `static/`, tanpa build |

Frontend memakai pustaka ringan **vendor lokal** di `static/vendor/` (aman
offline). JANGAN pakai `socket.io-client` (backend pakai WebSocket biasa) atau
`@mediapipe/tasks-vision` (deteksi ada di Python). Jangan menambah framework
berat/bundler.

---

## 4. Struktur folder

```
guardian/
├── CLAUDE.md
├── PRD_Study_Guardian.md
├── README.md
├── PANDUAN.md
├── requirements.txt
├── app.py                # entrypoint Flask: route, /video_feed, /ws, /api/*
├── camera.py             # loop kamera + MediaPipe Pose Landmarker (Tasks); frame + landmarks
├── analysis.py           # PunchAnalyzer (deteksi pukulan, target, skor) — punya self-test
├── db.py                 # koneksi PostgreSQL + query sesi & settings
├── schema.sql            # DDL tabel (lihat §7)
├── models/
│   └── pose_landmarker_lite.task   # model MediaPipe (vendor lokal, ~5,5 MB)
├── templates/
│   └── index.html        # arena layar penuh + HUD + target + tombol Play/Stop
└── static/
    ├── app.js            # komponen Alpine: WebSocket, Play/Stop, target, toast
    ├── style.css         # tema premium + energi tinju
    └── vendor/           # alpine.min.js, chart.umd.min.js, toastify.*, dayjs.min.js
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
    "status": "idle | playing",
    "metrics": { "left": { "ext": 1.2, "speed": 3.4 },
                 "right": { "ext": 0.4, "speed": 0.1 } },
    "target": { "id": "TR", "x": 0.70, "y": 0.35, "r": 0.13 },
    "last_event": { "seq": 12, "type": "hit | miss | none", "hand": "left",
                    "combo": 4, "speed": 4.8, "reaction_ms": 310 },
    "alerts": [],
    "stats": { "elapsed_sec": 95, "score": 1500, "combo": 4, "best_combo": 7,
               "punches": 22, "hits": 18, "accuracy": 82,
               "avg_speed": 3.6, "best_speed": 4.8,
               "last_reaction_ms": 310, "avg_reaction_ms": 313 }
  }
  ```
  `target` `null` saat `idle` (belum Play). Frontend memunculkan toast HIT/MISS
  saat `last_event.seq` berubah (agar event tidak terlewat).
- `POST /api/play` → **mulai bermain** langsung, tanpa kalibrasi (pakai jangkauan
  default ternormalisasi); reset statistik & munculkan target → `{ "ok": true }`.
- `POST /api/stop` → **berhenti** bermain. TIDAK menyimpan riwayat → `{ "ok": true, "summary": {…stats} }`.
- `GET /api/settings` / `PUT /api/settings` → baca/ubah ambang game (disimpan ke DB).

> Catatan: penyimpanan riwayat sesi (PostgreSQL `sessions`) saat ini dinonaktifkan
> di alur Stop sesuai permintaan; `db.save_session()` masih ada bila ingin diaktifkan.

---

## 6. Indeks landmark MediaPipe Pose yang dipakai

Tubuh bagian atas. Koordinat ter-normalisasi 0..1, sumbu **Y ke bawah**. Landmark
berasal dari **Tasks API** (`result.pose_landmarks[0]`), punya `.x/.y/.z/.visibility`.

```
11 left_shoulder · 12 right_shoulder
13 left_elbow · 14 right_elbow
15 left_wrist · 16 right_wrist
```

Fitur turunan (sumber kebenaran ada di `analysis.py` — JANGAN ubah rumus tanpa
menyamakan dengan PRD §12):

- `extension = jarak(pergelangan, bahu) / lebar_bahu`  → besar = lengan terjulur penuh
- `speed     = perpindahan pergelangan / dt` (unit-layar/detik, dihaluskan) → cepat = pukulan
- estimasi `m/s = speed × (0.40 / lebar_bahu)` (asumsi lebar bahu ~0,40 m)

Ambang (boleh diubah lewat `/api/settings`), harus sama dengan `analysis.py`:

```
PUNCH_SPEED_MIN   = 1.5     # kecepatan minimal (unit-layar/detik)
PUNCH_EXTEND_FRAC = 0.70    # pukulan sah bila extension >= 70% jangkauan default
REARM_FRAC        = 0.55    # harus menarik tangan < 55% untuk "isi ulang"
SPEED_SMOOTH      = 3       # smoothing kecepatan (kecil, agar pukulan cepat tak teredam)
TARGET_RADIUS     = 0.18    # radius zona target (ternormalisasi)
SCORE_BASE        = 100     # poin dasar per hit (dikali kombo)
```

`PunchAnalyzer` sudah punya: `start()` (Play — mulai, tanpa kalibrasi),
`stop()` (Stop), `analyze(landmarks)`, dan `stats.to_dict()`. Panggil dari
`app.py`, jangan duplikasi logikanya. Deteksi pukulan memakai mesin status
per-tangan (armed → fired → rearm) untuk mencegah satu gerakan terhitung
berkali-kali. Jangkauan memakai `DEFAULT_REACH` (tanpa kalibrasi manual).

---

## 7. Skema database (PostgreSQL)

```sql
CREATE TABLE sessions (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    duration_sec    INTEGER,
    score           INTEGER,
    punches         INTEGER DEFAULT 0,   -- total pukulan sah
    hits            INTEGER DEFAULT 0,   -- pukulan kena target
    accuracy        INTEGER,             -- 0..100 (%)
    best_combo      INTEGER DEFAULT 0,
    best_speed      REAL,                -- m/s (estimasi)
    avg_reaction_ms INTEGER
);

CREATE TABLE settings (
    id            INTEGER PRIMARY KEY DEFAULT 1,
    speed_min     REAL DEFAULT 2.0,
    extend_frac   REAL DEFAULT 0.80,
    target_radius REAL DEFAULT 0.13
);
```

`PunchStats.to_dict()` mengeluarkan kunci: `elapsed_sec, score, combo,
best_combo, punches, hits, accuracy, avg_speed, best_speed, last_reaction_ms,
avg_reaction_ms`. Saat menyimpan, `duration_sec ← elapsed_sec`; `combo`,
`avg_speed`, dan `last_reaction_ms` tidak disimpan (hanya untuk live).

> Catatan: `schema.sql` memuat `DROP TABLE IF EXISTS` agar pivot dari skema lama
> bersih — destruktif, jalankan hanya saat setup.

---

## 8. Perintah

```bash
# instalasi (lihat README/PANDUAN untuk venv Python 3.10)
pip install -r requirements.txt          # flask, flask-sock, psycopg2-binary, python-dotenv, numpy, opencv-contrib-python, mediapipe

# database
createdb study_guardian
psql -d study_guardian -f schema.sql

# jalankan (dev)
python app.py                            # buka http://<IP>:5000

# mode daya maksimal Jetson
sudo nvpmodel -m 0 && sudo jetson_clocks

# uji logika game tanpa kamera
python analysis.py                       # self-test PunchAnalyzer di blok __main__
```

---

## 9. Catatan Jetson (PENTING)

- **Jalankan MediaPipe di CPU.** GPU di Jetson Orin Nano rumit; bukan target MVP.
- Model `models/pose_landmarker_lite.task` ikut serta (vendor lokal) — salin ke perangkat.
- Pukulan itu **cepat**; jaga fps tetap tinggi (resolusi ~640×480, model *lite*,
  laju analisis ~15 Hz). fps rendah = pukulan cepat bisa terlewat.
- Catat versi yang berhasil (JetPack ↔ Python ↔ mediapipe) di README — bagian
  "environment" yang diminta tugas.

---

## 10. Konvensi kode

- Komentar & string yang terlihat user: **Bahasa Indonesia** (konsisten dgn `analysis.py`).
- Nama variabel/fungsi: bahasa Inggris, `snake_case` (Python), `camelCase`/Alpine (JS).
- Python: jaga gaya & kebersihan seperti `analysis.py`; fungsi kecil & jelas.
- Jangan menambah dependensi baru tanpa alasan kuat; tujuan proyek = simpel & cepat.
- Tangani kasus tepi: tidak ada pose, tangan keluar frame, belum Play →
  balas `status: "idle"` / `"playing"` tanpa deteksi, jangan crash.
- Privasi: JANGAN pernah menulis/mengirim frame video ke disk atau jaringan luar.

---

## 11. Urutan pengerjaan (status saat ini)

1. **[x]** `camera.py`: kamera → MediaPipe Pose Landmarker (Tasks, CPU) → skeleton.
2. **[x]** `analysis.py`: `PunchAnalyzer` — deteksi pukulan, target, skor. Self-test 19/19.
3. **[x]** `app.py`: Flask + `/video_feed` + `/ws` + `/api/*`, loop analisis 15 Hz.
4. **[x]** `db.py` + `schema.sql`: simpan & ambil riwayat + settings (PostgreSQL).
5. **[x]** `templates/index.html` + `static/*`: arena, overlay target, HUD, statistik, riwayat.
6. **[~]** Mode tambahan (Kombo, Timed Round), suara, autostart systemd — opsional, belum.

Tandai item saat selesai. Jaga kontrak §5 dan ambang §6 tetap sinkron di semua file.
