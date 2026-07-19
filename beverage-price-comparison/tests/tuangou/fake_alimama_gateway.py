"""阿里妈妈/淘宝联盟（TOP 协议）仿真网关（契约测试用）。

按同一算法**严格校验 MD5 签名**（secret + 排序参数串 + secret → MD5 大写），
签名不对返回标准 ``error_response``；响应结构与 TOP 一致
（tbk_dg_material_optional_response.result_list.map_data，价格「元」字符串）。
"""
from __future__ import annotations

from fastapi import FastAPI, Request

from app.tuangou.alimama_client import top_sign

FAKE_APPKEY = "ali_key_123"
FAKE_SECRET = "ali_secret_456"
FAKE_ADZONE = "110001"

FAKE_MATERIALS = [
    {   # 与美团/抖音仿真同品牌同人数 → 三平台对齐
        "item_id": 88001, "title": "海底捞欢聚4人餐代金套餐",
        "shop_title": "海底捞", "zk_final_price": "408.00", "reserve_price": "520.00",
        "commission_rate": "350",
        "coupon_share_url": "//uland.taobao.com/fake/hdl4p",
    },
    {
        "item_id": 88002, "title": "西贝亲子2-3人套餐",
        "shop_title": "西贝莜面村", "zk_final_price": "288.00", "reserve_price": "368.00",
        "commission_rate": "300",
        "url": "//uland.taobao.com/fake/xibei",
    },
]


def build_gateway() -> FastAPI:
    gw = FastAPI()

    @gw.get("/router/rest")
    async def router(request: Request):
        params = dict(request.query_params)
        got_sign = params.pop("sign", "")
        if params.get("app_key") != FAKE_APPKEY:
            return {"error_response": {"code": 25, "msg": "Invalid app Key"}}
        if top_sign(FAKE_SECRET, params) != got_sign:
            return {"error_response": {"code": 25, "msg": "Invalid signature",
                                       "sub_code": "isv.invalid-signature"}}
        if params.get("method") != "taobao.tbk.dg.material.optional":
            return {"error_response": {"code": 22, "msg": "Invalid method"}}
        if params.get("adzone_id") != FAKE_ADZONE:
            return {"error_response": {"code": 15, "msg": "Invalid adzone_id"}}
        if int(params.get("page_no", 1)) > 1:
            return {"tbk_dg_material_optional_response": {"result_list": {"map_data": []}}}
        return {"tbk_dg_material_optional_response": {
            "result_list": {"map_data": FAKE_MATERIALS},
            "total_results": len(FAKE_MATERIALS)}}

    return gw
