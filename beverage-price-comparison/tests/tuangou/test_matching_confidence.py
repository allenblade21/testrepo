"""G-R2 套餐跨平台匹配置信度分级测试（多信号：标题相似 + 价位带）。

阈值 TITLE_SIM_THRESHOLD=0.6 / PRICE_BAND_THRESHOLD=0.75 被本文件锁定，
调整须同步这里与 matching.py 文档字符串。
"""
from app.tuangou.matching import (
    PRICE_BAND_THRESHOLD,
    TITLE_SIM_THRESHOLD,
    build_comparable_deals,
    title_similarity,
)
from app.tuangou.models import DEAL_SET, GroupDeal


def _deal(platform, title, price, rid="r_brand_测试店", party=(4, 4)):
    return GroupDeal(
        id=f"{platform}_{title}", restaurant_id=rid, platform=platform, title=title,
        deal_type=DEAL_SET, party_size=party,
        list_price_cents=price, group_price_cents=price,
    )


# ---- 标题相似度 -------------------------------------------------------------

def test_title_similarity_basics():
    assert title_similarity("海底捞欢聚4人餐", "海底捞欢聚4人餐") == 1.0
    assert title_similarity("海底捞欢聚4人餐", "海底捞欢聚4人餐代金套餐") >= TITLE_SIM_THRESHOLD
    assert title_similarity("海底捞欢聚4人餐", "楠火锅麻辣双人餐") < TITLE_SIM_THRESHOLD
    assert title_similarity("", "任意") == 0.0
    # 归一化吸收空格/括号/横线
    assert title_similarity("海底捞 欢聚（4人）餐", "海底捞欢聚4人餐") == 1.0


# ---- 精确：双信号都过 -------------------------------------------------------

def test_exact_when_title_and_price_close():
    units = build_comparable_deals([
        _deal("美团点评", "海底捞欢聚4人餐", 39800),
        _deal("抖音", "海底捞欢聚4人餐", 38800),
    ])
    assert len(units) == 1
    assert units[0].match_confidence == "精确"
    assert "标题相似" in units[0].match_note


# ---- 疑似：任一信号不过（且必须给可解释原因）--------------------------------

def test_fuzzy_when_titles_diverge():
    units = build_comparable_deals([
        _deal("美团点评", "海底捞欢聚4人餐", 39800),
        _deal("抖音", "招牌毛肚双拼套餐", 39800),
    ])
    assert units[0].match_confidence == "疑似"
    assert "标题相似度低" in units[0].match_note
    assert "套餐内容可能有差异" in units[0].match_note


def test_fuzzy_when_price_band_far():
    """标题一致但价差过大（100 vs 300 → 0.33 < 0.75）→ 疑似。"""
    units = build_comparable_deals([
        _deal("美团点评", "海底捞欢聚4人餐", 10000),
        _deal("抖音", "海底捞欢聚4人餐", 30000),
    ])
    assert units[0].match_confidence == "疑似"
    assert "价位差异大" in units[0].match_note


def test_price_band_boundary():
    """价位带恰在阈值 0.75 上（30000/40000）→ 精确；略低于 → 疑似。"""
    at = build_comparable_deals([
        _deal("美团点评", "同款4人餐", 30000), _deal("抖音", "同款4人餐", 40000)])
    assert 30000 / 40000 == PRICE_BAND_THRESHOLD
    assert at[0].match_confidence == "精确"
    below = build_comparable_deals([
        _deal("美团点评", "同款4人餐", 29900), _deal("抖音", "同款4人餐", 40000)])
    assert below[0].match_confidence == "疑似"


# ---- 单平台 / 三平台混合 ----------------------------------------------------

def test_single_platform_unaffected():
    units = build_comparable_deals([_deal("美团点评", "海底捞欢聚4人餐", 39800)])
    assert units[0].match_confidence == "单平台"
    assert units[0].match_note == ""


def test_three_platform_weakest_pair_decides():
    """三平台里只要有一对不过信号，就整体降为疑似（取最弱对）。"""
    units = build_comparable_deals([
        _deal("美团点评", "海底捞欢聚4人餐", 39800),
        _deal("抖音", "海底捞欢聚4人餐", 38800),
        _deal("口碑", "完全不同的名字", 40800),
    ])
    assert units[0].match_confidence == "疑似"
