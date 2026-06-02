# PRD — Study Guardian: Punch Trainer
### Game Latihan Tinju Berbasis MediaPipe (Edge / Jetson Orin Nano)

| | |
|---|---|
| **Nama Produk** | Study Guardian — Punch Trainer |
| **Jenis Tugas** | Application-based project (Final Project MediaPipe) |
| **Platform** | Perangkat edge: NVIDIA Jetson Orin Nano + kamera (atau laptop untuk dev), antarmuka web (HTML/JS) yang disajikan Flask |
| **Tim** | Maksimal 5 orang |
| **Deadline** | 1 Juli 2026 |
| **Versi Dokumen** | 1.0 (Punch Trainer; Flask monolitik + PostgreSQL; MediaPipe Pose Landmarker Tasks API; deployment Jetson Orin Nano) |

> **Catatan arsitektur:** frontend **tidak dipisah** — memakai **HTML + JavaScript
> polos** (Alpine.js/Chart.js/Toastify/Day.js sebagai pustaka ringan vendor lokal)
> yang disajikan langsung oleh Flask (arsitektur monolitik). Tanpa Node/npm, tanpa
> langkah build. Inti: MediaPipe + seluruh logika game berjalan di Python on-device,
> database PostgreSQL.

---

## 1. Ringkasan Eksekutif

Punch Trainer adalah perangkat edge AI yang mengubah kamera menjadi **alat latihan
tinju interaktif**. Sebuah NVIDIA Jetson Orin Nano (atau laptop) dengan kamera
dipasang menghadap pemain; perangkat menjalankan MediaPipe secara lokal untuk
mendeteksi gerakan tubuh bagian atas (bahu, siku, pergelangan) secara real-time.
Sebuah target menyala di layar; pemain harus **meninju ke arah target dengan
pukulan yang benar** — cepat dan ter-ekstensi penuh. Sistem menilai pukulan,
menghitung skor, kombo, akurasi, kecepatan, dan waktu reaksi.

Nilai jual utama: **seluruh pemrosesan terjadi di perangkat (on-device / edge)** —
video tidak pernah meninggalkan perangkat, tanpa cloud — sementara Python menjadi
inti yang menjalankan deteksi MediaPipe sekaligus seluruh logika game. Ini contoh
nyata penerapan MediaPipe pada perangkat embedded yang **interaktif dan
gamified**, sesuai semangat dokumen tugas.

---

## 2. Latar Belakang & Pernyataan Masalah

Latihan tinju (atau olahraga refleks pada umumnya) butuh **umpan balik objektif**:
seberapa cepat pukulan, seberapa tepat sasaran, seberapa cepat reaksi. Alat
profesional (sensor sarung, reflex bag elektronik) mahal. Aplikasi yang ada sering
butuh perangkat khusus atau mengirim video ke cloud.

Punch Trainer menawarkan alternatif: cukup **satu kamera + perangkat edge**, semua
diproses lokal. Pemain mendapat skor, kombo, kecepatan, dan reaksi secara
real-time tanpa alat tambahan, tanpa mengirim rekaman ke mana pun — cocok untuk
latihan mandiri di rumah dan demonstrasi teknologi edge AI.

---

## 3. Tujuan & Bukan Tujuan

**Tujuan (MVP)**
- Mendeteksi **pukulan sah** (cepat + ekstensi penuh) secara real-time di perangkat.
- Mode **Target Reaksi**: target menyala di zona, pukulan dihitung hanya bila kena.
- Memberi umpan balik instan: skor, kombo, akurasi, kecepatan (estimasi), reaksi.
- Menyimpan & menampilkan riwayat sesi latihan beserta tren skor.
- Berjalan mandiri di Jetson Orin Nano; UI bisa dibuka dari layar perangkat atau perangkat se-jaringan.

