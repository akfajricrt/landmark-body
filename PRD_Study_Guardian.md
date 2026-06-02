# PRD — Study Guardian
### Sistem Pemantau Postur & Fokus Belajar Berbasis MediaPipe (Edge / Jetson Orin Nano)

| | |
|---|---|
| **Nama Produk** | Study Guardian |
| **Jenis Tugas** | Application-based project (Final Project MediaPipe) |
| **Platform** | Perangkat edge: NVIDIA Jetson Orin Nano + kamera, dengan antarmuka web sederhana (HTML/JS) yang disajikan Flask |
| **Tim** | Maksimal 5 orang |
| **Deadline** | 1 Juli 2026 |
| **Versi Dokumen** | 1.0 (Flask monolitik + PostgreSQL; frontend HTML/JS disajikan Flask; deployment Jetson Orin Nano) |

> **Catatan arsitektur:** frontend **tidak dipisah** — memakai **HTML + JavaScript polos yang disajikan langsung oleh Flask** (arsitektur monolitik). Lebih simpel & cepat: tanpa Node/npm, tanpa langkah build, satu server saja di Jetson. Inti: MediaPipe + analisis berjalan di Python on-device di Jetson, database PostgreSQL.
>
> Catatan: dokumen tugas hanya mensyaratkan front-back terpisah *jika* dipilih ("jika ... boleh pakai Flask/Django"); arsitektur monolitik ini sah dan tetap memenuhi syarat backend Python.

---

## 1. Ringkasan Eksekutif

Study Guardian adalah perangkat edge AI yang memantau postur tubuh dan kebiasaan duduk selama belajar. Sebuah NVIDIA Jetson Orin Nano dengan kamera dipasang menghadap meja belajar; perangkat ini menjalankan MediaPipe secara lokal untuk mendeteksi postur secara real-time, memberi peringatan halus saat user membungkuk, terlalu dekat ke layar, atau duduk miring, serta mengingatkan istirahat mata dengan aturan 20-20-20. User memantau status dan riwayatnya melalui antarmuka web sederhana (HTML + JavaScript) yang disajikan langsung oleh Flask di Jetson.

Nilai jual utamanya: **seluruh pemrosesan terjadi di perangkat (on-device / edge)** — video tidak pernah meninggalkan Jetson, tidak ada cloud, privat sepenuhnya — sementara Python (di Jetson) menjadi inti yang menjalankan deteksi MediaPipe sekaligus seluruh logika analisis. Ini menjadikan Study Guardian contoh nyata penerapan MediaPipe pada perangkat embedded, sesuai semangat dokumen tugas.

---

## 2. Latar Belakang & Pernyataan Masalah

Mahasiswa menghabiskan berjam-jam di depan laptop. Postur buruk yang berlangsung lama memicu nyeri leher–punggung (*text neck*), kelelahan mata digital, dan menurunnya konsentrasi. Masalahnya, orang tidak menyadari postur memburuk secara perlahan; tidak ada yang mengingatkan.

Solusi yang ada umumnya berupa perangkat keras mahal (sensor di kursi) atau aplikasi berbayar yang mengirim data ke cloud. Study Guardian menawarkan alternatif: perangkat kecil, berdiri sendiri di meja, memproses semuanya secara lokal tanpa mengirim data ke mana pun — cocok untuk pengguna yang peduli privasi.

---

## 3. Tujuan & Bukan Tujuan

**Tujuan (MVP)**
- Mendeteksi tiga masalah postur utama secara real-time di perangkat: membungkuk, terlalu dekat ke layar, badan miring.
- Memberi umpan balik visual yang tidak mengganggu, plus pengingat istirahat 20-20-20.
- Menyimpan dan menampilkan riwayat sesi belajar beserta skor postur.
- Berjalan mandiri di Jetson Orin Nano; antarmuka web bisa dibuka dari layar Jetson atau perangkat lain di jaringan yang sama.

**Bukan Tujuan (di luar lingkup MVP)**
- Tidak ada sistem login/akun multi-user (cukup satu pengguna lokal).
- Tidak mendiagnosis kondisi medis; hanya pengingat ergonomi.
- Tidak mengenali identitas wajah; hanya posisi tubuh.
- Tidak menargetkan akselerasi GPU sebagai syarat MVP (lihat Bagian 18 — GPU adalah opsi lanjutan).

