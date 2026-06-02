-- schema.sql — DDL PostgreSQL Study Guardian (CLAUDE.md §7 / PRD §10)
-- Jalankan: psql -U postgres -d study_guardian -f schema.sql

-- Riwayat sesi belajar. Catatan pemetaan nama: analysis.py memakai
-- too_close_events, sedangkan kolom di sini bernama close_events
-- (pemetaan dilakukan di db.py saat menyimpan).
CREATE TABLE IF NOT EXISTS sessions (
    id             SERIAL PRIMARY KEY,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    duration_sec   INTEGER,
    posture_score  INTEGER,          -- 0..100, % waktu postur baik
    slouch_events  INTEGER DEFAULT 0,
    close_events   INTEGER DEFAULT 0,
    tilt_events    INTEGER DEFAULT 0
);

-- Opsional (F11): pengaturan ambang tersimpan. Satu baris (id = 1).
CREATE TABLE IF NOT EXISTS settings (
    id              INTEGER PRIMARY KEY DEFAULT 1,
    slouch_ratio    REAL DEFAULT 0.82,
    close_ratio     REAL DEFAULT 1.22,
    tilt_degrees    REAL DEFAULT 9.0,
    break_interval  INTEGER DEFAULT 1200   -- detik (20 menit)
);

INSERT INTO settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
