"""抖音 + 阿里妈妈真实接入·端到端自动化测试（与美团联盟同一套路）。

各起一个仿真网关（真 HTTP + 真实鉴权方式：抖音 client_token 流程 /
阿里 TOP MD5 签名严格校验），验证客户端→鉴权→请求→解析→映射全链路；
最后**三源并跑**：同品牌同人数的「海底捞欢聚4人餐」跨三平台对齐进同一
可比单元（置信度=疑似），/compare 返回三平台并排与最优。
"""
from __future__ import annotations

import socket
import threading
import time

import pytest
import uvicorn

from app.tuangou.alimama_client import AlimamaAPIError, AlimamaClient, top_sign
from app.tuangou.alimama_adapter import AlimamaAdapter
from app.tuangou.douyin_client import DouyinAPIError, DouyinLifeClient
from app.tuangou.douyin_adapter import DouyinLifeAdapter
from tests.tuangou import fake_alimama_gateway as ali_gw
from tests.tuangou import fake_douyin_gateway as dy_gw
from tests.tuangou import fake_union_gateway as mt_gw


def _serve(app):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("仿真网关启动超时")
        time.sleep(0.05)
    return server, t, f"http://127.0.0.1:{port}"


@pytest.fixture(scope="module")
def gateways():
    started = [_serve(dy_gw.build_gateway()), _serve(ali_gw.build_gateway()),
               _serve(mt_gw.build_gateway())]
    yield {"douyin": started[0][2], "alimama": started[1][2], "union": started[2][2]}
    for server, t, _ in started:
        server.should_exit = True
        t.join(timeout=5)


# ---- 抖音：token 流程 + 映射（金额单位分，勿再 ×100）------------------------

def test_douyin_token_and_query(gateways):
    c = DouyinLifeClient(dy_gw.FAKE_CLIENT_KEY, dy_gw.FAKE_CLIENT_SECRET,
                         base_url=gateways["douyin"])
    data = c.product_online_get()
    assert len(data["products"]) == 3
    c.close()


def test_douyin_bad_secret_rejected(gateways):
    c = DouyinLifeClient(dy_gw.FAKE_CLIENT_KEY, "wrong", base_url=gateways["douyin"])
    with pytest.raises(DouyinAPIError) as ei:
        c.product_online_get()
    assert ei.value.code == 2190008
    c.close()


def test_douyin_adapter_mapping(gateways):
    c = DouyinLifeClient(dy_gw.FAKE_CLIENT_KEY, dy_gw.FAKE_CLIENT_SECRET,
                         base_url=gateways["douyin"])
    deals = DouyinLifeAdapter(c, grid_id="wangjing").fetch_deals()
    assert len(deals) == 2                          # 下线商品被丢弃
    hdl = next(d for d in deals if "海底捞" in d.title)
    assert hdl.group_price_cents == 38800           # 已是分：不得再 ×100
    assert hdl.list_price_cents == 52000
    assert hdl.party_size == (4, 4)
    assert hdl.platform == "抖音"
    assert hdl.has_menu_detail is False
    assert hdl.restaurant_id == "r_brand_海底捞"     # 平台无关伪门店（可跨平台对齐）
    assert hdl.deeplink.startswith("https://v.douyin.com/")
    c.close()


# ---- 阿里妈妈：TOP MD5 签名 + 映射 ------------------------------------------

def test_top_sign_vector():
    """独立向量：md5(secret + k1v1k2v2(排序) + secret) 大写。"""
    import hashlib
    params = {"b": "2", "a": "1"}
    expect = hashlib.md5("SECa1b2SEC".encode()).hexdigest().upper()
    assert top_sign("SEC", params) == expect


def test_alimama_query_and_bad_sign(gateways):
    ok = AlimamaClient(ali_gw.FAKE_APPKEY, ali_gw.FAKE_SECRET, ali_gw.FAKE_ADZONE,
                       base_url=gateways["alimama"])
    items = ok.material_search(q="团购")
    assert len(items) == 2
    ok.close()

    bad = AlimamaClient(ali_gw.FAKE_APPKEY, "wrong", ali_gw.FAKE_ADZONE,
                        base_url=gateways["alimama"])
    with pytest.raises(AlimamaAPIError) as ei:
        bad.material_search()
    assert ei.value.code == 25                      # Invalid signature
    bad.close()


