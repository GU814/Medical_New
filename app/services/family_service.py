"""
家庭成员服务 - 绑定 / 状态共享 / 紧急推送。

绑定流程(贴合微信生态):
  1) 主用户「添加成员」-> 生成 pending 邀请记录 + invite_token;
  2) 家庭成员在自己的微信里打开邀请落地页,点击「接受邀请」-> 其 openid 写入记录,
     状态置 bound。此后该成员即成为可推送 / 可查看的对象。

紧急推送:
  问诊中识别到紧急症状(_check_emergency)时,后台调用 notify_emergency,
  向所有「重大情况推送」开启的家庭成员发送订阅消息,并(按开关)附带用户常用地址。
"""

import logging
import secrets
from datetime import datetime

from app.db import repositories
from app.services import subscribe_service
import config

logger = logging.getLogger(__name__)

# 订阅消息模板场景键(对应 config.WX_SUBSCRIBE_TEMPLATES["family_emergency"])。
# 实际字段 key(thing1/thing2/...)需与你小程序后台配置的模板一一对应,此处为通用示例。
FAMILY_EMERGENCY_SCENE = "family_emergency"


def create_invite(user_id: int, payload) -> dict:
    """主用户添加家庭成员:生成待绑定邀请记录。"""
    token = secrets.token_hex(8)
    mid = repositories.add_family_member(
        user_id,
        member_name=payload.member_name,
        relationship=payload.relationship,
        gender=payload.gender,
        birth_date=payload.birth_date,
        phone=payload.phone,
        emergency_contact=payload.emergency_contact,
        notify_on_emergency=payload.notify_on_emergency,
        address_shared=payload.address_shared,
        can_view_status=payload.can_view_status,
        invite_token=token,
        invite_status="pending",
    )
    member = repositories.get_family_member(mid, user_id)
    return _serialize(member)


def accept_invite(token: str, member_openid: str, member_user_id: int = None) -> dict | None:
    """家庭成员接受邀请,绑定其微信号/账号。"""
    member = repositories.bind_family_member(token, member_openid, member_user_id)
    return _serialize(member) if member else None


def list_members(user_id: int) -> list:
    return [_serialize(m) for m in repositories.list_family_members(user_id)]


def update_member(member_id: int, user_id: int, payload) -> dict | None:
    fields = payload.dict(exclude_unset=True)
    ok = repositories.update_family_member(member_id, user_id, **fields)
    if not ok:
        return None
    member = repositories.get_family_member(member_id, user_id)
    return _serialize(member) if member else None


def delete_member(member_id: int, user_id: int):
    repositories.delete_family_member(member_id, user_id)


async def notify_emergency(user_id: int, emergency_text: str) -> list:
    """
    向该用户勾选「重大情况推送」的家庭成员发送紧急提醒。

    Returns: 每条推送的结果列表(供日志/前端展示)。
    注意:订阅消息能否真正送达,取决于(1)已配置 family_emergency 模板;
          (2)家庭成员此前在小程序里授权过该模板。dev 环境无模板时返回 mock。
    """
    user = repositories.get_user(user_id) or {}
    name = user.get("nickname") or "您的家人"
    gender = user.get("profile_gender") or ""
    age = user.get("profile_age") or ""
    who = name + (f"（{gender}{age}岁）" if (gender or age) else "")

    locs = repositories.list_locations(user_id)
    default = next((l for l in locs if l.get("is_default")), None) or (locs[0] if locs else None)
    address = (default or {}).get("address") or ""

    template_id = config.WX_SUBSCRIBE_TEMPLATES.get(FAMILY_EMERGENCY_SCENE)
    contacts = repositories.list_emergency_contacts(user_id)

    results = []
    for c in contacts:
        share_addr = bool(c.get("address_shared"))
        # 订阅消息 data 格式:{字段key:{value:文本}};key 需与微信后台模板一致
        data = {
            "thing1": {"value": f"{who}出现紧急情况"[:20]},
            "thing2": {"value": (emergency_text or "请尽快确认其安全")[:20]},
            "thing3": {"value": (f"地址:{address}" if (share_addr and address) else "地址未提供")[:20]},
            "time4": {"value": datetime.now().strftime("%Y-%m-%d %H:%M")},
        }
        openid = c.get("member_openid")
        target_user_id = c.get("member_user_id")
        if not template_id:
            results.append({"member": c.get("member_name"), "status": "skipped",
                            "reason": "未配置 family_emergency 模板"})
            continue
        if openid:
            res = await subscribe_service.send_subscribe_to_openid(openid, template_id, data)
        elif target_user_id:
            res = await subscribe_service.send_subscribe(target_user_id, template_id, data)
        else:
            results.append({"member": c.get("member_name"), "status": "skipped",
                            "reason": "无推送目标(openid)"})
            continue
        if res is None:
            results.append({"member": c.get("member_name"), "status": "failed"})
        elif res.get("mock"):
            results.append({"member": c.get("member_name"), "status": "mock"})
        else:
            results.append({"member": c.get("member_name"), "status": "sent"})
    logger.info(f"[family] 紧急推送 user={user_id} 共 {len(results)} 条: {results}")
    return results


def get_shared_status(user_id: int) -> dict:
    """供已绑定家庭成员查看的用户状态摘要。"""
    user = repositories.get_user(user_id) or {}
    rec = repositories.get_latest_record(user_id)
    locs = repositories.list_locations(user_id)
    default = next((l for l in locs if l.get("is_default")), None) or (locs[0] if locs else None)
    if rec:
        preview = rec.get("chief_complaint_preview") or "问诊记录"
        full = rec.get("full_report")
        summary = preview + ("（已生成报告）" if full else "（问诊中）")
    else:
        summary = "暂无问诊记录"
    return {
        "nickname": user.get("nickname") or "家人",
        "gender": user.get("profile_gender") or "",
        "age": user.get("profile_age") or "",
        "last_activity": (rec or {}).get("created_at") or user.get("created_at") or "",
        "status_summary": summary,
        "address": (default or {}).get("address") or "未设置常用地址",
    }


def get_status_by_token(token: str) -> dict | None:
    """家庭成员凭绑定令牌查看主用户状态(令牌即其接受邀请时持有的 invite_token)。"""
    member = repositories.get_family_member_by_token(token)
    if not member:
        return None
    if member.get("invite_status") != "bound":
        return None
    if not member.get("can_view_status"):
        return {"error": "该成员未被授权查看状态"}
    return get_shared_status(member.get("user_id"))


def _serialize(m: dict) -> dict:
    """统一布尔字段(0/1 -> bool)输出。"""
    if not m:
        return m
    for k in ("can_view_status", "emergency_contact", "notify_on_emergency", "address_shared"):
        if k in m:
            m[k] = bool(m[k])
    return m
