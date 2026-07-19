"""CPS 接入·边界专项测试。

本文件锁住 6 个实际复现并修复的边界缺陷（勿删，防回归）：
  B1 yuan_to_cents(inf/nan) 曾抛 OverflowError 炸掉整个数据源
  B2 parse_party("0人餐") 曾产出 (0,0) 死档（永远匹配不到任何人数）
  B3 人均取整曾用银行家舍入（2487.5→2488 / 2486.5→2486 不一致）
  B4 /compare party_size 非法值曾 500（"abc"）或被静默吞掉（-5）
  B5 抖音金额字符串小数曾 ValueError 炸掉整个 fetch
  B6 网关返回非 JSON 的 200（HTML 错误页）曾抛裸 JSONDecodeError
外加：金额/人数/分页/搜索的常规边界。
"""
from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.tuangou.cps_common import PARTY_UNKNOWN, cents_to_int, parse_party, yuan_to_cents
from app.tuangou.models import DEAL_SET, GroupDeal
from app.tuangou.pricing import compute_deal_price


def _client():
    from app.main import app
    return TestClient(app)


def _deal(group, subsidy=0, extra=0, party=(2, 2)):
    from app.tuangou.models import UsageRule
    return GroupDeal(
        id="b", restaurant_id="r", platform="美团点评", title="t", deal_type=DEAL_SET,
        party_size=party, list_price_cents=group, group_price_cents=group,
        subsidy_cents=subsidy,
        usage_rule=UsageRule(extra_fee_cents=extra),
    )


# ---- B1: 金额换算对非有限数免疫 ---------------------------------------------

def test_yuan_to_cents_non_finite_and_junk():
    assert yuan_to_cents(float("inf")) == 0      # 曾 OverflowError
    assert yuan_to_cents(float("-inf")) == 0
    assert yuan_to_cents(float("nan")) == 0
    assert yuan_to_cents(None) == 0
    assert yuan_to_cents("abc") == 0
    assert yuan_to_cents("") == 0
    assert yuan_to_cents([]) == 0


def test_yuan_to_cents_normal_and_rounding():
    assert yuan_to_cents("408.00") == 40800
    assert yuan_to_cents(0.01) == 1              # 最小金额粒度
    assert yuan_to_cents("0.005") == 0 or yuan_to_cents("0.005") == 1  # 亚分粒度不崩溃
    assert yuan_to_cents(-5) == -500             # 负数原样换算（由调用方按 <=0 丢弃）
    assert yuan_to_cents(9999999.99) == 999999999


def test_cents_to_int_boundaries():
    assert cents_to_int("38850") == 38850
    assert cents_to_int(38850.0) == 38850
    assert cents_to_int("388.5") == 388 or cents_to_int("388.5") == 389  # 不崩溃即可（B5 的底层）
    assert cents_to_int(float("inf")) == 0
    assert cents_to_int(None) == 0
    assert cents_to_int("x") == 0


# ---- B2: 人数解析无死档 ------------------------------------------------------

def test_parse_party_zero_and_absurd_fall_back_to_unknown():
    assert parse_party("0人餐") == PARTY_UNKNOWN         # 曾 (0,0) 死档
    assert parse_party("0-0人") == PARTY_UNKNOWN
    assert parse_party("888人宴") == PARTY_UNKNOWN       # 越界下限
    assert parse_party("2-888人") == (2, 99)             # 上限截断到 99


def test_parse_party_normal_still_works():
    assert parse_party("4人餐") == (4, 4)
    assert parse_party("5-3人") == (3, 5)                # 反序纠正
    assert parse_party("99人团建") == (99, 99)           # 合法上限


# ---- B3: 人均半数进位一致 ----------------------------------------------------

def test_per_capita_half_up_consistent():
    # 4975 分 ÷ 2 = 2487.5 → 必须 2488；4973 ÷ 2 = 2486.5 → 必须 2487
    assert compute_deal_price(_deal(4975)).per_capita_price == 2488
    assert compute_deal_price(_deal(4973)).per_capita_price == 2487   # round() 会给 2486
    # 无 .5 情形不受影响
    assert compute_deal_price(_deal(4972)).per_capita_price == 2486
    assert compute_deal_price(_deal(100, party=(3, 3))).per_capita_price == 33   # 33.33 → 33
    assert compute_deal_price(_deal(101, party=(3, 3))).per_capita_price == 34   # 33.67 → 34


def test_pricing_extreme_party_values():
    d = _deal(10000, party=(2, 2))
    assert compute_deal_price(d, party_size=0).people == 2      # 0=未指定 → 中值
    assert compute_deal_price(d, party_size=-7).people == 2     # 负数 → 中值（引擎层防御）
    assert compute_deal_price(d, party_size=99).per_capita_price == (2 * 10000 + 99) // 198


def test_pricing_subsidy_exactly_equals_group_price():
    r = compute_deal_price(_deal(10000, subsidy=10000))
    assert r.final_price == 0 and r.subsidy == 10000            # 恰好扣平，不为负


def test_pricing_subsidy_over_with_extra_fee():
    """补贴超额扣平后，附加费仍要加上：0 + 5000 = 5000。"""
    r = compute_deal_price(_deal(10000, subsidy=99999, extra=5000))
    assert r.subsidy == 10000
    assert r.final_price == 5000
    total = r.lines[0].amount + sum(ln.amount for ln in r.lines[1:])
    assert total == r.final_price                                # 明细仍闭合


