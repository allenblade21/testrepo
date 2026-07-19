"""团购比价 API 路由（``/api/tuangou/*``，延续 ADR-009/ADR-013 分路径约定）。

  GET  /api/tuangou/restaurants  按位置/网格/菜系/人数召回门店
  GET  /api/tuangou/search       按餐厅名/菜系/人数搜套餐（相关度+分页）
  POST /api/tuangou/compare      同门店到手价+人均+明细+使用规则；跨门店 409

页面 ``/tuangou`` 由 G-R3 补（本期非目标）。数据 API 挂载到主 app，不另起服务。
"""
from __future__ import annotations

import re
from dataclasses import asdict

import geo_data
from fastapi import APIRouter, Body, HTTPException, Query

from .models import ComparableDeal, Restaurant
from .pricing import compute_deal_price
from .store import DealStore

router = APIRouter(prefix="/api/tuangou", tags=["tuangou"])

# 团购数据快照（可重建）——独立于饮品 store，双 Tab 下层隔离（ADR-010）
deal_store = DealStore()


def _normalize(text: str) -> str:
    return re.sub(r"[\s　/／·,，、()（）]+", "", text).lower()


def _check_grid(grid: str) -> None:
    if grid and grid not in geo_data.GRIDS:
        raise HTTPException(status_code=400, detail=f"未知商圈网格: {grid}")


def _party_matches(party: tuple[int, int], want: int | None) -> bool:
    """人数筛选：选「4 人」只召回适用 3-5（区间覆盖 4）的套餐。"""
    if not want:
        return True
    return party[0] <= want <= party[1]


# ---- 序列化 ----------------------------------------------------------------

def _restaurant_brief(r: Restaurant) -> dict:
    return {
        "id": r.id, "name": r.name, "brand": r.brand, "branch": r.branch,
        "cuisine": r.cuisine, "grid_id": r.grid_id, "rating": r.rating,
        "avg_price": r.avg_price_cents,
    }


def _deal_public(deal) -> dict:
    return {
        "id": deal.id, "title": deal.title, "platform": deal.platform,
        "deal_type": deal.deal_type, "party_size": list(deal.party_size),
        "list_price": deal.list_price_cents, "group_price": deal.group_price_cents,
        "has_menu_detail": deal.has_menu_detail, "deeplink": deal.deeplink,
    }


def _unit_brief(unit: ComparableDeal) -> dict:
    rest = deal_store.restaurants_by_id.get(unit.restaurant_id)
    return {
        "id": unit.id,
        "restaurant": _restaurant_brief(rest) if rest else {"id": unit.restaurant_id},
        "party_size": list(unit.party_size),
        "match_confidence": unit.match_confidence,
        "platforms": [d.platform for d in unit.deals],
        "deals": [_deal_public(d) for d in unit.deals],
    }


# ---- 比价编排（同门店约束第三层：跨门店 409）------------------------------

def compute_deal_comparison(unit: ComparableDeal, party_size: int | None = None) -> dict:
    """对一个可比单元逐平台算团购到手价+人均，评选最优。

    跨门店（单元内 restaurant_id 不唯一）→ 409。单平台时最优即其自身。
    """
    if len({d.restaurant_id for d in unit.deals}) != 1:
        raise HTTPException(status_code=409, detail="可比套餐单元跨门店，拒绝比价")

    rest = deal_store.restaurants_by_id.get(unit.restaurant_id)
    platforms = []
    for deal in unit.deals:
        r = compute_deal_price(deal, party_size)
        platforms.append({
            "platform": r.platform, "deal_id": r.deal_id, "title": deal.title,
            "group_price": r.group_price, "subsidy": r.subsidy, "extra_fee": r.extra_fee,
            "final_price": r.final_price, "people": r.people,
            "per_capita_price": r.per_capita_price,
            "has_menu_detail": r.has_menu_detail, "note": r.note,
            "deeplink": deal.deeplink,
            "menu_items": [asdict(m) for m in deal.menu_items],
            "usage_rule": asdict(deal.usage_rule),
            "breakdown": [{"label": ln.label, "amount": ln.amount} for ln in r.lines],
        })

    # 最优按人均到手价（单平台即其自身）
    cheapest = min(platforms, key=lambda p: p["per_capita_price"]) if platforms else None
    savings = None
    if cheapest and len(platforms) > 1:
        highest = max(platforms, key=lambda p: p["per_capita_price"])
        savings = highest["per_capita_price"] - cheapest["per_capita_price"]

    platforms.sort(key=lambda p: p["per_capita_price"])
    return {
        "unit_id": unit.id,
        "restaurant": _restaurant_brief(rest) if rest else {"id": unit.restaurant_id},
        "party_size": list(unit.party_size),
        "party_used": platforms[0]["people"] if platforms else None,
        "match_confidence": unit.match_confidence,
        "price_as_of": deal_store.snapshot_at_iso,
        "platforms": platforms,
        "cheapest": cheapest["platform"] if cheapest else None,
        "per_capita_savings": savings,
        "mock_notice": "本页价格为 Mock 演示数据，非真实价格",
    }


