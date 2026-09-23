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
