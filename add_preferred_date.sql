-- 在 registrations 資料表加入 preferred_date 欄位
ALTER TABLE registrations ADD COLUMN IF NOT EXISTS preferred_date TEXT DEFAULT '';
