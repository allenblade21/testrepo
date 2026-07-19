"""美团联盟（CPS）开放 API 客户端——真实协议实现。

协议（与官方网关一致，参照公开 SDK 契约）：
  - 网关：``https://media.meituan.com/cps_open/common/api/v1/{gw}``，POST JSON
  - 签名：HMAC-SHA256
      contentMD5   = base64(md5(请求体字节))
      stringToSign = "POST\\n{contentMD5}\\nS-Ca-App:{app_key}\\nS-Ca-Timestamp:{ts_ms}\\n{req_path}"
      signature    = base64(hmac_sha256(secret, stringToSign))
    请求头：S-Ca-App / S-Ca-Timestamp / Content-MD5 / S-Ca-Signature /
            S-Ca-Signature-Headers: "S-Ca-Timestamp,S-Ca-App"
  - 响应：``code`` 0=成功、非 0=异常（``Message`` 为文案）

接口：
  - query_coupon      商品（券）查询：到店 platform=2 / 到餐 bizLine=1，经纬度×1e6 整数
  - get_referral_link 取推广链接（skuViewId → 可跟单计佣的 deeplink）

``base_url`` 与 ``transport`` 可注入：测试指向进程内仿真网关（ASGITransport），
真实调用则用默认网关 + 环境变量密钥。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

import httpx

UNION_BASE_URL = "https://media.meituan.com"
UNION_BASE_PATH = "/cps_open/common/api/v1/"

# 业务类型枚举（到店团购用 platform=2 + bizLine=1 到餐）
PLATFORM_DAOJIA = 1
PLATFORM_DAODIAN = 2
BIZLINE_DAOCAN = 1

LINKTYPE_H5 = 1
LINKTYPE_DEEPLINK = 3


class UnionAPIError(RuntimeError):
    """联盟接口返回非 0 code 或网络失败。"""

    def __init__(self, code: int, message: str):
        super().__init__(f"{code}:{message}")
        self.code = code
        self.message = message


def sign_request(secret: str, app_key: str, ts_ms: str, req_path: str, body: bytes) -> tuple[str, str]:
    """按联盟协议计算 (Content-MD5, S-Ca-Signature)。独立函数便于测试与网关校验复用。"""
    content_md5 = base64.b64encode(hashlib.md5(body).digest()).decode()
    string_to_sign = (
        f"POST\n{content_md5}\nS-Ca-App:{app_key}\nS-Ca-Timestamp:{ts_ms}\n{req_path}"
    )
    signature = base64.b64encode(
        hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    ).decode()
    return content_md5, signature


class MeituanUnionClient:
    def __init__(
        self,
        app_key: str,
        secret: str,
        base_url: str = UNION_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 10.0,
    ):
        self.app_key = app_key
        self.secret = secret
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url, transport=transport, timeout=timeout_s
        )

    def close(self) -> None:
        self._client.close()

    # ---- 底层：签名 + POST ------------------------------------------------

    def _post(self, gw: str, payload: dict[str, Any]) -> dict[str, Any]:
        req_path = UNION_BASE_PATH + gw
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        ts_ms = str(int(time.time() * 1000))
        content_md5, signature = sign_request(self.secret, self.app_key, ts_ms, req_path, body)
        try:
            resp = self._client.post(
                req_path,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "S-Ca-App": self.app_key,
                    "S-Ca-Timestamp": ts_ms,
                    "Content-MD5": content_md5,
                    "S-Ca-Signature": signature,
                    "S-Ca-Signature-Headers": "S-Ca-Timestamp,S-Ca-App",
                },
            )
        except httpx.HTTPError as e:  # 网络层失败统一归为 UnionAPIError（上层可回退）
            raise UnionAPIError(-1, f"网络错误: {e}") from e
        if resp.status_code != 200:
            raise UnionAPIError(resp.status_code, f"HTTP {resp.status_code}")
        data = resp.json()
        if data.get("code", 0) != 0:
            raise UnionAPIError(data.get("code", -1), data.get("Message") or data.get("message", ""))
        return data

    # ---- 商品（券）查询 ----------------------------------------------------

    def query_coupon(
        self,
        *,
        platform: int = PLATFORM_DAODIAN,
        biz_line: int = BIZLINE_DAOCAN,
        latitude: float | None = None,
        longitude: float | None = None,
        search_text: str = "",
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """到店到餐商品券查询。经纬度按协议放大 1e6 取整。"""
        payload: dict[str, Any] = {
            "platform": platform,
            "bizLine": biz_line,
            "pageNo": page_no,
            "pageSize": page_size,
        }
        if latitude is not None and longitude is not None:
            payload["latitude"] = int(latitude * 1_000_000)
            payload["longitude"] = int(longitude * 1_000_000)
        if search_text:
            payload["searchText"] = search_text
        return self._post("query_coupon", payload)

    # ---- 取推广链接（跟单计佣 deeplink）-----------------------------------

    def get_referral_link(
        self,
        sku_view_id: str,
        *,
        platform: int = PLATFORM_DAODIAN,
        biz_line: int = BIZLINE_DAOCAN,
        link_type: int = LINKTYPE_H5,
        sid: str = "",
    ) -> str:
        payload: dict[str, Any] = {
            "platform": platform,
            "bizLine": biz_line,
            "skuViewId": sku_view_id,
            "linkType": link_type,
        }
        if sid:
            payload["sid"] = sid
        data = self._post("get_referral_link", payload)
        return data.get("data", "")
