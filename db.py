"""
db.py — Akses PostgreSQL untuk riwayat sesi Study Guardian.

Konfigurasi koneksi lewat environment variable (punya default lokal):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

Desain tahan-gagal: bila PostgreSQL tidak tersedia, fungsi-fungsi di sini
TIDAK membuat aplikasi crash (CLAUDE.md §10) — penyimpanan dilewati dan
riwayat dikembalikan kosong, sehingga demo tetap jalan tanpa DB.
"""

import os

# Muat variabel dari berkas .env bila ada (opsional — tidak wajib).
# Dilakukan di awal agar DB_CONFIG di bawah membaca nilai dari .env.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # python-dotenv belum terpasang → pakai env/ default saja
    pass

try:
    import psycopg2
    import psycopg2.extras
    _PSYCOPG_OK = True
except ImportError:  # psycopg2 belum terpasang (mis. mesin dev)
    _PSYCOPG_OK = False

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5432"),
    "dbname": os.environ.get("DB_NAME", "study_guardian"),
    "user": os.environ.get("DB_USER", "mymac"),
    "password": os.environ.get("DB_PASSWORD", "password"),
}


def is_available():
    """True bila psycopg2 ada dan koneksi berhasil dibuka."""
    if not _PSYCOPG_OK:
        return False
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        return True
    except Exception as e:  # noqa: BLE001 — sengaja luas; demo tak boleh crash
        print(f"[db] PostgreSQL tidak tersedia: {e}")
        return False


def _connect():
    return psycopg2.connect(**DB_CONFIG)


def save_session(started_at, ended_at, stats):
    """Simpan satu sesi. `stats` adalah hasil PostureStats.to_dict()
    (kunci close_events sudah cocok dengan kolom DB). Mengembalikan id sesi,
    atau None bila gagal/DB tak tersedia."""
    if not _PSYCOPG_OK:
        print("[db] psycopg2 tidak terpasang — sesi tidak disimpan.")
        return None
    try:
        conn = _connect()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions
                    (started_at, ended_at, duration_sec, posture_score,
                     slouch_events, close_events, tilt_events)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    started_at,
                    ended_at,
                    stats.get("elapsed_sec"),
                    stats.get("posture_score"),
                    stats.get("slouch_events", 0),
                    stats.get("close_events", 0),   # pemetaan nama §7
                    stats.get("tilt_events", 0),
                ),
            )
            session_id = cur.fetchone()[0]
        conn.close()
        return session_id
    except Exception as e:  # noqa: BLE001
        print(f"[db] Gagal menyimpan sesi: {e}")
        return None


def get_history(limit=20):
    """Daftar sesi terakhir (list of dict) untuk GET /api/history.
    Mengembalikan list kosong bila DB tak tersedia."""
    if not _PSYCOPG_OK:
        return []
    try:
        conn = _connect()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, started_at, ended_at, duration_sec, posture_score,
                       slouch_events, close_events, tilt_events
                FROM sessions
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.close()
        # Serialkan timestamp ke ISO agar aman di-JSON-kan.
        result = []
        for r in rows:
            d = dict(r)
            for k in ("started_at", "ended_at"):
                if d.get(k) is not None:
                    d[k] = d[k].isoformat()
            result.append(d)
        return result
    except Exception as e:  # noqa: BLE001
        print(f"[db] Gagal mengambil riwayat: {e}")
        return []


def get_settings():
    """Ambil pengaturan ambang dari baris settings (id=1). Mengembalikan dict
    {slouch_ratio, close_ratio, tilt_degrees, break_interval} atau None bila
    DB tak tersedia / baris belum ada. Catatan nama: kolom DB 'close_ratio'
    dipetakan ke analyzer.too_close_ratio di app.py."""
    if not _PSYCOPG_OK:
        return None
    try:
        conn = _connect()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT slouch_ratio, close_ratio, tilt_degrees, break_interval
                FROM settings WHERE id = 1
                """
            )
            row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        print(f"[db] Gagal mengambil settings: {e}")
        return None


def save_settings(settings):
    """Simpan (upsert) pengaturan ke baris settings (id=1). `settings` adalah
    dict dengan kunci slouch_ratio, close_ratio, tilt_degrees, break_interval.
    Mengembalikan True bila tersimpan, False bila gagal/DB tak tersedia."""
    if not _PSYCOPG_OK:
        return False
    try:
        conn = _connect()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings
                    (id, slouch_ratio, close_ratio, tilt_degrees, break_interval)
                VALUES (1, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    slouch_ratio   = EXCLUDED.slouch_ratio,
                    close_ratio    = EXCLUDED.close_ratio,
                    tilt_degrees   = EXCLUDED.tilt_degrees,
                    break_interval = EXCLUDED.break_interval
                """,
                (
                    settings.get("slouch_ratio"),
                    settings.get("close_ratio"),
                    settings.get("tilt_degrees"),
                    settings.get("break_interval"),
                ),
            )
        conn.close()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[db] Gagal menyimpan settings: {e}")
        return False
