"""菜品明细缺失时的降级（G-R1，ADR-011）：不假装完整，如实标注。"""
from fastapi.testclient import TestClient


def _client():
    from app.main import app
    return TestClient(app)


def _unit_id(client, restaurant_id):
    res = client.get("/api/tuangou/search", params={"limit": 100}).json()["results"]
    return next(u["id"] for u in res if u["restaurant"]["id"] == restaurant_id)


def test_missing_menu_flagged_in_compare():
    """丰茂套餐无菜品明细 → has_menu_detail=False 且带降级说明。"""
    c = _client()
    uid = _unit_id(c, "r_fengmao_zgc")
    d = c.post("/api/tuangou/compare", json={"unit_id": uid}).json()
    plat = d["platforms"][0]
    assert plat["has_menu_detail"] is False
    assert "未含菜品明细" in plat["note"]
    assert plat["menu_items"] == []


def test_full_menu_not_flagged():
    """海底捞套餐有完整菜品 → has_menu_detail=True，无降级说明。"""
    c = _client()
    uid = _unit_id(c, "r_xibei_gm")
    d = c.post("/api/tuangou/compare", json={"unit_id": uid}).json()
    plat = d["platforms"][0]
    assert plat["has_menu_detail"] is True
    assert plat["note"] == ""
    assert len(plat["menu_items"]) > 0


def test_mock_notice_present():
    """诚实标注 Mock：比价结果必带非真实价格提示（铁律 5）。"""
    c = _client()
    uid = _unit_id(c, "r_haidilao_wj")
    d = c.post("/api/tuangou/compare", json={"unit_id": uid}).json()
    assert "非真实价格" in d["mock_notice"]
