"""地理能力：坐标→网格解析、商户距离、地点排名分（PRD §4.3）。

排名分 = 0.35×平台覆盖度 + 0.25×销量分位 + 0.20×距离衰减 + 0.20×评分
（初始权重，上线后按点击/转化漏斗调参——权重集中于此便于配置化）
"""
from __future__ import annotations

import math

import geo_data

W_COVERAGE, W_SALES, W_DISTANCE, W_RATING = 0.35, 0.25, 0.20, 0.20


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """两坐标间大圆距离（km）。"""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def resolve_grid(lat: float, lng: float) -> dict | None:
    """坐标 → 最近网格（超出服务半径返回 None）。"""
    best = None
    for gid, (name, glat, glng) in geo_data.GRIDS.items():
        d = haversine_km(lat, lng, glat, glng)
        if best is None or d < best[2]:
            best = (gid, name, d)
    if best is None or best[2] > geo_data.GRID_RADIUS_KM:
        return None
    return {"grid_id": best[0], "grid_name": best[1], "distance_km": round(best[2], 2)}


def merchant_distance_km(merchant: str, grid_id: str) -> float:
    """商户到网格中心的距离。"""
    lat, lng, _g, _r, _s = geo_data.MERCHANT_GEO[merchant]
    _name, glat, glng = geo_data.GRIDS[grid_id]
    return haversine_km(lat, lng, glat, glng)


def _distance_decay(km: float) -> float:
    """0-1km=1.0 线性衰减至 3km=0.2，更远 0.1。"""
    if km <= 1.0:
        return 1.0
    if km <= 3.0:
        return 1.0 - (km - 1.0) * 0.4
    return 0.1


def merchant_rank(merchant: str, grid_id: str, avg_platforms: float,
                  max_sales_in_grid: int) -> dict:
    """商户在网格内的排名分与可解释因子。"""
    _lat, _lng, _g, rating, sales = geo_data.MERCHANT_GEO[merchant]
    # 平台覆盖度：3平台=1.0 / 2平台=0.6，间线性
    coverage = max(0.0, min(1.0, 0.6 + (avg_platforms - 2.0) * 0.4))
    sales_pct = sales / max_sales_in_grid if max_sales_in_grid else 0.0
    dist_km = merchant_distance_km(merchant, grid_id)
    decay = _distance_decay(dist_km)
    rating_norm = rating / 5.0
    score = (W_COVERAGE * coverage + W_SALES * sales_pct
             + W_DISTANCE * decay + W_RATING * rating_norm)
    return {
        "score": round(score, 4),
        "distance_km": round(dist_km, 2),
        "factors": {
            "coverage": round(coverage, 2),
            "sales_pct": round(sales_pct, 2),
            "distance_decay": round(decay, 2),
            "rating": rating,
        },
    }
