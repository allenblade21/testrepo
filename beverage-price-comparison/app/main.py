"""FastAPI 入口 + 比价编排（v0.4.1 生产化基础）。

启动时 DataStore 完成「建库→适配器抽取→归并→匹配」快照；支持手动
（POST /admin/refresh）与定时（REFRESH_INTERVAL_S）重建。中间件提供
请求日志、延迟指标、限流；CORS 与管理令牌由环境变量配置。

接口：
  GET  /search          关键词召回（相关度+分页）
  GET  /merchants       聚合 API：按商户名聚合商品名列表
  GET  /compare         到手价比价（qty/配送口径/first_order）
  GET  /health /metrics 探针与运行指标
  POST /admin/refresh   重建数据快照（ADMIN_TOKEN 保护）
  GET  / , /test        双界面入口
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import Counter, deque
from contextlib import asynccontextmanager

from datetime import datetime, timezone, timedelta

import geo_data
import seed_data
from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response

from .config import settings
from .export_pdf import PDF_AVAILABLE, build_comparison_pdf
from .geo import merchant_rank, resolve_grid
from .matching import _normalize, search_units
from .models import ComparableUnit, Promotion
from .pricing import compute_price
from .store import DataStore
from .tuangou.routes import router as tuangou_router

# 展示用东八区时间（导出时间戳）
_CST = timezone(timedelta(hours=8))

VERSION = "0.4.1"
_WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web")
_START_TIME = time.time()

logging.basicConfig(level=logging.INFO, format="%(asctime)s level=%(levelname)s %(message)s")
_log = logging.getLogger("bpc")

# ---- 数据快照（可重建）----------------------------------------------------
store = DataStore()

# 兼容既有测试的模块级别名（指向首次快照；请求处理一律走 store.*）
_units: list[ComparableUnit] = store.units
_units_by_id = store.units_by_id


# ---- 生命周期：定时刷新任务 -------------------------------------------------
async def _refresh_loop() -> None:
    while True:
        await asyncio.sleep(settings.refresh_interval_s)
        try:
            store.rebuild()
            _log.info("event=refresh rebuilds=%d units=%d", store.rebuild_count, len(store.units))
        except Exception:  # noqa: BLE001 — 刷新失败不拖垮服务，保留旧快照
            _log.exception("event=refresh_failed（保留旧快照继续服务）")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    task = None
    if settings.refresh_interval_s > 0:
        task = asyncio.create_task(_refresh_loop())
        _log.info("event=refresh_scheduler_started interval_s=%d", settings.refresh_interval_s)
    yield
    if task:
        task.cancel()


app = FastAPI(title="饮品比价系统", version=VERSION, lifespan=_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# 团购团餐比价（新垂直 G-R1）：/api/tuangou/* 数据接口，与饮品下层隔离（ADR-010/013）
app.include_router(tuangou_router)

# ---- 可观测 + 限流中间件 ----------------------------------------------------
_metrics = {
    "requests_total": 0,
    "errors_total": 0,
    "rate_limited_total": 0,
    "by_path": Counter(),
    "latencies_ms": deque(maxlen=2000),
}
_rate_buckets: dict[str, deque] = {}


def _rate_limited(client: str) -> bool:
    """滑动窗口限流：每客户端每 60s 至多 rate_limit_per_min 个请求。"""
    limit = settings.rate_limit_per_min
    if limit <= 0:
        return False
    now = time.monotonic()
    bucket = _rate_buckets.setdefault(client, deque())
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


@app.middleware("http")
async def observability(request: Request, call_next):
    path = request.url.path
    client = request.client.host if request.client else "-"
    if not path.startswith("/health") and _rate_limited(client):
        _metrics["rate_limited_total"] += 1
        return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
    start = time.perf_counter()
    response = await call_next(request)
    dur_ms = (time.perf_counter() - start) * 1000
    _metrics["requests_total"] += 1
    _metrics["by_path"][path] += 1
    _metrics["latencies_ms"].append(dur_ms)
    if response.status_code >= 500:
        _metrics["errors_total"] += 1
    _log.info("method=%s path=%s status=%d dur_ms=%.1f client=%s",
              request.method, path, response.status_code, dur_ms, client)
    return response


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, int(len(values) * pct))
    return round(values[idx], 2)


# ---- 探针与运维接口 ----------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": VERSION,
        "units": len(store.units),
        "listings": len(store.listings),
        "snapshot_at": store.snapshot_at_iso,
        "rebuilds": store.rebuild_count,
        "uptime_s": int(time.time() - _START_TIME),
    }


@app.get("/metrics")
def metrics():
    lat = list(_metrics["latencies_ms"])
    return {
        "requests_total": _metrics["requests_total"],
        "errors_total": _metrics["errors_total"],
        "rate_limited_total": _metrics["rate_limited_total"],
        "latency_ms": {"p50": _percentile(lat, 0.50), "p95": _percentile(lat, 0.95),
                       "p99": _percentile(lat, 0.99), "samples": len(lat)},
        "top_paths": dict(_metrics["by_path"].most_common(10)),
    }


@app.post("/admin/refresh")
def admin_refresh(request: Request):
    """重建数据快照。设置 ADMIN_TOKEN 后须带 X-Admin-Token 请求头。"""
    if settings.admin_token and request.headers.get("X-Admin-Token") != settings.admin_token:
        raise HTTPException(status_code=401, detail="管理令牌无效")
    store.rebuild()
    return {"ok": True, "rebuilds": store.rebuild_count,
            "units": len(store.units), "snapshot_at": store.snapshot_at_iso}


# ---- 地理接口（PRD §4：定位与网格）------------------------------------------

def _check_grid(grid: str) -> None:
    if grid and grid not in geo_data.GRIDS:
        raise HTTPException(status_code=400, detail=f"未知商圈网格: {grid}")


def _in_grid(merchant: str, grid: str) -> bool:
    """商户是否服务该网格（Mock：按归属网格；真实阶段按配送范围判定）。"""
    geo = geo_data.MERCHANT_GEO.get(merchant)
    return geo is not None and geo[2] == grid


@app.get("/grids")
def grids():
    """商圈网格列表（界面手动选择器数据源）。"""
    return {"grids": [
        {"grid_id": gid, "name": name, "lat": lat, "lng": lng}
        for gid, (name, lat, lng) in geo_data.GRIDS.items()
    ]}


@app.get("/grid/resolve")
def grid_resolve(lat: float = Query(..., ge=-90, le=90),
                 lng: float = Query(..., ge=-180, le=180)):
    """坐标 → 商圈网格。坐标仅在本次请求中使用，不落库（隐私最小化）。"""
    hit = resolve_grid(lat, lng)
    if hit is None:
        return {"in_service": False,
                "message": "当前位置不在服务区（试点商圈：望京/国贸/中关村/五道口），请手动选择商圈"}
    return {"in_service": True, **hit}


# ---- 业务接口 ---------------------------------------------------------------

def _unit_brief(unit: ComparableUnit) -> dict:
    return {
        "id": unit.id,
        "merchant": unit.merchant,
        "name": unit.name,
        "brand": unit.brand,
        "spec": unit.spec,
        "type": unit.type,
        "platforms": [l.platform for l in unit.listings],
    }


@app.get("/search")
def search(
    q: str = Query("", description="关键词（商品名/品牌/商户名，空=浏览全库）"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    grid: str = Query("", description="商圈网格 ID；传入时只返回该网格内可送达商户的商品"),
):
    """全商户产品库搜索：相关度排序 + 分页 + 可选网格过滤。"""
    _check_grid(grid)
    hits = search_units(store.units, q)
    if grid:
        hits = [u for u in hits if _in_grid(u.merchant, grid)]
    page = hits[offset : offset + limit]
    return {
        "query": q,
        "total": len(hits),          # 命中总数
        "count": len(page),          # 本页返回数
        "offset": offset,
        "results": [_unit_brief(u) for u in page],
    }


def _product_brief(u: ComparableUnit) -> dict:
    return {"id": u.id, "merchant": u.merchant, "name": u.name,
            "type": u.type, "platforms": [l.platform for l in u.listings]}


def _sorted_units(units: list[ComparableUnit]) -> list[ComparableUnit]:
    return sorted(units, key=lambda x: (-len(x.listings), x.name))


def _merchant_groups(q: str, grid: str):
    """按商户名（模糊）聚合可比单元；网格过滤 + 地点排名分排序。

    返回已排序的 [(商户, 该商户单元列表, rank_or_None)]。
    有 grid 时按 PRD §4.3 排名分降序，否则按商品数降序。供 /merchants 与
    /discover 共用，避免逻辑重复。
    """
    nq = _normalize(q)
    groups: dict[str, list[ComparableUnit]] = {}
    for u in store.units:
        if nq and nq not in _normalize(u.merchant):
            continue
        if grid and not _in_grid(u.merchant, grid):
            continue
        groups.setdefault(u.merchant, []).append(u)

    max_sales = max(
        (geo_data.MERCHANT_GEO[m][4] for m in groups if m in geo_data.MERCHANT_GEO),
        default=0,
    ) if grid else 0

    result = []
    for m, us in groups.items():
        rank = None
        if grid:
            avg_platforms = sum(len(u.listings) for u in us) / len(us)
            rank = merchant_rank(m, grid, avg_platforms, max_sales)
        result.append((m, us, rank))

    if grid:
        result.sort(key=lambda t: -t[2]["score"])          # 排名分降序
    else:
        result.sort(key=lambda t: (-len(t[1]), t[0]))      # 商品数降序
    return result


@app.get("/merchants")
def merchants_aggregate(
    q: str = Query("", description="商户名关键词，空=全部商户"),
    grid: str = Query("", description="商圈网格 ID；传入时只返回网格内商户并按地点排名分排序"),
):
    """聚合 API：按商户名聚合，返回每个命中商户下的全部商品名列表。

    传入 grid 时：过滤为该网格内可送达商户，并按 PRD §4.3 排名分降序，
    附带距离与可解释因子。（无分页；界面分页版见 /discover）
    """
    _check_grid(grid)
    groups = _merchant_groups(q, grid)
    merchants = []
    for m, us, rank in groups:
        entry = {
            "merchant": m,
            "product_count": len(us),
            "products": [
                {"id": u.id, "name": u.name, "type": u.type,
                 "platforms": [l.platform for l in u.listings]}
                for u in _sorted_units(us)
            ],
        }
        if rank is not None:
            entry["rank"] = rank
        merchants.append(entry)

    resp = {"query": q, "count": len(merchants), "merchants": merchants}
    if grid:
        resp["grid"] = {"grid_id": grid, "name": geo_data.GRIDS[grid][0]}
    return resp


@app.get("/api/discover")
def discover(
    q: str = Query("", description="商户名关键词（模糊匹配），空=全部商户"),
    grid: str = Query("", description="商圈网格 ID；传入时按 GPS 网格过滤 + 地点排名"),
    merchant_limit: int = Query(20, ge=1, le=50, description="返回商户数上限"),
    product_limit: int = Query(100, ge=1, le=200, description="商品每页数量"),
    product_offset: int = Query(0, ge=0, description="商品分页偏移"),
):
    """商户发现 API（GPS + 模糊商户搜索 + 商品分页）——供「商户发现」界面用。

    - 商户：模糊匹配、可选网格过滤与地点排名，最多返回 merchant_limit（默认 20）家；
    - 商品：命中商户下的全部商品扁平化为一个列表，按 product_limit（默认 100）分页。
    """
    _check_grid(grid)
    groups = _merchant_groups(q, grid)
    merchant_total = len(groups)
    shown = groups[:merchant_limit]

    merchants = []
    flat: list[ComparableUnit] = []
    for m, us, rank in shown:
        entry = {"merchant": m, "product_count": len(us)}
        if rank is not None:
            entry["rank"] = rank
        merchants.append(entry)
        flat.extend(_sorted_units(us))   # 商品顺序随商户排名 → 商户内商品序

    product_total = len(flat)
    page = flat[product_offset : product_offset + product_limit]

    resp = {
        "query": q,
        "merchant_total": merchant_total,     # 命中商户总数
        "merchant_count": len(merchants),     # 本次返回商户数（≤ merchant_limit）
        "merchant_limit": merchant_limit,
        "merchants": merchants,
        "product_total": product_total,       # 命中商户下商品总数
        "product_offset": product_offset,
        "product_count": len(page),           # 本页商品数
        "products": [_product_brief(u) for u in page],
    }
    if grid:
        resp["grid"] = {"grid_id": grid, "name": geo_data.GRIDS[grid][0]}
    return resp


def _compute_comparison(unit_id: str, qty: int = 1, include_delivery: bool = True,
                        first_order: str = "") -> dict:
    """比价编排（供 /compare 与 /export 共用）。未找到→404，跨商户→409。"""
    unit = store.units_by_id.get(unit_id)
    if unit is None:
        raise HTTPException(status_code=404, detail="未找到该饮品")
    if len({l.merchant for l in unit.listings}) != 1:
        raise HTTPException(status_code=409, detail="可比单元跨商户，拒绝比价")

    first_order_set = {p.strip() for p in first_order.split(",") if p.strip()}
    platforms = []
    for listing in unit.listings:
        min_order = seed_data.STORE_MIN_ORDER.get((listing.merchant, listing.platform), 0)
        coupon = None
        if listing.platform in first_order_set:
            cfg = seed_data.FIRST_ORDER_COUPON.get(listing.platform)
            if cfg:
                coupon = Promotion(kind="首单券", desc=cfg[0], value=cfg[1], threshold=cfg[2])
        result = compute_price(
            listing, store.delivery[listing.platform], quantity=qty,
            include_delivery=include_delivery, min_order=min_order, first_order_coupon=coupon,
        )
        platforms.append({
            "platform": result.platform, "merchant": listing.merchant,
            "final_price": result.final_price, "subtotal": result.subtotal,
            "discount_total": result.discount_total, "delivery_fee": result.delivery_fee,
            "orderable": result.orderable, "note": result.note,
            "breakdown": [{"label": ln.label, "amount": ln.amount} for ln in result.lines],
        })

    orderable = [p for p in platforms if p["orderable"]]
    cheapest = min(orderable, key=lambda p: p["final_price"]) if orderable else None
    savings = None
    if cheapest and len(orderable) > 1:
        highest = max(orderable, key=lambda p: p["final_price"])
        savings = highest["final_price"] - cheapest["final_price"]

    platforms.sort(key=lambda p: (not p["orderable"], p["final_price"]))
    return {
        "beverage": _unit_brief(unit),
        "quantity": qty,
        "include_delivery": include_delivery,
        "first_order": sorted(first_order_set),
        "price_as_of": store.snapshot_at_iso,
        "platforms": platforms,
        "cheapest": cheapest["platform"] if cheapest else None,
        "savings_vs_max": savings,
    }


@app.get("/compare")
def compare(
    unit_id: str,
    qty: int = Query(1, ge=1, le=99),
    include_delivery: bool = True,
    first_order: str = Query("", description="当日尚未下过单的平台，逗号分隔；这些平台享每日首单券"),
):
    return _compute_comparison(unit_id, qty, include_delivery, first_order)


@app.post("/export")
def export_pdf(payload: dict = Body(..., description='{"items":[{"unit_id","qty","include_delivery","first_order"}]}')):
    """把一组比价结果导出为带时间戳的 PDF（附件下载）。

    items 为界面累积的会话比价记录；服务端按同一算价逻辑重算，保证 PDF 与
    界面一致。文件名与页眉均带时间戳。
    """
    if not PDF_AVAILABLE:
        raise HTTPException(status_code=501,
                            detail="PDF 导出在当前环境不可用（未安装 reportlab，精简部署降级）")
    items = payload.get("items") or []
    if not items:
        raise HTTPException(status_code=400, detail="没有可导出的比价结果")
    if len(items) > 100:
        raise HTTPException(status_code=400, detail="单次导出最多 100 项")

    results = []
    for it in items:
        uid = it.get("unit_id")
        if not uid:
            continue
        results.append(_compute_comparison(
            uid,
            qty=int(it.get("qty", 1) or 1),
            include_delivery=bool(it.get("include_delivery", True)),
            first_order=str(it.get("first_order", "")),
        ))
    if not results:
        raise HTTPException(status_code=400, detail="没有有效的比价条目")

    now = datetime.now(_CST)
    ts_display = now.strftime("%Y-%m-%d %H:%M:%S")
    ts_file = now.strftime("%Y%m%d_%H%M%S")
    pdf = build_comparison_pdf(results, ts_display, price_as_of=store.snapshot_at_iso)

    filename = f"比价结果_{ts_file}.pdf"
    from urllib.parse import quote
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            # filename* 用 RFC5987 编码中文名，兼容各浏览器下载
            "Content-Disposition": f"attachment; filename=comparison_{ts_file}.pdf; "
                                   f"filename*=UTF-8''{quote(filename)}",
            "X-Export-Timestamp": ts_file,
        },
    )


# ---- 界面入口 -------------------------------------------------------------
# /         正式客户比价界面（app.html）
# /discover 商户发现界面（GPS + 模糊商户搜索 + 商品分页，discover.html）
# /test     测试 + 报表控制台（内部，test.html）

@app.get("/")
def customer_app():
    return FileResponse(os.path.join(_WEB_DIR, "app.html"))


@app.get("/discover")
def discover_page():
    return FileResponse(os.path.join(_WEB_DIR, "discover.html"))


@app.get("/tuangou")
def tuangou_page():
    """团购团餐比价界面（G-R3；数据走 /api/tuangou/*，ADR-013 分路径）。"""
    return FileResponse(os.path.join(_WEB_DIR, "tuangou.html"))


@app.get("/test")
def test_console():
    return FileResponse(os.path.join(_WEB_DIR, "test.html"))
