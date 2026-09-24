# Об-ёрт-ка-ж-из-нен-н-ого-цик-ла-ф-ронт-а (в-ё-т-пол-ный-ст-ек-тя-нет-пар-сер-ный-compose)
# Раз-ра-бот-ка-с-гор-яч-им-пер-ез-аг-руз-ком:  cd v2app && npm run dev   (Vite-на-:5173, /api-прок-с-и-ру-ет-ся-на-:8010)

.PHONY: build up down logs restart version

build:      ## собрать-образ-ф-ронт-а
	docker compose build

up:         ## зап-ус-т-ить-ф-ронт-енд (и-об-нов-ить-при-изменениях)
	docker compose up -d --build
	@echo "Готово: http://localhost:8011/v2/ (легаси: http://localhost:8011/)"

down:       ## ост-анов-ить-фронт
	docker compose down

logs:       ## хвост-ло-гов-nginx
	docker compose logs -f --tail=100 frontend

restart:    ## пер-ез-ап-уск-б-ез-пер-ес-бор-ки
	docker compose restart frontend

$(if $(MAKECMDGOALS),,)
