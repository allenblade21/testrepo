"""美团联盟真实密钥冒烟脚本。

拿到联盟 API 授权后，一条命令验证「密钥有效 + 能拉到真实商品 + 能取链」：

    export MEITUAN_UNION_APPKEY=你的appkey
    export MEITUAN_UNION_SECRET=你的secret
    python tools/union_smoke.py [搜索词]

通过后把 TUANGOU_SOURCE=union 加进服务环境即切真实数据（回退保护已内建）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tuangou.union_client import MeituanUnionClient, UnionAPIError  # noqa: E402


def main() -> int:
    app_key = os.environ.get("MEITUAN_UNION_APPKEY", "")
    secret = os.environ.get("MEITUAN_UNION_SECRET", "")
    if not app_key or not secret:
        print("✗ 请先设置 MEITUAN_UNION_APPKEY / MEITUAN_UNION_SECRET 环境变量")
        return 2

    search = sys.argv[1] if len(sys.argv) > 1 else ""
    c = MeituanUnionClient(app_key, secret)
    try:
        data = c.query_coupon(search_text=search, page_size=5)
    except UnionAPIError as e:
        print(f"✗ 查询失败 code={e.code} message={e.message}")
        print("  排查：① appkey/secret 是否正确 ② API 授权是否已开通 ③ 频次是否超限")
        return 1

    items = data.get("data") or []
    print(f"✓ query_coupon 成功，返回 {len(items)} 条（hasNext={data.get('hasNext')}）")
    for it in items[:5]:
        d = it.get("couponPackDetail") or {}
        brand = (it.get("brandInfo") or {}).get("brandName", "?")
        print(f"  - [{brand}] {d.get('name')} 售价¥{d.get('sellPrice')} sku={d.get('skuViewId')}")

    if items:
        sku = (items[0].get("couponPackDetail") or {}).get("skuViewId", "")
        if sku:
            try:
                link = c.get_referral_link(sku)
                print(f"✓ get_referral_link 成功：{link[:80]}...")
            except UnionAPIError as e:
                print(f"✗ 取链失败 code={e.code} message={e.message}")
                return 1
    print("\n全部通过。下一步：服务环境加 TUANGOU_SOURCE=union 即切真实数据。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
