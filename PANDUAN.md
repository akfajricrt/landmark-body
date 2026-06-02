# Panduan Penggunaan — Study Guardian

Panduan langkah-demi-langkah menjalankan Study Guardian, dari nol sampai bisa
memantau postur di browser. Ditujukan untuk **mesin pengembangan (macOS)**;
catatan khusus Jetson ada di bagian akhir.

> Ringkasan dokumen lain: [`README.md`](README.md) = ikhtisar proyek,
> [`PRD_Study_Guardian.md`](PRD_Study_Guardian.md) = perencanaan,
> [`CLAUDE.md`](CLAUDE.md) = panduan teknis untuk asisten coding.

---

## 0. Prasyarat

- **Python 3.9–3.12** (mesin ini: 3.12 ✓). Cek: `python3 --version`.
- **Webcam** (bawaan laptop sudah cukup).
- **PostgreSQL** (opsional — aplikasi tetap jalan tanpanya, hanya riwayat tak tersimpan).

---

## 1. Masuk ke folder proyek

```bash
cd /Users/mymac/Master_Degree/Semester_2/WebDevelopment/guardian
```

## 2. Virtual environment (venv)

venv mengisolasi paket proyek agar tidak mencampuri Python sistem.

```bash
python3 -m venv venv      # buat sekali saja
source venv/bin/activate  # aktifkan tiap buka terminal baru -> prompt jadi (venv)
```

Untuk keluar nanti: `deactivate`.

## 3. Pasang semua dependensi

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Ini memasang: `flask`, `flask-sock`, `psycopg2-binary`, `python-dotenv`,
`opencv-python`, **`mediapipe`**. Unduhan MediaPipe + OpenCV cukup besar
(beberapa menit). **MediaPipe terpasang di langkah ini** — sebelumnya belum ada.

Cek MediaPipe berhasil:

```bash
python -c "import mediapipe, cv2; print('mediapipe', mediapipe.__version__, '| opencv', cv2.__version__)"
```

## 4. Konfigurasi `.env`

Berkas [`.env`](.env) sudah disiapkan untuk mesin ini (PostgreSQL brew: user
`mymac`, tanpa password, database `study_guardian`). Bila berbeda, salin
template dan sesuaikan:

```bash
cp .env.example .env   # lalu edit DB_USER / DB_PASSWORD / CAMERA_INDEX
```

Variabel yang dibaca:

| Variabel | Default | Arti |
|----------|---------|------|
| `DB_HOST` | localhost | host PostgreSQL |
| `DB_PORT` | 5432 | port PostgreSQL |
| `DB_NAME` | study_guardian | nama database |
| `DB_USER` | mymac | user database |
| `DB_PASSWORD` | (kosong) | password database |
| `CAMERA_INDEX` | 0 | index webcam (0 = default) |

## 5. Siapkan database (opsional, untuk riwayat sesi)

> Lewati bagian ini jika hanya ingin mencoba live view + kalibrasi.

PostgreSQL via Homebrew:

```bash
brew install postgresql@16
brew services start postgresql@16
createdb study_guardian
psql -d study_guardian -f schema.sql
```

Verifikasi tabel terbuat:

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
- Di terminal muncul status DB:
  - `PostgreSQL terhubung — riwayat sesi akan disimpan.` (DB aktif), atau
  - `PostgreSQL TIDAK tersedia — aplikasi tetap jalan, riwayat tidak tersimpan.`
- Server menyala di **http://localhost:5000**.

Buka alamat itu di browser (Chrome/Edge disarankan).

Kamera bukan index 0? Jalankan: `CAMERA_INDEX=1 python app.py`.

---

## 8. Cara memakai di browser

1. Tunggu **live view** (video ber-skeleton) muncul. Status awal: *Perlu Kalibrasi*.
2. **Duduk tegak** senyaman mungkin sebagai postur ideal Anda.
3. Tekan tombol **Kalibrasi** → sistem menyimpan baseline tubuh Anda.
4. Setelah itu status berubah otomatis:
   - 🟢 **Postur Baik**
   - 🟡 **Perlu Diperbaiki** + daftar peringatan (membungkuk / terlalu dekat / miring).
5. Panel kanan menampilkan **skor postur**, **durasi**, jumlah **event**, dan metrik langsung.
6. Tiap 20 menit muncul pengingat **istirahat 20-20-20**.
7. Tekan **Akhiri Sesi** untuk menyimpan ringkasan ke riwayat (butuh DB aktif).
8. **Riwayat Sesi** di panel kanan menampilkan sesi-sesi sebelumnya.

> Tips demo: pengingat istirahat default 20 menit. Untuk mendemokannya cepat,
> kecilkan `BREAK_INTERVAL_SEC` di [`analysis.py`](analysis.py) (mis. `20`).

---

## 9. Menghentikan & membersihkan

- Hentikan server: `Ctrl + C` di terminal.
- Keluar venv: `deactivate`.

---

## 10. Masalah umum (troubleshooting)

| Gejala | Penyebab & solusi |
|--------|-------------------|
| `ModuleNotFoundError: mediapipe` | Dependensi belum dipasang → ulangi langkah 3 (`pip install -r requirements.txt`) di dalam venv. |
| Live view hitam / "Kamera belum siap" | Izin kamera macOS belum diberikan, atau index salah → cek System Settings → Privacy → Camera; coba `CAMERA_INDEX=1`. |
| Tombol Kalibrasi gagal ("Pose tidak terdeteksi") | Wajah & bahu harus terlihat penuh di frame; perbaiki pencahayaan & posisi. |
| `PostgreSQL TIDAK tersedia` | DB belum jalan/salah kredensial → `brew services start postgresql@16`, cek `.env`. Aplikasi tetap jalan, hanya riwayat tak tersimpan. |
| `pip install mediapipe` gagal | Pastikan `pip` terbaru (`pip install --upgrade pip`); bila perlu pin versi: `pip install mediapipe==0.10.14`. |

---

## 11. Catatan untuk Jetson Orin Nano

Di Jetson, **jangan** pasang `opencv-python` lewat pip bila OpenCV bawaan
JetPack sudah berfungsi (CLAUDE.md §9). Langkah ringkas:

1. Mode daya maksimal: `sudo nvpmodel -m 0 && sudo jetson_clocks`.
2. Verifikasi kamera: `v4l2-ctl --list-devices`.
3. MediaPipe dijalankan di **CPU** (model *lite*) — GPU bukan target MVP.
4. Bila `pip install mediapipe` gagal di aarch64, pakai wheel komunitas atau
   build dari source (lihat [`PRD_Study_Guardian.md`](PRD_Study_Guardian.md) §19).
5. Catat kombinasi versi yang berhasil (JetPack ↔ Python ↔ mediapipe) di
   [`README.md`](README.md) — diminta sebagai bagian "environment".

Langkah 1–9 di atas sama; cukup ganti alamat akses ke `http://<IP_JETSON>:5000`
agar bisa dibuka dari perangkat lain di jaringan yang sama.
