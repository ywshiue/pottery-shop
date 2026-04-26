import uuid
from fastapi import APIRouter, UploadFile, File, Header, HTTPException
from database import sb_storage_upload, verify_admin_token

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_SIZE = 8 * 1024 * 1024  # 8MB

@router.post("/")
async def upload_image(file: UploadFile = File(...), authorization: str = Header(...)):
    """管理員上傳商品圖片"""
    token = authorization.replace("Bearer ", "")
    await verify_admin_token(token)

    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="只支援 JPG、PNG、WebP 格式")

    file_bytes = await file.read()
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="圖片不能超過 8MB")

    ext = file.filename.split(".")[-1] if "." in file.filename else "jpg"
    file_path = f"{uuid.uuid4().hex}.{ext}"

    url = await sb_storage_upload(file_bytes, file_path, file.content_type)
    return {"url": url}
