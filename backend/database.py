import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = os.getenv("SUPABASE_PUBLISHABLE_KEY")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")


async def sb_fetch(path: str, method: str = "GET", body=None, use_secret: bool = True) -> any:
    """Supabase REST API 呼叫"""
    key = SUPABASE_SECRET_KEY if use_secret else SUPABASE_PUBLISHABLE_KEY
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    url = f"{SUPABASE_URL}/rest/v1{path}"
    async with httpx.AsyncClient() as client:
        response = await client.request(method, url, headers=headers, json=body)
        if not response.is_success:
            raise Exception(f"Supabase error {response.status_code}: {response.text}")
        text = response.text
        return response.json() if text else None


async def sb_storage_upload(file_bytes: bytes, file_path: str, content_type: str) -> str:
    """上傳圖片到 Supabase Storage，回傳公開 URL"""
    key = SUPABASE_SECRET_KEY
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }
    url = f"{SUPABASE_URL}/storage/v1/object/products/{file_path}"
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, content=file_bytes)
        if not response.is_success:
            raise Exception(f"Upload failed: {response.text}")
    return f"{SUPABASE_URL}/storage/v1/object/public/products/{file_path}"


async def verify_admin_token(token: str) -> dict:
    """驗證 Supabase Auth token，確認是管理員"""
    headers = {
        "apikey": SUPABASE_PUBLISHABLE_KEY,
        "Authorization": f"Bearer {token}",
    }
    url = f"{SUPABASE_URL}/auth/v1/user"
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        if not response.is_success:
            raise Exception("Invalid token")
    user = response.json()
    admin_email = os.getenv("ADMIN_EMAIL")
    if admin_email and user.get("email") != admin_email:
        raise Exception("Not admin")
    return user
