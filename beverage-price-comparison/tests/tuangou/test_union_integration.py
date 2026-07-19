"""美团联盟真实接入·端到端自动化测试。

在本地起一个**仿真联盟网关**（真 HTTP 服务 + 与协议一致的签名校验），
客户端→签名→请求→解析→映射→Store 全链路自动化验证：

  1. 签名算法向量（独立复算 HMAC-SHA256 / Content-MD5）
  2. 客户端调 query_coupon / get_referral_link 走通（签名被网关严格校验）
  3. 适配器映射：元→分、官方 originalPrlice 拼写、人数解析、
     不可售丢弃、无菜品明细降级、deeplink 归因链接
  4. DealStore 按环境变量切 union 源；密钥错误/网关不可达时回退 Mock 保活
  5. （可选）设置真实密钥后跑真网关冒烟（默认 skip）

诚实边界：仿真网关验证的是与**公开协议**的一致性；与官方生产网关的最终
一致性需真实密钥冒烟（tools/union_smoke.py）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import socket
import threading
import time

import pytest
import uvicorn

from app.tuangou.union_client import (
    UNION_BASE_PATH,
    MeituanUnionClient,
    UnionAPIError,
    sign_request,
)
from app.tuangou.union_adapter import MeituanUnionAdapter, parse_party
from tests.tuangou.fake_union_gateway import FAKE_APPKEY, FAKE_SECRET, build_gateway


# ---- 仿真网关（真 HTTP 服务，module 级起一次）------------------------------

def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def gateway_url():
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(
        build_gateway(), host="127.0.0.1", port=port, log_level="warning"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    deadline = time.time() + 10
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("仿真网关启动超时")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    t.join(timeout=5)


def _client(base, key=FAKE_APPKEY, secret=FAKE_SECRET):
    return MeituanUnionClient(key, secret, base_url=base)


# ---- 1. 签名算法向量 --------------------------------------------------------

def test_signature_vector():
    """独立复算：Content-MD5=base64(md5(body))；HMAC-SHA256(stringToSign)。"""
    body = b'{"pageNo":1}'
    ts = "1720000000000"
    path = UNION_BASE_PATH + "query_coupon"
    md5_b64, sig = sign_request("sec", "app", ts, path, body)

    assert md5_b64 == base64.b64encode(hashlib.md5(body).digest()).decode()
    expect = ("POST\n" + md5_b64 + "\nS-Ca-App:app\nS-Ca-Timestamp:" + ts + "\n" + path)
    assert sig == base64.b64encode(
        hmac.new(b"sec", expect.encode(), hashlib.sha256).digest()).decode()


def test_party_parse():
    assert parse_party("海底捞欢聚4人餐") == (4, 4)
    assert parse_party("西贝家庭2-3人套餐") == (2, 3)
    assert parse_party("3~5人烤肉") == (3, 5)
    assert parse_party("畅吃券") == (1, 99)   # 无人数 → 未知档


# ---- 2/3. 客户端 + 适配器全链路（签名被网关严格校验）------------------------

def test_query_coupon_roundtrip(gateway_url):
    c = _client(gateway_url)
    data = c.query_coupon(latitude=39.996, longitude=116.474)
    assert data["code"] == 0
    assert len(data["data"]) == 4
    c.close()


def test_bad_secret_rejected(gateway_url):
    """密钥错误 → 网关签名校验拒绝（code=401）。证明签名真的被校验。"""
    c = _client(gateway_url, secret="wrong_secret")
    with pytest.raises(UnionAPIError) as ei:
        c.query_coupon()
    assert ei.value.code == 401
    c.close()


def test_adapter_mapping(gateway_url):
    c = _client(gateway_url)
    adapter = MeituanUnionAdapter(c, grid_id="wangjing", sid="tab1")
    deals = adapter.fetch_deals()

    # 不可售的「过期4人餐」被丢弃：4 条源数据 → 3 条入库
    assert len(deals) == 3
    by_title = {d.title: d for d in deals}

    hdl = by_title["海底捞欢聚4人餐"]
    assert hdl.group_price_cents == 39800          # 398.0 元 → 39800 分
    assert hdl.list_price_cents == 52000           # originalPrlice 拼写兼容
    assert hdl.party_size == (4, 4)                # 标题解析人数
    assert hdl.has_menu_detail is False            # 联盟无菜品明细 → 降级
    assert hdl.deeplink.startswith("https://dpurl.cn/fake/sku_hdl_001")
    assert "sid=tab1" in hdl.deeplink              # 渠道追踪参数带上

    assert by_title["西贝家庭2-3人套餐"].party_size == (2, 3)
    assert by_title["丰茂烤串畅吃券"].party_size == (1, 99)

    rests = adapter.fetch_restaurants()
    assert {r.brand for r in rests} == {"海底捞", "西贝莜面村", "丰茂烤串"}
    assert all(r.id.startswith("r_union_") for r in rests)
    c.close()


# ---- 4. DealStore 环境切源 + 回退保活 ---------------------------------------

def _with_env(monkeypatch, base, secret=FAKE_SECRET):
    monkeypatch.setenv("TUANGOU_SOURCE", "union")
    monkeypatch.setenv("MEITUAN_UNION_APPKEY", FAKE_APPKEY)
    monkeypatch.setenv("MEITUAN_UNION_SECRET", secret)
    monkeypatch.setenv("MEITUAN_UNION_BASE", base)


def test_store_uses_union_source(monkeypatch, gateway_url):
    from app.tuangou.store import DealStore
    _with_env(monkeypatch, gateway_url)
    store = DealStore()
    assert store.source == "union"
    assert len(store.deals) == 3
    assert all(d.id.startswith("u_") for d in store.deals)
    # 到手价链路可用：随便取一个单元算价不炸、金额为分
    unit = store.units[0]
    from app.tuangou.pricing import compute_deal_price
    r = compute_deal_price(unit.deals[0])
    assert isinstance(r.final_price, int) and r.final_price > 0


def test_store_falls_back_on_bad_secret(monkeypatch, gateway_url):
    """密钥错 → 联盟拉取失败 → 回退 Mock 保活（服务不挂、数据可用）。"""
    from app.tuangou.store import DealStore
    _with_env(monkeypatch, gateway_url, secret="wrong")
    store = DealStore()
    assert "mock" in store.source and "回退" in store.source
    assert len(store.deals) == 4                    # Mock 种子
    assert all(not d.id.startswith("u_") for d in store.deals)


def test_store_falls_back_on_unreachable_gateway(monkeypatch):
    from app.tuangou.store import DealStore
    _with_env(monkeypatch, "http://127.0.0.1:1")    # 不可达端口
    store = DealStore()
    assert "回退" in store.source
    assert len(store.deals) == 4


def test_store_mock_by_default(monkeypatch):
    from app.tuangou.store import DealStore
    monkeypatch.delenv("TUANGOU_SOURCE", raising=False)
    store = DealStore()
    assert store.source == "mock"


# ---- 5. 真实网关冒烟（有真实密钥才跑）--------------------------------------

@pytest.mark.skipif(
    not (os.environ.get("MEITUAN_UNION_REAL_APPKEY") and os.environ.get("MEITUAN_UNION_REAL_SECRET")),
    reason="未配置真实联盟密钥（MEITUAN_UNION_REAL_APPKEY/SECRET）",
)
def test_real_gateway_smoke():
    c = MeituanUnionClient(
        os.environ["MEITUAN_UNION_REAL_APPKEY"],
        os.environ["MEITUAN_UNION_REAL_SECRET"],
    )
    data = c.query_coupon(page_size=1)
    assert data["code"] == 0
    c.close()
