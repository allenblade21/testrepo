"""种子数据（Mock）。

模拟三个平台上饮品的价格与优惠。数值为演示用途，非真实数据。
将来接入真实数据源时，本文件与 Mock 适配器一并替换即可，上层逻辑不变。

金额单位：分。
"""

# 各平台配送策略： (平台, 基础配送费, 满X分免配送)
DELIVERY = [
    ("阿里闪购", 300, 3900),
    ("京东", 500, 9900),
    ("美团", 500, 3900),
]

# 现制饮品起送价（按平台），分
MIN_ORDER = {"阿里闪购": 1500, "京东": 0, "美团": 2000}

# 商品条目。promotions 每项： (kind, desc, value, threshold)
# barcode 有值表示瓶装标品（按条码精确匹配）；None 表示现制饮品。
LISTINGS = [
    # ---- 可口可乐 330ml×6罐（瓶装标品，条码 6901010101010）----
    dict(platform="阿里闪购", brand="可口可乐", name="经典可乐", spec="330ml×6罐",
         type="bottled", barcode="6901010101010", list_price=1590, sale_price=1390,
         promotions=[("满减", "满15减2", 200, 1500)]),
    dict(platform="京东", brand="可口可乐", name="Coca-Cola 汽水", spec="330ml×6罐",
         type="bottled", barcode="6901010101010", list_price=1580, sale_price=1290,
         promotions=[("补贴", "平台补贴", 100, 0)]),
    dict(platform="美团", brand="可口可乐", name="可口可乐", spec="330ml×6罐",
         type="bottled", barcode="6901010101010", list_price=1600, sale_price=1450,
         promotions=[("第二件半价", "第二件半价", 0, 0)]),

    # ---- 农夫山泉 550ml×12（瓶装标品，条码 6902020202020）----
    dict(platform="阿里闪购", brand="农夫山泉", name="饮用天然水", spec="550ml×12瓶",
         type="bottled", barcode="6902020202020", list_price=2500, sale_price=2280,
         promotions=[("券", "满20减3", 300, 2000)]),
    dict(platform="京东", brand="农夫山泉", name="天然水", spec="550ml×12瓶",
         type="bottled", barcode="6902020202020", list_price=2490, sale_price=2190,
         promotions=[]),
    dict(platform="美团", brand="农夫山泉", name="农夫山泉天然水", spec="550ml×12瓶",
         type="bottled", barcode="6902020202020", list_price=2500, sale_price=2350,
         promotions=[("满减", "满23减3", 300, 2300)]),

    # ---- 元气森林 白桃味 480ml×6（瓶装标品，条码 6903030303030）----
    dict(platform="阿里闪购", brand="元气森林", name="白桃味苏打气泡水", spec="480ml×6瓶",
         type="bottled", barcode="6903030303030", list_price=3300, sale_price=2990,
         promotions=[("满减", "满28减3", 300, 2800)]),
    dict(platform="京东", brand="元气森林", name="白桃气泡水", spec="480ml×6瓶",
         type="bottled", barcode="6903030303030", list_price=3300, sale_price=3080,
         promotions=[("补贴", "平台补贴", 200, 0)]),
    # 美团缺货此款 → 展示「仅两平台可比」的情况

    # ---- 喜茶 多肉葡萄 大杯（现制饮品，无条码）----
    dict(platform="阿里闪购", brand="喜茶", name="多肉葡萄", spec="大杯/正常糖/去冰",
         type="made", barcode=None, list_price=2900, sale_price=2600,
         promotions=[("券", "新客立减3元", 300, 0)]),
    dict(platform="美团", brand="喜茶", name="多肉葡萄", spec="大杯 正常糖 去冰",
         type="made", barcode=None, list_price=2900, sale_price=2500,
         promotions=[("满减", "满25减4", 400, 2500)]),
    # 京东现制较少 → 该款仅两平台

    # ---- 瑞幸 生椰拿铁 大杯（现制饮品，无条码）----
    dict(platform="阿里闪购", brand="瑞幸咖啡", name="生椰拿铁", spec="大杯/标准",
         type="made", barcode=None, list_price=1900, sale_price=1690,
         promotions=[]),
    dict(platform="京东", brand="瑞幸咖啡", name="生椰拿铁", spec="大杯 标准",
         type="made", barcode=None, list_price=1900, sale_price=1590,
         promotions=[("补贴", "平台补贴", 100, 0)]),
    dict(platform="美团", brand="瑞幸咖啡", name="生椰拿铁", spec="大杯　标准",
         type="made", barcode=None, list_price=1900, sale_price=1780,
         promotions=[("券", "咖啡券减5", 500, 1500)]),
]
