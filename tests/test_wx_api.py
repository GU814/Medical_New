"""
wx_api 单元测试 - 不触网,验证缓存/锁/降级/解析容错

运行: .venv/Scripts/python.exe -m pytest tests/test_wx_api.py -q
"""

import asyncio
from unittest.mock import patch

import config
from app.core import wx_api


def test_dev_mode_returns_mock_and_no_network():
    """默认无 AppID/Secret -> dev 降级,返回 mock token,下游 wx_request 返回 mock"""
    if config.WX_APPID and config.WX_SECRET:
        return  # 环境已配真实密钥,跳过 dev 断言
    token = asyncio.run(wx_api.get_access_token())
    assert token == "dev-mock-access-token"
    res = asyncio.run(
        wx_api.wx_request("POST", "/cgi-bin/message/subscribe/send", json={"a": 1})
    )
    assert res == {"mock": True}
    content, ctype = asyncio.run(
        wx_api.wx_get_bytes("POST", "/wxa/getwxacodeunlimit", json={"a": 1})
    )
    assert ctype == "mock"


def test_token_cache_and_lock_only_one_request():
    """真实模式下:连续两次获取,只真实请求 1 次(token 缓存命中)"""
    calls = {"n": 0}

    class _FakeResp:
        def json(self):
            return {"access_token": "tok_abc", "expires_in": 7200}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            calls["n"] += 1
            return _FakeResp()

    with patch.object(config, "WX_APPID", "appid_test"), patch.object(
        config, "WX_SECRET", "secret_test"
    ), patch.object(wx_api.httpx, "AsyncClient", _FakeClient):
        wx_api._token_cache["access_token"] = None
        wx_api._token_cache["expires_at"] = 0
        t1 = asyncio.run(wx_api.get_access_token())
        t2 = asyncio.run(wx_api.get_access_token())

    assert t1 == "tok_abc" == t2
    assert calls["n"] == 1, f"应仅请求 1 次,实际 {calls['n']}"


def test_token_fetch_failure_degrades_to_none():
    """微信返回错误(无 access_token)时返回 None,不抛异常"""
    class _ErrResp:
        def json(self):
            return {"errcode": 40013, "errmsg": "invalid appid"}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return _ErrResp()

    with patch.object(config, "WX_APPID", "appid_test"), patch.object(
        config, "WX_SECRET", "secret_test"
    ), patch.object(wx_api.httpx, "AsyncClient", _FakeClient):
        wx_api._token_cache["access_token"] = None
        wx_api._token_cache["expires_at"] = 0
        token = asyncio.run(wx_api.get_access_token())

    assert token is None
