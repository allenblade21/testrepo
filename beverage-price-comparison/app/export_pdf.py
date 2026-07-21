"""比价结果 PDF 导出。

用 reportlab + 内置中文 CID 字体（STSong-Light，无需外部字体文件）把一组
比价结果渲染为带时间戳的 PDF。金额单位「分」→ 展示「元」。

**reportlab 是可选依赖**（C 扩展，安卓 Termux 等环境可能装不上）：缺失时
本模块仍可导入、服务照常启动，仅 ``/export`` 返回 501 明确降级（见
``PDF_AVAILABLE`` 与 docs/安卓本地后端方案.md）。勿把 reportlab 的 import
挪回模块顶层硬依赖——那会让精简环境整个后端起不来。
"""
from __future__ import annotations

import io

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    PDF_AVAILABLE = True
except ImportError:  # 精简环境（如安卓 Termux）无 reportlab：导出降级，其余全量可用
    PDF_AVAILABLE = False

if PDF_AVAILABLE:
    _FONT = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(_FONT))


def _yuan(cents: int) -> str:
    return f"¥{cents / 100:.2f}"


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName=_FONT, fontSize=18, spaceAfter=4),
        "meta": ParagraphStyle("m", parent=ss["Normal"], fontName=_FONT, fontSize=9,
                               textColor=colors.HexColor("#5c7076"), spaceAfter=2),
        "h2": ParagraphStyle("h", parent=ss["Heading2"], fontName=_FONT, fontSize=12,
                             spaceBefore=12, spaceAfter=4),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontName=_FONT, fontSize=9,
                             textColor=colors.HexColor("#5c7076"), spaceAfter=4),
        "note": ParagraphStyle("n", parent=ss["Normal"], fontName=_FONT, fontSize=8,
                              textColor=colors.HexColor("#9aa1a7")),
    }


def build_comparison_pdf(results: list[dict], timestamp: str, price_as_of: str = "") -> bytes:
    """把比价结果列表渲染为 PDF 字节。

    results: /compare 返回结构的列表；timestamp: 展示用时间戳字符串。
    """
    if not PDF_AVAILABLE:
        raise RuntimeError("reportlab 未安装，PDF 导出不可用（精简环境降级）")
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=18 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            title="饮品比价结果")
    flow = [
        Paragraph("饮品比价结果", st["title"]),
        Paragraph(f"导出时间：{timestamp}", st["meta"]),
        Paragraph(f"共 {len(results)} 项比价 · 阿里闪购 / 京东 / 美团 · 演示数据（Mock），非真实价格", st["meta"]),
    ]
    if price_as_of:
        flow.append(Paragraph(f"价格快照：{price_as_of}", st["meta"]))
    flow.append(Spacer(1, 6))

    for i, r in enumerate(results, 1):
        bev = r["beverage"]
        flow.append(Paragraph(f"{i}. {bev['name']}", st["h2"]))
        sub = f"🏪 {bev['merchant']} · 数量 ×{r.get('quantity', 1)} · " \
              f"{'含配送费' if r.get('include_delivery', True) else '不含配送费'}"
        if r.get("first_order"):
            sub += f" · 首单券：{'/'.join(r['first_order'])}"
        flow.append(Paragraph(sub, st["sub"]))

        # 平台对比表：平台 / 到手价 / 明细 / 状态
        head = ["平台", "到手价", "明细", "状态"]
        rows = [head]
        for p in r["platforms"]:
            detail = "  ".join(
                f"{b['label']}{'−' if b['amount'] < 0 else ''}{_yuan(abs(b['amount']))}"
                for b in p["breakdown"]
            )
            price = _yuan(p["final_price"]) if p["orderable"] else "—"
            status = ("✔最便宜" if p["platform"] == r["cheapest"]
                      else ("可下单" if p["orderable"] else p["note"]))
            rows.append([p["platform"], price, Paragraph(detail, st["note"]), status])

        tbl = Table(rows, colWidths=[24 * mm, 22 * mm, 96 * mm, 26 * mm])
        style = [
            ("FONT", (0, 0), (-1, -1), _FONT, 8.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f4")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#41565d")),
            ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe7e9")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        # 高亮最便宜行
        for ri, p in enumerate(r["platforms"], 1):
            if p["platform"] == r["cheapest"]:
                style.append(("BACKGROUND", (0, ri), (-1, ri), colors.HexColor("#e6f5ec")))
                style.append(("TEXTCOLOR", (1, ri), (1, ri), colors.HexColor("#0e8a45")))
        tbl.setStyle(TableStyle(style))
        flow.append(tbl)

        if r.get("cheapest") and r.get("savings_vs_max"):
            flow.append(Spacer(1, 3))
            flow.append(Paragraph(
                f"→ 选「{r['cheapest']}」最省，比最贵平台省 {_yuan(r['savings_vs_max'])}", st["sub"]))

    doc.build(flow)
    return buf.getvalue()
