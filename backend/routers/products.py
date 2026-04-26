from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
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

# ── 公開：任何人都可以讀取商品 ─────────────────────────────
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
    data = await sb_fetch("/products", method="POST", body=product.model_dump())
    return data[0] if data else {}

@router.patch("/{product_id}")
async def update_product(product_id: int, product: ProductIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    data = await sb_fetch(f"/products?id=eq.{product_id}", method="PATCH", body=product.model_dump(exclude_none=True))
    return data[0] if data else {}

@router.delete("/{product_id}")
async def delete_product(product_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/products?id=eq.{product_id}", method="DELETE")
    return {"message": "已刪除"}