---

## 4. Target Pengguna

**Persona utama — "Sinta, mahasiswi tingkat 2"**
Belajar 4–6 jam sehari di kamar kos. Sering pegal leher tapi tidak sadar kapan postur memburuk. Ingin alat yang tinggal dinyalakan dan bekerja sendiri. Mengutamakan privasi — tidak nyaman jika rekaman dirinya dikirim ke server cloud.

**Kebutuhan kunci persona:** perangkat menyala otomatis & langsung memantau, peringatan jelas tapi tidak mengganggu konsentrasi, dan jaminan data tidak ke mana-mana.

---

## 5. User Stories

1. Sebagai pengguna, saya ingin **perangkat langsung memantau saat dinyalakan** tanpa setup rumit.
2. Sebagai pengguna, saya ingin **mengkalibrasi postur ideal saya** agar penilaian sesuai tubuh saya.
3. Sebagai pengguna, saya ingin **diberi tahu saat membungkuk** agar bisa langsung memperbaiki posisi.
4. Sebagai pengguna, saya ingin **diingatkan istirahat mata** secara berkala.
5. Sebagai pengguna, saya ingin **melihat skor & statistik di akhir sesi** lewat tampilan web.
6. Sebagai pengguna, saya ingin **yakin video saya diproses lokal di perangkat** dan tidak dikirim ke cloud.

---

## 6. Kebutuhan Fungsional

| ID | Fitur | Deskripsi | Prioritas |
|----|-------|-----------|-----------|
| F1 | Akuisisi kamera | Ambil frame dari kamera (USB/CSI) di Jetson via OpenCV | Wajib |
| F2 | Deteksi pose on-device | Jalankan MediaPipe Pose Landmarker (Python) di Jetson, gambar skeleton overlay | Wajib |
| F3 | Kalibrasi | Aksi dari UI untuk menetapkan postur tegak sebagai patokan (baseline) | Wajib |
| F4 | Deteksi membungkuk | Peringatan saat kepala turun di bawah ambang baseline | Wajib |
| F5 | Deteksi jarak layar | Peringatan saat wajah terlalu dekat ke kamera | Wajib |
| F6 | Deteksi badan miring | Peringatan saat garis bahu melebihi kemiringan ambang | Wajib |
| F7 | Pengingat 20-20-20 | Tiap 20 menit, ingatkan istirahatkan mata 20 detik | Wajib |
| F8 | Statistik sesi | Skor postur (% waktu baik), durasi, jumlah event pelanggaran | Wajib |
| F9 | Riwayat sesi | Simpan ringkasan tiap sesi ke PostgreSQL & tampilkan daftar | Wajib |
| F10 | Live view di web | Tampilkan video ber-skeleton + status di halaman HTML/JS yang disajikan Flask | Wajib |
| F11 | Pengaturan sensitivitas | Slider untuk menyetel ambang & interval istirahat | Opsional |
| F12 | Notifikasi suara | Bunyi lembut saat peringatan (bisa dimatikan) | Opsional |
| F13 | Autostart | Aplikasi berjalan otomatis saat Jetson menyala (systemd) | Opsional |

---

## 7. Kebutuhan Non-Fungsional

- **Performa (Jetson, CPU):** target ≥ 12–15 fps untuk pose *lite* satu orang pada resolusi ~640×480. Gunakan mode daya maksimal (`nvpmodel` / `jetson_clocks`).
- **Latency umpan balik:** peringatan muncul < 500 ms setelah postur berubah.
- **Privasi:** seluruh pemrosesan terjadi di Jetson; tidak ada data video yang keluar ke internet. Antarmuka web hanya menampilkan hasil di jaringan lokal.
- **Termal & daya:** Jetson harus berventilasi cukup; pantau suhu agar tidak *throttling* saat sesi panjang.
- **Kemudahan pakai:** ideal-nya menyala → langsung memantau (autostart); kalibrasi cukup satu aksi.
- **Kompatibilitas antarmuka:** halaman web dibuka via Chrome/Edge dari Jetson atau perangkat se-jaringan.

---

## 8. Arsitektur Sistem

Perangkat edge mandiri: semua inti berjalan di Jetson; antarmuka web disajikan dari Jetson.

