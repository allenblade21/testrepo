"""比价结果 PDF 导出（POST /export）测试。"""
from fastapi.testclient import TestClient

from app.export_pdf import build_comparison_pdf
from app.main import _compute_comparison, app

client = TestClient(app)


def _uid(q, merchant):
    res = client.get("/search", params={"q": q, "limit": 100}).json()["results"]
    return next(r["id"] for r in res if merchant in r["merchant"])


# ---- PDF 构建（单元级）------------------------------------------------------

def test_build_pdf_bytes_valid():
    r = _compute_comparison(_uid("可乐", "永辉"))
    pdf = build_comparison_pdf([r], "2026-07-13 22:58:00")
    assert pdf[:5] == b"%PDF-", "必须是合法 PDF 头"
    assert pdf.rstrip().endswith(b"%%EOF")
    assert len(pdf) > 1000


def test_build_pdf_multiple_items():
    rs = [_compute_comparison(_uid("可乐", "永辉")),
          _compute_comparison(_uid("瑞幸", "瑞幸"), qty=2)]
    pdf = build_comparison_pdf(rs, "2026-07-13 22:58:00")
    assert pdf[:5] == b"%PDF-"


# ---- /export 端点 ----------------------------------------------------------

def test_export_returns_pdf_with_timestamped_filename():
    uid = _uid("可乐", "永辉")
    r = client.post("/export", json={"items": [{"unit_id": uid, "qty": 1}]})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:5] == b"%PDF-"
    cd = r.headers["content-disposition"]
    assert "attachment" in cd
    # 文件名带时间戳（形如 comparison_YYYYMMDD_HHMMSS.pdf）
    import re
    assert re.search(r"comparison_\d{8}_\d{6}\.pdf", cd)
    assert r.headers["x-export-timestamp"]


def test_export_multiple_items_all_included():
    items = [
        {"unit_id": _uid("可乐", "永辉"), "qty": 1},
        {"unit_id": _uid("农夫山泉", "永辉"), "qty": 2, "include_delivery": False},
        {"unit_id": _uid("瑞幸", "瑞幸"), "qty": 1, "first_order": "美团"},
    ]
    r = client.post("/export", json={"items": items})
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
    # 多项应比单项 PDF 更大（内容更多）
    single = client.post("/export", json={"items": items[:1]})
    assert len(r.content) > len(single.content)


def test_export_empty_400():
    assert client.post("/export", json={"items": []}).status_code == 400
    assert client.post("/export", json={}).status_code == 400


def test_export_unknown_unit_404():
    """含未知 unit_id → 复用比价校验，404。"""
    assert client.post("/export", json={"items": [{"unit_id": "不存在"}]}).status_code == 404


def test_export_over_limit_400():
    uid = _uid("可乐", "永辉")
    r = client.post("/export", json={"items": [{"unit_id": uid}] * 101})
    assert r.status_code == 400


def test_export_respects_qty_and_first_order():
    """导出重算逻辑与 /compare 一致（同参数 PDF 可生成，且首单券场景不报错）。"""
    uid = _uid("可乐", "永辉")
    r = client.post("/export", json={"items": [
        {"unit_id": uid, "qty": 2, "include_delivery": True, "first_order": "阿里闪购,京东,美团"}]})
    assert r.status_code == 200 and r.content[:5] == b"%PDF-"
