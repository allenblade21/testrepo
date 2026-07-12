"""FastAPI 入口 + 比价编排。

启动时：建库 → 实例化三平台适配器 → 拉取条目 → 匹配成可比单元。
接口：
  GET /search   关键词召回可比饮品
  GET /compare  某饮品在三平台的到手价对比
  GET /health   健康检查
  GET /         前端页面
"""
from __future__ import annotations

import os

import seed_data
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse

from .adapters.alibaba import AlibabaAdapter
from .adapters.jd import JDAdapter
from .adapters.meituan import MeituanAdapter
from .db import init_db
from .matching import build_units, search_units
from .models import ComparableUnit, Promotion
from .pricing import compute_price

app = FastAPI(title="饮品比价系统", version="0.1.0")

_WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")

# ---- 启动时初始化 -------------------------------------------------------
_conn = init_db()
_adapters = [AlibabaAdapter(_conn), JDAdapter(_conn), MeituanAdapter(_conn)]
_delivery = {a.platform: a.fetch_delivery() for a in _adapters}

_all_listings = []
for _a in _adapters:
    _all_listings.extend(_a.fetch_listings())

_units: list[ComparableUnit] = build_units(_all_listings)
_units_by_id = {u.id: u for u in _units}


def _unit_brief(unit: ComparableUnit) -> dict:
    return {
        "id": unit.id,
        "merchant": unit.merchant,
        "name": unit.name,
        "brand": unit.brand,
        "spec": unit.spec,
        "type": unit.type,
        "platforms": [l.platform for l in unit.listings],
    }


@app.get("/health")
def health():
    return {"status": "ok", "units": len(_units), "listings": len(_all_listings)}


@app.get("/search")
def search(
    q: str = Query("", description="关键词（商品名/品牌/商户名，空=浏览全库）"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """全商户产品库搜索：相关度排序 + 分页。"""
    hits = search_units(_units, q)
    page = hits[offset : offset + limit]
    return {
        "query": q,
        "total": len(hits),          # 命中总数
        "count": len(page),          # 本页返回数
        "offset": offset,
        "results": [_unit_brief(u) for u in page],
    }


@app.get("/compare")
def compare(
    unit_id: str,
    qty: int = Query(1, ge=1, le=99),
    include_delivery: bool = True,
    first_order: str = Query("", description="当日尚未下过单的平台，逗号分隔；这些平台享每日首单券"),
):
    unit = _units_by_id.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="未找到该饮品")

    # 商户约束（双保险）：比价的所有条目必须属于同一商户
    if len({l.merchant for l in unit.listings}) != 1:
        raise HTTPException(status_code=409, detail="可比单元跨商户，拒绝比价")

    first_order_set = {p.strip() for p in first_order.split(",") if p.strip()}

    platforms = []
    for listing in unit.listings:
        # 起送价为商户×平台级门店属性（商家自设），对所有品类生效；未配置=0
        min_order = seed_data.STORE_MIN_ORDER.get((listing.merchant, listing.platform), 0)
        coupon = None
        if listing.platform in first_order_set:
            cfg = seed_data.FIRST_ORDER_COUPON.get(listing.platform)
            if cfg:
                coupon = Promotion(kind="首单券", desc=cfg[0], value=cfg[1], threshold=cfg[2])
        result = compute_price(
            listing,
            _delivery[listing.platform],
            quantity=qty,
            include_delivery=include_delivery,
            min_order=min_order,
            first_order_coupon=coupon,
        )
        platforms.append(
            {
                "platform": result.platform,
                "merchant": listing.merchant,
                "final_price": result.final_price,
                "subtotal": result.subtotal,
                "discount_total": result.discount_total,
                "delivery_fee": result.delivery_fee,
                "orderable": result.orderable,
                "note": result.note,
                "breakdown": [{"label": ln.label, "amount": ln.amount} for ln in result.lines],
            }
        )

    orderable = [p for p in platforms if p["orderable"]]
    cheapest = min(orderable, key=lambda p: p["final_price"]) if orderable else None
    savings = None
    if cheapest and len(orderable) > 1:
        highest = max(orderable, key=lambda p: p["final_price"])
        savings = highest["final_price"] - cheapest["final_price"]

    # 按到手价升序展示，不可下单排最后
    platforms.sort(key=lambda p: (not p["orderable"], p["final_price"]))

    return {
        "beverage": _unit_brief(unit),
        "quantity": qty,
        "include_delivery": include_delivery,
        "first_order": sorted(first_order_set),
        "platforms": platforms,
        "cheapest": cheapest["platform"] if cheapest else None,
        "savings_vs_max": savings,
    }


# ---- 两个界面入口 ---------------------------------------------------------
# 入口1: /test  测试 + 报表控制台（内部）
# 入口2: /      正式客户使用界面

@app.get("/")
def customer_app():
    return FileResponse(os.path.join(_WEB_DIR, "app.html"))


@app.get("/test")
def test_console():
    return FileResponse(os.path.join(_WEB_DIR, "test.html"))
