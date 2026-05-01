from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import os, httpx
from database import sb_fetch, verify_admin_token

router = APIRouter()

# ── Models ────────────────────────────────────────────────
class ClassIn(BaseModel):
    type:        str
    name:        str
    date_desc:   Optional[str] = ""
    duration:    Optional[str] = ""
    price:       int
    price_note:  Optional[str] = ""
    capacity:    int
    location:    Optional[str] = ""
    description: Optional[str] = ""
    notes:       Optional[str] = ""
    is_active:   Optional[bool] = True
    image_url:        Optional[str] = ""
    image_urls:       Optional[list] = []
    subtitle:         Optional[str] = ""
    instructor_name:  Optional[str] = ""
    instructor_bio:   Optional[str] = ""
    instructor_photo: Optional[str] = ""

class RegistrationIn(BaseModel):
    class_id:       int
    name:           str
    phone:          str
    email:          str
    members:        Optional[int] = 1
    course_type:    Optional[str] = ""
    preferred_date: Optional[str] = ""
    note:           Optional[str] = ""

class PaymentConfirmReg(BaseModel):
    last5_digits: str

class RegStatusUpdate(BaseModel):
    status: str

# ── 公開：讀取課程 ────────────────────────────────────────
@router.get("/")
async def list_classes(type: Optional[str] = None):
    # Return ALL classes (active and inactive) so frontend can show "暫停報名"
    q = "/classes?order=created_at.asc"
    if type:
        q = f"/classes?type=eq.{type}&order=created_at.asc"
    return await sb_fetch(q, use_secret=False)

# ── 公開：報名 ────────────────────────────────────────────
@router.post("/register")
async def register(reg: RegistrationIn):
    # 確認課程存在且有名額
    classes = await sb_fetch(f"/classes?id=eq.{reg.class_id}", use_secret=False)
    if not classes:
        raise HTTPException(404, "找不到此課程")
    cls = classes[0]

    if not cls["is_active"]:
        raise HTTPException(400, "此課程目前不開放報名")

    members = reg.members or 1
    if cls["registered"] + members > cls["capacity"]:
        raise HTTPException(400, "報名人數已滿")

    # 計算費用
    total = cls["price"] * members

    # 建立報名記錄
    data = await sb_fetch("/registrations", method="POST", body={
        "class_id":      reg.class_id,
        "class_title":   cls.get("name", cls.get("title","")), 
        "name":          reg.name,
        "phone":         reg.phone,
        "email":         reg.email,
        "members":       members,
        "course_type":   reg.course_type,
        "preferred_date": reg.preferred_date,
        "note":          reg.note,
        "total_amount":  total,
    })
    reg_id = data[0]["id"]

    # 更新已報名人數（只更新專業課程）
    if cls.get("type") != "單次體驗":
        await sb_fetch(f"/classes?id=eq.{reg.class_id}", method="PATCH",
                       body={"registered": cls["registered"] + members})

    # 寄確認信給學員
    await send_reg_confirm(reg_id, reg, cls, total)

    return {"reg_id": reg_id, "total": total}

# ── 公開：學員確認匯款 ────────────────────────────────────
@router.post("/register/{reg_id}/payment")
async def confirm_reg_payment(reg_id: int, body: PaymentConfirmReg):
    if len(body.last5_digits) != 5 or not body.last5_digits.isdigit():
        raise HTTPException(400, "請填入正確的帳號後五碼")

    regs = await sb_fetch(f"/registrations?id=eq.{reg_id}")
    if not regs:
        raise HTTPException(404, "找不到報名記錄")

    await sb_fetch(f"/registrations?id=eq.{reg_id}", method="PATCH", body={
        "status": "paid",
        "payment_last5": body.last5_digits,
    })

    await send_payment_notify_reg(reg_id, regs[0], body.last5_digits)
    return {"message": "已收到匯款確認"}

# ── 公開：已預約日期與時段狀態 ───────────────────────────
@router.get("/debug-regs/{class_id}")
async def debug_regs(class_id: int):
    """Debug: show all registrations and their statuses"""
    regs = await sb_fetch(
        f"/registrations?class_id=eq.{class_id}&select=id,status,preferred_date,members,course_type",
        use_secret=False
    )
    return regs

