"""美团联盟仿真网关（契约测试用）。

用 FastAPI 实现与官方网关一致的契约：
  - 路径 ``/cps_open/common/api/v1/query_coupon`` 与 ``get_referral_link``（POST JSON）
  - **按同一算法校验签名**（Content-MD5 + HMAC-SHA256 stringToSign）——签名不对
    返回 code=401，证明客户端签名实现自洽于协议；
  - 响应结构与官方一致：code/Message、hasNext、data[]（brandInfo /
    couponPackDetail(含官方拼写 ``originalPrlice``) / commissionInfo /
    availablePoiInfo）。

诚实边界：这是「契约仿真」，验证的是我方实现与**公开协议**一致；
与官方生产网关的最终一致性需真实密钥冒烟（tools/union_smoke.py）。
"""
from __future__ import annotations

from fastapi import FastAPI, Request

from app.tuangou.union_client import UNION_BASE_PATH, sign_request

FAKE_APPKEY = "test_appkey_123"
FAKE_SECRET = "test_secret_456"

# 仿真到店到餐商品券库（价格单位：元，与官方口径一致）
FAKE_COUPONS = [
    {
        "brandInfo": {"brandName": "海底捞"},
        "availablePoiInfo": {"availablePoiNum": 12},
        "commissionInfo": {"commissionPercent": 400, "commission": 15.92},
        "couponPackDetail": {
            "name": "海底捞欢聚4人餐", "skuViewId": "sku_hdl_001",
            "sellPrice": 398.0, "originalPrlice": 520.0,   # 官方字段拼写如此
            "saleVolume": "1000+", "saleStatus": True, "platform": 2,
        },
    },
    {
        "brandInfo": {"brandName": "西贝莜面村"},
        "availablePoiInfo": {"availablePoiNum": 6},
        "commissionInfo": {"commissionPercent": 350, "commission": 10.43},
        "couponPackDetail": {
            "name": "西贝家庭2-3人套餐", "skuViewId": "sku_xibei_001",
            "sellPrice": 298.0, "originalPrlice": 368.0,
            "saleVolume": "500+", "saleStatus": True, "platform": 2,
        },
    },
    {   # 无人数关键词 → 适配器应记为未知档 (1,99)
        "brandInfo": {"brandName": "丰茂烤串"},
        "availablePoiInfo": {"availablePoiNum": 3},
        "commissionInfo": {"commissionPercent": 300},
        "couponPackDetail": {
            "name": "丰茂烤串畅吃券", "skuViewId": "sku_fm_001",
            "sellPrice": 199.0, "originalPrlice": 249.0,
            "saleVolume": "100+", "saleStatus": True, "platform": 2,
        },
    },
    {   # 不可售 → 适配器应丢弃
        "brandInfo": {"brandName": "已下架店"},
        "couponPackDetail": {
            "name": "过期4人餐", "skuViewId": "sku_dead_001",
            "sellPrice": 100.0, "saleStatus": False, "platform": 2,
        },
    },
]


def build_gateway(strict_sign: bool = True) -> FastAPI:
    gw = FastAPI()

    async def _verify(request: Request, gw_name: str) -> dict | None:
        """校验签名；失败返回错误响应 dict，成功返回 None。"""
        if not strict_sign:
            return None
        body = await request.body()
        ts = request.headers.get("S-Ca-Timestamp", "")
        app = request.headers.get("S-Ca-App", "")
        got_md5 = request.headers.get("Content-MD5", "")
        got_sig = request.headers.get("S-Ca-Signature", "")
        if app != FAKE_APPKEY:
            return {"code": 401, "Message": "无效 appkey"}
        exp_md5, exp_sig = sign_request(FAKE_SECRET, app, ts, UNION_BASE_PATH + gw_name, body)
        if got_md5 != exp_md5:
            return {"code": 401, "Message": "Content-MD5 校验失败"}
        if got_sig != exp_sig:
            return {"code": 401, "Message": "签名校验失败"}
        return None

    @gw.post(UNION_BASE_PATH + "query_coupon")
    async def query_coupon(request: Request):
        err = await _verify(request, "query_coupon")
        if err:
            return err
        payload = await request.json()
        page = int(payload.get("pageNo", 1))
        if page > 1:  # 仿真只有一页
            return {"code": 0, "hasNext": False, "data": []}
        return {"code": 0, "hasNext": False, "data": FAKE_COUPONS}

    @gw.post(UNION_BASE_PATH + "get_referral_link")
    async def get_referral_link(request: Request):
        err = await _verify(request, "get_referral_link")
        if err:
            return err
        payload = await request.json()
        sku = payload.get("skuViewId", "")
        if not sku:
            return {"code": 400, "Message": "缺少 skuViewId"}
        sid = payload.get("sid", "")
        return {"code": 0, "data": f"https://dpurl.cn/fake/{sku}?utm={FAKE_APPKEY}&sid={sid}"}

    return gw
