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
    # 登录资料:新会话创建时预填,避免跨会话重复询问(年龄/性别)
    age: Optional[int] = Field(None, ge=0, le=150, description="年龄")
    gender: Optional[str] = Field(None, max_length=10, description="性别")


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


# ==================== 地理位置 ====================
class LocationAdd(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="地点名称")
    address: Optional[str] = Field(None, max_length=200, description="详细地址")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="纬度")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="经度")
    is_default: bool = False


class LocationItem(BaseModel):
    id: int
    name: str
    address: Optional[str] = None


# ==================== 家庭成员 ====================
class FamilyMemberAdd(BaseModel):
    member_name: str = Field(..., min_length=1, max_length=30, description="家庭成员称呼/姓名")
    relationship: Optional[str] = Field(None, max_length=20, description="关系(父母/配偶/子女…)")
    gender: Optional[str] = Field(None, max_length=10, description="性别")
    birth_date: Optional[str] = Field(None, max_length=20, description="出生日期")
    phone: Optional[str] = Field(None, max_length=20, description="联系电话")
    emergency_contact: bool = False
    notify_on_emergency: bool = True
    address_shared: bool = True
    can_view_status: bool = True


class FamilyMemberUpdate(BaseModel):
    member_name: Optional[str] = Field(None, max_length=30)
    relationship: Optional[str] = Field(None, max_length=20)
    gender: Optional[str] = Field(None, max_length=10)
    birth_date: Optional[str] = Field(None, max_length=20)
    phone: Optional[str] = Field(None, max_length=20)
    emergency_contact: Optional[bool] = None
    notify_on_emergency: Optional[bool] = None
    address_shared: Optional[bool] = None
    can_view_status: Optional[bool] = None


class FamilyAcceptInvite(BaseModel):
    token: str = Field(..., min_length=1, description="绑定邀请令牌")
    member_openid: Optional[str] = Field(None, description="家庭成员微信号(openid);缺省取当前登录用户")
    member_user_id: Optional[int] = Field(None, description="若成员也是本 App 用户,关联其 user_id;缺省取当前登录用户")


# ==================== 订阅消息 ====================
class SubscribeAuthorize(BaseModel):
    template_id: str = Field(..., description="订阅模板 ID")
    scene: Optional[str] = Field(None, description="授权场景,如 consult_done")


class ReminderCreate(BaseModel):
    template_id: str = Field(..., description="订阅模板 ID")
    data: dict = Field(..., description="模板填充数据,如 {'thing1':{'value':'复诊提醒'}}")
    scheduled_at: Optional[str] = Field(None, description="计划发送时间,留空立即发送")


class ReminderItem(BaseModel):
    id: int
    template_id: str
    data: dict
    status: str
    scheduled_at: str
    sent_at: Optional[str] = None
    fail_reason: Optional[str] = None


# ==================== 小程序码 ====================
class WxacodeRequest(BaseModel):
    scene: str = Field(..., min_length=1, max_length=32, description="场景值,最长32字符,仅ASCII")
    page: Optional[str] = Field(None, description="落地页路径,默认 WXACODE_DEFAULT_PAGE")
    width: int = Field(430, ge=280, le=1280, description="二维码宽度px")


class WxacodeResponse(BaseModel):
    image_base64: Optional[str] = None
    content_type: str = "image/png"
    mock: bool = False