@router.get("/booked-dates/{class_id}")
async def get_booked_dates(class_id: int):
    """
    回傳日期時段狀態與剩餘名額。
    capacity = 同天同時段上限人數。
    - 包場(group)預約某天 → 整天 fully_booked
    - 個人預約上午 → 這天只能繼續選上午(最多capacity人)，下午不能選，也不能包場
    - 個人預約下午 → 這天只能繼續選下午，上午不能選，也不能包場
    """
    from collections import defaultdict

    cls_info = await sb_fetch(f"/classes?id=eq.{class_id}&select=capacity", use_secret=False)
    MAX_PER_SLOT = cls_info[0]["capacity"] if cls_info else 4

    regs = await sb_fetch(
        f"/registrations?class_id=eq.{class_id}&status=neq.cancelled&select=preferred_date,members,course_type",
        use_secret=False
    )

    slots = defaultdict(lambda: {"morning": 0, "afternoon": 0, "has_group": False})

    for r in regs:
        pd = r.get("preferred_date", "") or ""
        if not pd:
            continue
        parts = pd.strip().split(" ")
        date_part = parts[0]
        time_part = parts[1] if len(parts) > 1 else ""
        members = int(r.get("members") or 1)
        course_type = r.get("course_type", "") or ""

        if course_type == "group":
            slots[date_part]["has_group"] = True
        elif "09:00" in time_part:
            slots[date_part]["morning"] += members
        elif "13:30" in time_part:
            slots[date_part]["afternoon"] += members

    result = {}
    for date, s in slots.items():
        morning = s["morning"]
        afternoon = s["afternoon"]
        has_group = s["has_group"]

        morning_rem = max(0, MAX_PER_SLOT - morning)
        afternoon_rem = max(0, MAX_PER_SLOT - afternoon)

        if has_group:
            status = "fully_booked"
        elif morning > 0 and afternoon > 0:
            # 上下午都有人 → 不能包場
            if morning_rem == 0 and afternoon_rem == 0:
                status = "fully_booked"
            elif morning_rem == 0:
                status = "afternoon_only"
            elif afternoon_rem == 0:
                status = "morning_only"
            else:
                status = "no_group"
        elif morning > 0:
            # 只有上午有人 → 只能選上午
            status = "fully_booked" if morning_rem == 0 else "morning_only"
        elif afternoon > 0:
            # 只有下午有人 → 只能選下午
            status = "fully_booked" if afternoon_rem == 0 else "afternoon_only"
        else:
            continue

        result[date] = {
            "status": status,
            "morning_remaining": morning_rem,
            "afternoon_remaining": afternoon_rem,
        }

    return result


@router.post("/register/{reg_id}/cancel")
async def cancel_registration(reg_id: int):
    regs = await sb_fetch(f"/registrations?id=eq.{reg_id}")
    if not regs:
        raise HTTPException(404, "找不到報名記錄")
    reg = regs[0]
    if reg["status"] in ("cancelled",):
        raise HTTPException(400, "此報名已取消")

    await sb_fetch(f"/registrations?id=eq.{reg_id}", method="PATCH",
                   body={"status": "cancelled"})

    # 恢復名額
    if reg["class_id"]:
        classes = await sb_fetch(f"/classes?id=eq.{reg['class_id']}")
        if classes:
            new_count = max(0, classes[0]["registered"] - (reg["members"] or 1))
            await sb_fetch(f"/classes?id=eq.{reg['class_id']}", method="PATCH",
                           body={"registered": new_count})

    await send_cancel_reg_email(reg)
    # Decrement registered count (only for 專業課程)
    cls_type_check = await sb_fetch(f"/classes?id=eq.{reg['class_id']}&select=registered,type", use_secret=True)
    if cls_type_check and cls_type_check[0].get("type") != "單次體驗":
        members = reg.get("members") or 1
        new_count = max(0, (cls_type_check[0].get("registered") or 0) - members)
        await sb_fetch(f"/classes?id=eq.{reg['class_id']}", method="PATCH", body={"registered": new_count})
    return {"message": "報名已取消"}

