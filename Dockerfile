FROM python:3.12-slim

RUN pip install uv --no-cache-dir

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen

COPY kpi/        ./kpi/
COPY collections/ ./collections/
COPY config.yml  ./
COPY update_duckdb.py sync_notion.py main.py ./

ENV PYTHONUNBUFFERED=1

CMD ["uv", "run", "sh", "-c", \
     "python update_duckdb.py && python sync_notion.py"]
