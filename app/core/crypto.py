"""
加密核心模块 - 医学问诊智能体小程序后端

三层密钥体系:
    MASTER_KEY(环境变量,32字节) ─HKDF-SHA256─▶ KEK(密钥加密密钥,派生,不存储)
    KEK ─AES-256-GCM 加密─▶ DEK(数据加密密钥,每用户随机32字节,密文存 user_keys)
    DEK ─AES-256-GCM 加密─▶ 字段密文(存于各业务表)

设计要点:
- nonce 每次随机 12 字节,绝不复用;同一明文每次密文不同
- DEK 进程级 LRU 缓存(user_id→DEK,TTL 10 分钟),摊销取出开销
- 密文格式:base64(nonce || ciphertext_with_tag)
- 空值透传:明文为空/None 时直接返回原值,避免空串加密噪声
- MASTER_KEY 为空时(仅 dev)自动生成内存随机密钥,重启后旧密文不可解密(仅限开发)
"""

import base64
import logging
import os
import secrets
import threading
import time

import config

logger = logging.getLogger(__name__)

# 延迟导入,避免循环依赖
# from app.db.connection import get_conn

# ==================== 密钥派生 ====================

_KEK_INFO = b"medical-bot-kek-v1"
_KEK_SALT = b"medical-bot-salt-v1"
_NONCE_LEN = 12  # GCM 推荐 12 字节
_KEY_LEN = 32    # AES-256
_CACHE_TTL = 600  # DEK 缓存 10 分钟


def _load_master_key() -> bytes:
    """加载主密钥:优先环境变量 base64,为空则 dev 模式生成内存随机密钥"""
    raw = config.MASTER_KEY
    if raw:
        try:
            key = base64.b64decode(raw)
            if len(key) == _KEY_LEN:
                return key
            # 非 32 字节,用 HKDF 派生到 32 字节
        except Exception:
            pass
        # fallback:直接用 UTF-8 字节做 HKDF 输入
        return _hkdf(raw.encode("utf-8"))

    # dev 模式:读取/生成「持久化」的本地开发密钥。
    # 之前的实现每次进程启动都 secrets.token_bytes() 现造一把,
    # 结果上次运行写入的加密字段下次启动全部解不开(日志刷"解密字段失败")。
    # 这里改为落盘到 data/.dev_master_key,保证重启后仍能解密历史数据。
    key = _load_or_create_dev_master_key()
    if key:
        if not getattr(_load_master_key, "_warned", False):
            logger.warning(
                "MASTER_KEY 未配置,使用本地开发密钥 data/.dev_master_key(仅限开发,勿用于生产)"
            )
            _load_master_key._warned = True
        return key

    if not getattr(_load_master_key, "_warned", False):
        logger.warning("MASTER_KEY 未配置且无法落盘,使用内存随机密钥(重启后旧密文不可解密)")
        _load_master_key._warned = True
    return secrets.token_bytes(_KEY_LEN)


def _dev_master_key_path() -> str:
    """开发密钥落盘路径:优先项目根/data,回退到系统临时目录"""
    base = getattr(config, "DATA_DIR", None) or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base, "data")
    try:
        os.makedirs(data_dir, exist_ok=True)
    except Exception:
        import tempfile
        data_dir = tempfile.gettempdir()
    return os.path.join(data_dir, ".dev_master_key")


def _load_or_create_dev_master_key():
    """读取已存在的开发主密钥,不存在则生成并写入(0600 权限)"""
    path = _dev_master_key_path()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read().strip()
            if raw:
                key = base64.b64decode(raw)
                if len(key) == _KEY_LEN:
                    return key
    except Exception as e:
        logger.warning(f"读取开发主密钥失败({path}): {e}")

    try:
        key = secrets.token_bytes(_KEY_LEN)
        with open(path, "w", encoding="utf-8") as f:
            f.write(base64.b64encode(key).decode("ascii"))
        try:
            os.chmod(path, 0o600)
        except Exception:
            pass
        logger.info(f"已生成开发用主密钥: {path}")
        return key
    except Exception as e:
        logger.warning(f"写入开发主密钥失败: {e}")
        return None


def _hkdf(ikm: bytes, salt: bytes = _KEK_SALT, info: bytes = _KEK_INFO, length: int = _KEY_LEN) -> bytes:
    """HKDF-SHA256 派生密钥"""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    )
    return hkdf.derive(ikm)


_kek_cache = None
_kek_lock = threading.Lock()


def _get_kek() -> bytes:
    """获取 KEK(进程级单例,从 MASTER_KEY 派生)"""
    global _kek_cache
    if _kek_cache is not None:
        return _kek_cache
    with _kek_lock:
        if _kek_cache is None:
            master = _load_master_key()
            _kek_cache = _hkdf(master)
    return _kek_cache


