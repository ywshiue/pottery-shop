-- ============================================================
--  陶藝工坊 — Supabase SQL 初始化
--  在 Supabase Dashboard → SQL Editor 貼上執行一次
-- ============================================================

CREATE TABLE products (
  id          BIGSERIAL PRIMARY KEY,
  name        TEXT NOT NULL,
  category    TEXT NOT NULL,
  price       INT  NOT NULL,
  stock       INT  NOT NULL DEFAULT 0,
  sizes       TEXT,
  image_url   TEXT,
  description TEXT,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE orders (
  id             BIGSERIAL PRIMARY KEY,
  customer_name  TEXT NOT NULL,
  customer_email TEXT NOT NULL,
  customer_phone TEXT NOT NULL,
  address        TEXT NOT NULL,
  payment_method TEXT NOT NULL,
  total_amount   INT  NOT NULL,
  status         TEXT NOT NULL DEFAULT 'pending',
  note           TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE order_items (
  id           BIGSERIAL PRIMARY KEY,
  order_id     BIGINT REFERENCES orders(id) ON DELETE CASCADE,
  product_id   BIGINT REFERENCES products(id),
  product_name TEXT NOT NULL,
  size         TEXT,
  qty          INT  NOT NULL,
  unit_price   INT  NOT NULL
);

-- Storage bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('products', 'products', true)
ON CONFLICT DO NOTHING;

-- RLS
ALTER TABLE products    ENABLE ROW LEVEL SECURITY;
ALTER TABLE orders      ENABLE ROW LEVEL SECURITY;
ALTER TABLE order_items ENABLE ROW LEVEL SECURITY;

CREATE POLICY "anyone can read products"    ON products    FOR SELECT USING (true);
CREATE POLICY "anyone can insert orders"    ON orders      FOR INSERT WITH CHECK (true);
CREATE POLICY "anyone can insert items"     ON order_items FOR INSERT WITH CHECK (true);
CREATE POLICY "service role all products"   ON products    FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service role all orders"     ON orders      FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "service role all items"      ON order_items FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "public read images"          ON storage.objects FOR SELECT USING (bucket_id = 'products');
CREATE POLICY "service role upload images"  ON storage.objects FOR INSERT WITH CHECK (bucket_id = 'products');
CREATE POLICY "service role delete images"  ON storage.objects FOR DELETE USING (bucket_id = 'products');