```
                       NVIDIA JETSON ORIN NANO
┌─────────────────────────────────────────────────────────────┐
│  Kamera (USB / CSI)                                           │
│        │                                                      │
│        ▼                                                      │
│  OpenCV  ──►  MediaPipe Pose Landmarker (Python, on-device)   │
│                       │                                       │
│                       ▼                                       │
│              PostureAnalyzer (Python)                         │
│              • kalibrasi & smoothing                          │
│              • deteksi bungkuk / jarak / miring               │
│              • timer 20-20-20  • hitung statistik             │
│                       │                                       │
│        ┌──────────────┼───────────────────────┐              │
│        ▼              ▼                        ▼              │
│   Flask + flask-sock                      PostgreSQL          │
│   • menyajikan index.html (HTML/JS)       (riwayat sesi)      │
│   • MJPEG video feed (skeleton)                               │
│   • WebSocket: feedback + statistik                           │
│   • REST: kalibrasi, riwayat, pengaturan                      │
└───────────────────────────┬───────────────────────────────────┘
                            │  HTTP / WebSocket (jaringan lokal)
                            ▼
                  ┌──────────────────────┐
                  │   Browser            │
                  │  (HTML + JS polos,   │
                  │   disajikan Flask)   │
                  │  • Live view (MJPEG) │
                  │  • Panel status &    │
                  │    statistik         │
                  │  • Halaman riwayat   │
                  └──────────────────────┘
```

**Mengapa begini:** menjalankan deteksi di Jetson menjadikan produk perangkat edge AI sejati (sesuai tujuan memakai Jetson) dan menjaga privasi (video tidak pernah ke cloud). Python di Jetson menjadi inti penuh: menjalankan MediaPipe *dan* seluruh logika keputusan. Flask sekaligus menyajikan halaman HTML/JS, sehingga **tidak ada server frontend terpisah** — satu proses Flask saja menangani UI, video, status, dan data. Lebih sedikit yang harus dipasang & dijalankan di Jetson.

> Alternatif (jika Jetson tidak tersedia saat pengembangan): deteksi tetap bisa dijalankan di browser dengan `@mediapipe/tasks-vision`, lalu dipindahkan ke Jetson belakangan. Logika `PostureAnalyzer` identik karena murni Python. Frontend HTML/JS yang sama tetap dipakai.

---

## 9. Technology Stack

| Lapisan | Teknologi | Alasan |
|---------|-----------|--------|
| Perangkat | NVIDIA Jetson Orin Nano (JetPack/L4T) | Edge AI, target embedded MediaPipe |
| Kamera | Webcam USB (paling mudah) atau kamera CSI | USB paling kompatibel & cepat dipasang |
| Akuisisi & gambar | OpenCV (Python) | Ambil frame, gambar skeleton, encode MJPEG |
| Deteksi pose | `mediapipe` (Python, Pose Landmarker, model *lite*) di Jetson | Inti deteksi on-device |
| Logika analisis | Python murni (`PostureAnalyzer`) | Inti keputusan; portabel & teruji |
| Backend + frontend | **Flask** + `flask-sock` (WebSocket) | Satu server: menyajikan HTML/JS sekaligus API; ringan & mudah di Jetson |
| Database | **PostgreSQL** (via `psycopg2` / SQLAlchemy) | Sesuai permintaan; andal & skalabel |
| Frontend | **HTML + JavaScript polos** (disajikan Flask via Jinja2/static) | Tanpa Node/npm & tanpa build — paling simpel & cepat untuk MVP |
| Komunikasi | MJPEG (video) + WebSocket (status) + REST (data) | MJPEG hemat untuk streaming; WS untuk update real-time |

Catatan instalasi MediaPipe di Jetson: lihat Bagian 19. Jalankan pada **CPU** untuk MVP; akselerasi GPU bersifat opsional dan rumit.

---

## 10. Model Data (PostgreSQL)

