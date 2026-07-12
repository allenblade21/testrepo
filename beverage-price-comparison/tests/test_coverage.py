"""平台覆盖专项测试：两平台单元 + 美团不可用（缺席/起送拦截）逐单元用例。

背景：产品目录按现实建模——商户不会把每个商品在每个平台都上架
（tools/generate_catalog.py：瓶装 2/3 概率仅上 2 平台，现制 1/3），
因此存在大量两平台可比单元与缺美团单元。本文件用参数化为
**每一个**此类单元生成独立用例，保证降级比价行为全部正确：

  - 两平台单元（70 个）：仅在可得平台间比价，计数/商户/明细全部一致
  - 缺美团单元（23 个）：美团不参与报价，优雅降级
  - 美团在场但被商户级起送价拦截（喜茶）：灰显排除，不参与最优评选
  - 全库扫描：116 个单元的比价响应不变式逐一校验

目录为固定种子生成（数据不变），计数哨兵可安全钉死；
若日后有意重生成目录，需同步更新哨兵数字。
"""
import pytest
from fastapi.testclient import TestClient

import seed_data
from app.main import app, _units

client = TestClient(app)

# ---- 从真实目录动态发现三类单元 --------------------------------------------

TWO_PLATFORM = [u for u in _units if len(u.listings) == 2]
NO_MEITUAN = [u for u in _units if "美团" not in {l.platform for l in u.listings}]
MEITUAN_BLOCKED_X1 = [
    u for u in _units
    for l in u.listings
    if l.platform == "美团"
    and l.sale_price < seed_data.STORE_MIN_ORDER.get((l.merchant, "美团"), 0)
]

def _id(u):
    return f"{u.merchant}·{u.name}"


def _compare(u, qty=1):
    resp = client.get("/compare", params={"unit_id": u.id, "qty": qty})
    assert resp.status_code == 200, f"{_id(u)} 比价失败: {resp.text}"
    return resp.json()


def _assert_invariants(u, d):
    """任何单元比价响应必须满足的不变式。"""
    plats = d["platforms"]
    assert len(plats) == len(u.listings), "报价数必须等于该单元上架平台数"
    assert {p["merchant"] for p in plats} == {u.merchant}, "所有报价必须同商户"
    for p in plats:
        assert p["final_price"] >= 0, "到手价不得为负"
        assert sum(b["amount"] for b in p["breakdown"]) == p["final_price"], "明细必须对账"
        if not p["orderable"]:
            assert "起送" in p["note"], "不可下单必须给出起送原因"
    orderable = [p for p in plats if p["orderable"]]
    if orderable:
        assert d["cheapest"] == min(orderable, key=lambda p: p["final_price"])["platform"]
        if len(orderable) > 1:
            assert d["savings_vs_max"] == (
                max(p["final_price"] for p in orderable)
                - min(p["final_price"] for p in orderable)
            )
        else:
            assert d["savings_vs_max"] is None, "仅一个可下单平台时无节省额"
    else:
        assert d["cheapest"] is None
    # 排序：可下单在前且按到手价升序
    assert plats[: len(orderable)] == orderable
    finals = [p["final_price"] for p in orderable]
    assert finals == sorted(finals)


# ---- 哨兵：目录构成与已知情况数量（固定种子，回归即报警）------------------

def test_catalog_coverage_sentinel():
    assert len(_units) == 116
    assert len(TWO_PLATFORM) == 70, "两平台单元数变化：目录被改动或匹配回归"
    assert len(NO_MEITUAN) == 23
    assert len(MEITUAN_BLOCKED_X1) == 1
    assert MEITUAN_BLOCKED_X1[0].merchant == "喜茶(国贸店)"


# ---- 每个两平台单元一条独立用例 --------------------------------------------

@pytest.mark.parametrize("u", TWO_PLATFORM, ids=_id)
def test_two_platform_unit_compares_correctly(u):
    """两平台单元：仅在可得的 2 个平台间比价，全部不变式成立。"""
    d = _compare(u)
    assert len(d["platforms"]) == 2
    _assert_invariants(u, d)


# ---- 每个缺美团单元一条独立用例 --------------------------------------------

@pytest.mark.parametrize("u", NO_MEITUAN, ids=_id)
def test_unit_without_meituan_degrades_gracefully(u):
    """美团未上架：不出现在报价中，其余平台正常评选最优。"""
    d = _compare(u)
    assert "美团" not in {p["platform"] for p in d["platforms"]}
    assert d["cheapest"] is not None, "缺美团不应导致无法比价"
    _assert_invariants(u, d)


# ---- 美团在场但不能下单（起送拦截）------------------------------------------

@pytest.mark.parametrize("u", MEITUAN_BLOCKED_X1, ids=_id)
def test_meituan_present_but_blocked_by_min_order(u):
    """美团报价在场但 ×1 未达商户起送价：灰显排除、不参与最优。"""
    d = _compare(u, qty=1)
    mt = next(p for p in d["platforms"] if p["platform"] == "美团")
    assert mt["orderable"] is False
    assert "起送" in mt["note"]
    assert d["cheapest"] != "美团"
    assert d["platforms"][-1]["platform"] == "美团", "被拦截的美团必须排最后"
    _assert_invariants(u, d)
    # 数量解锁后美团恢复参与
    d2 = _compare(u, qty=2)
    mt2 = next(p for p in d2["platforms"] if p["platform"] == "美团")
    assert mt2["orderable"] is True


# ---- 全库扫描：116 个单元全部满足不变式 --------------------------------------

def test_full_catalog_sweep_all_units():
    for u in _units:
        _assert_invariants(u, _compare(u))
