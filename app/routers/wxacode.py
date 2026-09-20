"""小程序码路由 - 生成带 scene 的无限小程序码(复用 wx_api token 底座)"""

import base64
import logging

from fastapi import APIRouter, Depends

from app.core import wx_api
from app.core.deps import get_current_user
from app.models.schemas import WxacodeRequest, WxacodeResponse
import config

router = APIRouter(prefix="/api/wxacode", tags=["小程序码"])
logger = logging.getLogger(__name__)


@router.post("", response_model=WxacodeResponse)
async def generate(req: WxacodeRequest, user_id: int = Depends(get_current_user)):
    page = req.page or config.WXACODE_DEFAULT_PAGE
    payload = {"scene": req.scene, "page": page, "width": req.width}

    content, ctype = await wx_api.wx_get_bytes("POST", "/wxa/getwxacodeunlimit", json=payload)
    if content is None:
        # 真实调用失败或 dev 模式:降级返回占位(mock),不 500
        logger.info("[wxacode] 返回占位(降级)")
        return WxacodeResponse(mock=True)

    return WxacodeResponse(
        image_base64=base64.b64encode(content).decode("ascii"),
        content_type=ctype or "image/png",
    )
