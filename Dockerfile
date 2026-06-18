FROM python:3.12-slim

RUN pip install uv --no-cache-dir

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY kpi/        ./kpi/
COPY collections/ ./collections/
COPY config.yml  ./

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "sh", "-c", "kpi-update && kpi-sync"]
