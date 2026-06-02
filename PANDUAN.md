# Panduan Penggunaan — Punch Trainer

Panduan langkah-demi-langkah menjalankan Study Guardian **Punch Trainer** (game
latihan tinju), dari nol sampai bisa bermain di browser. Ditujukan untuk **mesin
pengembangan (macOS)**; catatan khusus Jetson ada di bagian akhir.

> Ringkasan dokumen lain: [`README.md`](README.md) = ikhtisar proyek,
> [`PRD_Study_Guardian.md`](PRD_Study_Guardian.md) = perencanaan,
> [`CLAUDE.md`](CLAUDE.md) = panduan teknis untuk asisten coding.

---

## 0. Prasyarat

- **Python 3.10** (dipilih demi stabilitas MediaPipe). Mesin ini sudah punya
  via Homebrew di `/usr/local/opt/python@3.10/bin/python3.10`.
  Belum ada? Pasang: `brew install python@3.10`.
- **Webcam** + ruang gerak cukup agar bahu & kedua tangan terlihat saat memukul.
- **PostgreSQL** (sudah terpasang & berjalan di mesin ini). Opsional secara umum —
  aplikasi tetap jalan tanpanya, hanya riwayat & pengaturan tak tersimpan.

> **Kombinasi versi TERVERIFIKASI:** Python `3.10.20` · mediapipe `0.10.14` ·
> opencv-contrib-python `4.9.0.80` · numpy `1.26.4` · flask `3.1.3`.

---

## 1. Masuk ke folder proyek

```bash
cd /Users/mymac/Master_Degree/Semester_2/WebDevelopment/guardian
```

## 2. Virtual environment (venv) dengan Python 3.10

```bash
# Buat venv 3.10 (sekali saja)
/usr/local/opt/python@3.10/bin/python3.10 -m venv venv

# Aktifkan (tiap buka terminal baru) -> prompt jadi (venv)
source venv/bin/activate

python --version          # harus: Python 3.10.20
```

Keluar venv: `deactivate`. Bangun ulang: `rm -rf venv` lalu ulangi.

## 3. Pasang semua dependensi

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Memasang: `flask`, `flask-sock`, `psycopg2-binary`, `python-dotenv`, `numpy<2`,
**`opencv-contrib-python==4.9.0.80`**, **`mediapipe==0.10.14`** (plus dependensi).

> **Kenapa versi di-pin?** Tanpa pin, instalasi bisa macet lama (pip *backtracking*
> atau membangun OpenCV dari source / bentrok numpy). Detail di komentar
> [`requirements.txt`](requirements.txt).

Cek berhasil:
```bash
python -c "import mediapipe, cv2; print('mediapipe', mediapipe.__version__, '| opencv', cv2.__version__)"
```

## 3b. Model MediaPipe (Tasks API)

Aplikasi memakai **MediaPipe Pose Landmarker (Tasks API)** yang butuh berkas model.
Model lite **sudah disertakan** di [`models/pose_landmarker_lite.task`](models/)
(±5,5 MB). Bila hilang, unduh ulang:

```bash
curl -sSL -o models/pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

## 4. Konfigurasi `.env`

Berkas [`.env`](.env) sudah disiapkan. Bila berbeda, salin template:
`cp .env.example .env` lalu sesuaikan.

| Variabel | Default | Arti |
|----------|---------|------|
| `DB_HOST` | localhost | host PostgreSQL |
| `DB_PORT` | 5432 | port PostgreSQL |
| `DB_NAME` | study_guardian | nama database |
| `DB_USER` | mymac | user database |
| `DB_PASSWORD` | (sesuai `.env`) | password database |
| `CAMERA_INDEX` | 0 | index webcam (0 = default) |
| `POSE_MODEL_PATH` | models/pose_landmarker_lite.task | lokasi model (jarang diubah) |

## 5. Database (sudah disiapkan)

DB `study_guardian` + tabel `sessions` & `settings` **sudah dibuat** di mesin ini.
Untuk referensi / mesin lain:

```bash
brew install postgresql@16 && brew services start postgresql@16
createdb study_guardian
psql -d study_guardian -f schema.sql      # PERHATIAN: schema.sql me-reset tabel (DROP)
psql -d study_guardian -c "\dt"           # harus muncul: sessions, settings
```

---

## 6. Uji logika game (tanpa kamera)

```bash
python analysis.py
```
Harus menampilkan **`19 lulus, 0 gagal`**.

## 7. Jalankan aplikasi

```bash
python app.py
```

Yang terjadi:
- Kamera dinyalakan (macOS minta **izin akses kamera** pertama kali — izinkan).
- Status DB & pengaturan tercetak di terminal.
- Server menyala di **http://localhost:5000**.

Kamera bukan index 0? Jalankan: `CAMERA_INDEX=1 python app.py`.

---

## 8. Cara main

1. Tunggu **arena** (layar penuh, live view ber-skeleton) muncul. Status awal: *Tekan Play*.
2. Tekan **▶ Play** → **langsung mulai, tanpa kalibrasi**. Target 🥊 langsung muncul.
3. **Tinju cepat** ke arah target yang menyala — gerakkan tangan sampai (di video)
   **menutupi 🥊**. Poin **hanya masuk** bila pukulan:
   - **Cepat** (melewati ambang kecepatan), **dan**
   - **Lengan cukup lurus** (lalu ditarik kembali ke guard sebelum pukulan berikutnya), **dan**
   - **Kena zona** target.
4. **HIT** → toast "HIT! xKombo · kecepatan · reaksi", kombo & skor naik, target
   pindah. **MISS** (pelan/setengah/meleset) → tidak dapat poin, kombo putus.
5. HUD di atas video menampilkan **skor, kombo, waktu**.
6. Tekan **⏹ Stop** untuk berhenti. (Riwayat sengaja **tidak disimpan**.)

> Tips: kalau pukulan sah Anda tak terdeteksi, longgarkan ambang (turunkan
> `speed_min`/`extend_frac`) lewat API pengaturan di bawah. Kalau gerakan kecil pun
> terhitung, naikkan ambangnya.

---

## 9. Pengaturan sensitivitas (ambang) — opsional

Ambang game bisa dibaca/diubah via REST dan **tersimpan ke PostgreSQL** (dimuat
lagi otomatis saat aplikasi di-restart):

```bash
# Lihat ambang sekarang
curl http://localhost:5000/api/settings

