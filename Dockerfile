FROM python:3.12-slim AS runtime

ARG VERSION=dev
LABEL org.opencontainers.image.version=${VERSION}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VERSION=${VERSION}

WORKDIR /app

COPY pyproject.toml README.md ./
COPY request_shock ./request_shock

RUN pip install --no-cache-dir .

USER nobody

ENTRYPOINT ["request-shock"]
