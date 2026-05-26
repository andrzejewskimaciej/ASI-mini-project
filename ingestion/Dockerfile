FROM python:3.10-slim AS base

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# dev: -u dla natychmiastowych logów w docker logs
FROM base AS dev

COPY . .

CMD ["python", "-u", "main.py"]


# prod: standardowe uruchomienie
FROM base AS prod

COPY . .

CMD ["python", "main.py"]