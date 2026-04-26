# 陶藝工坊 部署說明

## 一、GitHub 建立 repo

1. 去 github.com → New repository → 命名（例如 pottery-shop）
2. 在電腦終端機執行：

```bash
cd pottery-shop        # 進入這個專案資料夾
git init
git add .
git commit -m "init"
git remote add origin https://github.com/你的帳號/pottery-shop.git
git push -u origin main
```

---

## 二、Supabase 建表

1. supabase.com → 建立新專案
2. SQL Editor → 貼上 supabase_setup.sql → Run
3. Authentication → Users → Add user → 建立你的管理員帳號

---

## 三、Render 部署後端（免費）

1. render.com → 註冊 → New Web Service
2. 連接你的 GitHub repo
3. 設定：
   - **Root Directory**：`backend`
   - **Build Command**：`pip install -r requirements.txt`
   - **Start Command**：`uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Environment Variables 新增：

| 變數名稱 | 值 |
|---|---|
| `SUPABASE_URL` | Supabase Settings → API → Project URL |
| `SUPABASE_PUBLISHABLE_KEY` | Supabase Settings → API → Publishable key |
| `SUPABASE_SECRET_KEY` | Supabase Settings → API Keys → Secret key |
| `ADMIN_EMAIL` | 你的管理員 Email |
| `FRONTEND_URL` | 等 Vercel 部署完再填（先填 * 也可以） |

5. Deploy → 等待完成 → 複製你的後端網址（格式：https://pottery-shop-xxxx.onrender.com）

---

## 四、填入後端網址

打開 `frontend/index.html` 和 `frontend/admin.html`，找到最上面這行換掉：

```js
const API = 'https://你的後端名稱.onrender.com';
```

換成第三步得到的 Render 網址，然後再 git push 一次。

---

## 五、Vercel 部署前端（免費）

1. vercel.com → New Project → 選你的 GitHub repo
2. 設定：
   - **Root Directory**：`frontend`
3. Deploy → 完成！

---

## 六、更新 FRONTEND_URL

回到 Render → Environment Variables → 把 `FRONTEND_URL` 換成你的 Vercel 網址。

---

## 完成！

| 網址 | 說明 |
|---|---|
| `https://你的網址.vercel.app` | 消費者購物頁 |
| `https://你的網址.vercel.app/admin.html` | 管理後台 |

---

## 之後加 Line Pay

只需要：
1. 在 `backend/routers/` 新增 `linepay.py`
2. 在 `backend/main.py` 加一行 include_router
3. 在 `frontend/index.html` 的付款方式區塊加一個 Line Pay 選項

現有程式碼完全不需要動。
