-- 若已執行過舊版 classes_migration.sql，執行這個 alter 版本
-- 若還沒執行過，直接執行這個完整版

-- 完整建立（全新）
CREATE TABLE IF NOT EXISTS classes (
  id            BIGSERIAL PRIMARY KEY,
  type          TEXT NOT NULL DEFAULT '',
  name          TEXT NOT NULL DEFAULT '',
  date_desc     TEXT DEFAULT '',
  duration      TEXT DEFAULT '',
  price         INTEGER NOT NULL DEFAULT 0,
  price_note    TEXT DEFAULT '',
  capacity      INTEGER NOT NULL DEFAULT 4,
  registered    INTEGER DEFAULT 0,
  location      TEXT DEFAULT '',
  description   TEXT DEFAULT '',
  notes         TEXT DEFAULT '',
  is_active     BOOLEAN DEFAULT true,
  image_url     TEXT DEFAULT '',
  image_urls    TEXT[] DEFAULT '{}',
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS registrations (
  id            BIGSERIAL PRIMARY KEY,
  class_id      INTEGER REFERENCES classes(id) ON DELETE SET NULL,
  class_title   TEXT NOT NULL DEFAULT '',
  name          TEXT NOT NULL DEFAULT '',
  phone         TEXT NOT NULL DEFAULT '',
  email         TEXT NOT NULL DEFAULT '',
  members       INTEGER DEFAULT 1,
  course_type   TEXT DEFAULT '',
  note          TEXT DEFAULT '',
  status        TEXT DEFAULT 'pending',
  payment_last5 TEXT DEFAULT '',
  total_amount  INTEGER DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 若舊表已存在，補上缺少的欄位
ALTER TABLE classes ADD COLUMN IF NOT EXISTS name TEXT NOT NULL DEFAULT '';
ALTER TABLE classes ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE classes ADD COLUMN IF NOT EXISTS image_url TEXT DEFAULT '';
ALTER TABLE classes ADD COLUMN IF NOT EXISTS image_urls TEXT[] DEFAULT '{}';
-- 把舊 title 欄位資料搬到 name（若存在）
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='classes' AND column_name='title') THEN
    UPDATE classes SET name = title WHERE name = '';
  END IF;
END $$;

-- RLS
ALTER TABLE classes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE registrations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "public read active classes" ON classes;
DROP POLICY IF EXISTS "anyone can register"         ON registrations;
DROP POLICY IF EXISTS "admin all classes"           ON classes;
DROP POLICY IF EXISTS "admin all registrations"     ON registrations;

CREATE POLICY "public read active classes"
  ON classes FOR SELECT USING (is_active = true);

CREATE POLICY "anyone can register"
  ON registrations FOR INSERT WITH CHECK (true);

CREATE POLICY "admin all classes"
  ON classes FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "admin all registrations"
  ON registrations FOR ALL USING (true) WITH CHECK (true);