**Bukan Tujuan (di luar lingkup MVP)**
- Tidak mengukur **tenaga/impact** pukulan (kamera hanya mengukur gerakan, kecepatan, ekstensi, akurasi).
- Tidak ada login/akun multi-user (cukup satu pemain lokal).
- Tidak mengklasifikasi jenis pukulan (jab/cross/hook) secara presisi di MVP.
- Tidak menargetkan akselerasi GPU sebagai syarat MVP (lihat §18).

---

## 4. Target Pengguna

**Persona utama — "Raka, mahasiswa yang suka olahraga"**
Ingin latihan refleks & kecepatan tangan di kamar kos tanpa alat mahal. Suka
tantangan terukur (skor, kombo) dan progres yang kelihatan. Mengutamakan privasi —
tidak mau rekaman dirinya dikirim ke server cloud.

**Kebutuhan kunci persona:** tinggal nyalakan & main, umpan balik instan yang
terasa seperti game, dan jaminan video diproses lokal.

---

## 5. User Stories

1. Sebagai pemain, saya ingin **mengkalibrasi jangkауan tangan saya** agar penilaian pukulan adil untuk tubuh saya.
2. Sebagai pemain, saya ingin **target menyala** sehingga saya tahu harus meninju ke mana.
3. Sebagai pemain, saya ingin **hanya pukulan benar (cepat + penuh + tepat) yang dapat poin** agar latihan bermakna.
4. Sebagai pemain, saya ingin **melihat skor, kombo, kecepatan, dan reaksi** secara real-time.
5. Sebagai pemain, saya ingin **melihat ringkasan & tren progres** di akhir sesi.
6. Sebagai pemain, saya ingin **yakin video saya diproses lokal** dan tidak dikirim ke cloud.

---

## 6. Kebutuhan Fungsional

| ID | Fitur | Deskripsi | Prioritas |
|----|-------|-----------|-----------|
| F1 | Akuisisi kamera | Ambil frame dari kamera (USB/CSI) via OpenCV | Wajib |
| F2 | Deteksi pose on-device | MediaPipe Pose Landmarker (Tasks API, Python), gambar skeleton overlay | Wajib |
| F3 | Kalibrasi jangkauan | Aksi UI untuk menetapkan jangkauan lengan penuh sebagai patokan | Wajib |
| F4 | Deteksi pukulan sah | Kenali pukulan: kecepatan ≥ ambang + ekstensi ≥ ambang (relatif kalibrasi) | Wajib |
| F5 | Target & zona | Target menyala di salah satu zona; pukulan dicek mengenai target | Wajib |
| F6 | Skor & kombo | Hit menambah skor (dikali kombo); meleset memutus kombo | Wajib |
| F7 | Metrik latihan | Akurasi, kecepatan (estimasi m/s), waktu reaksi | Wajib |
| F8 | Statistik sesi | Skor, durasi, pukulan, hits, kombo terbaik, kecepatan terbaik | Wajib |
| F9 | Riwayat sesi | Simpan ringkasan tiap sesi ke PostgreSQL & tampilkan daftar + grafik tren | Wajib |
| F10 | Live view di web | Video ber-skeleton + overlay target + HUD di halaman HTML/JS | Wajib |
| F11 | Pengaturan sensitivitas | Atur ambang kecepatan/ekstensi/radius target (disimpan ke DB) | Opsional |
| F12 | Notifikasi suara | Bunyi saat HIT/MISS (bisa dimatikan) | Opsional |
| F13 | Mode tambahan | Kombo (urutan zona), Timed Round (ronde berwaktu) | Opsional |
| F14 | Autostart | Aplikasi berjalan otomatis saat perangkat menyala (systemd) | Opsional |

---

## 7. Kebutuhan Non-Fungsional

- **Performa (CPU):** target ≥ 15 fps untuk pose *lite* satu orang pada ~640×480.
  Penting karena pukulan cepat — fps rendah bisa melewatkan puncak gerakan.
