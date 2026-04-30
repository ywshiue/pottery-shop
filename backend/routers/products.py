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
    image_url: Optional[str] = None
    image_urls: Optional[List[str]] = []
    series_id: Optional[int] = None
    series_name: Optional[str] = "" 

# ── 公開：任何人可以讀 ─────────────────────────────────────
@router.get("/")
async def list_products(category: Optional[str] = None, series_name: Optional[str] = None):
    q = "/products?order=created_at.desc"
    if category:
        q += f"&category=eq.{category}"
    if series_name:
        q += f"&series_name=eq.{series_name}"
    return await sb_fetch(q, use_secret=False)

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


# ── 系列 ──────────────────────────────────────────────────
@router.get("/series")
async def list_series():
    return await sb_fetch("/series?order=name.asc", use_secret=False)

class SeriesIn(BaseModel):
    name: str

@router.post("/series")
async def create_series(body: SeriesIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    existing = await sb_fetch(f"/series?name=eq.{body.name}", use_secret=False)
    if existing:
        return existing[0]
    data = await sb_fetch("/series", method="POST", body={"name": body.name})
    return data[0]

@router.delete("/series/{series_id}")
async def delete_series(series_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/series?id=eq.{series_id}", method="DELETE")
    return {"message": "已刪除"}
