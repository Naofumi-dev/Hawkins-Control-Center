FROM node:22-slim AS web
WORKDIR /web
COPY apps/control-center/package.json apps/control-center/package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/control-center/index.html apps/control-center/tsconfig.json apps/control-center/vite.config.ts ./
COPY apps/control-center/src ./src
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN adduser --disabled-password --gecos "" finder
COPY client_finder /app/client_finder
COPY data/deliverables.json /app/data/deliverables.json
COPY data/source_registry.json /app/data/source_registry.json
COPY --from=web /web/dist /app/web
USER finder
EXPOSE 8088
ENV CLIENT_FINDER_BIND=0.0.0.0
ENV CLIENT_FINDER_WEB_ROOT=/app/web
CMD ["python", "-m", "client_finder", "serve"]
