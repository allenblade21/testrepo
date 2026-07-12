FROM python:3.11-slim

WORKDIR /app

# 先装依赖，充分利用构建缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8077

# 非 root 运行
RUN useradd -m appuser
USER appuser

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8077/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8077"]
