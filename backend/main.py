import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from routers import products, orders, upload, auth, questions, classes

load_dotenv()

app = FastAPI(title="陶藝工坊 API")

# CORS — 允許前端網站呼叫
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
    expose_headers=["*"],
)

# 路由
app.include_router(auth.router,     prefix="/auth",     tags=["auth"])
app.include_router(products.router, prefix="/products", tags=["products"])
app.include_router(orders.router,   prefix="/orders",   tags=["orders"])
app.include_router(upload.router,    prefix="/upload",    tags=["upload"])
app.include_router(questions.router, prefix="/questions", tags=["questions"])
app.include_router(classes.router,   prefix="/classes",   tags=["classes"])

# 之後加 Line Pay 只需要新增這一行：
# from routers import linepay
# app.include_router(linepay.router, prefix="/pay", tags=["pay"])

@app.get("/")
def root():
    return {"status": "ok", "message": "陶藝工坊 API 運作中"}

@app.get("/bank-info")
def bank_info():
    """回傳銀行匯款資訊（從環境變數取得）"""
    import os
    return {
        "bank_name":    os.getenv("BANK_NAME",    ""),
        "bank_code":    os.getenv("BANK_CODE",    ""),
        "bank_account": os.getenv("BANK_ACCOUNT", ""),
        "bank_holder":  os.getenv("BANK_HOLDER",  ""),
    }