```sql
CREATE TABLE sessions (
    id             SERIAL PRIMARY KEY,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    duration_sec   INTEGER,
    posture_score  INTEGER,          -- 0..100, % waktu postur baik
    slouch_events  INTEGER DEFAULT 0,
    close_events   INTEGER DEFAULT 0,
    tilt_events    INTEGER DEFAULT 0
);

-- opsional, untuk F11 (pengaturan tersimpan)
CREATE TABLE settings (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    slouch_ratio    REAL DEFAULT 0.82,
    close_ratio     REAL DEFAULT 1.22,
    tilt_degrees    REAL DEFAULT 9.0,
    break_interval  INTEGER DEFAULT 1200   -- detik (20 menit)
);
```

---

## 11. Spesifikasi API & Protokol

**Streaming video:** `GET /video_feed` → aliran MJPEG (`multipart/x-mixed-replace`) berisi frame ber-skeleton. Ditampilkan di halaman sebagai `<img src="/video_feed">`.

**Status real-time (WebSocket ` /ws`):** server (Jetson) mendorong feedback tiap analisis.
```json
{
  "type": "feedback",
  "status": "good | warn | need_calibration",
  "metrics": { "head_ratio": 0.95, "eye_width": 0.10, "tilt_deg": 3.2 },
  "flags": { "slouching": false, "too_close": true, "tilted": false, "break_due": false },
  "alerts": [ "Wajah terlalu dekat ke layar — mundur sedikit." ],
  "stats": { "elapsed_sec": 540, "posture_score": 82,
             "slouch_events": 3, "close_events": 1, "tilt_events": 0 }
}
```

**REST:**
- `POST /api/calibrate` → menetapkan baseline dari frame saat ini; balas `{ "baseline": { "head_ratio": 1.2, "eye_width": 0.08 } }`.
- `POST /api/session/end` → tutup sesi & simpan ke PostgreSQL.
- `GET /api/history` → daftar JSON sesi terakhir.
- `GET /api/settings` / `PUT /api/settings` → baca/ubah ambang (F11).

---

## 12. Detail Algoritma Analisis (inti Python)

Logika ini portabel, baik dijalankan di browser maupun di Jetson. Dari 33 landmark dihitung tiga fitur:

**a. Rasio tinggi kepala (deteksi membungkuk)**
`head_ratio = (Y_bahu_tengah − Y_mata_tengah) / lebar_bahu`. Dinormalisasi terhadap lebar bahu agar **tidak terpengaruh jarak user ke kamera**. Membungkuk bila rasio < 82% dari baseline.

**b. Lebar antar-mata (deteksi jarak layar)**
`eye_width = jarak(mata_kiri, mata_kanan)`, **sengaja tidak dinormalisasi** — pelebaran inilah penanda wajah mendekat. Terlalu dekat bila > 122% dari baseline.

**c. Kemiringan bahu (deteksi badan miring)**
Sudut garis bahu terhadap horizontal via `atan2`. Miring bila > 9°.

**Kalibrasi:** fitur saat duduk tegak disimpan sebagai *baseline*; semua ambang relatif terhadapnya → adil untuk semua bentuk tubuh.
**Smoothing:** rata-rata bergerak 8 frame untuk meredam getaran deteksi.
**Penghitungan event:** dihitung hanya pada transisi baik → buruk.
**Aturan 20-20-20:** timer di Python; tiap 20 menit memunculkan pengingat.

> Catatan laporan: normalisasi & pemilihan ambang relatif inilah "tuning details" yang bisa kalian elaborasi sebagai kontribusi teknis.

---

## 13. Kebutuhan UI/UX (HTML + JavaScript, disajikan Flask)

**Halaman utama (Dashboard):**
- Live view (MJPEG) dengan overlay skeleton di tengah.
- Indikator status besar: hijau "Postur Baik" / kuning "Perlu Diperbaiki".
- Daftar peringatan aktif (muncul/hilang halus).
- Tombol **Kalibrasi**, **Akhiri Sesi**.
- Panel statistik live: skor postur, durasi, jumlah event.
- Panduan singkat saat pertama buka: "1) Duduk tegak 2) Kalibrasi".

**Halaman Riwayat:** daftar sesi sebelumnya dengan skor & durasi (data dari PostgreSQL).

**Implementasi:** satu halaman `index.html` + file JS/CSS statis yang disajikan Flask. Live view memakai `<img src="/video_feed">` (MJPEG); status diperbarui via WebSocket; riwayat diambil via `fetch('/api/history')`.

