# Panduan Penggunaan — Study Guardian

Panduan langkah-demi-langkah menjalankan Study Guardian, dari nol sampai bisa
memantau postur di browser. Ditujukan untuk **mesin pengembangan (macOS)**;
catatan khusus Jetson ada di bagian akhir.

> Ringkasan dokumen lain: [`README.md`](README.md) = ikhtisar proyek,
> [`PRD_Study_Guardian.md`](PRD_Study_Guardian.md) = perencanaan,
> [`CLAUDE.md`](CLAUDE.md) = panduan teknis untuk asisten coding.

---

## 0. Prasyarat

- **Python 3.10** (dipilih demi stabilitas MediaPipe). Mesin ini sudah punya
  via Homebrew di `/usr/local/opt/python@3.10/bin/python3.10`.
  Belum ada? Pasang: `brew install python@3.10`.
- **Webcam** (bawaan laptop sudah cukup).
- **PostgreSQL** (sudah terpasang & berjalan di mesin ini). Opsional secara
  umum — aplikasi tetap jalan tanpanya, hanya riwayat & pengaturan tak tersimpan.

> **Kombinasi versi yang TERVERIFIKASI** (catat untuk laporan environment):
> Python `3.10.20` · mediapipe `0.10.14` · opencv-contrib-python `4.9.0.80` ·
> numpy `1.26.4` · flask `3.1.3`.

---

## 1. Masuk ke folder proyek

```bash
cd /Users/mymac/Master_Degree/Semester_2/WebDevelopment/guardian
```

## 2. Virtual environment (venv) dengan Python 3.10

venv mengisolasi paket proyek agar tidak mencampuri Python sistem (yang 3.12).
**Penting:** buat venv memakai Python 3.10, bukan `python3` sistem.

```bash
# Buat venv 3.10 (sekali saja)
/usr/local/opt/python@3.10/bin/python3.10 -m venv venv

# Aktifkan (tiap buka terminal baru) -> prompt jadi (venv)
source venv/bin/activate

# Pastikan benar 3.10
python --version          # harus: Python 3.10.20
```

Untuk keluar nanti: `deactivate`.

> Bila perlu membangun ulang dari nol: `rm -rf venv` lalu ulangi langkah di atas.

## 3. Pasang semua dependensi

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Memasang: `flask`, `flask-sock`, `psycopg2-binary`, `python-dotenv`, `numpy<2`,
**`opencv-contrib-python==4.9.0.80`**, **`mediapipe==0.10.14`** (plus dependensi
mediapipe seperti jax, matplotlib, protobuf).

> **Kenapa versi di-pin?** Tanpa pin, instalasi bisa macet lama:
> - `mediapipe` tanpa versi → pip *backtracking* (unduh puluhan versi).
> - `opencv-contrib-python` terbaru tak punya wheel (compile dari source) /
>   memaksa `numpy>=2` yang bentrok dengan mediapipe. Versi `4.9.0.80` aman.
>
> Detail alasan ada di komentar dalam [`requirements.txt`](requirements.txt).

Cek MediaPipe & OpenCV berhasil:

```bash
python -c "import mediapipe, cv2; print('mediapipe', mediapipe.__version__, '| opencv', cv2.__version__)"
```

## 3b. Model MediaPipe (Tasks API)

Aplikasi memakai **MediaPipe Pose Landmarker (Tasks API)** yang butuh berkas
model. Model lite **sudah disertakan** di
[`models/pose_landmarker_lite.task`](models/) (±5,5 MB), jadi biasanya tak perlu
apa-apa. Bila hilang, unduh ulang:

```bash
curl -sSL -o models/pose_landmarker_lite.task \
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task
```

## 4. Konfigurasi `.env`

Berkas [`.env`](.env) sudah disiapkan untuk mesin ini. Bila berbeda, salin
template dan sesuaikan:

```bash
cp .env.example .env   # lalu edit kredensial DB / CAMERA_INDEX
```

Variabel yang dibaca:

| Variabel | Default | Arti |
|----------|---------|------|
| `DB_HOST` | localhost | host PostgreSQL |
| `DB_PORT` | 5432 | port PostgreSQL |
| `DB_NAME` | study_guardian | nama database |
| `DB_USER` | mymac | user database |
| `DB_PASSWORD` | (sesuai `.env`) | password database |
| `CAMERA_INDEX` | 0 | index webcam (0 = default) |
| `POSE_MODEL_PATH` | models/pose_landmarker_lite.task | lokasi model (jarang diubah) |

> Catatan macOS + Homebrew: PostgreSQL lokal umumnya pakai autentikasi *trust*,
> sehingga nilai `DB_PASSWORD` boleh apa saja (diabaikan) selama koneksi lokal.

## 5. Database (sudah disiapkan)

Di mesin ini DB `study_guardian` + tabel `sessions` & `settings` **sudah dibuat**.
Untuk referensi / mesin lain:

```bash
brew install postgresql@16
brew services start postgresql@16
createdb study_guardian
psql -d study_guardian -f schema.sql
```

Verifikasi tabel:

```bash
psql -d study_guardian -c "\dt"     # harus muncul: sessions, settings
```

---

## 6. Uji logika analisis (tanpa kamera)

Cara cepat memastikan inti perhitungan benar — tidak butuh kamera/DB:

```bash
python analysis.py
```

Harus menampilkan **`17 lulus, 0 gagal`**.

## 7. Jalankan aplikasi

```bash
python app.py
```

