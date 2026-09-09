# ============ 阶段 1：构建前端 ============
FROM node:24-alpine AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ============ 阶段 2：后端 + 托管前端 ============
FROM python:3.11-slim
WORKDIR /app

# 后端依赖
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 后端代码
COPY backend/app/ /app/backend/app/

# 前端产物（由 FastAPI 托管）
COPY --from=frontend-builder /build/dist /app/frontend/dist

ENV PYTHONPATH=/app/backend \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
