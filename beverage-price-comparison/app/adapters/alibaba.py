"""阿里闪购适配器（Mock）。"""
from __future__ import annotations

from ..models import ALIBABA
from .base import MockAdapter


class AlibabaAdapter(MockAdapter):
    platform = ALIBABA
