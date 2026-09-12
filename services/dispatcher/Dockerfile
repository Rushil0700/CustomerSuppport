# syntax=docker/dockerfile:1
# Build from the repository root:
#   docker build -f services/dispatcher/Dockerfile -t support/dispatcher .

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies are copied and installed before the source so an edit to the
# service code does not invalidate the (slow) dependency layer.
COPY services/dispatcher/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

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
COPY services/dispatcher/dispatcher /app/dispatcher

USER support
EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8004/health || exit 1

CMD ["uvicorn", "dispatcher.main:app", "--host", "0.0.0.0", "--port", "8004", "--no-access-log"]
