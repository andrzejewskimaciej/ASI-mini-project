FROM python:3.10-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# dev z hot-reload
FROM base AS dev

# watchfiles potrzebne na Windows bind-mountach (NTFS/WSL2)
RUN pip install --no-cache-dir watchfiles==0.21.0

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--reload", \
     "--reload-dir", "/app"]


# prod: tylko kod aplikacji, bez testów
FROM base AS prod

# kopiujemy tylko app/, pomijamy test_backend.py i locustfile.py
COPY ./app ./app

EXPOSE 8000

# 2 workery dla lepszej współbieżności
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2"]