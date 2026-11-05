import os
import uuid
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import get_db
from models import User
from schemas import ResponseModel
from utils import get_current_admin

router = APIRouter(prefix="/file", tags=["图片管理"])

UPLOAD_DIR = FilePath("upload")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_FILE_SIZE = 5 * 1024 * 1024
IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


@router.post(
    "/upload_image",
    summary="上传图片",
    response_model=ResponseModel,
)
def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin),
):
    header = file.file.read(16)
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="文件不能为空")
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 5MB")

    detected_type = next(
        (extension for signature, extension in IMAGE_SIGNATURES if header.startswith(signature)),
        None,
    )
    if not detected_type:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG 或 GIF 图片")

    new_filename = f"{uuid.uuid4().hex}.{detected_type}"
    save_path = UPLOAD_DIR / new_filename
    with save_path.open("xb") as output:
        output.write(file.file.read())

    return ResponseModel.success(
        data={
            "filename": new_filename,
            "url": f"/upload/{new_filename}",
            "original_name": file.filename,
            "size_kb": round(file_size / 1024, 2),
        }
    )
