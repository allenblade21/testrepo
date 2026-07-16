"""种子数据构成哨兵（G-R1）。

钉死团购 Mock 数据构成：门店数 / 套餐数 / 可比单元数 / 缺菜品明细数。
若报警，说明数据/匹配被动了——先查原因，不要改哨兵迁就（铁律 6）。
"""
from app.tuangou import seed_deals
from app.tuangou.matching import build_comparable_deals


def test_seed_counts_pinned():
    assert len(seed_deals.RESTAURANTS) == 3, "门店数变化"
    assert len(seed_deals.DEALS) == 4, "套餐数变化"

    units = build_comparable_deals(seed_deals.DEALS)
    assert len(units) == 4, "可比单元数变化"

    without_menu = [d for d in seed_deals.DEALS if not d.has_menu_detail]
    assert len(without_menu) == 1, "缺菜品明细套餐数变化（降级演练用例）"


def test_seed_all_single_platform():
    """G-R1 单平台：所有套餐均为美团点评，所有单元置信度为单平台。"""
    from app.tuangou.models import MEITUAN_DIANPING
    assert {d.platform for d in seed_deals.DEALS} == {MEITUAN_DIANPING}
    units = build_comparable_deals(seed_deals.DEALS)
    assert {u.match_confidence for u in units} == {"单平台"}
