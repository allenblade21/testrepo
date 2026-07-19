"""团购数据仓库：把「适配器抽取 → 建索引 → 构建可比单元」封装为可重建快照。

复用饮品 DataStore 范式（ADR-002 / 内存快照）：``DealStore.rebuild()`` 可随时
原子重建。单元 ID 由内容哈希派生（确定性），重建不改已有单元 ID。

数据源由环境变量选择（真实 CPS API 就绪即切，代码零改动）：
  TUANGOU_SOURCE                逗号分隔多源：mock / union(美团联盟) /
                                douyin(抖音生活服务) / alimama(淘宝联盟)。默认 mock
  MEITUAN_UNION_APPKEY/SECRET[/BASE/SID]     美团联盟密钥
  DOUYIN_CLIENT_KEY/SECRET[/BASE/ACCOUNT_ID] 抖音生活服务密钥
  ALIMAMA_APPKEY/SECRET/ADZONE_ID[/BASE]     淘宝联盟密钥 + 推广位
  TUANGOU_GRID                  取数商圈网格（默认 wangjing）

弹性策略：**单个真实源失败只跳过该源**（其余源照常）；全部真实源失败/为空
则**回退 Mock 保活**（与饮品刷新失败不拖垮服务同策略）。
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from .adapters import MockMeituanTuangouAdapter, TuangouAdapter
from .matching import build_comparable_deals
from .models import ComparableDeal, GroupDeal, Restaurant

_log = logging.getLogger("bpc.tuangou")


def _build_adapters() -> list[tuple[str, TuangouAdapter]]:
    """按环境变量装配 (源名, 适配器) 列表。配置缺失的源记警告并跳过。"""
    sources = [s.strip().lower()
               for s in os.environ.get("TUANGOU_SOURCE", "mock").split(",") if s.strip()]
    grid = os.environ.get("TUANGOU_GRID", "wangjing")
    out: list[tuple[str, TuangouAdapter]] = []
    for source in sources:
        if source == "mock":
            out.append(("mock", MockMeituanTuangouAdapter()))
        elif source == "union":
            key, sec = os.environ.get("MEITUAN_UNION_APPKEY", ""), os.environ.get("MEITUAN_UNION_SECRET", "")
            if not (key and sec):
                _log.warning("event=source_config_missing source=union")
                continue
            from .union_adapter import MeituanUnionAdapter
            from .union_client import UNION_BASE_URL, MeituanUnionClient
            out.append(("union", MeituanUnionAdapter(
                MeituanUnionClient(key, sec, base_url=os.environ.get("MEITUAN_UNION_BASE", UNION_BASE_URL)),
                grid_id=grid, sid=os.environ.get("MEITUAN_UNION_SID", ""))))
        elif source == "douyin":
            key, sec = os.environ.get("DOUYIN_CLIENT_KEY", ""), os.environ.get("DOUYIN_CLIENT_SECRET", "")
            if not (key and sec):
                _log.warning("event=source_config_missing source=douyin")
                continue
            from .douyin_adapter import DouyinLifeAdapter
            from .douyin_client import DOUYIN_BASE_URL, DouyinLifeClient
            out.append(("douyin", DouyinLifeAdapter(
                DouyinLifeClient(key, sec,
                                 account_id=os.environ.get("DOUYIN_ACCOUNT_ID", ""),
                                 base_url=os.environ.get("DOUYIN_BASE", DOUYIN_BASE_URL)),
                grid_id=grid)))
        elif source == "alimama":
            key, sec = os.environ.get("ALIMAMA_APPKEY", ""), os.environ.get("ALIMAMA_SECRET", "")
            adzone = os.environ.get("ALIMAMA_ADZONE_ID", "")
            if not (key and sec and adzone):
                _log.warning("event=source_config_missing source=alimama")
                continue
            from .alimama_adapter import AlimamaAdapter
            from .alimama_client import ALIMAMA_BASE_URL, AlimamaClient
            out.append(("alimama", AlimamaAdapter(
                AlimamaClient(key, sec, adzone, base_url=os.environ.get("ALIMAMA_BASE", ALIMAMA_BASE_URL)),
                grid_id=grid)))
        else:
            _log.warning("event=unknown_source source=%s", source)
    return out


class DealStore:
    def __init__(self) -> None:
        self.rebuild_count = 0
        self.source = "mock"
        self.rebuild()

    def rebuild(self) -> None:
        """全量重建快照。先在局部完成构建，再原子替换属性。"""
        now = datetime.now(timezone.utc)
        as_of = now.isoformat(timespec="seconds")

        restaurants: list[Restaurant] = []
        deals: list[GroupDeal] = []
        ok: list[str] = []
        failed: list[str] = []
        for name, adapter in _build_adapters():
            try:
                fetched = adapter.fetch_deals()
                for d in fetched:
                    d.price_as_of = as_of  # 统一戳快照时间（团购时效性强）
                    deals.append(d)
                restaurants.extend(adapter.fetch_restaurants())
                ok.append(name)
                if name != "mock" and not fetched:
                    _log.warning("event=source_empty source=%s", name)
            except Exception:  # noqa: BLE001 — 单源失败只跳过该源
                _log.exception("event=source_fetch_failed source=%s", name)
                failed.append(name)

        if not deals:  # 全部真实源失败/为空 → 回退 Mock 保活
            fallback_of = ",".join(failed) or "配置"
            _log.warning("event=all_sources_failed 回退 mock (%s)", fallback_of)
            mock = MockMeituanTuangouAdapter()
            for d in mock.fetch_deals():
                d.price_as_of = as_of
                deals.append(d)
            restaurants.extend(mock.fetch_restaurants())
            source = f"mock({fallback_of}失败回退)"
        else:
            source = "+".join(ok)
            if failed:
                source += f"（{','.join(failed)}失败跳过）"

        # 多源可能产生同品牌伪门店重复 → 按 id 去重（首见为准）
        dedup: dict[str, Restaurant] = {}
        for r in restaurants:
            dedup.setdefault(r.id, r)
        restaurants = list(dedup.values())

        units = build_comparable_deals(deals)
        self.source = source

        self.restaurants = restaurants
        self.restaurants_by_id = dedup
        self.deals = deals
        self.deals_by_id = {d.id: d for d in deals}
        self.units = units
        self.units_by_id = {u.id: u for u in units}
        self.snapshot_at = now
        self.rebuild_count += 1

    @property
    def snapshot_at_iso(self) -> str:
        return self.snapshot_at.isoformat(timespec="seconds")
