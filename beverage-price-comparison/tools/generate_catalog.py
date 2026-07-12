"""产品库目录生成器（一次性运行，固定随机种子，输出 catalog_data.py）。

生成全商户饮品目录：12 家新商户 × 数十种饮品 × 2-3 平台上架，
用于支撑正式搜索 API 的全库检索。核心 4 家商户（永辉/罗森/喜茶/瑞幸）
不在此生成，保留在 seed_data.py 手工数据中，保证既有场景基线不变。

运行：python tools/generate_catalog.py  （在 beverage-price-comparison 目录下）
"""
import random

rng = random.Random(20260712)  # 固定种子，输出可复现

PLATFORMS = ["阿里闪购", "京东", "美团"]

# 瓶装商户（商超/便利店）
BOTTLED_MERCHANTS = [
    "沃尔玛(望京店)", "7-Eleven(国贸店)", "全家FamilyMart(三里屯店)",
    "盒马鲜生(大望路店)", "物美超市(学院路店)", "便利蜂(中关村店)",
]

# 瓶装标品： (品牌, 品名, 规格, 条码, 基准价分)
BOTTLED = [
    ("可口可乐", "无糖可乐", "500ml", "6901010102017", 350),
    ("百事可乐", "经典百事", "330ml×6罐", "6901011103024", 1350),
    ("雪碧", "柠檬味汽水", "500ml", "6901010104031", 350),
    ("芬达", "橙味汽水", "500ml", "6901010105048", 350),
    ("农夫山泉", "饮用天然水", "550ml", "6902020201055", 200),
    ("怡宝", "纯净水", "555ml", "6902021202062", 200),
    ("百岁山", "天然矿泉水", "570ml", "6902022203079", 300),
    ("元气森林", "白桃味苏打气泡水", "480ml", "6903030301086", 550),
    ("元气森林", "青瓜味苏打气泡水", "480ml", "6903030302093", 550),
    ("东方树叶", "茉莉花茶", "500ml", "6902020304100", 450),
    ("三得利", "无糖乌龙茶", "500ml", "6904040305117", 450),
    ("康师傅", "冰红茶", "500ml", "6905050306124", 300),
    ("统一", "绿茶", "500ml", "6905051307131", 300),
    ("王老吉", "凉茶", "310ml×6罐", "6906060308148", 1500),
    ("加多宝", "凉茶", "310ml×6罐", "6906061309155", 1450),
    ("红牛", "维生素功能饮料", "250ml×6罐", "6907070310162", 3600),
    ("脉动", "青柠口味维生素饮料", "600ml", "6908080311179", 450),
    ("维他", "柠檬茶", "250ml×6盒", "6909090312186", 1650),
    ("旺仔", "牛奶", "245ml×4罐", "6910100313193", 1800),
    ("伊利", "纯牛奶", "250ml×6盒", "6911110314209", 1900),
    ("蒙牛", "特仑苏纯牛奶", "250ml×6盒", "6912120315216", 2800),
    ("安慕希", "希腊风味酸奶", "205g×6盒", "6913130316223", 3200),
    ("美汁源", "果粒橙", "1.25L", "6914140317230", 900),
    ("汇源", "100%橙汁", "1L", "6915150318247", 1200),
    ("椰树", "椰汁", "245ml×6罐", "6916160319254", 2200),
    ("北冰洋", "橙味汽水", "248ml×6罐", "6917170320261", 2400),
]

