from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import os, httpx
from database import sb_fetch, verify_admin_token

router = APIRouter()

class QuestionIn(BaseModel):
    email:    str
    question: str

class AnswerIn(BaseModel):
    answer: str

def mask_email(email: str) -> str:
    """a***@gmail.com 格式"""
    if '@' not in email:
        return email
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        return f"{local}***@{domain}"
    return f"{local[0]}***@{domain}"

# ── 公開：任何人可以提問 ───────────────────────────────────
@router.post("/")
async def submit_question(q: QuestionIn):
    if not q.email or not q.question:
        raise HTTPException(400, "請填寫所有欄位")

    data = await sb_fetch("/questions", method="POST", body={
        "email":    q.email,
        "question": q.question,
    })

    # 通知店家
    await notify_admin(q)
    return {"message": "已送出問題"}

# ── 公開：取得所有已回覆的問答 ────────────────────────────
@router.get("/public")
async def get_public_questions():
    data = await sb_fetch(
        "/questions?answer=not.is.null&order=created_at.desc",
        use_secret=False
    )
    # 遮蔽 email
    for q in data:
        q["display_name"] = mask_email(q.get("email", ""))
        del q["email"]
    return data

# ── 管理員：取得所有提問 ──────────────────────────────────
@router.get("/")
async def get_all_questions(authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    return await sb_fetch("/questions?order=created_at.desc")

# ── 管理員：回覆問題 ──────────────────────────────────────
@router.patch("/{question_id}")
async def answer_question(
    question_id: int,
    body: AnswerIn,
    authorization: str = Header(...)
):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)

    if not body.answer.strip():
        raise HTTPException(400, "回覆內容不能為空")

    # 撈原始問題取得 email
    questions = await sb_fetch(f"/questions?id=eq.{question_id}")
    if not questions:
        raise HTTPException(404, "找不到此問題")

    await sb_fetch(f"/questions?id=eq.{question_id}", method="PATCH", body={
        "answer":      body.answer,
        "answered_at": "now()",
    })

    # 寄回覆通知給消費者
    await notify_customer(questions[0], body.answer)
    return {"message": "已回覆"}

# ── 管理員：刪除問題 ──────────────────────────────────────
@router.delete("/{question_id}")
async def delete_question(question_id: int, authorization: str = Header(...)):
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)
    await sb_fetch(f"/questions?id=eq.{question_id}", method="DELETE")
    return {"message": "已刪除"}

# ── 寄信 ──────────────────────────────────────────────────
async def notify_admin(q: QuestionIn):
    api_key     = os.getenv("RESEND_API_KEY")
    admin_email = os.getenv("ADMIN_EMAIL")
    if not api_key or not admin_email:
        return
    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F5F2EE;padding:28px 24px;border-radius:12px">
      <h2 style="color:#2C4A6E;font-size:18px;margin:0 0 16px">是陶。收到新提問</h2>
      <div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px">
        <p style="font-size:13px;color:#6B7280;margin:0 0 12px">提問者：{q.email}</p>
        <p style="font-size:14px;color:#1C2B3A;margin:0;line-height:1.8;border-top:1px solid #E0DCD5;padding-top:12px">{q.question}</p>
      </div>
      <a href="https://pottery-shop-alpha.vercel.app/admin.html"
         style="display:block;text-align:center;background:#2C4A6E;color:#fff;padding:11px;border-radius:8px;text-decoration:none;font-size:13px;font-weight:600">
        前往後台回覆
      </a>
      <p style="font-size:11px;color:#9CA3AF;text-align:center;margin-top:14px">是陶。It's Pottery</p>
    </div>"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": "是陶。<onboarding@resend.dev>", "to": [admin_email],
                      "subject": f"是陶。新提問", "html": html}, timeout=10)
    except Exception:
        pass

async def notify_customer(question: dict, answer: str):
    api_key = os.getenv("RESEND_API_KEY")
    if not api_key:
        return
    html = f"""
    <div style="font-family:'Helvetica Neue',Arial,sans-serif;max-width:520px;margin:0 auto;background:#F5F2EE;padding:28px 24px;border-radius:12px">
      <h2 style="color:#2C4A6E;font-size:18px;margin:0 0 16px">是陶。回覆了您的問題</h2>
      <div style="background:#fff;border-radius:10px;padding:16px 20px;margin-bottom:16px">
        <p style="font-size:12px;color:#6B7280;margin:0 0 6px;text-transform:uppercase;letter-spacing:.5px">您的問題</p>
        <p style="font-size:14px;color:#6B7280;margin:0 0 14px;line-height:1.7">{question.get('question','')}</p>
        <p style="font-size:12px;color:#2C4A6E;margin:0 0 6px;text-transform:uppercase;letter-spacing:.5px;font-weight:600">回覆</p>
        <p style="font-size:14px;color:#1C2B3A;margin:0;line-height:1.7">{answer}</p>
      </div>
      <p style="font-size:12px;color:#9CA3AF;text-align:center;line-height:1.8;margin:0">
        此信件為系統自動發送，請勿直接回覆<br>
        是陶。It's Pottery
      </p>
    </div>"""
    try:
        async with httpx.AsyncClient() as client:
            await client.post("https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"from": "是陶。<onboarding@resend.dev>", "to": [question.get("email")],
                      "subject": "是陶。回覆了您的問題", "html": html}, timeout=10)
    except Exception:
        pass
