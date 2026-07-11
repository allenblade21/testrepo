"""京东适配器（Mock）。"""
from __future__ import annotations

from ..models import JD
from .base import MockAdapter


class JDAdapter(MockAdapter):
    platform = JD
