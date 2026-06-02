"""
db.py — Akses PostgreSQL untuk riwayat & pengaturan game tinju Study Guardian.

Konfigurasi koneksi lewat environment variable (punya default lokal):
    DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

Desain tahan-gagal: bila PostgreSQL tidak tersedia, fungsi-fungsi di sini
TIDAK membuat aplikasi crash — penyimpanan dilewati dan riwayat dikembalikan
kosong, sehingga demo tetap jalan tanpa DB.
"""

import os

# Muat variabel dari berkas .env bila ada (opsional — tidak wajib).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
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
    "password": os.environ.get("DB_PASSWORD", "postgres"),
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
    """Simpan satu sesi latihan. `stats` adalah hasil PunchStats.to_dict().
    Mengembalikan id sesi, atau None bila gagal/DB tak tersedia."""
    if not _PSYCOPG_OK:
        print("[db] psycopg2 tidak terpasang — sesi tidak disimpan.")
        return None
    try:
        conn = _connect()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions
                    (started_at, ended_at, duration_sec, score, punches, hits,
                     accuracy, best_combo, best_speed, avg_reaction_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    started_at,
                    ended_at,
                    stats.get("elapsed_sec"),
                    stats.get("score"),
                    stats.get("punches", 0),
                    stats.get("hits", 0),
                    stats.get("accuracy"),
                    stats.get("best_combo", 0),
                    stats.get("best_speed"),
                    stats.get("avg_reaction_ms"),
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
                SELECT id, started_at, ended_at, duration_sec, score, punches,
                       hits, accuracy, best_combo, best_speed, avg_reaction_ms
                FROM sessions
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.close()
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
    {speed_min, extend_frac, target_radius} atau None bila DB tak tersedia."""
    if not _PSYCOPG_OK:
        return None
    try:
        conn = _connect()
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT speed_min, extend_frac, target_radius FROM settings WHERE id = 1"
            )
            row = cur.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:  # noqa: BLE001
        print(f"[db] Gagal mengambil settings: {e}")
        return None


def save_settings(settings):
    """Simpan (upsert) pengaturan ke baris settings (id=1). `settings` dict
    dengan kunci speed_min, extend_frac, target_radius. True bila tersimpan."""
    if not _PSYCOPG_OK:
        return False
    try:
        conn = _connect()
        with conn, conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO settings (id, speed_min, extend_frac, target_radius)
                VALUES (1, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    speed_min     = EXCLUDED.speed_min,
                    extend_frac   = EXCLUDED.extend_frac,
                    target_radius = EXCLUDED.target_radius
                """,
                (
                    settings.get("speed_min"),
                    settings.get("extend_frac"),
                    settings.get("target_radius"),
                ),
            )
        conn.close()
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[db] Gagal menyimpan settings: {e}")
        return False
