# 小智 Agent 服务镜像（FastAPI + uvicorn）
# 构建：docker build -t xiaozhi-api .
# 运行：docker run -p 8000:8000 --env-file .env xiaozhi-api
FROM python:3.12-slim

WORKDIR /app

# 先装依赖（利用 Docker 层缓存：依赖没变就不重装）
COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt

# 再拷代码与知识库
COPY *.py ./
COPY knowledge ./knowledge

# 可写数据（会话库/日志/索引）落在挂载卷，容器重建不丢
ENV XZ_DATA_DIR=/app/data
RUN mkdir -p /app/data && useradd -m app && chown -R app /app
USER app

EXPOSE 8000

# 健康检查：命中 / 健康接口
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/').status==200 else 1)"

# DASHSCOPE_API_KEY 由运行时通过 --env-file/.env 注入，绝不打进镜像
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
