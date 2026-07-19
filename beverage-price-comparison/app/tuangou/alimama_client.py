"""阿里妈妈 / 淘宝联盟（TOP 协议）客户端——真实协议实现。

协议（标准淘宝开放平台 TOP 网关）：
  - 网关：``https://eco.taobao.com/router/rest``（GET/POST 表单）
  - 系统参数：method / app_key / timestamp(yyyy-MM-dd HH:mm:ss) / format=json /
    v=2.0 / sign_method=md5 / sign
  - **MD5 签名**：所有参数按 key 字典序排序，拼成 ``secret + k1v1k2v2... + secret``，
    MD5 后**大写**。
  - 物料搜索：``taobao.tbk.dg.material.optional``（淘客物料，含本地生活/饿了么
    物料入口；q 关键词 + adzone_id 推广位）
  - 错误：``error_response{code, msg, sub_code, sub_msg}``

诚实说明：阿里系「到店团购（口碑/高德）」开放能力仍在迁移（PRD §12.1），本客户端
以淘宝联盟物料 API 为**阿里系 CPS 取数入口**；到店专用接口就绪后同法替换 method。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx

ALIMAMA_BASE_URL = "https://eco.taobao.com"
ROUTER_PATH = "/router/rest"
METHOD_MATERIAL = "taobao.tbk.dg.material.optional"


class AlimamaAPIError(RuntimeError):
    def __init__(self, code, message: str):
        super().__init__(f"{code}:{message}")
        self.code = code
        self.message = message


def top_sign(secret: str, params: dict[str, Any]) -> str:
    """TOP MD5 签名：secret + 按 key 排序的 k v 连接串 + secret → MD5 大写。"""
    joined = "".join(f"{k}{params[k]}" for k in sorted(params))
    return hashlib.md5((secret + joined + secret).encode("utf-8")).hexdigest().upper()


class AlimamaClient:
    def __init__(
        self,
        app_key: str,
        secret: str,
        adzone_id: str,
        base_url: str = ALIMAMA_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 10.0,
    ):
        self.app_key = app_key
        self.secret = secret
        self.adzone_id = adzone_id
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"), transport=transport, timeout=timeout_s
        )

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, biz_params: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "method": method,
            "app_key": self.app_key,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "format": "json",
            "v": "2.0",
            "sign_method": "md5",
            **{k: v for k, v in biz_params.items() if v not in (None, "")},
        }
        params["sign"] = top_sign(self.secret, params)
        try:
            resp = self._client.get(ROUTER_PATH, params=params)
        except httpx.HTTPError as e:
            raise AlimamaAPIError(-1, f"网络错误: {e}") from e
        if resp.status_code != 200:
            raise AlimamaAPIError(resp.status_code, f"HTTP {resp.status_code}")
        body = resp.json() or {}
        if "error_response" in body:
            err = body["error_response"]
            raise AlimamaAPIError(err.get("code", -1),
                                  err.get("sub_msg") or err.get("msg", ""))
        return body

    def material_search(self, q: str = "", page_no: int = 1, page_size: int = 20) -> list[dict]:
        """淘客物料搜索，返回 map_data 列表。"""
        body = self._call(METHOD_MATERIAL, {
            "adzone_id": self.adzone_id,
            "q": q,
            "page_no": page_no,
            "page_size": page_size,
        })
        resp = body.get("tbk_dg_material_optional_response") or {}
        return ((resp.get("result_list") or {}).get("map_data")) or []
