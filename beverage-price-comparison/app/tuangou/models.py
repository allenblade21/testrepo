"""团购数据模型（G-R1）。

金额统一以「分」为单位存储（整数字段以 ``_cents`` 结尾），展示时换算为「元」。

比价边界字段是 ``restaurant_id``（门店）——等价于饮品的 ``merchant``。只有
**同一门店**在不同平台上的套餐才会被对齐比价（同门店约束，见 ADR-012）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---- 团购平台（独立于即时零售三平台）--------------------------------------

MEITUAN_DIANPING = "美团点评"
DOUYIN = "抖音"
KOUBEI = "口碑"
XIAOHONGSHU = "小红书"
KUAISHOU = "快手"

TUANGOU_PLATFORMS = [MEITUAN_DIANPING, DOUYIN, KOUBEI, XIAOHONGSHU, KUAISHOU]

# 套餐类型
DEAL_SET = "套餐"
DEAL_VOUCHER = "代金券"  # G-R1 不做，仅占位


@dataclass(frozen=True)
class MenuItem:
    """套餐内的一个菜品项。"""

    name: str
    spec: str = ""        # 份量/规格，如 "2 份" "500ml"
    qty: int = 1
    is_gift: bool = False


@dataclass(frozen=True)
class UsageRule:
    """团购使用规则（团购特有，透明展示以避免「买了不能用」）。

    ``extra_fee_cents`` 为不含在团购价内的附加费（包间费/服务费/茶位费），
    计入到手价的**加项**。
    """

    time_windows: tuple[str, ...] = ()   # 可用时段，如 ("工作日", "避开节假日")
    need_reserve: bool = False           # 是否需预约
    per_table_limit: int = 0             # 每桌可用张数，0=不限
    extra_fee_cents: int = 0             # 包间费/服务费/茶位费（分）
    stackable_voucher: bool = False      # 能否叠加代金券
    refund_policy: str = "过期退"        # 退款政策


@dataclass
class Restaurant:
    """餐厅门店。``id`` 是团购比价的硬边界字段，不可去。"""

    id: str
    brand: str            # 品牌，如「海底捞」
    branch: str           # 门店，如「望京店」
    cuisine: str          # 菜系：火锅/烧烤/正餐…
    grid_id: str          # 商圈网格（复用 geo）
    lat: float            # 坐标仅解析用，不落库（复用 ADR-006 隐私最小化）
    lng: float
    rating: float = 0.0
    avg_price_cents: int = 0   # 人均参考价（分）

    @property
    def name(self) -> str:
        return f"{self.brand}({self.branch})"


@dataclass
class GroupDeal:
    """团购套餐——可比单元的成员。

    ``restaurant_id`` 为所属门店（比价边界）。金额字段一律以分存储。
    ``menu_items`` 可能为空（联盟/CPS 授权未必含菜品明细）——此时 ``has_menu_detail``
    为 False，界面需标注「未含菜品明细」，匹配退化（见 ADR-011）。
    """

    id: str
    restaurant_id: str
    platform: str
    title: str
    deal_type: str                       # 套餐 / 代金券
    party_size: tuple[int, int]          # 适用人数区间 (min, max)
    list_price_cents: int                # 门市价/划线价（合规敏感，PRD §9）
    group_price_cents: int               # 团购价
    subsidy_cents: int = 0               # 平台补贴/神券可减（分）
    menu_items: list[MenuItem] = field(default_factory=list)
    usage_rule: UsageRule = field(default_factory=UsageRule)
    deeplink: str = ""                   # CPS 跳转下单链接（转化闭环）
    price_as_of: str = ""                # 价格快照时间（团购时效性强）

    @property
    def has_menu_detail(self) -> bool:
        return len(self.menu_items) > 0

    @property
    def party_midpoint(self) -> int:
        """未指定人数时，取人数区间中值算人均。"""
        lo, hi = self.party_size
        return max(1, (lo + hi) // 2)


@dataclass
class ComparableDeal:
    """可比套餐单元：同一门店、同一人数档下跨平台对齐的套餐集合。

    约束：单元内所有套餐必须属于**同一门店**（``restaurant_id`` 唯一）。
    G-R1 单平台，每个单元只含 1 条套餐，``match_confidence`` 恒为「单平台」。
    """

    id: str
    restaurant_id: str
    party_size: tuple[int, int]
    deals: list[GroupDeal] = field(default_factory=list)
    match_confidence: str = "单平台"     # 精确 / 疑似 / 单平台（G-R2 多信号判定）
    match_note: str = ""                 # 可解释说明（疑似时必须给差异原因）