- **Latency umpan balik:** HIT/MISS muncul < 200 ms setelah pukulan.
- **Privasi:** seluruh pemrosesan di perangkat; tidak ada video keluar ke internet.
- **Termal & daya (Jetson):** ventilasi cukup; pakai mode daya maksimal.
- **Kemudahan pakai:** nyala → kalibrasi satu aksi → langsung main.
- **Kompatibilitas:** UI dibuka via Chrome/Edge dari perangkat atau se-jaringan.

---

## 8. Arsitektur Sistem

Perangkat edge mandiri: semua inti berjalan di perangkat; UI disajikan dari perangkat.

```
                       PERANGKAT (Jetson Orin Nano / laptop)
┌─────────────────────────────────────────────────────────────┐
│  Kamera (USB / CSI)                                           │
│        │                                                      │
│        ▼                                                      │
│  OpenCV  ──►  MediaPipe Pose Landmarker (Tasks API, on-device)│
│                       │                                       │
│                       ▼                                       │
│              PunchAnalyzer (Python)                           │
│              • kalibrasi jangkauan & smoothing                │
│              • deteksi pukulan (cepat + ekstensi + armed)     │
│              • target/zona • skor • kombo • reaksi            │
│                       │                                       │
│        ┌──────────────┼───────────────────────┐              │
│        ▼              ▼                        ▼              │
│   Flask + flask-sock                      PostgreSQL          │
│   • menyajikan index.html (HTML/JS)       (riwayat sesi)      │
│   • MJPEG video feed (skeleton)                               │
│   • WebSocket: state game (target, event, stats)             │
│   • REST: kalibrasi, riwayat, pengaturan                      │
└───────────────────────────┬───────────────────────────────────┘
                            │  HTTP / WebSocket (jaringan lokal)
                            ▼
                  ┌──────────────────────┐
                  │   Browser            │
                  │  • Arena (MJPEG)     │
                  │  • Overlay target 🥊 │
                  │  • HUD skor/kombo    │
                  │  • Statistik & riwayat│
                  └──────────────────────┘
```

**Mengapa begini:** menjalankan deteksi di perangkat menjadikan produk edge AI
sejati dan menjaga privasi. Python menjadi inti penuh: menjalankan MediaPipe *dan*
seluruh logika game. Flask sekaligus menyajikan UI → **tidak ada server frontend
terpisah**.

---

## 9. Technology Stack

| Lapisan | Teknologi | Alasan |
|---------|-----------|--------|
| Perangkat | Jetson Orin Nano (JetPack/L4T) / laptop | Edge AI, target embedded MediaPipe |
| Kamera | Webcam USB / kamera CSI | USB paling kompatibel |
| Akuisisi & gambar | OpenCV (Python) | Ambil frame, gambar skeleton, encode MJPEG |
| Deteksi pose | `mediapipe` **Tasks API** (`PoseLandmarker`, model *lite*) | Inti deteksi on-device, API resmi terbaru |
| Logika game | Python murni (`PunchAnalyzer`) | Inti keputusan; portabel & teruji |
| Backend + frontend | **Flask** + `flask-sock` (WebSocket) | Satu server: UI + API; ringan |
| Database | **PostgreSQL** (`psycopg2`) | Andal & skalabel |
| Frontend | **HTML + JS** + Alpine.js · Chart.js · Toastify · Day.js (vendor lokal) | Reaktif, grafik, toast, tanpa build |
| Komunikasi | MJPEG (video) + WebSocket (state) + REST (data) | MJPEG hemat; WS real-time |

Jalankan pada **CPU** untuk MVP; akselerasi GPU opsional & rumit (§18).

---

## 10. Model Data (PostgreSQL)

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