# 现制商户及其菜单： 商户 -> [(品牌, 品名, 规格, 基准价分)]
MADE_MENUS = {
    "奈雪的茶(朝阳大悦城店)": [
        ("奈雪的茶", "霸气橙子", "大杯/少糖/去冰", 2800),
        ("奈雪的茶", "芝士草莓", "大杯/标准", 3200),
        ("奈雪的茶", "鸭屎香宝藏茶", "大杯/标准糖/常温", 2200),
    ],
    "古茗(望京SOHO店)": [
        ("古茗", "超A芝士葡萄", "大杯/正常冰", 1900),
        ("古茗", "椰椰芒芒", "大杯/少冰", 1700),
        ("古茗", "云雾轻乳茶", "中杯/标准", 1300),
    ],
    "蜜雪冰城(五道口店)": [
        ("蜜雪冰城", "珍珠奶茶", "大杯/标准糖", 800),
        ("蜜雪冰城", "冰鲜柠檬水", "大杯/少糖", 500),
        ("蜜雪冰城", "摇摇奶昔", "大杯/标准", 900),
    ],
    "星巴克(嘉里中心店)": [
        ("星巴克", "拿铁", "大杯/热", 3300),
        ("星巴克", "美式咖啡", "大杯/冰", 2800),
        ("星巴克", "抹茶星冰乐", "大杯/标准", 3600),
    ],
    "库迪咖啡(西二旗店)": [
        ("库迪咖啡", "生椰拿铁", "大杯/标准", 1200),
        ("库迪咖啡", "茉莉花香拿铁", "大杯/少冰", 1400),
    ],
    "CoCo都可(西单店)": [
        ("CoCo都可", "珍珠奶茶", "大杯/半糖", 1200),
        ("CoCo都可", "百香果双响炮", "大杯/去冰", 1400),
    ],
}


def gen_promos(base_price):
    """按价位随机生成 0-2 个真实感优惠。"""
    promos = []
    roll = rng.random()
    if roll < 0.30:
        pass  # 无优惠
    elif roll < 0.55:
        off = max(100, base_price // 10 // 100 * 100)
        threshold = base_price - rng.choice([0, 100, 200])
        promos.append(("满减", f"满{threshold // 100}减{off // 100}", off, threshold))
    elif roll < 0.75:
        val = rng.choice([100, 200, 300])
        promos.append(("补贴", "平台补贴", val, 0))
    elif roll < 0.90:
        val = rng.choice([200, 300, 500])
        threshold = base_price + rng.choice([0, 200, 500])
        promos.append(("券", f"满{threshold // 100}减{val // 100}", val, threshold))
    else:
        promos.append(("第二件半价", "第二件半价", 0, 0))
    return promos


def vary(base, pct=8):
    """价格在 ±pct% 内确定性浮动，取整到分位十位。"""
    delta = rng.randint(-pct, pct) / 100
    return max(100, int(base * (1 + delta)) // 10 * 10)


def gen():
    listings = []
    # 瓶装：每个商户随机上架 60% 的商品，每个商品在 2-3 个平台有售
    for merchant in BOTTLED_MERCHANTS:
        for brand, name, spec, barcode, base in BOTTLED:
            if rng.random() > 0.6:
                continue
            platforms = rng.sample(PLATFORMS, rng.choice([2, 2, 3]))
            for pf in platforms:
                sale = vary(base)
                listings.append(dict(
                    platform=pf, merchant=merchant, brand=brand, name=name,
                    spec=spec, type="bottled", barcode=barcode,
                    list_price=int(sale * 1.12) // 10 * 10, sale_price=sale,
                    promotions=gen_promos(sale),
                ))
    # 现制：每家门店菜单全量上架，每款在 2-3 个平台有售
    for merchant, menu in MADE_MENUS.items():
        for brand, name, spec, base in menu:
            platforms = rng.sample(PLATFORMS, rng.choice([2, 3, 3]))
            for pf in platforms:
                sale = vary(base, 6)
                listings.append(dict(
                    platform=pf, merchant=merchant, brand=brand, name=name,
                    spec=spec, type="made", barcode=None,
                    list_price=int(sale * 1.1) // 10 * 10, sale_price=sale,
                    promotions=gen_promos(sale),
                ))
    return listings


def main():
    listings = gen()
    lines = [
        '"""全商户饮品目录（由 tools/generate_catalog.py 以固定种子生成，勿手改）。"""',
        "",
        "LISTINGS_EXTRA = [",
    ]
    for l in listings:
        lines.append(f"    {l!r},")
    lines.append("]")
    with open("catalog_data.py", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    merchants = {l["merchant"] for l in listings}
    print(f"生成 {len(listings)} 条上架条目，覆盖 {len(merchants)} 家商户")


if __name__ == "__main__":
    main()
