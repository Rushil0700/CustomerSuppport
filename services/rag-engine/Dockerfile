# syntax=docker/dockerfile:1
# Build from the repository root:
#   docker build -f services/rag-engine/Dockerfile -t support/rag-engine .

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies are copied and installed before the source so an edit to the
# service code does not invalidate the (slow) dependency layer.
COPY services/rag-engine/requirements.txt ./requirements.txt
# CPU-only torch: the default wheel drags in ~2GB of CUDA we never use.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
 && pip install --no-cache-dir -r requirements.txt

COPY libs/support_common /build/libs/support_common
RUN pip install --no-cache-dir /build/libs/support_common


FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 support

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY services/rag-engine/rag_engine /app/rag_engine
COPY support-kb /app/support-kb

# Cache the embedding model into the image so a cold pod does not download
# it on first request.
ENV HF_HOME=/home/support/.cache/huggingface
RUN mkdir -p /data/chroma $HF_HOME && chown -R support:support /data $HF_HOME
USER support
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

EXPOSE 8002

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8002/health || exit 1

CMD ["uvicorn", "rag_engine.main:app", "--host", "0.0.0.0", "--port", "8002", "--no-access-log"]
