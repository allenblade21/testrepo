"""三平台 CPS 真实密钥统一冒烟脚本。

    python tools/cps_smoke.py meituan   # 需 MEITUAN_UNION_APPKEY/SECRET
    python tools/cps_smoke.py douyin    # 需 DOUYIN_CLIENT_KEY/SECRET[/DOUYIN_ACCOUNT_ID]
    python tools/cps_smoke.py alimama   # 需 ALIMAMA_APPKEY/SECRET/ADZONE_ID
    python tools/cps_smoke.py all       # 依次冒烟已配密钥的平台

通过后把对应源名加进 TUANGOU_SOURCE（逗号分隔可多源），如：
    export TUANGOU_SOURCE=union,douyin,alimama
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def smoke_meituan() -> bool:
    from app.tuangou.union_client import MeituanUnionClient, UnionAPIError
    key, sec = os.environ.get("MEITUAN_UNION_APPKEY", ""), os.environ.get("MEITUAN_UNION_SECRET", "")
    if not (key and sec):
        print("· meituan：未配置 MEITUAN_UNION_APPKEY/SECRET，跳过")
        return False
    c = MeituanUnionClient(key, sec)
    try:
        data = c.query_coupon(page_size=3)
    except UnionAPIError as e:
        print(f"✗ meituan 失败 code={e.code} message={e.message}")
        return False
    items = data.get("data") or []
    print(f"✓ meituan query_coupon 成功，{len(items)} 条")
    for it in items[:3]:
        d = it.get("couponPackDetail") or {}
        print(f"   - {d.get('name')} ¥{d.get('sellPrice')}")
    return True


def smoke_douyin() -> bool:
    from app.tuangou.douyin_client import DouyinAPIError, DouyinLifeClient
    key, sec = os.environ.get("DOUYIN_CLIENT_KEY", ""), os.environ.get("DOUYIN_CLIENT_SECRET", "")
    if not (key and sec):
        print("· douyin：未配置 DOUYIN_CLIENT_KEY/SECRET，跳过")
        return False
    c = DouyinLifeClient(key, sec, account_id=os.environ.get("DOUYIN_ACCOUNT_ID", ""))
    try:
        data = c.product_online_get(count=3)
    except DouyinAPIError as e:
        print(f"✗ douyin 失败 code={e.code} message={e.message}")
        print("  排查：① client_key/secret ② 生活服务能力是否开通 ③ account_id 是否必填")
        return False
    items = data.get("products") or []
    print(f"✓ douyin 商品查询成功，{len(items)} 条")
    for it in items[:3]:
        p, s = it.get("product") or {}, it.get("sku") or {}
        print(f"   - {p.get('product_name')} {int(s.get('actual_amount') or 0)/100:.2f}元")
    return True


def smoke_alimama() -> bool:
    from app.tuangou.alimama_client import AlimamaAPIError, AlimamaClient
    key = os.environ.get("ALIMAMA_APPKEY", "")
    sec = os.environ.get("ALIMAMA_SECRET", "")
    adzone = os.environ.get("ALIMAMA_ADZONE_ID", "")
    if not (key and sec and adzone):
        print("· alimama：未配置 ALIMAMA_APPKEY/SECRET/ADZONE_ID，跳过")
        return False
    c = AlimamaClient(key, sec, adzone)
    try:
        items = c.material_search(q="团购", page_size=3)
    except AlimamaAPIError as e:
        print(f"✗ alimama 失败 code={e.code} message={e.message}")
        print("  排查：① appkey/secret ② 淘客 API 权限 ③ adzone_id(推广位)是否有效")
        return False
    print(f"✓ alimama 物料搜索成功，{len(items)} 条")
    for it in items[:3]:
        print(f"   - [{it.get('shop_title')}] {it.get('title')} ¥{it.get('zk_final_price')}")
    return True


SMOKES = {"meituan": smoke_meituan, "douyin": smoke_douyin, "alimama": smoke_alimama}


def main() -> int:
    target = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    if target == "all":
        results = [fn() for fn in SMOKES.values()]
        return 0 if any(results) else 1
    if target not in SMOKES:
        print(f"用法：python tools/cps_smoke.py {{{'|'.join(SMOKES)}|all}}")
        return 2
    return 0 if SMOKES[target]() else 1


if __name__ == "__main__":
    raise SystemExit(main())
