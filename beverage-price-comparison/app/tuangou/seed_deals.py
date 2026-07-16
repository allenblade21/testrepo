"""团购 Mock 种子数据（G-R1，固定可复现，永不随机重生成）。

承载 G-R1 测试场景基线，构成被 ``test_tuangou_seed_sentinel`` 钉死——改动数据
即报警，先查原因不要改哨兵迁就（复用 seed_data 纪律）。

场景覆盖（对应设计文档 §8）：
  - 正常套餐（完整菜品+规则+补贴）：海底捞 4 人套餐
  - 附加费加项（包间费）：西贝包间套餐
  - 菜品明细缺失（演练降级）：丰茂烤串套餐（menu_items 为空）
  - 人数区间（未选人数取中值）：海底捞 3-5 人档、丰茂 3-4 人档
  - 补贴超额（到手价封顶不为负）：海底捞双人套餐（补贴 > 团购价）
  - 划线价（门市价 > 团购价，Mock 合规占位）：全部

所有价格为 Mock 演示数据，界面「非真实价格」标注不得移除（铁律 5）。
"""
from __future__ import annotations

from .models import (
    MEITUAN_DIANPING,
    DEAL_SET,
    GroupDeal,
    MenuItem,
    Restaurant,
    UsageRule,
)

# ---- 门店 ------------------------------------------------------------------

RESTAURANTS = [
    Restaurant(
        id="r_haidilao_wj", brand="海底捞", branch="望京店", cuisine="火锅",
        grid_id="wangjing", lat=39.9955, lng=116.4738, rating=4.8, avg_price_cents=12000,
    ),
    Restaurant(
        id="r_xibei_gm", brand="西贝莜面村", branch="国贸店", cuisine="正餐",
        grid_id="guomao", lat=39.9092, lng=116.4602, rating=4.6, avg_price_cents=8000,
    ),
    Restaurant(
        id="r_fengmao_zgc", brand="丰茂烤串", branch="中关村店", cuisine="烧烤",
        grid_id="zhongguancun", lat=39.9835, lng=116.3145, rating=4.5, avg_price_cents=7000,
    ),
]

# ---- 团购套餐（G-R1 单平台：美团点评）--------------------------------------

DEALS = [
    # 正常套餐：完整菜品 + 使用规则 + 补贴；人数区间 3-5（未选人数取中值 4）
    GroupDeal(
        id="d_hdl_4p", restaurant_id="r_haidilao_wj", platform=MEITUAN_DIANPING,
        title="海底捞欢聚 4 人套餐", deal_type=DEAL_SET, party_size=(3, 5),
        list_price_cents=52000, group_price_cents=39800, subsidy_cents=3000,
        menu_items=[
            MenuItem("番茄锅底", "1 份"),
            MenuItem("肥牛卷", "2 份", qty=2),
            MenuItem("虾滑", "1 份"),
            MenuItem("时蔬拼盘", "1 份"),
            MenuItem("小酥肉", "1 份"),
            MenuItem("果盘", "1 份", is_gift=True),
        ],
        usage_rule=UsageRule(
            time_windows=("全天",), need_reserve=True, per_table_limit=1,
            extra_fee_cents=0, stackable_voucher=False, refund_policy="随时退",
        ),
        deeplink="https://dpurl.cn/mock/hdl4p?cps=BPC",
    ),
    # 附加费加项：包间费 ¥50（不含在团购价内）；固定 4 人
    GroupDeal(
        id="d_xibei_room", restaurant_id="r_xibei_gm", platform=MEITUAN_DIANPING,
        title="西贝家庭聚餐包间套餐（4 人）", deal_type=DEAL_SET, party_size=(4, 4),
        list_price_cents=36800, group_price_cents=29800, subsidy_cents=0,
        menu_items=[
            MenuItem("莜面鱼鱼", "1 份"),
            MenuItem("牛大骨", "1 份"),
            MenuItem("羊肉串", "10 串", qty=10),
            MenuItem("沙棘汁", "1 扎"),
        ],
        usage_rule=UsageRule(
            time_windows=("工作日", "避开节假日"), need_reserve=True, per_table_limit=1,
            extra_fee_cents=5000, stackable_voucher=False, refund_policy="过期退",
        ),
        deeplink="https://dpurl.cn/mock/xibei?cps=BPC",
    ),
    # 菜品明细缺失（联盟未授权菜品字段）→ 降级；人数区间 3-4（中值 3）
    GroupDeal(
        id="d_fengmao", restaurant_id="r_fengmao_zgc", platform=MEITUAN_DIANPING,
        title="丰茂烤串 3-4 人欢聚套餐", deal_type=DEAL_SET, party_size=(3, 4),
        list_price_cents=24900, group_price_cents=19900, subsidy_cents=1000,
        menu_items=[],  # 缺失：has_menu_detail=False
        usage_rule=UsageRule(
            time_windows=("全天",), need_reserve=False, per_table_limit=2,
            extra_fee_cents=0, stackable_voucher=True, refund_policy="随时退",
        ),
        deeplink="https://dpurl.cn/mock/fengmao?cps=BPC",
    ),
    # 补贴超额（补贴 > 团购价）→ 到手价封顶为 0，不为负（复用饮品不变式）
    GroupDeal(
        id="d_hdl_2p", restaurant_id="r_haidilao_wj", platform=MEITUAN_DIANPING,
        title="海底捞双人套餐", deal_type=DEAL_SET, party_size=(2, 2),
        list_price_cents=21800, group_price_cents=16800, subsidy_cents=20000,
        menu_items=[
            MenuItem("番茄锅底", "1 份"),
            MenuItem("肥牛卷", "1 份"),
            MenuItem("宽粉", "1 份"),
        ],
        usage_rule=UsageRule(
            time_windows=("全天",), need_reserve=False, per_table_limit=1,
            extra_fee_cents=0, stackable_voucher=False, refund_policy="随时退",
        ),
        deeplink="https://dpurl.cn/mock/hdl2p?cps=BPC",
    ),
]
