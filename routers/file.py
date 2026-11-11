"""上传 JPG PNG GIF 图片，并返回可访问的文件地址"""
import os
import uuid
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from models import User
from schemas import ResponseModel
from utils import get_current_admin

router = APIRouter(prefix="/file", tags=["图片管理"])

#上传目录使用相对当前运行目录的upload
#Docker中通过Volume持久化
UPLOAD_DIR = FilePath("upload")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
#5MB限制用于避免过大的文件占用磁盘和带宽
MAX_FILE_SIZE = 5 * 1024 * 1024
#文件头签名用于判断真实图片类型
#不能只相信客户端提交的文件扩展名
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
    current_admin: User = Depends(get_current_admin),
):
    #读取文件前16字节检查图片签名
    header = file.file.read(16)
    #移动到文件末尾计算真实字节数，再恢复复读取位置
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    #空文件和超过5MB的文件直接拒绝
    if file_size <= 0:
        raise HTTPException(status_code=400, detail="文件不能为空")
    if file_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 5MB")

    #根据文件头识别真实格式，伪造.jpg扩展名的其他文件也会被拒绝
    detected_type = next(
        (extension for signature, extension in IMAGE_SIGNATURES if header.startswith(signature)),
        None,
    )
    if not detected_type:
        raise HTTPException(status_code=400, detail="仅支持 JPG、PNG 或 GIF 图片")
    #使用UUID生成文件名，避免重名覆盖，也避免直接使用客户端文件产生路径问题
    new_filename = f"{uuid.uuid4().hex}.{detected_type}"
    save_path = UPLOAD_DIR / new_filename
    #模式xb只在文件不存在时创建
    #防止意外覆盖已有文件
    with save_path.open("xb") as output:
        output.write(file.file.read())

    return ResponseModel.success(
        data={
            "filename": new_filename,
            #返回URL对应main.py中挂载的/upload静态目录
            "url": f"/upload/{new_filename}",
            "original_name": file.filename,
            "size_kb": round(file_size / 1024, 2),
        }
    )
