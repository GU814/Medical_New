"""
安全核心模块 - JWT 签发/校验 + 微信 code2session 调用

职责:
- code2session:用小程序 code 换取 openid/session_key
- JWT 签发:payload 含 sub(user_id) + openid_hash(审计用),exp=7d
- JWT 校验:解析并验证签名与有效期
- session_key 短期缓存(5min TTL),用于解密手机号等 encrypted_data,绝不返回前端
"""

import hashlib
import logging
import time

import config

logger = logging.getLogger(__name__)

# session_key 缓存:openid -> (session_key, expire_ts)
_session_key_cache: dict = {}


def hash_openid(openid: str) -> str:
    """对 openid 做哈希(存入 JWT payload 便于审计,不暴露真实 openid)"""
    return hashlib.sha256(openid.encode("utf-8")).hexdigest()[:16]


# ==================== JWT ====================

def create_access_token(user_id: int, openid: str) -> tuple:
    """
    签发 JWT。
    Returns: (token, expires_in_seconds)
    """
    import jwt

    now = int(time.time())
    exp = now + config.JWT_TTL_DAYS * 86400
    payload = {
        "sub": str(user_id),
        "oid": hash_openid(openid),
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, config.SECRET_KEY, algorithm=config.JWT_ALG)
    return token, exp - now


def decode_access_token(token: str) -> dict:
    """
    解码并校验 JWT。
    Raises: jwt.PyJWTError(过期/签名错误/格式错误)
    Returns: payload dict,含 sub(user_id 字符串)
    """
    import jwt

    payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALG])
    return payload


# ==================== 微信 code2session ====================

def code2session(code: str) -> dict:
    """
    用小程序前端传来的 code 调用微信 jscode2session 换取 openid/session_key。
    Returns: {openid, session_key, unionid?}
    Raises: ValueError(配置缺失/微信返回错误)
    """
    if not config.WX_APPID or not config.WX_SECRET:
        # dev 模式:无 appid/secret 时,用 code 模拟 openid,便于本地联调
        logger.warning("WX_APPID/WX_SECRET 未配置,使用 dev 模拟 openid(仅开发)")
        mock_openid = "dev_" + hashlib.md5(code.encode("utf-8")).hexdigest()[:24]
        return {"openid": mock_openid, "session_key": "dev_session_key"}

    import httpx

    url = f"{config.WX_API_BASE}/sns/jscode2session"
    params = {
        "appid": config.WX_APPID,
        "secret": config.WX_SECRET,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params=params)
            data = resp.json()
    except Exception as e:
        logger.error(f"调用 code2session 网络失败: {e}")
        raise ValueError(f"微信登录服务暂时不可用: {e}")

    if "errcode" in data and data["errcode"] != 0:
        logger.error(f"code2session 返回错误: {data}")
        raise ValueError(f"微信登录失败: {data.get('errmsg', '未知错误')}")

    openid = data.get("openid")
    session_key = data.get("session_key")
    if not openid or not session_key:
        raise ValueError("微信登录返回数据不完整")

    # 缓存 session_key(短期,用于解密 encrypted_data)
    _session_key_cache[openid] = (session_key, time.time() + config.SESSION_KEY_TTL)

    return {
        "openid": openid,
        "session_key": session_key,
        "unionid": data.get("unionid"),
    }


def get_session_key(openid: str) -> str:
    """获取缓存的 session_key(用于解密手机号等 encrypted_data)"""
    cached = _session_key_cache.get(openid)
    if cached and cached[1] > time.time():
        return cached[0]
    return None
