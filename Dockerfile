FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY autoops ./autoops
COPY connector_fixtures ./connector_fixtures
COPY data ./data
COPY mock_data ./mock_data
COPY README.md .

EXPOSE 8000

CMD ["sh", "-c", "python -m autoops ingest mock_data --db data/autoops.db --rebuild && python -m autoops serve --host 0.0.0.0 --port 8000 --db data/autoops.db"]
