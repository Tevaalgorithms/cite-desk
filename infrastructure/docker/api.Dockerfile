# CiteDesk API. Build from the repository root:
#   docker build -f infrastructure/docker/api.Dockerfile -t citedesk-api .
# Add --build-arg EXTRAS="--extra models" to bake in the local embedding model and cross-encoder.
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.10.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
ARG EXTRAS=""
RUN uv sync --locked --no-dev --no-editable --extra postgres ${EXTRAS}
# With the local models, download them now so the container never needs the network to start.
ENV FASTEMBED_CACHE_PATH=/opt/models
RUN mkdir -p /opt/models && if [ -n "${EXTRAS}" ]; then \
      /app/.venv/bin/python -c "from citedesk.adapters.local_models import CrossEncoderReranker, FastEmbedEmbedder; FastEmbedEmbedder(); CrossEncoderReranker()"; \
    fi \
    && chmod -R a+rX /opt/models

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /opt/models /opt/models
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 FASTEMBED_CACHE_PATH=/opt/models
USER app
WORKDIR /home/app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "citedesk.api.main:create_production_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