Yang terjadi:
- Kamera dinyalakan (macOS minta **izin akses kamera** pertama kali — izinkan).
- Di terminal muncul status DB & pengaturan:
  - `PostgreSQL terhubung — riwayat sesi akan disimpan.` lalu
    `Pengaturan ambang dimuat dari DB: {…}` (DB aktif), atau
  - `PostgreSQL TIDAK tersedia — aplikasi tetap jalan, …` (tanpa DB).
- Server menyala di **http://localhost:5000**.

Buka alamat itu di browser (Chrome/Edge disarankan).

Kamera bukan index 0? Jalankan: `CAMERA_INDEX=1 python app.py`.

---

## 8. Cara memakai di browser

1. Tunggu **live view** (video ber-skeleton) muncul. Status awal: *Perlu Kalibrasi*.
2. **Duduk tegak** senyaman mungkin sebagai postur ideal Anda.
3. Tekan tombol **Kalibrasi** → sistem menyimpan baseline tubuh Anda
   (muncul toast "Kalibrasi berhasil").
4. Setelah itu status berubah otomatis:
   - 🟢 **Postur Baik**
   - 🟡 **Perlu Diperbaiki** + **toast** peringatan (membungkuk / terlalu dekat /
     miring) yang hanya muncul saat postur baru memburuk (tidak spam).
5. Panel kanan: **skor postur** (cincin), **durasi**, rincian **event**, dan
   **grafik tren** skor antar-sesi.
6. Tiap 20 menit muncul pengingat **istirahat 20-20-20**.
7. Tekan **Akhiri Sesi** untuk menyimpan ringkasan ke riwayat (butuh DB aktif).
8. **Riwayat & grafik** memperbarui otomatis setelah sesi disimpan.

> Tips demo: pengingat istirahat default 20 menit. Untuk mendemokannya cepat,
> kecilkan `BREAK_INTERVAL_SEC` di [`analysis.py`](analysis.py) (mis. `20`),
> atau ubah lewat API pengaturan di bawah.

---

## 9. Pengaturan sensitivitas (ambang) — opsional

Ambang deteksi bisa dibaca/diubah via REST dan **tersimpan ke PostgreSQL**
(dimuat lagi otomatis saat aplikasi di-restart):

```bash
# Lihat ambang sekarang
curl http://localhost:5000/api/settings

# Ubah sebagian ambang (yang lain tetap). Nama kunci: slouch_ratio, close_ratio,
# tilt_degrees, break_interval.
curl -X PUT http://localhost:5000/api/settings \
  -H "Content-Type: application/json" \
  -d '{"tilt_degrees": 12, "break_interval": 600}'
```

> Arti ambang (relatif ke baseline kalibrasi): `slouch_ratio` makin **besar**
> = makin sensitif terhadap membungkuk; `close_ratio` makin **kecil** = makin
> sensitif terhadap wajah mendekat; `tilt_degrees` makin **kecil** = makin
> sensitif terhadap miring; `break_interval` = detik antar pengingat istirahat.

---

## 10. Menghentikan & membersihkan

- Hentikan server: `Ctrl + C` di terminal.
- Keluar venv: `deactivate`.

---

## 11. Masalah umum (troubleshooting)

| Gejala | Penyebab & solusi |
|--------|-------------------|
| `python --version` bukan 3.10 | venv dibuat dari Python salah → `rm -rf venv` lalu ulangi langkah 2 dengan `/usr/local/opt/python@3.10/bin/python3.10`. |
| `ModuleNotFoundError: mediapipe` | Dependensi belum dipasang / venv belum aktif → `source venv/bin/activate` lalu langkah 3. |
| `RuntimeError: Model tidak ditemukan` | Berkas model hilang → unduh ulang (lihat §3b). |
| Live view hitam / "Kamera belum siap" | Izin kamera macOS belum diberikan, atau index salah → System Settings → Privacy → Camera; coba `CAMERA_INDEX=1`. |
| Tombol Kalibrasi gagal ("Pose tidak terdeteksi") | Wajah & bahu harus terlihat penuh di frame; perbaiki pencahayaan & posisi. |
| `PostgreSQL TIDAK tersedia` | DB belum jalan → `brew services start postgresql@16`; cek `.env`. Aplikasi tetap jalan, hanya riwayat/pengaturan tak tersimpan. |
| `pip install` macet lama / unduh berulang | Pola *backtracking* — pastikan pakai `requirements.txt` yang sudah di-pin (jangan lepas pin `mediapipe`/`opencv-contrib-python`). |

---

## 12. Catatan untuk Jetson Orin Nano

Di Jetson, **jangan** pasang `opencv-contrib-python`/`opencv-python` lewat pip
bila OpenCV bawaan JetPack sudah berfungsi (CLAUDE.md §9). Langkah ringkas:

1. Mode daya maksimal: `sudo nvpmodel -m 0 && sudo jetson_clocks`.
2. Verifikasi kamera: `v4l2-ctl --list-devices`.
3. MediaPipe dijalankan di **CPU** (model *lite*, Tasks API) — GPU bukan target MVP.
4. Model `models/pose_landmarker_lite.task` ikut serta; salin ke perangkat
   (atau unduh ulang seperti §3b).
5. Bila `pip install mediapipe` gagal di aarch64, pakai wheel komunitas atau
   build dari source (lihat [`PRD_Study_Guardian.md`](PRD_Study_Guardian.md) §19).
6. Catat kombinasi versi yang berhasil (JetPack ↔ Python ↔ mediapipe) di
   [`README.md`](README.md) — diminta sebagai bagian "environment".

Langkah 1–10 di atas sama; cukup ganti alamat akses ke `http://<IP_JETSON>:5000`
agar bisa dibuka dari perangkat lain di jaringan yang sama.
