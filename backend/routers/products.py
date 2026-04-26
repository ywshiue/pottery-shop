from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
from database import sb_fetch, verify_admin_token

router = APIRouter()

class ProductIn(BaseModel):
    name: str
    category: str
    price: int
    stock: int
    sizes: Optional[str] = ""
    description: Optional[str] = ""
    image_url: Optional[str] = None       # 主圖（第一張，向下相容）
    image_urls: Optional[List[str]] = []  # 多張圖片

# ── 公開：任何人可以讀 ─────────────────────────────────────
@router.get("/")
async def list_products(category: Optional[str] = None):
    if category:
        data = await sb_fetch(f"/products?category=eq.{category}&order=created_at.desc", use_secret=False)
    else:
        data = await sb_fetch("/products?order=created_at.desc", use_secret=False)
    return data

@router.get("/{product_id}")
async def get_product(product_id: int):
    data = await sb_fetch(f"/products?id=eq.{product_id}", use_secret=False)
    if not data:
        raise HTTPException(status_code=404, detail="找不到商品")
    return data[0]

# ── 管理員才能新增/修改/刪除 ───────────────────────────────
@router.post("/")
async def create_product(product: ProductIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    payload = product.model_dump()
    # 主圖自動帶第一張
    if product.image_urls:
        payload["image_url"] = product.image_urls[0]
    data = await sb_fetch("/products", method="POST", body=payload)
    return data[0] if data else {}

@router.patch("/{product_id}")
async def update_product(product_id: int, product: ProductIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    payload = product.model_dump(exclude_none=True)
    if product.image_urls:
        payload["image_url"] = product.image_urls[0]
    data = await sb_fetch(f"/products?id=eq.{product_id}", method="PATCH", body=payload)
    return data[0] if data else {}

@router.delete("/{product_id}")
async def delete_product(product_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    # 只封存（stock 設 0），不真正刪除，保留訂單歷史
    await sb_fetch(f"/products?id=eq.{product_id}", method="PATCH", body={"stock": 0})
    return {"message": "已封存（庫存設為 0）"}

@router.delete("/{product_id}/permanent")
async def permanent_delete(product_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/products?id=eq.{product_id}", method="DELETE")
    return {"message": "已永久刪除"}
