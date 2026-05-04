import os
import time
from collections import defaultdict
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from routers import products, orders, upload, auth, questions, classes

load_dotenv()

app = FastAPI(title="陶藝工坊 API")

# ── CORS ──────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://pottery-shop-alpha.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# ── Rate Limiting (login brute-force protection) ──────────
_login_attempts: dict = defaultdict(list)
LOGIN_MAX = 10        # max attempts
LOGIN_WINDOW = 300    # per 5 minutes

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.url.path == "/auth/login" and request.method == "POST":
        ip = request.client.host
        now = time.time()
        attempts = _login_attempts[ip]
        # Remove old attempts outside window
        attempts[:] = [t for t in attempts if now - t < LOGIN_WINDOW]
        if len(attempts) >= LOGIN_MAX:
            return JSONResponse(
                status_code=429,
                content={"detail": "登入嘗試次數過多，請 5 分鐘後再試"}
            )
        attempts.append(now)
    return await call_next(request)

# ── Security headers ──────────────────────────────────────
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

# ── Routes ────────────────────────────────────────────────
app.include_router(auth.router,      prefix="/auth",      tags=["auth"])
app.include_router(products.router,  prefix="/products",  tags=["products"])
app.include_router(orders.router,    prefix="/orders",    tags=["orders"])
app.include_router(upload.router,    prefix="/upload",    tags=["upload"])
app.include_router(questions.router, prefix="/questions", tags=["questions"])
app.include_router(classes.router,   prefix="/classes",   tags=["classes"])

@app.get("/")
def root():
    return {"status": "ok", "message": "陶藝工坊 API 運作中"}

@app.get("/bank-info")
def bank_info():
    return {
        "bank_name":    os.getenv("BANK_NAME",    ""),
        "bank_code":    os.getenv("BANK_CODE",    ""),
        "bank_account": os.getenv("BANK_ACCOUNT", ""),
        "bank_holder":  os.getenv("BANK_HOLDER",  ""),
    }