# ==================== DEK 管理 ====================

# user_id -> (dek_bytes, expire_ts)
_dek_cache: dict = {}
_dek_cache_lock = threading.Lock()


def _get_or_create_dek(user_id: int) -> bytes:
    """获取用户 DEK:优先缓存,其次从 user_keys 解密,首次则生成并存储"""
    now = time.time()
    with _dek_cache_lock:
        cached = _dek_cache.get(user_id)
        if cached and cached[1] > now:
            return cached[0]

    # 从库加载或新建
    from app.db.connection import get_conn

    dek = None
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT encrypted_dek FROM user_keys WHERE user_id=?", (user_id,)
        )
        row = cur.fetchone()
        if row:
            dek = _decrypt_with_kek(row["encrypted_dek"])

    if dek is None:
        # 首次:生成随机 DEK,用 KEK 加密存库
        dek = secrets.token_bytes(_KEY_LEN)
        encrypted_dek = _encrypt_with_kek(dek)
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_keys(user_id, encrypted_dek, kek_version, created_at) "
                "VALUES (?, ?, 1, ?)",
                (user_id, encrypted_dek, now_str),
            )
            conn.commit()
        logger.info(f"为用户 {user_id} 生成新 DEK")

    with _dek_cache_lock:
        _dek_cache[user_id] = (dek, now + _CACHE_TTL)
    return dek


def _encrypt_with_kek(plaintext_bytes: bytes) -> str:
    """用 KEK 加密(DEK 本身的保护)"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    kek = _get_kek()
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(kek).encrypt(nonce, plaintext_bytes, None)
    return base64.b64encode(nonce + ct).decode("ascii")


def _decrypt_with_kek(b64_ciphertext: str) -> bytes:
    """用 KEK 解密(DEK 本身的还原)"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(b64_ciphertext)
    nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return AESGCM(_get_kek()).decrypt(nonce, ct, None)


# ==================== 字段级加解密 ====================

def encrypt_field(user_id: int, plaintext) -> str:
    """
    加密单个字段。
    空值(None/空串)直接透传返回原值,避免空串加密噪声。
    Returns: base64 密文字符串;空值返回原值(可能是 None 或 "")
    """
    if plaintext is None:
        return None
    if isinstance(plaintext, str) and plaintext == "":
        return ""
    if not isinstance(plaintext, str):
        plaintext = str(plaintext)

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    dek = _get_or_create_dek(user_id)
    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(dek).encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


def decrypt_field(user_id: int, ciphertext) -> str:
    """
    解密单个字段。
    空值/非密文(空串或 None)直接透传;解密失败返回空串并记录(避免单字段错乱阻断整行)。
    """
    if ciphertext is None:
        return None
    if isinstance(ciphertext, str) and ciphertext == "":
        return ""

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        raw = base64.b64decode(ciphertext)
        if len(raw) < _NONCE_LEN + 1:
            # 不是合法密文,直接返回原值(兼容未加密的遗留数据)
            return ciphertext
        nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
        dek = _get_or_create_dek(user_id)
        return AESGCM(dek).decrypt(nonce, ct, None).decode("utf-8")
    except Exception as e:
        logger.error(f"解密字段失败(user_id={user_id}): {e}")
        return ""


# ==================== 行级批量加解密 ====================

# 敏感字段集合(用于行级加解密)
PATIENT_SENSITIVE_FIELDS = (
    "patient_name", "chief_complaint", "present_illness", "past_history",
    "personal_history", "family_history", "system_review", "diagnosis",
    "full_report",
)
SESSION_SENSITIVE_FIELDS = PATIENT_SENSITIVE_FIELDS + ("conversation_history", "report")


def encrypt_record(user_id: int, record: dict, fields) -> dict:
    """批量加密记录中指定字段,返回新 dict(不修改原对象)"""
    out = dict(record)
    for f in fields:
        if f in out:
            out[f] = encrypt_field(user_id, out[f])
    return out


def decrypt_record(user_id: int, record: dict, fields) -> dict:
    """批量解密记录中指定字段,返回新 dict(不修改原对象)"""
    out = dict(record)
    for f in fields:
        if f in out:
            out[f] = decrypt_field(user_id, out[f])
    return out


def clear_dek_cache(user_id: int = None):
    """清除 DEK 缓存(密钥轮换后调用)"""
    with _dek_cache_lock:
        if user_id is not None:
            _dek_cache.pop(user_id, None)
        else:
            _dek_cache.clear()
