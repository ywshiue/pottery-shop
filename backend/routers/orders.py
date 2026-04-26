from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
from database import sb_fetch, verify_admin_token

router = APIRouter()

class OrderItem(BaseModel):
    product_id: int
    product_name: str
    size: Optional[str] = ""
    qty: int
    unit_price: int

class OrderIn(BaseModel):
    customer_name: str
    customer_email: str
    customer_phone: str
    address: str
    payment_method: str
    note: Optional[str] = ""
    items: List[OrderItem]

# ── 公開：任何人都可以下單 ─────────────────────────────────
@router.post("/")
async def create_order(order: OrderIn):
    if not order.items:
        raise HTTPException(status_code=400, detail="購物車是空的")

    total = sum(i.qty * i.unit_price for i in order.items) + 100  # +運費

    # 建立訂單
    order_data = await sb_fetch("/orders", method="POST", body={
        "customer_name":  order.customer_name,
        "customer_email": order.customer_email,
        "customer_phone": order.customer_phone,
        "address":        order.address,
        "payment_method": order.payment_method,
        "total_amount":   total,
        "note":           order.note,
    })
    order_id = order_data[0]["id"]

    # 寫入訂單明細
    items_payload = [
        {
            "order_id":     order_id,
            "product_id":   i.product_id,
            "product_name": i.product_name,
            "size":         i.size,
            "qty":          i.qty,
            "unit_price":   i.unit_price,
        }
        for i in order.items
    ]
    await sb_fetch("/order_items", method="POST", body=items_payload)

    # 扣庫存
    for i in order.items:
        prod = await sb_fetch(f"/products?id=eq.{i.product_id}", use_secret=False)
        if prod:
            new_stock = max(0, prod[0]["stock"] - i.qty)
            await sb_fetch(f"/products?id=eq.{i.product_id}", method="PATCH", body={"stock": new_stock})

    return {"order_id": order_id, "total": total}

# ── 管理員才能看訂單 ───────────────────────────────────────
@router.get("/")
async def list_orders(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)

    orders = await sb_fetch("/orders?order=created_at.desc")
    items  = await sb_fetch("/order_items?order=order_id.asc")

    # 把訂單明細附加到每筆訂單
    for o in orders:
        o["items"] = [i for i in items if i["order_id"] == o["id"]]

    return orders

@router.patch("/{order_id}/status")
async def update_status(order_id: int, body: dict, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)

    valid = {"pending", "paid", "shipped", "completed", "cancelled"}
    status = body.get("status")
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"無效狀態，必須是：{valid}")

    await sb_fetch(f"/orders?id=eq.{order_id}", method="PATCH", body={"status": status})
    return {"message": "狀態已更新"}