**Arah desain:** tenang & tidak melelahkan mata (tema terang lembut/warna hangat), peringatan terlihat tanpa mengganggu fokus.

---

## 14. Lingkup MVP vs Pengembangan Lanjutan

**MVP (wajib selesai):** F1–F10 — kamera, deteksi pose on-device, kalibrasi, tiga deteksi postur, pengingat 20-20-20, statistik, riwayat (PostgreSQL), live view (HTML/JS disajikan Flask).

**Jika sempat:** F11 (slider sensitivitas), F12 (suara), F13 (autostart systemd), grafik tren skor antar-sesi.

**Ide masa depan (sebut di laporan):** akselerasi GPU/TensorRT, deteksi mata mengantuk, beberapa profil pengguna, integrasi Pomodoro.

> Prinsip dokumen tugas: **kualitas, bukan kuantitas.** Kunci MVP, pastikan demo mulus.

---

## 15. Rencana Kerja (±4 Minggu)

| Minggu | Target | Keluaran |
|--------|--------|----------|
| 1 | Bring-up Jetson: JetPack, kamera jalan via OpenCV, MediaPipe Pose terinstal & mendeteksi (CPU) | Skeleton tergambar di Jetson |
| 2 | Inti analisis Python (kalibrasi, tiga deteksi, smoothing, statistik) + Flask (MJPEG + WS) | Feedback real-time benar; terlihat di browser lokal |
| 3 | UI HTML/JS rapi (disajikan Flask), PostgreSQL + riwayat, pengingat 20-20-20, pengujian | Aplikasi utuh & nyaman dipakai |
| 4 | Autostart (opsional), laporan, dokumentasi, latihan demo, perbaikan | Dokumen submission + demo siap |

**Tonggak kritis:** akhir Minggu 1, kamera + MediaPipe harus sudah jalan di Jetson (ini bagian paling berisiko — kerjakan paling awal).

---

## 16. Pembagian Tugas (5 orang)

| Peran | Tanggung jawab |
|-------|----------------|
| Jetson & deployment | Setup JetPack, kamera, instalasi MediaPipe, autostart, profil daya/termal |
| Pipeline MediaPipe + OpenCV | Akuisisi frame, deteksi pose, gambar skeleton, MJPEG |
| Logika analisis Python | `PostureAnalyzer`: kalibrasi, deteksi, smoothing, tuning ambang (kontribusi teknis terbesar) |
| Backend Flask + PostgreSQL | API, WebSocket, skema & query DB, pengujian |
| Frontend (HTML/JS) + laporan | Halaman `index.html` + JS (live view, panel status, riwayat), integrasi, lab report, koordinasi demo |

Catatan: kontribusi individu memengaruhi nilai individu — dokumentasikan pembagiannya.

---

## 17. Rencana Pengujian

- **Unit test logika analisis:** beri pose palsu (tegak, menunduk, mata melebar, bahu miring) → pastikan status/peringatan benar.
- **Uji fungsional:** tiap fitur F1–F10 diuji dengan skenario nyata di Jetson.
- **Uji kalibrasi:** pengguna dengan tinggi/jarak berbeda → skor tetap adil.
- **Uji performa Jetson:** ukur fps & suhu selama sesi panjang; pastikan tidak *throttling*/crash.
- **Uji jaringan:** akses UI dari perangkat lain di jaringan lokal.

---

## 18. Risiko & Mitigasi

| Risiko | Dampak | Mitigasi |
|--------|--------|----------|
| **GPU MediaPipe di Jetson sulit** (tak ada wheel GPU resmi, sering jatuh ke CPU) | Waktu terbuang mengejar GPU | **Jalankan di CPU** untuk MVP; GPU hanya jika sempat. Pakai model *lite* & resolusi sedang |
| Instalasi MediaPipe di aarch64 gagal | Pipeline tak jalan | Coba `pip install mediapipe`; jika gagal untuk JetPack/Python kalian, pakai wheel komunitas aarch64 atau build dari source (lihat Bagian 19) |
| fps rendah di CPU | Demo tersendat | Turunkan resolusi, proses tiap-N frame, gunakan `jetson_clocks` |
| Termal *throttling* sesi panjang | Performa turun | Ventilasi/heatsink-fan; pantau suhu |
| Kamera tak terdeteksi | Tidak ada input | Utamakan webcam USB; verifikasi dengan `v4l2-ctl --list-devices` |
| Front camera tak melihat bungkuk samping sempurna | Akurasi terbatas | Pakai proksi (kepala turun) yang valid dari depan; jelaskan keterbatasan di laporan |
| Scope membengkak | Tidak selesai | Kunci MVP F1–F10 |

