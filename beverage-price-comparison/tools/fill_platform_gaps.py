"""平台缺口补齐脚本（一次性运行，确定性输出）。

读取 catalog_data.py，为生成目录中平台数 <3 的 (商户, 商品) 组合补上
缺失平台的上架条目，使生成目录全部三平台可比。

规则（全部确定性，可复现）：
  - 补齐价 = 该商品已有平台售价均值，取整到「角」；原价 = 售价×1.12
  - 优惠由 (商户+品名+平台) 的稳定哈希决定：40% 无优惠 / 30% 满减 / 30% 补贴
  - 仅处理 catalog_data.py（生成目录）；seed_data.py 手工数据不动——
    其中 3 个两平台单元为有意保留（缺货降级/商户隔离/起送场景演示位）

运行：python tools/fill_platform_gaps.py
"""
import hashlib

from catalog_data import LISTINGS_EXTRA

PLATFORMS = ["阿里闪购", "京东", "美团"]


def _stable_pct(key: str) -> int:
    """0-99 的稳定哈希值（跨运行一致）。"""
    return int(hashlib.sha1(key.encode("utf-8")).hexdigest(), 16) % 100


def fill():
    groups: dict[tuple, list[dict]] = {}
    for l in LISTINGS_EXTRA:
        groups.setdefault((l["merchant"], l["brand"], l["name"], l["spec"]), []).append(l)

    added = []
    for key, rows in groups.items():
        have = {r["platform"] for r in rows}
        missing = [p for p in PLATFORMS if p not in have]
        if not missing:
            continue
        avg_sale = sum(r["sale_price"] for r in rows) // len(rows) // 10 * 10
        rep = rows[0]
        for pf in missing:
            hkey = f"{key[0]}|{key[2]}|{pf}"
            roll = _stable_pct(hkey)
            if roll < 40:
                promos = []
            elif roll < 70:
                off = max(100, avg_sale // 10 // 100 * 100)
                threshold = avg_sale - 100
                promos = [("满减", f"满{threshold // 100}减{off // 100}", off, threshold)]
            else:
                promos = [("补贴", "平台补贴", 100 + roll % 3 * 100, 0)]
            added.append(dict(
                platform=pf, merchant=rep["merchant"], brand=rep["brand"],
                name=rep["name"], spec=rep["spec"], type=rep["type"],
                barcode=rep["barcode"],
                list_price=int(avg_sale * 1.12) // 10 * 10, sale_price=avg_sale,
                promotions=promos,
            ))
    return added


def main():
    added = fill()
    merged = LISTINGS_EXTRA + added
    lines = [
        '"""全商户饮品目录（tools/generate_catalog.py 生成 + fill_platform_gaps.py 补齐平台缺口，勿手改）。"""',
        "",
        "LISTINGS_EXTRA = [",
    ]
    for l in merged:
        lines.append(f"    {l!r},")
    lines.append("]")
    with open("catalog_data.py", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"补齐 {len(added)} 条缺失平台条目，目录 {len(LISTINGS_EXTRA)} → {len(merged)} 条")


if __name__ == "__main__":
    main()
