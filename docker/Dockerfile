# IDK Clips server image (server or hybrid mode).
#
#   docker build -f docker/Dockerfile -t openclip .                          # API + web interface
#   docker build -f docker/Dockerfile --build-arg WEB_BUILD=false -t openclip-api .   # API only
#
# Status: provided for self-hosting; not yet built or tested by the maintainers.

ARG WEB_BUILD=true

# ---------------------------------------------------------------- web build
FROM node:22-bookworm-slim AS web
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json frontend/
RUN cd frontend && npm ci --no-fund --no-audit
COPY frontend frontend
COPY docs docs
COPY README.md LICENSE CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md ./
# Same-origin API: the backend serves these files itself.
RUN cd frontend && npm run build

# ------------------------------------------------------------------ runtime
FROM python:3.13-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    OPENCLIP_HOST=0.0.0.0 \
    OPENCLIP_DATA_DIR=/data
# FFmpeg is needed in server mode (processing on the server) and for media checks.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 openclip
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY processing processing
RUN pip install ./processing
COPY backend backend

FROM runtime AS final-true
COPY --from=web /src/frontend/out /app/frontend/out

FROM runtime AS final-false

FROM final-${WEB_BUILD}
RUN mkdir -p /data && chown openclip:openclip /data
USER openclip
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"
CMD ["python", "-m", "app"]
