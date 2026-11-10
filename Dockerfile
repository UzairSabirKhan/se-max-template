# One image for every host (Railway, Render, local Docker).
# Stage 1 builds the React editor; stage 2 runs FastAPI, which serves the editor, the API and /shop.

# ---- 1. Frontend ---------------------------------------------------------------------------------
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# Production builds always use the real API (mock mode is opt-in for local work only).
ENV VITE_API_MODE=live
RUN npm run build

# ---- 2. Backend ----------------------------------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

RUN pip install --no-cache-dir uv==0.11.29
WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY --from=web /web/dist ./web/dist

RUN useradd --create-home --uid 10001 scrapeonce && chown -R scrapeonce /app
USER scrapeonce

EXPOSE 8000
# ONE worker: the scheduler runs inside the app and must not start twice (docs/adr 0004).
# $PORT is set by Railway and Render; 8000 when run locally.
# --no-proxy-headers: uvicorn must never replace the client address with X-Forwarded-For, which the
# client controls (it even does so by default for requests from 127.0.0.1). Fake addresses would
# bypass the assistant's rate limit (D-22). The app reads only the platform proxy's own entry itself
# (app/api/agent.py, _client_key).
CMD ["sh", "-c", "exec /app/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-proxy-headers"]
