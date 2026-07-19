"""抖音生活服务开放平台客户端——真实协议实现。

协议（developer.open-douyin.com 生活服务开放能力）：
  - 凭证：``POST https://open.douyin.com/oauth/client_token/``
      {client_key, client_secret, grant_type:"client_credential"}
      → data.access_token（有效期 expires_in 秒，客户端内缓存续期）
  - 商品线上数据查询：``GET /goodlife/v1/goods/product/online/get/``
      请求头 ``access-token``；参数 account_id / cursor / count
  - 响应包封：金额单位为**分**（与美团联盟的「元」不同，映射时勿再 ×100）；
    错误以 ``data.error_code``（或顶层 ``err_no``）非 0 表示。

``base_url``/``transport`` 可注入：测试指向进程内仿真网关，真实调用走官方域名。
"""
from __future__ import annotations

import time
from typing import Any

import httpx

DOUYIN_BASE_URL = "https://open.douyin.com"
TOKEN_PATH = "/oauth/client_token/"
PRODUCT_ONLINE_PATH = "/goodlife/v1/goods/product/online/get/"


class DouyinAPIError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(f"{code}:{message}")
        self.code = code
        self.message = message


class DouyinLifeClient:
    def __init__(
        self,
        client_key: str,
        client_secret: str,
        account_id: str = "",
        base_url: str = DOUYIN_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 10.0,
    ):
        self.client_key = client_key
        self.client_secret = client_secret
        self.account_id = account_id
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), transport=transport, timeout=timeout_s
        )
        self._token = ""
        self._token_expire_at = 0.0

    def close(self) -> None:
        self._client.close()

    # ---- client_token（缓存续期）------------------------------------------

    def _access_token(self) -> str:
        if self._token and time.time() < self._token_expire_at - 60:
            return self._token
        try:
            resp = self._client.post(TOKEN_PATH, json={
                "client_key": self.client_key,
                "client_secret": self.client_secret,
                "grant_type": "client_credential",
            })
        except httpx.HTTPError as e:
            raise DouyinAPIError(-1, f"网络错误: {e}") from e
        data = (resp.json() or {}).get("data") or {}
        if resp.status_code != 200 or data.get("error_code", 0) != 0 or not data.get("access_token"):
            raise DouyinAPIError(data.get("error_code", resp.status_code),
                                 data.get("description", "获取 client_token 失败"))
        self._token = data["access_token"]
        self._token_expire_at = time.time() + float(data.get("expires_in", 7200))
        return self._token

    # ---- 商品线上数据查询 ---------------------------------------------------

    def product_online_get(self, cursor: int = 0, count: int = 50) -> dict[str, Any]:
        params: dict[str, Any] = {"cursor": cursor, "count": count}
        if self.account_id:
            params["account_id"] = self.account_id
        try:
            resp = self._client.get(
                PRODUCT_ONLINE_PATH, params=params,
                headers={"access-token": self._access_token(),
                         "content-type": "application/json"},
            )
        except httpx.HTTPError as e:
            raise DouyinAPIError(-1, f"网络错误: {e}") from e
        if resp.status_code != 200:
            raise DouyinAPIError(resp.status_code, f"HTTP {resp.status_code}")
        body = resp.json() or {}
        data = body.get("data") or {}
        code = data.get("error_code", body.get("err_no", 0))
        if code != 0:
            raise DouyinAPIError(code, data.get("description") or body.get("err_msg", ""))
        return data