# Ubah sebagian (yang lain tetap)
curl -X PUT http://localhost:5000/api/settings \
  -H "Content-Type: application/json" \
  -d '{"speed_min": 2.5, "target_radius": 0.16}'
```

| Kunci | Arti | Efek |
|-------|------|------|
| `speed_min` | kecepatan minimal pukulan | makin **besar** = makin sulit/menuntut pukulan cepat |
| `extend_frac` | ekstensi minimal (fraksi jangkauan) | makin **besar** = lengan harus lebih lurus |
| `target_radius` | radius zona target | makin **besar** = target lebih mudah dikenai |

---

## 10. Menghentikan & membersihkan

- Hentikan server: `Ctrl + C`.
- Keluar venv: `deactivate`.

---

## 11. Masalah umum (troubleshooting)

| Gejala | Penyebab & solusi |
|--------|-------------------|
| `python --version` bukan 3.10 | venv salah → `rm -rf venv` lalu ulangi langkah 2 dengan `/usr/local/opt/python@3.10/bin/python3.10`. |
| `ModuleNotFoundError: mediapipe` | venv belum aktif / dependensi belum dipasang → `source venv/bin/activate` lalu langkah 3. |
| `RuntimeError: Model tidak ditemukan` | Berkas model hilang → unduh ulang (§3b). |
| Live view hitam / "Kamera belum siap" | Izin kamera macOS belum diberikan, atau index salah → System Settings → Privacy → Camera; coba `CAMERA_INDEX=1`. |
| Pukulan tidak terhitung | Ambang terlalu ketat / fps rendah → turunkan `speed_min`/`extend_frac` (§9); pastikan tangan kembali ke posisi guard antar-pukulan (rearm), dan tangan menutupi 🥊 di video. |
| Target 🥊 tidak muncul | Belum tekan **▶ Play**, atau tubuh tak terlihat → tekan Play & pastikan bahu+tangan masuk frame. |
| `PostgreSQL TIDAK tersedia` | DB belum jalan → `brew services start postgresql@16`; cek `.env`. Aplikasi tetap jalan, riwayat tak tersimpan. |

---

## 12. Catatan untuk Jetson Orin Nano

1. Mode daya maksimal: `sudo nvpmodel -m 0 && sudo jetson_clocks`.
2. Verifikasi kamera: `v4l2-ctl --list-devices`.
3. MediaPipe di **CPU** (model *lite*, Tasks API). Pukulan cepat → jaga fps tinggi.
4. Salin `models/pose_landmarker_lite.task` ke perangkat (atau unduh ulang §3b).
5. **Jangan** pasang `opencv-contrib-python` via pip bila OpenCV JetPack sudah berfungsi.
6. Bila `pip install mediapipe` gagal di aarch64 → wheel komunitas / build dari
   source ([`PRD_Study_Guardian.md`](PRD_Study_Guardian.md) §19).
7. Catat kombinasi versi yang berhasil di [`README.md`](README.md).

Langkah 1–10 di atas sama; cukup ganti alamat akses ke `http://<IP_JETSON>:5000`.
