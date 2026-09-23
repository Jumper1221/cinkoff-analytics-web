#!/usr/bin/env bash
# Синк src/ → cinkoff_parser/app/static + деплой в контейнер + рестарт.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)/src"
DST="/home/mikhail/projects/cinkoff_parser/app/static"
CTR="cinkoff_parser-web-1"

rsync -a --delete "$SRC/" "$DST/"
docker exec "$CTR" mkdir -p /app/static
docker cp "$DST/." "$CTR:/app/static/"
docker restart "$CTR" >/dev/null
sleep 2
curl -s -m 5 http://localhost:8010/healthz && echo " ← сайт жив"
