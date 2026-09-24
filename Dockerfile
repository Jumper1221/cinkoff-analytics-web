# Многостадийная-сборка-SPA-v2: node-сбор-ка → раз-да-ча-nginx
FROM node:22-slim AS build
WORKDIR /app
COPY v2app/package.json v2app/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY v2app/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html/v2
EXPOSE 8080
