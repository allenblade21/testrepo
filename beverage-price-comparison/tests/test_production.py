"""生产化基础（v0.4.1）专项测试：探针/指标/刷新/限流/CORS/新鲜度。"""
import pytest
from fastapi.testclient import TestClient

from app import main as m
from app.config import settings

client = TestClient(m.app)


def test_health_exposes_ops_fields():
    d = client.get("/health").json()
    assert d["status"] == "ok"
    assert d["version"] == m.VERSION
    assert d["units"] == 116 and d["listings"] == 278
    assert "snapshot_at" in d and "uptime_s" in d
    assert d["rebuilds"] >= 1


def test_compare_includes_price_freshness():
    uid = client.get("/search", params={"q": "永辉"}).json()["results"][0]["id"]
    d = client.get("/compare", params={"unit_id": uid}).json()
    assert d["price_as_of"] == m.store.snapshot_at_iso


def test_metrics_endpoint_shape():
    client.get("/health")   # 保证至少有样本
    d = client.get("/metrics").json()
    assert d["requests_total"] >= 1
    assert set(d["latency_ms"]) == {"p50", "p95", "p99", "samples"}
    assert d["errors_total"] >= 0 and d["rate_limited_total"] >= 0


def test_admin_refresh_rebuilds_snapshot():
    before = client.get("/health").json()
    r = client.post("/admin/refresh")
    assert r.status_code == 200
    after = client.get("/health").json()
    assert after["rebuilds"] == before["rebuilds"] + 1
    assert after["units"] == before["units"] == 116, "重建不得改变数据构成"
    # 单元 ID 由内容哈希派生：重建后旧 ID 仍可比价
    uid = client.get("/search", params={"q": "永辉"}).json()["results"][0]["id"]
    assert client.get("/compare", params={"unit_id": uid}).status_code == 200


def test_admin_refresh_requires_token_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "secret-token")
    assert client.post("/admin/refresh").status_code == 401
    ok = client.post("/admin/refresh", headers={"X-Admin-Token": "secret-token"})
    assert ok.status_code == 200


def test_rate_limit_enforced_and_health_exempt(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_min", 3)
    m._rate_buckets.clear()
    codes = [client.get("/search", params={"q": "可乐"}).status_code for _ in range(4)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429, "超过限额必须 429"
    assert client.get("/health").status_code == 200, "健康探针不受限流"
    m._rate_buckets.clear()


def test_rate_limit_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_min", 0)
    m._rate_buckets.clear()
    codes = {client.get("/search").status_code for _ in range(10)}
    assert codes == {200}


def test_cors_headers_present():
    r = client.get("/health", headers={"Origin": "https://example.com"})
    assert r.headers.get("access-control-allow-origin") in ("*", "https://example.com")