def test_alimama_adapter_mapping(gateways):
    c = AlimamaClient(ali_gw.FAKE_APPKEY, ali_gw.FAKE_SECRET, ali_gw.FAKE_ADZONE,
                      base_url=gateways["alimama"])
    deals = AlimamaAdapter(c, grid_id="wangjing").fetch_deals()
    assert len(deals) == 2
    hdl = next(d for d in deals if "海底捞" in d.title)
    assert hdl.group_price_cents == 40800           # "408.00" 元字符串 → 分
    assert hdl.platform == "口碑"
    assert hdl.restaurant_id == "r_brand_海底捞"
    assert hdl.deeplink.startswith("https://uland.taobao.com/")   # // 补协议
    xibei = next(d for d in deals if "西贝" in d.title)
    assert xibei.party_size == (2, 3)
    c.close()


# ---- 三源并跑：跨平台对齐 + 全链路比价 --------------------------------------

def _env_three_sources(monkeypatch, gw):
    monkeypatch.setenv("TUANGOU_SOURCE", "union,douyin,alimama")
    monkeypatch.setenv("MEITUAN_UNION_APPKEY", mt_gw.FAKE_APPKEY)
    monkeypatch.setenv("MEITUAN_UNION_SECRET", mt_gw.FAKE_SECRET)
    monkeypatch.setenv("MEITUAN_UNION_BASE", gw["union"])
    monkeypatch.setenv("DOUYIN_CLIENT_KEY", dy_gw.FAKE_CLIENT_KEY)
    monkeypatch.setenv("DOUYIN_CLIENT_SECRET", dy_gw.FAKE_CLIENT_SECRET)
    monkeypatch.setenv("DOUYIN_BASE", gw["douyin"])
    monkeypatch.setenv("ALIMAMA_APPKEY", ali_gw.FAKE_APPKEY)
    monkeypatch.setenv("ALIMAMA_SECRET", ali_gw.FAKE_SECRET)
    monkeypatch.setenv("ALIMAMA_ADZONE_ID", ali_gw.FAKE_ADZONE)
    monkeypatch.setenv("ALIMAMA_BASE", gw["alimama"])


def test_three_sources_cross_platform_unit(monkeypatch, gateways):
    """海底捞4人餐来自三个平台 → 对齐进同一单元，置信度=疑似。"""
    from app.tuangou.store import DealStore
    _env_three_sources(monkeypatch, gateways)
    store = DealStore()
    assert store.source == "union+douyin+alimama"
    assert len(store.deals) == 3 + 2 + 2            # 美团3 + 抖音2 + 阿里2

    hdl_unit = next(u for u in store.units
                    if u.restaurant_id == "r_brand_海底捞" and u.party_size == (4, 4))
    assert len(hdl_unit.deals) == 3                 # 三平台对齐
    assert hdl_unit.match_confidence == "疑似"       # 跨平台语义匹配未验真 → 如实标注
    assert {d.platform for d in hdl_unit.deals} == {"美团点评", "抖音", "口碑"}


def test_three_sources_compare_cheapest(monkeypatch, gateways):
    """跨平台比价：抖音 388.00 最便宜；人均与节省额正确。"""
    from app.tuangou.store import DealStore
    from app.tuangou.routes import compute_deal_comparison
    _env_three_sources(monkeypatch, gateways)
    store = DealStore()
    import app.tuangou.routes as routes_mod
    monkeypatch.setattr(routes_mod, "deal_store", store)

    unit = next(u for u in store.units
                if u.restaurant_id == "r_brand_海底捞" and u.party_size == (4, 4))
    d = compute_deal_comparison(unit, party_size=4)
    assert d["cheapest"] == "抖音"
    prices = {p["platform"]: p["per_capita_price"] for p in d["platforms"]}
    assert prices == {"抖音": 9700, "美团点评": 9950, "口碑": 10200}
    assert d["per_capita_savings"] == 10200 - 9700
    assert all(p["has_menu_detail"] is False for p in d["platforms"])   # 三源均降级


def test_partial_source_failure_keeps_others(monkeypatch, gateways):
    """抖音密钥错 → 只跳过抖音，美团+阿里照常（单源失败不拖垮）。"""
    from app.tuangou.store import DealStore
    _env_three_sources(monkeypatch, gateways)
    monkeypatch.setenv("DOUYIN_CLIENT_SECRET", "wrong")
    store = DealStore()
    assert "union" in store.source and "alimama" in store.source
    assert "douyin" in store.source and "失败跳过" in store.source
    assert len(store.deals) == 3 + 2                # 抖音缺席，其余照常