# ---- B4: /compare party_size 非法值 → 400（不再 500 / 静默）------------------

def _uid(c):
    return c.get("/api/tuangou/search").json()["results"][0]["id"]


def test_compare_party_size_invalid_string_400():
    c = _client()
    r = c.post("/api/tuangou/compare", json={"unit_id": _uid(c), "party_size": "abc"})
    assert r.status_code == 400                                  # 曾 500
    assert "party_size" in r.json()["detail"]


def test_compare_party_size_negative_400():
    c = _client()
    r = c.post("/api/tuangou/compare", json={"unit_id": _uid(c), "party_size": -5})
    assert r.status_code == 400                                  # 曾 200 静默吞掉


def test_compare_party_size_out_of_range_400():
    c = _client()
    assert c.post("/api/tuangou/compare",
                  json={"unit_id": _uid(c), "party_size": 100}).status_code == 400


def test_compare_party_size_none_zero_ok():
    c = _client()
    uid = _uid(c)
    for v in (None, 0):
        r = c.post("/api/tuangou/compare", json={"unit_id": uid, "party_size": v})
        assert r.status_code == 200
        assert r.json()["party_used"] >= 1                       # 落到中值


def test_compare_party_size_boundary_1_and_99_ok():
    c = _client()
    uid = _uid(c)
    for v in (1, 99):
        assert c.post("/api/tuangou/compare",
                      json={"unit_id": uid, "party_size": v}).status_code == 200


# ---- B5: 抖音脏金额只丢弃该条，不炸整个源 -----------------------------------

def test_douyin_dirty_amount_drops_item_not_source():
    from app.tuangou.douyin_adapter import DouyinLifeAdapter

    class _StubClient:
        def product_online_get(self, cursor=0, count=50):
            return {"products": [
                {"product": {"product_id": 1, "product_name": "正常4人餐",
                             "account_name": "A店", "status": 1},
                 "sku": {"actual_amount": 38800, "origin_amount": 52000}},
                {"product": {"product_id": 2, "product_name": "脏数据套餐",
                             "account_name": "B店", "status": 1},
                 "sku": {"actual_amount": "not-a-number"}},        # 曾 ValueError 炸 fetch
                {"product": {"product_id": 3, "product_name": "inf套餐",
                             "account_name": "C店", "status": 1},
                 "sku": {"actual_amount": float("inf")}},
            ], "has_more": False}

    deals = DouyinLifeAdapter(_StubClient(), grid_id="wangjing").fetch_deals()
    assert [d.title for d in deals] == ["正常4人餐"]              # 脏条目被丢弃，源存活


# ---- B6: 非 JSON 200 响应 → 结构化 APIError（三客户端一致）-------------------

def _html_transport():
    return httpx.MockTransport(lambda req: httpx.Response(200, text="<html>bad gateway</html>"))


def test_union_client_non_json_response():
    from app.tuangou.union_client import MeituanUnionClient, UnionAPIError
    c = MeituanUnionClient("k", "s", transport=_html_transport())
    with pytest.raises(UnionAPIError) as ei:
        c.query_coupon()
    assert ei.value.code == -2                                   # 曾裸 JSONDecodeError
    c.close()


def test_douyin_client_non_json_response():
    from app.tuangou.douyin_client import DouyinAPIError, DouyinLifeClient
    c = DouyinLifeClient("k", "s", transport=_html_transport())
    with pytest.raises(DouyinAPIError) as ei:
        c.product_online_get()
    assert ei.value.code == -2
    c.close()


def test_alimama_client_non_json_response():
    from app.tuangou.alimama_client import AlimamaAPIError, AlimamaClient
    c = AlimamaClient("k", "s", "1", transport=_html_transport())
    with pytest.raises(AlimamaAPIError) as ei:
        c.material_search()
    assert ei.value.code == -2
    c.close()


# ---- 常规边界：API 参数校验 / 分页 / 空集 ------------------------------------

def test_search_pagination_boundaries():
    c = _client()
    total = c.get("/api/tuangou/search").json()["total"]
    # offset 超总数 → 空页不报错
    d = c.get("/api/tuangou/search", params={"offset": total + 100}).json()
    assert d["count"] == 0 and d["total"] == total
    # limit 越界 → 422（FastAPI 参数校验）
    assert c.get("/api/tuangou/search", params={"limit": 0}).status_code == 422
    assert c.get("/api/tuangou/search", params={"limit": 101}).status_code == 422
    assert c.get("/api/tuangou/search", params={"offset": -1}).status_code == 422


def test_restaurants_party_boundaries():
    c = _client()
    assert c.get("/api/tuangou/restaurants", params={"party": 99}).status_code == 200
    assert c.get("/api/tuangou/restaurants", params={"party": 100}).status_code == 422
    assert c.get("/api/tuangou/restaurants", params={"party": -1}).status_code == 422
    # 无人覆盖的人数 → 空集不报错
    d = c.get("/api/tuangou/restaurants", params={"party": 99}).json()
    assert d["count"] == 0


def test_search_party_no_match_empty():
    c = _client()
    d = c.get("/api/tuangou/search", params={"party": 99}).json()
    assert d["total"] == 0 and d["results"] == []


def test_build_units_empty_input():
    from app.tuangou.matching import build_comparable_deals
    assert build_comparable_deals([]) == []


def test_compare_body_not_object_422():
    c = _client()
    assert c.post("/api/tuangou/compare", json=[1, 2, 3]).status_code == 422
