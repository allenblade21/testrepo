"""平台适配器接口。

每个平台一个实现，向上层提供统一的取数能力。当前均为 Mock 实现
（从 SQLite 种子数据读取）。将来接入真实数据源（官方 API / 合规采集）时，
只需新增/替换实现，业务层（匹配、算价、比价）无需改动。
"""
from __future__ import annotations

import abc
import sqlite3

from ..db import load_delivery, load_listings
from ..models import DeliveryPolicy, Listing


class PlatformAdapter(abc.ABC):
    """平台适配器统一接口。"""

    platform: str

    @abc.abstractmethod
    def fetch_listings(self) -> list[Listing]:
        """拉取本平台饮品条目。"""

    @abc.abstractmethod
    def fetch_delivery(self) -> DeliveryPolicy:
        """拉取本平台配送策略。"""


class MockAdapter(PlatformAdapter):
    """基于 SQLite 种子数据的 Mock 适配器基类。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def fetch_listings(self) -> list[Listing]:
        return load_listings(self._conn, self.platform)

    def fetch_delivery(self) -> DeliveryPolicy:
        return load_delivery(self._conn, self.platform)