CREATE TABLE settings (        -- F11: ambang tersimpan
    id            INTEGER PRIMARY KEY DEFAULT 1,
    speed_min     REAL DEFAULT 2.0,
    extend_frac   REAL DEFAULT 0.80,
    target_radius REAL DEFAULT 0.13
);
```

---

## 11. Spesifikasi API & Protokol

**Streaming video:** `GET /video_feed` → MJPEG (`multipart/x-mixed-replace`) berisi
frame ber-skeleton. Ditampilkan sebagai `<img src="/video_feed">` dengan overlay
target di atasnya.

**State game (WebSocket `/ws`):** server mendorong feedback tiap analisis.
```json
{
  "type": "feedback",
  "status": "ready | need_calibration",
  "metrics": { "left": {"ext": 1.2, "speed": 3.4}, "right": {"ext": 0.4, "speed": 0.1} },
  "target": { "id": "TR", "x": 0.70, "y": 0.35, "r": 0.13 },
  "last_event": { "seq": 12, "type": "hit", "hand": "left", "combo": 4,
                  "speed": 4.8, "reaction_ms": 310 },
  "alerts": [],
  "stats": { "elapsed_sec": 95, "score": 1500, "combo": 4, "best_combo": 7,
             "punches": 22, "hits": 18, "accuracy": 82,
             "avg_speed": 3.6, "best_speed": 4.8,
             "last_reaction_ms": 310, "avg_reaction_ms": 313 }
}
```

**REST:**
- `POST /api/calibrate` → tetapkan jangkauan; balas `{ "baseline": { "reach_left": 1.8, "reach_right": 1.7 } }`.
- `POST /api/session/end` → tutup sesi & simpan ke PostgreSQL.
- `GET /api/history` → daftar JSON sesi terakhir.
- `GET /api/settings` / `PUT /api/settings` → baca/ubah ambang (F11), disimpan ke DB.

---

## 12. Detail Algoritma (inti Python)

Dari landmark tubuh atas dihitung, **per tangan** (kiri 11/13/15, kanan 12/14/16):

**a. Ekstensi lengan**
`extension = jarak(pergelangan, bahu) / lebar_bahu`. Dinormalisasi lebar bahu agar
**tidak terpengaruh jarak ke kamera**. Lengan terjulur penuh = nilai besar.

**b. Kecepatan pergelangan**
`speed = perpindahan_pergelangan / dt` (unit-layar/detik), dihaluskan ringan
(window kecil agar pukulan cepat tidak teredam). Estimasi `m/s = speed ×
(0,40 / lebar_bahu)` (asumsi lebar bahu ~0,40 m).

**Kalibrasi:** jangkauan penuh (extension saat tangan terjulur) disimpan sebagai
*baseline* per tangan; ambang relatif terhadapnya → adil untuk semua ukuran badan.

**Deteksi pukulan (mesin status per tangan):** tangan "armed" saat ditarik
(extension < 55% jangkauan). Pukulan **sah** terdaftar saat extension ≥ 80%
jangkauan **dan** speed ≥ ambang **dan** sedang armed → status jadi "fired"
(mencegah double-count) sampai ditarik lagi.

**Target & skor:** satu target aktif di sebuah zona. Saat pukulan sah terjadi,
posisi pergelangan dicek terhadap zona target: **kena** → skor += `SCORE_BASE ×
kombo`, kombo++, catat reaksi (waktu sejak target muncul), target baru muncul;
**meleset** → kombo putus.

> Catatan laporan: normalisasi terhadap lebar bahu, ambang relatif berbasis
> kalibrasi, dan mesin status armed/rearm inilah "tuning details" yang bisa
> dielaborasi sebagai kontribusi teknis.

---

## 13. Kebutuhan UI/UX (HTML + JavaScript, disajikan Flask)

**Arena (halaman utama):**
- Live view (MJPEG) dengan overlay skeleton.
- **Overlay target 🥊** yang menyala/berdenyut di zona aktif.
- **HUD** di atas video: skor, kombo, waktu.
- Indikator status: "Siap — Tinju!" / "Perlu Kalibrasi".
- Strip metrik kecepatan kiri/kanan (m/s).
- Tombol **Mulai (Kalibrasi)**, **Selesai**.
- **Toast** HIT (kombo, kecepatan, reaksi) / MISS.

**Panel statistik & riwayat:** akurasi, kecepatan terbaik, pukulan, hits, kombo
terbaik, reaksi rata-rata; **grafik tren skor** antar-sesi (Chart.js) + daftar riwayat.

**Implementasi:** satu `index.html` + JS/CSS statis + pustaka vendor lokal. Status
via WebSocket; riwayat via `fetch('/api/history')`.

**Arah desain:** premium, energik (aksen merah tinju), target jelas terlihat,
umpan balik instan.

---

## 14. Lingkup MVP vs Pengembangan Lanjutan

**MVP (wajib):** F1–F10 — kamera, deteksi pose on-device, kalibrasi jangkauan,
deteksi pukulan sah, target & skor/kombo, metrik (akurasi/kecepatan/reaksi),
statistik, riwayat (PostgreSQL), live view + overlay target.

**Jika sempat:** F11 (UI slider sensitivitas — endpoint sudah ada), F12 (suara),
F13 (mode Kombo & Timed Round), F14 (autostart systemd).

**Ide masa depan:** klasifikasi jenis pukulan (jab/cross/hook), mode dua tangan
spesifik, papan peringkat, integrasi musik/ritme, akselerasi GPU/TensorRT.

> Prinsip dokumen tugas: **kualitas, bukan kuantitas.** Kunci MVP, demo mulus.

---

## 15. Rencana Kerja (±4 Minggu)

| Minggu | Target | Keluaran |
|--------|--------|----------|
| 1 | Bring-up Jetson/laptop: kamera via OpenCV, MediaPipe Pose Landmarker (Tasks, CPU) | Skeleton tergambar |
| 2 | Inti `PunchAnalyzer` (kalibrasi, deteksi pukulan, target, skor) + Flask (MJPEG + WS) | Pukulan terdeteksi & dinilai benar |
| 3 | UI arena rapi (overlay target, HUD, toast), PostgreSQL + riwayat + grafik, pengujian | Game utuh & enak dimainkan |
| 4 | Mode tambahan (opsional), laporan, dokumentasi, latihan demo, perbaikan | Submission + demo siap |

**Tonggak kritis:** akhir Minggu 1, kamera + MediaPipe jalan di perangkat (paling berisiko).

---

## 16. Pembagian Tugas (5 orang)

| Peran | Tanggung jawab |
|-------|----------------|
| Jetson & deployment | Setup JetPack, kamera, instalasi MediaPipe, autostart, profil daya/termal |
| Pipeline MediaPipe + OpenCV | Akuisisi frame, Pose Landmarker (Tasks), skeleton, MJPEG |
| Logika game Python | `PunchAnalyzer`: kalibrasi, deteksi pukulan, target, skor, tuning ambang (kontribusi teknis terbesar) |
| Backend Flask + PostgreSQL | API, WebSocket, skema & query DB, pengujian |
| Frontend (HTML/JS) + laporan | Arena + overlay target + HUD + statistik, integrasi, lab report, koordinasi demo |

---

## 17. Rencana Pengujian

- **Unit test logika game:** beri pose palsu (guard, terjulur cepat, terjulur pelan,
  setengah, meleset) → pastikan pukulan sah/hit/miss/skor benar (lihat self-test `analysis.py`).
- **Uji fungsional:** tiap fitur F1–F10 diuji dengan skenario nyata.
- **Uji kalibrasi:** pemain dengan jangkauan berbeda → penilaian tetap adil.
- **Uji performa:** ukur fps & suhu; pastikan pukulan cepat tertangkap.
- **Uji jaringan:** akses UI dari perangkat lain di jaringan lokal.

---

## 18. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| **fps rendah** melewatkan pukulan cepat | Hit tak terdeteksi | Resolusi sedang, model *lite*, analisis ~15 Hz, `jetson_clocks` |
| **Ambiguitas kedalaman 2D** (pukulan lurus ke kamera) | Akurasi terbatas | Fokus pukulan ke zona layar (gerakan terlihat di 2D); jelaskan keterbatasan di laporan |
| GPU MediaPipe di Jetson sulit | Waktu terbuang | **Jalankan di CPU**; GPU hanya jika sempat |
| Instalasi MediaPipe di aarch64 gagal | Pipeline tak jalan | Wheel komunitas / build dari source (§19) |
| Tidak ada sensor impact | Tak bisa ukur tenaga | Posisikan sebagai latihan kecepatan/akurasi/reaksi, bukan tenaga |
| Scope membengkak | Tidak selesai | Kunci MVP F1–F10 |

---

## 19. Panduan Deployment Jetson Orin Nano

1. **Flash JetPack** stabil untuk Orin Nano; pastikan CUDA & OpenCV bawaan.
2. **Mode daya maksimal:** `sudo nvpmodel -m 0 && sudo jetson_clocks`.
3. **Verifikasi kamera:** `v4l2-ctl --list-devices`; uji ambil frame OpenCV.
4. **Pasang MediaPipe (Python):** coba `pip install mediapipe`; bila gagal untuk
   kombinasi JetPack/Python, pakai wheel aarch64 komunitas / build dari source.
   Jalur GPU rumit — bukan target MVP.
5. **Backend + frontend:** `pip install flask flask-sock psycopg2-binary python-dotenv`.
   OpenCV mungkin sudah ada dari JetPack — jangan timpa. Frontend cukup taruh
   `templates/` + `static/` (pustaka vendor lokal) — **tanpa Node/npm**.
6. **Model:** salin `models/pose_landmarker_lite.task` ke perangkat.
7. **PostgreSQL:** `sudo apt install postgresql`; buat DB & jalankan `schema.sql`.
8. **Autostart (opsional, F14):** service `systemd` agar berjalan saat boot.

**Catatan versi:** kombinasi JetPack ↔ Python ↔ MediaPipe menentukan keberhasilan.
Catat versi yang berhasil di README — bagian "environment" yang diminta tugas.

---

## 20. Metrik Keberhasilan

- Deteksi pukulan sah benar pada ≥ 90% skenario uji (cepat-penuh dihitung, pelan/setengah tidak).
- Hit/miss terhadap target tepat, kombo & skor konsisten.
- fps cukup (≥ ~15) sehingga pukulan cepat tertangkap; umpan balik < 200 ms.
- Riwayat sesi tersimpan di PostgreSQL & tampil benar (termasuk grafik tren).
- Pemain percobaan bisa main tanpa penjelasan tambahan.

---

## 21. Pemetaan ke Requirement Tugas

| Requirement Tugas | Cara Punch Trainer memenuhinya |
|-------------------|-------------------------------|
| Berbasis MediaPipe | Inti deteksi memakai MediaPipe Pose Landmarker (Tasks API, on-device) |
| Berjalan di perangkat embedded | Dijalankan di Jetson Orin Nano — sesuai contoh embedded |
| Aplikasi utuh & mudah dipakai | Nyala → kalibrasi → main; UI web dengan panduan & umpan balik instan |
| Backend berbasis Python | Flask + seluruh deteksi & logika game di Python |
| Arsitektur (separasi opsional) | Monolitik: Flask menyajikan UI + API + video dalam satu proses (sah & lebih simpel) |
| User experience tinggi | Gamified: target, skor, kombo, toast, grafik progres |
| Inovasi | Reflex/punch trainer edge on-device tanpa cloud; penilaian relatif berbasis kalibrasi |
| Tidak menyalin proyek | Logika & arsitektur dirancang sendiri |
| Kualitas > kuantitas | Lingkup MVP dikunci, eksekusi rapi |

---

*Dokumen ini adalah PRD perencanaan. Untuk submission akhir, isi konten relevan
(fungsi, ide implementasi, tech stack, environment versi Jetson, pengujian, deployment).*