---

## 19. Panduan Deployment Jetson Orin Nano

**Langkah ringkas (urutan disarankan):**
1. **Flash JetPack** terbaru yang stabil untuk Orin Nano via NVIDIA SDK Manager; pastikan CUDA & OpenCV bawaan terpasang.
2. **Mode daya maksimal:** `sudo nvpmodel -m 0 && sudo jetson_clocks`.
3. **Verifikasi kamera:** colok webcam USB → `v4l2-ctl --list-devices`; uji ambil frame dengan OpenCV.
4. **Pasang MediaPipe (Python):**
   - Coba dulu jalur termudah: `pip install mediapipe` (beberapa versi menyediakan wheel `linux_aarch64` yang berjalan di CPU).
   - Jika tidak tersedia untuk kombinasi JetPack/Python kalian, gunakan **wheel aarch64 dari komunitas** (mis. repo PINTO0309 / jiuqiant / anion0278) atau **build dari source** mengikuti panduan Jetson. Catat: jalur GPU (delegate CUDA) rumit dan sering jatuh ke CPU — bukan target MVP.
5. **Backend + frontend:** `pip install flask flask-sock psycopg2-binary opencv-python` (OpenCV mungkin sudah ada dari JetPack — jangan timpa jika sudah berfungsi). Flask sekaligus menyajikan `index.html` + aset statis (folder `templates/` & `static/`).
6. **PostgreSQL:** `sudo apt install postgresql`; buat database & user; jalankan skema di Bagian 10.
7. **Frontend:** cukup taruh `index.html` + JS/CSS di folder statis Flask — **tidak perlu Node/npm atau build**. Akses via alamat IP Jetson di browser.
8. **Autostart (opsional, F13):** buat service `systemd` agar pipeline + Flask berjalan saat boot.

**Catatan versi:** kombinasi JetPack ↔ versi Python ↔ versi MediaPipe sangat menentukan keberhasilan instalasi. Catat versi yang berhasil di laporan — ini bagian "environment" yang diminta dokumen tugas.

---

## 20. Metrik Keberhasilan

- Tiga deteksi postur berfungsi benar pada ≥ 90% skenario uji.
- Berjalan stabil di Jetson sepanjang demo tanpa crash/throttling parah.
- fps cukup untuk terasa real-time (≥ ~12 fps) dan umpan balik < 500 ms.
- Riwayat sesi tersimpan di PostgreSQL & tampil benar di halaman web.
- Pengguna percobaan bisa memakai tanpa penjelasan tambahan.

---

## 21. Pemetaan ke Requirement Tugas

| Requirement Tugas | Cara Study Guardian memenuhinya |
|-------------------|-------------------------------|
| Berbasis MediaPipe | Inti deteksi memakai MediaPipe Pose Landmarker (Python, on-device) |
| Berjalan di perangkat embedded | Dijalankan di Jetson Orin Nano — sesuai contoh embedded di dokumen tugas |
| Aplikasi utuh & mudah dipakai | Perangkat menyala → memantau; UI web sederhana dengan panduan |
| Backend berbasis Python | Flask + seluruh deteksi & analisis di Python |
| Arsitektur (separasi opsional) | Monolitik: Flask menyajikan UI + API + video dalam satu proses. Dokumen tugas tidak mewajibkan separasi — ini sah & lebih simpel |
| User experience tinggi | Desain tenang, peringatan tidak mengganggu, autostart |
| Inovasi | Pemrosesan edge on-device tanpa cloud (privasi); ambang relatif berbasis kalibrasi |
| Tidak menyalin proyek | Logika & arsitektur dirancang sendiri, bukan klon repo |
| Kualitas > kuantitas | Lingkup MVP dikunci, fokus eksekusi rapi |

---

*Dokumen ini adalah PRD perencanaan Untuk submission akhir, isi konten relevan (fungsi, ide implementasi, tech stack, environment versi Jetson, pengujian, deployment).
