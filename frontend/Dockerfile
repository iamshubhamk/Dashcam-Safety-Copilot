# Dashboard image: build the Vite app, then serve the static files with nginx.
# nginx also proxies /api to the API container, so the browser sees one origin (no CORS).
FROM node:22.21.1-bookworm-slim AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ENV VITE_API_MODE=http
RUN npx vite build

FROM nginx:1.28.0-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
