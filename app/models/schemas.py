"""pydantic 请求/响应模型"""

from typing import Optional

from pydantic import BaseModel, Field


# ==================== 认证 ====================
class WxLoginRequest(BaseModel):
    code: str = Field(..., description="wx.login 获取的 code")


class WxLoginResponse(BaseModel):
    token: str
    expires_in: int
    user_id: int
    is_new: bool


class ProfileUpdate(BaseModel):
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None


# ==================== 问诊会话 ====================
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000, description="用户输入")
    session_id: Optional[str] = Field(None, description="会话 ID,缺省则新建/恢复最近")


# ==================== 记录 ====================
class ShareCreateRequest(BaseModel):
    record_id: int
    ttl_hours: int = Field(72, ge=1, le=168)


# ==================== 反馈 ====================
class FeedbackCreate(BaseModel):
    session_id: Optional[str] = None
    rating: int = Field(..., ge=1, le=5)
    content: Optional[str] = None
