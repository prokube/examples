FROM node:24-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tsconfig.json vite.config.ts eslint.config.js ./
COPY public ./public
COPY src ./src

ARG CLEF_MODEL_NAME=clef-flash
RUN npm run build \
    && sed -i "s/name=\"clef-model-name\" content=\"\"/name=\"clef-model-name\" content=\"${CLEF_MODEL_NAME}\"/" dist/index.html

FROM nginxinc/nginx-unprivileged:1.29-alpine

COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

ENV CLEF_POLICY=heuristic \
    CLEF_UPSTREAM=clef-flash-predictor:80

EXPOSE 8080
