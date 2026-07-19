"""抖音生活服务仿真网关（契约测试用）。

实现真实鉴权流程：``POST /oauth/client_token/`` 校验 client_key/secret 发 token，
商品查询校验 ``access-token`` 头；响应结构与官方一致（data.error_code、
products[].product/sku，金额单位**分**）。海底捞条目与美团联盟仿真数据同品牌
同人数——用于验证**跨平台同品牌对齐**（G-R2 地基）。
"""
from __future__ import annotations

from fastapi import FastAPI, Request

from app.tuangou.douyin_client import PRODUCT_ONLINE_PATH, TOKEN_PATH

FAKE_CLIENT_KEY = "dy_key_123"
FAKE_CLIENT_SECRET = "dy_secret_456"
FAKE_TOKEN = "dy_token_abc"

FAKE_PRODUCTS = [
    {   # 与美团联盟仿真的海底捞同品牌同人数 → 应对齐进同一可比单元，且更便宜
        "product": {"product_id": 7100001, "product_name": "海底捞欢聚4人餐",
                    "account_name": "海底捞", "status": 1,
                    "h5_url": "https://v.douyin.com/fake/hdl4p"},
        "sku": {"actual_amount": 38800, "origin_amount": 52000},   # 单位：分
        "sold_num": 2100,
    },
    {
        "product": {"product_id": 7100002, "product_name": "楠火锅双人餐",
                    "account_name": "楠火锅", "status": 1,
                    "h5_url": "https://v.douyin.com/fake/nan2p"},
        "sku": {"actual_amount": 15800, "origin_amount": 20600},
        "sold_num": 800,
    },
    {   # 下线商品 → 适配器应丢弃
        "product": {"product_id": 7100003, "product_name": "已下线套餐",
                    "account_name": "下线店", "status": 2},
        "sku": {"actual_amount": 9900, "origin_amount": 12000},
    },
]


def build_gateway() -> FastAPI:
    gw = FastAPI()

    @gw.post(TOKEN_PATH)
    async def client_token(request: Request):
        body = await request.json()
        if (body.get("client_key") != FAKE_CLIENT_KEY
                or body.get("client_secret") != FAKE_CLIENT_SECRET
                or body.get("grant_type") != "client_credential"):
            return {"data": {"error_code": 2190008, "description": "无效的 client_key 或 client_secret"}}
        return {"data": {"error_code": 0, "access_token": FAKE_TOKEN, "expires_in": 7200}}

    @gw.get(PRODUCT_ONLINE_PATH)
    async def product_online(request: Request):
        if request.headers.get("access-token") != FAKE_TOKEN:
            return {"data": {"error_code": 2190002, "description": "access token 无效"}}
        return {"data": {"error_code": 0, "description": "success",
                         "products": FAKE_PRODUCTS, "has_more": False, "next_cursor": 0}}

    return gw