# ── 管理員：課程 CRUD ─────────────────────────────────────
@router.get("/admin/classes")
async def admin_list_classes(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    return await sb_fetch("/classes?order=created_at.desc")

@router.post("/admin/classes")
async def create_class(cls: ClassIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    body = cls.model_dump()
    if not body.get('image_urls'): body['image_urls'] = []
    data = await sb_fetch("/classes", method="POST", body=body)
    return data[0]

@router.patch("/admin/classes/{class_id}")
async def update_class(class_id: int, cls: ClassIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    body = cls.model_dump()
    if not body.get('image_urls'): body['image_urls'] = []
    await sb_fetch(f"/classes?id=eq.{class_id}", method="PATCH", body=body)
    return {"message": "已更新"}

@router.delete("/admin/classes/{class_id}")
async def delete_class(class_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/classes?id=eq.{class_id}", method="DELETE")
    return {"message": "已刪除"}

# ── 管理員：報名管理 ──────────────────────────────────────
@router.get("/admin/registrations")
async def admin_list_regs(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    return await sb_fetch("/registrations?order=created_at.desc")

@router.patch("/admin/registrations/{reg_id}")
async def update_reg(reg_id: int, body: RegStatusUpdate, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/registrations?id=eq.{reg_id}", method="PATCH",
                   body={"status": body.status})
    return {"message": "已更新"}

@router.delete("/admin/registrations/{reg_id}")
async def delete_reg(reg_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    # Get registration before deleting to update registered count
    regs = await sb_fetch(f"/registrations?id=eq.{reg_id}&select=class_id,members,status", use_secret=True)
    await sb_fetch(f"/registrations?id=eq.{reg_id}", method="DELETE")
    # Decrement registered count if not already cancelled (only for 專業課程)
    if regs and regs[0].get("status") != "cancelled":
        reg = regs[0]
        cls_check = await sb_fetch(f"/classes?id=eq.{reg['class_id']}&select=registered,type", use_secret=True)
        if cls_check and cls_check[0].get("type") != "單次體驗":
            members = reg.get("members") or 1
            new_count = max(0, (cls_check[0].get("registered") or 0) - members)
            await sb_fetch(f"/classes?id=eq.{reg['class_id']}", method="PATCH", body={"registered": new_count})
    return {"message": "已刪除"}

# ── 寄信 ─────────────────────────────────────────────────
BANK_INFO = lambda: {
    "name":    os.getenv("BANK_NAME", ""),
    "code":    os.getenv("BANK_CODE", ""),
    "account": os.getenv("BANK_ACCOUNT", ""),
}

async def send_reg_confirm(reg_id: int, reg: RegistrationIn, cls: dict, total: int):
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key: return
    bank = BANK_INFO()
    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:540px;margin:0 auto;background:#F5F2EE;padding:28px 24px;border-radius:12px">
      <h2 style="color:#2C4A6E;font-size:18px;margin:0 0 4px">是陶。課程報名確認</h2>
      <p style="color:#6B7280;font-size:13px;margin:0 0 20px">報名編號 <strong style="color:#1C2B3A">#{reg_id}</strong></p>
      <div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:14px">
        <p style="font-size:14px;color:#1C2B3A;line-height:1.9;margin:0">
          親愛的 {reg.name}，<br><br>
          我們已收到您報名 <strong>{cls.get('name', cls.get('title',''))}</strong> 的申請。<br>
          報名方式：<strong>{'包場' if reg.course_type == 'group' else '個人'}</strong>　人數：<strong>{reg.members or 1} 人</strong><br>
          {f'希望上課日期：<strong>{reg.preferred_date}</strong><br>' if reg.preferred_date else ''}
          請於 <strong>24 小時內完成匯款</strong>，逾期將自動取消報名。
        </p>
      </div>
      <div style="background:#E8EEF5;border:1px solid #B8D0E8;border-radius:10px;padding:16px 20px;margin-bottom:14px">
        <div style="font-size:11px;color:#2C4A6E;font-weight:600;letter-spacing:1px;margin-bottom:10px">匯款資訊</div>
        <table style="width:100%;font-size:13px;border-collapse:collapse">
          <tr><td style="padding:4px 0;color:#6B7280">銀行名稱</td><td style="text-align:right;font-weight:500">{bank['name']}</td></tr>
          <tr><td style="padding:4px 0;color:#6B7280">銀行代碼</td><td style="text-align:right;font-weight:500">{bank['code']}</td></tr>
          <tr style="border-top:1px solid #B8D0E8">
            <td style="padding:8px 0 4px;color:#6B7280">帳號</td>
            <td style="text-align:right;font-weight:700;color:#2C4A6E;font-size:15px">{bank['account']}</td>
          </tr>
          <tr style="border-top:1px solid #B8D0E8">
            <td style="padding:8px 0 4px;color:#6B7280">應匯金額</td>
            <td style="text-align:right;font-weight:700;color:#2C4A6E;font-size:15px">NT${total:,}</td>
          </tr>
        </table>
      </div>
      <p style="font-size:11px;color:#9CA3AF;text-align:center;line-height:1.8;margin:0">
        此信件為系統自動發送，請勿直接回覆<br>
        如有疑問請透過 Instagram @ywshiue 聯繫<br>
        是陶。It's Pottery
      </p>
    </div>"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": "是陶。<onboarding@resend.dev>", "to": [reg.email],
                      "subject": f"是陶。課程報名確認 #{reg_id}｜{cls.get('name', cls.get('title',''))}",
                      "html": html}, timeout=10)
    except Exception: pass

async def send_payment_notify_reg(reg_id: int, reg: dict, last5: str):
    api_key     = os.getenv("RESEND_API_KEY")
    admin_email = os.getenv("ADMIN_EMAIL")
    if not api_key or not admin_email: return
    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F5F2EE;padding:28px 24px;border-radius:12px">
      <h2 style="color:#2C4A6E;font-size:18px;margin:0 0 16px">💰 是陶。課程報名匯款通知</h2>
      <div style="background:#E8EEF5;border:1px solid #B8D0E8;border-radius:10px;padding:16px 20px;margin-bottom:14px">
        <p style="font-size:13px;color:#6B7280;margin:0 0 6px">帳號後五碼：<strong style="color:#2C4A6E;font-size:18px;letter-spacing:3px">{last5}</strong></p>
        <p style="font-size:13px;color:#6B7280;margin:0">應收金額：<strong>NT${reg['total_amount']:,}</strong></p>
      </div>
      <div style="background:#fff;border-radius:10px;padding:14px 20px;margin-bottom:14px;font-size:13px;color:#4B5563;line-height:1.8">
        <strong>{reg['name']}</strong> · {reg['phone']}<br>
        {reg['email']}<br>
        課程：{reg['class_title']}
        {f"<br>堂數：{reg['course_type']}" if reg.get('course_type') else ''}
        {f"<br>希望日期：{reg['preferred_date']}" if reg.get('preferred_date') else ''}
        {f"<br>人數：{reg['members']}" if reg.get('members') else ''}
      </div>
      <a href="https://pottery-shop-alpha.vercel.app/admin.html"
         style="display:block;text-align:center;background:#2C4A6E;color:#fff;padding:11px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600">
        前往後台確認
      </a>
      <p style="font-size:11px;color:#9CA3AF;text-align:center;margin-top:14px">是陶。It's Pottery</p>
    </div>"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": "是陶。<onboarding@resend.dev>", "to": [admin_email],
                      "subject": f"是陶。課程匯款 #{reg_id}｜{reg['name']}｜後五碼 {last5}",
                      "html": html}, timeout=10)
    except Exception: pass

async def send_cancel_reg_email(reg: dict):
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key or not reg.get("email"): return
    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F5F2EE;padding:28px 24px;border-radius:12px">
      <h2 style="color:#8B6F47;font-size:18px;margin:0 0 16px">是陶。課程報名已取消</h2>
      <div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px">
        <p style="font-size:14px;color:#1C2B3A;line-height:1.9;margin:0">
          親愛的 {reg.get('name', '')}，<br><br>
          您的課程報名 <strong>#{reg['id']}</strong>（{reg.get('class_title','')}）已成功取消。<br>
          如有疑問請透過 Instagram @ywshiue 聯繫。
        </p>
      </div>
      <p style="font-size:11px;color:#9CA3AF;text-align:center;line-height:1.8;margin:0">
        此信件為系統自動發送，請勿直接回覆<br>是陶。It's Pottery
      </p>
    </div>"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": "是陶。<onboarding@resend.dev>", "to": [reg["email"]],
                      "subject": f"是陶。課程報名 #{reg['id']} 已取消",
                      "html": html}, timeout=10)
    except Exception: pass


