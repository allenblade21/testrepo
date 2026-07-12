"""环境变量驱动的运行配置（生产化基础）。

所有配置均有安全默认值，开发/测试零配置可跑；部署时通过环境变量覆盖。
"""
from __future__ import annotations

import os


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        # 数据快照定时刷新间隔（秒）。0=关闭（开发/测试默认）
        self.refresh_interval_s: int = _int("REFRESH_INTERVAL_S", 0)
        # 每客户端每分钟请求上限。0=不限流（开发/测试默认）
        self.rate_limit_per_min: int = _int("RATE_LIMIT_PER_MIN", 0)
        # CORS 允许来源，逗号分隔；默认 * （比价接口为公开只读）
        self.cors_origins: list[str] = [
            o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()
        ]
        # 管理接口令牌（/admin/refresh）。为空=不校验（仅限开发环境）
        self.admin_token: str = os.getenv("ADMIN_TOKEN", "")


settings = Settings()
