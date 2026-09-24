#!/usr/bin/env bash
# Деплой-SPA-v2: build → rsync → /snap/bin/docker cp → restart → healthz. Легаси-деплой-НЕ-трогает.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT/v2app"
npm run build
rsync -a --delete "$ROOT/v2app/dist/" /home/mikhail/projects/cinkoff_parser/app/static_v2/
/snap/bin/docker exec cinkoff_parser-web-1 mkdir -p /app/static_v2
/snap/bin/docker cp /home/mikhail/projects/cinkoff_parser/app/static_v2/. cinkoff_parser-web-1:/app/static_v2/
/snap/bin/docker restart cinkoff_parser-web-1 >/dev/null
sleep 3
curl -s -m 5 -o /dev/null -w 'v2: %0http_code\n' http://localhost:8010/v2/
curl -s -m 5 http://localhost:8010/healthz && echo " ← сайт жив"
