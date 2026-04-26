import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

class LoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def login(req: LoginRequest):
    """管理員登入，回傳 access_token"""
    url = f"{os.getenv('SUPABASE_URL')}/auth/v1/token?grant_type=password"
    headers = {
        "apikey": os.getenv("SUPABASE_PUBLISHABLE_KEY"),
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        res = await client.post(url, headers=headers, json={
            "email": req.email,
            "password": req.password,
        })

    if not res.is_success:
        raise HTTPException(status_code=401, detail="Email 或密碼錯誤")

    data = res.json()
    if not data.get("access_token"):
        raise HTTPException(status_code=401, detail="登入失敗")

    # 確認是管理員 email
    admin_email = os.getenv("ADMIN_EMAIL")
    if admin_email and data.get("user", {}).get("email") != admin_email:
        raise HTTPException(status_code=403, detail="此帳號無管理員權限")

    return {
        "access_token": data["access_token"],
        "email": data["user"]["email"],
    }
