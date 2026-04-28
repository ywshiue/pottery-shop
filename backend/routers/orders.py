from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, List
from database import sb_fetch, verify_admin_token
import os, httpx

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

class StatusUpdate(BaseModel):
    status: str
    internal_note: Optional[str] = None

VALID_STATUS = {"pending", "confirmed", "shipped", "completed", "cancelled"}

# ── 寄信（Resend）────────────────────────────────────────────
async def send_order_email(order_id: int, order: OrderIn, total: int):
    """有新訂單時寄 Email 通知給店家"""
    api_key = os.getenv("RESEND_API_KEY")
    admin_email = os.getenv("ADMIN_EMAIL")
    if not api_key or not admin_email:
        return  # 沒設定就跳過，不影響下單流程

    items_html = "".join([
        f"<tr><td style='padding:6px 12px;border-bottom:1px solid #E0DCD5'>{i.product_name}"
        f"{'（'+i.size+'）' if i.size else ''}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #E0DCD5;text-align:center'>{i.qty}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #E0DCD5;text-align:right'>NT${i.unit_price * i.qty:,}</td></tr>"
        for i in order.items
    ])

    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:560px;margin:0 auto;background:#F5F2EE;padding:32px 24px;border-radius:12px">
      <h2 style="color:#2C4A6E;font-size:20px;margin:0 0 4px">是陶。新訂單通知</h2>
      <p style="color:#6B7280;font-size:13px;margin:0 0 24px">訂單編號 <strong style="color:#1C2B3A">#{order_id}</strong></p>

      <div style="background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:16px">
        <div style="font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:.8px;margin-bottom:10px">顧客資料</div>
        <p style="margin:0 0 4px;font-size:14px"><strong>{order.customer_name}</strong></p>
        <p style="margin:0 0 4px;font-size:13px;color:#4B5563">📞 {order.customer_phone}</p>
        <p style="margin:0 0 4px;font-size:13px;color:#4B5563">✉️ {order.customer_email}</p>
        <p style="margin:0;font-size:13px;color:#4B5563">📍 {order.address}</p>
        {f'<p style="margin:8px 0 0;font-size:12px;color:#6B7280">備註：{order.note}</p>' if order.note else ''}
      </div>

      <div style="background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:16px">
        <div style="font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:.8px;margin-bottom:10px">訂購商品</div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <thead>
            <tr style="background:#F5F2EE">
              <th style="padding:6px 12px;text-align:left;font-weight:600;color:#6B7280">商品</th>
              <th style="padding:6px 12px;text-align:center;font-weight:600;color:#6B7280">數量</th>
              <th style="padding:6px 12px;text-align:right;font-weight:600;color:#6B7280">小計</th>
            </tr>
          </thead>
          <tbody>{items_html}</tbody>
        </table>
        <div style="display:flex;justify-content:space-between;padding:10px 12px 0;font-size:13px;color:#6B7280">
          <span>運費</span><span>NT$160</span>
        </div>
        <div style="display:flex;justify-content:space-between;padding:8px 12px 0;font-size:15px;font-weight:700;color:#2C4A6E;border-top:1px solid #E0DCD5;margin-top:8px">
          <span>合計</span><span>NT${total:,}</span>
        </div>
      </div>

      <div style="background:#fff;border-radius:10px;padding:14px 20px;margin-bottom:24px">
        <div style="font-size:12px;color:#6B7280;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px">付款方式</div>
        <p style="margin:0;font-size:14px;color:#1C2B3A">{order.payment_method}</p>
      </div>

      <a href="https://pottery-shop-alpha.vercel.app/admin.html"
         style="display:block;text-align:center;background:#2C4A6E;color:#fff;padding:12px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;letter-spacing:.5px">
        前往後台查看訂單
      </a>
      <p style="text-align:center;font-size:11px;color:#9CA3AF;margin-top:16px">是陶。 · It's Pottery</p>
    </div>
    """

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "是陶。<onboarding@resend.dev>",
                    "to": [admin_email],
                    "subject": f"是陶。新訂單 #{order_id}｜{order.customer_name}",
                    "html": html,
                },
                timeout=10,
            )
    except Exception:
        pass  # 寄信失敗不影響下單


async def send_customer_email(order_id: int, order: OrderIn, total: int):
    """下單後寄給消費者：告知已收到訂單，確認匯款後出貨"""
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return

    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:560px;margin:0 auto;background:#F5F2EE;padding:32px 24px;border-radius:12px">
      <h2 style="color:#2C4A6E;font-size:20px;margin:0 0 4px">是陶。訂單已收到</h2>
      <p style="color:#6B7280;font-size:13px;margin:0 0 24px">訂單編號 <strong style="color:#1C2B3A">#{order_id}</strong></p>

      <div style="background:#fff;border-radius:10px;padding:18px 20px;margin-bottom:20px">
        <p style="margin:0;font-size:14px;color:#1C2B3A;line-height:1.9">
          親愛的 {order.customer_name}，<br><br>
          我們已收到您的訂單，感謝您對是陶。的支持。<br>
          確認收到匯款後，將盡快為您安排出貨。<br><br>
          如有任何疑問，歡迎透過 Instagram @ywshiue 與我們聯繫。
        </p>
      </div>

      <p style="font-size:11px;color:#9CA3AF;text-align:center;line-height:1.8;margin:0;border-top:1px solid #E0DCD5;padding-top:16px">
        此信件為系統自動發送，請勿直接回覆<br>
        是陶。It's Pottery
      </p>
    </div>
    """

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "是陶。<onboarding@resend.dev>",
                    "to": [order.customer_email],
                    "subject": f"是陶。已收到您的訂單 #{order_id}",
                    "html": html,
                },
                timeout=10,
            )
    except Exception:
        pass

