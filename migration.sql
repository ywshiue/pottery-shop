-- 在 Supabase SQL Editor 執行這個（已有資料不會遺失）

-- 1. 商品表加入多圖欄位
ALTER TABLE products ADD COLUMN IF NOT EXISTS image_urls TEXT[] DEFAULT '{}';

-- 把現有的 image_url 搬到 image_urls（如果有的話）
UPDATE products
SET image_urls = ARRAY[image_url]
WHERE image_url IS NOT NULL AND (image_urls IS NULL OR image_urls = '{}');

-- 2. 訂單表加入內部備註欄位
ALTER TABLE orders ADD COLUMN IF NOT EXISTS internal_note TEXT DEFAULT '';
