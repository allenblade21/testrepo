"""精简模式（无 reportlab，安卓本地部署）降级测试。

锁住 v0.8.4 的可选依赖设计：reportlab 缺失时——
  1. `app.export_pdf` 仍可导入、`PDF_AVAILABLE=False`（服务能启动，不崩）；
  2. `build_comparison_pdf` 抛 RuntimeError（明确报错，非 NameError）；
  3. `POST /export` 返回 **501** 与清晰文案（非 500/崩溃）；
  4. 其余接口（搜索/比价/团购）完全不受影响。
在装有 reportlab 的环境通过 import 拦截模拟缺失。
"""
from __future__ import annotations

import builtins
import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def lite_export(monkeypatch):
    """模拟 reportlab 不存在：拦截 import 并重载 export_pdf。"""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "reportlab" or name.startswith("reportlab."):
            raise ImportError(f"No module named '{name}' (simulated lite env)")
        return real_import(name, *args, **kwargs)

    saved = {k: v for k, v in sys.modules.items() if k.startswith("reportlab")}
    for k in saved:
        del sys.modules[k]
    monkeypatch.setattr(builtins, "__import__", fake_import)

    import app.export_pdf as ep
    importlib.reload(ep)
    assert ep.PDF_AVAILABLE is False
    yield ep

    # 还原：撤销拦截（monkeypatch 自动）后重载回全量模式
    monkeypatch.undo()
    sys.modules.update(saved)
    importlib.reload(ep)
    assert ep.PDF_AVAILABLE is True


def test_module_importable_without_reportlab(lite_export):
    """缺 reportlab 时模块可导入、旗标为 False——服务能启动。"""
    assert lite_export.PDF_AVAILABLE is False


def test_build_raises_clear_runtime_error(lite_export):
    with pytest.raises(RuntimeError) as ei:
        lite_export.build_comparison_pdf([], "2026-07-19 12:00:00")
    assert "reportlab" in str(ei.value)


def test_export_endpoint_501_and_others_unaffected(monkeypatch):
    """/export → 501 且文案清晰；搜索/比价/团购接口照常。"""
    import app.main as main_mod
    monkeypatch.setattr(main_mod, "PDF_AVAILABLE", False)
    c = TestClient(main_mod.app)

    uid = c.get("/search", params={"q": "瑞幸", "limit": 5}).json()["results"][0]["id"]
    r = c.post("/export", json={"items": [{"unit_id": uid}]})
    assert r.status_code == 501
    assert "reportlab" in r.json()["detail"]

    # 其余链路不受影响
    assert c.get("/compare", params={"unit_id": uid}).status_code == 200
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/api/tuangou/health").status_code == 200
    tg = c.get("/api/tuangou/search").json()
    assert tg["total"] >= 1