# ── 公開：任何人可以下單 ───────────────────────────────────
@router.post("/")
async def create_order(order: OrderIn):
    if not order.items:
        raise HTTPException(status_code=400, detail="購物車是空的")

    total = sum(i.qty * i.unit_price for i in order.items) + 160

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

    # 只寄確認信給消費者（告知匯款資訊）
    await send_customer_email(order_id, order, total)

    return {"order_id": order_id, "total": total}

# ── 管理員才能看/更新訂單 ──────────────────────────────────
@router.get("/")
async def list_orders(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    orders = await sb_fetch("/orders?order=created_at.desc")
    items  = await sb_fetch("/order_items?order=order_id.asc")
    for o in orders:
        o["items"] = [i for i in items if i["order_id"] == o["id"]]
    return orders

@router.patch("/{order_id}")
async def update_order(order_id: int, body: StatusUpdate, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    if body.status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"無效狀態")
    payload = {"status": body.status}
    if body.internal_note is not None:
        payload["internal_note"] = body.internal_note
    await sb_fetch(f"/orders?id=eq.{order_id}", method="PATCH", body=payload)
    return {"message": "訂單已更新"}


class PaymentConfirm(BaseModel):
    last5_digits: str

@router.post("/{order_id}/payment")
async def confirm_payment(order_id: int, body: PaymentConfirm):
    """消費者填入後五碼，系統自動寄通知信給店家"""
    if len(body.last5_digits) != 5 or not body.last5_digits.isdigit():
        raise HTTPException(status_code=400, detail="請填入正確的帳號後五碼")

    # 更新訂單狀態為 paid + 記錄後五碼
    await sb_fetch(f"/orders?id=eq.{order_id}", method="PATCH", body={
        "status": "paid",
        "internal_note": f"消費者匯款帳號後五碼：{body.last5_digits}"
    })

    # 撈訂單資訊
    orders = await sb_fetch(f"/orders?id=eq.{order_id}")
    if not orders:
        raise HTTPException(status_code=404, detail="找不到訂單")
    order = orders[0]

    # 撈訂單明細
    items = await sb_fetch(f"/order_items?order_id=eq.{order_id}")

    # 寄通知信給店家
    await send_payment_notify(order_id, order, items, body.last5_digits)

    return {"message": "已收到匯款確認"}


async def send_payment_notify(order_id: int, order: dict, items: list, last5: str):
    """消費者完成匯款後，寄通知信給店家"""
    api_key = os.getenv("RESEND_API_KEY")
    admin_email = os.getenv("ADMIN_EMAIL")
    if not api_key or not admin_email:
        return

    items_html = "".join([
        f"<tr><td style='padding:6px 12px;border-bottom:1px solid #E0DCD5'>{i['product_name']}"
        f"{'（'+i['size']+'）' if i.get('size') else ''} ×{i['qty']}</td>"
        f"<td style='padding:6px 12px;border-bottom:1px solid #E0DCD5;text-align:right'>NT${i['unit_price']*i['qty']:,}</td></tr>"
        for i in items
    ])

    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:560px;margin:0 auto;background:#F5F2EE;padding:32px 24px;border-radius:12px">
      <h2 style="color:#2C4A6E;font-size:20px;margin:0 0 4px">💰 是陶。收到匯款通知</h2>
      <p style="color:#6B7280;font-size:13px;margin:0 0 20px">訂單 <strong style="color:#1C2B3A">#{order_id}</strong> 消費者已完成匯款</p>

      <div style="background:#E8EEF5;border:1px solid #B8D0E8;border-radius:10px;padding:16px 20px;margin-bottom:16px">
        <div style="font-size:12px;color:#2C4A6E;font-weight:600;letter-spacing:.8px;margin-bottom:10px">匯款資訊</div>
        <div style="display:flex;justify-content:space-between;font-size:14px">
          <span style="color:#6B7280">帳號後五碼</span>
          <span style="font-weight:700;color:#2C4A6E;font-size:18px;letter-spacing:3px">{last5}</span>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:14px;margin-top:8px">
          <span style="color:#6B7280">應收金額</span>
          <span style="font-weight:700;color:#2C4A6E">NT${order['total_amount']:,}</span>
        </div>
      </div>

      <div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px">
        <div style="font-size:12px;color:#6B7280;letter-spacing:.8px;margin-bottom:10px">顧客資料</div>
        <p style="margin:0 0 4px;font-size:14px"><strong>{order['customer_name']}</strong></p>
        <p style="margin:0 0 4px;font-size:13px;color:#4B5563">📞 {order['customer_phone']}</p>
        <p style="margin:0 0 4px;font-size:13px;color:#4B5563">✉️ {order['customer_email']}</p>
        <p style="margin:0;font-size:13px;color:#4B5563">📍 {order['address']}</p>
      </div>

      <div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:20px">
        <div style="font-size:12px;color:#6B7280;letter-spacing:.8px;margin-bottom:10px">訂購商品</div>
        <table style="width:100%;border-collapse:collapse;font-size:13px">
          <tbody>{items_html}</tbody>
        </table>
        <div style="display:flex;justify-content:space-between;padding:8px 12px 0;font-size:15px;font-weight:700;color:#2C4A6E;border-top:1px solid #E0DCD5;margin-top:8px">
          <span>合計</span><span>NT${order['total_amount']:,}</span>
        </div>
      </div>

      <a href="https://pottery-shop-alpha.vercel.app/admin.html"
         style="display:block;text-align:center;background:#2C4A6E;color:#fff;padding:12px;border-radius:8px;text-decoration:none;font-size:14px;font-weight:600;letter-spacing:.5px">
        前往後台確認並出貨
      </a>
      <p style="text-align:center;font-size:11px;color:#9CA3AF;margin-top:16px">是陶。· It's Pottery</p>
    </div>
    """

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "from": "是陶。<onboarding@resend.dev>",
                    "to": [admin_email],
                    "subject": f"💰 是陶。收到匯款 #{order_id}｜後五碼 {last5}",
                    "html": html,
                },
                timeout=10,
            )
    except Exception:
        pass


@router.delete("/{order_id}")
async def delete_order(order_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/order_items?order_id=eq.{order_id}", method="DELETE")
    await sb_fetch(f"/orders?id=eq.{order_id}", method="DELETE")
    return {"message": "訂單已刪除"}


class CancelRequest(BaseModel):
    pass

@router.post("/{order_id}/cancel")
async def cancel_order_by_customer(order_id: int):
    """消費者主動取消訂單，恢復庫存並寄通知信"""
    # 用 secret key 讀取（允許消費者查詢自己的訂單）
    orders = await sb_fetch(f"/orders?id=eq.{order_id}")
    if not orders:
        raise HTTPException(status_code=404, detail="找不到訂單")

    order = orders[0]
    # 允許 pending / paid / confirmed 都可以取消
    if order["status"] in ("shipped", "completed", "cancelled"):
        raise HTTPException(status_code=400, detail="此訂單無法取消")

    # 更新狀態
    await sb_fetch(f"/orders?id=eq.{order_id}", method="PATCH", body={"status": "cancelled"})

    # 恢復庫存
    items = await sb_fetch(f"/order_items?order_id=eq.{order_id}")
    for item in items:
        pid = item.get("product_id")
        if not pid:
            continue
        prod = await sb_fetch(f"/products?id=eq.{pid}", use_secret=False)
        if prod:
            new_stock = prod[0]["stock"] + item["qty"]
            await sb_fetch(f"/products?id=eq.{pid}", method="PATCH", body={"stock": new_stock})

    # 寄取消通知信給消費者
    await send_cancel_email(order)

    return {"message": "訂單已取消"}


async def send_cancel_email(order: dict):
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key or not order.get("customer_email"):
        return

    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F5F2EE;padding:28px 24px;border-radius:12px">
      <h2 style="color:#8B6F47;font-size:18px;margin:0 0 16px">是陶。訂單已取消</h2>
      <div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px">
        <p style="font-size:14px;color:#1C2B3A;line-height:1.9;margin:0">
          親愛的 {order.get('customer_name', '')}，<br><br>
          您的訂單 <strong>#{order['id']}</strong> 已成功取消。<br>
          如有任何疑問，歡迎透過 Instagram @ywshiue 與我們聯繫。
        </p>
      </div>
      <p style="font-size:11px;color:#9CA3AF;text-align:center;line-height:1.8;margin:0">
        此信件為系統自動發送，請勿直接回覆<br>
        是陶。It's Pottery
      </p>
    </div>"""

    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "from": "是陶。<onboarding@resend.dev>",
                    "to": [order["customer_email"]],
                    "subject": f"是陶。訂單 #{order['id']} 已取消",
                    "html": html,
                },
                timeout=10,
            )
    except Exception:
        pass
