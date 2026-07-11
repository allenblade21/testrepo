"""美团适配器（Mock）。"""
from __future__ import annotations

from ..models import MEITUAN
from .base import MockAdapter


class MeituanAdapter(MockAdapter):
    platform = MEITUAN