# ---- 接口 ------------------------------------------------------------------

@router.get("/health")
def tuangou_health():
    """团购数据源探针：当前源（mock/union/回退）、快照时间、数据量。"""
    return {
        "source": deal_store.source,
        "snapshot_at": deal_store.snapshot_at_iso,
        "rebuilds": deal_store.rebuild_count,
        "restaurants": len(deal_store.restaurants),
        "deals": len(deal_store.deals),
        "units": len(deal_store.units),
    }


@router.get("/restaurants")
def restaurants(
    q: str = Query("", description="餐厅名/品牌/菜系关键词，空=全部"),
    grid: str = Query("", description="商圈网格 ID；传入时只返回该网格门店"),
    cuisine: str = Query("", description="菜系过滤，如 火锅/烧烤/正餐"),
    party: int = Query(0, ge=0, le=99, description="用餐人数；只返回适用该人数的门店"),
):
    """按位置/网格/菜系/人数召回门店，按评分降序（G-R1 简版排名）。"""
    _check_grid(grid)
    nq = _normalize(q)
    ncuisine = _normalize(cuisine)
    out = []
    for r in deal_store.restaurants:
        if grid and r.grid_id != grid:
            continue
        if ncuisine and ncuisine not in _normalize(r.cuisine):
            continue
        if nq and nq not in _normalize(r.name + r.cuisine):
            continue
        rest_deals = [d for d in deal_store.deals if d.restaurant_id == r.id]
        if party:
            rest_deals = [d for d in rest_deals if _party_matches(d.party_size, party)]
        if party and not rest_deals:
            continue
        entry = _restaurant_brief(r)
        entry["deal_count"] = len(rest_deals)
        out.append(entry)
    out.sort(key=lambda e: -e["rating"])
    resp = {"query": q, "count": len(out), "restaurants": out}
    if grid:
        resp["grid"] = {"grid_id": grid, "name": geo_data.GRIDS[grid][0]}
    return resp


@router.get("/search")
def search(
    q: str = Query("", description="餐厅名/菜系/套餐名关键词，空=浏览全部"),
    party: int = Query(0, ge=0, le=99, description="用餐人数筛选（区间覆盖）"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """按关键词 + 人数搜团购套餐（可比单元），分页返回。"""
    nq = _normalize(q)
    hits = []
    for unit in deal_store.units:
        if not _party_matches(unit.party_size, party):
            continue
        rest = deal_store.restaurants_by_id.get(unit.restaurant_id)
        hay = _normalize(
            (rest.name + rest.cuisine if rest else unit.restaurant_id)
            + "".join(d.title for d in unit.deals)
        )
        if nq and nq not in hay:
            continue
        hits.append(unit)

    total = len(hits)
    page = hits[offset : offset + limit]
    return {
        "query": q, "party": party, "total": total,
        "count": len(page), "offset": offset,
        "results": [_unit_brief(u) for u in page],
    }


@router.post("/compare")
def compare(payload: dict = Body(..., description='{"unit_id": "...", "party_size": 4}')):
    """团购到手价比价：同门店逐平台算价+人均+明细+使用规则；跨门店 409。"""
    unit_id = payload.get("unit_id")
    if not unit_id:
        raise HTTPException(status_code=400, detail="缺少 unit_id")
    unit = deal_store.units_by_id.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="未找到该团购套餐单元")
    party = payload.get("party_size")
    party = int(party) if party else None
    return compute_deal_comparison(unit, party)
