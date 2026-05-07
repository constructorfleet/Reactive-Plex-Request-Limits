FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

FROM base AS dev

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      build-essential \
      curl \
      git \
      openssh-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY request_shock ./request_shock
COPY tests ./tests
COPY tools ./tools

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -e '.[dev]'

FROM base AS runtime

COPY pyproject.toml README.md ./
COPY request_shock ./request_shock

RUN pip install --no-cache-dir .

USER nobody

ENTRYPOINT ["request-shock"]