# ── 公開：讀取頁面設定 ────────────────────────────────────
@router.get("/settings")
async def get_settings():
    data = await sb_fetch("/class_settings?order=key.asc", use_secret=False)
    return {item["key"]: item["value"] for item in data}

@router.get("/photos")
async def get_photos():
    data = await sb_fetch("/class_photos?order=sort_order.asc", use_secret=False)
    return data

# ── 管理員：更新設定 ──────────────────────────────────────
class SettingIn(BaseModel):
    key:   str
    value: str

@router.patch("/admin/settings")
async def update_setting(body: SettingIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    # upsert
    await sb_fetch(
        f"/class_settings?key=eq.{body.key}",
        method="PATCH",
        body={"value": body.value}
    )
    return {"message": "已更新"}

# ── 管理員：照片 CRUD ─────────────────────────────────────
class PhotoIn(BaseModel):
    category:   str
    url:        str
    sort_order: Optional[int] = 0

@router.get("/admin/photos")
async def admin_get_photos(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    return await sb_fetch("/class_photos?order=sort_order.asc")

@router.post("/admin/photos")
async def add_photo(body: PhotoIn, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    data = await sb_fetch("/class_photos", method="POST", body=body.model_dump())
    return data[0]

@router.delete("/admin/photos/{photo_id}")
async def delete_photo(photo_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/class_photos?id=eq.{photo_id}", method="DELETE")
    return {"message": "已刪除"}
