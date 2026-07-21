#!/data/data/com.termux/files/usr/bin/bash
# 安卓本地后端一键脚本（在 Termux 内运行）。
# 用法：
#   bash tools/android_termux_run.sh setup   # 首次：装依赖（可能需 20~40 分钟，rust 编译 pydantic_core）
#   bash tools/android_termux_run.sh start   # 起服务 → 本机 http://127.0.0.1:8077
# 详细说明与排障见 docs/安卓本地后端方案.md
set -e
cd "$(dirname "$0")/.."

case "${1:-start}" in
  setup)
    echo "== ① 更新包源并安装 Python/编译工具 =="
    pkg update -y
    pkg install -y python rust binutils
    echo "== ② 安装精简依赖（无 reportlab；pydantic_core 走 rust 本地编译）=="
    pip install --upgrade pip
    pip install -r requirements-android.txt
    echo "== ③ 自检 =="
    python - <<'PY'
import fastapi, pydantic, uvicorn, httpx
from app.export_pdf import PDF_AVAILABLE
print("fastapi", fastapi.__version__, "| pydantic", pydantic.VERSION)
print("PDF 导出可用:", PDF_AVAILABLE, "（False=精简模式，/export 返回 501，其余全量可用）")
PY
    echo "== setup 完成。运行: bash tools/android_termux_run.sh start =="
    ;;
  start)
    echo "起服务：本机浏览器/薄壳 APK 打开 http://127.0.0.1:8077"
    echo "（团购健康探针 /api/tuangou/health；Ctrl+C 停止）"
    exec python -m uvicorn app.main:app --host 127.0.0.1 --port 8077
    ;;
  test)
    python -m pytest -q
    ;;
  *)
    echo "用法: bash tools/android_termux_run.sh {setup|start|test}"; exit 2 ;;
esac
