# Cinkoff Analytics Web

Фронтенд-SPA (Vue 3 + Chart.js, без билд-степа) для аналитики заказов поставщика.

**Связь с парсером**: этот репозиторий — только статика/вьюхи. Их раздаёт бэкенд
`cinkoff_parser/app/web.py` (FastAPI, read-only JSON API к единственной Postgres-БД).
Данные здесь не копируются: все запросы — в ту же БД, что и парсер.

## Структура

- `src/index.html` — каркас (подключает Vue и Chart.js локально из `src/vendor/`)
- `src/js/app.js` — роутинг вкладок + тема
- `src/js/views/*.js` — по файлу на вкладку (dashboard, orders, items, remnants, prices)
- `src/js/common.js` — api(), форматтеры, цвета, хелперы графиков
- `src/css/app.css` — вся тема (светлая по умолчанию, тёмная через [data-theme=dark])

## Деплой (пока ручной)

```bash
./deploy.sh   # rsync src/ → cinkoff_parser/app/static/ + docker cp + restart web
```

## Правила (см. полный список: cinkoff_parser/docs/ANALYTICS_ROADMAP.md)

1. Одна фича = одна задача: сделать → проверить в headless-браузере → закоммитить.
2. Без билд-степа: только ES-модули и vendored-библиотеки (работает в закрытой сети).
3. Новая вкладка = 1 файл в `src/js/views/` + 1 строка в `app.js: VIEWS`.


## Продакшн-деплой (Compose, 24.09.2026)

Весь-фронт-енд-разв-ор-ач-ивается-Docker-Compose-О-Д-Н-О-Й-ко-ман-дой-из-КОРНЯ-этого-реп-о:

```bash
docker compose up -d --build     # соб-рать-и-зап-устить (перв-ый-раз-~1 мин)
docker compose up -d --build     # же-ко-м-анда-для-обновления-после-правок (перес-бор-ка-только-изменённых-слоёв)
docker compose logs -f frontend  # смот-реть-лог-и-nginx
docker compose down              # ост-ановить
```

Что-происходит: многостадийный-Dockerfile (node:22-соб-ирает-v2app-через-`npm ci && npm run build` → nginx:1.27-alpine-раз-даёт-дис-т).
nginx-прок-сирует-`/api/*`-и-`/healthz`-на-бэк-енд-`web:8000`-из-сети-`cinkoff_parser_default`
(стек-пар-сер-а-должен-быть-запущен). Порт-: **8011**-—-`/v2/`-новый-фронт, `/`-легаси-через-бэк.
Кэш: асс-еты-с-хеш-ем-—-immutable-год, index.html-—-no-cache.

Треб-ов-ания: networks-внеш-няя-`cinkoff_parser_default`-должна-сущ-еств-овать (п-ояв-ля-ет-ся-после-перв-о-го-зап-уска-па-р-сер-но-го-compose; если-нет-—-`docker network create cinkoff_parser_default`).

Раз-ра-бот-ка-без-сборки: `cd v2app && npm run dev`-—-Vite-дев-с-ер-вер-:5173-с-горяч-им-перез-агруз-ком-и-прок-си-`/api`-на-:8010.
