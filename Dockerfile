# Build stage — install dependencies
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage
FROM python:3.12-slim
WORKDIR /app

COPY --from=builder /install /usr/local
COPY app/ app/
COPY scripts/ scripts/
COPY migrations/ migrations/
COPY arp_common.py .
COPY alembic.ini .

# Data files needed by migration script and importer service
COPY Arp_Seasonal_Plan.xlsx .
COPY itelescopesystems.xlsx .
COPY arp_ned_coords.csv .
COPY arp_moon_data.json .
COPY asu.tsv .

RUN useradd -r appuser
USER appuser

EXPOSE 8000
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8000", "app:create_app()"]
