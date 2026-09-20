"""
多模态输入路由 - 语音识别 / 图片识别

- POST /api/asr     : 上传音频文件 -> 转写为文本 {text}
- POST /api/vision  : 上传图片文件 -> 识别为文本 {text}(可选 ?prompt=)

两个端点都接入现有问诊流程:前端拿到 text 后,把 text 作为用户输入复用 /api/chat 的 SSE 问诊。
鉴权:与 /api/chat 一致,需 Authorization: Bearer <token>(AuthMiddleware 已放行白名单之外的路径)。

错误处理与边界:
- 401 未登录(AuthMiddleware / get_current_user)
- 400 文件为空 / 格式不支持
- 413 超过大小上限
- 422 识别结果为空(听不清/看不清)
- 501 功能未启用(ASR_ENABLED / VISION_ENABLED=false)
- 502 底层识别服务失败(模型未拉取、网络异常等)
"""

import asyncio
import logging
import os

from fastapi import APIRouter, Depends, File, HTTPException, status, UploadFile

import config
from app.core.deps import get_current_user
from app.services import asr_service, vision_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["多模态输入"])


def _audio_limit_bytes() -> int:
    """音频大小上限(字节),随配置动态读取"""
    return config.ASR_MAX_SIZE_MB * 1024 * 1024


def _image_limit_bytes() -> int:
    """图片大小上限(字节),随配置动态读取"""
    return config.VISION_MAX_SIZE_MB * 1024 * 1024


def _check_size(upload: UploadFile, limit_bytes: int, kind: str):
    """优先用 UploadFile.size(来自 Content-Length),缺失则读完后再校验"""
    declared = getattr(upload, "size", None)
    if isinstance(declared, int) and declared > limit_bytes:
        mb = limit_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{kind}过大,请控制在 {mb}MB 以内",
        )


def _check_format(upload: UploadFile, supported, kind: str):
    ext = (upload.filename or "").rsplit(".", 1)[-1].lower() if upload.filename else ""
    if ext and ext not in supported:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的{kind}格式:.{ext};支持 {', '.join(supported)}",
        )


@router.post("/asr")
async def asr(
    audio: UploadFile = File(..., description="音频文件(支持 mp3/wav/m4a/amr/pcm)"),
    user_id: int = Depends(get_current_user),
):
    """语音识别:音频 -> 文本"""
    limit = _audio_limit_bytes()
    _check_size(audio, limit, "音频")
    _check_format(audio, config.ASR_SUPPORTED_FORMATS, "音频")

    data = await audio.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="音频文件为空")
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"音频过大,请控制在 {config.ASR_MAX_SIZE_MB}MB 以内",
        )

    try:
        text = await asyncio.to_thread(asr_service.transcribe, data, audio.filename)
    except NotImplementedError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    except ValueError as e:
        # 业务逻辑层已明确判定的非法输入
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"语音识别失败 user={user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"语音识别失败:{e}")

    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="未能识别出文字,请重试或改用文字输入",
        )
    return {"text": text}


@router.post("/vision")
async def vision(
    image: UploadFile = File(..., description="图片文件(支持 jpg/png/webp/bmp/gif)"),
    prompt: str | None = None,
    user_id: int = Depends(get_current_user),
):
    """图片识别:图片 -> 文本(可选识别指令)"""
    limit = _image_limit_bytes()
    _check_size(image, limit, "图片")
    _check_format(image, config.VISION_SUPPORTED_FORMATS, "图片")

    data = await image.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="图片文件为空")
    if len(data) > limit:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"图片过大,请控制在 {config.VISION_MAX_SIZE_MB}MB 以内",
        )

    try:
        text = await asyncio.to_thread(vision_service.recognize, data, image.filename, prompt)
    except NotImplementedError as e:
        raise HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"图片识别失败 user={user_id}: {e}")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"图片识别失败:{e}")

    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="未能从图片中识别出信息,请重试或更换图片",
        )
    return {"text": text}
