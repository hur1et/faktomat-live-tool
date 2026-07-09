# Fly.io / Container-Deployment (Plan B, UEBERGABE 3).
#
# Build läuft aus der Repo-Wurzel:  docker build -f deploy/Dockerfile .
# bzw. fly deploy --dockerfile deploy/Dockerfile
#
# items.json und benchmark.json liegen NICHT im Repo (Lizenz). Deploy
# passiert deshalb aus einer Arbeitskopie, in der beide Dateien in der
# Wurzel liegen; sie landen nur im privaten Fly-Registry-Image, nie auf
# GitHub. Fehlt items.json, bricht der Build hier ab - gewollt (fail-loud).

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ server/
COPY client/ client/
COPY scoring/ scoring/
COPY items.json benchmark.json ./

ENV FAKTOMAT_ITEMS=/app/items.json
# FAKTOMAT_DEV hier NIEMALS setzen (Anonymitäts-Gate, siehe Datenschutz-Review).

# --no-access-log ist Pflicht: das Access-Log enthielte Client-IPs und das
# Host-Token aus dem SSE-Query-String; Fly persistiert stdout in Log-Drains.
CMD ["python", "-m", "uvicorn", "server.app:app", \
     "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
