-- schema.sql — DDL PostgreSQL Study Guardian (Punch Trainer / latihan tinju)
-- Jalankan: psql -d study_guardian -f schema.sql
--
-- PERHATIAN: DROP di bawah menghapus tabel lama (termasuk skema postur lama).
-- Aman untuk dev; jalankan sekali saat setup/pivot.

DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS settings;

-- Riwayat sesi latihan tinju.
CREATE TABLE sessions (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    duration_sec    INTEGER,
    score           INTEGER,
    punches         INTEGER DEFAULT 0,   -- total pukulan sah dilempar
    hits            INTEGER DEFAULT 0,   -- pukulan yang kena target
    accuracy        INTEGER,             -- 0..100 (%)
    best_combo      INTEGER DEFAULT 0,
    best_speed      REAL,                -- m/s (estimasi)
    avg_reaction_ms INTEGER
);

-- Pengaturan ambang game (F11). Satu baris (id = 1).
CREATE TABLE settings (
    id            INTEGER PRIMARY KEY DEFAULT 1,
    speed_min     REAL DEFAULT 1.5,    -- kecepatan minimal pukulan (unit-layar/dtk)
    extend_frac   REAL DEFAULT 0.70,   -- ekstensi minimal (fraksi jangkauan kalibrasi)
    target_radius REAL DEFAULT 0.18    -- radius zona target (ternormalisasi)
);

INSERT INTO settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;
