"""地理能力测试：网格解析、网格过滤、地点排名（PRD §4 骨架）。"""
from fastapi.testclient import TestClient

import geo_data
from app.geo import haversine_km
from app.main import app, _units

client = TestClient(app)

WANGJING = (39.9960, 116.4740)   # 望京网格中心
SHANGHAI = (31.2304, 121.4737)   # 服务区外坐标


# ---- 基础数据完整性 ---------------------------------------------------------

def test_every_merchant_has_geo():
    """全库每个商户必须有坐标/网格/评分/月售（排名的数据前提）。"""
    merchants = {u.merchant for u in _units}
    assert merchants <= set(geo_data.MERCHANT_GEO), "存在无地理信息的商户"
    for m in merchants:
        lat, lng, grid, rating, sales = geo_data.MERCHANT_GEO[m]
        assert grid in geo_data.GRIDS
        assert 0 < rating <= 5 and sales > 0


def test_grids_endpoint():
    d = client.get("/grids").json()
    assert len(d["grids"]) == 4
    assert {g["grid_id"] for g in d["grids"]} == set(geo_data.GRIDS)


# ---- 坐标 → 网格解析 --------------------------------------------------------

def test_resolve_at_grid_center():
    d = client.get("/grid/resolve", params={"lat": WANGJING[0], "lng": WANGJING[1]}).json()
    assert d["in_service"] is True
    assert d["grid_id"] == "wangjing"
    assert d["distance_km"] < 0.1


def test_resolve_out_of_service():
    """服务区外坐标 → 明确的不在服务区提示（隐私：坐标不回显）。"""
    d = client.get("/grid/resolve", params={"lat": SHANGHAI[0], "lng": SHANGHAI[1]}).json()
    assert d["in_service"] is False
    assert "手动选择" in d["message"]


def test_resolve_picks_nearest_grid():
    """五道口与中关村相距约 2km：更靠近五道口的点必须解析为五道口。"""
    d = client.get("/grid/resolve", params={"lat": 39.9925, "lng": 116.3400}).json()
    assert d["grid_id"] == "wudaokou"


def test_resolve_rejects_invalid_coords():
    assert client.get("/grid/resolve", params={"lat": 91, "lng": 0}).status_code == 422


# ---- 网格过滤 ---------------------------------------------------------------

def test_search_grid_filter_only_returns_grid_merchants():
    d = client.get("/search", params={"q": "", "grid": "wangjing", "limit": 100}).json()
    assert d["total"] > 0
    wangjing_merchants = {m for m, g in geo_data.MERCHANT_GEO.items() if g[2] == "wangjing"}
    assert {r["merchant"] for r in d["results"]} <= wangjing_merchants


def test_search_without_grid_unchanged():
    """不传 grid → 全库行为完全不变（向后兼容基线）。"""
    d = client.get("/search", params={"q": ""}).json()
    assert d["total"] == len(_units) == 116


def test_search_unknown_grid_400():
    assert client.get("/search", params={"grid": "moon"}).status_code == 400


def test_merchants_grid_filter_zero_leakage():
    """网格聚合：范围外商户零泄漏（FR-B3）。"""
    for gid in geo_data.GRIDS:
        d = client.get("/merchants", params={"grid": gid}).json()
        expect = {m for m, g in geo_data.MERCHANT_GEO.items() if g[2] == gid}
        got = {e["merchant"] for e in d["merchants"]}
        assert got <= expect, f"{gid} 泄漏了范围外商户: {got - expect}"
        assert d["grid"]["grid_id"] == gid


# ---- 地点排名 ---------------------------------------------------------------

def test_merchants_grid_ranking_order_and_factors():
    """网格内商户按排名分降序，且因子可解释、分数与因子加权一致。"""
    d = client.get("/merchants", params={"grid": "wangjing"}).json()
    assert d["count"] >= 3
    scores = [e["rank"]["score"] for e in d["merchants"]]
    assert scores == sorted(scores, reverse=True), "必须按排名分降序"
    for e in d["merchants"]:
        r = e["rank"]
        assert 0 < r["score"] <= 1
        assert r["distance_km"] >= 0
        f = r["factors"]
        recomputed = round(0.35 * f["coverage"] + 0.25 * f["sales_pct"]
                           + 0.20 * f["distance_decay"] + 0.20 * f["rating"] / 5.0, 4)
        assert abs(recomputed - r["score"]) < 0.01, "分数必须与公示因子加权一致（可解释性）"


def test_ranking_coverage_factor_reflects_platforms():
    """平台覆盖度因子：三平台商户 coverage=1.0，两平台商户=0.6。"""
    d = client.get("/merchants", params={"grid": "guomao"}).json()
    by_m = {e["merchant"]: e for e in d["merchants"]}
    xicha = by_m["喜茶(国贸店)"]              # 唯一单元为两平台
    assert xicha["rank"]["factors"]["coverage"] == 0.6
    seven = by_m["7-Eleven(国贸店)"]          # 全部三平台
    assert seven["rank"]["factors"]["coverage"] == 1.0


def test_haversine_sanity():
    """望京到国贸直线约 9-11km（北京实际），公式量级必须正确。"""
    d = haversine_km(*WANGJING, 39.9088, 116.4590)
    assert 8 < d < 12