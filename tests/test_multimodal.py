"""
多模态输入路由测试 - 语音识别 / 图片识别

覆盖:鉴权、功能未启用、空文件、格式不支持、超限、识别为空、正常识别。
使用 FastAPI TestClient + 本地 JWT,真实模型调用通过 mock 替换,避免依赖外部服务。
"""

import pytest
from fastapi.testclient import TestClient

import config
from app.main import create_app
from app.core.security import create_access_token


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_header():
    token, _ = create_access_token(1, "dev_openid")
    return {"Authorization": f"Bearer {token}"}


def _enable(monkeypatch, asr=True, vision=True):
    monkeypatch.setattr(config, "ASR_ENABLED", asr)
    monkeypatch.setattr(config, "VISION_ENABLED", vision)


# ---------------- 鉴权 ----------------
def test_asr_requires_auth(client):
    res = client.post("/api/asr", files={"audio": ("a.mp3", b"x", "audio/mpeg")})
    assert res.status_code == 401


# ---------------- 功能未启用 -> 501 ----------------
def test_asr_disabled_returns_501(client, auth_header, monkeypatch):
    _enable(monkeypatch, asr=False)
    res = client.post(
        "/api/asr", files={"audio": ("a.mp3", b"x", "audio/mpeg")}, headers=auth_header
    )
    assert res.status_code == 501
    assert "未启用" in res.json()["detail"]


def test_vision_disabled_returns_501(client, auth_header, monkeypatch):
    _enable(monkeypatch, vision=False)
    res = client.post(
        "/api/vision", files={"image": ("a.png", b"x", "image/png")}, headers=auth_header
    )
    assert res.status_code == 501


# ---------------- 空文件 -> 400 ----------------
def test_asr_empty_file_400(client, auth_header, monkeypatch):
    _enable(monkeypatch)
    res = client.post(
        "/api/asr", files={"audio": ("a.mp3", b"", "audio/mpeg")}, headers=auth_header
    )
    assert res.status_code == 400


# ---------------- 格式不支持 -> 400 ----------------
def test_asr_unsupported_format_400(client, auth_header, monkeypatch):
    _enable(monkeypatch)
    res = client.post(
        "/api/asr", files={"audio": ("a.txt", b"xxxx", "text/plain")}, headers=auth_header
    )
    assert res.status_code == 400
    assert "不支持" in res.json()["detail"]


# ---------------- 超过大小上限 -> 413 ----------------
def test_asr_too_large_413(client, auth_header, monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(config, "ASR_MAX_SIZE_MB", 0)  # 任意非空文件都超限
    res = client.post(
        "/api/asr", files={"audio": ("a.mp3", b"xxxx", "audio/mpeg")}, headers=auth_header
    )
    assert res.status_code == 413


# ---------------- 识别结果为空 -> 422 ----------------
def test_asr_empty_result_422(client, auth_header, monkeypatch):
    _enable(monkeypatch)
    import app.routers.multimodal as mm

    monkeypatch.setattr(mm.asr_service, "transcribe", lambda data, filename: "")
    res = client.post(
        "/api/asr", files={"audio": ("a.mp3", b"voice", "audio/mpeg")}, headers=auth_header
    )
    assert res.status_code == 422


# ---------------- 正常识别 -> 200 ----------------
def test_asr_ok(client, auth_header, monkeypatch):
    _enable(monkeypatch)
    import app.routers.multimodal as mm

    monkeypatch.setattr(mm.asr_service, "transcribe", lambda data, filename: "我头疼三天")
    res = client.post(
        "/api/asr", files={"audio": ("a.mp3", b"voice", "audio/mpeg")}, headers=auth_header
    )
    assert res.status_code == 200
    assert res.json()["text"] == "我头疼三天"


def test_vision_ok(client, auth_header, monkeypatch):
    _enable(monkeypatch, vision=True)
    import app.routers.multimodal as mm

    monkeypatch.setattr(
        mm.vision_service,
        "recognize",
        lambda data, filename, prompt=None: "血常规:白细胞 12.0(偏高)",
    )
    res = client.post(
        "/api/vision",
        files={"image": ("a.png", b"img", "image/png")},
        headers=auth_header,
    )
    assert res.status_code == 200
    assert "白细胞" in res.json()["text"]


# ---------------- 底层失败 -> 502 ----------------
def test_vision_backend_error_502(client, auth_header, monkeypatch):
    _enable(monkeypatch, vision=True)
    import app.routers.multimodal as mm

    def boom(data, filename, prompt=None):
        raise RuntimeError("模型未拉取")

    monkeypatch.setattr(mm.vision_service, "recognize", boom)
    res = client.post(
        "/api/vision",
        files={"image": ("a.png", b"img", "image/png")},
        headers=auth_header,
    )
    assert res.status_code == 502
