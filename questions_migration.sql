-- 消費者提問表
CREATE TABLE questions (
  id          BIGSERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  email       TEXT NOT NULL,
  question    TEXT NOT NULL,
  answer      TEXT,
  is_public   BOOLEAN DEFAULT false,
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  answered_at TIMESTAMPTZ
);

ALTER TABLE questions ENABLE ROW LEVEL SECURITY;

-- 任何人可以提問
CREATE POLICY "anyone can insert questions"
  ON questions FOR INSERT WITH CHECK (true);

-- 任何人可以看公開的問答
CREATE POLICY "public read answered questions"
  ON questions FOR SELECT USING (is_public = true);

-- service_role 可以看全部、回覆
CREATE POLICY "admin all questions"
  ON questions FOR ALL USING (true) WITH CHECK (true);
